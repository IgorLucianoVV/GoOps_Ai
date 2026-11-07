"""Analytics: NPS (módulo inicial), CX, Logística, Produtos e Regional. Todos via métricas governadas."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from goops_core.db import Database
from goops_core.permissions import Principal
from data_platform.analytics.domains import cx_overview, logistics_overview, products_overview, regional_overview
from data_platform.analytics.nps import NpsAnalytics
from data_platform.storage import Lakehouse

from ..deps import db_dep, lake_dep, ok, require

router = APIRouter(prefix="/analytics", tags=["analytics"])


def nps_filters(start: Optional[str] = Query(default=None), end: Optional[str] = Query(default=None),
                state: Optional[List[str]] = Query(default=None), product_line: Optional[List[str]] = Query(default=None),
                carrier: Optional[List[str]] = Query(default=None),
                shipping_type: Optional[List[str]] = Query(default=None)) -> dict:
    return {"start": start, "end": end, "state": state, "product_line": product_line, "carrier": carrier,
            "shipping_type": shipping_type}


def _a(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep),
       lake: Lakehouse = Depends(lake_dep)) -> NpsAnalytics:
    return NpsAnalytics(db, lake, p)


@router.get("/nps/overview")
def nps_overview(f: dict = Depends(nps_filters), a: NpsAnalytics = Depends(_a)):
    return ok(a.overview(f))


@router.get("/nps/evolution")
def nps_evolution(f: dict = Depends(nps_filters), a: NpsAnalytics = Depends(_a)):
    return ok(a.evolution(f))


@router.get("/nps/distribution")
def nps_distribution(f: dict = Depends(nps_filters), a: NpsAnalytics = Depends(_a)):
    return ok(a.distribution(f))


@router.get("/nps/by-state")
def nps_by_state(f: dict = Depends(nps_filters), a: NpsAnalytics = Depends(_a)):
    return ok(a.by_dimension("state", f))


@router.get("/nps/by-product")
def nps_by_product(f: dict = Depends(nps_filters), a: NpsAnalytics = Depends(_a)):
    return ok(a.by_dimension("product_line", f))


@router.get("/nps/by-carrier")
def nps_by_carrier(f: dict = Depends(nps_filters), a: NpsAnalytics = Depends(_a)):
    return ok({"carrier": a.by_dimension("carrier", f), "shipping_type": a.by_dimension("shipping_type", f)})


@router.get("/nps/correlation")
def nps_correlation(f: dict = Depends(nps_filters), a: NpsAnalytics = Depends(_a)):
    return ok(a.correlation(f))


@router.get("/nps/comments")
def nps_comments(f: dict = Depends(nps_filters), top: int = Query(default=20, ge=5, le=50), a: NpsAnalytics = Depends(_a)):
    return ok(a.comments(f, top))


@router.get("/nps/filters")
def nps_filter_options(a: NpsAnalytics = Depends(_a)):
    return ok(a.filter_options())


@router.get("/cx")
def cx(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)):
    return ok(cx_overview(db, lake, p))


@router.get("/logistics")
def logistics(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep),
              lake: Lakehouse = Depends(lake_dep)):
    return ok(logistics_overview(db, lake, p))


@router.get("/products")
def products(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep),
             lake: Lakehouse = Depends(lake_dep)):
    return ok(products_overview(db, lake, p))


@router.get("/regional")
def regional(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep),
             lake: Lakehouse = Depends(lake_dep)):
    return ok(regional_overview(db, lake, p))
