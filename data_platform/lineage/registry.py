"""Data Lineage: grafo de dependências fonte -> bronze -> silver -> gold -> métrica.

Nós são identificados por "<tipo>:<chave>" (source, bronze, dataset, metric).
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional

from goops_core.db import Database
from goops_core.errors import NotFound, ValidationError
from goops_core.util import jload, new_id, now_iso

NODE_TYPES = ("source", "bronze", "dataset", "metric")


def add_edge(db: Database, upstream: str, downstream: str, transform: str) -> None:
    for node in (upstream, downstream):
        if node.split(":", 1)[0] not in NODE_TYPES:
            raise ValidationError(f"Tipo de nó inválido: {node}")
    ts = now_iso()
    db.execute("INSERT INTO lineage_edges (id, upstream, downstream, transform, created_at, updated_at) "
               "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (upstream, downstream) DO UPDATE SET "
               "transform = excluded.transform, updated_at = excluded.updated_at",
               (new_id("LIN"), upstream, downstream, transform, ts, ts))


def _node_details(db: Database, node: str) -> dict:
    kind, key = node.split(":", 1)
    info: Dict[str, object] = {"id": node, "type": kind, "key": key}
    if kind == "source":
        r = db.fetchone("SELECT key, name, entity, connector, status, is_demo, last_sync_at FROM sources WHERE key = ?", (key,))
        if r:
            last = db.fetchone("SELECT id, status, records_ingested, schema_version, finished_at FROM ingestion_runs "
                               "WHERE source_key = ? ORDER BY started_at DESC LIMIT 1", (key,))
            info.update(label=r["name"], layer="L0 Fontes", is_demo=bool(r["is_demo"]), details={**r, "last_run": last})
    elif kind in ("bronze", "dataset"):
        ds_key = f"bronze_{key}" if kind == "bronze" else key
        r = db.fetchone("SELECT key, layer, scope, domain, name, row_count, schema_version, last_built_at, "
                        "last_pipeline_run_id, is_demo FROM datasets WHERE key = ?", (ds_key,))
        if r:
            t = db.fetchone("SELECT transform, rule_version, executed_at FROM transformations WHERE dataset_key = ? "
                            "ORDER BY executed_at DESC LIMIT 1", (ds_key,))
            layer_label = {"bronze": "L1 Bronze", "silver": "L2 Silver", "gold_corporate": "L3 Gold corporativa",
                           "gold_domain": "L3 Gold de domínio"}.get(r["layer"], r["layer"])
            info.update(label=r["name"], layer=layer_label, is_demo=bool(r["is_demo"]),
                        details={**r, "last_transformation": t})
    elif kind == "metric":
        r = db.fetchone("SELECT metric_key, name, version, scope, domain, status, owner, formula_text FROM semantic_metrics "
                        "WHERE metric_key = ?", (key,))
        if r:
            info.update(label=r["name"], layer="L4 Semântica", details=r)
    info.setdefault("label", key)
    info.setdefault("layer", kind)
    return info


def graph(db: Database, node: Optional[str] = None, direction: str = "upstream", max_depth: int = 10) -> dict:
    edges = db.fetchall("SELECT upstream, downstream, transform, updated_at FROM lineage_edges")
    if node is None:
        nodes = {e["upstream"] for e in edges} | {e["downstream"] for e in edges}
        selected = edges
    else:
        all_nodes = {e["upstream"] for e in edges} | {e["downstream"] for e in edges}
        if node not in all_nodes:
            raise NotFound(f"Nó de lineage não encontrado: {node}")
        nodes, selected = {node}, []
        directions = ["upstream", "downstream"] if direction == "both" else [direction]
        for d in directions:
            queue, seen = deque([(node, 0)]), {node}
            while queue:
                cur, depth = queue.popleft()
                if depth >= max_depth:
                    continue
                for e in edges:
                    nxt = e["upstream"] if d == "upstream" and e["downstream"] == cur else (
                        e["downstream"] if d == "downstream" and e["upstream"] == cur else None)
                    if nxt:
                        if e not in selected:
                            selected.append(e)
                        if nxt not in seen:
                            seen.add(nxt); nodes.add(nxt); queue.append((nxt, depth + 1))
    return {"nodes": [_node_details(db, n) for n in sorted(nodes)], "edges": selected}


def upstream_path(db: Database, node: str) -> List[str]:
    """Lista ordenada de nós a montante (útil para explicar a origem de um indicador)."""
    g = graph(db, node, "upstream")
    return [n["id"] for n in g["nodes"]]
