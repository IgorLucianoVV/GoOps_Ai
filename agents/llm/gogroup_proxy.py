"""AI Proxy do Gogroup: Jev (`/v1/systemone`) para decisões tipadas rápidas e baratas.

Usado pelo Agente de Atendimento para desempatar a intenção de mensagens ambíguas: devolve a escolha com
probabilidade; abaixo de 0,7 de confiança o caso continua com uma pessoa. O custo estimado de cada chamada
(US$ por tokens de entrada, informado pelo proxy) é registrado em `llm_calls`. O token vem do cofre de
configurações (Settings › Modelos e chaves) ou de AI_PROXY_API_KEY — nunca do código.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from goops_core.db import Database
from goops_core.errors import ExternalSourceError, ValidationError
from goops_core.util import new_id, now_iso

from .providers import GOGROUP_BASE_URL


def jev(db: Database, token: Optional[str], state: Any, questions: Dict[str, Any], *, agent_key: str, task: str,
        agent_run_id: Optional[str] = None, timeout: int = 15) -> Dict[str, Any]:
    if not token:
        raise ValidationError("Token do AI Proxy Gogroup não configurado.")
    import requests
    t0 = time.perf_counter()
    try:
        r = requests.post(f"{GOGROUP_BASE_URL}/systemone", timeout=timeout,
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                          json={"state": state, "questions": questions})
    except requests.RequestException as exc:
        _log(db, agent_key, task, agent_run_id, "jev", None, None, False, type(exc).__name__)
        raise ExternalSourceError(f"AI Proxy indisponível ({type(exc).__name__}).") from exc
    latency = int((time.perf_counter() - t0) * 1000)
    if r.status_code >= 400:
        _log(db, agent_key, task, agent_run_id, "jev", None, None, False, f"HTTP {r.status_code}")
        raise ExternalSourceError(f"AI Proxy respondeu HTTP {r.status_code}.")
    body = r.json()
    usage = body.get("usage") or {}
    cost = usage.get("estimated_cost_usd") or r.headers.get("x-estimated-cost-usd")
    _log(db, agent_key, task, agent_run_id, body.get("model") or "jev", usage.get("input_tokens"),
         float(cost) if cost is not None else None, True, None, latency)
    return {"answers": body.get("answers") or {}, "model": body.get("model"), "usage": usage, "latency_ms": latency}


def _log(db: Database, agent_key: str, task: str, run_id: Optional[str], model: str, tin: Optional[int],
         cost: Optional[float], ok: bool, error: Optional[str], latency: Optional[int] = None) -> None:
    db.execute("INSERT INTO llm_calls (id, agent_run_id, agent_key, task, level, provider, model, input_tokens, output_tokens, "
               "cost_usd, latency_ms, success, error, created_at) VALUES (?, ?, ?, ?, 1, 'gogroup', ?, ?, 0, ?, ?, ?, ?, ?)",
               (new_id("LLM"), run_id, agent_key, task, model, tin, cost, latency, int(ok), error, now_iso()))
