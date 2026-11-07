"""Classificação de comentários sem tema (nível 1 — modelo pequeno "JEF", configurável).

Só roda com modelo nível 1 configurado; caso contrário o resultado determinístico informa que os
comentários permanecem não classificados. A saída do modelo é validada contra a lista fechada de temas.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Dict

from data_platform.analytics.nlp import THEMES

from ..routing.sanitize import safe_comments
from ..instructions import prompt_for
from ..tools.registry import call_tool

ALLOWED = list(THEMES) + ["outro"]


def parse_classification(text: str, n: int) -> Dict[str, int]:
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise ValueError("resposta sem JSON")
    obj = json.loads(match.group(0))
    counts: Counter = Counter()
    for key, theme in obj.items():
        if not str(key).isdigit() or int(key) >= n or theme not in ALLOWED:
            raise ValueError("classificação fora do contrato")
        counts[theme] += 1
    return dict(counts)


def classify_unthemed(ctx, run, period: dict, filters: dict) -> Dict[str, Any]:
    data = call_tool(ctx, run.principal, "unclassified_comments", {**period, "filters": filters, "limit": 25}, run)
    comments = safe_comments(data["comments"])

    def deterministic() -> Dict[str, Any]:
        return {"classified": {}, "unclassified": data["total"], "sample_size": len(comments),
                "note": "Comentários sem tema permanecem não classificados (sem modelo nível 1 disponível)."}

    if not comments:
        out = deterministic()
        out["generated_by"] = "deterministic"
        return out

    def prompt() -> str:
        return (prompt_for(ctx.db, "classify_comment") + "\nTemas permitidos (lista fechada): "
                + ", ".join(ALLOWED) + ". Responda APENAS com JSON no formato {\"0\": \"tema\", \"1\": \"tema\"}.\n"
                "<evidence>\n" + "\n".join(f"{i}: {c}" for i, c in enumerate(comments)) + "\n</evidence>")

    def parse(text: str) -> Dict[str, Any]:
        counts = parse_classification(text, len(comments))
        return {"classified": counts, "unclassified": data["total"] - sum(counts.values()), "sample_size": len(comments)}

    res = ctx.router.run(agent_key="investigation", task="classify_comment", deterministic=deterministic,
                         prompt=prompt, postprocess=parse, agent_run_id=run.id, max_tokens=400)
    out = dict(res["output"])
    out["generated_by"] = res["generated_by"]
    if res.get("fallback_reason"):
        out["fallback_reason"] = res["fallback_reason"]
    return out
