"""Perfis de mapeamento editáveis pela interface (Fonte -> Silver).

* Perfis embutidos (default, gocase_xlsx) ficam em mappings.py e são somente-leitura.
* Perfis personalizados ficam no banco (mapping_profiles), versionados (mapping_profile_versions) e auditados.
* Uma definição só pode referenciar campos CANÔNICOS, tipos permitidos e derivações controladas — nada de código.
* A prévia aplica o mapeamento e as regras de qualidade a payloads reais da Bronze, SEM gravar nada.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from goops_core.audit import record_audit
from goops_core.db import Database
from goops_core.errors import NotFound, ValidationError
from goops_core.permissions import Principal, require_permission
from goops_core.util import jdump, jload, new_id, now_iso, to_jsonable

from ..storage import Lakehouse
from .mappings import MAPPINGS, PROFILES, mapping_for

TYPES = ["id", "id_int", "string", "upper", "uf", "int", "float", "datetime"]
DERIVATIONS = {"product_line_from_name": "Linha de produto a partir do nome do material (regra v1.0)"}
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
_PATH_RE = re.compile(r"^[^\x00-\x1f]{1,120}$")

FIELD_HELP = {
    "order_id": "Chave canônica do pedido (relaciona pedidos, avaliações e entregas).",
    "evaluation_id": "Identificador único da avaliação.", "delivery_id": "Identificador único da entrega.",
    "order_item_id": "Chave do item (apenas fontes por item).", "score": "Nota NPS de 0 a 10.",
    "evaluation_date": "Data da avaliação (referência temporal do NPS).", "order_date": "Data do pedido.",
    "order_total": "Valor (do pedido ou do item).", "state": "UF (aceita sigla ou nome do estado).",
    "carrier": "Transportadora.", "shipping_type": "Tipo de frete.", "delivery_days": "Dias de entrega informados pela fonte.",
}


def canonical_schema() -> Dict[str, Any]:
    out = {}
    for entity, m in MAPPINGS.items():
        out[entity] = {"dataset": m["dataset"], "natural_key": m["natural_key"],
                       "fields": [{"field": f, "type": spec["type"], "required": bool(spec.get("required")),
                                   "help": FIELD_HELP.get(f)} for f, spec in m["fields"].items()]}
    return {"entities": out, "types": TYPES, "derivations": DERIVATIONS, "grains": {"orders": ["order", "item"]}}


def _custom_row(db: Database, profile: str, entity: str) -> Optional[dict]:
    return db.fetchone("SELECT * FROM mapping_profiles WHERE profile_key = ? AND entity = ?", (profile, entity))


def profile_exists(db: Database, profile: str) -> bool:
    return profile in PROFILES or bool(db.fetchone("SELECT id FROM mapping_profiles WHERE profile_key = ?", (profile,)))


def resolve_mapping(db: Database, entity: str, profile: str = "default") -> Dict[str, Any]:
    if profile in PROFILES:
        return mapping_for(entity, profile)
    row = _custom_row(db, profile, entity)
    if not row:
        if db.fetchone("SELECT id FROM mapping_profiles WHERE profile_key = ?", (profile,)):
            return mapping_for(entity, "default")  # perfil existe, mas não sobrepõe esta entidade
        raise ValidationError(f"Perfil de mapeamento desconhecido: {profile}")
    m = mapping_for(entity, profile, override=jload(row["definition"], {}))
    m["version"] = f"{profile}-v{row['version']}"
    return m


def validate_definition(entity: str, definition: Dict[str, Any]) -> Dict[str, Any]:
    if entity not in MAPPINGS:
        raise ValidationError(f"Entidade inválida: {entity}")
    if not isinstance(definition, dict):
        raise ValidationError("Definição deve ser um objeto.")
    canonical = MAPPINGS[entity]["fields"]
    allowed_top = {"fields", "grain", "natural_key"}
    if set(definition) - allowed_top:
        raise ValidationError(f"Chaves não permitidas: {sorted(set(definition) - allowed_top)}")
    clean: Dict[str, Any] = {"fields": {}}
    grain = definition.get("grain", MAPPINGS[entity]["grain"])
    if entity == "orders" and grain not in ("order", "item"):
        raise ValidationError("Grão de pedidos deve ser 'order' ou 'item'.")
    if entity != "orders" and grain != MAPPINGS[entity]["grain"]:
        raise ValidationError("Somente pedidos aceitam grão por item.")
    clean["grain"] = grain
    for field, spec in (definition.get("fields") or {}).items():
        if field not in canonical:
            raise ValidationError(f"Campo não canônico: {field}")
        if not isinstance(spec, dict):
            raise ValidationError(f"Especificação inválida para {field}.")
        ftype = spec.get("type", canonical[field]["type"])
        if ftype not in TYPES:
            raise ValidationError(f"Tipo inválido em {field}: {ftype}")
        out: Dict[str, Any] = {"type": ftype}
        modes = [k for k in ("from", "compose", "derive") if k in spec]
        if len(modes) > 1:
            raise ValidationError(f"{field}: use apenas um entre from, compose e derive.")
        if "derive" in spec:
            if spec["derive"] not in DERIVATIONS:
                raise ValidationError(f"Derivação não permitida: {spec['derive']}")
            if not isinstance(spec.get("source"), str) or not _PATH_RE.match(spec["source"]):
                raise ValidationError(f"{field}: informe 'source' para a derivação.")
            out.update(derive=spec["derive"], source=spec["source"])
        elif "compose" in spec:
            parts = spec["compose"]
            if not isinstance(parts, list) or not 2 <= len(parts) <= 4 or not all(isinstance(p, str) and _PATH_RE.match(p) for p in parts):
                raise ValidationError(f"{field}: 'compose' deve listar de 2 a 4 caminhos.")
            out["compose"] = parts
        else:
            paths = spec.get("from", [])
            if isinstance(paths, str):
                paths = [paths]
            if not isinstance(paths, list) or len(paths) > 10 or not all(isinstance(p, str) and _PATH_RE.match(p) for p in paths):
                raise ValidationError(f"{field}: 'from' deve ser uma lista de até 10 caminhos.")
            out["from"] = [p.strip() for p in paths if p.strip()]
        if canonical[field].get("required"):
            out["required"] = True
        clean["fields"][field] = out
    natural_key = definition.get("natural_key") or ("order_item_id" if grain == "item" else MAPPINGS[entity]["natural_key"])
    if natural_key not in canonical:
        raise ValidationError(f"Chave natural inválida: {natural_key}")
    clean["natural_key"] = natural_key
    effective = mapping_for(entity, "default", override=clean)["fields"]
    for must in {natural_key, "order_id"}:
        spec = effective[must]
        if not (spec.get("from") or spec.get("compose") or spec.get("derive")):
            raise ValidationError(f"O campo '{must}' precisa de uma origem (é chave obrigatória).")
    return clean


def list_profiles(db: Database) -> List[dict]:
    out = []
    for key, ents in PROFILES.items():
        for entity in MAPPINGS:
            m = mapping_for(entity, key)
            out.append({"profile_key": key, "entity": entity, "builtin": True, "version": m["version"],
                        "definition": {"fields": m["fields"], "grain": m.get("grain"), "natural_key": m["natural_key"]},
                        "customized": entity in ents, "updated_at": None, "updated_by": None, "description": "Perfil embutido"})
    for r in db.fetchall("SELECT * FROM mapping_profiles ORDER BY profile_key, entity"):
        m = mapping_for(r["entity"], r["profile_key"], override=jload(r["definition"], {}))
        out.append({"profile_key": r["profile_key"], "entity": r["entity"], "builtin": False, "version": r["version"],
                    "definition": {"fields": m["fields"], "grain": m.get("grain"), "natural_key": m["natural_key"]},
                    "customized": True, "updated_at": r["updated_at"], "updated_by": r["updated_by"],
                    "description": r["description"], "based_on": r["based_on"]})
    for p in out:
        p["used_by"] = [s["key"] for s in db.fetchall("SELECT key, config, entity FROM sources")
                        if s["entity"] == p["entity"] and (jload(s["config"], {}) or {}).get("mapping_profile", "default") == p["profile_key"]]
    return out


def save_profile(db: Database, actor: Principal, profile_key: str, entity: str, definition: Dict[str, Any],
                 change_note: str, description: str = "", based_on: Optional[str] = None) -> dict:
    require_permission(actor, "data:write")
    if profile_key in PROFILES:
        raise ValidationError("Perfis embutidos são somente-leitura. Crie um novo perfil (ex.: duplicando este).")
    if not _KEY_RE.match(profile_key or ""):
        raise ValidationError("Chave do perfil inválida (minúsculas, números e _; 3–41 caracteres).")
    if not change_note or len(change_note) < 5:
        raise ValidationError("Descreva a alteração (mín. 5 caracteres).")
    clean = validate_definition(entity, definition)
    row = _custom_row(db, profile_key, entity)
    ts = now_iso()
    version = (row["version"] + 1) if row else 1
    if row:
        db.execute("UPDATE mapping_profiles SET version = ?, definition = ?, description = ?, updated_by = ?, updated_at = ? "
                   "WHERE id = ?", (version, jdump(clean), description or row["description"], actor.actor_label, ts, row["id"]))
    else:
        db.execute("INSERT INTO mapping_profiles (id, profile_key, entity, version, definition, description, based_on, "
                   "updated_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (new_id("MAP"), profile_key, entity, version, jdump(clean), description, based_on, actor.actor_label, ts, ts))
    db.execute("INSERT INTO mapping_profile_versions (id, profile_key, entity, version, definition, change_note, created_by, "
               "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (new_id("MPV"), profile_key, entity, version, jdump(clean), change_note, actor.actor_label, ts))
    record_audit(db, actor, "mapping.save", "mapping_profile", f"{profile_key}:{entity}", {"version": version, "note": change_note})
    return next(p for p in list_profiles(db) if p["profile_key"] == profile_key and p["entity"] == entity)


def profile_versions(db: Database, profile_key: str, entity: str) -> List[dict]:
    rows = db.fetchall("SELECT * FROM mapping_profile_versions WHERE profile_key = ? AND entity = ? ORDER BY version DESC",
                       (profile_key, entity))
    if not rows and profile_key not in PROFILES:
        raise NotFound("Perfil não encontrado.")
    for r in rows:
        r["definition"] = jload(r["definition"], {})
    return rows


def _flatten_keys(payload: Any, prefix: str = "", depth: int = 0) -> List[str]:
    keys: List[str] = []
    if isinstance(payload, dict) and depth < 4:
        for k, v in payload.items():
            path = f"{prefix}{k}"
            keys.append(path)
            if isinstance(v, dict):
                keys.extend(_flatten_keys(v, path + ".", depth + 1))
    return keys


def preview(db: Database, lake: Lakehouse, actor: Principal, entity: str, definition: Dict[str, Any],
            source_key: Optional[str] = None, sample: Optional[List[dict]] = None, limit: int = 200) -> Dict[str, Any]:
    """Aplica o mapeamento a payloads reais (Bronze da fonte) ou a uma amostra colada — sem gravar nada."""
    require_permission(actor, "data:read")
    from ..quality.engine import run_row_rules
    from .transforms import map_records
    clean = validate_definition(entity, definition)
    mapping = mapping_for(entity, "preview", override=clean)
    limit = max(1, min(int(limit), 1000))
    if sample is not None:
        if not isinstance(sample, list) or not all(isinstance(x, dict) for x in sample):
            raise ValidationError("A amostra deve ser uma lista de objetos JSON.")
        envelopes = [{"_source": "amostra", "_run_id": "preview", "_bronze_id": f"preview:{i}", "_ingested_at": now_iso(),
                      "_payload_hash": str(i), "payload": p} for i, p in enumerate(sample[:limit])]
    else:
        if not source_key:
            raise ValidationError("Informe uma fonte (source_key) ou uma amostra de payloads.")
        src = db.fetchone("SELECT key, entity FROM sources WHERE key = ?", (source_key,))
        if not src:
            raise NotFound("Fonte não encontrada.")
        if src["entity"] != entity:
            raise ValidationError(f"A fonte {source_key} é da entidade {src['entity']}, não {entity}.")
        envelopes = lake.read_bronze(source_key)[-limit:]
    if not envelopes:
        return {"rows": [], "records": 0, "message": "Sem payloads na Bronze para esta fonte. Sincronize a fonte ou cole uma amostra."}
    df = map_records(envelopes, entity, "preview", mapping=mapping)
    valid, quarantined, results = run_row_rules(df, MAPPINGS[entity]["dataset"], clean["natural_key"])
    key_counts: Counter = Counter()
    for env in envelopes:
        key_counts.update(_flatten_keys(env.get("payload") or {}))
    used = set()
    for spec in mapping["fields"].values():
        used.update(spec.get("from", []) or [])
        used.update(spec.get("compose", []) or [])
        if spec.get("source"):
            used.add(spec["source"])
    n = len(df)
    fields = []
    for f, spec in mapping["fields"].items():
        errors = int(df["_cast_errors"].map(lambda e: f in (e or {})).sum())
        filled = int(df[f].notna().sum())
        fields.append({"field": f, "type": spec["type"], "required": bool(spec.get("required")),
                       "coverage_pct": round(filled / n * 100, 1) if n else None, "cast_errors": errors,
                       "configured": bool(spec.get("from") or spec.get("compose") or spec.get("derive")),
                       "examples": [to_jsonable(v) for v in df[f].dropna().astype(str).unique()[:3]]})
    cols = list(mapping["fields"])
    rows = []
    reasons = quarantined["_reasons"].to_dict() if len(quarantined) else {}
    for idx, r in df.head(25).iterrows():
        rows.append({"values": {c: to_jsonable(r[c]) for c in cols}, "cast_errors": r["_cast_errors"] or {},
                     "quarantine_reasons": (reasons.get(idx) or "").split("|") if idx in reasons else []})
    return {
        "records": n, "valid": int(len(valid)), "quarantined": int(len(quarantined)),
        "fields": fields, "rows": rows,
        "dq": [{k: r[k] for k in ("rule_key", "severity", "failed", "checked", "status")} for r in results],
        "payload_keys": [{"path": k, "count": c, "used": k in used} for k, c in key_counts.most_common(80)],
        "unused_keys": [k for k, _ in key_counts.most_common() if k not in used][:40],
        "mapping_version": "prévia (não salva)",
    }
