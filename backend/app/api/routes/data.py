"""Sources, ingestão, Data Lakehouse, qualidade, lineage, dicionário, pipeline e demo."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from goops_core.db import Database
from goops_core.errors import PermissionDenied, ValidationError
from goops_core.permissions import Principal, has_permission
from data_platform.bootstrap import load_demo
from data_platform.catalog import get_dataset, list_datasets, storage_layer_for
from data_platform.dictionary.catalog import list_dictionary
from data_platform.ingestion.service import (create_source, get_source, list_ingestion_runs, list_sources, reset_cursor,
                                            sync_source, test_source, update_source)
from data_platform.retention import apply_retention
from data_platform.lineage.registry import graph
from data_platform.pipelines.runner import list_pipeline_runs, run_pipeline
from data_platform.quality.service import list_quarantine, quality_overview
from data_platform.storage import Lakehouse

from ...schemas.requests import MappingPreview, MappingSave, DemoLoadRequest, PipelineRequest, RetentionRequest, SourceCreate, SourceUpdate, SyncRequest
from ..deps import db_dep, lake_dep, ok, require

router = APIRouter()

LAYERS = [
    {"key": "sources", "level": "L0", "name": "Sources", "description": "Fontes originais (APIs e sistemas)."},
    {"key": "bronze", "level": "L1", "name": "Bronze", "description": "Payloads brutos preservados, append-only."},
    {"key": "silver", "level": "L2", "name": "Silver", "description": "Dados normalizados, validados e integrados."},
    {"key": "gold_corporate", "level": "L3", "name": "Corporate Gold", "description": "Base analítica corporativa."},
    {"key": "gold_domain", "level": "L3", "name": "Domain Gold", "description": "Conjuntos especializados por domínio."},
    {"key": "semantic", "level": "L4", "name": "Semantic & Intelligence", "description": "Métricas governadas e agentes."},
]
PII_COLUMNS = {"customer_id", "comment"}


@router.get("/sources", tags=["sources"])
def sources(p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep)):
    return ok(list_sources(db))


@router.post("/sources", tags=["sources"], status_code=201)
def sources_create(body: SourceCreate, p: Principal = Depends(require("data:write")), db: Database = Depends(db_dep)):
    return ok(create_source(db, p, key=body.key, name=body.name, entity=body.entity, connector=body.connector,
                            config=body.config, is_demo=body.connector == "demo"))


@router.get("/sources/{source_id}", tags=["sources"])
def source_detail(source_id: str, p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep)):
    src = get_source(db, source_id)
    return ok({**src, "runs": list_ingestion_runs(db, src["key"], 20)})


@router.post("/sources/{source_id}", tags=["sources"])
def source_update(source_id: str, body: SourceUpdate, p: Principal = Depends(require("data:write")),
                  db: Database = Depends(db_dep)):
    return ok(update_source(db, p, source_id, name=body.name, config=body.config, status=body.status))


@router.post("/sources/{source_id}/cursor/reset", tags=["sources"])
def source_cursor_reset(source_id: str, p: Principal = Depends(require("data:write")), db: Database = Depends(db_dep)):
    return ok(reset_cursor(db, p, source_id))


@router.post("/sources/{source_id}/test", tags=["sources"])
def source_test(source_id: str, p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep)):
    return ok(test_source(db, p, source_id))


@router.post("/sources/{source_id}/sync", tags=["sources"])
def source_sync(source_id: str, body: SyncRequest = SyncRequest(), p: Principal = Depends(require("data:sync")),
                db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)):
    src = get_source(db, source_id)
    return ok(sync_source(db, lake, p, src["key"], body.full_refresh),
              {"note": "Ingestão grava apenas na Bronze. Execute o pipeline para atualizar Silver/Gold."})


@router.get("/data/ingestion-runs", tags=["data"])
def ingestion_runs(source: str = Query(default=None), limit: int = Query(default=100, ge=1, le=500),
                   p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep)):
    return ok(list_ingestion_runs(db, source, limit))


@router.get("/data/layers", tags=["data"])
def layers(p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep)):
    datasets = list_datasets(db)
    out = []
    for layer in LAYERS:
        if layer["key"] == "sources":
            items = list_sources(db)
            out.append({**layer, "count": len(items), "rows": None})
        elif layer["key"] == "semantic":
            n = db.fetchone("SELECT COUNT(*) AS n FROM semantic_metrics")["n"]
            out.append({**layer, "count": n, "rows": None})
        else:
            ds = [d for d in datasets if d["layer"] == layer["key"]]
            out.append({**layer, "count": len(ds), "rows": sum(d["row_count"] or 0 for d in ds),
                        "last_built_at": max((d["last_built_at"] or "" for d in ds), default=None)})
    return ok({"layers": out, "pipeline_runs": list_pipeline_runs(db, 10)})


@router.get("/data/datasets", tags=["data"])
def datasets(layer: str = Query(default=None), domain: str = Query(default=None),
             p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep)):
    return ok(list_datasets(db, layer, domain))


@router.get("/data/datasets/{key}", tags=["data"])
def dataset_detail(key: str, preview: int = Query(default=20, ge=0, le=200), p: Principal = Depends(require("data:read")),
                   db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)):
    ds = get_dataset(db, key)
    if ds.get("domain") and not has_permission(p, "data:read", ds["domain"]):
        raise PermissionDenied(f"Sem acesso ao domínio {ds['domain']}.")
    rows = []
    layer = storage_layer_for(ds)
    masked = []
    if preview and layer:
        rows = lake.preview(layer, key, preview)
        if not has_permission(p, "data:pii"):
            masked = sorted(PII_COLUMNS & set(rows[0].keys())) if rows else []
            for r in rows:
                for c in masked:
                    if r.get(c) is not None:
                        r[c] = "•••"
    return ok({**ds, "preview": rows, "masked_columns": masked,
               "dictionary": list_dictionary(db, key), "lineage": graph(db, f"dataset:{key}", "both", 3)
               if layer else None})


@router.get("/data/quality", tags=["data"])
def quality(p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep)):
    return ok(quality_overview(db))


@router.get("/data/quality/quarantine", tags=["data"])
def quarantine(dataset: str = Query(default=None), p: Principal = Depends(require("data:read")),
               db: Database = Depends(db_dep)):
    rows = list_quarantine(db, dataset)
    if not has_permission(p, "data:pii"):
        for r in rows:
            for c in PII_COLUMNS:
                if r["payload"].get(c) is not None:
                    r["payload"][c] = "•••"
    return ok(rows)


@router.get("/data/lineage", tags=["data"])
def lineage(node: str = Query(default=None), direction: str = Query(default="upstream", pattern="^(upstream|downstream|both)$"),
            p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep)):
    return ok(graph(db, node, direction))


@router.get("/data/dictionary", tags=["data"])
def dictionary(dataset: str = Query(default=None), q: str = Query(default=None, max_length=60),
               p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep)):
    return ok(list_dictionary(db, dataset, q))


@router.post("/data/pipeline/run", tags=["data"])
def pipeline_run(body: PipelineRequest = PipelineRequest(), p: Principal = Depends(require("data:sync")),
                 db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)):
    return ok(run_pipeline(db, lake, p, sync=body.sync))


@router.get("/data/pipeline/runs", tags=["data"])
def pipeline_runs(p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep)):
    return ok(list_pipeline_runs(db, 50))


@router.post("/data/retention", tags=["data"])
def retention(body: RetentionRequest = RetentionRequest(), p: Principal = Depends(require("data:write")),
              db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)):
    return ok(apply_retention(db, lake, p, dry_run=body.dry_run))


@router.post("/demo/load", tags=["demo"])
def demo_load(body: DemoLoadRequest = DemoLoadRequest(), p: Principal = Depends(require("settings:write")),
              db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)):
    from goops_core.config import get_settings
    if not get_settings().demo_mode:
        raise ValidationError("DEMO_MODE desativado neste ambiente.")
    return ok(load_demo(db, lake, body.scenario, body.reset), {"is_demo": True})


# ------------------------------------------------------------------ mapeamentos Fonte -> Silver
@router.get("/mapping/schema", tags=["mapping"])
def mapping_schema(p: Principal = Depends(require("data:read"))):
    from data_platform.silver.profiles import canonical_schema
    return ok(canonical_schema())


@router.get("/mapping/profiles", tags=["mapping"])
def mapping_profiles(p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep)):
    from data_platform.silver.profiles import list_profiles
    return ok(list_profiles(db))


@router.post("/mapping/profiles", tags=["mapping"])
def mapping_save(body: MappingSave, p: Principal = Depends(require("data:write")), db: Database = Depends(db_dep)):
    from data_platform.silver.profiles import save_profile
    return ok(save_profile(db, p, body.profile_key, body.entity, body.definition, body.change_note, body.description,
                           body.based_on), {"note": "Reprocesse o pipeline (sem ingestão) para aplicar aos dados existentes."})


@router.get("/mapping/profiles/{profile_key}/{entity}/versions", tags=["mapping"])
def mapping_versions(profile_key: str, entity: str, p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep)):
    from data_platform.silver.profiles import profile_versions
    return ok(profile_versions(db, profile_key, entity))


@router.post("/mapping/preview", tags=["mapping"])
def mapping_preview(body: MappingPreview, p: Principal = Depends(require("data:read")), db: Database = Depends(db_dep),
                    lake: Lakehouse = Depends(lake_dep)):
    from data_platform.silver.profiles import preview
    return ok(preview(db, lake, p, body.entity, body.definition, body.source_key, body.sample, body.limit))
