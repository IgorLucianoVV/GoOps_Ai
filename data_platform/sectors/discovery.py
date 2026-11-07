"""Descoberta de campos de uma fonte: achata o payload, infere tipos e sugere papéis (chave, data, dimensão...).

Nada aqui executa código do usuário: só lê amostras e aplica heurísticas determinísticas e explicáveis.
Valores de campos que parecem dados pessoais são mascarados nos exemplos.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any, Dict, List

from ..silver.transforms import _parse_dt

PII_NAME = re.compile(r"(e-?mail|telefone|celular|fone|contato|cpf|cnpj|rg\b|nome|name|ip_?address|ipaddress|"
                      r"endereco|endereço|address|phone|whatsapp|cep)", re.I)
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.I)
TRUE_WORDS = {"sim", "s", "true", "yes", "y", "verdadeiro"}
FALSE_WORDS = {"nao", "não", "n", "false", "no", "falso"}
ID_NAME = re.compile(r"(^id$|_id$|^id_|codigo|código|protocolo|pedido|ticket|order|reference|numero|número|^n[ºo°])", re.I)
TIME_NAME = re.compile(r"(data|date|criad|created|entrada|abertura|emitid|timestamp|dt_)", re.I)
MAX_SAMPLE = 2000


def slug(text: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    if not t or not t[0].isalpha():
        t = f"campo_{t}" if t else "campo"
    return t[:50]


def flatten(payload: Any, prefix: str = "", depth: int = 0) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(payload, dict) and depth < 4:
        for k, v in payload.items():
            if str(k).startswith("_"):
                continue
            path = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(flatten(v, path, depth + 1))
            elif isinstance(v, list):
                if v and isinstance(v[0], dict):
                    out.update(flatten(v[0], f"{path}.0", depth + 1))
                else:
                    out[path] = None if not v else ", ".join(str(x) for x in v[:5])
            else:
                out[path] = v
    return out


def _is_num(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return v == v  # NaN
    try:
        float(str(v).replace(",", "."))
        return True
    except ValueError:
        return False


def infer_type(values: List[Any]) -> str:
    vals = [v for v in values if v not in (None, "") and not (isinstance(v, float) and v != v)]
    if not vals:
        return "string"
    words = {str(v).strip().lower() for v in vals}
    if all(isinstance(v, bool) for v in vals) or (words <= TRUE_WORDS | FALSE_WORDS and len(words) <= 4):
        return "bool"
    nums = [v for v in vals if _is_num(v)]
    if len(nums) >= 0.95 * len(vals):
        fl = [float(str(v).replace(",", ".")) for v in nums]
        return "int" if all(f.is_integer() for f in fl) else "float"
    dates = sum(1 for v in vals[:300] if not _parse_dt(v)[1] and _parse_dt(v)[0] is not None)
    if dates >= 0.9 * min(len(vals), 300):
        return "datetime"
    return "string"


def profile(records: List[dict]) -> Dict[str, Any]:
    # Bronze é append-only: a mesma linha aparece em várias execuções — analisa cada payload uma única vez
    seen, uniq_records = set(), []
    for r in reversed(records):
        h = r.get("_payload_hash") if isinstance(r, dict) else None
        if h and h in seen:
            continue
        seen.add(h)
        uniq_records.append(r)
    rows = [flatten(r.get("payload", r) if isinstance(r, dict) and "payload" in r else r) for r in uniq_records[:MAX_SAMPLE]]
    n = len(rows)
    cols: Dict[str, List[Any]] = defaultdict(list)
    for r in rows:
        for k, v in r.items():
            cols[k].append(v)
    fields: List[Dict[str, Any]] = []
    used_names: Counter = Counter()
    for path, vals in cols.items():
        filled = [v for v in vals if v not in (None, "") and not (isinstance(v, float) and v != v)]
        typ = infer_type(filled)
        distinct = len({str(v) for v in filled})
        avg_len = (sum(len(str(v)) for v in filled) / len(filled)) if filled else 0
        sample = filled[:200]
        emails = sum(1 for v in sample if EMAIL.fullmatch(str(v).strip() or "-"))
        pii = bool(PII_NAME.search(path)) or (bool(sample) and emails / len(sample) >= 0.2)
        name = slug(path.split(".")[-1] if "." in path else path)
        used_names[name] += 1
        if used_names[name] > 1:
            name = f"{name}_{used_names[name]}"
        uniq = distinct / len(filled) if filled else 0
        if typ in ("string", "int") and ID_NAME.search(path) and uniq >= 0.9:
            typ = "id"
        role = "attribute"
        if typ == "datetime":
            role = "time"
        elif typ == "bool":
            role = "dimension"
        elif typ in ("int", "float"):
            role = "measure" if distinct > 2 else "dimension"
        elif typ == "string":
            role = "text" if avg_len > 60 else ("dimension" if distinct <= 60 and uniq < 0.5 else "attribute")
        examples = [("•••" if pii else str(v)[:60]) for v in list(dict.fromkeys(str(x) for x in filled))[:3]]
        fields.append({"path": path, "name": name, "label": path.split(".")[-1], "type": typ, "role": role,
                       "fill_pct": round(len(filled) / n * 100, 1) if n else 0, "distinct": distinct,
                       "uniqueness": round(uniq, 3), "examples": examples, "pii": pii,
                       "include": not pii and role != "text"})
    # chave: id mais completo e único; data principal: primeira data bem preenchida (preferindo nomes de "entrada/criação")
    ids = sorted([f for f in fields if f["type"] == "id" and f["uniqueness"] >= 0.99 and f["fill_pct"] >= 99 and not f["pii"]],
                 key=lambda f: (not re.search(r"(^|_)id($|_)", f["name"]), -f["uniqueness"]))
    key = ids[0]["name"] if ids else None
    for f in fields:
        if f["type"] == "id":
            f["role"] = "key" if f["name"] == key else ("dimension" if f["distinct"] <= 60 else "attribute")
    times = sorted([f for f in fields if f["role"] == "time" and f["fill_pct"] >= 80],
                   key=lambda f: (not TIME_NAME.search(f["path"]) or "fecha" in f["path"].lower(), -f["fill_pct"]))
    time_field = times[0]["name"] if times else None
    return {"records_sampled": n, "fields": fields, "suggested_key": key, "suggested_time_field": time_field}
