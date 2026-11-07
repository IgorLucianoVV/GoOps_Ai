"""Corporate Semantic Registry + Domain Semantic Registry.

Regras centrais:
 * Métricas corporativas (scope=corporate, chave METRIC_*) são a referência oficial.
 * Domínios podem ter métricas próprias, versionadas e documentadas, com chaves próprias.
 * Uma métrica de domínio só pode declarar `equivalent_to` uma métrica corporativa se usar
   exatamente a mesma definição, filtros e fonte. Caso contrário, é rejeitada.
 * Toda alteração gera nova versão (pendente) e só entra em vigor após aprovação.
 * Quem propõe não aprova a própria alteração (segregação de funções).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pandas as pd

from goops_core.audit import record_audit
from goops_core.db import Database
from goops_core.errors import Conflict, NotFound, PermissionDenied, ValidationError
from goops_core.permissions import SYSTEM_PRINCIPAL, Principal, can_access_domain, has_permission, require_permission
from goops_core.util import jdump, jload, new_id, now_iso

from ..catalog import get_dataset, storage_layer_for
from ..lineage.registry import add_edge
from ..storage import Lakehouse
from .engine import apply_filters, compute, compute_grouped, validate_condition, validate_definition
from .seed import CORPORATE_METRICS, DOMAIN_METRICS, DOMAINS

_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{3,60}$")
_JSON = ("formula_definition", "dimensions", "source_datasets", "filters")
_EDITABLE = ("name", "description", "formula_text", "formula_definition", "unit", "dimensions", "filters", "owner")


def _row(r: dict) -> dict:
    for f in _JSON:
        r[f] = jload(r.get(f), None)
    r["relationship"] = describe_relationship(r)
    return r


def describe_relationship(m: dict) -> str:
    if m["scope"] == "corporate":
        return "Métrica corporativa oficial"
    if m.get("equivalent_to"):
        return f"Equivalente à métrica corporativa {m['equivalent_to']} (definição idêntica)"
    if m.get("related_corporate_metric"):
        return (f"Métrica específica do domínio '{m['domain']}' — relacionada, mas NÃO equivalente, "
                f"a {m['related_corporate_metric']}")
    return f"Métrica específica do domínio '{m['domain']}'"


def _bump(version: str, major: bool) -> str:
    try:
        ma, mi = (int(x) for x in version.split("."))
    except ValueError:
        ma, mi = 1, 0
    return f"{ma + 1}.0" if major else f"{ma}.{mi + 1}"


def seed_domains(db: Database) -> None:
    for key, name, desc in DOMAINS:
        db.execute("INSERT INTO domains (key, name, description, status, created_at) VALUES (?, ?, ?, ?, ?) "
                   "ON CONFLICT (key) DO NOTHING", (key, name, desc, "active" if key != "finance" else "planned", now_iso()))
    # nomes antigos em inglês (bancos existentes) → português
    for key, old in (("cx", "Customer Experience"), ("finance", "Finance (preparado)")):
        new = next(n for k, n, _ in DOMAINS if k == key)
        db.execute("UPDATE domains SET name = ? WHERE key = ? AND name = ?", (new, key, old))


def list_domains(db: Database) -> List[dict]:
    return db.fetchall("SELECT * FROM domains ORDER BY created_at, key")


def _insert_metric(db: Database, m: dict, scope: str, status: str, actor: Principal) -> None:
    ts = now_iso()
    db.execute(
        "INSERT INTO semantic_metrics (id, metric_key, name, description, formula_text, formula_definition, unit, scope, "
        "domain, dimensions, source_datasets, filters, equivalent_to, related_corporate_metric, version, status, owner, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (new_id("MET"), m["metric_key"], m["name"], m["description"], m["formula_text"], jdump(m["formula_definition"]),
         m["unit"], scope, m.get("domain") if scope == "domain" else "corporate", jdump(m["dimensions"]),
         jdump(m["source_datasets"]), jdump(m.get("filters") or []), m.get("equivalent_to"),
         m.get("related_corporate_metric"), "1.0", status, m["owner"], ts, ts))
    snapshot = {k: m.get(k) for k in ("name", "description", "formula_text", "formula_definition", "unit", "dimensions",
                                      "filters", "owner", "source_datasets")}
    db.execute("INSERT INTO semantic_metric_versions (id, metric_key, version, snapshot, change_note, status, proposed_by, "
               "proposed_at, reviewed_by, reviewed_at) VALUES (?, ?, '1.0', ?, ?, ?, ?, ?, ?, ?)",
               (new_id("MVR"), m["metric_key"], jdump(snapshot), "Versão inicial",
                "approved" if status == "active" else "pending", actor.actor_label, ts,
                actor.actor_label if status == "active" else None, ts if status == "active" else None))
    for ds in m["source_datasets"]:
        add_edge(db, f"dataset:{ds}", f"metric:{m['metric_key']}", f"semantic definition v1.0")


def seed_metrics(db: Database) -> int:
    created = 0
    for m in CORPORATE_METRICS:
        if not db.fetchone("SELECT id FROM semantic_metrics WHERE metric_key = ?", (m["metric_key"],)):
            _insert_metric(db, m, "corporate", "active", SYSTEM_PRINCIPAL); created += 1
    for m in DOMAIN_METRICS:
        if not db.fetchone("SELECT id FROM semantic_metrics WHERE metric_key = ?", (m["metric_key"],)):
            _insert_metric(db, m, "domain", "active", SYSTEM_PRINCIPAL); created += 1
    return created


def rebuild_metric_lineage(db: Database) -> None:
    for m in db.fetchall("SELECT metric_key, version, source_datasets FROM semantic_metrics"):
        for ds in jload(m["source_datasets"], []):
            add_edge(db, f"dataset:{ds}", f"metric:{m['metric_key']}", f"semantic definition v{m['version']}")


def list_metrics(db: Database, scope: Optional[str] = None, domain: Optional[str] = None) -> List[dict]:
    clauses, params = [], []
    if scope:
        clauses.append("scope = ?"); params.append(scope)
    if domain:
        clauses.append("domain = ?"); params.append(domain)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return [_row(r) for r in db.fetchall(f"SELECT * FROM semantic_metrics {where} ORDER BY scope, metric_key", params)]


def get_metric(db: Database, key: str) -> dict:
    r = db.fetchone("SELECT * FROM semantic_metrics WHERE metric_key = ? OR id = ?", (key, key))
    if not r:
        raise NotFound(f"Métrica {key} não encontrada.")
    return _row(r)


def list_versions(db: Database, key: str) -> List[dict]:
    m = get_metric(db, key)
    rows = db.fetchall("SELECT * FROM semantic_metric_versions WHERE metric_key = ? ORDER BY proposed_at, version",
                       (m["metric_key"],))
    for r in rows:
        r["snapshot"] = jload(r["snapshot"], {})
        r["is_current"] = r["version"] == m["version"] and r["status"] == "approved"
    return rows


def pending_approvals(db: Database) -> List[dict]:
    rows = db.fetchall("SELECT v.*, m.scope, m.domain, m.name FROM semantic_metric_versions v "
                       "JOIN semantic_metrics m ON m.metric_key = v.metric_key WHERE v.status = 'pending' "
                       "ORDER BY v.proposed_at")
    for r in rows:
        r["snapshot"] = jload(r["snapshot"], {})
    return rows


def _dataset_fields(db: Database, datasets: List[str]) -> Optional[set]:
    fields: set = set()
    for ds in datasets:
        r = db.fetchone("SELECT schema_def FROM datasets WHERE key = ?", (ds,))
        if not r:
            return None  # dataset ainda não construído: validação estrutural apenas
        fields |= set(jload(r["schema_def"], {}).keys())
    return fields


def _validate_payload(db: Database, m: dict) -> None:
    for f in ("name", "description", "formula_text", "unit", "owner"):
        if not m.get(f) or not isinstance(m[f], str):
            raise ValidationError(f"Campo obrigatório: {f}")
    if not isinstance(m.get("dimensions"), list) or not isinstance(m.get("source_datasets"), list) \
            or not m["source_datasets"]:
        raise ValidationError("dimensions e source_datasets devem ser listas (source_datasets não vazia).")
    fields = _dataset_fields(db, m["source_datasets"])
    validate_definition(m["formula_definition"], fields)
    for cond in m.get("filters") or []:
        validate_condition(cond, fields)
    if fields is not None:
        missing = [d for d in m["dimensions"] if d not in fields]
        if missing:
            raise ValidationError(f"Dimensões inexistentes no dataset: {missing}")


def _check_equivalence(db: Database, m: dict) -> None:
    target = m.get("equivalent_to")
    if not target:
        return
    corp = get_metric(db, target)
    if corp["scope"] != "corporate":
        raise ValidationError("equivalent_to deve referenciar uma métrica corporativa.")
    same = (corp["formula_definition"] == m["formula_definition"] and (corp["filters"] or []) == (m.get("filters") or [])
            and corp["source_datasets"] == m["source_datasets"])
    if not same:
        raise ValidationError(
            f"A métrica usa critérios diferentes de {target} e não pode ser declarada equivalente. "
            f"Use 'related_corporate_metric' para indicar apenas relação.")


def create_metric(db: Database, actor: Principal, payload: Dict[str, Any]) -> dict:
    scope = payload.get("scope")
    key = (payload.get("metric_key") or "").strip()
    if scope not in ("corporate", "domain"):
        raise ValidationError("scope deve ser 'corporate' ou 'domain'.")
    if not _KEY_RE.match(key):
        raise ValidationError("metric_key inválida (MAIÚSCULAS, números e _).")
    if scope == "corporate":
        require_permission(actor, "semantic:write_corporate")
        if not key.startswith("METRIC_"):
            raise ValidationError("Métricas corporativas devem usar o prefixo METRIC_.")
    else:
        domain = payload.get("domain")
        if not domain or not db.fetchone("SELECT key FROM domains WHERE key = ? AND key <> 'corporate'", (domain,)):
            raise ValidationError("Domínio inválido para métrica de domínio.")
        require_permission(actor, "semantic:write", domain)
        if key.startswith("METRIC_"):
            raise ValidationError("O prefixo METRIC_ é reservado ao catálogo corporativo.")
    if db.fetchone("SELECT id FROM semantic_metrics WHERE metric_key = ?", (key,)):
        raise Conflict("metric_key já existe.")
    m = {k: payload.get(k) for k in ("name", "description", "formula_text", "formula_definition", "unit", "dimensions",
                                     "source_datasets", "filters", "owner", "domain", "equivalent_to",
                                     "related_corporate_metric")}
    m["metric_key"] = key
    _validate_payload(db, m)
    if scope == "domain":
        _check_equivalence(db, m)
    elif m.get("equivalent_to"):
        raise ValidationError("equivalent_to só se aplica a métricas de domínio.")
    _insert_metric(db, m, scope, "pending_approval", actor)
    record_audit(db, actor, "metric.create", "metric", key, {"scope": scope, "domain": m.get("domain")})
    return get_metric(db, key)


def propose_change(db: Database, actor: Principal, key: str, changes: Dict[str, Any], note: str) -> dict:
    m = get_metric(db, key)
    if m["scope"] == "corporate":
        require_permission(actor, "semantic:write_corporate")
    else:
        require_permission(actor, "semantic:write", m["domain"])
    bad = set(changes) - set(_EDITABLE)
    if bad:
        raise ValidationError(f"Campos não editáveis: {sorted(bad)}")
    if not note:
        raise ValidationError("Informe uma justificativa (change_note).")
    if db.fetchone("SELECT id FROM semantic_metric_versions WHERE metric_key = ? AND status = 'pending'", (m["metric_key"],)):
        raise Conflict("Já existe uma versão pendente para esta métrica.")
    current = {k: m.get(k) for k in _EDITABLE}
    current["source_datasets"] = m["source_datasets"]
    new = {**current, **changes}
    _validate_payload(db, {**new, "metric_key": key})
    if m["scope"] == "domain" and m.get("equivalent_to"):
        _check_equivalence(db, {**new, "equivalent_to": m["equivalent_to"]})
    major = new["formula_definition"] != current["formula_definition"] or (new.get("filters") or []) != (current.get("filters") or [])
    version = _bump(m["version"], major)
    db.execute("INSERT INTO semantic_metric_versions (id, metric_key, version, snapshot, change_note, status, proposed_by, "
               "proposed_at) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
               (new_id("MVR"), m["metric_key"], version, jdump(new), note, actor.actor_label, now_iso()))
    record_audit(db, actor, "metric.propose_change", "metric", m["metric_key"], {"version": version, "major": major})
    return {"metric_key": m["metric_key"], "proposed_version": version, "status": "pending", "major_change": major}


def review_version(db: Database, actor: Principal, key: str, version: str, approve: bool, note: str = "") -> dict:
    m = get_metric(db, key)
    v = db.fetchone("SELECT * FROM semantic_metric_versions WHERE metric_key = ? AND version = ?", (m["metric_key"], version))
    if not v:
        raise NotFound("Versão não encontrada.")
    if v["status"] != "pending":
        raise Conflict(f"Versão não está pendente (status: {v['status']}).")
    if m["scope"] == "corporate":
        require_permission(actor, "semantic:approve_corporate")
    else:
        require_permission(actor, "semantic:approve", m["domain"])
    if v["proposed_by"] == actor.actor_label:
        raise PermissionDenied("Segregação de funções: quem propõe não pode aprovar a própria alteração.")
    status = "approved" if approve else "rejected"
    ts = now_iso()
    db.execute("UPDATE semantic_metric_versions SET status = ?, reviewed_by = ?, reviewed_at = ?, review_note = ? "
               "WHERE id = ?", (status, actor.actor_label, ts, note, v["id"]))
    if approve:
        snap = jload(v["snapshot"], {})
        db.execute("UPDATE semantic_metrics SET name = ?, description = ?, formula_text = ?, formula_definition = ?, "
                   "unit = ?, dimensions = ?, filters = ?, owner = ?, version = ?, status = 'active', updated_at = ? "
                   "WHERE metric_key = ?",
                   (snap["name"], snap["description"], snap["formula_text"], jdump(snap["formula_definition"]),
                    snap["unit"], jdump(snap["dimensions"]), jdump(snap.get("filters") or []), snap["owner"], version, ts,
                    m["metric_key"]))
        for ds in m["source_datasets"]:
            add_edge(db, f"dataset:{ds}", f"metric:{m['metric_key']}", f"semantic definition v{version}")
    record_audit(db, actor, f"metric.version_{status}", "metric", m["metric_key"], {"version": version, "note": note})
    return get_metric(db, key)


# ------------------------------------------------------------------ cálculo governado
_FRAME_CACHE: Dict[str, tuple] = {}


def load_dataset_frame(db: Database, lake: Lakehouse, dataset_key: str) -> pd.DataFrame:
    ds = get_dataset(db, dataset_key)
    stamp = ds.get("last_built_at")
    cached = _FRAME_CACHE.get(dataset_key)
    if cached and cached[0] == stamp and cached[1] == str(lake.base):
        return cached[2]
    layer = storage_layer_for(ds)
    if not layer:
        raise ValidationError(f"Dataset {dataset_key} não é consultável por métricas.")
    df = lake.read_table(layer, dataset_key)
    _FRAME_CACHE[dataset_key] = (stamp, str(lake.base), df)
    return df


def clear_cache() -> None:
    _FRAME_CACHE.clear()


def _provenance(db: Database, m: dict, defn: dict, df: pd.DataFrame, group_by: Optional[str],
                applied: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Sinaliza quando o resultado depende de campos sintéticos ou inclui registros de demonstração.
    O campo de tempo só conta quando há filtro de período (senão não altera o valor)."""
    period = bool(applied) and any(k in applied for k in ("start", "end"))
    used = {defn.get("field"), defn.get("time_field") if period else None, group_by,
            (defn.get("numerator") or {}).get("field"), (defn.get("base_filter") or {}).get("field")}
    used |= {f.get("field") for f in (m.get("filters") or []) if isinstance(f, dict)}
    row = db.fetchone("SELECT synthetic_fields FROM datasets WHERE key = ?", (m["source_datasets"][0],))
    syn = set(jload(row["synthetic_fields"], []) or []) if row else set()
    fields = sorted(f for f in used if f and f in syn)
    base = df
    if defn.get("base_filter") and len(df):
        from .engine import condition_mask
        base = df[condition_mask(df, defn["base_filter"])]
    if defn.get("field") and defn.get("type") == "mean" and defn["field"] in base.columns:
        base = base[base[defn["field"]].notna()]
    demo_rows = bool("_is_demo" in base.columns and len(base) and base["_is_demo"].astype(bool).any())
    return {"synthetic_fields": fields, "includes_demo_rows": demo_rows, "synthetic": bool(fields) or demo_rows}


def compute_metric(db: Database, lake: Lakehouse, actor: Principal, key: str, filters: Optional[Dict[str, Any]] = None,
                   group_by: Optional[str] = None, frame: Optional[pd.DataFrame] = None,
                   allow_draft: bool = False) -> Dict[str, Any]:
    """Calcula uma métrica do catálogo aplicando filtros de dimensão/período validados.
    `allow_draft`: prévia de métrica ainda não aprovada (sinalizada como rascunho) para quem pode editá-la."""
    require_permission(actor, "analytics:read")
    m = get_metric(db, key)
    draft = m["status"] == "pending_approval" and allow_draft and has_permission(actor, "semantic:write", m["domain"])
    if m["status"] != "active" and not draft:
        raise ValidationError(f"Métrica {key} não está ativa (status: {m['status']}).")
    if m["scope"] == "domain" and not can_access_domain(actor, m["domain"]):
        raise PermissionDenied(f"Sem acesso ao domínio {m['domain']}.")
    defn = m["formula_definition"]
    df = frame if frame is not None else load_dataset_frame(db, lake, m["source_datasets"][0])
    df = apply_filters(df, m["filters"])
    applied = {}
    for dim, value in (filters or {}).items():
        if value in (None, "", []):
            continue
        if dim in ("start", "end"):
            tf = defn.get("time_field")
            if not tf:
                raise ValidationError("Métrica sem time_field não aceita filtro de período.")
            ts = pd.to_datetime(value, errors="coerce")
            if pd.isna(ts):
                raise ValidationError(f"Data inválida em '{dim}'.")
            df = df[df[tf] >= ts] if dim == "start" else df[df[tf] < ts + pd.Timedelta(days=1)]
        elif dim in m["dimensions"]:
            values = value if isinstance(value, list) else [value]
            df = df[df[dim].isin(values)]
        else:
            raise ValidationError(f"Filtro não permitido para {key}: {dim}")
        applied[dim] = value
    meta = {"metric_key": m["metric_key"], "version": m["version"], "scope": m["scope"], "domain": m["domain"],
            "unit": m["unit"], "formula_text": m["formula_text"], "filters_applied": applied,
            "relationship": m["relationship"], "status": m["status"], "draft": draft,
            **_provenance(db, m, defn, df, group_by, applied)}
    if group_by:
        if group_by not in m["dimensions"]:
            raise ValidationError(f"Agrupamento não permitido para {key}: {group_by}")
        return {"metric": meta, "groups": compute_grouped(defn, df, group_by)}
    return {"metric": meta, "result": compute(defn, df)}


# ------------------------------------------------------------------ domínios
_DOMAIN_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


def create_domain(db: Database, actor: Principal, key: str, name: str, description: str = "",
                  owner: Optional[str] = None) -> dict:
    require_permission(actor, "settings:write")
    if not _DOMAIN_RE.match(key or ""):
        raise ValidationError("Chave de domínio inválida (minúsculas, números e _).")
    if not name or len(name) > 80:
        raise ValidationError("Nome do domínio obrigatório (máx. 80).")
    if db.fetchone("SELECT key FROM domains WHERE key = ?", (key,)):
        raise Conflict("Domínio já existe.")
    db.execute("INSERT INTO domains (key, name, description, owner, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
               (key, name, description, owner, now_iso()))
    record_audit(db, actor, "domain.create", "domain", key, {"name": name, "owner": owner})
    return db.fetchone("SELECT * FROM domains WHERE key = ?", (key,))


def update_domain(db: Database, actor: Principal, key: str, name: Optional[str] = None, description: Optional[str] = None,
                  owner: Optional[str] = None, status: Optional[str] = None) -> dict:
    require_permission(actor, "settings:write")
    if key == "corporate" and status not in (None, "active"):
        raise ValidationError("O domínio corporativo não pode ser desativado.")
    if not db.fetchone("SELECT key FROM domains WHERE key = ?", (key,)):
        raise NotFound("Domínio não encontrado.")
    if status is not None and status not in ("active", "planned", "inactive"):
        raise ValidationError("Status inválido (active, planned, inactive).")
    sets, params = [], []
    for col, val in (("name", name), ("description", description), ("owner", owner), ("status", status)):
        if val is not None:
            sets.append(f"{col} = ?"); params.append(val)
    if sets:
        db.execute(f"UPDATE domains SET {', '.join(sets)} WHERE key = ?", (*params, key))
        record_audit(db, actor, "domain.update", "domain", key, {"name": name, "owner": owner, "status": status})
    return db.fetchone("SELECT * FROM domains WHERE key = ?", (key,))
