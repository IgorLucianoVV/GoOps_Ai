"""Atendimento conversacional: um chat contínuo por cliente e canal, com ATENDIMENTOS dentro dele.

Segue o padrão das plataformas de mercado (Zendesk, Intercom, Blip, Octadesk):
  * WhatsApp/e-mail/Reclame Aqui: uma conversa persistente por identidade do cliente no canal;
  * mensagem nova com atendimento aberto CONTINUA o atendimento (nova triagem com o contexto acumulado — ex.: chegou a
    foto pedida, veio o número do pedido); cobrança enquanto aguarda conta como "cobrança", não como recontato;
  * mensagem após o encerramento abre um atendimento de CONTINUAÇÃO ligado ao anterior (recontato se for o mesmo
    pedido dentro da janela); "obrigado" logo após o encerramento não abre caso novo;
  * atendimento aguardando o cliente é encerrado por inatividade;
  * robô e pessoa no mesmo chat: o robô responde assuntos informativos, coleta evidências e passa para a pessoa.
As horas do chat seguem o relógio dos dados (não o do servidor) para manter a ordem das falas.
"""
from __future__ import annotations

import logging
import random
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from goops_core.db import Database
from goops_core.operations import execute_operation, propose_operation
from goops_core.permissions import Principal, agent_principal, require_permission
from goops_core.runtime_config import get_section
from goops_core.support_catalog import CHANNELS, INTENTS
from goops_core.util import jdump, jload, new_id, now_iso
from data_platform.analytics.nlp import normalize
from data_platform.storage import Lakehouse

from . import triage
from .service import (HISTORY_WINDOW_DAYS, History, SupportData, _damage_rates, _dt, _iso, _row, triage_contact)

log = logging.getLogger("goops.support.conversations")
OPEN = ("pending_human", "pending_approval", "awaiting_customer")
_COURTESY = re.compile(r"^(ok+|okay|obrigad[oa]s?|muito obrigad[oa]|valeu|vlw|beleza|blz|certo|perfeito|show|top|"
                       r"entendi|combinado|grat[oa]|tudo bem|ta bom|ok obrigad[oa])( (obrigad[oa]|valeu|entao))?$")
HANDOVER = {"whatsapp": "Recebemos sua mensagem 🙌 Um atendente vai continuar por aqui em instantes.",
            "email": "Recebemos sua mensagem. Um atendente vai responder por este e-mail em breve.",
            "reclameaqui": None}   # canal público: sem resposta automática
CLOSING = {"support_reshipment": "Tudo certo: geramos o reenvio do seu pedido. O novo rastreio chega por aqui.",
           "support_exchange": "Sua troca foi aprovada! Enviamos o código de postagem para devolução.",
           "support_carrier_ticket": "A transportadora retornou o chamado e confirmou a entrega. Qualquer coisa, é só chamar!",
           "support_cancel_order": "Pedido cancelado e estorno solicitado. O valor aparece em até 2 faturas.",
           "inconsistente": "Analisamos as informações e não identificamos o problema relatado. Se puder nos enviar mais "
                            "detalhes, reabrimos o atendimento.",
           None: "Qualquer outra dúvida, é só chamar por aqui!"}


def is_courtesy(text: Optional[str]) -> bool:
    t = normalize(text)
    return bool(t) and len(t) <= 40 and bool(_COURTESY.match(t))


def mask_handle(channel: str, handle: Optional[str]) -> str:
    """Exibição minimizada da identidade no canal (últimos dígitos do telefone, inicial do e-mail)."""
    h = str(handle or "")
    if channel == "whatsapp":
        digits = re.sub(r"\D", "", h)
        return f"+55 ({digits[2:4]}) •••••-{digits[-4:]}" if len(digits) >= 8 else "WhatsApp"
    if channel == "email" and "@" in h:
        user, dom = h.split("@", 1)
        return f"{user[:1]}•••@{dom}"
    return h or CHANNELS.get(channel, channel)


# ---------------------------------------------------------------------------------------------- mensagens
def post_message(c, *, conversation_id: str, contact_id: Optional[str], direction: str, author_type: str,
                 author: str, text: str, sent_at: datetime, channel: str, attachments: Optional[list] = None,
                 generated_by: Optional[str] = None, is_demo: bool = False) -> str:
    mid = new_id("MSG")
    c.execute("INSERT INTO support_messages (id, conversation_id, contact_id, direction, author_type, author, text, "
              "attachments, sent_at, channel, processed, is_demo, generated_by, created_at) "
              "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
              (mid, conversation_id, contact_id, direction, author_type, author, text, jdump(attachments or []),
               _iso(sent_at), channel, int(is_demo), generated_by, now_iso()))
    return mid


def _last_out(c, case_id: str) -> Optional[datetime]:
    r = c.fetchone("SELECT MAX(sent_at) AS t FROM support_messages WHERE contact_id = ? AND direction = 'out'", (case_id,))
    return _dt(r["t"]) if r and r["t"] else None


def refresh_conversation(c, conv_id: str) -> None:
    last = c.fetchone("SELECT sent_at, text, author_type FROM support_messages WHERE conversation_id = ? AND "
                      "author_type <> 'note' ORDER BY sent_at DESC, created_at DESC LIMIT 1", (conv_id,))
    last_in = c.fetchone("SELECT MAX(sent_at) AS t FROM support_messages WHERE conversation_id = ? AND direction = 'in'",
                         (conv_id,))["t"]
    last_out = c.fetchone("SELECT MAX(sent_at) AS t FROM support_messages WHERE conversation_id = ? AND direction = 'out'",
                          (conv_id,))["t"]
    unread = c.fetchone("SELECT COUNT(*) AS n FROM support_messages WHERE conversation_id = ? AND direction = 'in' "
                        "AND sent_at > ?", (conv_id, last_out or ""))["n"]
    case = c.fetchone("SELECT id, status FROM support_contacts WHERE conversation_id = ? ORDER BY received_at DESC LIMIT 1",
                      (conv_id,))
    n = c.fetchone("SELECT COUNT(*) AS n FROM support_contacts WHERE conversation_id = ?", (conv_id,))["n"]
    c.execute("UPDATE support_conversations SET last_message_at = ?, last_message_preview = ?, last_author_type = ?, "
              "last_inbound_at = ?, unread = ?, current_case_id = ?, status = ?, cases_count = ?, updated_at = ? WHERE id = ?",
              (last["sent_at"] if last else None, (last["text"] or "")[:160] if last else None,
               last["author_type"] if last else None, last_in, unread if case and case["status"] in OPEN else 0,
               case["id"] if case else None, "open" if case and case["status"] in OPEN else "closed", n, now_iso(),
               conv_id))


def data_clock(db: Database) -> datetime:
    r = db.fetchone("SELECT MAX(sent_at) AS t FROM support_messages")
    return _dt(r["t"]) if r and r["t"] else datetime.utcnow().replace(microsecond=0)


def next_out_time(c, conv_id: str) -> datetime:
    """Horário (relógio dos dados) para uma fala nova: logo após a última fala da conversa."""
    r = c.fetchone("SELECT MAX(sent_at) AS t FROM support_messages WHERE conversation_id = ?", (conv_id,))
    if r and r["t"]:
        return _dt(r["t"]) + timedelta(minutes=1)
    g = c.fetchone("SELECT MAX(sent_at) AS t FROM support_messages")
    return (_dt(g["t"]) if g and g["t"] else datetime.utcnow().replace(microsecond=0)) + timedelta(minutes=1)


# ---------------------------------------------------------------------------------------------- processamento
_TRIAGE_COLS = ("intent", "intent_confidence", "intent_source", "sentiment", "urgency", "priority_score", "is_claim",
                "veracity_score", "veracity_label", "veracity_factors", "routing", "routing_reasons", "suggested_actions",
                "suggested_reply", "reply_generated_by", "systems_touched", "manual_minutes", "saved_minutes",
                "avoidable", "avoidable_reason", "injection_suspected", "order_id", "order_link", "customer_id")
_JSONCOLS = {"veracity_factors", "routing_reasons", "suggested_actions", "systems_touched"}


def _vals(t: Dict[str, Any], cols) -> list:
    return [jdump(t[k]) if k in _JSONCOLS else t[k] for k in cols]


def _needs_evidence(t: Dict[str, Any]) -> bool:
    facts = {f["factor"] for f in (t.get("veracity_factors") or {}).get("factors", [])}
    return bool(facts & {"Sem evidência", "Foto anterior à entrega"})


def _is_open(case: dict, t: datetime, cfg: Dict[str, Any]) -> bool:
    st = case["status"]
    if st in ("auto_resolved", "resolved"):
        end = _dt(case.get("resolved_at"))
        return bool(end and t < end)
    if st == "awaiting_customer":
        lo = case.get("_last_out") or _dt(case["received_at"])
        return t <= lo + timedelta(hours=int(cfg.get("inactivity_close_hours", 48)))
    if case.get("_hist"):
        last_in = _dt(case.get("last_inbound_at")) or _dt(case["received_at"])
        return (t - last_in) <= timedelta(hours=int(cfg.get("continue_window_hours", 72)))
    return True


def _closed_at(case: dict) -> Optional[datetime]:
    if case["status"] in ("auto_resolved", "resolved"):
        return _dt(case.get("resolved_at"))
    return None


def process_messages(db: Database, lake: Lakehouse, actor_label: str = "agent:support", simulate_history: bool = True,
                     live: bool = False) -> Dict[str, Any]:
    cfg, policies = get_section(db, "support"), get_section(db, "policies")
    pending = db.fetchall("SELECT * FROM support_messages WHERE processed = 0 ORDER BY sent_at, external_id")
    if not pending:
        return {"processed": 0}
    data = SupportData(lake)
    hist = History(db.fetchall("SELECT id, received_at, intent, order_id, customer_id, is_claim FROM support_contacts "
                               "WHERE status <> 'new'"))
    pre = []
    for m in pending:
        it = triage.classify_intent(m.get("subject"), m["text"])["intent"]
        o, _ = data.find_order(triage.find_order_reference(m.get("subject"), m["text"]), m.get("customer_ref"),
                               _dt(m["sent_at"]), it, m["text"])
        pre.append({"order_id": (o or {}).get("order_id"), "intent": it})
    rates = _damage_rates(db, data, pre)
    clock = data_clock(db)
    cutoff = clock - timedelta(days=HISTORY_WINDOW_DAYS)
    # IA (fora da transação): Jev desempata intenções ambíguas das mensagens novas (não do histórico da demo)
    from goops_core.runtime_config import effective_settings
    from .assist import ai_classify, case_summary
    settings = effective_settings(db)
    ai: Dict[str, dict] = {}
    if cfg.get("llm_classify_low_confidence") and getattr(settings, "ai_proxy_api_key", None):
        for m in pending:
            if simulate_history and not live and _dt(m["sent_at"]) < cutoff:
                continue
            cls = triage.classify_intent(m.get("subject"), m["text"])
            if (cls["confidence"] < float(cfg.get("min_confidence", 0.6)) or cls["intent"] == "outros") and not is_courtesy(m["text"]):
                r = ai_classify(db, settings, m.get("subject"), m["text"], m["channel"])
                if r and r["confidence"] >= 0.7:
                    ai[m["id"]] = r
    summarize: List[Tuple[str, bool]] = []
    convs: Dict[Tuple[str, str], dict] = {(r["channel"], r["handle"]): r for r in db.fetchall("SELECT * FROM support_conversations")}
    latest: Dict[str, dict] = {}
    for r in db.fetchall("SELECT c.* FROM support_contacts c JOIN support_conversations v ON v.current_case_id = c.id"):
        latest[r["conversation_id"]] = r
    texts: Dict[str, List[dict]] = {}
    touched, hist_cases, auto_actions = set(), [], []
    counts = {"new_cases": 0, "continued": 0, "courtesy": 0, "chases": 0}
    ts = now_iso()
    with db.connect() as c:
        for case in latest.values():
            case["_last_out"] = _last_out(c, case["id"])
        for m in pending:
            t = _dt(m["sent_at"])
            history_mode = simulate_history and not live and t < cutoff
            key = (m["channel"], m["handle"])
            conv = convs.get(key)
            if conv is None:
                conv = {"id": new_id("CNV"), "channel": m["channel"], "handle": m["handle"], "customer_id": m.get("customer_ref"),
                        "cases_count": 0, "is_demo": m["is_demo"]}
                c.execute("INSERT INTO support_conversations (id, channel, handle, customer_id, status, cases_count, is_demo, "
                          "created_at, updated_at) VALUES (?, ?, ?, ?, 'open', 0, ?, ?, ?)",
                          (conv["id"], m["channel"], m["handle"], m.get("customer_ref"), m["is_demo"], ts, ts))
                convs[key] = conv
            touched.add(conv["id"])
            case = latest.get(conv["id"])
            courtesy = is_courtesy(m["text"])
            if case and _is_open(case, t, cfg):
                mode = "continue"
            elif case and courtesy and _closed_at(case) and \
                    t - _closed_at(case) <= timedelta(hours=int(cfg.get("reopen_window_hours", 24))):
                mode = "quiet"
            else:
                mode = "new"

            if mode == "new":
                cid = new_id("CT")
                row = {"id": cid, "channel": m["channel"], "customer_id": m.get("customer_ref") or conv.get("customer_id"),
                       "subject": m.get("subject"), "message": m["text"], "attachments": jload(m.get("attachments"), []),
                       "received_at": m["sent_at"]}
                tr = triage_contact(row, data, hist, rates, cfg, policies)
                if m["id"] in ai and ai[m["id"]]["intent"] != tr["intent"]:
                    r = ai[m["id"]]
                    tr = triage_contact(row, data, hist, rates, cfg, policies,
                                        intent_override=(r["intent"], r["confidence"], "ia"))
                conv["cases_count"] = int(conv.get("cases_count") or 0) + 1
                status = tr["status"]
                first_resp = resolved = None
                if status == "auto_resolved":
                    first_resp = resolved = t + timedelta(minutes=1)
                elif status == "awaiting_customer":
                    first_resp = t + timedelta(minutes=1)
                cols = ["id", "source_key", "external_id", "channel", "subject", "message", "attachments", "received_at",
                        "status", "is_demo", "simulation_truth", "conversation_id", "case_number", "message_count",
                        "follow_up_of", "last_inbound_at", "is_repeat", "repeat_of", "contact_number", "first_response_at",
                        "resolved_at", "resolution", "triaged_at", "created_at", "updated_at", *_TRIAGE_COLS]
                vals = [cid, m["source_key"], m["external_id"], m["channel"], m.get("subject"), m["text"], m.get("attachments") or "[]",
                        m["sent_at"], status, m["is_demo"], m.get("simulation_truth"), conv["id"], conv["cases_count"], 1,
                        case["id"] if case else None, m["sent_at"], tr["is_repeat"], tr["repeat_of"], tr["contact_number"],
                        _iso(first_resp), _iso(resolved), "Resposta automática com dados do pedido" if resolved else None,
                        ts, ts, ts, *_vals(tr, _TRIAGE_COLS)]
                c.execute(f"INSERT INTO support_contacts ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
                c.execute("UPDATE support_messages SET processed = 1, conversation_id = ?, contact_id = ? WHERE id = ?",
                          (conv["id"], cid, m["id"]))
                if conv.get("customer_id") is None and tr.get("customer_id"):
                    conv["customer_id"] = tr["customer_id"]
                    c.execute("UPDATE support_conversations SET customer_id = ? WHERE id = ?", (tr["customer_id"], conv["id"]))
                msg = (f"Triagem: {INTENTS[tr['intent']]['label']} ({tr['intent_confidence']:.0%}) · urgência {tr['urgency']} · "
                       f"{'automático' if tr['routing'] == 'auto' else 'fila humana'}"
                       + (f" · veracidade {tr['veracity_label']} ({tr['veracity_score']})" if tr["veracity_score"] is not None else ""))
                c.execute("INSERT INTO support_events (id, contact_id, actor, event_type, message, data, created_at) "
                          "VALUES (?, ?, ?, 'triage', ?, ?, ?)", (new_id("SEV"), cid, actor_label, msg,
                                                                  jdump({"reasons": tr["routing_reasons"]["reasons"]}), ts))
                if m["id"] in ai and tr["intent_source"] == "ia":
                    c.execute("INSERT INTO support_events (id, contact_id, actor, event_type, message, data, created_at) "
                              "VALUES (?, ?, ?, 'ai', ?, ?, ?)",
                              (new_id("SEV"), cid, actor_label, f"IA (Jev · AI Proxy Gogroup) classificou como "
                               f"{INTENTS[tr['intent']]['label']} ({tr['intent_confidence']:.0%}); as regras estavam em dúvida.",
                               jdump(ai[m["id"]]), ts))
                if tr["routing"] == "human":
                    summarize.append((cid, not history_mode))
                new_case = {**row, **tr, "id": cid, "status": status, "received_at": m["sent_at"], "last_inbound_at": m["sent_at"],
                            "resolved_at": _iso(resolved), "conversation_id": conv["id"], "message_count": 1,
                            "chase_count": 0, "_hist": history_mode, "_last_out": None, "is_demo": m["is_demo"]}
                if tr["routing"] == "auto" or (tr["routing"] == "human" and _needs_evidence(tr) and m["channel"] != "reclameaqui"):
                    post_message(c, conversation_id=conv["id"], contact_id=cid, direction="out", author_type="bot",
                                 author="Agente de Atendimento", text=tr["suggested_reply"], sent_at=t + timedelta(minutes=1),
                                 channel=m["channel"], generated_by="deterministic", is_demo=bool(m["is_demo"]))
                    new_case["_last_out"] = t + timedelta(minutes=1)
                elif HANDOVER.get(m["channel"]):
                    post_message(c, conversation_id=conv["id"], contact_id=cid, direction="out", author_type="bot",
                                 author="Agente de Atendimento", text=HANDOVER[m["channel"]], sent_at=t + timedelta(minutes=1),
                                 channel=m["channel"], generated_by="deterministic", is_demo=bool(m["is_demo"]))
                latest[conv["id"]] = new_case
                texts[cid] = [{"text": m["text"], "attachments": jload(m.get("attachments"), [])}]
                hist.add({**new_case})
                if history_mode:
                    hist_cases.append(cid)
                else:
                    auto_actions += [(cid, a, tr) for a in tr["suggested_actions"] if a.get("auto")]
                counts["new_cases"] += 1
                continue

            # continuação do atendimento aberto ou agradecimento logo após o encerramento
            cid = case["id"]
            c.execute("UPDATE support_messages SET processed = 1, conversation_id = ?, contact_id = ? WHERE id = ?",
                      (conv["id"], cid, m["id"]))
            case["message_count"] = int(case.get("message_count") or 1) + 1
            case["last_inbound_at"] = m["sent_at"]
            if mode == "quiet" or courtesy:
                c.execute("UPDATE support_contacts SET message_count = ?, updated_at = ? WHERE id = ?",
                          (case["message_count"], ts, cid))
                counts["courtesy"] += 1
                continue
            counts["continued"] += 1
            if cid not in texts:
                texts[cid] = [{"text": r["text"], "attachments": jload(r["attachments"], [])} for r in
                              c.fetchall("SELECT text, attachments FROM support_messages WHERE contact_id = ? AND direction = 'in' "
                                         "AND id <> ? ORDER BY sent_at", (cid, m["id"]))]
            texts[cid].append({"text": m["text"], "attachments": jload(m.get("attachments"), [])})
            was = case["status"]
            human_involved = c.fetchone("SELECT COUNT(*) AS n FROM support_messages WHERE contact_id = ? AND author_type = 'human'",
                                        (cid,))["n"] > 0
            if was in ("pending_human", "pending_approval"):
                case["chase_count"] = int(case.get("chase_count") or 0) + (0 if (m.get("attachments") or "[]") != "[]" else 1)
                counts["chases"] += 1
            atts = [a for x in texts[cid] for a in (x["attachments"] or [])]
            row2 = {"id": cid, "channel": case["channel"], "customer_id": case.get("customer_id") or m.get("customer_ref"),
                    "subject": case.get("subject"), "message": "\n".join(x["text"] for x in texts[cid] if not is_courtesy(x["text"])),
                    "attachments": atts, "received_at": case["received_at"]}
            tr = triage_contact(row2, data, hist, rates, cfg, policies,
                                force_intent=case["intent"] if case.get("intent_source") == "humano" else None,
                                force_order=case.get("order_id") if case.get("order_link") == "humano" else None,
                                exclude_case=cid)
            if was == "awaiting_customer":
                status = tr["status"] if tr["status"] != "awaiting_customer" else "awaiting_customer"
            else:
                status = was          # já com uma pessoa: o robô não encerra sozinho
                tr["routing"] = "human"
            upd_cols = [k for k in _TRIAGE_COLS if k not in ("avoidable", "avoidable_reason")]
            c.execute(f"UPDATE support_contacts SET {', '.join(f'{k} = ?' for k in upd_cols)}, status = ?, message_count = ?, "
                      f"chase_count = ?, last_inbound_at = ?, attachments = ?, triaged_at = ?, updated_at = ? WHERE id = ?",
                      (*_vals(tr, upd_cols), status, case["message_count"], case["chase_count"], m["sent_at"], jdump(atts),
                       ts, ts, cid))
            score = f" · {tr['veracity_score']}" if tr["veracity_score"] is not None else ""
            c.execute("INSERT INTO support_events (id, contact_id, actor, event_type, message, data, created_at) "
                      "VALUES (?, ?, ?, 'retriage', ?, ?, ?)",
                      (new_id("SEV"), cid, actor_label,
                       f"Nova mensagem do cliente: triagem atualizada (veracidade {tr['veracity_label']}{score}).", jdump({}), ts))
            case.update({k: tr[k] for k in _TRIAGE_COLS}, status=status)
            if status in ("pending_human", "pending_approval"):
                summarize.append((cid, not case.get("_hist")))
            reply_at = t + timedelta(minutes=1)
            if was == "awaiting_customer" and status == "auto_resolved":
                post_message(c, conversation_id=conv["id"], contact_id=cid, direction="out", author_type="bot",
                             author="Agente de Atendimento", text=tr["suggested_reply"], sent_at=reply_at, channel=m["channel"],
                             generated_by="deterministic", is_demo=bool(m["is_demo"]))
                c.execute("UPDATE support_contacts SET resolved_at = ?, resolution = 'Resposta automática com dados do pedido' "
                          "WHERE id = ?", (_iso(reply_at), cid))
                case["resolved_at"] = _iso(reply_at)
            elif was == "awaiting_customer" and status == "pending_human" and HANDOVER.get(m["channel"]):
                post_message(c, conversation_id=conv["id"], contact_id=cid, direction="out", author_type="bot",
                             author="Agente de Atendimento", text=HANDOVER[m["channel"]], sent_at=reply_at, channel=m["channel"],
                             generated_by="deterministic", is_demo=bool(m["is_demo"]))
            elif not human_involved and atts and (m.get("attachments") or "[]") != "[]" and m["channel"] != "reclameaqui":
                post_message(c, conversation_id=conv["id"], contact_id=cid, direction="out", author_type="bot",
                             author="Agente de Atendimento", text="Recebemos a foto, obrigado! Um atendente já vai analisar.",
                             sent_at=reply_at, channel=m["channel"], generated_by="deterministic", is_demo=bool(m["is_demo"]))
            case["_last_out"] = reply_at if status == "awaiting_customer" else case.get("_last_out")
        if hist_cases:
            _simulate_history(c, hist_cases, cfg, clock)
        for cid in touched:
            refresh_conversation(c, cid)
        # cobrança enquanto aguardava também é contato evitável
        c.execute("UPDATE support_contacts SET avoidable = 1, avoidable_reason = 'Cliente precisou cobrar retorno' "
                  "WHERE chase_count > 0 AND avoidable = 0")
    _write_summaries(db, data, summarize, bool(cfg.get("llm_summary", True)))
    executed = 0
    if auto_actions:
        agent = agent_principal("support")
        for cid, a, tr in auto_actions:
            try:
                op = propose_operation(db, agent, action_type=a["action_type"], contact_id=cid,
                                       description=f"{a['why']} (proposta automática do Agente de Atendimento)",
                                       params={"contact_id": cid, "order_id": tr["order_id"] or "",
                                               "carrier": str((data.orders.get(tr["order_id"] or "") or {}).get("carrier") or ""),
                                               "reason": INTENTS[tr["intent"]]["label"]})
                if op["status"] == "approved":
                    execute_operation(db, agent, op["id"])
                    executed += 1
            except Exception:  # noqa: BLE001
                log.exception("auto action failed for %s", cid)
    by_status = {r["status"]: r["n"] for r in db.fetchall("SELECT status, COUNT(*) AS n FROM support_contacts GROUP BY status")}
    return {"processed": len(pending), **counts, "by_status": by_status, "auto_actions_executed": executed}


def _write_summaries(db: Database, data: SupportData, items: List[Tuple[str, bool]], llm: bool) -> None:
    """Resumo do caso para quem assume (base determinística; IA só reescreve nos casos novos/ao vivo)."""
    from .assist import case_summary
    seen = {}
    for cid, live_case in items:
        seen[cid] = seen.get(cid, False) or live_case
    for cid, live_case in seen.items():
        c = db.fetchone("SELECT * FROM support_contacts WHERE id = ?", (cid,))
        if not c:
            continue
        o = data.orders.get(c.get("order_id") or "")
        out = case_summary(db, c, o, use_llm=llm and live_case)
        db.execute("UPDATE support_contacts SET case_summary = ?, summary_generated_by = ? WHERE id = ?",
                   (out["text"], out["generated_by"], cid))


def _simulate_history(c, case_ids: List[str], cfg: Dict[str, Any], clock: datetime) -> None:
    """Desfecho SIMULADO dos atendimentos antigos da carga inicial: resposta humana (com texto), cobranças
    respondidas, encerramento por inatividade e mensagem de encerramento — tudo no relógio dos dados."""
    rng = random.Random(len(case_ids))
    for cid in case_ids:
        case = c.fetchone("SELECT * FROM support_contacts WHERE id = ?", (cid,))
        if case["status"] in ("auto_resolved", "resolved"):
            c.execute("UPDATE support_contacts SET history_simulated = 1 WHERE id = ?", (cid,))
            continue
        msgs = c.fetchall("SELECT sent_at, direction, author_type FROM support_messages WHERE contact_id = ? ORDER BY sent_at", (cid,))
        first_in = _dt(case["received_at"])
        last_in = max(_dt(x["sent_at"]) for x in msgs if x["direction"] == "in")
        last_any = max(_dt(x["sent_at"]) for x in msgs)
        nxt = c.fetchone("SELECT MIN(received_at) AS t FROM support_contacts WHERE conversation_id = ? AND received_at > ?",
                         (case["conversation_id"], case["received_at"]))["t"]
        upper = (_dt(nxt) - timedelta(minutes=10)) if nxt else clock
        demo = bool(case["is_demo"])
        conv, ch = case["conversation_id"], case["channel"]
        if case["status"] == "awaiting_customer":
            end = min(last_any + timedelta(hours=int(cfg.get("inactivity_close_hours", 48))), max(upper, last_any + timedelta(minutes=5)))
            post_message(c, conversation_id=conv, contact_id=cid, direction="system", author_type="system", author="GoOps",
                         text="Atendimento encerrado por inatividade do cliente (simulado).", sent_at=end, channel=ch, is_demo=demo)
            c.execute("UPDATE support_contacts SET status = 'resolved', resolved_at = ?, resolution = ?, history_simulated = 1 "
                      "WHERE id = ?", (_iso(end), "Encerrado por inatividade do cliente (simulado)", cid))
            continue
        fr = max(first_in + timedelta(minutes=rng.randint(40, 60 * 26)), last_any + timedelta(minutes=1)
                 if last_any < first_in + timedelta(hours=1) else first_in + timedelta(minutes=40))
        if fr > upper:
            fr = max(first_in + timedelta(minutes=5), upper - timedelta(minutes=30))
        resolved = max(fr + timedelta(minutes=30), last_in + timedelta(minutes=rng.randint(60, 60 * 48)))
        resolved = min(resolved, max(upper, fr + timedelta(minutes=10)))
        acts = jload(case["suggested_actions"], []) or []
        key = "inconsistente" if case["veracity_label"] == "inconsistente" else (acts[0]["action_type"] if acts else None)
        post_message(c, conversation_id=conv, contact_id=cid, direction="out", author_type="human", author="Atendente",
                     text=case["suggested_reply"] or "Olá! Estamos verificando.", sent_at=fr, channel=ch, is_demo=demo)
        for x in msgs:
            xt = _dt(x["sent_at"])
            if x["direction"] == "in" and xt > fr and xt < resolved - timedelta(minutes=30):
                post_message(c, conversation_id=conv, contact_id=cid, direction="out", author_type="human", author="Atendente",
                             text="Estamos acompanhando seu caso e retornamos em breve.",
                             sent_at=min(xt + timedelta(minutes=rng.randint(20, 240)), resolved - timedelta(minutes=5)),
                             channel=ch, is_demo=demo)
        post_message(c, conversation_id=conv, contact_id=cid, direction="out", author_type="human", author="Atendente",
                     text=CLOSING.get(key, CLOSING[None]), sent_at=resolved, channel=ch, is_demo=demo)
        res = ("Encerrado após verificação: reclamação não comprovada (simulado)" if key == "inconsistente" else
               f"{acts[0]['title']} realizada pelo atendente (simulado)" if acts else "Respondido pelo atendente (simulado)")
        post_message(c, conversation_id=conv, contact_id=cid, direction="system", author_type="system", author="GoOps",
                     text=f"Atendimento encerrado · {res}", sent_at=resolved + timedelta(seconds=30), channel=ch, is_demo=demo)
        c.execute("UPDATE support_contacts SET status = 'resolved', first_response_at = ?, resolved_at = ?, resolution = ?, "
                  "history_simulated = 1 WHERE id = ?", (_iso(fr), _iso(resolved), res, cid))


# ---------------------------------------------------------------------------------------------- consulta
_CONV_SORTS = {"priority": "COALESCE(k.priority_score, -1) DESC, v.last_message_at DESC",
               "recent": "v.last_message_at DESC", "oldest": "v.last_inbound_at ASC"}


def list_conversations(db: Database, actor: Principal, *, queue: Optional[str] = "open", channel: Optional[str] = None,
                       urgency: Optional[str] = None, intent: Optional[str] = None, q: Optional[str] = None,
                       sort: str = "priority", limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    require_permission(actor, "support:read", "atendimento")
    clauses, params = ["1 = 1"], []
    if queue == "open":
        clauses.append("v.status = 'open'")
    if channel:
        if channel not in CHANNELS:
            from goops_core.errors import ValidationError
            raise ValidationError("Canal inválido.")
        clauses.append("v.channel = ?"); params.append(channel)
    if urgency:
        clauses.append("k.urgency = ?"); params.append(urgency)
    if intent:
        clauses.append("k.intent = ?"); params.append(intent)
    if q:
        term = f"%{q.strip()[:60]}%"
        clauses.append("(v.customer_id LIKE ? OR v.last_message_preview LIKE ? OR EXISTS (SELECT 1 FROM support_contacts x "
                       "WHERE x.conversation_id = v.id AND (x.order_id LIKE ? OR x.message LIKE ?)))")
        params += [term, term, term, term]
    where = " AND ".join(clauses)
    order = _CONV_SORTS.get(sort, _CONV_SORTS["priority"])
    limit, offset = max(1, min(int(limit), 200)), max(0, int(offset))
    base = f"FROM support_conversations v LEFT JOIN support_contacts k ON k.id = v.current_case_id WHERE {where}"
    total = db.fetchone(f"SELECT COUNT(*) AS n {base}", params)["n"]
    rows = db.fetchall(f"SELECT v.*, k.intent, k.urgency, k.priority_score, k.veracity_label, k.veracity_score, k.routing, "
                       f"k.status AS case_status, k.order_id, k.is_repeat, k.chase_count, k.case_number "
                       f"{base} ORDER BY {order} LIMIT {limit} OFFSET {offset}", params)
    for r in rows:
        r["handle_display"] = mask_handle(r["channel"], r["handle"])
        r["display_name"] = f"Cliente {r['customer_id']}" if r.get("customer_id") else "Contato sem cadastro"
        r["last_message_preview"] = triage.mask_pii(r.get("last_message_preview"))
        r["intent_label"] = INTENTS.get(r.get("intent") or "", {}).get("label")
        r["is_demo"] = bool(r["is_demo"])
        r.pop("handle", None)
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def get_conversation(db: Database, actor: Principal, conv_id: str) -> Dict[str, Any]:
    require_permission(actor, "support:read", "atendimento")
    v = db.fetchone("SELECT * FROM support_conversations WHERE id = ?", (conv_id,))
    if not v:
        from goops_core.errors import NotFound
        raise NotFound("Conversa não encontrada.")
    msgs = db.fetchall("SELECT id, contact_id, direction, author_type, author, text, attachments, sent_at, generated_by "
                       "FROM support_messages WHERE conversation_id = ? ORDER BY sent_at, created_at", (conv_id,))
    for m in msgs:
        m["text"] = triage.mask_pii(m["text"])
        m["attachments"] = jload(m["attachments"], [])
    cases = db.fetchall("SELECT id, case_number, received_at, status, intent, urgency, veracity_label, veracity_score, routing, "
                        "order_id, resolution, resolved_at, is_repeat, follow_up_of, chase_count, message_count, history_simulated "
                        "FROM support_contacts WHERE conversation_id = ? ORDER BY received_at", (conv_id,))
    for k in cases:
        k["intent_label"] = INTENTS.get(k.get("intent") or "", {}).get("label")
        k["history_simulated"] = bool(k["history_simulated"])
        k["is_repeat"] = bool(k["is_repeat"])
    others = []
    if v.get("customer_id"):
        others = db.fetchall("SELECT id, channel, status, last_message_at FROM support_conversations WHERE customer_id = ? "
                             "AND id <> ? ORDER BY last_message_at DESC", (v["customer_id"], conv_id))
    last_in = _dt(v.get("last_inbound_at"))
    clock = data_clock(db)
    window = None
    if v["channel"] == "whatsapp" and last_in:
        remaining = (last_in + timedelta(hours=24) - clock).total_seconds() / 3600
        window = {"open": remaining > 0, "hours_left": round(max(0.0, remaining), 1),
                  "rule": "WhatsApp: texto livre até 24 h após a última mensagem do cliente; depois, só modelo aprovado."}
    return {"id": v["id"], "channel": v["channel"], "channel_label": CHANNELS.get(v["channel"]),
            "handle_display": mask_handle(v["channel"], v["handle"]), "customer_id": v.get("customer_id"),
            "display_name": f"Cliente {v['customer_id']}" if v.get("customer_id") else "Contato sem cadastro",
            "status": v["status"], "current_case_id": v.get("current_case_id"), "unread": v["unread"],
            "is_demo": bool(v["is_demo"]), "messages": msgs, "cases": cases, "other_conversations": others,
            "whatsapp_window": window, "clock": _iso(clock)}


def add_note(db: Database, actor: Principal, conv_id: str, text: str, contact_id: Optional[str] = None) -> Dict[str, Any]:
    require_permission(actor, "support:write", "atendimento")
    text = (text or "").strip()
    if not 2 <= len(text) <= 2000:
        from goops_core.errors import ValidationError
        raise ValidationError("A nota deve ter entre 2 e 2000 caracteres.")
    v = db.fetchone("SELECT id, channel, current_case_id, is_demo FROM support_conversations WHERE id = ?", (conv_id,))
    if not v:
        from goops_core.errors import NotFound
        raise NotFound("Conversa não encontrada.")
    with db.connect() as c:
        mid = post_message(c, conversation_id=conv_id, contact_id=contact_id or v["current_case_id"], direction="system",
                           author_type="note", author=actor.name, text=text, sent_at=next_out_time(c, conv_id),
                           channel=v["channel"], is_demo=bool(v["is_demo"]))
    return {"id": mid}


def system_message(db: Database, contact_id: str, text: str) -> None:
    """Fala do sistema no chat (ação proposta/aprovada/executada, mudança de status)."""
    r = db.fetchone("SELECT conversation_id, channel, is_demo FROM support_contacts WHERE id = ?", (contact_id,))
    if not r or not r["conversation_id"]:
        return
    with db.connect() as c:
        post_message(c, conversation_id=r["conversation_id"], contact_id=contact_id, direction="system", author_type="system",
                     author="GoOps", text=text, sent_at=next_out_time(c, r["conversation_id"]), channel=r["channel"],
                     is_demo=bool(r["is_demo"]))
        refresh_conversation(c, r["conversation_id"])
