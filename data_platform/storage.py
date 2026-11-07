"""Armazenamento do Lakehouse.

* Bronze: JSON Lines append-only, um arquivo por execução de ingestão (nunca sobrescrito).
* Silver/Gold/Quarantine: Parquet (pyarrow) quando disponível; fallback CSV + sidecar de schema
  que preserva tipos (ex.: identificadores como string, mantendo zeros à esquerda).

Interface pensada para ser substituída por Apache Iceberg / Delta Lake no futuro (ver DECISIONS.md).
"""
from __future__ import annotations

import hashlib
import json
import re
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from goops_core.util import now_iso, to_jsonable

log = logging.getLogger("goops.storage")

LAYERS = ("silver", "gold/corporate", "gold/domains/cx", "gold/domains/logistics", "gold/domains/products",
          "quarantine")


def _pyarrow_available() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _kind(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "bool"
    if pd.api.types.is_integer_dtype(series):
        return "int"
    if pd.api.types.is_float_dtype(series):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    return "string"


class Lakehouse:
    def __init__(self, base_path: Path, storage_format: str = "auto"):
        self.base = Path(base_path)
        self.base.mkdir(parents=True, exist_ok=True)
        if storage_format == "auto":
            storage_format = "parquet" if _pyarrow_available() else "csv"
        if storage_format == "parquet" and not _pyarrow_available():
            log.warning("pyarrow indisponível; usando CSV com schema sidecar.")
            storage_format = "csv"
        self.format = storage_format

    # ---------------- Bronze ----------------
    def bronze_dir(self, source_key: str) -> Path:
        return self.base / "bronze" / source_key

    def write_bronze(self, source_key: str, run_id: str, records: Iterable[dict], schema_version: str,
                     is_demo: bool) -> Dict[str, object]:
        ingested_at = now_iso()
        day = ingested_at[:10]
        path = self.bronze_dir(source_key) / f"ingest_date={day}" / f"run_id={run_id}" / "part-00000.jsonl"
        if path.exists():
            raise FileExistsError(f"Arquivo Bronze já existe e não pode ser sobrescrito: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with path.open("w", encoding="utf-8") as fh:
            for i, payload in enumerate(records):
                envelope = {
                    "_bronze_id": f"{run_id}:{i:07d}",
                    "_source": source_key,
                    "_ingested_at": ingested_at,
                    "_run_id": run_id,
                    "_schema_version": schema_version,
                    "_payload_hash": payload_hash(payload),
                    "_is_demo": bool(is_demo),
                    "payload": payload,
                }
                fh.write(json.dumps(envelope, ensure_ascii=False, default=str) + "\n")
                count += 1
        return {"path": str(path.relative_to(self.base)), "count": count, "ingested_at": ingested_at}

    def read_bronze(self, source_key: str) -> List[dict]:
        root = self.bronze_dir(source_key)
        if not root.exists():
            return []
        out: List[dict] = []
        for path in sorted(root.rglob("*.jsonl")):
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        out.append(json.loads(line))
        out.sort(key=lambda r: (r["_ingested_at"], r["_bronze_id"]))
        return out

    def bronze_stats(self, source_key: str) -> dict:
        root = self.bronze_dir(source_key)
        files = sorted(root.rglob("*.jsonl")) if root.exists() else []
        return {"files": len(files), "bytes": sum(f.stat().st_size for f in files)}

    # ---------------- Tabelas ----------------
    def _table_path(self, layer: str, key: str) -> Path:
        # Domínios criados na interface ganham gold/domains/<chave> (chave validada: minúsculas, números e _)
        dyn = layer.startswith("gold/domains/") and re.fullmatch(r"[a-z][a-z0-9_]{1,30}", layer.rsplit("/", 1)[-1])
        if layer not in LAYERS and not dyn:
            raise ValueError(f"Camada inválida: {layer}")
        if not re.fullmatch(r"[A-Za-z0-9_]{1,80}", key):
            raise ValueError(f"Nome de tabela inválido: {key}")
        ext = "parquet" if self.format == "parquet" else "csv"
        return self.base / layer / f"{key}.{ext}"

    def write_table(self, layer: str, key: str, df: pd.DataFrame) -> Dict[str, object]:
        path = self._table_path(layer, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        schema = {c: _kind(df[c]) for c in df.columns}
        tmp = path.with_suffix(path.suffix + ".tmp")
        if self.format == "parquet":
            df.to_parquet(tmp, index=False)
        else:
            out = df.copy()
            for c, k in schema.items():
                if k == "datetime":
                    out[c] = out[c].dt.strftime("%Y-%m-%dT%H:%M:%S").where(out[c].notna(), None)
            out.to_csv(tmp, index=False)
        tmp.replace(path)  # escrita atômica
        path.with_suffix(".schema.json").write_text(json.dumps(schema), encoding="utf-8")
        return {"path": str(path.relative_to(self.base)), "rows": int(len(df)), "schema": schema, "format": self.format}

    def table_exists(self, layer: str, key: str) -> bool:
        return self._table_path(layer, key).exists()

    def read_table(self, layer: str, key: str) -> pd.DataFrame:
        path = self._table_path(layer, key)
        if not path.exists():
            raise FileNotFoundError(f"Dataset {layer}/{key} ainda não foi construído.")
        if self.format == "parquet":
            return pd.read_parquet(path)
        schema = json.loads(path.with_suffix(".schema.json").read_text(encoding="utf-8"))
        dtypes = {c: "string" for c, k in schema.items() if k == "string"}
        df = pd.read_csv(path, dtype=dtypes, keep_default_na=False, na_values=[""])
        for c, k in schema.items():
            if c not in df.columns:
                continue
            if k == "datetime":
                df[c] = pd.to_datetime(df[c], errors="coerce")
            elif k == "bool":
                df[c] = df[c].map({"True": True, "False": False, True: True, False: False}).astype("boolean")
            elif k == "int":
                df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
            elif k == "float":
                df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
        for c in df.columns:
            if schema.get(c) == "string":
                df[c] = df[c].astype(object).where(df[c].notna(), None)
        return df

    def preview(self, layer: str, key: str, limit: int = 50) -> List[dict]:
        df = self.read_table(layer, key).head(max(1, min(limit, 500)))
        return [to_jsonable(r) for r in df.to_dict(orient="records")]

    def reset(self) -> None:
        import shutil
        if self.base.exists():
            shutil.rmtree(self.base)
        self.base.mkdir(parents=True, exist_ok=True)


_lake: Optional[Lakehouse] = None


def get_lakehouse() -> Lakehouse:
    global _lake
    if _lake is None:
        from goops_core.config import get_settings
        s = get_settings()
        _lake = Lakehouse(s.lakehouse_path, s.storage_format)
    return _lake


def set_lakehouse(lake: Optional[Lakehouse]) -> None:
    global _lake
    _lake = lake
