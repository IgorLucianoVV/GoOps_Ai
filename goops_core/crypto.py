"""Cifragem de segredos em repouso (chaves de API configuradas pela interface).

Construção encrypt-then-MAC somente com a biblioteca padrão:
  * chaves derivadas de SECRET_KEY por HMAC-SHA256 (rótulos distintos para cifra e autenticação);
  * fluxo de chave = SHA-256(chave_cifra || nonce || contador) — modo contador;
  * autenticação = HMAC-SHA256(chave_mac, versão || nonce || texto_cifrado), verificada em tempo constante.
O texto em claro nunca é retornado pela API nem registrado em logs/auditoria.
ATENÇÃO: os segredos dependem de um SECRET_KEY estável; se ele mudar, os segredos precisam ser recadastrados.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from .errors import ValidationError

_VERSION = b"g1"


def _keys(secret_key: str) -> tuple:
    base = secret_key.encode()
    return (hmac.new(base, b"goops-secret-encryption", hashlib.sha256).digest(),
            hmac.new(base, b"goops-secret-authentication", hashlib.sha256).digest())


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out, counter = bytearray(), 0
    while len(out) < length:
        out += hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        counter += 1
    return bytes(out[:length])


def encrypt_secret(plaintext: str, secret_key: str) -> str:
    enc, mac = _keys(secret_key)
    nonce = secrets.token_bytes(16)
    data = plaintext.encode()
    ct = bytes(a ^ b for a, b in zip(data, _keystream(enc, nonce, len(data))))
    tag = hmac.new(mac, _VERSION + nonce + ct, hashlib.sha256).digest()
    return "g1:" + base64.urlsafe_b64encode(nonce + ct + tag).decode()


def decrypt_secret(token: str, secret_key: str) -> str:
    if not token or not token.startswith("g1:"):
        raise ValidationError("Formato de segredo inválido.")
    raw = base64.urlsafe_b64decode(token[3:].encode())
    nonce, ct, tag = raw[:16], raw[16:-32], raw[-32:]
    enc, mac = _keys(secret_key)
    if not hmac.compare_digest(tag, hmac.new(mac, _VERSION + nonce + ct, hashlib.sha256).digest()):
        raise ValidationError("Segredo não pôde ser autenticado (SECRET_KEY alterado?). Recadastre a chave.")
    return bytes(a ^ b for a, b in zip(ct, _keystream(enc, nonce, len(ct)))).decode()


def hint(plaintext: str) -> str:
    return ("…" + plaintext[-4:]) if len(plaintext) >= 8 else "…"
