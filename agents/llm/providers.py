"""Fábrica de modelos de chat (LangChain) para qualquer provedor configurado na interface.

Cada provedor é um pacote opcional; a disponibilidade é verificada em tempo de execução e exibida em Settings.
Credenciais vêm SEMPRE da configuração cifrada (ou do ambiente) — nunca do frontend.
"""
from __future__ import annotations

import importlib.util
from typing import Any, Dict, List

from goops_core.config import Settings
from goops_core.errors import ValidationError

GOGROUP_BASE_URL = "https://ai-proxy.gogroupbr.com/v1"   # AI Proxy do Gogroup (formato OpenAI)

PROVIDERS: Dict[str, Dict[str, Any]] = {
    "gogroup": {"label": "AI Proxy Gogroup (evento)", "module": "langchain_openai", "package": "langchain-openai",
                "secret": "ai_proxy_api_key", "examples": ["latest", "glm-5.3-flash", "gpt-6-luna", "mimo-v2.6-flash"]},
    "anthropic": {"label": "Anthropic (Claude)", "module": "langchain_anthropic", "package": "langchain-anthropic",
                  "secret": "anthropic_api_key", "examples": ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"]},
    "openai": {"label": "OpenAI", "module": "langchain_openai", "package": "langchain-openai",
               "secret": "openai_api_key", "examples": ["gpt-4o-mini", "gpt-4o"]},
    "google": {"label": "Google (Gemini)", "module": "langchain_google_genai", "package": "langchain-google-genai",
               "secret": "google_api_key", "examples": ["gemini-2.0-flash", "gemini-1.5-pro"]},
    "ollama": {"label": "Ollama (local, sem custo)", "module": "langchain_ollama", "package": "langchain-ollama",
               "secret": None, "examples": ["llama3.1", "qwen2.5"]},
    "openai_compatible": {"label": "OpenAI-compatível (gateway)", "module": "langchain_openai", "package": "langchain-openai",
                          "secret": "openai_api_key", "examples": []},
}


# Catálogo de referência exibido na lista de seleção (pode ficar desatualizado: use "Atualizar do provedor" em
# Settings para buscar os modelos que a sua chave realmente enxerga, ou "Outro…" para digitar um id).
MODEL_CATALOG: Dict[str, List[Dict[str, str]]] = {
    "gogroup": [{"id": "latest", "label": "latest — modelo mais avançado do proxy"},
                {"id": "gpt-6-luna", "label": "GPT-6 Luna — rápido"}, {"id": "gpt-6-sol", "label": "GPT-6 Sol"},
                {"id": "glm-5.3-flash", "label": "GLM 5.3 Flash — rápido, texto e imagem"},
                {"id": "glm-5.3", "label": "GLM 5.3 — mais capaz (só texto)"},
                {"id": "mimo-v2.6-flash", "label": "MiMo v2.6 Flash"}],
    "anthropic": [{"id": "claude-opus-5-5", "label": "Claude Opus 5.5 — mais capaz"},
                  {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5 — equilíbrio"},
                  {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5 — rápido e econômico"}],
    "openai": [{"id": "gpt-5", "label": "GPT-5"}, {"id": "gpt-5-mini", "label": "GPT-5 mini"},
               {"id": "gpt-4.1", "label": "GPT-4.1"}, {"id": "gpt-4.1-mini", "label": "GPT-4.1 mini"},
               {"id": "gpt-4o-mini", "label": "GPT-4o mini"}],
    "google": [{"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"}, {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
               {"id": "gemini-2.0-flash", "label": "Gemini 2.0 Flash"}],
    "ollama": [{"id": "llama3.1", "label": "Llama 3.1 (local)"}, {"id": "qwen2.5", "label": "Qwen 2.5 (local)"},
               {"id": "mistral", "label": "Mistral (local)"}],
    "openai_compatible": [],
}

_NOT_CHAT = ("embedding", "tts", "whisper", "dall-e", "image", "audio", "realtime", "transcribe", "moderation", "search")


def discover_models(provider: str, settings: Settings, timeout: int = 10) -> Dict[str, Any]:
    """Lista os modelos que a credencial configurada enxerga (endpoints públicos de listagem de cada provedor).

    Nunca devolve credenciais nem corpo de erro bruto; em falha, volta o catálogo de referência com o motivo.
    """
    import requests
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise ValidationError(f"Provedor não suportado: {provider}")
    catalog = MODEL_CATALOG.get(provider, [])
    try:
        if spec["secret"] and not getattr(settings, spec["secret"], None):
            raise ValidationError(f"Cadastre a chave de {spec['label']} antes de buscar os modelos.")
        if provider == "anthropic":
            r = requests.get("https://api.anthropic.com/v1/models", params={"limit": 100}, timeout=timeout,
                             headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"})
            r.raise_for_status()
            models = [{"id": m["id"], "label": m.get("display_name") or m["id"]} for m in r.json().get("data", [])]
        elif provider == "gogroup":
            r = requests.get(f"{GOGROUP_BASE_URL}/models", headers={"Authorization": f"Bearer {settings.ai_proxy_api_key}"},
                             timeout=timeout)
            r.raise_for_status()
            ids = sorted(m["id"] for m in r.json().get("data", []) if m.get("id") and not m["id"].lower().startswith("deepseek"))
            models = [{"id": i, "label": i} for i in ids]
        elif provider in ("openai", "openai_compatible"):
            base = "https://api.openai.com/v1" if provider == "openai" else (settings.openai_base_url or "").rstrip("/")
            if not base:
                raise ValidationError("Informe a base URL do provedor OpenAI-compatível.")
            headers = {"Authorization": f"Bearer {settings.openai_api_key}"} if settings.openai_api_key else {}
            r = requests.get(f"{base}/models", headers=headers, timeout=timeout)
            r.raise_for_status()
            ids = sorted(m["id"] for m in r.json().get("data", []) if m.get("id"))
            if provider == "openai":
                ids = [i for i in ids if not any(x in i for x in _NOT_CHAT)]
            models = [{"id": i, "label": i} for i in ids]
        elif provider == "google":
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 200},
                             headers={"x-goog-api-key": settings.google_api_key}, timeout=timeout)
            r.raise_for_status()
            models = [{"id": m["name"].split("/", 1)[-1], "label": m.get("displayName") or m["name"]}
                      for m in r.json().get("models", [])
                      if "generateContent" in (m.get("supportedGenerationMethods") or [])]
        elif provider == "ollama":
            base = (settings.ollama_base_url or "http://localhost:11434").rstrip("/")
            r = requests.get(f"{base}/api/tags", timeout=timeout)
            r.raise_for_status()
            models = [{"id": m["name"], "label": m["name"] + " (instalado)"} for m in r.json().get("models", []) if m.get("name")]
        else:
            models = []
        return {"provider": provider, "source": "provider", "models": models[:300], "error": None}
    except ValidationError as exc:
        return {"provider": provider, "source": "catalog", "models": catalog, "error": exc.message}
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "?"
        hint = " (chave inválida?)" if code in (401, 403) else ""
        return {"provider": provider, "source": "catalog", "models": catalog, "error": f"Provedor respondeu HTTP {code}{hint}."}
    except Exception as exc:  # noqa: BLE001 - nunca expor detalhes sensíveis
        return {"provider": provider, "source": "catalog", "models": catalog,
                "error": f"Não foi possível consultar o provedor ({type(exc).__name__})."}


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def langgraph_available() -> bool:
    return module_available("langgraph") and module_available("langchain_core")


def provider_status(settings: Settings) -> List[Dict[str, Any]]:
    out = []
    for key, spec in PROVIDERS.items():
        secret = spec["secret"]
        has_cred = True if secret is None else bool(getattr(settings, secret, None))
        if key == "openai_compatible":
            has_cred = bool(settings.openai_base_url)
        out.append({"provider": key, "label": spec["label"], "package": spec["package"],
                    "installed": module_available(spec["module"]), "credential": has_cred,
                    "examples": spec["examples"], "models": MODEL_CATALOG.get(key, []), "needs_key": secret is not None})
    return out


def build_chat_model(provider: str, model: str, settings: Settings, max_tokens: int = 1200, temperature: float = 0.1):
    """Instancia o modelo LangChain do provedor. Importações são tardias (pacotes opcionais)."""
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise ValidationError(f"Provedor não suportado: {provider}")
    if not module_available(spec["module"]):
        raise ValidationError(f"Pacote {spec['package']} não instalado (pip install -r backend/requirements.txt).")
    if spec["secret"] and not getattr(settings, spec["secret"], None):
        raise ValidationError(f"Credencial do provedor {spec['label']} não configurada (Settings › Modelos e chaves).")
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=settings.anthropic_api_key, max_tokens=max_tokens,
                             temperature=temperature, timeout=90, max_retries=2)
    if provider == "gogroup":
        from langchain_openai import ChatOpenAI
        if model.lower().startswith("deepseek"):
            raise ValidationError("Modelos DeepSeek estão bloqueados no evento.")
        extra = max_tokens if not model.startswith(("glm", "mimo", "k3", "kimi")) else max(max_tokens, 2000)
        return ChatOpenAI(model=model, max_tokens=extra, temperature=temperature, timeout=90, max_retries=2,
                          api_key=settings.ai_proxy_api_key, base_url=GOGROUP_BASE_URL)
    if provider in ("openai", "openai_compatible"):
        from langchain_openai import ChatOpenAI
        kwargs: Dict[str, Any] = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "timeout": 90,
                                  "max_retries": 2, "api_key": settings.openai_api_key or "not-needed"}
        if provider == "openai_compatible":
            if not settings.openai_base_url:
                raise ValidationError("Informe a base URL do provedor OpenAI-compatível.")
            kwargs["base_url"] = settings.openai_base_url
        return ChatOpenAI(**kwargs)
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, google_api_key=settings.google_api_key, max_output_tokens=max_tokens,
                                      temperature=temperature, timeout=90, max_retries=2)
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, base_url=settings.ollama_base_url or "http://localhost:11434",
                          temperature=temperature, num_predict=max_tokens)
    raise ValidationError(f"Provedor não suportado: {provider}")


def message_text(msg: Any) -> str:
    """Conteúdo textual de uma AIMessage (Anthropic pode devolver lista de blocos)."""
    content = getattr(msg, "content", msg)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content
                       if not isinstance(b, dict) or b.get("type") in (None, "text"))
    return str(content or "")


def usage_of(msg: Any) -> Dict[str, Any]:
    usage = getattr(msg, "usage_metadata", None) or {}
    meta = getattr(msg, "response_metadata", None) or {}
    return {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
            "model": meta.get("model_name") or meta.get("model")}
