"""Conector de arquivos (XLSX/CSV) para cargas de planilhas.

Segurança: o caminho é SEMPRE relativo ao diretório de importação permitido (DATA_IMPORT_DIR,
padrão <projeto>/data). Tentativas de sair dele (../, caminhos absolutos) são rejeitadas.
Minimização de dados: `exclude_fields` remove colunas antes da gravação na Bronze.

Configuração:
  {"path": "seed/gocase/nps.xlsx", "format": "xlsx", "sheet": null,
   "exclude_fields": ["Name", "Ipaddress"], "mapping_profile": "gocase_xlsx", "schema_version": "gocase-xlsx-1"}
"""
from __future__ import annotations

import math
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional

from goops_core.config import ROOT_DIR
from goops_core.errors import ExternalSourceError, ValidationError

from .base import BaseConnector, FetchResult


def import_dir() -> Path:
    return Path(os.environ.get("DATA_IMPORT_DIR", str(ROOT_DIR / "data"))).resolve()


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
    if hasattr(v, "item"):  # numpy scalar
        v = v.item()
        return None if isinstance(v, float) and math.isnan(v) else v
    if type(v).__name__ == "Timestamp":
        return v.to_pydatetime().isoformat(sep=" ")
    return v


class FileConnector(BaseConnector):
    kind = "file"

    def __init__(self, source_key: str, config: Dict[str, Any]):
        super().__init__(source_key, config)
        rel = str(config.get("path") or "")
        if not rel:
            raise ValidationError(f"Fonte {source_key}: informe 'path' relativo ao diretório de importação.")
        base = import_dir()
        target = (base / rel).resolve()
        if base != target and base not in target.parents:
            raise ValidationError("Caminho fora do diretório de importação permitido.")
        self.path = target
        self.format = (config.get("format") or self.path.suffix.lstrip(".")).lower()
        if self.format not in ("xlsx", "csv"):
            raise ValidationError("Formato suportado: xlsx ou csv.")
        self.exclude = set(config.get("exclude_fields") or [])

    def _read(self):
        import pandas as pd
        if not self.path.exists():
            raise ExternalSourceError(f"Arquivo não encontrado para a fonte {self.source_key}: {self.path.name}")
        try:
            if self.format == "xlsx":
                df = pd.read_excel(self.path, sheet_name=self.config.get("sheet") or 0, dtype=object)
            else:
                df = pd.read_csv(self.path, dtype=str, sep=self.config.get("separator", ","),
                                 encoding=self.config.get("encoding", "utf-8"))
        except ExternalSourceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ExternalSourceError(f"Falha ao ler {self.path.name}: {type(exc).__name__}") from exc
        return df

    def test_connection(self) -> Dict[str, Any]:
        df = self._read()
        return {"ok": True, "file": self.path.name, "rows": int(len(df)),
                "columns": [c for c in df.columns if c not in self.exclude], "excluded": sorted(self.exclude)}

    def fetch(self, since: Optional[str] = None) -> FetchResult:
        df = self._read()
        cols = [c for c in df.columns if c not in self.exclude]
        records = [{c: _jsonable(v) for c, v in zip(cols, row)} for row in df[cols].itertuples(index=False, name=None)]
        return FetchResult(records=records, next_cursor=None, pages=1,
                           schema_version=str(self.config.get("schema_version", f"file-{self.format}")))
