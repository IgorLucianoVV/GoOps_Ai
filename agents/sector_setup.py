"""IA ajudando a montar um setor: refina a sugestão de campos (nomes, rótulos, tipos, papéis) e propõe métricas.

Regras de segurança:
  * a IA recebe apenas o PERFIL dos campos (caminho, tipo inferido, preenchimento, cardinalidade e até 3 exemplos curtos,
    mascarados quando parecem dados pessoais) — nunca a base inteira;
  * o retorno é JSON validado campo a campo contra listas fechadas (tipos, papéis, tipos de fórmula); qualquer coisa
    fora disso é descartada;
  * a IA NUNCA consegue incluir um campo marcado como dado pessoal, nem criar métrica ativa: tudo volta como
    sugestão para revisão humana (e métricas seguem a aprovação com segregação de funções);
  * sem modelo configurado (ou em falha), vale a heurística determinística — identificada na resposta.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from goops_core.db import Database
from data_platform.sectors.datasets import ROLES, TYPES

from .routing.router import CostRouter

FORMULAS = {"count", "mean", "sum", "median", "percentile", "count_distinct", "rate"}
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")


def _extract_json(text: str) -> Any:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("resposta sem JSON")
    return json.loads(m.group(0))


def _prompt(sector: str, prof: Dict[str, Any]) -> str:
    fields = [{k: f[k] for k in ("path", "type", "role", "fill_pct", "distinct", "examples", "pii")} for f in prof["fields"]]
    return (
        "Você está configurando um conjunto de dados para o setor "
        f"'{sector}'. A partir do PERFIL dos campos, proponha para cada campo: name (snake_case, português, sem acento), "
        "label (rótulo curto em português), type (id|string|int|float|datetime|bool), role "
        "(key|time|dimension|measure|text|attribute) e include (true/false). Escolha key_field e time_field. "
        "Proponha até 6 métricas úteis para o setor no formato {key_suffix, name, description, unit, formula} onde formula "
        "é {type: count|mean|sum|median|percentile|count_distinct|rate, field?, q?, numerator?: {field, op, value?}, "
        "base_filter?: {field, op}} usando SOMENTE nomes de campos propostos. Responda apenas JSON: "
        '{"fields":[{"path":...,"name":...,"label":...,"type":...,"role":...,"include":...}],'
        '"key_field":...,"time_field":...,"metrics":[...]}\n'
        f"<evidence>{json.dumps(fields, ensure_ascii=False)[:12000]}</evidence>")


def _merge(prof: Dict[str, Any], ai: Dict[str, Any]) -> Dict[str, Any]:
    by_path = {f["path"]: dict(f) for f in prof["fields"]}
    for g in ai.get("fields") or []:
        f = by_path.get(g.get("path"))
        if not f:
            continue
        if isinstance(g.get("name"), str) and NAME_RE.match(g["name"]):
            f["name"] = g["name"]
        if isinstance(g.get("label"), str) and 0 < len(g["label"]) <= 80:
            f["label"] = g["label"]
        if g.get("type") in TYPES:
            f["type"] = g["type"]
        if g.get("role") in ROLES:
            f["role"] = g["role"]
        if isinstance(g.get("include"), bool):
            f["include"] = g["include"] and not f["pii"]      # a IA nunca inclui dado pessoal
        f["ai"] = True
    fields = list(by_path.values())
    seen: Dict[str, int] = {}
    for f in fields:                                         # nomes únicos
        seen[f["name"]] = seen.get(f["name"], 0) + 1
        if seen[f["name"]] > 1:
            f["name"] = f"{f['name']}_{seen[f['name']]}"
    names = {f["name"] for f in fields if f["include"]}
    key = ai.get("key_field") if ai.get("key_field") in names else prof["suggested_key"]
    time_f = ai.get("time_field") if ai.get("time_field") in names else prof["suggested_time_field"]
    metrics = []
    for m in (ai.get("metrics") or [])[:6]:
        fm = m.get("formula") or {}
        if fm.get("type") not in FORMULAS:
            continue
        used = {fm.get("field"), (fm.get("numerator") or {}).get("field"), (fm.get("base_filter") or {}).get("field")} - {None}
        if not used <= names:
            continue
        suffix = re.sub(r"[^A-Z0-9_]", "_", str(m.get("key_suffix") or "IA").upper())[:30] or "IA"
        metrics.append({"key_suffix": suffix, "name": str(m.get("name") or suffix)[:120],
                        "description": str(m.get("description") or "Sugerida por IA; revise antes de aprovar.")[:500],
                        "unit": str(m.get("unit") or "")[:40] or "valor",
                        "formula": {k: v for k, v in fm.items() if k in ("type", "field", "q", "numerator", "base_filter")}})
    return {**prof, "fields": fields, "suggested_key": key, "suggested_time_field": time_f, "ai_metrics": metrics}


def refine_with_ai(db: Database, sector: str, prof: Dict[str, Any]) -> Dict[str, Any]:
    router = CostRouter(db)
    res = router.run(agent_key="assistant", task="sector_setup", deterministic=lambda: {**prof, "ai_metrics": []},
                     prompt=lambda: _prompt(sector, prof), max_tokens=2500,
                     postprocess=lambda text: _merge(prof, _extract_json(text)))
    return {**res["output"], "generated_by": res["generated_by"], "fallback_reason": res.get("fallback_reason")}
