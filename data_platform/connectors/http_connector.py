"""Conector REST/JSON genérico e configurável (sem contrato presumido).

Exemplo de configuração (sources.config):
{
  "base_url": "https://api.exemplo.interno",       # definido pelo cliente, nunca inventado
  "endpoint": "/v1/orders",
  "auth": {"type": "bearer", "token_env": "ORDERS_API_TOKEN"},
  "pagination": {"type": "page", "page_param": "page", "size_param": "per_page", "page_size": 200,
                 "data_path": "data", "max_pages": 1000},
  "incremental": {"param": "updated_since", "cursor_field": "updated_at"},
  "timeout": 30, "max_retries": 3, "rate_limit_per_sec": 5, "schema_version": "1.0"
}
Tipos de paginação suportados: none | page | offset | cursor (next_path).
"""
from __future__ import annotations

import base64
import ipaddress
import os
import re
import socket
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from goops_core.errors import ExternalSourceError, ValidationError

from .base import BaseConnector, FetchResult, RetryableError


def _dig(obj: Any, path: Optional[str]) -> Any:
    if not path:
        return obj
    for part in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


# ---------- Proteções de saída (exfiltração de segredos e SSRF) ----------
# A configuração da fonte só referencia credenciais pelo NOME da variável de ambiente. Sem restrição, quem edita fontes
# poderia apontar `token_env=SECRET_KEY` para um servidor próprio e receber o segredo no cabeçalho. Por isso:
#   * o nome precisa seguir o padrão de credencial de fonte (prefixo SOURCE_ ou sufixo _TOKEN/_USER/_USERNAME/_PASSWORD)
#     ou estar em SOURCE_CREDENTIAL_ENV_ALLOWLIST; variáveis de infraestrutura/LLM são sempre recusadas;
#   * o host não pode resolver para rede privada/loopback/link-local (metadados de nuvem, banco interno), salvo se
#     listado em SOURCE_ALLOWED_PRIVATE_HOSTS; redirecionamentos não são seguidos.
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_DENIED_ENV = {"SECRET_KEY", "DATABASE_URL", "POSTGRES_PASSWORD", "POSTGRES_USER", "DEMO_ADMIN_PASSWORD",
               "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "OPENAI_BASE_URL", "OLLAMA_BASE_URL"}
_DENIED_PREFIX = ("LLM_", "POSTGRES", "DATABASE", "AWS_", "AZURE_", "GCP_", "GOOGLE_", "ANTHROPIC", "OPENAI",
                  "GITHUB_", "PGPASS", "APP_", "TOKEN_TTL", "RATE_LIMIT", "SCHEDULER")
_ALLOWED_SUFFIX = ("_TOKEN", "_USER", "_USERNAME", "_PASSWORD")


def _csv_env(name: str) -> set:
    return {x.strip() for x in os.environ.get(name, "").split(",") if x.strip()}


def validate_credential_env(name: str) -> str:
    """Valida o nome da variável de ambiente usada como credencial de uma fonte."""
    name = str(name or "").strip()
    if name in _csv_env("SOURCE_CREDENTIAL_ENV_ALLOWLIST"):
        return name
    if not _ENV_NAME.match(name):
        raise ValidationError("Nome de variável de credencial inválido (use MAIÚSCULAS, números e _).")
    if name in _DENIED_ENV or name.startswith(_DENIED_PREFIX):
        raise ValidationError(f"A variável '{name}' é de infraestrutura e não pode ser usada como credencial de fonte.")
    if not (name.startswith("SOURCE_") or name.endswith(_ALLOWED_SUFFIX)):
        raise ValidationError("Credenciais de fonte devem usar o prefixo SOURCE_ ou terminar em _TOKEN, _USER, "
                              "_USERNAME ou _PASSWORD (ou constar em SOURCE_CREDENTIAL_ENV_ALLOWLIST).")
    return name


def _is_private(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast
            or addr.is_unspecified)


def validate_outbound_url(url: str, resolve: bool = True, strict: bool = False) -> str:
    """Recusa esquemas não HTTP(S) e hosts internos. `strict`: falha também se o host não resolver."""
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValidationError("URL da fonte deve ser http(s) com host válido.")
    host = parsed.hostname.lower()
    if host in _csv_env("SOURCE_ALLOWED_PRIVATE_HOSTS"):
        return url
    if parsed.username or parsed.password:
        raise ValidationError("Não inclua usuário/senha na URL; use as variáveis de credencial.")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValidationError("Host interno não permitido para fontes externas (veja SOURCE_ALLOWED_PRIVATE_HOSTS).")
    try:
        ips = [host] if _looks_like_ip(host) else ([] if not resolve else
                                                   sorted({ai[4][0] for ai in socket.getaddrinfo(host, None)}))
    except socket.gaierror:
        if strict:
            raise ExternalSourceError(f"Não foi possível resolver o host {host}.")
        return url
    for ip in ips:
        if _is_private(ip.split("%")[0]):
            raise ValidationError(f"O host {host} aponta para rede privada/interna ({ip}). "
                                  "Libere explicitamente em SOURCE_ALLOWED_PRIVATE_HOSTS se for intencional.")
    return url


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


class HttpJsonConnector(BaseConnector):
    kind = "http_json"

    def __init__(self, source_key: str, config: Dict[str, Any]):
        super().__init__(source_key, config)
        if not config.get("base_url"):
            raise ValidationError(f"Fonte {source_key}: 'base_url' não configurada. Informe a URL real da API.")
        self.base_url = config["base_url"].rstrip("/")
        self.endpoint = config.get("endpoint", "")
        validate_outbound_url(self.base_url + self.endpoint)
        auth = config.get("auth") or {}
        for k in ("token_env", "user_env"):
            if auth.get(k):
                validate_credential_env(auth[k])
        self.timeout = float(config.get("timeout", 30))

    def _headers(self) -> Dict[str, str]:
        auth = self.config.get("auth") or {"type": "none"}
        headers = {"Accept": "application/json"}
        kind = auth.get("type", "none")
        if kind == "none":
            return headers
        secret = os.environ.get(validate_credential_env(auth.get("token_env", "")), "")
        if not secret:
            raise ValidationError(f"Variável de ambiente de credencial não definida para {self.source_key}.")
        if kind == "bearer":
            headers["Authorization"] = f"Bearer {secret}"
        elif kind == "api_key":
            headers[auth.get("header", "X-API-Key")] = secret
        elif kind == "basic":
            user = os.environ.get(validate_credential_env(auth.get("user_env", "")), "")
            headers["Authorization"] = "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()
        else:
            raise ValidationError(f"Tipo de autenticação não suportado: {kind}")
        return headers

    def _get(self, params: Dict[str, Any]) -> Any:
        import requests

        def call() -> Any:
            url = validate_outbound_url(self.base_url + self.endpoint, strict=True)  # revalida (DNS pode mudar)
            try:
                resp = requests.get(url, params=params, headers=self._headers(), timeout=self.timeout,
                                    allow_redirects=False)
            except requests.RequestException as exc:
                raise RetryableError(type(exc).__name__) from exc
            if resp.status_code == 429 or resp.status_code >= 500:
                raise RetryableError(f"HTTP {resp.status_code}")
            if 300 <= resp.status_code < 400:
                raise ExternalSourceError(f"Fonte {self.source_key} respondeu redirecionamento ({resp.status_code}); "
                                          "configure a URL final.")
            if resp.status_code >= 400:
                raise ExternalSourceError(f"Fonte {self.source_key} respondeu HTTP {resp.status_code}.")
            return resp.json()

        return self.with_retries(call)

    def test_connection(self) -> Dict[str, Any]:
        pag = self.config.get("pagination") or {}
        params = {}
        if pag.get("size_param"):
            params[pag["size_param"]] = 1
        body = self._get(params)
        data = _dig(body, pag.get("data_path"))
        return {"ok": True, "sample_records": len(data) if isinstance(data, list) else None}

    def fetch(self, since: Optional[str] = None) -> FetchResult:
        pag = self.config.get("pagination") or {"type": "none"}
        inc = self.config.get("incremental") or {}
        kind = pag.get("type", "none")
        size = int(pag.get("page_size", 100))
        max_pages = int(pag.get("max_pages", 1000))
        params: Dict[str, Any] = {}
        if since and inc.get("param"):
            params[inc["param"]] = since
        records: List[dict] = []
        failures: List[dict] = []
        page, offset, cursor, pages = int(pag.get("start_page", 1)), 0, None, 0
        while pages < max_pages:
            p = dict(params)
            if kind == "page":
                p[pag.get("page_param", "page")] = page
                p[pag.get("size_param", "per_page")] = size
            elif kind == "offset":
                p[pag.get("offset_param", "offset")] = offset
                p[pag.get("size_param", "limit")] = size
            elif kind == "cursor" and cursor:
                p[pag.get("cursor_param", "cursor")] = cursor
            body = self._get(p)
            pages += 1
            data = _dig(body, pag.get("data_path"))
            if not isinstance(data, list):
                raise ExternalSourceError(f"Fonte {self.source_key}: resposta sem lista em '{pag.get('data_path')}'.")
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    records.append(item)
                else:
                    failures.append({"record_ref": f"page{pages}:{i}", "error": "registro não é objeto JSON",
                                     "payload": str(item)[:500]})
            if kind == "none" or not data:
                break
            if kind == "page":
                if len(data) < size:
                    break
                page += 1
            elif kind == "offset":
                if len(data) < size:
                    break
                offset += size
            elif kind == "cursor":
                cursor = _dig(body, pag.get("next_path", "next"))
                if not cursor:
                    break
        next_cursor = None
        if inc.get("cursor_field") and records:
            values = [str(r.get(inc["cursor_field"])) for r in records if r.get(inc["cursor_field"])]
            next_cursor = max(values) if values else since
        return FetchResult(records=records, next_cursor=next_cursor or since, pages=pages, failures=failures,
                           schema_version=str(self.config.get("schema_version", "unknown")))
