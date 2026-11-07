"""Configuração central do GoOps AI.

Lê variáveis de ambiente (e opcionalmente um arquivo .env na raiz do projeto).
Nenhum segredo é registrado em logs: __repr__ mascara campos sensíveis.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
log = logging.getLogger("goops.config")

_SENSITIVE = ("key", "secret", "password", "token")


def load_dotenv(path: Path) -> None:
    """Parser mínimo de .env (KEY=VALUE). Não sobrescreve variáveis já definidas."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value[:1] in ("'", '"') and value[0] in value[1:]:
            value = value[1:value.index(value[0], 1)]          # valor entre aspas (pode conter #)
        elif " #" in value or "\t#" in value:
            value = value.split("#", 1)[0].strip()               # comentário ao final da linha
        os.environ.setdefault(key.strip(), value)


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class ModelTier:
    """Modelo configurado para um nível do Intelligent Cost Routing."""
    level: int
    provider: str  # none | anthropic | openai_compatible
    model: Optional[str]
    alias: str = ""

    @property
    def enabled(self) -> bool:
        return self.provider not in ("", "none") and bool(self.model)


@dataclass
class Settings:
    app_env: str
    database_url: str
    lakehouse_path: Path
    storage_format: str
    secret_key: str
    secret_key_ephemeral: bool
    token_ttl_minutes: int
    cors_origins: list
    demo_mode: bool
    demo_admin_password: Optional[str]
    action_execution_mode: str
    rate_limit_per_minute: int
    models: Dict[int, ModelTier] = field(default_factory=dict)
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    ai_proxy_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    google_api_key: Optional[str] = None
    ollama_base_url: Optional[str] = None
    chat_models: list = field(default_factory=list)
    model_pricing: Dict[str, Dict[str, float]] = field(default_factory=dict)
    cost_limit_per_run_usd: float = 0.50
    cost_limit_daily_usd: float = 5.00
    monitor_nps_drop_points: float = 8.0
    monitor_min_sample: int = 30
    monitor_carrier_late_increase_pp: float = 15.0
    monitor_product_detractor_ratio: float = 1.8
    auto_investigate: bool = True

    def __repr__(self) -> str:  # nunca expor segredos
        parts = []
        for k, v in self.__dict__.items():
            if any(s in k for s in _SENSITIVE) and v:
                v = "***"
            parts.append(f"{k}={v!r}")
        return f"Settings({', '.join(parts)})"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def _build_settings() -> Settings:
    load_dotenv(ROOT_DIR / ".env")
    app_env = _env("APP_ENV", "development")

    secret = _env("SECRET_KEY")
    ephemeral = False
    if not secret:
        if app_env == "production":
            raise RuntimeError("SECRET_KEY é obrigatório em produção.")
        # Desenvolvimento: chave local persistida em var/.secret_key (fora do git) para que sessões e chaves de API
        # cifradas sobrevivam a reinícios da API (ex.: uvicorn --reload).
        key_file = ROOT_DIR / "var" / ".secret_key"
        try:
            if key_file.exists():
                secret = key_file.read_text(encoding="utf-8").strip()
            if not secret:
                key_file.parent.mkdir(parents=True, exist_ok=True)
                secret = secrets.token_urlsafe(48)
                key_file.write_text(secret, encoding="utf-8")
                try:
                    key_file.chmod(0o600)
                except OSError:
                    pass
            log.warning("SECRET_KEY não definido: usando chave local de desenvolvimento em var/.secret_key.")
        except OSError:
            secret = secrets.token_urlsafe(48)
            ephemeral = True
            log.warning("SECRET_KEY não definido: usando chave efêmera (tokens expiram ao reiniciar).")

    models: Dict[int, ModelTier] = {}
    for level, prefix, alias in ((1, "SMALL", "JEF"), (2, "ECONOMY", ""), (3, "ADVANCED", "")):
        models[level] = ModelTier(
            level=level,
            provider=(_env(f"LLM_{prefix}_PROVIDER", "none") or "none").lower(),
            model=_env(f"LLM_{prefix}_MODEL"),
            alias=_env(f"LLM_{prefix}_ALIAS", alias) or "",
        )

    pricing: Dict[str, Dict[str, float]] = {}
    raw_pricing = _env("MODEL_PRICING_JSON")
    if raw_pricing:
        try:
            pricing = json.loads(raw_pricing)
        except json.JSONDecodeError:
            log.error("MODEL_PRICING_JSON inválido; custos serão registrados como desconhecidos.")

    return Settings(
        app_env=app_env,
        database_url=_env("DATABASE_URL", f"sqlite:///{(ROOT_DIR / 'var' / 'goops.db').as_posix()}"),
        lakehouse_path=Path(_env("LAKEHOUSE_PATH", str(ROOT_DIR / "var" / "lakehouse"))),
        storage_format=(_env("STORAGE_FORMAT", "auto") or "auto").lower(),
        secret_key=secret,
        secret_key_ephemeral=ephemeral,
        token_ttl_minutes=int(_env("TOKEN_TTL_MINUTES", "480")),
        cors_origins=[o.strip() for o in (_env("CORS_ORIGINS", "http://localhost:3000") or "").split(",") if o.strip()],
        demo_mode=(_env("DEMO_MODE", "true") or "true").lower() == "true",
        demo_admin_password=_env("DEMO_ADMIN_PASSWORD"),
        action_execution_mode=_env("ACTION_EXECUTION_MODE", "simulated") or "simulated",
        rate_limit_per_minute=int(_env("RATE_LIMIT_PER_MINUTE", "300")),
        models=models,
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        openai_api_key=_env("OPENAI_API_KEY"),
        ai_proxy_api_key=_env("AI_PROXY_API_KEY"),
        openai_base_url=_env("OPENAI_BASE_URL"),
        google_api_key=_env("GOOGLE_API_KEY"),
        ollama_base_url=_env("OLLAMA_BASE_URL", "http://localhost:11434"),
        model_pricing=pricing,
        cost_limit_per_run_usd=_env_float("COST_LIMIT_PER_RUN_USD", 0.50),
        cost_limit_daily_usd=_env_float("COST_LIMIT_DAILY_USD", 5.00),
        monitor_nps_drop_points=_env_float("MONITOR_NPS_DROP_POINTS", 8.0),
        monitor_min_sample=int(_env("MONITOR_MIN_SAMPLE", "30")),
        monitor_carrier_late_increase_pp=_env_float("MONITOR_CARRIER_LATE_INCREASE_PP", 15.0),
        monitor_product_detractor_ratio=_env_float("MONITOR_PRODUCT_DETRACTOR_RATIO", 1.8),
        auto_investigate=(_env("AUTO_INVESTIGATE", "true") or "true").lower() == "true",
    )


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = _build_settings()
    return _settings


def reset_settings() -> None:
    """Usado em testes após alterar variáveis de ambiente."""
    global _settings
    _settings = None
