"""Ferramentas governadas disponíveis aos agentes.

Cada ferramenta possui contrato explícito (parâmetros e tipos permitidos), permissão mínima
exigida e é somente-leitura. NÃO existe ferramenta de SQL arbitrário. Toda chamada é auditada
na timeline do incidente (quando houver).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import pandas as pd

from goops_core.errors import PermissionDenied, ValidationError
from goops_core.permissions import Principal, has_permission
from data_platform.analytics.nps import NpsAnalytics
from data_platform.lineage.registry import upstream_path
from data_platform.quality.service import quality_overview
from data_platform.semantic.registry import compute_metric, get_metric


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    permission: str
    domain: Optional[str]
    params: Dict[str, tuple]  # nome -> (tipos aceitos, obrigatório)
    fn: Callable[..., Any]


def _period(params: dict) -> dict:
    return {k: params[k] for k in ("start", "end") if params.get(k)}


def _nps_breakdown(ctx, p):
    return compute_metric(ctx.db, ctx.lake, p["_principal"], "METRIC_NPS_001", {**_period(p), **(p.get("filters") or {})},
                          p["dimension"])


def _nps_total(ctx, p):
    return compute_metric(ctx.db, ctx.lake, p["_principal"], "METRIC_NPS_001", {**_period(p), **(p.get("filters") or {})})


def _nps_monthly(ctx, p):
    return NpsAnalytics(ctx.db, ctx.lake, p["_principal"]).evolution(p.get("filters"))


def _late_rate(ctx, p):
    return compute_metric(ctx.db, ctx.lake, p["_principal"], "METRIC_LATE_DELIVERY_RATE_001",
                          {**_period(p), **(p.get("filters") or {})}, p.get("group_by"))


def _delivery_days(ctx, p):
    return compute_metric(ctx.db, ctx.lake, p["_principal"], "METRIC_DELIVERY_DAYS_001",
                          {**_period(p), **(p.get("filters") or {})}, p.get("group_by"))


def _themes(ctx, p):
    a = NpsAnalytics(ctx.db, ctx.lake, p["_principal"])
    filters = {**_period(p), **(p.get("filters") or {})}
    res = a.comments(filters, top=10)
    cat = p.get("category", "detractors")
    return {"comments_available": res["comments_available"], "category": cat,
            "themes": res[cat]["themes"], "comments_processed": res[cat]["comments_processed"],
            "injection_suspected": res["injection_suspected"]}


def _dq(ctx, p):
    q = quality_overview(ctx.db)
    datasets = set(p.get("datasets") or [])
    results = [r for r in q["results"] if not datasets or r["dataset"] in datasets]
    return {"pipeline_run_id": q["pipeline_run_id"], "summary": q["summary"],
            "issues": [{k: r[k] for k in ("rule_key", "dataset", "severity", "failed", "checked", "fail_rate", "status")}
                       for r in results if r["status"] != "passed"]}


def _lineage(ctx, p):
    return {"node": p["node"], "upstream": upstream_path(ctx.db, p["node"])}


def _metric_def(ctx, p):
    m = get_metric(ctx.db, p["metric_key"])
    return {k: m[k] for k in ("metric_key", "name", "version", "scope", "domain", "formula_text", "relationship")}


def _delay_risk(ctx, p):
    df = ctx.lake.read_table("gold/domains/logistics", "logistics_delay_risk")
    if p.get("carrier"):
        df = df[df["carrier"] == p["carrier"]]
    if p.get("states"):
        df = df[df["state"].isin(p["states"])]
    return {"open_deliveries": int(len(df)), "high_risk": int((df["risk_level"] == "high").sum()),
            "medium_risk": int((df["risk_level"] == "medium").sum()),
            "by_state": df.groupby("state").size().sort_values(ascending=False).head(10).to_dict()}


def _unclassified(ctx, p):
    a = NpsAnalytics(ctx.db, ctx.lake, p["_principal"])
    df = a.frame(a.clean_filters({**_period(p), **(p.get("filters") or {})}))
    df = df[(df["score_category"] == "detractor") & df["has_comment"].astype(bool) & df["themes"].isna()
            & ~df["injection_suspected"].astype(bool)]
    return {"total": int(len(df)), "comments": df["comment"].head(int(p.get("limit", 25))).tolist()}


TOOLS: Dict[str, Tool] = {t.name: t for t in [
    Tool("unclassified_comments", "Comentários de detratores sem tema (exclui suspeitas de injeção)", "analytics:read", "cx",
         {"start": (str, False), "end": (str, False), "filters": (dict, False), "limit": (int, False)}, _unclassified),
    Tool("nps_total", "NPS oficial (METRIC_NPS_001) para um período/filtros", "analytics:read", None,
         {"start": (str, False), "end": (str, False), "filters": (dict, False)}, _nps_total),
    Tool("nps_monthly", "Série mensal do NPS oficial", "analytics:read", None, {"filters": (dict, False)}, _nps_monthly),
    Tool("nps_breakdown", "NPS oficial por dimensão (state, carrier, product_line, shipping_type)", "analytics:read", None,
         {"dimension": (str, True), "start": (str, False), "end": (str, False), "filters": (dict, False)}, _nps_breakdown),
    Tool("delivery_late_rate", "Taxa de atraso corporativa (METRIC_LATE_DELIVERY_RATE_001)", "analytics:read", "logistics",
         {"group_by": (str, False), "start": (str, False), "end": (str, False), "filters": (dict, False)}, _late_rate),
    Tool("delivery_days", "Prazo médio pedido→entrega (METRIC_DELIVERY_DAYS_001)", "analytics:read", "logistics",
         {"group_by": (str, False), "start": (str, False), "end": (str, False), "filters": (dict, False)}, _delivery_days),
    Tool("comment_themes", "Temas de comentários (NLP determinístico)", "analytics:read", "cx",
         {"category": (str, False), "start": (str, False), "end": (str, False), "filters": (dict, False)}, _themes),
    Tool("data_quality_status", "Resultado das regras de qualidade da última execução", "data:read", None,
         {"datasets": (list, False)}, _dq),
    Tool("lineage_upstream", "Origem (lineage a montante) de um nó", "data:read", None, {"node": (str, True)}, _lineage),
    Tool("metric_definition", "Definição oficial de uma métrica do catálogo", "semantic:read", None,
         {"metric_key": (str, True)}, _metric_def),
    Tool("delay_risk_summary", "Resumo de entregas em aberto com risco de atraso", "analytics:read", "logistics",
         {"carrier": (str, False), "states": (list, False)}, _delay_risk),
]}

ALLOWED_DIMENSIONS = {"state", "carrier", "product_line", "shipping_type", "eval_month", "ship_month"}


def call_tool(ctx, principal: Principal, name: str, params: Optional[dict] = None, run=None) -> Any:
    tool = TOOLS.get(name)
    if tool is None:
        raise ValidationError(f"Ferramenta inexistente: {name}")
    if not has_permission(principal, tool.permission, tool.domain):
        if run is not None:
            run.event("tool_denied", f"Acesso negado à ferramenta {name}", {"tool": name})
        raise PermissionDenied(f"{principal.actor_label} não pode usar a ferramenta {name}.")
    params = dict(params or {})
    for key, value in params.items():
        if key not in tool.params:
            raise ValidationError(f"Parâmetro não permitido em {name}: {key}")
        if value is not None and not isinstance(value, tool.params[key][0]):
            raise ValidationError(f"Tipo inválido para {key} em {name}")
    for key, (_, required) in tool.params.items():
        if required and params.get(key) in (None, ""):
            raise ValidationError(f"Parâmetro obrigatório ausente em {name}: {key}")
    for dim in ("dimension", "group_by"):
        if params.get(dim) and params[dim] not in ALLOWED_DIMENSIONS:
            raise ValidationError(f"Dimensão não permitida: {params[dim]}")
    result = tool.fn(ctx, {**params, "_principal": principal})
    if run is not None:
        run.event("tool_call", f"Consulta governada: {tool.description}",
                  {"tool": name, "params": {k: v for k, v in params.items()}})
    return result
