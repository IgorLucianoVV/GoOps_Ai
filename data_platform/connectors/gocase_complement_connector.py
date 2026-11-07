"""Conector do complemento SINTÉTICO da seed Gocase (ver data_platform/demo/gocase_complement.py).

Configuração: {"kind": "delivery_dates" | "transit_orders" | "transit_deliveries", "seed": 42,
               "role": "complement" (só preenche lacunas) | omitido (registros novos)}
Fontes deste conector são sempre is_demo=True e podem ser desativadas em Lakehouse › Fontes.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from goops_core.errors import ValidationError

from ..demo.gocase_complement import generate_complement
from .base import BaseConnector, FetchResult

KINDS = ("delivery_dates", "transit_orders", "transit_deliveries")


class GocaseComplementConnector(BaseConnector):
    kind = "gocase_complement"

    def __init__(self, source_key: str, config: Dict[str, Any]):
        super().__init__(source_key, config)
        self.data_kind = config.get("kind")
        if self.data_kind not in KINDS:
            raise ValidationError(f"Fonte {source_key}: 'kind' deve ser um de {', '.join(KINDS)}.")
        self.seed = int(config.get("seed", 42))

    def _data(self) -> list:
        return [dict(r) for r in generate_complement(self.seed)[self.data_kind]]

    def test_connection(self) -> Dict[str, Any]:
        return {"ok": True, "demo": True, "synthetic": True, "records_available": len(self._data())}

    def fetch(self, since: Optional[str] = None) -> FetchResult:
        data = self._data()
        return FetchResult(records=data, next_cursor=None, pages=1, schema_version="gocase-complemento-1")
