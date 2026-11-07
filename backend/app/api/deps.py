"""Dependências da API: banco, lakehouse, autenticação e autorização."""
from __future__ import annotations

from typing import Callable, Optional

import hmac

from fastapi import Cookie, Depends, Header, Request

from goops_core.db import Database, get_db
from goops_core.errors import AuthenticationError
from goops_core.permissions import Principal, require_permission
from goops_core.users import principal_from_token
from data_platform.storage import Lakehouse, get_lakehouse


def db_dep() -> Database:
    return get_db()


def lake_dep() -> Lakehouse:
    return get_lakehouse()


SESSION_COOKIE, CSRF_COOKIE, CSRF_HEADER = "goops_session", "goops_csrf", "x-csrf-token"


def current_principal(request: Request, authorization: Optional[str] = Header(default=None),
                      goops_session: Optional[str] = Cookie(default=None), goops_csrf: Optional[str] = Cookie(default=None),
                      db: Database = Depends(db_dep)) -> Principal:
    """Aceita Bearer (clientes de API) ou cookie httpOnly (navegador). Com cookie, requisições que alteram
    estado exigem o cabeçalho X-CSRF-Token igual ao cookie goops_csrf (double-submit)."""
    if authorization and authorization.lower().startswith("bearer "):
        return principal_from_token(db, authorization.split(" ", 1)[1].strip())
    if goops_session:
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            sent = request.headers.get(CSRF_HEADER) or ""
            if not goops_csrf or not hmac.compare_digest(sent, goops_csrf):
                raise AuthenticationError("Token CSRF ausente ou inválido.")
        return principal_from_token(db, goops_session)
    raise AuthenticationError("Autenticação necessária.")


def require(permission: str, domain: Optional[str] = None) -> Callable[..., Principal]:
    def dep(principal: Principal = Depends(current_principal)) -> Principal:
        require_permission(principal, permission, domain)
        return principal
    return dep


def ok(data, meta: Optional[dict] = None) -> dict:
    """Envelope padrão de resposta."""
    return {"data": data, "meta": meta or {}}
