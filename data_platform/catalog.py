"""Catálogo de datasets (todas as camadas) e registro de transformações."""
from __future__ import annotations

from typing import List, Optional

from goops_core.db import Database
from goops_core.errors import NotFound
from goops_core.util import jdump, jload, new_id, now_iso

LAYER_ORDER = {"bronze": 1, "silver": 2, "gold_corporate": 3, "gold_domain": 4, "quarantine": 5}


def register_dataset(db: Database, *, key: str, layer: str, scope: str, name: str, description: str,
                     grain: str, path: Optional[str], fmt: Optional[str], row_count: int, schema: dict,
                     schema_version: str, is_demo: bool, pipeline_run_id: Optional[str] = None,
                     domain: Optional[str] = None, sensitivity: str = "internal",
                     synthetic_fields: Optional[List[str]] = None) -> None:
    db.execute(
        "INSERT INTO datasets (key, layer, scope, domain, name, description, grain, path, format, row_count, schema_def, "
        "schema_version, sensitivity, is_demo, last_built_at, last_pipeline_run_id, synthetic_fields) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (key) DO UPDATE SET layer = excluded.layer, scope = excluded.scope, domain = excluded.domain, "
        "name = excluded.name, description = excluded.description, grain = excluded.grain, path = excluded.path, "
        "format = excluded.format, row_count = excluded.row_count, schema_def = excluded.schema_def, "
        "schema_version = excluded.schema_version, sensitivity = excluded.sensitivity, is_demo = excluded.is_demo, "
        "last_built_at = excluded.last_built_at, last_pipeline_run_id = excluded.last_pipeline_run_id, "
        "synthetic_fields = excluded.synthetic_fields",
        (key, layer, scope, domain, name, description, grain, path, fmt, int(row_count), jdump(schema),
         schema_version, sensitivity, int(is_demo), now_iso(), pipeline_run_id, jdump(sorted(synthetic_fields or []))))


def record_transformation(db: Database, *, dataset_key: str, inputs: List[str], transform: str,
                          rule_version: str, rows_in: int, rows_out: int, actor: str,
                          pipeline_run_id: Optional[str]) -> None:
    db.execute(
        "INSERT INTO transformations (id, pipeline_run_id, dataset_key, inputs, transform, rule_version, rows_in, "
        "rows_out, executed_at, actor) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (new_id("TRF"), pipeline_run_id, dataset_key, jdump(inputs), transform, rule_version, int(rows_in),
         int(rows_out), now_iso(), actor))


def _row(r: dict) -> dict:
    r["schema"] = jload(r.pop("schema_def", None), {})
    r["is_demo"] = bool(r["is_demo"])
    r["synthetic_fields"] = jload(r.get("synthetic_fields"), []) or []
    return r


def list_datasets(db: Database, layer: Optional[str] = None, domain: Optional[str] = None) -> List[dict]:
    clauses, params = [], []
    if layer:
        clauses.append("layer = ?"); params.append(layer)
    if domain:
        clauses.append("domain = ?"); params.append(domain)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = [_row(r) for r in db.fetchall(f"SELECT * FROM datasets {where}", params)]
    rows.sort(key=lambda r: (LAYER_ORDER.get(r["layer"], 9), r["key"]))
    return rows


def get_dataset(db: Database, key: str) -> dict:
    r = db.fetchone("SELECT * FROM datasets WHERE key = ?", (key,))
    if not r:
        raise NotFound(f"Dataset {key} não encontrado.")
    ds = _row(r)
    ds["transformations"] = [
        {**t, "inputs": jload(t["inputs"], [])}
        for t in db.fetchall("SELECT * FROM transformations WHERE dataset_key = ? ORDER BY executed_at DESC LIMIT 20",
                             (key,))
    ]
    return ds


STORAGE_LAYER = {"silver": "silver", "gold_corporate": "gold/corporate", "quarantine": "quarantine"}


def storage_layer_for(ds: dict) -> Optional[str]:
    if ds["layer"] == "gold_domain":
        return f"gold/domains/{ds['domain']}"
    return STORAGE_LAYER.get(ds["layer"])
