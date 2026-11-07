"""Limitação de requisições.

* memory   — janela deslizante por IP no processo (padrão; uma instância).
* database — janela fixa de 1 minuto compartilhada entre instâncias (tabela rate_limit_hits).
Selecionado por RATE_LIMIT_BACKEND (configuração de infraestrutura).
"""
from __future__ import annotations

import ipaddress
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict


def _trusted_proxy(peer: str) -> bool:
    """Proxies confiáveis: TRUSTED_PROXIES (IPs separados por vírgula) ou, por padrão, loopback/rede privada — caso do
    Next.js (rewrite /api) e do proxy reverso no Docker. Um cliente público não consegue forjar X-Forwarded-For."""
    explicit = {x.strip() for x in os.environ.get("TRUSTED_PROXIES", "").split(",") if x.strip()}
    if explicit:
        return peer in explicit
    try:
        addr = ipaddress.ip_address(peer)
        return addr.is_loopback or addr.is_private
    except ValueError:
        return peer == "testclient"


def client_key(peer: str, forwarded_for: str | None) -> str:
    """IP do cliente real. Atrás do proxy, todas as requisições chegariam com o IP do frontend e o limite seria global."""
    if forwarded_for and _trusted_proxy(peer):
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    return peer


class SlidingWindowLimiter:
    def __init__(self, per_minute: int, window_seconds: float = 60):
        self.per_minute = max(1, per_minute)
        self.window = window_seconds
        self.hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._calls = 0

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        self._calls += 1
        if self._calls % 1000 == 0:   # descarta chaves ociosas (evita crescimento indefinido)
            for k in [k for k, v in self.hits.items() if not v or now - v[-1] > self.window]:
                self.hits.pop(k, None)
        if len(q) >= self.per_minute:
            return False
        q.append(now)
        return True


class DatabaseLimiter:
    def __init__(self, db, per_minute: int):
        self.db, self.per_minute, self._calls = db, max(1, per_minute), 0

    def allow(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        window = now.strftime("%Y-%m-%dT%H:%M")
        with self.db.connect() as c:
            row = c.fetchone("INSERT INTO rate_limit_hits (bucket, hits, window_start) VALUES (?, 1, ?) "
                             "ON CONFLICT (bucket) DO UPDATE SET hits = rate_limit_hits.hits + 1 RETURNING hits",
                             (f"{key}|{window}", window))
            self._calls += 1
            if self._calls % 200 == 0:
                c.execute("DELETE FROM rate_limit_hits WHERE window_start < ?",
                          ((now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M"),))
        return int(row["hits"]) <= self.per_minute
