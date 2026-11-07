"""Setores dinâmicos: fonte → campos → conjunto de dados → métricas → painel → agentes, tudo configurável na interface."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from goops_core.db import Database
from goops_core.errors import GoOpsError, NotFound, ValidationError
from goops_core.permissions import Principal, require_permission
from agents.custom import (RULES, SECTOR_ACTIONS, TEMPLATES, delete_agent, get_agent, list_agents, run_agent, save_agent)
from data_platform.connectors.registry import CONNECTORS, build_connector
from data_platform.ingestion.service import create_source, get_source, list_sources
from data_platform.sectors.dashboards import CHARTS, can_edit, get_dashboard, render_dashboard, save_dashboard, sector_metrics
from data_platform.sectors.datasets import (DERIVES, JOINABLE, ROLES, TYPES, default_widgets, get_custom_dataset,
                                            list_custom_datasets, metric_dimensions, preview_rows, save_custom_dataset,
                                            suggest_metrics)
from data_platform.sectors.discovery import profile
from data_platform.semantic.registry import create_domain, create_metric, list_domains
from data_platform.storage import Lakehouse
from goops_core.incidents import CATEGORIES, SEVERITIES

from ..deps import db_dep, lake_dep, ok, require

router = APIRouter(prefix="/sectors", tags=["sectors"])
BUILTIN_PAGES = {"cx": "/analytics/cx", "logistics": "/analytics/logistics", "products": "/analytics/products"}


class SectorCreate(BaseModel):
    key: str = Field(min_length=2, max_length=31)
    name: str = Field(min_length=2, max_length=80)
    description: str = ""


class SourceCreate(BaseModel):
    key: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=120)
    connector: str
    config: Dict[str, Any] = Field(default_factory=dict)


class DiscoverRequest(BaseModel):
    source_key: str
    use_ai: bool = False
    sector: str = ""


class MetricPreview(BaseModel):
    payload: Dict[str, Any]
    group_by: Optional[str] = None


class DatasetSave(BaseModel):
    key: str = Field(min_length=2, max_length=41)
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    definition: Dict[str, Any]


class MetricsBulk(BaseModel):
    metrics: List[Dict[str, Any]]
    create_dashboard: bool = True


class DashboardSave(BaseModel):
    name: str = Field(default="Painel do setor", max_length=120)
    widgets: List[Dict[str, Any]]


class AgentSave(BaseModel):
    key: str = Field(min_length=3, max_length=50)
    name: str = Field(min_length=2, max_length=80)
    template: str
    config: Dict[str, Any]
    interval_minutes: Optional[int] = None
    enabled: bool = True


def _domain(db: Database, key: str) -> dict:
    d = db.fetchone("SELECT * FROM domains WHERE key = ?", (key,))
    if not d or key == "corporate":
        raise NotFound("Setor não encontrado.")
    return d


@router.get("/catalog")
def catalog(p: Principal = Depends(require("data:read"))):
    """Opções para os formulários (tipos, papéis, gráficos, modelos de agente, conectores)."""
    return ok({"field_types": sorted(TYPES), "roles": sorted(ROLES), "derives": sorted(DERIVES), "charts": sorted(CHARTS),
               "joinable": JOINABLE, "agent_templates": TEMPLATES, "rules": RULES, "severities": SEVERITIES,
               "sector_actions": SECTOR_ACTIONS,
               "categories": CATEGORIES, "connectors": [c for c in CONNECTORS if c in ("file", "http_json")]})


@router.get("")
def sectors(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep)):
    out = []
    for d in list_domains(db):
        if d["key"] == "corporate":
            continue
        out.append({**d, "datasets": len(list_custom_datasets(db, d["key"])), "metrics": len(sector_metrics(db, d["key"])),
                    "agents": len(list_agents(db, d["key"])), "has_dashboard": bool(get_dashboard(db, d["key"])),
                    "builtin_page": BUILTIN_PAGES.get(d["key"])})
    return ok(out)


@router.post("", status_code=201)
def sector_create(body: SectorCreate, p: Principal = Depends(require("settings:write")), db: Database = Depends(db_dep)):
    return ok(create_domain(db, p, body.key, body.name, body.description))


@router.get("/{domain}")
def sector_detail(domain: str, p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep),
                  lake: Lakehouse = Depends(lake_dep)):
    d = _domain(db, domain)
    datasets = []
    for ds in list_custom_datasets(db, domain):
        prev = preview_rows(lake, ds, 0)
        datasets.append({**ds, "dimensions": metric_dimensions(ds), "built": prev["built"], "rows": prev.get("total")})
    keys = {s for ds in datasets for s in ds["definition"]["source_keys"]}
    sources = [s for s in list_sources(db) if s["key"] in keys or (s["entity"] == "custom" and s["config"].get("domain") == domain)]
    return ok({"domain": d, "datasets": datasets, "sources": sources, "metrics": sector_metrics(db, domain),
               "agents": list_agents(db, domain), "dashboard": get_dashboard(db, domain), "can_edit": can_edit(p, domain),
               "builtin_page": BUILTIN_PAGES.get(domain)})


@router.get("/{domain}/dashboard")
def dashboard(domain: str, start: Optional[str] = Query(default=None), end: Optional[str] = Query(default=None),
              p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep),
              lake: Lakehouse = Depends(lake_dep)):
    _domain(db, domain)
    return ok(render_dashboard(db, lake, p, domain, {"start": start, "end": end}))


@router.post("/{domain}/dashboard")
def dashboard_save(domain: str, body: DashboardSave, p: Principal = Depends(require("analytics:read")),
                   db: Database = Depends(db_dep)):
    _domain(db, domain)
    return ok(save_dashboard(db, p, domain, body.name, body.widgets))


@router.post("/{domain}/sources", status_code=201)
def sector_source(domain: str, body: SourceCreate, p: Principal = Depends(require("data:write")),
                  db: Database = Depends(db_dep)):
    _domain(db, domain)
    if body.connector not in ("file", "http_json"):
        raise ValidationError("Use os conectores 'file' (planilha em data/) ou 'http_json' (API REST).")
    return ok(create_source(db, p, key=body.key, name=body.name, entity="custom", connector=body.connector,
                            config={**body.config, "domain": domain}))


@router.post("/discover")
def discover(body: DiscoverRequest, p: Principal = Depends(require("data:write")), db: Database = Depends(db_dep),
             lake: Lakehouse = Depends(lake_dep)):
    """Lê uma amostra da fonte (Bronze, se já sincronizada; senão direto do conector, sem gravar) e sugere campos."""
    src = get_source(db, body.source_key)
    records = lake.read_bronze(src["key"])[-2000:]
    origin = "bronze"
    if not records:
        try:
            records = build_connector(src["key"], src["connector"], src["config"]).fetch().records[:2000]
        except GoOpsError as exc:
            raise ValidationError(f"Não foi possível ler a fonte: {exc.message}")
        origin = "conector"
    if not records:
        raise ValidationError("A fonte não retornou registros para analisar.")
    prof = profile(records)
    if body.use_ai:
        from agents.sector_setup import refine_with_ai
        prof = refine_with_ai(db, body.sector or src["name"], prof)
    else:
        prof = {**prof, "generated_by": "deterministic", "ai_metrics": []}
    return ok({**prof, "origin": origin, "source_key": src["key"]})


@router.get("/joinable/datasets")
def joinable(exclude: Optional[str] = Query(default=None), p: Principal = Depends(require("data:read")),
             db: Database = Depends(db_dep)):
    from data_platform.sectors.datasets import joinable_datasets
    return ok(joinable_datasets(db, exclude))


@router.post("/{domain}/metrics/preview")
def metric_preview(domain: str, body: MetricPreview, p: Principal = Depends(require("semantic:read")),
                   db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)):
    from data_platform.sectors.metrics import preview_metric
    _domain(db, domain)
    return ok(preview_metric(db, lake, p, domain, body.payload, body.group_by))


@router.post("/{domain}/datasets", status_code=201)
def dataset_save(domain: str, body: DatasetSave, p: Principal = Depends(require("data:write")),
                 db: Database = Depends(db_dep)):
    _domain(db, domain)
    ds = save_custom_dataset(db, p, key=body.key, domain=domain, name=body.name, description=body.description,
                             definition=body.definition)
    for s in ds["definition"]["source_keys"]:
        src = get_source(db, s)
        if src["config"].get("dataset") != ds["key"]:
            from data_platform.ingestion.service import update_source
            update_source(db, p, s, config={**{k: v for k, v in src["config"].items() if k != "entity"},
                                            "dataset": ds["key"], "domain": domain})
    return ok(ds, {"note": "Execute o pipeline para construir o conjunto (Silver/Gold)."})


@router.get("/datasets/{key}/preview")
def dataset_preview(key: str, p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep),
                    lake: Lakehouse = Depends(lake_dep)):
    return ok(preview_rows(lake, get_custom_dataset(db, key)))


@router.get("/datasets/{key}/suggest-metrics")
def dataset_suggest(key: str, p: Principal = Depends(require("semantic:read")), db: Database = Depends(db_dep)):
    ds = get_custom_dataset(db, key)
    existing = {m["metric_key"] for m in sector_metrics(db, ds["domain"])}
    return ok([{**m, "exists": m["metric_key"] in existing} for m in suggest_metrics(ds)])


@router.post("/{domain}/metrics")
def metrics_bulk(domain: str, body: MetricsBulk, p: Principal = Depends(require("semantic:read")),
                 db: Database = Depends(db_dep)):
    _domain(db, domain)
    created, errors = [], []
    for m in body.metrics[:30]:
        try:
            created.append(create_metric(db, p, {**m, "scope": "domain", "domain": domain}))
        except GoOpsError as exc:
            errors.append({"metric_key": m.get("metric_key"), "error": exc.message})
    dash = get_dashboard(db, domain)
    if body.create_dashboard and created and not dash:
        ds_key = (created[0]["source_datasets"][0] or "").replace("gold_", "", 1)
        try:
            ds = get_custom_dataset(db, ds_key)
            dash = save_dashboard(db, p, domain, "Painel do setor", default_widgets(created, ds))
        except GoOpsError as exc:
            errors.append({"metric_key": "painel", "error": exc.message})
    return ok({"created": created, "errors": errors, "dashboard": dash},
              {"note": "Métricas novas ficam 'aguardando aprovação' (segregação de funções). Até lá aparecem no painel como rascunho."})


@router.get("/{domain}/agents")
def agents(domain: str, p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    return ok(list_agents(db, domain))


@router.post("/{domain}/agents")
def agent_save(domain: str, body: AgentSave, p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    _domain(db, domain)
    return ok(save_agent(db, p, key=body.key, domain=domain, name=body.name, template=body.template, config=body.config,
                         interval_minutes=body.interval_minutes, enabled=body.enabled))


@router.post("/agents/{key}/run")
def agent_run(key: str, p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep),
              lake: Lakehouse = Depends(lake_dep)):
    return ok(run_agent(db, lake, p, key))


@router.post("/agents/{key}/delete")
def agent_delete(key: str, p: Principal = Depends(require("agents:read")), db: Database = Depends(db_dep)):
    delete_agent(db, p, key)
    return ok({"deleted": key})
