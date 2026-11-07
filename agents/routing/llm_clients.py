"""Clientes de LLM configuráveis (sem credenciais no código).

Provedores suportados:
  * anthropic           -> POST https://api.anthropic.com/v1/messages (API pública documentada)
  * openai_compatible   -> POST {OPENAI_BASE_URL}/chat/completions (padrão OpenAI-compatível)
  * none                -> sem LLM (a plataforma usa fallback determinístico, identificado como tal)
O modelo "JEF" (nível 1) é apenas um alias configurável: provedor e modelo vêm do ambiente.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from goops_core.config import ModelTier, Settings
from goops_core.errors import ExternalSourceError, ValidationError


@dataclass
class LLMResponse:
    text: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    latency_ms: int
    provider: str
    model: str


class LLMClient:
    def __init__(self, tier: ModelTier, settings: Settings):
        self.tier = tier
        self.settings = settings

    def complete(self, system: str, prompt: str, max_tokens: int = 600) -> LLMResponse:
        import requests

        provider, model = self.tier.provider, self.tier.model or ""
        from ..llm.providers import PROVIDERS, build_chat_model, module_available
        if provider in PROVIDERS and module_available(PROVIDERS[provider]["module"]) and module_available("langchain_core"):
            from ..llm.assistant_graph import complete_text
            text, usage, latency = complete_text(build_chat_model(provider, model, self.settings, max_tokens), system, prompt)
            return LLMResponse(text, usage["input_tokens"], usage["output_tokens"], latency, provider, usage["model"] or model)
        if provider in ("openai", "google", "ollama"):
            raise ValidationError(f"Pacote do provedor {provider} não instalado (pip install -r backend/requirements.txt).")
        t0 = time.perf_counter()
        if provider == "anthropic":
            key = self.settings.anthropic_api_key
            if not key:
                raise ValidationError("ANTHROPIC_API_KEY não configurada.")
            resp = requests.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
                "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": model, "max_tokens": max_tokens, "system": system,
                      "messages": [{"role": "user", "content": prompt}]})
            if resp.status_code >= 400:
                raise ExternalSourceError(f"LLM respondeu HTTP {resp.status_code}")
            body = resp.json()
            text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
            usage = body.get("usage") or {}
            return LLMResponse(text, usage.get("input_tokens"), usage.get("output_tokens"),
                               int((time.perf_counter() - t0) * 1000), provider, model)
        if provider in ("openai_compatible", "gogroup"):
            if provider == "gogroup":
                from ..llm.providers import GOGROUP_BASE_URL
                base, key = GOGROUP_BASE_URL, self.settings.ai_proxy_api_key
                if not key:
                    raise ValidationError("Token do AI Proxy Gogroup não configurado (Settings › Modelos e chaves).")
                if model.lower().startswith("deepseek"):
                    raise ValidationError("Modelos DeepSeek estão bloqueados no evento.")
                if model.startswith(("glm", "mimo", "k3", "kimi")):
                    max_tokens = max(max_tokens, 2000)   # extras raciocinam antes de responder
            else:
                base, key = self.settings.openai_base_url, self.settings.openai_api_key
            if not base:
                raise ValidationError("OPENAI_BASE_URL não configurada.")
            headers = {"content-type": "application/json"}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            resp = requests.post(base.rstrip("/") + "/chat/completions", timeout=60, headers=headers,
                                 json={"model": model, "max_tokens": max_tokens,
                                       "messages": [{"role": "system", "content": system},
                                                    {"role": "user", "content": prompt}]})
            if resp.status_code >= 400:
                raise ExternalSourceError(f"LLM respondeu HTTP {resp.status_code}")
            body = resp.json()
            text = body["choices"][0]["message"]["content"]
            usage = body.get("usage") or {}
            return LLMResponse(text, usage.get("prompt_tokens"), usage.get("completion_tokens"),
                               int((time.perf_counter() - t0) * 1000), provider, model)
        raise ValidationError(f"Provedor de LLM não suportado: {provider}")


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatTurn:
    """Uma rodada do modelo: texto (pode ser vazio) + chamadas de ferramentas pedidas."""
    text: str
    tool_calls: list
    raw_assistant: object          # mensagem a reenviar no histórico (formato do provedor)
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    latency_ms: int
    provider: str
    model: str


def _post(url: str, headers: dict, body: dict, timeout: int = 90) -> dict:
    import requests
    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    if resp.status_code >= 400:
        detail = ""
        try:
            detail = (resp.json().get("error") or {}).get("message", "")[:200]
        except Exception:  # noqa: BLE001
            pass
        raise ExternalSourceError(f"LLM respondeu HTTP {resp.status_code}" + (f": {detail}" if detail else ""))
    return resp.json()


def chat_with_tools(client: "LLMClient", system: str, messages: list, tools: list, max_tokens: int = 1200) -> ChatTurn:
    """Uma chamada com tool calling. `messages` usa o formato do provedor (mantido pelo chamador).
    `tools`: [{"name", "description", "parameters": JSON Schema}] — convertidos para o formato de cada provedor."""
    tier, settings = client.tier, client.settings
    provider, model = tier.provider, tier.model or ""
    t0 = time.perf_counter()
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValidationError("Chave Anthropic não configurada (Settings › Modelos e chaves).")
        body = _post("https://api.anthropic.com/v1/messages",
                     {"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                     {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages,
                      "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]})
        blocks = body.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        calls = [ToolCall(b["id"], b["name"], b.get("input") or {}) for b in blocks if b.get("type") == "tool_use"]
        usage = body.get("usage") or {}
        return ChatTurn(text, calls, {"role": "assistant", "content": blocks}, usage.get("input_tokens"),
                        usage.get("output_tokens"), int((time.perf_counter() - t0) * 1000), provider, model)
    if provider in ("openai_compatible", "gogroup"):
        from ..llm.providers import GOGROUP_BASE_URL
        base = GOGROUP_BASE_URL if provider == "gogroup" else settings.openai_base_url
        key = settings.ai_proxy_api_key if provider == "gogroup" else settings.openai_api_key
        if not base:
            raise ValidationError("OPENAI base URL não configurada.")
        import json as _json
        headers = {"content-type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = _post(base.rstrip("/") + "/chat/completions", headers,
                     {"model": model, "max_tokens": max_tokens, "messages": [{"role": "system", "content": system}] + messages,
                      "tools": [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                                  "parameters": t["parameters"]}} for t in tools]})
        msg = body["choices"][0]["message"]
        calls = []
        for c in msg.get("tool_calls") or []:
            try:
                args = _json.loads(c["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            calls.append(ToolCall(c["id"], c["function"]["name"], args))
        usage = body.get("usage") or {}
        return ChatTurn(msg.get("content") or "", calls, msg, usage.get("prompt_tokens"), usage.get("completion_tokens"),
                        int((time.perf_counter() - t0) * 1000), provider, model)
    raise ValidationError(f"Provedor não suporta ferramentas: {provider}")


def tool_result_messages(provider: str, results: list) -> list:
    """results: [(ToolCall, content_str, is_error)] -> mensagens no formato do provedor."""
    if provider == "anthropic":
        return [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": c.id, "content": content,
                                              **({"is_error": True} if err else {})} for c, content, err in results]}]
    return [{"role": "tool", "tool_call_id": c.id, "content": content} for c, content, _ in results]
