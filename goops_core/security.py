"""Hash de senhas (PBKDF2) e tokens assinados (HMAC-SHA256) — apenas stdlib."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict

from .errors import AuthenticationError

_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("Senha deve ter ao menos 8 caracteres.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(payload: Dict[str, Any], secret: str, ttl_minutes: int) -> str:
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl_minutes * 60
    raw = _b64(json.dumps(body, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest())
    return f"{raw}.{sig}"


def decode_token(token: str, secret: str) -> Dict[str, Any]:
    try:
        raw, sig = token.split(".")
    except ValueError as exc:
        raise AuthenticationError("Token malformado.") from exc
    expected = _b64(hmac.new(secret.encode(), raw.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise AuthenticationError("Assinatura do token inválida.")
    payload = json.loads(_unb64(raw))
    if payload.get("exp", 0) < time.time():
        raise AuthenticationError("Token expirado.")
    return payload
