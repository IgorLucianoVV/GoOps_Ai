"""L2 Silver: normalização, tipagem, deduplicação controlada, integração e qualidade.

Fluxo por entidade:
  Bronze (todas as execuções) -> mapeamento versionado -> deduplicação (versão mais recente por chave
  natural; duplicatas exatas e conflitos registrados) -> regras de linha (erros => quarentena) ->
  relacionamentos entre entidades (órfãos sinalizados, nunca descartados) -> Silver.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from goops_core.db import Database
from goops_core.util import jdump, new_id, now_iso

from ..provenance import any_demo, row_fields
from ..catalog import record_transformation, register_dataset
from ..lineage.registry import add_edge
from ..quality.engine import meta_result, run_row_rules
from ..storage import Lakehouse
from .mappings import MAPPINGS, mapping_for, product_line_from_name

_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z")
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MONTHS.update({"fev": 2, "abr": 4, "mai": 5, "ago": 8, "set": 9, "out": 10, "dez": 12})
_TEXT_DATE = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3})[a-z]*,?\s+(\d{4}),?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?$")
_ISO_Z = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")

UF_BY_NAME = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA", "ceara": "CE", "distrito federal": "DF",
    "espirito santo": "ES", "goias": "GO", "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS",
    "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR", "pernambuco": "PE", "piaui": "PI",
    "rio de janeiro": "RJ", "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR",
    "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE", "tocantins": "TO",
}


def _to_uf(text: str):
    t = text.strip()
    if len(t) == 2 and t.isalpha():
        return t.upper()
    import unicodedata
    norm = "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))
    return UF_BY_NAME.get(" ".join(norm.split()))
META_COLS = ["_source", "_run_id", "_bronze_id", "_ingested_at", "_payload_hash", "_is_demo", "_synthetic_fields"]
# Chaves de relacionamento nunca são preenchidas por complemento
_NEVER_COMPLEMENT = {"order_id", "reference", "delivery_id", "evaluation_id", "order_item_id"}


def _parse_dt(value: Any) -> Tuple[Optional[datetime], bool]:
    """Retorna (data, erro). Valor ausente não é erro."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or value == "":
        return None, False
    if isinstance(value, datetime):
        return value, False
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            return dt.replace(tzinfo=None), False
        except ValueError:
            continue
    m = _ISO_Z.match(text)  # ISO com milissegundos e fuso (ex.: 2025-04-04T01:03:20.307Z) -> UTC sem fuso
    if m:
        try:
            frac = (m.group(3) or "")[1:7].ljust(6, "0") if m.group(3) else "000000"
            tz = m.group(4) or "Z"
            tz = "+00:00" if tz == "Z" else (tz if ":" in tz else tz[:3] + ":" + tz[3:])
            dt = datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}.{frac}{tz}")
            return dt.astimezone(timezone.utc).replace(tzinfo=None), False
        except ValueError:
            return None, True
    m = _TEXT_DATE.match(text)  # ex.: "9 May, 2025, 14:01"
    if m and m.group(2).lower() in _MONTHS:
        try:
            return datetime(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)), int(m.group(4)),
                            int(m.group(5)), int(m.group(6) or 0)), False
        except ValueError:
            return None, True
    return None, True


def _cast(value: Any, kind: str) -> Tuple[Any, Optional[str]]:
    """Converte um valor. Retorna (valor, código_de_erro|None)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, None
    if kind == "id":
        if isinstance(value, bool):
            return None, "invalid_id"
        if isinstance(value, (int, float)):
            return str(int(value)), "id_numeric"  # zeros à esquerda podem ter sido perdidos NA ORIGEM
        text = str(value).strip()
        return (text or None), None
    if kind == "id_int":  # identificadores que a fonte entrega como inteiros (sem zeros à esquerda a preservar)
        if isinstance(value, bool):
            return None, "invalid_id"
        if isinstance(value, (int, float)):
            return (str(int(value)) if float(value).is_integer() else None), (None if float(value).is_integer() else "invalid_id")
        text = str(value).strip()
        return (text or None), None
    if kind == "uf":
        text = str(value).strip()
        if not text:
            return None, None
        uf = _to_uf(text)
        return (uf, None) if uf else (text.upper(), "invalid_uf")
    if kind in ("string", "upper"):
        text = str(value).strip()
        if not text:
            return None, None
        return (text.upper() if kind == "upper" else text), None
    if kind == "int":
        try:
            f = float(value)
            if not f.is_integer():
                return None, "not_integer"
            return int(f), None
        except (TypeError, ValueError):
            return None, "not_numeric"
    if kind == "float":
        try:
            return float(value), None
        except (TypeError, ValueError):
            return None, "not_numeric"
    if kind == "datetime":
        dt, err = _parse_dt(value)
        return dt, ("invalid_date" if err else None)
    raise ValueError(f"tipo de mapeamento desconhecido: {kind}")


_MISSING = object()


def lookup(payload: Any, path: str) -> Any:
    """Busca um campo no payload: chave exata primeiro; depois caminho aninhado com ponto (ex.: "order.code",
    "items.0.sku"). Retorna _MISSING se não existir."""
    if isinstance(payload, dict) and path in payload:
        return payload[path]
    cur = payload
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return _MISSING
    return cur


def map_records(envelopes: List[dict], entity: str, profile: str = "default",
                mapping: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    mapping = mapping or mapping_for(entity, profile)
    rows = []
    for env in envelopes:
        payload = env.get("payload") or {}
        row: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        for field, spec in mapping["fields"].items():
            if "compose" in spec:
                parts = [lookup(payload, src) for src in spec["compose"]]
                parts = [None if p is _MISSING else p for p in parts]
                raw = None if any(p in (None, "") for p in parts) else ":".join(
                    str(int(p)) if isinstance(p, float) and p.is_integer() else str(p).strip() for p in parts)
            elif spec.get("derive") == "product_line_from_name":
                v = lookup(payload, spec["source"])
                raw = product_line_from_name(None if v is _MISSING else v)
            else:
                raw = None
                for src in spec.get("from", []):
                    v = lookup(payload, src)
                    if v is not _MISSING:
                        raw = v
                        break
            value, err = _cast(raw, spec["type"])
            row[field] = value
            if err:
                errors[field] = err
        row["_cast_errors"] = errors
        row["_source"] = env["_source"]
        row["_run_id"] = env["_run_id"]
        row["_bronze_id"] = env["_bronze_id"]
        row["_ingested_at"] = env["_ingested_at"]
        row["_payload_hash"] = env["_payload_hash"]
        row["_is_demo"] = bool(env.get("_is_demo"))
        rows.append(row)
    cols = list(mapping["fields"]) + ["_cast_errors"] + META_COLS
    df = pd.DataFrame(rows, columns=cols)
    for field, spec in mapping["fields"].items():
        if spec["type"] == "datetime":
            df[field] = pd.to_datetime(df[field], errors="coerce")
        elif spec["type"] == "int":
            df[field] = pd.to_numeric(df[field], errors="coerce").astype("Int64")
        elif spec["type"] == "float":
            df[field] = pd.to_numeric(df[field], errors="coerce").astype(float)
    return df


def aggregate_items(items: pd.DataFrame) -> pd.DataFrame:
    """Itens -> 1 linha por pedido. Produto/linha principal = item de maior valor (brindes de valor zero não
    dominam); valor do pedido = soma dos itens; data do pedido = menor data entre os itens."""
    if items.empty:
        return items.drop(columns=["order_item_id"], errors="ignore")
    it = items.sort_values(["order_id", "order_total", "_ingested_at"], ascending=[True, False, True], kind="stable")
    primary = it.drop_duplicates("order_id", keep="first").set_index("order_id")
    agg = items.groupby("order_id").agg(order_date=("order_date", "min"), order_total=("order_total", "sum"),
                                        n_items=("order_item_id", "count"),
                                        product_lines=("product_line", lambda s: "|".join(sorted(set(s.dropna())))),
                                        _dq_flags=("_dq_flags", lambda s: "|".join(sorted({f for v in s.dropna() for f in str(v).split("|")})) or None))
    out = primary.drop(columns=["order_date", "order_total", "_dq_flags"]).join(agg).reset_index()
    out["order_item_id"] = None
    return out


def deduplicate(df: pd.DataFrame, natural_key: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Mantém a versão mais recente por chave natural. Registros sem chave seguem para as regras (quarentena)."""
    df = df.sort_values(["_ingested_at", "_bronze_id"], kind="stable")
    keyed = df[df[natural_key].notna()]
    no_key = df[df[natural_key].isna()]
    last = keyed.groupby(natural_key)["_ingested_at"].transform("max")
    latest = keyed[keyed["_ingested_at"] == last]
    superseded = len(keyed) - len(latest)
    dup_mask = latest.duplicated([natural_key, "_payload_hash"], keep="first")
    exact_dups = latest[dup_mask]
    unique = latest[~dup_mask]
    conflict_mask = unique.duplicated(natural_key, keep=False)
    conflict_keys = unique.loc[conflict_mask, natural_key].unique().tolist()
    final = unique.drop_duplicates(natural_key, keep="last")
    stats = {
        "input_rows": int(len(df)), "superseded_versions": int(superseded),
        "exact_duplicates": int(len(exact_dups)), "exact_duplicate_keys": exact_dups[natural_key].astype(str).tolist(),
        "version_conflicts": int(len(conflict_keys)), "conflict_keys": [str(k) for k in conflict_keys],
        "missing_key": int(len(no_key)),
    }
    return pd.concat([final, no_key]), stats


def _write_quarantine(db: Database, lake: Lakehouse, run_id: str, dataset: str, q: pd.DataFrame) -> None:
    if q.empty:
        return
    cols = [c for c in q.columns if c not in ("_cast_errors",)]
    lake.write_table("quarantine", dataset, q[cols])
    with db.connect() as c:
        for _, r in q.iterrows():
            payload = {k: r[k] for k in cols if not k.startswith("_") or k in ("_bronze_id", "_run_id", "_source")}
            key = r.get("_record_key")
            c.execute("INSERT INTO quarantine (id, pipeline_run_id, dataset, record_key, reasons, payload, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (new_id("QRN"), run_id, dataset, None if key is None or pd.isna(key) else str(key),
                       r["_reasons"], jdump({**payload, "cast_errors": r.get("_cast_errors")}), now_iso()))


def _merge_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Consolida resultados da mesma regra vindos de várias fontes."""
    merged: Dict[tuple, Dict[str, Any]] = {}
    for r in results:
        k = (r["rule_key"], r["dataset"])
        if k not in merged:
            merged[k] = dict(r, sample=list(r["sample"]))
        else:
            m = merged[k]
            m["checked"] += r["checked"]
            m["failed"] += r["failed"]
            m["sample"] = (m["sample"] + list(r["sample"]))[:5]
    for m in merged.values():
        sev = m["severity"]
        m["status"] = "passed" if m["failed"] == 0 else ("failed" if sev == "error" else ("info" if sev == "info" else "warning"))
    return list(merged.values())


EXTRA_ORDER_COLS = ["n_items", "product_lines"]


def _apply_complement(base: pd.DataFrame, parts: List[pd.DataFrame], key: str, fields: List[str]):
    """Preenche SOMENTE campos nulos de registros existentes com valores de fontes complementares (sintéticas),
    registrando por linha quais campos vieram do complemento (`_synthetic_fields`). Nunca cria registros."""
    if "_synthetic_fields" not in base.columns:
        base["_synthetic_fields"] = None
    if not parts or base.empty:
        return base, {}
    comp = pd.concat(parts, ignore_index=True).sort_values(["_ingested_at", "_bronze_id"], kind="stable")
    comp = comp.drop_duplicates(key, keep="last").set_index(key)
    base = base.copy()
    tags = pd.Series([[] for _ in range(len(base))], index=base.index)
    filled: Dict[str, int] = {}
    for f in fields:
        if f in _NEVER_COMPLEMENT or f == key or f not in comp.columns:
            continue
        values = base[key].map(comp[f])
        mask = base[f].isna() & values.notna()
        if not mask.any():
            continue
        if pd.api.types.is_datetime64_any_dtype(comp[f]):
            base[f] = pd.to_datetime(base[f])
        base.loc[mask, f] = values[mask]
        for i in base.index[mask]:
            tags.at[i].append(f)
        filled[f] = int(mask.sum())
    prev = base["_synthetic_fields"].fillna("")
    joined = tags.map(lambda t: "|".join(t))
    base["_synthetic_fields"] = (prev + "|" + joined).str.strip("|").replace("", None)
    return base, filled


def build_silver(db: Database, lake: Lakehouse, pipeline_run_id: str, actor: str = "pipeline") -> Dict[str, Any]:
    from goops_core.util import jload
    sources = db.fetchall("SELECT key, entity, is_demo, config FROM sources WHERE status = 'active'")
    frames: Dict[str, pd.DataFrame] = {}
    items_frames: List[pd.DataFrame] = []
    summary: Dict[str, Any] = {"datasets": {}, "dq_results": []}
    is_demo_any = any(s["is_demo"] for s in sources)
    versions: Dict[str, List[str]] = {}

    for entity, canonical in MAPPINGS.items():
        ds = canonical["dataset"]
        prefix = {"orders": "orders", "nps": "nps", "deliveries": "deliveries"}[entity]
        valid_parts, q_parts, results_all = [], [], []
        stats_total = {"input_rows": 0, "superseded_versions": 0, "exact_duplicates": 0, "version_conflicts": 0,
                       "missing_key": 0}
        bronze_rows = 0
        src_keys: List[str] = []
        complement_parts: List[pd.DataFrame] = []
        for src in [x for x in sources if x["entity"] == entity]:
            src_cfg = jload(src["config"], {}) or {}
            profile = src_cfg.get("mapping_profile", "default")
            from .profiles import resolve_mapping
            m = resolve_mapping(db, entity, profile)
            versions.setdefault(ds, []).append(f"{profile}:{m['version']}")
            src_keys.append(src["key"])
            envelopes = lake.read_bronze(src["key"])
            bronze_rows += len(envelopes)
            mapped = map_records(envelopes, entity, profile, mapping=m)
            nk = m["natural_key"]
            deduped, stats = deduplicate(mapped, nk)
            for k in stats_total:
                stats_total[k] += stats[k]
            valid, quarantined, results = run_row_rules(deduped, ds, nk)
            quarantined["_record_key"] = quarantined[nk] if len(quarantined) else None
            results.append(meta_result(f"{prefix}_exact_duplicates", ds, "warning", stats["input_rows"],
                                       stats["exact_duplicates"], stats["exact_duplicate_keys"]))
            results.append(meta_result(f"{prefix}_version_conflicts", ds, "warning", stats["input_rows"],
                                       stats["version_conflicts"], stats["conflict_keys"]))
            numeric_ids = mapped["_cast_errors"].map(lambda e: any(v == "id_numeric" for v in (e or {}).values()))
            results.append(meta_result("ids_numeric_type", ds, "warning", len(mapped), int(numeric_ids.sum()),
                                       mapped.loc[numeric_ids, nk].astype(str).tolist()))
            results_all.extend(results)
            if m.get("grain") == "item":
                items_frames.append(valid.drop(columns=["_cast_errors"]))
                valid = aggregate_items(valid)
            elif entity == "orders":
                valid = valid.assign(n_items=1, product_lines=valid["product_line"])
            if src_cfg.get("role") == "complement":       # só preenche lacunas de registros existentes
                complement_parts.append(valid)
            else:
                valid_parts.append(valid)
            q_parts.append(quarantined)
        cols = list(canonical["fields"]) + ["_cast_errors"] + META_COLS + ["_dq_flags"] + (EXTRA_ORDER_COLS if entity == "orders" else [])
        valid_all = pd.concat(valid_parts, ignore_index=True) if valid_parts else pd.DataFrame(columns=cols)
        for c in cols:
            if c not in valid_all.columns:
                valid_all[c] = None
        # Mesma chave canônica vinda de fontes diferentes: mantém a versão mais recente
        cnk = canonical["natural_key"]
        valid_all = valid_all.sort_values(["_ingested_at", "_bronze_id"], kind="stable").drop_duplicates(cnk, keep="last")
        valid_all, filled = _apply_complement(valid_all, complement_parts, cnk, list(canonical["fields"]))
        q_all = pd.concat(q_parts, ignore_index=True) if any(len(q) for q in q_parts) else pd.DataFrame()
        _write_quarantine(db, lake, pipeline_run_id, ds, q_all)
        frames[entity] = valid_all
        summary["datasets"][ds] = {"bronze_rows": bronze_rows, "dedup": stats_total, "valid": int(len(valid_all)),
                                   "complemented_fields": filled,
                                   "quarantined": int(len(q_all)), "sources": src_keys,
                                   "mapping_versions": versions.get(ds, [])}
        summary["dq_results"].extend(_merge_results(results_all))

    # ---------- Relacionamentos (grão preservado, órfãos sinalizados) ----------
    orders, nps, deliv = frames["orders"], frames["nps"], frames["deliveries"]
    order_ids = set(orders["order_id"].dropna())
    nps["is_orphan"] = ~nps["order_id"].isin(order_ids)
    deliv["is_orphan"] = ~deliv["order_id"].isin(order_ids)
    n_eval = nps.groupby("order_id").size()
    n_del = deliv.groupby("order_id").size()
    orders["n_evaluations"] = orders["order_id"].map(n_eval).fillna(0).astype(int)
    orders["n_deliveries"] = orders["order_id"].map(n_del).fillna(0).astype(int)
    # Cliente do pedido: quando a base de pedidos não traz, deriva da avaliação NPS do mesmo pedido (dado real)
    cid = nps.dropna(subset=["customer_id"]).drop_duplicates("order_id").set_index("order_id")["customer_id"]
    if len(cid):
        orders["customer_id"] = orders["customer_id"].astype(object).where(orders["customer_id"].notna(),
                                                                            orders["order_id"].map(cid))
    summary["dq_results"].append(meta_result("nps_orphan_evaluation", "silver_nps_evaluations", "warning", len(nps),
                                             int(nps["is_orphan"].sum()), nps.loc[nps["is_orphan"], "evaluation_id"].tolist()))
    summary["dq_results"].append(meta_result("deliveries_orphan", "silver_deliveries", "warning", len(deliv),
                                             int(deliv["is_orphan"].sum()), deliv.loc[deliv["is_orphan"], "delivery_id"].tolist()))
    summary["dq_results"].append(meta_result("orders_without_evaluation", "silver_orders", "info", len(orders),
                                             int((orders["n_evaluations"] == 0).sum()), []))

    # ---------- Persistência ----------
    descriptions = {
        "silver_orders": ("Pedidos (Silver)", "Pedidos normalizados, tipados e deduplicados (itens agregados por pedido "
                          "quando a fonte é por item).", "1 linha por pedido"),
        "silver_nps_evaluations": ("Avaliações NPS (Silver)", "Avaliações normalizadas; notas inválidas em quarentena.",
                                   "1 linha por avaliação"),
        "silver_deliveries": ("Entregas (Silver)", "Entregas normalizadas; relação 1:N com pedidos.", "1 linha por entrega"),
    }
    outputs = [("orders", orders), ("nps", nps), ("deliveries", deliv)]
    for entity, df in outputs:
        mapping = MAPPINGS[entity]
        ds = mapping["dataset"]
        out = df.drop(columns=["_cast_errors"], errors="ignore").reset_index(drop=True)
        written = lake.write_table("silver", ds, out)
        name, desc, grain = descriptions[ds]
        register_dataset(db, key=ds, layer="silver", scope="corporate", name=name, description=desc, grain=grain,
                         path=written["path"], fmt=written["format"], row_count=written["rows"],
                         schema=written["schema"], schema_version=mapping["version"], is_demo=any_demo(df),
                         pipeline_run_id=pipeline_run_id, sensitivity="pii" if entity != "deliveries" else "internal",
                         synthetic_fields=sorted(row_fields(df)))
        src_keys = summary["datasets"][ds]["sources"]
        record_transformation(db, dataset_key=ds, inputs=[f"bronze_{k}" for k in src_keys],
                              transform=f"map({entity}) + dedup + dq_rules + relationships",
                              rule_version=", ".join(summary["datasets"][ds]["mapping_versions"]) or mapping["version"],
                              rows_in=summary["datasets"][ds]["bronze_rows"], rows_out=written["rows"], actor=actor,
                              pipeline_run_id=pipeline_run_id)
        for k in src_keys:
            add_edge(db, f"bronze:{k}", f"dataset:{ds}", f"silver mapping ({', '.join(summary['datasets'][ds]['mapping_versions'])})")
    if items_frames:
        items = pd.concat(items_frames, ignore_index=True)
        w = lake.write_table("silver", "silver_order_items", items.reset_index(drop=True))
        register_dataset(db, key="silver_order_items", layer="silver", scope="corporate", name="Itens de pedido (Silver)",
                         description="Itens de pedido normalizados (fontes com grão de item).", grain="1 linha por item",
                         path=w["path"], fmt=w["format"], row_count=w["rows"], schema=w["schema"],
                         schema_version="1.0", is_demo=any_demo(items), pipeline_run_id=pipeline_run_id, sensitivity="internal")
        record_transformation(db, dataset_key="silver_order_items", inputs=[f"bronze_{k}" for k in summary["datasets"]["silver_orders"]["sources"]],
                              transform="map(orders, grain=item) + dedup + dq_rules", rule_version="1.0",
                              rows_in=summary["datasets"]["silver_orders"]["bronze_rows"], rows_out=w["rows"], actor=actor,
                              pipeline_run_id=pipeline_run_id)
        add_edge(db, "dataset:silver_order_items", "dataset:silver_orders", "aggregate items -> orders")
        summary["datasets"]["silver_order_items"] = {"valid": int(len(items)), "quarantined": 0}

    with db.connect() as c:
        for r in summary["dq_results"]:
            c.execute("INSERT INTO dq_results (id, pipeline_run_id, rule_key, dataset, severity, rule_version, checked, "
                      "failed, status, sample, executed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (new_id("DQR"), pipeline_run_id, r["rule_key"], r["dataset"], r["severity"], r["rule_version"],
                       int(r["checked"]), int(r["failed"]), r["status"], jdump(r["sample"]), now_iso()))
    return summary
