"""Camada de conectores: padroniza autenticação, paginação, erros, rate limit, retentativas
e execução incremental. Cada fonte é independente.

IMPORTANTE: os contratos das APIs reais (Pedidos, NPS, Entregas) ainda não foram confirmados.
O HttpJsonConnector é totalmente configurável (endpoint, paginação, campos) e NÃO assume
nenhum contrato específico. Credenciais são lidas de variáveis de ambiente indicadas na
configuração (ex.: {"auth": {"type": "bearer", "token_env": "ORDERS_API_TOKEN"}}).
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from goops_core.errors import ExternalSourceError

log = logging.getLogger("goops.connectors")


@dataclass
class FetchResult:
    records: List[dict]
    next_cursor: Optional[str] = None
    pages: int = 0
    failures: List[dict] = field(default_factory=list)
    schema_version: str = "unknown"


class RetryableError(Exception):
    """Erro transitório (timeout, 429, 5xx)."""


class RateLimiter:
    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second if per_second and per_second > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        if self.interval <= 0:
            return
        delta = time.monotonic() - self._last
        if delta < self.interval:
            time.sleep(self.interval - delta)
        self._last = time.monotonic()


class BaseConnector(ABC):
    kind = "base"

    def __init__(self, source_key: str, config: Dict[str, Any]):
        self.source_key = source_key
        self.config = config or {}
        self.max_retries = int(self.config.get("max_retries", 3))
        self.backoff_seconds = float(self.config.get("backoff_seconds", 0.5))
        self.rate_limiter = RateLimiter(float(self.config.get("rate_limit_per_sec", 0)))

    def with_retries(self, fn: Callable[[], Any]) -> Any:
        attempt = 0
        while True:
            try:
                self.rate_limiter.wait()
                return fn()
            except RetryableError as exc:
                attempt += 1
                if attempt > self.max_retries:
                    raise ExternalSourceError(f"Fonte {self.source_key}: falha após {self.max_retries} retentativas.",
                                              {"last_error": str(exc)[:200]}) from exc
                sleep = self.backoff_seconds * (2 ** (attempt - 1))
                log.warning("retry %s/%s on %s in %.2fs", attempt, self.max_retries, self.source_key, sleep)
                time.sleep(sleep)

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]: ...

    @abstractmethod
    def fetch(self, since: Optional[str] = None) -> FetchResult: ...
