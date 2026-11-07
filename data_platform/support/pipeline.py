"""Atendimento ao Cliente (Desafio 1) no Lakehouse: fontes de contatos → Bronze → caixa operacional → Gold → métricas.

Fontes:
  * `support_demo_contatos` (conector `support_demo`): contatos SINTÉTICOS de WhatsApp, e-mail e Reclame Aqui gerados a
    partir dos pedidos da Gold (is_demo). Como depende da Gold, é sincronizada nesta etapa (depois da Gold corporativa),
    e não na etapa geral de ingestão.
  * Fontes reais: qualquer fonte `file`/`http_json` com `config.recipe = "support"` e um `field_map` declarativo
    (ex.: {"channel": "canal", "external_id": "id", "received_at": "data", "message": "texto", "subject": "assunto",
    "customer_ref": "cliente"}). A Bronze preserva o payload original; aqui só se faz o mapeamento.

Etapa do pipeline (build_support):
  1. sincroniza as fontes de demonstração;  2. normaliza a Bronze e insere contatos NOVOS na tabela operacional
  `support_contacts` (idempotente por fonte + id externo);  3. o Agente de Atendimento faz a triagem dos novos;
  4. grava `gold_support_contacts` (SEM texto livre nem identificador de cliente) e registra métricas/painel/agentes.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from goops_core.db import Database
from goops_core.errors import ValidationError
from goops_core.permissions import SYSTEM_PRINCIPAL, Principal
from goops_core.support_catalog import CHANNELS, INTENTS
from goops_core.util import jdump, jload, new_id, now_iso

from ..catalog import record_transformation, register_dataset
from ..lineage.registry import add_edge
from ..storage import Lakehouse
from .generator import SCHEMA_VERSION, generate_live_batch

log = logging.getLogger("goops.support")
DOMAIN = "atendimento"
DEMO_SOURCE = "support_demo_contatos"
GOLD = "gold_support_contacts"
OWNER = "Responsável Atendimento"
DIMS = ["month", "channel", "intent_label", "routing", "urgency", "veracity_label", "carrier", "product_line", "status"]


# ---------------------------------------------------------------------------------------------- seeds / recurso
def _m(key, name, desc, ftext, fdef, unit, filters=None):
    return {"metric_key": key, "name": name, "description": desc, "formula_text": ftext,
            "formula_definition": {**fdef, "time_field": "received_at"}, "unit": unit, "dimensions": DIMS,
            "source_datasets": [GOLD], "filters": filters or [], "owner": OWNER, "domain": DOMAIN}


METRICS = [
    _m("SUP_CONTATOS", "Contatos recebidos", "Contatos de clientes por WhatsApp, e-mail e Reclame Aqui.", "contagem(contatos)",
       {"type": "count"}, "contatos"),
    _m("SUP_TAXA_AUTOMACAO", "% resolvidos sem pessoa", "Contatos tratados automaticamente pela matriz de automação "
       "(resposta informativa com dados governados) / total × 100.", "roteamento = automático / total × 100",
       {"type": "rate", "numerator": {"field": "routing", "op": "eq", "value": "auto"}}, "%"),
    _m("SUP_TAXA_RECONTATO", "% de recontato", "Contatos em que o cliente voltou pelo mesmo assunto dentro da janela de "
       "recontato / total × 100.", "recontato / total × 100", {"type": "rate", "numerator": {"field": "is_repeat", "op": "is_true"}}, "%"),
    _m("SUP_TAXA_EVITAVEIS", "% de contatos evitáveis", "Contatos que um aviso proativo teria dispensado (atraso não "
       "comunicado, status de entrega, prazo de estorno) ou recontatos / total × 100.", "evitável / total × 100",
       {"type": "rate", "numerator": {"field": "avoidable", "op": "is_true"}}, "%"),
    _m("SUP_RECLAMACOES_INCONSISTENTES", "% de reclamações não sustentadas pelos dados", "Reclamações de reparação com "
       "veracidade 'inconsistente' / reclamações × 100. Vão para revisão humana; nunca são negadas automaticamente.",
       "inconsistente / reclamações × 100",
       {"type": "rate", "numerator": {"field": "veracity_label", "op": "eq", "value": "inconsistente"},
        "base_filter": {"field": "is_claim", "op": "is_true"}}, "%"),
    _m("SUP_HORAS_ECONOMIZADAS", "Horas de atendimento poupadas", "Soma do esforço manual poupado (premissas por assunto "
       "em Configurações › Atendimento).", "soma(minutos poupados) / 60", {"type": "sum", "field": "saved_hours"}, "horas"),
    _m("SUP_HORAS_MANUAIS", "Esforço manual de referência", "Horas que os mesmos contatos exigiriam em atendimento 100% "
       "manual (premissas por assunto).", "soma(minutos manuais) / 60", {"type": "sum", "field": "manual_hours"}, "horas"),
    _m("SUP_TEMPO_1A_RESPOSTA", "Tempo até a 1ª resposta (mediana)", "Mediana de minutos entre o contato e a primeira "
       "resposta ao cliente.", "mediana(minutos até 1ª resposta)", {"type": "median", "field": "first_response_minutes"}, "min"),
    _m("SUP_SISTEMAS_POR_CONTATO", "Sistemas por contato (manual)", "Média de sistemas/portais que o atendimento manual "
       "exigiria (pedidos, transportadora, chamados, ERP, financeiro...).", "média(sistemas)",
       {"type": "mean", "field": "systems_count"}, "sistemas"),
]
WIDGETS = [
    {"id": "s1", "title": "Contatos recebidos", "metric_key": "SUP_CONTATOS", "chart": "kpi", "group_by": None},
    {"id": "s2", "title": "% resolvidos sem pessoa", "metric_key": "SUP_TAXA_AUTOMACAO", "chart": "kpi", "group_by": None},
    {"id": "s3", "title": "% de recontato", "metric_key": "SUP_TAXA_RECONTATO", "chart": "kpi", "group_by": None},
    {"id": "s4", "title": "Horas poupadas", "metric_key": "SUP_HORAS_ECONOMIZADAS", "chart": "kpi", "group_by": None},
    {"id": "s5", "title": "Contatos por mês", "metric_key": "SUP_CONTATOS", "chart": "bar", "group_by": "month"},
    {"id": "s6", "title": "Automação por assunto", "metric_key": "SUP_TAXA_AUTOMACAO", "chart": "bar", "group_by": "intent_label"},
    {"id": "s7", "title": "Recontato por canal", "metric_key": "SUP_TAXA_RECONTATO", "chart": "bar", "group_by": "channel"},
    {"id": "s8", "title": "Reclamações não sustentadas por transportadora", "metric_key": "SUP_RECLAMACOES_INCONSISTENTES",
     "chart": "table", "group_by": "carrier"},
]
AGENTS = [
    ("sup_monitor_recontato", "Monitor de recontato", "metric_monitor",
     {"metric_key": "SUP_TAXA_RECONTATO", "rule": "above", "threshold": 25, "segment_by": "channel", "min_n": 30,
      "severity": "medium", "category": "customer_service"}, 1440),
    ("sup_causas_contatos", "Causas da variação de contatos", "driver_analysis",
     {"metric_key": "SUP_CONTATOS", "dimensions": ["intent_label", "carrier", "channel"], "min_n": 10}, 10080),
    ("sup_resumo", "Resumo do atendimento", "summary",
     {"metric_keys": ["SUP_CONTATOS", "SUP_TAXA_AUTOMACAO", "SUP_TAXA_RECONTATO", "SUP_HORAS_ECONOMIZADAS"],
      "use_ai": False}, 10080),
]


def seed_support(db: Database, with_demo_source: bool = True) -> bool:
    from ..ingestion.service import create_source
    from ..semantic.registry import _insert_metric
    ts = now_iso()
    created = False
    if not db.fetchone("SELECT key FROM domains WHERE key = ?", (DOMAIN,)):
        db.execute("INSERT INTO domains (key, name, description, owner, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
                   (DOMAIN, "Atendimento ao cliente", "Contatos por WhatsApp, e-mail e Reclame Aqui — Desafio 1.", OWNER, ts))
        created = True
    if with_demo_source and not db.fetchone("SELECT id FROM sources WHERE key = ?", (DEMO_SOURCE,)):
        create_source(db, SYSTEM_PRINCIPAL, key=DEMO_SOURCE, name="Demo sintética · contatos (WhatsApp, e-mail, Reclame Aqui)",
                      entity="custom", connector="support_demo",
                      config={"recipe": "support", "domain": DOMAIN, "seed": 7, "scale": 1.0, "seed_source": True},
                      is_demo=True)
        created = True
    for m in METRICS:
        if not db.fetchone("SELECT id FROM semantic_metrics WHERE metric_key = ?", (m["metric_key"],)):
            _insert_metric(db, m, "domain", "active", SYSTEM_PRINCIPAL)
            created = True
    if not db.fetchone("SELECT id FROM dashboards WHERE key = ?", (DOMAIN,)):
        db.execute("INSERT INTO dashboards (id, key, domain, name, widgets, created_by, created_at, updated_at) "
                   "VALUES (?, ?, ?, ?, ?, 'system', ?, ?)", (new_id("DSH"), DOMAIN, DOMAIN, "Painel de atendimento",
                                                              jdump(WIDGETS), ts, ts))
        created = True
    for key, name, template, cfg, interval in AGENTS:
        if not db.fetchone("SELECT id FROM custom_agents WHERE key = ?", (key,)):
            db.execute("INSERT INTO custom_agents (id, key, domain, name, template, config, interval_minutes, enabled, "
                       "created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'system', ?, ?)",
                       (new_id("CAG"), key, DOMAIN, name, template, jdump(cfg), interval, ts, ts))
            created = True
    return created


def set_enabled(db: Database, enabled: bool) -> None:
    """Liga/desliga o Atendimento (domínio, fontes de contatos e agentes); dados e histórico são preservados."""
    if enabled:
        seed_support(db, with_demo_source=_has_demo_base(db))
    if not db.fetchone("SELECT key FROM domains WHERE key = ?", (DOMAIN,)):
        return
    db.execute("UPDATE domains SET status = ? WHERE key = ?", ("active" if enabled else "inactive", DOMAIN))
    for r in db.fetchall("SELECT key, config FROM sources WHERE entity = 'custom'"):
        if (jload(r["config"], {}) or {}).get("recipe") == "support":
            db.execute("UPDATE sources SET status = ? WHERE key = ?", ("active" if enabled else "inactive", r["key"]))
    db.execute("UPDATE custom_agents SET enabled = ? WHERE domain = ?", (int(enabled), DOMAIN))


def _has_demo_base(db: Database) -> bool:
    """A fonte sintética de contatos acompanha as bases de pedidos de demonstração/seed (não é criada sobre dados reais
    de clientes sem que alguém a crie explicitamente)."""
    return bool(db.fetchone("SELECT id FROM sources WHERE key IN ('demo_orders', 'gocase_orders')"))


# ---------------------------------------------------------------------------------------------- normalização
DEFAULT_FIELD_MAP = {"external_id": "external_id", "channel": "channel", "received_at": "received_at",
                     "customer_ref": "customer_ref", "subject": "subject", "message": "message", "sender": "sender",
                     "attachments": "attachments", "simulation_truth": "simulation_truth"}
_CHANNEL_ALIASES = {"whatsapp": "whatsapp", "wpp": "whatsapp", "zap": "whatsapp", "email": "email", "e-mail": "email",
                    "mail": "email", "reclameaqui": "reclameaqui", "reclame aqui": "reclameaqui", "ra": "reclameaqui"}


def _get(payload: dict, path: Optional[str]) -> Any:
    if not path:
        return None
    cur: Any = payload
    for part in str(path).split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def normalize_payload(payload: dict, field_map: Optional[Dict[str, str]] = None, default_channel: Optional[str] = None
                      ) -> Optional[Dict[str, Any]]:
    fm = {**DEFAULT_FIELD_MAP, **(field_map or {})}
    msg = _get(payload, fm["message"])
    ext = _get(payload, fm["external_id"])
    when = pd.to_datetime(_get(payload, fm["received_at"]), errors="coerce")
    ch = str(_get(payload, fm["channel"]) or default_channel or "").strip().lower()
    ch = _CHANNEL_ALIASES.get(ch, ch)
    if not msg or ext is None or pd.isna(when) or ch not in CHANNELS:
        return None
    att = _get(payload, fm["attachments"])
    cust = None if _get(payload, fm["customer_ref"]) in (None, "") else str(_get(payload, fm["customer_ref"]))[:60]
    sender = _get(payload, fm["sender"])
    from .generator import handle_for
    handle = str(sender)[:120] if sender not in (None, "") else handle_for(ch, cust or f"ext-{ext}")
    return {"handle": handle, "external_id": str(ext)[:120], "channel": ch, "received_at": when.strftime("%Y-%m-%dT%H:%M:%S"),
            "customer_id": None if _get(payload, fm["customer_ref"]) in (None, "") else str(_get(payload, fm["customer_ref"]))[:60],
            "subject": (str(_get(payload, fm["subject"]))[:300] if _get(payload, fm["subject"]) else None),
            "message": str(msg)[:5000], "attachments": att if isinstance(att, list) else [],
            "simulation_truth": _get(payload, fm["simulation_truth"])}


def upsert_contacts(db: Database, lake: Lakehouse) -> Dict[str, int]:
    """Lê a Bronze das fontes de atendimento ativas e registra as mensagens ainda não conhecidas (a agrupar/triar)."""
    inserted, invalid = 0, 0
    sources = [r for r in db.fetchall("SELECT key, connector, config, is_demo FROM sources WHERE status = 'active' "
                                      "AND entity = 'custom'") if (jload(r["config"], {}) or {}).get("recipe") == "support"]
    ts = now_iso()
    for src in sources:
        cfg = jload(src["config"], {}) or {}
        known = {r["external_id"] for r in db.fetchall("SELECT external_id FROM support_messages WHERE source_key = ?",
                                                       (src["key"],))}
        batch = []
        for env in lake.read_bronze(src["key"]):
            if src["connector"] == "support_demo" and env.get("_schema_version") != SCHEMA_VERSION:
                continue   # carga sintética de versão anterior (substituída pela regeneração no modelo de conversas)
            rec = normalize_payload(env["payload"], cfg.get("field_map"), cfg.get("default_channel"))
            if rec is None:
                invalid += 1
                continue
            if rec["external_id"] in known:
                continue
            known.add(rec["external_id"])
            batch.append(rec)
        with db.connect() as c:
            for rec in batch:
                c.execute("INSERT INTO support_messages (id, source_key, external_id, direction, author_type, author, text, "
                          "attachments, sent_at, channel, handle, customer_ref, subject, processed, is_demo, simulation_truth, "
                          "created_at) VALUES (?, ?, ?, 'in', 'customer', ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
                          (new_id("MSG"), src["key"], rec["external_id"], "Cliente", rec["message"], jdump(rec["attachments"]),
                           rec["received_at"], rec["channel"], rec["handle"], rec["customer_id"], rec["subject"],
                           int(src["is_demo"]),
                           jdump(rec["simulation_truth"]) if src["is_demo"] and rec["simulation_truth"] else None, ts))
        inserted += len(batch)
    return {"inserted": inserted, "invalid": invalid, "sources": len(sources)}


def _rebuild_if_legacy(db: Database) -> bool:
    """Bancos da versão anterior (contatos sem conversa): refaz o Atendimento a partir da Bronze no modelo de conversas.
    A fonte de demonstração é regenerada (cursor zerado) para trazer os diálogos completos."""
    legacy = db.fetchone("SELECT COUNT(*) AS n FROM support_contacts WHERE conversation_id IS NULL")["n"]
    if not legacy:
        return False
    with db.connect() as c:
        c.execute("DELETE FROM operations WHERE contact_id IS NOT NULL")
        for t in ("support_events", "support_messages", "support_conversations", "support_contacts"):
            c.execute(f"DELETE FROM {t}")
        c.execute("UPDATE sources SET cursor = NULL WHERE connector = 'support_demo'")
    log.info("Atendimento migrado para o modelo de conversas (reconstruído a partir da Bronze).")
    return True


# ---------------------------------------------------------------------------------------------- Gold
def build_gold(db: Database, lake: Lakehouse, pipeline_run_id: Optional[str], actor: str = "pipeline") -> Dict[str, Any]:
    rows = db.fetchall("SELECT id, source_key, channel, order_id, received_at, status, intent, urgency, sentiment, is_claim, "
                       "veracity_label, routing, is_repeat, contact_number, avoidable, avoidable_reason, manual_minutes, "
                       "saved_minutes, systems_touched, first_response_at, resolved_at, is_demo, history_simulated, "
                       "message_count, chase_count, case_number, follow_up_of "
                       "FROM support_contacts WHERE status <> 'new'")
    if not rows:
        return {"rows": 0}
    df = pd.DataFrame(rows)
    df["received_at"] = pd.to_datetime(df["received_at"], errors="coerce")
    df["month"] = df["received_at"].dt.strftime("%Y-%m")
    df["intent_label"] = df["intent"].map(lambda i: INTENTS.get(i, {}).get("label", i))
    for b in ("is_claim", "is_repeat", "avoidable", "is_demo", "history_simulated"):
        df[b] = df[b].astype(bool)
    df["manual_hours"] = (df["manual_minutes"].astype(float) / 60).round(4)
    df["saved_hours"] = (df["saved_minutes"].astype(float) / 60).round(4)
    df["systems_count"] = df["systems_touched"].map(lambda s: len(jload(s, []) or []))
    df["first_response_minutes"] = ((pd.to_datetime(df["first_response_at"], errors="coerce") - df["received_at"])
                                    .dt.total_seconds() / 60).round(1)
    df["resolution_hours"] = ((pd.to_datetime(df["resolved_at"], errors="coerce") - df["received_at"])
                              .dt.total_seconds() / 3600).round(2)
    try:
        orders = lake.read_table("gold/corporate", "gold_orders")[["order_id", "carrier", "product_line", "state"]]
        orders["order_id"] = orders["order_id"].astype(str)
        df = df.merge(orders, on="order_id", how="left")
    except FileNotFoundError:
        df["carrier"] = df["product_line"] = df["state"] = None
    for c in ("carrier", "product_line", "state", "veracity_label"):
        df[c] = df[c].fillna("Não identificado")
    df["order_linked"] = df["order_id"].notna()
    df["is_follow_up"] = df["follow_up_of"].notna()
    df["had_chase"] = df["chase_count"].fillna(0).astype(int) > 0
    df = df.rename(columns={"id": "contact_id", "is_demo": "_is_demo"})
    cols = ["contact_id", "channel", "received_at", "month", "intent", "intent_label", "status", "urgency", "sentiment",
            "is_claim", "veracity_label", "routing", "is_repeat", "contact_number", "avoidable", "avoidable_reason",
            "order_linked", "carrier", "product_line", "state", "manual_minutes", "saved_minutes", "manual_hours",
            "saved_hours", "systems_count", "first_response_minutes", "resolution_hours", "message_count", "chase_count",
            "had_chase", "case_number", "is_follow_up", "history_simulated", "_is_demo"]
    out = df[cols]
    w = lake.write_table(f"gold/domains/{DOMAIN}", GOLD, out)
    synthetic = sorted({"first_response_minutes", "resolution_hours", "status"}) if out["history_simulated"].any() else []
    register_dataset(db, key=GOLD, layer="gold_domain", scope="domain", domain=DOMAIN, name="Contatos de atendimento",
                     description="Gold de domínio (atendimento) · 1 linha por contato triado. Sem texto da mensagem nem "
                                 "identificador do cliente (minimização). Tempos de contatos antigos da demo são simulados.",
                     grain="1 linha por contato", path=w["path"], fmt=w["format"], row_count=w["rows"], schema=w["schema"],
                     schema_version="support-1.0", is_demo=bool(out["_is_demo"].any()), pipeline_run_id=pipeline_run_id,
                     synthetic_fields=synthetic)
    srcs = sorted(set(df["source_key"]))
    for s in srcs:
        add_edge(db, f"bronze:{s}", f"dataset:{GOLD}", "triagem do Agente de Atendimento (support_contacts)")
    add_edge(db, "dataset:gold_orders", f"dataset:{GOLD}", "vínculo contato → pedido (transportadora, linha, UF)")
    record_transformation(db, dataset_key=GOLD, inputs=[f"bronze_{s}" for s in srcs] + ["gold_orders"],
                          transform="support triage + gold projection", rule_version="1.0", rows_in=len(rows),
                          rows_out=w["rows"], actor=actor, pipeline_run_id=pipeline_run_id)
    return {"rows": w["rows"]}


def build_support(db: Database, lake: Lakehouse, pipeline_run_id: Optional[str], actor: Principal) -> Dict[str, Any]:
    from goops_core.runtime_config import get_section
    if not get_section(db, "features").get("support", True):
        return {"skipped": "Atendimento desligado em Configurações › Recursos"}
    seed_support(db, with_demo_source=_has_demo_base(db))
    rebuilt = _rebuild_if_legacy(db)
    from ..ingestion.service import sync_source
    synced = {}
    for r in db.fetchall("SELECT key FROM sources WHERE connector = 'support_demo' AND status = 'active'"):
        synced[r["key"]] = sync_source(db, lake, actor, r["key"]).get("records")
    up = upsert_contacts(db, lake)
    from agents.support.service import process_new
    tri = process_new(db, lake, "agent:support")
    gold = build_gold(db, lake, pipeline_run_id, actor.actor_label)
    return {"synced": synced, **up, "triage": tri, "gold_rows": gold.get("rows"), "rebuilt_legacy": rebuilt}


def _live_follow_ups(db: Database, start, seed: int) -> List[Dict[str, Any]]:
    """Clientes respondendo em conversas ABERTAS (demo ao vivo): a foto pedida chega, alguém cobra retorno."""
    import random as _r
    from datetime import timedelta as _td
    rng = _r.Random(seed)
    out: List[Dict[str, Any]] = []
    rows = db.fetchall("SELECT k.id, k.channel, k.veracity_factors, k.status, k.order_id, v.handle, v.customer_id "
                       "FROM support_contacts k JOIN support_conversations v ON v.current_case_id = k.id "
                       "WHERE k.status IN ('pending_human', 'awaiting_customer') AND k.channel <> 'reclameaqui' "
                       "ORDER BY k.priority_score DESC LIMIT 40")
    photo = [r for r in rows if "Sem evidência" in (r["veracity_factors"] or "")][:2]
    chase = [r for r in rows if r["status"] == "pending_human" and r not in photo][:1]
    t = start
    for i, r in enumerate(photo + chase):
        t = t + _td(minutes=rng.randint(2, 7))
        is_photo = r in photo
        out.append({"external_id": f"LIVE-{seed}-F{i:02d}", "channel": r["channel"], "sender": r["handle"],
                    "customer_ref": r["customer_id"], "received_at": t.strftime("%Y-%m-%dT%H:%M:%S"),
                    "subject": None, "message": "Segue a foto 📷" if is_photo else "Oi, alguma novidade sobre o meu caso?",
                    "attachments": [{"type": "image", "taken_at": (t - _td(minutes=3)).isoformat()}] if is_photo else [],
                    "simulation_truth": {"follow_up": "photo" if is_photo else "chase", "genuine": True}, "live": True})
    return out


def simulate_incoming(db: Database, lake: Lakehouse, actor: Principal, count: int = 12) -> Dict[str, Any]:
    """Demonstração ao vivo: chegam `count` contatos novos (sintéticos) e o agente faz a triagem na hora."""
    from goops_core.permissions import require_permission
    require_permission(actor, "support:write", DOMAIN)
    count = max(1, min(int(count), 50))
    src = db.fetchone("SELECT key, is_demo FROM sources WHERE key = ?", (DEMO_SOURCE,))
    if not src:
        raise ValidationError("A fonte de contatos de demonstração não existe (carregue a demo e rode o pipeline).")
    orders = lake.read_table("gold/corporate", "gold_orders")
    from agents.support.service import clock, process_new
    start = clock(db) or pd.Timestamp.utcnow().to_pydatetime()
    seed = 1000 + db.fetchone("SELECT COUNT(*) AS n FROM support_contacts")["n"]
    records = generate_live_batch(orders, start, count, seed)
    records += _live_follow_ups(db, start, seed)
    run_id = new_id("ING")
    written = lake.write_bronze(DEMO_SOURCE, run_id, records, SCHEMA_VERSION, True)
    db.execute("INSERT INTO ingestion_runs (id, source_key, started_at, finished_at, status, records_ingested, records_failed, "
               "pages, schema_version, bronze_path, triggered_by, is_demo) VALUES (?, ?, ?, ?, 'success', ?, 0, 1, ?, ?, ?, 1)",
               (run_id, DEMO_SOURCE, now_iso(), now_iso(), written["count"], SCHEMA_VERSION, written["path"], actor.actor_label))
    up = upsert_contacts(db, lake)
    tri = process_new(db, lake, "agent:support", live=True)
    build_gold(db, lake, None, actor.actor_label)
    from ..semantic.registry import clear_cache
    clear_cache()
    return {"received": up["inserted"], "triage": tri}
