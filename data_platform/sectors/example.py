"""Setor de exemplo criado 100% por configuração: Reputação (ReclameAqui), a partir da planilha do Desafio 3 do case.

É exatamente o que o assistente "Novo setor" da interface gera: domínio + fonte + conjunto de dados + métricas +
painel + agentes. Dados pessoais (e-mail, telefone e texto livre da reclamação) não são ingeridos.
"""
from __future__ import annotations

from goops_core.db import Database
from goops_core.permissions import SYSTEM_PRINCIPAL
from goops_core.util import jdump, new_id, now_iso

DOMAIN = "reputacao"
SOURCE = "reclameaqui_planilha"
DATASET = "reclameaqui"
PATH = "seed/gocase/reclameaqui.xlsx"

DEFINITION = {
    "source_keys": [SOURCE], "key_field": "id", "time_field": "data_entrada", "relationships": [],
    "fields": [
        {"name": "id", "label": "ID da reclamação", "from": "ID", "type": "id", "role": "key"},
        {"name": "data_entrada", "label": "Data da entrada", "from": "Data da entrada", "type": "datetime", "role": "time"},
        {"name": "data_fechamento", "label": "Data do fechamento", "from": "Data do fechamento", "type": "datetime",
         "role": "attribute"},
        {"name": "status", "label": "Status", "from": "Status", "type": "string", "role": "dimension"},
        {"name": "causa", "label": "Causa do problema", "from": "Causa do problema", "type": "string", "role": "dimension"},
        {"name": "atendente", "label": "Tratado por", "from": "Tratado por", "type": "string", "role": "dimension"},
        {"name": "resolvido", "label": "Problema resolvido", "from": "Seu problema foi resolvido?", "type": "bool",
         "role": "dimension"},
        {"name": "voltaria", "label": "Voltaria a fazer negócio", "from": "Voltaria a fazer negócio?", "type": "bool",
         "role": "dimension"},
        {"name": "nota", "label": "Nota do consumidor", "from": "Nota do consumidor", "type": "float", "role": "measure"},
        {"name": "dias_resposta", "label": "Dias até o fechamento", "derive": "days_between",
         "args": ["data_entrada", "data_fechamento"], "type": "float", "role": "measure"},
    ],
}
DIMS = ["month", "status", "causa", "atendente", "resolvido", "voltaria"]
GOLD = f"gold_{DATASET}"
OWNER = "Responsável Reputação"


def _m(key, name, desc, ftext, fdef, unit):
    return {"metric_key": key, "name": name, "description": desc, "formula_text": ftext,
            "formula_definition": {**fdef, "time_field": "data_entrada"}, "unit": unit, "dimensions": DIMS,
            "source_datasets": [GOLD], "filters": [], "owner": OWNER, "domain": DOMAIN}


METRICS = [
    _m("REP_RA_VOLUME", "Reclamações recebidas", "Quantidade de reclamações no ReclameAqui.", "contagem(reclamações)",
       {"type": "count"}, "reclamações"),
    _m("REP_RA_NOTA_MEDIA", "Nota média do consumidor", "Média das notas (0–10) dadas pelo consumidor após o atendimento; "
       "reclamações sem nota são excluídas.", "média(nota)", {"type": "mean", "field": "nota"}, "nota (0-10)"),
    _m("REP_RA_RESOLVIDAS", "% problemas resolvidos", "Percentual de 'Sim' entre os consumidores que responderam se o "
       "problema foi resolvido.", "resolvido = sim / resolvido informado × 100",
       {"type": "rate", "numerator": {"field": "resolvido", "op": "is_true"}, "base_filter": {"field": "resolvido", "op": "not_null"}}, "%"),
    _m("REP_RA_DIAS_RESPOSTA", "Tempo médio até o fechamento", "Média de dias entre a entrada e o fechamento da reclamação.",
       "média(data_fechamento − data_entrada)", {"type": "mean", "field": "dias_resposta"}, "dias"),
    _m("REP_RA_FECHADAS_7D", "% fechadas em até 7 dias", "Percentual de reclamações fechadas em até 7 dias (SLA ideal "
       "do case) entre as fechadas.", "dias_resposta ≤ 7 / fechadas × 100",
       {"type": "rate", "numerator": {"field": "dias_resposta", "op": "le", "value": 7},
        "base_filter": {"field": "dias_resposta", "op": "not_null"}}, "%"),
    _m("REP_RA_VOLTARIA", "% voltaria a fazer negócio", "Percentual de 'Sim' entre os consumidores que responderam.",
       "voltaria = sim / voltaria informado × 100",
       {"type": "rate", "numerator": {"field": "voltaria", "op": "is_true"}, "base_filter": {"field": "voltaria", "op": "not_null"}}, "%"),
]

WIDGETS = [
    {"id": "w1", "title": "Nota média do consumidor", "metric_key": "REP_RA_NOTA_MEDIA", "chart": "kpi", "group_by": None},
    {"id": "w2", "title": "% problemas resolvidos", "metric_key": "REP_RA_RESOLVIDAS", "chart": "kpi", "group_by": None},
    {"id": "w3", "title": "Tempo médio até o fechamento", "metric_key": "REP_RA_DIAS_RESPOSTA", "chart": "kpi", "group_by": None},
    {"id": "w4", "title": "% fechadas em até 7 dias", "metric_key": "REP_RA_FECHADAS_7D", "chart": "kpi", "group_by": None},
    {"id": "w5", "title": "Nota média por mês", "metric_key": "REP_RA_NOTA_MEDIA", "chart": "line", "group_by": "month"},
    {"id": "w6", "title": "Reclamações por mês", "metric_key": "REP_RA_VOLUME", "chart": "bar", "group_by": "month"},
    {"id": "w7", "title": "Nota média por atendente", "metric_key": "REP_RA_NOTA_MEDIA", "chart": "bar", "group_by": "atendente"},
    {"id": "w8", "title": "Tempo até o fechamento por atendente", "metric_key": "REP_RA_DIAS_RESPOSTA", "chart": "bar",
     "group_by": "atendente"},
    {"id": "w9", "title": "Reclamações por causa", "metric_key": "REP_RA_VOLUME", "chart": "table", "group_by": "causa"},
]

AGENTS = [
    ("rep_monitor_nota", "Monitor da nota no ReclameAqui", "metric_monitor",
     {"metric_key": "REP_RA_NOTA_MEDIA", "rule": "drop", "threshold": 0.5, "segment_by": "atendente", "min_n": 15,
      "severity": "medium", "category": "customer_service"}, 1440),
    ("rep_causas_nota", "Investigação da nota (por atendente e causa)", "driver_analysis",
     {"metric_key": "REP_RA_NOTA_MEDIA", "dimensions": ["atendente", "causa"], "min_n": 10}, None),
    ("rep_resumo_semanal", "Resumo semanal de reputação", "summary",
     {"metric_keys": ["REP_RA_VOLUME", "REP_RA_NOTA_MEDIA", "REP_RA_RESOLVIDAS", "REP_RA_FECHADAS_7D"]}, 10080),
]


def seed_reputation_sector(db: Database) -> bool:
    """Idempotente. Retorna True se criou algo."""
    from ..connectors.file_connector import import_dir
    if not (import_dir() / PATH).exists():
        return False
    from ..ingestion.service import create_source
    from ..semantic.registry import _insert_metric
    ts = now_iso()
    created = False
    if not db.fetchone("SELECT key FROM domains WHERE key = ?", (DOMAIN,)):
        db.execute("INSERT INTO domains (key, name, description, owner, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
                   (DOMAIN, "Reputação (ReclameAqui)", "Setor criado por configuração: reclamações públicas, notas e "
                    "tempo de resposta.", OWNER, ts))
        created = True
    if not db.fetchone("SELECT id FROM sources WHERE key = ?", (SOURCE,)):
        create_source(db, SYSTEM_PRINCIPAL, key=SOURCE, name="Gocase · Base ReclameAqui (planilha do case)", entity="custom",
                      connector="file", config={"path": PATH, "format": "xlsx", "seed": True, "dataset": DATASET, "domain": DOMAIN,
                                                "exclude_fields": ["E-mail", "Nº de Contato", "Reclamação"],
                                                "schema_version": "ra-xlsx-1"}, is_demo=False)
        created = True
    if not db.fetchone("SELECT id FROM custom_datasets WHERE key = ?", (DATASET,)):
        db.execute("INSERT INTO custom_datasets (id, key, domain, name, description, definition, created_by, created_at, "
                   "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (new_id("CDS"), DATASET, DOMAIN, "Reclamações ReclameAqui",
                    "Reclamações públicas (Desafio 3 do case), sem dados pessoais.", jdump(DEFINITION), "system", ts, ts))
        created = True
    for m in METRICS:
        if not db.fetchone("SELECT id FROM semantic_metrics WHERE metric_key = ?", (m["metric_key"],)):
            _insert_metric(db, m, "domain", "active", SYSTEM_PRINCIPAL)
            created = True
    if not db.fetchone("SELECT id FROM dashboards WHERE key = ?", (DOMAIN,)):
        db.execute("INSERT INTO dashboards (id, key, domain, name, widgets, created_by, created_at, updated_at) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (new_id("DSH"), DOMAIN, DOMAIN, "Painel de reputação", jdump(WIDGETS),
                                                       "system", ts, ts))
        created = True
    for key, name, template, cfg, interval in AGENTS:
        if not db.fetchone("SELECT id FROM custom_agents WHERE key = ?", (key,)):
            db.execute("INSERT INTO custom_agents (id, key, domain, name, template, config, interval_minutes, enabled, "
                       "created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'system', ?, ?)",
                       (new_id("CAG"), key, DOMAIN, name, template, jdump(cfg), interval, ts, ts))
            created = True
    return created
