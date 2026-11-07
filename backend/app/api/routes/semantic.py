"""Semantic Governance: catálogo corporativo/domínio, versões, aprovações e cálculo governado."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from goops_core.audit import list_audit
from goops_core.db import Database
from goops_core.permissions import Principal
from data_platform.semantic.registry import (compute_metric, create_metric, get_metric, list_domains, list_metrics,
                                             list_versions, pending_approvals, propose_change, review_version)
from data_platform.storage import Lakehouse

from ...schemas.requests import MetricChange, MetricCreate, VersionReview
from ..deps import db_dep, lake_dep, ok, require

router = APIRouter(prefix="/semantic", tags=["semantic"])


@router.get("/metrics")
def metrics(scope: Optional[str] = Query(default=None, pattern="^(corporate|domain)$"),
            domain: Optional[str] = Query(default=None), p: Principal = Depends(require("semantic:read")),
            db: Database = Depends(db_dep)):
    return ok(list_metrics(db, scope, domain))


@router.post("/metrics", status_code=201)
def metrics_create(body: MetricCreate, p: Principal = Depends(require("semantic:read")), db: Database = Depends(db_dep)):
    return ok(create_metric(db, p, body.model_dump()),
              {"note": "Nova métrica criada com status 'pending_approval'; ativa após aprovação."})


@router.get("/metrics/{key}")
def metric_detail(key: str, p: Principal = Depends(require("semantic:read")), db: Database = Depends(db_dep)):
    m = get_metric(db, key)
    return ok({**m, "versions": list_versions(db, key), "audit": list_audit(db, "metric", m["metric_key"], limit=50)})


@router.get("/metrics/{key}/versions")
def metric_versions(key: str, p: Principal = Depends(require("semantic:read")), db: Database = Depends(db_dep)):
    return ok(list_versions(db, key))


@router.post("/metrics/{key}/versions")
def metric_propose(key: str, body: MetricChange, p: Principal = Depends(require("semantic:read")),
                   db: Database = Depends(db_dep)):
    return ok(propose_change(db, p, key, body.changes, body.change_note))


@router.post("/metrics/{key}/approve")
def metric_approve(key: str, body: VersionReview, p: Principal = Depends(require("semantic:read")),
                   db: Database = Depends(db_dep)):
    return ok(review_version(db, p, key, body.version, body.approve, body.note))


@router.get("/metrics/{key}/value")
def metric_value(key: str, group_by: Optional[str] = Query(default=None), start: Optional[str] = Query(default=None),
                 end: Optional[str] = Query(default=None), p: Principal = Depends(require("analytics:read")),
                 db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)):
    return ok(compute_metric(db, lake, p, key, {"start": start, "end": end}, group_by))


@router.get("/metrics/{key}/explain")
def metric_explain(key: str, p: Principal = Depends(require("semantic:read")), db: Database = Depends(db_dep),
                   lake: Lakehouse = Depends(lake_dep)):
    from agents.explain import explain_metric
    return ok(explain_metric(db, lake, p, key))


@router.get("/approvals")
def approvals(p: Principal = Depends(require("semantic:read")), db: Database = Depends(db_dep)):
    return ok(pending_approvals(db))


@router.get("/domains")
def domains(p: Principal = Depends(require("semantic:read")), db: Database = Depends(db_dep)):
    return ok(list_domains(db))


@router.get("/audit")
def semantic_audit(p: Principal = Depends(require("audit:read")), db: Database = Depends(db_dep)):
    return ok(list_audit(db, "metric", limit=300))
