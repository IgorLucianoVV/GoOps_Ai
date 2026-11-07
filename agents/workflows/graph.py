"""Executor de grafo de estados (hierárquico, controlado e persistido).

Inspirado no modelo StateGraph do LangGraph: nós são funções puras sobre um estado
compartilhado; arestas podem ser condicionais; um nó pode interromper o fluxo
("interrupt") para aguardar aprovação humana, e o fluxo é retomado a partir do nó
indicado. O estado e cada passo são persistidos em workflow_runs (auditável).
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Union

from goops_core.db import Database
from goops_core.errors import GoOpsError
from goops_core.util import jdump, jload, new_id, now_iso

END = "__end__"
NodeFn = Callable[[Dict[str, Any]], Dict[str, Any]]


class Interrupt(Exception):
    def __init__(self, resume_at: str, reason: str):
        super().__init__(reason)
        self.resume_at, self.reason = resume_at, reason


class StateGraph:
    def __init__(self, name: str):
        self.name = name
        self.nodes: Dict[str, NodeFn] = {}
        self.edges: Dict[str, Union[str, Callable[[Dict[str, Any]], str]]] = {}
        self.entry: Optional[str] = None

    def add_node(self, name: str, fn: NodeFn) -> "StateGraph":
        self.nodes[name] = fn
        return self

    def add_edge(self, src: str, dst: Union[str, Callable[[Dict[str, Any]], str]]) -> "StateGraph":
        self.edges[src] = dst
        return self

    def set_entry(self, name: str) -> "StateGraph":
        self.entry = name
        return self

    def describe(self) -> dict:
        return {"name": self.name, "entry": self.entry, "nodes": list(self.nodes),
                "edges": {k: (v if isinstance(v, str) else "conditional") for k, v in self.edges.items()}}

    def run(self, db: Database, state: Dict[str, Any], run_id: Optional[str] = None, start: Optional[str] = None,
            incident_id: Optional[str] = None, max_steps: int = 25) -> Dict[str, Any]:
        if run_id is None:
            run_id = new_id("WFR")
            db.execute("INSERT INTO workflow_runs (id, workflow, incident_id, status, current_node, state, steps, "
                       "started_at, updated_at) VALUES (?, ?, ?, 'running', ?, ?, ?, ?, ?)",
                       (run_id, self.name, incident_id, start or self.entry, jdump(state), jdump([]), now_iso(), now_iso()))
            steps: List[dict] = []
        else:
            row = db.fetchone("SELECT steps FROM workflow_runs WHERE id = ?", (run_id,))
            steps = jload(row["steps"], []) if row else []
            db.execute("UPDATE workflow_runs SET status = 'running', updated_at = ? WHERE id = ?", (now_iso(), run_id))
        state = {**state, "workflow_run_id": run_id}
        node = start or self.entry
        status, error = "completed", None
        for _ in range(max_steps):
            if node == END or node is None:
                break
            t0 = time.perf_counter()
            try:
                update = self.nodes[node](state) or {}
                state.update(update)
                steps.append({"node": node, "status": "success", "ms": int((time.perf_counter() - t0) * 1000), "ts": now_iso()})
            except Interrupt as it:
                steps.append({"node": node, "status": "interrupted", "reason": it.reason, "ts": now_iso()})
                db.execute("UPDATE workflow_runs SET status = 'waiting', current_node = ?, state = ?, steps = ?, "
                           "updated_at = ? WHERE id = ?", (it.resume_at, jdump(state), jdump(steps), now_iso(), run_id))
                return {"run_id": run_id, "status": "waiting", "resume_at": it.resume_at, "state": state}
            except Exception as exc:  # noqa: BLE001
                error = exc.message if isinstance(exc, GoOpsError) else f"{type(exc).__name__}: {str(exc)[:300]}"
                steps.append({"node": node, "status": "failed", "error": error, "ts": now_iso()})
                status = "failed"
                break
            nxt = self.edges.get(node, END)
            node = nxt(state) if callable(nxt) else nxt
            db.execute("UPDATE workflow_runs SET current_node = ?, state = ?, steps = ?, updated_at = ? WHERE id = ?",
                       (node, jdump(state), jdump(steps), now_iso(), run_id))
        db.execute("UPDATE workflow_runs SET status = ?, current_node = ?, state = ?, steps = ?, updated_at = ?, "
                   "finished_at = ?, error = ? WHERE id = ?",
                   (status, None, jdump(state), jdump(steps), now_iso(), now_iso(), error, run_id))
        return {"run_id": run_id, "status": status, "error": error, "state": state}


def list_workflow_runs(db: Database, incident_id: Optional[str] = None, limit: int = 100) -> List[dict]:
    limit = max(1, min(int(limit), 500))
    if incident_id:
        rows = db.fetchall(f"SELECT * FROM workflow_runs WHERE incident_id = ? ORDER BY started_at DESC LIMIT {limit}",
                           (incident_id,))
    else:
        rows = db.fetchall(f"SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT {limit}")
    for r in rows:
        r["state"] = jload(r["state"], {})
        r["steps"] = jload(r["steps"], [])
    return rows
