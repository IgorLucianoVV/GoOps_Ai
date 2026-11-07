"""Adaptador de banco de metadados (catálogo, governança, operações, auditoria).

Suporta SQLite (desenvolvimento/testes) e PostgreSQL (Docker/produção) com o mesmo SQL.
Regras:
  * Todas as consultas usam parâmetros (placeholders "?"), nunca concatenação -> proteção contra SQL injection.
  * O placeholder é convertido para "%s" no PostgreSQL.
  * Migrações versionadas em infrastructure/database/migrations/*.sql.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, List, Optional

from .config import ROOT_DIR
from .util import now_iso

log = logging.getLogger("goops.db")
MIGRATIONS_DIR = ROOT_DIR / "infrastructure" / "database" / "migrations"


class Connection:
    def __init__(self, raw: Any, dialect: str):
        self.raw = raw
        self.dialect = dialect

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.dialect == "postgresql" else sql

    def execute(self, sql: str, params: Iterable[Any] = ()) -> Any:
        cur = self.raw.cursor()
        cur.execute(self._sql(sql), tuple(params))
        return cur

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> List[dict]:
        cur = self.execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]

    def fetchone(self, sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
        cur = self.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row is not None else None

    def executescript(self, script: str) -> None:
        if self.dialect == "sqlite":
            self.raw.executescript(script)
        else:
            self.raw.execute(script)


class Database:
    def __init__(self, url: str):
        self.url = url
        if url.startswith("sqlite:///"):
            self.dialect = "sqlite"
            self.path = url[len("sqlite:///"):]
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        elif url.startswith(("postgresql://", "postgres://")):
            self.dialect = "postgresql"
            self.path = None
        else:
            raise ValueError("DATABASE_URL não suportada (use sqlite:/// ou postgresql://)")

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        if self.dialect == "sqlite":
            raw = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            raw.row_factory = sqlite3.Row
            raw.execute("PRAGMA foreign_keys=ON")
            raw.execute("PRAGMA journal_mode=WAL")
        else:  # pragma: no cover - requer PostgreSQL
            import psycopg
            from psycopg.rows import dict_row

            raw = psycopg.connect(self.url, row_factory=dict_row)
        conn = Connection(raw, self.dialect)
        try:
            yield conn
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()

    # Atalhos de uma única operação
    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> List[dict]:
        with self.connect() as c:
            return c.fetchall(sql, params)

    def fetchone(self, sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
        with self.connect() as c:
            return c.fetchone(sql, params)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self.connect() as c:
            c.execute(sql, params)

    def health(self) -> dict:
        try:
            self.fetchone("SELECT 1 AS ok")
            return {"status": "ok", "dialect": self.dialect}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "dialect": self.dialect, "error": type(exc).__name__}

    def migrate(self) -> List[str]:
        """Aplica migrações pendentes em ordem. Idempotente."""
        applied: List[str] = []
        with self.connect() as c:
            c.executescript(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL);"
            )
            done = {r["version"] for r in c.fetchall("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem
            if version in done:
                continue
            with self.connect() as c:
                c.executescript(path.read_text(encoding="utf-8"))
                c.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)", (version, now_iso()))
            applied.append(version)
            log.info("migration applied: %s", version)
        return applied


_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        from .config import get_settings

        _db = Database(get_settings().database_url)
    return _db


def set_db(db: Optional[Database]) -> None:
    global _db
    _db = db
