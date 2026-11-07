"""Erros de domínio padronizados (mapeados para respostas HTTP na API)."""
from __future__ import annotations

from typing import Any, Optional


class GoOpsError(Exception):
    code = "goops_error"
    status = 400

    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class ValidationError(GoOpsError):
    code, status = "validation_error", 422


class NotFound(GoOpsError):
    code, status = "not_found", 404


class PermissionDenied(GoOpsError):
    code, status = "permission_denied", 403


class AuthenticationError(GoOpsError):
    code, status = "authentication_error", 401


class Conflict(GoOpsError):
    code, status = "conflict", 409


class PolicyViolation(GoOpsError):
    code, status = "policy_violation", 403


class ExternalSourceError(GoOpsError):
    code, status = "external_source_error", 502
