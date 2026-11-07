"""Conector de contatos de atendimento SINTÉTICOS (Desafio 1). Ver data_platform/support/generator.py.

Configuração: {"recipe": "support", "seed": 7, "scale": 1.0}. Lê os pedidos da Gold corporativa, por isso é
sincronizado na etapa `support` do pipeline (depois da Gold), não na ingestão geral. Fonte sempre is_demo=True.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from goops_core.errors import ValidationError

from ..support.generator import SCHEMA_VERSION, generate_contacts
from .base import BaseConnector, FetchResult


class SupportDemoConnector(BaseConnector):
    """Contatos sintéticos coerentes com os pedidos da Gold. Carga histórica uma única vez (cursor)."""
    kind = "support_demo"

    def __init__(self, source_key: str, config: Dict[str, Any]):
        super().__init__(source_key, config)
        self.seed = int(config.get("seed", 7))
        self.scale = float(config.get("scale", 1.0))
        if not 0.1 <= self.scale <= 5:
            raise ValidationError("'scale' deve estar entre 0,1 e 5.")

    def _orders(self) -> pd.DataFrame:
        from ..storage import get_lakehouse
        try:
            return get_lakehouse().read_table("gold/corporate", "gold_orders")
        except FileNotFoundError:
            return pd.DataFrame()

    def test_connection(self) -> Dict[str, Any]:
        o = self._orders()
        return {"ok": True, "demo": True, "synthetic": True, "orders_available": int(len(o))}

    def fetch(self, since: Optional[str] = None) -> FetchResult:
        if since == "history-loaded":
            return FetchResult(records=[], next_cursor=since, pages=0, schema_version=SCHEMA_VERSION)
        o = self._orders()
        if o.empty:
            return FetchResult(records=[], next_cursor=None, pages=0, schema_version=SCHEMA_VERSION)
        return FetchResult(records=generate_contacts(o, self.seed, self.scale), next_cursor="history-loaded", pages=1,
                           schema_version=SCHEMA_VERSION)
