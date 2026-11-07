"""Turno do Agente de Atendimento: o que um colega faria sozinho a cada rodada, sem ninguém pedir.

1. Processa as mensagens novas (triagem, respostas, ações sem aprovação).
2. Lembra o cliente antes de encerrar por inatividade e encerra quando o prazo vence.
3. Levanta a mão: atendimento sem resposta humana além do SLA → alerta no canal do time com o resumo do caso.
4. Cobra aprovações paradas.
5. Trabalha em equipe: muitas reclamações de entrega da mesma transportadora em 48 h → abre incidente de logística
   e aciona o Supervisor, que chama os agentes de Investigação e Resolução.
6. Manda o resumo do dia no canal do time (uma vez por dia).
Roda pelo agendador (Configurações › Monitor, agendador e retenção) ou pelo botão "Rodar turno agora". Na demo, o
relógio é o dos dados; "avançar o relógio" simula o passar das horas para mostrar lembretes, SLA e encerramentos.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from goops_core.db import Database
from goops_core.incidents import create_incident, list_incidents
from goops_core.permissions import Principal, agent_principal, require_permission
from goops_core.runtime_config import get_section
from goops_core.support_catalog import CHANNELS, INTENTS
from goops_core.util import jdump, jload, new_id, now_iso
from data_platform.storage import Lakehouse

from agents.base import AgentContext, AgentRun
from agents.team_channel import notify

from .conversations import data_clock, post_message, refresh_conversation
from .service import _dt, _iso, process_new

log = logging.getLogger("goops.support.shift")
OFFSET_KEY = "support:clock_offset_hours"
DELIVERY_INTENTS = ("atraso_entrega", "nao_recebido", "avaria", "onde_esta_pedido")


def _offset(db: Database) -> float:
    r = db.fetchone("SELECT value FROM app_settings WHERE key = ?", (OFFSET_KEY,))
    return float(jload(r["value"], 0) or 0) if r else 0.0


def shift_clock(db: Database) -> datetime:
    """Relógio do turno: última mensagem de CLIENTE (não muda com as falas que o agente agenda) + avanço da demo."""
    r = db.fetchone("SELECT MAX(sent_at) AS t FROM support_messages WHERE direction = 'in'")
    base = _dt(r["t"]) if r and r["t"] else data_clock(db)
    return base + timedelta(hours=_offset(db))


def _advance(db: Database, hours: float) -> None:
    val = jdump(_offset(db) + hours)
    db.execute("INSERT INTO app_settings (key, value, updated_by, updated_at) VALUES (?, ?, 'agent:support', ?) "
               "ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
               (OFFSET_KEY, val, now_iso()))


def _done(db: Database, cid: str, kind: str) -> bool:
    return bool(db.fetchone("SELECT id FROM support_events WHERE contact_id = ? AND event_type = ?", (cid, kind)))


def _event(db: Database, cid: str, kind: str, message: str) -> None:
    db.execute("INSERT INTO support_events (id, contact_id, actor, event_type, message, data, created_at) "
               "VALUES (?, ?, 'agent:support', ?, ?, '{}', ?)", (new_id("SEV"), cid, kind, message, now_iso()))


def queue_text(db: Database) -> str:
    rows = db.fetchall("SELECT urgency, COUNT(*) AS n FROM support_contacts WHERE status IN ('pending_human', 'pending_approval', "
                       "'awaiting_customer') GROUP BY urgency")
    by = {r["urgency"]: r["n"] for r in rows}
    total = sum(by.values())
    appr = db.fetchone("SELECT COUNT(*) AS n FROM operations WHERE status = 'pending_approval'")["n"]
    return (f"📥 Fila do atendimento: {total} em aberto (crítica {by.get('critica', 0)}, alta {by.get('alta', 0)}, "
            f"média {by.get('media', 0)}, baixa {by.get('baixa', 0)}). Ações aguardando aprovação: {appr}.")


def digest_text(db: Database, day: Optional[str] = None) -> str:
    day = day or shift_clock(db).strftime("%Y-%m-%d")
    r = db.fetchone("SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN routing = 'auto' THEN 1 ELSE 0 END), 0) AS auto, "
                    "COALESCE(SUM(saved_minutes), 0) AS saved, COALESCE(SUM(is_repeat), 0) AS rep FROM support_contacts "
                    "WHERE substr(received_at, 1, 10) = ?", (day,))
    n = r["n"] or 0
    return (f"🗓️ Resumo do atendimento ({day[8:10]}/{day[5:7]}): {n} atendimentos novos, {r['auto']} resolvidos sem pessoa "
            f"({(r['auto'] / n * 100 if n else 0):.0f}%), {r['rep']} recontatos, ≈{(r['saved'] or 0) / 60:.1f} h poupadas. "
            + queue_text(db))


def _spikes(db: Database, now: datetime, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    since = _iso(now - timedelta(hours=48))
    rows = db.fetchall("SELECT order_id, intent FROM support_contacts WHERE received_at >= ? AND order_id IS NOT NULL "
                       f"AND intent IN ({','.join('?' * len(DELIVERY_INTENTS))})", (since, *DELIVERY_INTENTS))
    if not rows:
        return []
    from data_platform.storage import get_lakehouse
    from .service import SupportData
    data = SupportData(get_lakehouse())
    by: Dict[str, Dict[str, int]] = {}
    for r in rows:
        carrier = (data.orders.get(r["order_id"]) or {}).get("carrier")
        if carrier:
            by.setdefault(carrier, {})
            by[carrier][r["intent"]] = by[carrier].get(r["intent"], 0) + 1
    out = []
    for carrier, cnt in by.items():
        total = sum(cnt.values())
        if total >= int(cfg.get("spike_min_contacts", 5)):
            out.append({"carrier": carrier, "contacts": total, "by_intent": cnt})
    return sorted(out, key=lambda x: -x["contacts"])


def run_shift(db: Database, lake: Lakehouse, actor: Principal, advance_hours: float = 0.0) -> Dict[str, Any]:
    require_permission(actor, "support:write", "atendimento") if actor.kind == "user" else None
    cfg = get_section(db, "support")
    if advance_hours:
        _advance(db, max(0.0, min(float(advance_hours), 168.0)))
    ctx = AgentContext(db, lake)
    out: Dict[str, Any] = {"processed": 0, "reminders": 0, "closed_inactive": 0, "sla_alerts": 0, "approval_reminders": 0,
                           "incidents": [], "digest": False}
    with AgentRun(ctx, "support", "shift", {"advance_hours": advance_hours}) as run:
        tri = process_new(db, lake, "agent:support", live=True)
        out["processed"] = tri.get("processed", 0)
        now = shift_clock(db)
        out["clock"] = _iso(now)
        inact = timedelta(hours=float(cfg.get("inactivity_close_hours", 48)))
        lead = timedelta(hours=float(cfg.get("reminder_before_close_hours", 12)))
        # 2. lembrete e encerramento por inatividade do cliente
        for k in db.fetchall("SELECT id, conversation_id, channel, is_demo FROM support_contacts WHERE status = 'awaiting_customer'"):
            last = db.fetchone("SELECT MAX(sent_at) AS t FROM support_messages WHERE contact_id = ? AND direction = 'out' "
                               "AND author_type <> 'note'", (k["id"],))["t"]
            last_in = db.fetchone("SELECT MAX(sent_at) AS t FROM support_messages WHERE contact_id = ? AND direction = 'in'",
                                  (k["id"],))["t"]
            if not last or (last_in and last_in > last and not _done(db, k["id"], "reminder")):
                continue
            base = _dt(last)
            if now >= base + inact:
                with db.connect() as c:
                    post_message(c, conversation_id=k["conversation_id"], contact_id=k["id"], direction="system",
                                 author_type="system", author="GoOps", text="Atendimento encerrado por inatividade do cliente.",
                                 sent_at=base + inact, channel=k["channel"], is_demo=bool(k["is_demo"]))
                    c.execute("UPDATE support_contacts SET status = 'resolved', resolved_at = ?, resolution = ?, updated_at = ? "
                              "WHERE id = ?", (_iso(base + inact), "Encerrado por inatividade do cliente", now_iso(), k["id"]))
                    refresh_conversation(c, k["conversation_id"])
                _event(db, k["id"], "closed_inactive", "Encerrado por inatividade do cliente (turno do agente).")
                out["closed_inactive"] += 1
            elif lead.total_seconds() > 0 and now >= base + inact - lead and not _done(db, k["id"], "reminder"):
                hours = int(lead.total_seconds() // 3600)
                with db.connect() as c:
                    post_message(c, conversation_id=k["conversation_id"], contact_id=k["id"], direction="out", author_type="bot",
                                 author="Agente de Atendimento",
                                 text=f"Oi! Ainda precisa de ajuda com este atendimento? Se não tivermos retorno em {hours} h, "
                                      "vamos encerrá-lo — é só responder por aqui para continuar.",
                                 sent_at=base + inact - lead, channel=k["channel"], is_demo=bool(k["is_demo"]))
                    refresh_conversation(c, k["conversation_id"])
                _event(db, k["id"], "reminder", "Lembrete de inatividade enviado ao cliente.")
                out["reminders"] += 1
        # 3. SLA de primeira resposta humana estourado → levanta a mão no canal do time
        sla = timedelta(hours=float(cfg.get("sla_first_response_hours", 4)))
        for k in db.fetchall("SELECT id, external_id, received_at, urgency, case_summary, channel FROM support_contacts "
                             "WHERE status = 'pending_human' AND history_simulated = 0 AND first_response_at IS NULL"):
            if now - _dt(k["received_at"]) >= sla and not _done(db, k["id"], "sla_alert"):
                hrs = (now - _dt(k["received_at"])).total_seconds() / 3600
                notify(db, "sla", f"⏰ SLA estourado: atendimento {k['external_id']} ({CHANNELS.get(k['channel'])}) há "
                                  f"{hrs:.0f} h sem resposta de uma pessoa · urgência {k['urgency']}.\n{k['case_summary'] or ''}",
                       contact_id=k["id"], dedupe_key=f"sla:{k['id']}", link=f"/atendimento/{k['id']}")
                _event(db, k["id"], "sla_alert", f"SLA de 1ª resposta estourado ({hrs:.0f} h): time avisado no canal.")
                out["sla_alerts"] += 1
        # 4. aprovações paradas há mais de 2 h (relógio real)
        cutoff = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        for op in db.fetchall("SELECT id, title, contact_id FROM operations WHERE status = 'pending_approval' AND created_at < ?",
                              (cutoff,)):
            if notify(db, "approval_reminder", f"🔔 Aprovação pendente há mais de 2 h: {op['title']}", operation_id=op["id"],
                      contact_id=op["contact_id"], dedupe_key=f"remind:{op['id']}",
                      link=f"/atendimento/{op['contact_id']}" if op["contact_id"] else "/operations"):
                out["approval_reminders"] += 1
        # 5. equipe: pico de reclamações de entrega por transportadora → incidente + Supervisor (Investigação/Resolução)
        open_fp = {i.get("fingerprint") for i in list_incidents(db, only_open=True)}
        for sp in _spikes(db, now, cfg):
            fp = f"support_spike:{sp['carrier']}:{now:%Y-%m-%d}"
            if fp in open_fp or db.fetchone("SELECT id FROM incidents WHERE fingerprint = ?", (fp,)):
                continue
            detail = ", ".join(f"{INTENTS[i]['label']}: {n}" for i, n in sp["by_intent"].items())
            inc = create_incident(db, agent_principal("support"), title=f"Pico de reclamações de entrega · {sp['carrier']}",
                                  description=f"O Agente de Atendimento recebeu {sp['contacts']} reclamações de entrega de pedidos da "
                                              f"{sp['carrier']} nas últimas 48 h ({detail}).",
                                  category="logistics", domain="logistics", severity="high" if sp["contacts"] >= 10 else "medium",
                                  source="agent:support", fingerprint=fp, is_demo=True,
                                  signal={"type": "support_contact_spike", "carrier": sp["carrier"], "contacts": sp["contacts"],
                                          "by_intent": sp["by_intent"], "window_hours": 48, "detected_at": _iso(now)})["incident"]
            run.event("handoff", f"Agente de Atendimento acionou o Supervisor: incidente {inc['id']} ({sp['carrier']}).")
            try:
                from agents.supervisor.agent import Supervisor
                inv = Supervisor(db, lake).investigate(inc["id"], agent_principal("support"), _internal=True)
            except Exception:  # noqa: BLE001
                log.exception("investigation failed for %s", inc["id"])
                inv = {}
            notify(db, "incident", f"🚨 {sp['contacts']} reclamações de entrega da {sp['carrier']} em 48 h. Abri o incidente "
                                   f"{inc['id']} e chamei os agentes de Investigação e Resolução.",
                   incident_id=inc["id"], dedupe_key=f"incident:{inc['id']}", link=f"/incidents/{inc['id']}")
            out["incidents"].append({"incident_id": inc["id"], "carrier": sp["carrier"], "contacts": sp["contacts"],
                                     "workflow": inv.get("status")})
        # 6. resumo do dia (uma vez por dia do relógio dos dados)
        day = now.strftime("%Y-%m-%d")
        if notify(db, "digest", digest_text(db, day), dedupe_key=f"digest:{day}", link="/atendimento"):
            out["digest"] = True
        run.output = out
    return out


def shift_status(db: Database) -> Dict[str, Any]:
    last = db.fetchone("SELECT id, status, output, started_at, finished_at FROM agent_runs WHERE agent_key = 'support' "
                       "AND task = 'shift' ORDER BY started_at DESC LIMIT 1")
    if last:
        last["output"] = jload(last["output"], None)
    return {"last_run": last, "clock": _iso(shift_clock(db)), "offset_hours": _offset(db),
            "scheduler": {k: v for k, v in get_section(db, "scheduler").items() if k.startswith("support")}}
