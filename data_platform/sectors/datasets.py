"""Conjuntos de dados configuráveis por setor (sem código).

Definição (JSON validado, sem expressões livres):
  {"source_keys": ["reclameaqui_file"],
   "key_field": "id", "time_field": "data_entrada",
   "fields": [{"name": "nota", "label": "Nota do consumidor", "from": "Nota do consumidor", "type": "float",
               "role": "measure"},
              {"name": "dias_resposta", "label": "Dias até o fechamento", "derive": "days_between",
               "args": ["data_entrada", "data_fechamento"], "type": "float", "role": "measure"}],
   "relationships": [{"field": "pedido", "dataset": "gold_orders", "on": "order_id", "bring": ["product_line"]}]}

Tipos: id, string, int, float, datetime, bool. Papéis: key, time, dimension, measure, text, attribute.
Derivações controladas: days_between(a, b), hours_between(a, b). Campos marcados como PII não são aceitos.
Pipeline: Bronze (fontes do setor) → silver_<key> (tipado, deduplicado, quarentena) → gold_<key> (Gold de domínio,
com coluna `month` AAAA-MM e campos trazidos de relacionamentos). As métricas do setor consultam gold_<key>.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from goops_core.audit import record_audit
from goops_core.db import Database
from goops_core.errors import Conflict, NotFound, ValidationError
from goops_core.permissions import Principal, require_permission
from goops_core.util import jdump, jload, new_id, now_iso

from ..catalog import record_transformation, register_dataset
from ..lineage.registry import add_edge
from ..silver.transforms import _cast, _write_quarantine, lookup, _MISSING
from ..storage import Lakehouse
from .discovery import FALSE_WORDS, TRUE_WORDS

KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")
TYPES = {"id", "string", "int", "float", "datetime", "bool"}
ROLES = {"key", "time", "dimension", "measure", "text", "attribute"}
DERIVES = {"days_between": "datetime", "hours_between": "datetime"}
RESERVED = {"month", "_is_demo", "_source", "_run_id", "_bronze_id", "_ingested_at", "_reasons", "_record_key"}
# Chaves sugeridas para as Golds do núcleo; qualquer Gold (corporativa ou de setor) pode ser relacionada.
JOINABLE = {"gold_orders": "order_id", "gold_delivery_performance": "order_id", "gold_customer_experience": "customer_id"}
BLOCKED_BRING = re.compile(r"(^_|customer_id|e_?mail|telefone|phone|cpf|nome|name$|comment|comentario)", re.I)


def joinable_datasets(db: Database, exclude: Optional[str] = None) -> List[Dict[str, Any]]:
    """Golds disponíveis para relacionamento, com colunas que podem ser trazidas (sem identificadores pessoais)."""
    out = []
    for r in db.fetchall("SELECT key, name, layer, domain, schema_def FROM datasets WHERE layer IN ('gold_corporate', "
                         "'gold_domain') ORDER BY layer, key"):
        if r["key"] == exclude:
            continue
        cols = list((jload(r["schema_def"], {}) or {}).keys())
        out.append({"key": r["key"], "name": r["name"], "layer": r["layer"], "domain": r["domain"],
                    "columns": [c for c in cols if not c.startswith("_")],
                    "bringable": [c for c in cols if not BLOCKED_BRING.search(c)],
                    "suggested_on": JOINABLE.get(r["key"])})
    return out


def _row(r: dict) -> dict:
    r["definition"] = jload(r["definition"], {})
    return r


def list_custom_datasets(db: Database, domain: Optional[str] = None) -> List[dict]:
    rows = db.fetchall("SELECT * FROM custom_datasets " + ("WHERE domain = ? " if domain else "") + "ORDER BY created_at",
                       (domain,) if domain else ())
    return [_row(r) for r in rows]


def get_custom_dataset(db: Database, key: str) -> dict:
    r = db.fetchone("SELECT * FROM custom_datasets WHERE key = ?", (key,))
    if not r:
        raise NotFound(f"Conjunto de dados {key} não encontrado.")
    return _row(r)


def gold_key(key: str) -> str:
    return f"gold_{key}"


def validate_definition(db: Database, d: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(d, dict):
        raise ValidationError("Definição inválida.")
    allowed = {"source_keys", "key_field", "time_field", "fields", "relationships"}
    if set(d) - allowed:
        raise ValidationError(f"Chaves não permitidas: {sorted(set(d) - allowed)}")
    sources = d.get("source_keys") or []
    if not sources or not all(isinstance(s, str) for s in sources):
        raise ValidationError("Informe ao menos uma fonte (source_keys).")
    for s in sources:
        if not db.fetchone("SELECT id FROM sources WHERE key = ?", (s,)):
            raise ValidationError(f"Fonte inexistente: {s}")
    fields = d.get("fields") or []
    if not fields or len(fields) > 80:
        raise ValidationError("Selecione entre 1 e 80 campos.")
    names, clean = set(), []
    for f in fields:
        name = str(f.get("name") or "")
        if not NAME_RE.match(name) or name in RESERVED:
            raise ValidationError(f"Nome de campo inválido: '{name}' (minúsculas, números e _).")
        if name in names:
            raise ValidationError(f"Campo duplicado: {name}")
        names.add(name)
        typ, role = f.get("type"), f.get("role")
        if typ not in TYPES:
            raise ValidationError(f"Tipo inválido em {name}: {typ}")
        if role not in ROLES:
            raise ValidationError(f"Papel inválido em {name}: {role}")
        if f.get("pii"):
            raise ValidationError(f"O campo {name} foi marcado como dado pessoal e não pode ser incluído.")
        out = {"name": name, "label": str(f.get("label") or name)[:80], "type": typ, "role": role}
        if f.get("derive"):
            if f["derive"] not in DERIVES:
                raise ValidationError(f"Derivação não permitida: {f['derive']}")
            args = f.get("args") or []
            if len(args) != 2:
                raise ValidationError(f"{f['derive']} exige dois campos de data.")
            out.update(derive=f["derive"], args=[str(a) for a in args], type="float")
        else:
            if not isinstance(f.get("from"), str) or not f["from"]:
                raise ValidationError(f"Informe a origem (caminho no payload) de {name}.")
            out["from"] = f["from"][:200]
        clean.append(out)
    by_name = {f["name"]: f for f in clean}
    for f in clean:
        for a in f.get("args", []):
            if a not in by_name or by_name[a]["type"] != "datetime" or by_name[a].get("derive"):
                raise ValidationError(f"{f['name']}: '{a}' deve ser um campo de data do próprio conjunto.")
    key_field, time_field = d.get("key_field"), d.get("time_field")
    if key_field not in by_name or by_name[key_field].get("derive"):
        raise ValidationError("Escolha o campo-chave (identificador único de cada registro).")
    if time_field is not None and (time_field not in by_name or by_name[time_field]["type"] != "datetime"):
        raise ValidationError("O campo de data principal deve ser um campo do tipo data.")
    rels = []
    targets = {t["key"]: t for t in joinable_datasets(db)}
    for r in d.get("relationships") or []:
        t = targets.get(r.get("dataset"))
        if not t or r.get("field") not in by_name:
            raise ValidationError(f"Relacionamento inválido: escolha um campo do conjunto e uma Gold existente ({r.get('dataset')}).")
        on = r.get("on") or t["suggested_on"]
        if on not in t["columns"]:
            raise ValidationError(f"Coluna de ligação inexistente em {t['key']}: {on}")
        bring = [b for b in (r.get("bring") or []) if isinstance(b, str) and b in t["bringable"] and b != on]
        clash = [b for b in bring if b in by_name or b == "month"]
        if clash:
            raise ValidationError(f"Colunas trazidas conflitam com campos do conjunto: {clash}")
        if not bring:
            raise ValidationError(f"Escolha ao menos uma coluna de {t['key']} para trazer.")
        rels.append({"field": r["field"], "dataset": t["key"], "on": on, "bring": bring[:10]})
    return {"source_keys": sources, "key_field": key_field, "time_field": time_field, "fields": clean,
            "relationships": rels}


def save_custom_dataset(db: Database, actor: Principal, *, key: str, domain: str, name: str, description: str,
                        definition: Dict[str, Any]) -> dict:
    require_permission(actor, "data:write")
    if not KEY_RE.match(key or ""):
        raise ValidationError("Chave inválida (minúsculas, números e _).")
    if not db.fetchone("SELECT key FROM domains WHERE key = ? AND key <> 'corporate'", (domain,)):
        raise ValidationError("Domínio (setor) inexistente.")
    clean = validate_definition(db, definition)
    for s in clean["source_keys"]:  # fontes do setor ficam marcadas com a entidade 'custom'
        src = db.fetchone("SELECT id, entity, config FROM sources WHERE key = ?", (s,))
        if src["entity"] not in ("custom",):
            raise ValidationError(f"A fonte {s} pertence à entidade '{src['entity']}' (núcleo). Use uma fonte do setor.")
    existing = db.fetchone("SELECT id, version, domain FROM custom_datasets WHERE key = ?", (key,))
    ts = now_iso()
    if existing:
        if existing["domain"] != domain:
            raise Conflict("Já existe um conjunto com esta chave em outro setor.")
        db.execute("UPDATE custom_datasets SET name = ?, description = ?, definition = ?, version = version + 1, "
                   "updated_by = ?, updated_at = ? WHERE key = ?", (name, description, jdump(clean), actor.actor_label, ts, key))
    else:
        db.execute("INSERT INTO custom_datasets (id, key, domain, name, description, definition, created_by, created_at, "
                   "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (new_id("CDS"), key, domain, name, description, jdump(clean), actor.actor_label, ts, ts))
    record_audit(db, actor, "sector.dataset_save", "dataset", key, {"domain": domain, "fields": len(clean["fields"])})
    return get_custom_dataset(db, key)


def _to_bool(v: Any):
    if v is None or (isinstance(v, float) and v != v):
        return None, None
    if isinstance(v, bool):
        return v, None
    t = str(v).strip().lower()
    if t in TRUE_WORDS or t == "1":
        return True, None
    if t in FALSE_WORDS or t == "0":
        return False, None
    return None, "not_boolean"


def map_custom(envelopes: List[dict], d: Dict[str, Any]) -> pd.DataFrame:
    rows = []
    plain = [f for f in d["fields"] if not f.get("derive")]
    for env in envelopes:
        payload = env.get("payload") or {}
        row: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        for f in plain:
            raw = lookup(payload, f["from"])
            raw = None if raw is _MISSING else raw
            if f["type"] == "bool":
                val, err = _to_bool(raw)
            else:
                val, err = _cast(raw, f["type"])
                if f["type"] == "id" and err == "id_numeric":
                    err = None
            row[f["name"]] = val
            if err:
                errors[f["name"]] = err
        row.update(_errors=errors, _source=env.get("_source"), _run_id=env.get("_run_id"), _bronze_id=env.get("_bronze_id"),
                   _ingested_at=env.get("_ingested_at"), _is_demo=bool(env.get("_is_demo")))
        rows.append(row)
    df = pd.DataFrame(rows)
    for f in plain:
        if f["name"] not in df:
            df[f["name"]] = None
        if f["type"] == "datetime":
            df[f["name"]] = pd.to_datetime(df[f["name"]], errors="coerce")
        elif f["type"] in ("int", "float"):
            df[f["name"]] = pd.to_numeric(df[f["name"]], errors="coerce")
    for f in [x for x in d["fields"] if x.get("derive")]:
        a, b = df[f["args"][0]], df[f["args"][1]]
        secs = (b - a).dt.total_seconds()
        df[f["name"]] = (secs / (86400 if f["derive"] == "days_between" else 3600)).round(2)
    return df


def build_custom_datasets(db: Database, lake: Lakehouse, pipeline_run_id: str, actor: str = "pipeline") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for ds in list_custom_datasets(db):
        if ds["status"] != "active":
            continue
        d, key, domain = ds["definition"], ds["key"], ds["domain"]
        active = {r["key"] for r in db.fetchall("SELECT key FROM sources WHERE status = 'active'")}
        envs: List[dict] = []
        for s in d["source_keys"]:
            if s in active:
                envs.extend(lake.read_bronze(s))
        df = map_custom(envs, d) if envs else pd.DataFrame(columns=[f["name"] for f in d["fields"]] + ["_errors"])
        k, t = d["key_field"], d.get("time_field")
        rows_in = len(df)
        if len(df):
            df = df.sort_values(["_ingested_at", "_bronze_id"], kind="stable")
            reasons = pd.Series([[] for _ in range(len(df))], index=df.index)
            for i in df.index[df[k].isna()]:
                reasons.at[i].append(f"{k}: ausente")
            if t:
                for i in df.index[df[t].isna()]:
                    reasons.at[i].append(f"{t}: data ausente ou inválida")
            bad = reasons.map(bool)
            q = df[bad].copy()
            if len(q):
                q["_reasons"] = reasons[bad].map("; ".join)
                q["_record_key"] = q[k]
                q["_cast_errors"] = q.pop("_errors")
            _write_quarantine(db, lake, pipeline_run_id, f"silver_{key}", q)
            df = df[~bad].drop_duplicates(k, keep="last")
            quarantined = int(bad.sum())
        else:
            quarantined = 0
        df = df.drop(columns=["_errors"], errors="ignore").reset_index(drop=True)
        w = lake.write_table("silver", f"silver_{key}", df)
        register_dataset(db, key=f"silver_{key}", layer="silver", scope="domain", domain=domain,
                         name=f"{ds['name']} (Silver)", description=ds.get("description") or "Conjunto configurado pelo setor.",
                         grain="1 linha por registro (chave: %s)" % k, path=w["path"], fmt=w["format"], row_count=w["rows"],
                         schema=w["schema"], schema_version=f"v{ds['version']}", is_demo=bool(len(df) and df["_is_demo"].any()),
                         pipeline_run_id=pipeline_run_id, sensitivity="internal")
        gold = df.copy()
        gold["month"] = gold[t].dt.strftime("%Y-%m") if t and len(gold) else None
        for rel in d.get("relationships") or []:
            try:
                from ..catalog import get_dataset, storage_layer_for
                other = lake.read_table(storage_layer_for(get_dataset(db, rel["dataset"])), rel["dataset"])
            except (FileNotFoundError, NotFound):
                continue
            cols = [c for c in rel["bring"] if c in other.columns and c not in gold.columns]
            if cols:
                right = other[[rel["on"], *cols]].drop_duplicates(rel["on"]).rename(columns={rel["on"]: "_join_r"})
                right["_join_r"] = right["_join_r"].astype(str)
                gold["_join"] = gold[rel["field"]].map(lambda v: None if v is None or v != v else str(v))
                gold = gold.merge(right, how="left", left_on="_join", right_on="_join_r").drop(columns=["_join", "_join_r"])
                add_edge(db, f"dataset:{rel['dataset']}", f"dataset:{gold_key(key)}", f"join {rel['field']}→{rel['on']}")
        for f in d["fields"]:
            if f["role"] == "dimension" and f["name"] in gold and gold[f["name"]].dtype == object:
                gold[f["name"]] = gold[f["name"]].where(gold[f["name"]].notna(), None)
        wg = lake.write_table(f"gold/domains/{domain}", gold_key(key), gold.reset_index(drop=True))
        register_dataset(db, key=gold_key(key), layer="gold_domain", scope="domain", domain=domain,
                         name=ds["name"], description=f"Gold de domínio ({domain}) · {ds['name']} — conjunto configurado na interface",
                         grain="1 linha por registro", path=wg["path"], fmt=wg["format"], row_count=wg["rows"],
                         schema=wg["schema"], schema_version=f"v{ds['version']}",
                         is_demo=bool(len(gold) and gold["_is_demo"].any()), pipeline_run_id=pipeline_run_id)
        for s in d["source_keys"]:
            add_edge(db, f"bronze:{s}", f"dataset:silver_{key}", f"mapeamento configurável v{ds['version']}")
        add_edge(db, f"dataset:silver_{key}", f"dataset:{gold_key(key)}", "month + relacionamentos")
        record_transformation(db, dataset_key=gold_key(key), inputs=[f"silver_{key}"], transform="custom dataset build",
                              rule_version=f"v{ds['version']}", rows_in=rows_in, rows_out=wg["rows"], actor=actor,
                              pipeline_run_id=pipeline_run_id)
        out[key] = {"rows_in": rows_in, "rows": wg["rows"], "quarantined": quarantined}
    return out


# ------------------------------------------------------------------ sugestões (heurísticas, sempre revisáveis)
def _mkey(domain: str, ds_key: str, suffix: str) -> str:
    base = re.sub(r"[^A-Z0-9_]", "_", f"{domain}_{ds_key}_{suffix}".upper())
    return re.sub(r"_+", "_", base)[:60]


def metric_dimensions(ds: dict) -> List[str]:
    d = ds["definition"]
    dims = [f["name"] for f in d["fields"] if f["role"] == "dimension"]
    for rel in d.get("relationships") or []:
        dims += [b for b in rel["bring"] if b not in dims]
    return (["month"] if d.get("time_field") else []) + dims


def suggest_metrics(ds: dict) -> List[Dict[str, Any]]:
    d, key, domain = ds["definition"], ds["key"], ds["domain"]
    t = d.get("time_field")
    dims = metric_dimensions(ds)
    base = {"scope": "domain", "domain": domain, "dimensions": dims, "source_datasets": [gold_key(key)],
            "owner": f"Responsável do setor {domain}"}
    out = [{**base, "metric_key": _mkey(domain, key, "VOLUME"), "name": f"Volume de registros — {ds['name']}",
            "description": f"Quantidade de registros válidos em {ds['name']}.", "formula_text": "contagem(registros)",
            "formula_definition": {"type": "count", **({"time_field": t} if t else {})}, "unit": "registros"}]
    for f in d["fields"]:
        if f["role"] == "measure":
            dur = f.get("derive") in DERIVES
            out.append({**base, "metric_key": _mkey(domain, key, f"AVG_{f['name']}"), "name": f"Média de {f['label']}",
                        "description": f"Média aritmética de {f['label']} (valores nulos excluídos).",
                        "formula_text": f"média({f['name']})",
                        "formula_definition": {"type": "mean", "field": f["name"], **({"time_field": t} if t else {})},
                        "unit": "dias" if f.get("derive") == "days_between" else ("horas" if dur else f["label"])})
            if dur:
                out.append({**base, "metric_key": _mkey(domain, key, f"P90_{f['name']}"), "name": f"P90 de {f['label']}",
                            "description": f"Percentil 90 de {f['label']}: 90% dos registros ficam abaixo deste valor.",
                            "formula_text": f"percentil90({f['name']})",
                            "formula_definition": {"type": "percentile", "q": 90, "field": f["name"], **({"time_field": t} if t else {})},
                            "unit": "dias" if f["derive"] == "days_between" else "horas"})
        if f["type"] == "bool":
            out.append({**base, "metric_key": _mkey(domain, key, f"RATE_{f['name']}"), "name": f"% {f['label']} (sim)",
                        "description": f"Percentual de registros com {f['label']} = sim, entre os que responderam.",
                        "formula_text": f"{f['name']} = sim / {f['name']} informado × 100",
                        "formula_definition": {"type": "rate", "numerator": {"field": f["name"], "op": "is_true"},
                                               "base_filter": {"field": f["name"], "op": "not_null"},
                                               **({"time_field": t} if t else {})}, "unit": "%"})
    for m in out:
        m["metric_key"] = m["metric_key"] if len(m["metric_key"]) >= 4 else m["metric_key"] + "_001"
    return out


def default_widgets(metrics: List[dict], ds: dict) -> List[Dict[str, Any]]:
    dims = [x for x in metric_dimensions(ds) if x != "month"]
    w: List[Dict[str, Any]] = []
    for m in metrics[:4]:
        w.append({"id": new_id("W"), "title": m["name"], "metric_key": m["metric_key"], "chart": "kpi", "group_by": None})
    if "month" in metric_dimensions(ds):
        for m in metrics[:2]:
            w.append({"id": new_id("W"), "title": f"{m['name']} por mês", "metric_key": m["metric_key"], "chart": "line",
                      "group_by": "month"})
    for m in metrics[1:3]:
        if dims:
            w.append({"id": new_id("W"), "title": f"{m['name']} por {dims[0]}", "metric_key": m["metric_key"], "chart": "bar",
                      "group_by": dims[0]})
    return w


def preview_rows(lake: Lakehouse, ds: dict, limit: int = 20) -> Dict[str, Any]:
    try:
        df = lake.read_table(f"gold/domains/{ds['domain']}", gold_key(ds["key"]))
    except FileNotFoundError:
        return {"rows": [], "columns": [], "built": False}
    from goops_core.util import to_jsonable
    cols = [c for c in df.columns if not c.startswith("_")]
    return {"rows": [to_jsonable(r) for r in df[cols].head(limit).replace({np.nan: None}).to_dict(orient="records")],
            "columns": cols, "built": True, "total": int(len(df))}
