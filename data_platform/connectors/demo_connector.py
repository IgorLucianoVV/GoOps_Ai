"""Conector de DEMONSTRAÇÃO: entrega payloads sintéticos do gerador como se fossem de uma API.

Suporta paginação simulada e injeção de falha (config {"simulate_failure": true}) para testes.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from goops_core.errors import ExternalSourceError

from ..demo.generator import generate
from .base import BaseConnector, FetchResult, RetryableError

_CACHE: Dict[tuple, Dict[str, list]] = {}


class DemoConnector(BaseConnector):
    kind = "demo"

    def __init__(self, source_key: str, config: Dict[str, Any]):
        super().__init__(source_key, config)
        self.entity = config.get("entity", source_key.replace("demo_", ""))
        self.scenario = config.get("scenario", "full")
        self.seed = int(config.get("seed", 42))
        self.page_size = int(config.get("page_size", 500))

    def _data(self) -> list:
        key = (self.scenario, self.seed)
        if key not in _CACHE:
            _CACHE[key] = generate(self.scenario, self.seed)
        return [dict(r) for r in _CACHE[key][self.entity]]

    def test_connection(self) -> Dict[str, Any]:
        if self.config.get("simulate_failure"):
            raise ExternalSourceError(f"Fonte demo {self.source_key}: falha simulada.")
        return {"ok": True, "demo": True, "records_available": len(self._data())}

    def fetch(self, since: Optional[str] = None) -> FetchResult:
        attempts = {"n": 0}
        fail_mode = self.config.get("simulate_failure")

        def first_page() -> list:
            attempts["n"] += 1
            if fail_mode == "transient" and attempts["n"] == 1:
                raise RetryableError("timeout simulado")
            if fail_mode and fail_mode != "transient":
                raise RetryableError("HTTP 503 simulado")
            return self._data()

        data = self.with_retries(first_page)
        cursor_field = "updated_at" if self.entity in ("orders", "deliveries") else None
        if since and cursor_field:
            data = [r for r in data if (r.get(cursor_field) or "") > since]
        pages = max(1, -(-len(data) // self.page_size))
        next_cursor = since
        if cursor_field:
            vals = [r[cursor_field] for r in data if r.get(cursor_field)]
            next_cursor = max(vals) if vals else since
        return FetchResult(records=data, next_cursor=next_cursor, pages=pages, schema_version="demo-1.0")
