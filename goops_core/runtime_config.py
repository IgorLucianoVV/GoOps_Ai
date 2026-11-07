"""Configuração de runtime editável pela INTERFACE do produto.

Precedência: valor salvo na interface (tabela app_settings) > variável de ambiente > padrão.
Seções: llm, cost, monitor, scheduler, retention, policies, features, support. Chaves de API são guardadas
CIFRADAS (goops_core.crypto) e nunca retornadas em claro — a API expõe apenas se estão
configuradas e um sufixo de 4 caracteres.
"""
from __future__ import annotations

import copy
import re
import dataclasses
from typing import Any, Dict, List, Optional

from .audit import record_audit
from .config import ModelTier, Settings, get_settings
from .crypto import decrypt_secret, encrypt_secret, hint
from .db import Database
from .errors import ValidationError
from .permissions import Principal, require_permission
from .support_catalog import CHANNELS as SUPPORT_CHANNELS, DEFAULT_CONFIG as SUPPORT_DEFAULTS, INTENTS as SUPPORT_INTENTS
from .util import jdump, jload, now_iso

PROVIDERS = ["none", "gogroup", "anthropic", "openai", "google", "ollama", "openai_compatible"]
SECRET_NAMES = {"ai_proxy_api_key": "Token do AI Proxy Gogroup (gw-tok-…)",
                "telegram_bot_token": "Token do bot do Telegram (canal do time)",
                "slack_webhook_url": "URL do webhook do Slack (canal do time)",
                "anthropic_api_key": "Chave de API Anthropic (Claude)", "openai_api_key": "Chave de API OpenAI / compatível",
                "google_api_key": "Chave de API Google (Gemini)"}


def _env_secret(name: str):
    env = get_settings()
    import os
    return {"ai_proxy_api_key": env.ai_proxy_api_key, "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN") or None,
            "slack_webhook_url": os.environ.get("SLACK_WEBHOOK_URL") or None,
            "anthropic_api_key": env.anthropic_api_key, "openai_api_key": env.openai_api_key,
            "google_api_key": env.google_api_key}.get(name)
APPROVER_ROLE_CHOICES = ["admin", "data_owner", "domain_owner", "data_steward"]

DEFAULTS: Dict[str, Dict[str, Any]] = {
    "scheduler": {"pipeline_enabled": False, "pipeline_interval_minutes": 360,
                  "monitor_enabled": False, "monitor_interval_minutes": 60,
                  "retention_enabled": False, "retention_interval_minutes": 1440,
                  "support_enabled": False, "support_interval_minutes": 15},
    "retention": {"bronze_days": 180, "quarantine_days": 90, "logs_days": 90},
    "policies": {},
    # Recursos opcionais da demonstração (ligáveis/desligáveis em Configurações › Recursos)
    "support": copy.deepcopy(SUPPORT_DEFAULTS),
    # Canal do time: onde os agentes avisam e pedem aprovação (app sempre; Telegram/Slack quando configurados)
    "team_channel": {"provider": "app", "telegram_chat_id": "", "app_base_url": "http://localhost:3000",
                     "notify_approvals": True, "notify_sla": True, "notify_incidents": True, "notify_digest": True},
    "features": {"support": True, "sector_stock": True, "whatif": True, "briefing_enabled": False, "briefing_interval_minutes": 1440,
                 "briefing_ai": False, "briefing_slack": True, "briefing_slack_channel": "#operacoes",
                 "briefing_email": False, "briefing_email_to": []},
}


def _env_section(name: str, s: Settings) -> Dict[str, Any]:
    if name == "llm":
        return {"levels": {str(l): {"provider": t.provider, "model": t.model or "", "alias": t.alias}
                           for l, t in s.models.items()},
                "openai_base_url": s.openai_base_url or "", "ollama_base_url": s.ollama_base_url or "",
                "pricing": copy.deepcopy(s.model_pricing), "chat_models": []}
    if name == "cost":
        return {"limit_per_run_usd": s.cost_limit_per_run_usd, "limit_daily_usd": s.cost_limit_daily_usd}
    if name == "monitor":
        return {"nps_drop_points": s.monitor_nps_drop_points, "min_sample": s.monitor_min_sample,
                "carrier_late_increase_pp": s.monitor_carrier_late_increase_pp,
                "product_detractor_ratio": s.monitor_product_detractor_ratio, "auto_investigate": s.auto_investigate}
    return copy.deepcopy(DEFAULTS.get(name, {}))


SECTIONS = ("llm", "cost", "monitor", "scheduler", "retention", "policies", "features", "support", "team_channel")


def _stored(db: Database, key: str) -> Optional[dict]:
    row = db.fetchone("SELECT value, updated_by, updated_at FROM app_settings WHERE key = ?", (key,))
    if not row:
        return None
    return {"value": jload(row["value"], None), "updated_by": row["updated_by"], "updated_at": row["updated_at"]}


def get_section(db: Database, name: str) -> Dict[str, Any]:
    if name not in SECTIONS:
        raise ValidationError(f"Seção desconhecida: {name}")
    base = _env_section(name, get_settings())
    stored = _stored(db, f"config:{name}")
    if stored and isinstance(stored["value"], dict):
        _deep_merge(base, stored["value"])
    return base


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict) and k not in ("pricing", "policies", "chat_models"):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def get_secret(db: Database, name: str) -> Optional[str]:
    stored = _stored(db, f"secret:{name}")
    if stored and stored["value"]:
        return decrypt_secret(stored["value"], get_settings().secret_key)
    return _env_secret(name)


def effective_settings(db: Database) -> Settings:
    """Settings do ambiente com as substituições feitas pela interface (modelos, chaves, limites, monitor)."""
    s = get_settings()
    llm, cost, mon = get_section(db, "llm"), get_section(db, "cost"), get_section(db, "monitor")
    models = {int(l): ModelTier(level=int(l), provider=(v.get("provider") or "none"), model=(v.get("model") or None),
                                alias=v.get("alias") or "") for l, v in llm["levels"].items()}
    keys = {}
    for name in SECRET_NAMES:
        try:
            keys[name] = get_secret(db, name)
        except ValidationError:
            keys[name] = _env_secret(name)
    return dataclasses.replace(
        s, models=models, ai_proxy_api_key=keys["ai_proxy_api_key"], anthropic_api_key=keys["anthropic_api_key"], openai_api_key=keys["openai_api_key"],
        google_api_key=keys["google_api_key"], openai_base_url=llm.get("openai_base_url") or None,
        ollama_base_url=llm.get("ollama_base_url") or s.ollama_base_url, chat_models=list(llm.get("chat_models") or []),
        model_pricing=llm.get("pricing") or {}, cost_limit_per_run_usd=float(cost["limit_per_run_usd"]),
        cost_limit_daily_usd=float(cost["limit_daily_usd"]), monitor_nps_drop_points=float(mon["nps_drop_points"]),
        monitor_min_sample=int(mon["min_sample"]), monitor_carrier_late_increase_pp=float(mon["carrier_late_increase_pp"]),
        monitor_product_detractor_ratio=float(mon["product_detractor_ratio"]), auto_investigate=bool(mon["auto_investigate"]))


# ------------------------------------------------------------------ validação
def _num(v: Any, name: str, lo: float, hi: float, integer: bool = False) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValidationError(f"{name} deve ser numérico.")
    if not (lo <= v <= hi):
        raise ValidationError(f"{name} deve estar entre {lo} e {hi}.")
    if integer and int(v) != v:
        raise ValidationError(f"{name} deve ser inteiro.")
    return int(v) if integer else float(v)


def _validate(name: str, value: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("Valor da seção deve ser um objeto.")
    if name == "llm":
        out: Dict[str, Any] = {}
        levels = value.get("levels", {})
        if levels:
            out["levels"] = {}
            for lvl, cfg in levels.items():
                if str(lvl) not in ("1", "2", "3"):
                    raise ValidationError("Níveis permitidos: 1, 2, 3.")
                provider = (cfg.get("provider") or "none").strip()
                if provider not in PROVIDERS:
                    raise ValidationError(f"Provedor inválido: {provider}")
                model = (cfg.get("model") or "").strip()
                if provider != "none" and not model:
                    raise ValidationError(f"Informe o modelo do nível {lvl}.")
                if model.lower().startswith("deepseek"):
                    raise ValidationError("Modelos DeepSeek estão bloqueados no evento; use glm-5.3, gpt-6-* ou latest.")
                if len(model) > 120 or len(cfg.get("alias") or "") > 40:
                    raise ValidationError("Nome de modelo/alias muito longo.")
                out["levels"][str(lvl)] = {"provider": provider, "model": model, "alias": (cfg.get("alias") or "").strip()}
        if "openai_base_url" in value:
            url = (value.get("openai_base_url") or "").strip()
            if url and not url.startswith(("https://", "http://")):
                raise ValidationError("OPENAI base URL deve começar com http(s)://")
            out["openai_base_url"] = url
        if "ollama_base_url" in value:
            url = (value.get("ollama_base_url") or "").strip()
            if url and not url.startswith(("https://", "http://")):
                raise ValidationError("URL do Ollama deve começar com http(s)://")
            out["ollama_base_url"] = url
        if "chat_models" in value:
            models_out, seen = [], set()
            for item in value.get("chat_models") or []:
                prov = (item.get("provider") or "").strip()
                mdl = (item.get("model") or "").strip()
                if prov not in PROVIDERS or prov == "none":
                    raise ValidationError(f"Provedor inválido na lista do chat: {prov}")
                if mdl.lower().startswith("deepseek"):
                    raise ValidationError("Modelos DeepSeek estão bloqueados no evento.")
                if not mdl or len(mdl) > 120 or any(c.isspace() for c in mdl):
                    raise ValidationError("Modelo inválido na lista do chat.")
                key = f"{prov}:{mdl}"
                if key in seen:
                    continue
                seen.add(key)
                models_out.append({"id": key, "provider": prov, "model": mdl,
                                   "label": (item.get("label") or f"{prov} · {mdl}").strip()[:60]})
            if len(models_out) > 12:
                raise ValidationError("No máximo 12 modelos na lista do chat.")
            out["chat_models"] = models_out
        if "pricing" in value:
            pricing = {}
            for model, p in (value.get("pricing") or {}).items():
                if not model or len(model) > 120:
                    raise ValidationError("Nome de modelo inválido na tabela de preços.")
                pricing[model] = {"input_per_mtok": _num(p.get("input_per_mtok", 0), "Preço de entrada", 0, 10000),
                                  "output_per_mtok": _num(p.get("output_per_mtok", 0), "Preço de saída", 0, 10000)}
            out["pricing"] = pricing
        return out
    if name == "cost":
        return {"limit_per_run_usd": _num(value.get("limit_per_run_usd"), "Limite por execução", 0, 1000),
                "limit_daily_usd": _num(value.get("limit_daily_usd"), "Limite diário", 0, 100000)}
    if name == "monitor":
        return {"nps_drop_points": _num(value.get("nps_drop_points"), "Queda de NPS", 1, 100),
                "min_sample": _num(value.get("min_sample"), "Amostra mínima", 1, 100000, True),
                "carrier_late_increase_pp": _num(value.get("carrier_late_increase_pp"), "Aumento de atraso", 1, 100),
                "product_detractor_ratio": _num(value.get("product_detractor_ratio"), "Razão de detratores", 1, 20),
                "auto_investigate": bool(value.get("auto_investigate"))}
    if name == "scheduler":
        out = {}
        for job, min_interval in (("pipeline", 5), ("monitor", 5), ("retention", 60), ("support", 1)):
            out[f"{job}_enabled"] = bool(value.get(f"{job}_enabled"))
            out[f"{job}_interval_minutes"] = _num(value.get(f"{job}_interval_minutes", DEFAULTS["scheduler"][f"{job}_interval_minutes"]),
                                                  f"Intervalo de {job}", min_interval, 10080, True)
        return out
    if name == "retention":
        return {k: _num(value.get(k), k, 7, 3650, True) for k in ("bronze_days", "quarantine_days", "logs_days")}
    if name == "features":
        d = DEFAULTS["features"]
        out = {k: bool(value.get(k, d[k])) for k in ("support", "sector_stock", "whatif", "briefing_enabled", "briefing_ai",
                                                     "briefing_slack", "briefing_email")}
        out["briefing_interval_minutes"] = _num(value.get("briefing_interval_minutes", d["briefing_interval_minutes"]),
                                                "Frequência do briefing", 60, 10080, True)
        ch = str(value.get("briefing_slack_channel", d["briefing_slack_channel"]) or "").strip()
        if ch and not re.fullmatch(r"#[a-z0-9_\-]{1,80}", ch):
            raise ValidationError("Canal do Slack deve ser como #operacoes (minúsculas, números, - e _).")
        out["briefing_slack_channel"] = ch or "#operacoes"
        emails = value.get("briefing_email_to", d["briefing_email_to"]) or []
        if isinstance(emails, str):
            emails = [e.strip() for e in emails.split(",") if e.strip()]
        if len(emails) > 20 or any(not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", e, re.I) for e in emails):
            raise ValidationError("E-mails do briefing inválidos (até 20, separados por vírgula).")
        out["briefing_email_to"] = emails
        return out
    if name == "support":
        return _validate_support(value)
    if name == "team_channel":
        d = DEFAULTS["team_channel"]
        prov = value.get("provider", d["provider"])
        if prov not in ("app", "telegram", "slack"):
            raise ValidationError("Canal do time: use app, telegram ou slack.")
        chat = str(value.get("telegram_chat_id", d["telegram_chat_id"]) or "").strip()
        if chat and not re.fullmatch(r"-?\d{3,20}|@[A-Za-z0-9_]{4,64}", chat):
            raise ValidationError("ID do chat do Telegram inválido (número, ex.: -1001234567890, ou @canal).")
        url = str(value.get("app_base_url", d["app_base_url"]) or "").strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            raise ValidationError("Endereço do GoOps deve começar com http(s)://")
        out = {"provider": prov, "telegram_chat_id": chat, "app_base_url": url or d["app_base_url"]}
        for k in ("notify_approvals", "notify_sla", "notify_incidents", "notify_digest"):
            out[k] = bool(value.get(k, d[k]))
        return out
    if name == "policies":
        from .policies import ACTION_CATALOG, CRITICAL_AREAS
        out = {}
        for action, cfg in value.items():
            if action not in ACTION_CATALOG:
                raise ValidationError(f"Ação desconhecida: {action}")
            roles = cfg.get("approver_roles") or []
            if not roles or any(r not in APPROVER_ROLE_CHOICES for r in roles):
                raise ValidationError(f"Aprovadores inválidos para {action}. Opções: {APPROVER_ROLE_CHOICES}")
            critical = bool(set(ACTION_CATALOG[action]["impacted_areas"]) & CRITICAL_AREAS)
            requires = bool(cfg.get("requires_approval", True))
            if critical and not requires:
                raise ValidationError(f"{action} impacta área crítica: a aprovação humana não pode ser desativada.")
            if critical and roles == ["data_steward"]:
                raise ValidationError("Ações críticas exigem ao menos um aprovador com papel de dono (admin/data_owner/domain_owner).")
            out[action] = {"approver_roles": roles, "requires_approval": requires or critical}
        return out
    raise ValidationError(f"Seção desconhecida: {name}")


def _validate_support(value: Dict[str, Any]) -> Dict[str, Any]:
    """Matriz de automação do Atendimento. Listas fechadas; nada aqui executa código."""
    d = SUPPORT_DEFAULTS
    out: Dict[str, Any] = {}
    intents = value.get("auto_intents", d["auto_intents"])
    if not isinstance(intents, list) or any(i not in SUPPORT_INTENTS for i in intents):
        raise ValidationError(f"Intenções inválidas. Opções: {sorted(SUPPORT_INTENTS)}")
    claims_auto = [i for i in intents if SUPPORT_INTENTS[i]["claim"] and i != "atraso_entrega"]
    if claims_auto:
        raise ValidationError("Reclamações que pedem reparação (avaria, defeito, não recebido, produto errado) exigem "
                              f"verificação e não podem ser resolvidas sem pessoa: {claims_auto}")
    out["auto_intents"] = sorted(set(intents))
    channels = value.get("human_channels", d["human_channels"])
    if not isinstance(channels, list) or any(c not in SUPPORT_CHANNELS for c in channels):
        raise ValidationError(f"Canais inválidos. Opções: {sorted(SUPPORT_CHANNELS)}")
    out["human_channels"] = sorted(set(channels))
    urg = value.get("human_from_urgency", d["human_from_urgency"])
    if urg not in ("media", "alta", "critica"):
        raise ValidationError("Urgência para revisão humana deve ser media, alta ou critica.")
    out["human_from_urgency"] = urg
    out["min_confidence"] = _num(value.get("min_confidence", d["min_confidence"]), "Confiança mínima", 0.3, 0.99)
    out["claim_value_human_brl"] = _num(value.get("claim_value_human_brl", d["claim_value_human_brl"]),
                                        "Valor para revisão humana", 0, 100000)
    out["veracity_consistent_min"] = _num(value.get("veracity_consistent_min", d["veracity_consistent_min"]),
                                          "Faixa consistente", 50, 95, True)
    out["veracity_inconsistent_max"] = _num(value.get("veracity_inconsistent_max", d["veracity_inconsistent_max"]),
                                            "Faixa inconsistente", 5, 49, True)
    out["recontact_window_days"] = _num(value.get("recontact_window_days", d["recontact_window_days"]),
                                        "Janela de recontato", 1, 60, True)
    out["auto_minutes"] = _num(value.get("auto_minutes", d["auto_minutes"]), "Minutos por contato automático", 0, 30)
    out["reopen_window_hours"] = _num(value.get("reopen_window_hours", d["reopen_window_hours"]),
                                      "Janela de reabertura (h)", 0, 168, True)
    out["inactivity_close_hours"] = _num(value.get("inactivity_close_hours", d["inactivity_close_hours"]),
                                         "Encerramento por inatividade (h)", 1, 720, True)
    out["continue_window_hours"] = _num(value.get("continue_window_hours", d["continue_window_hours"]),
                                        "Janela de continuidade (h)", 1, 720, True)
    out["sla_first_response_hours"] = _num(value.get("sla_first_response_hours", d["sla_first_response_hours"]),
                                           "SLA de 1ª resposta (h)", 0.25, 168)
    out["reminder_before_close_hours"] = _num(value.get("reminder_before_close_hours", d["reminder_before_close_hours"]),
                                              "Lembrete antes de encerrar (h)", 0, 168)
    out["spike_min_contacts"] = _num(value.get("spike_min_contacts", d["spike_min_contacts"]),
                                     "Mínimo de reclamações para incidente", 2, 1000, True)
    for k in ("repeat_to_human", "auto_carrier_ticket", "llm_classify_low_confidence", "llm_summary", "llm_reply"):
        out[k] = bool(value.get(k, d[k]))
    mm = value.get("manual_minutes", d["manual_minutes"]) or {}
    if not isinstance(mm, dict) or any(k not in SUPPORT_INTENTS for k in mm):
        raise ValidationError("Minutos manuais: use as intenções do catálogo.")
    out["manual_minutes"] = {k: _num(mm.get(k, d["manual_minutes"][k]), f"Minutos de {k}", 0, 600)
                             for k in SUPPORT_INTENTS}
    return out


def update_section(db: Database, actor: Principal, name: str, value: Dict[str, Any]) -> Dict[str, Any]:
    require_permission(actor, "settings:write")
    if name not in SECTIONS:
        raise ValidationError(f"Seção desconhecida: {name}")
    clean = _validate(name, value)
    stored = _stored(db, f"config:{name}")
    merged = stored["value"] if stored and isinstance(stored["value"], dict) else {}
    if name in ("policies",):
        merged = clean
    else:
        merged = {**merged, **clean}
    db.execute("INSERT INTO app_settings (key, value, updated_by, updated_at) VALUES (?, ?, ?, ?) "
               "ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by, "
               "updated_at = excluded.updated_at", (f"config:{name}", jdump(merged), actor.actor_label, now_iso()))
    record_audit(db, actor, "settings.update", "settings", name, {"fields": sorted(clean.keys())})
    return get_section(db, name)


def reset_section(db: Database, actor: Principal, name: str) -> Dict[str, Any]:
    require_permission(actor, "settings:write")
    db.execute("DELETE FROM app_settings WHERE key = ?", (f"config:{name}",))
    record_audit(db, actor, "settings.reset", "settings", name, {})
    return get_section(db, name)


def set_secret(db: Database, actor: Principal, name: str, value: Optional[str]) -> dict:
    require_permission(actor, "settings:write")
    if name not in SECRET_NAMES:
        raise ValidationError("Segredo desconhecido.")
    if value is None or value == "":
        db.execute("DELETE FROM app_settings WHERE key = ?", (f"secret:{name}",))
        record_audit(db, actor, "settings.secret_cleared", "settings", name, {})
    else:
        value = value.strip()
        if len(value) < 8 or len(value) > 500 or any(c.isspace() for c in value):
            raise ValidationError("Chave inválida (8–500 caracteres, sem espaços).")
        db.execute("INSERT INTO app_settings (key, value, updated_by, updated_at) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by, "
                   "updated_at = excluded.updated_at",
                   (f"secret:{name}", jdump(encrypt_secret(value, get_settings().secret_key)), actor.actor_label, now_iso()))
        record_audit(db, actor, "settings.secret_set", "settings", name, {"hint": hint(value)})
    return secrets_view(db)[name]


def secrets_view(db: Database) -> Dict[str, dict]:
    env = get_settings()
    out = {}
    for name, label in SECRET_NAMES.items():
        stored = _stored(db, f"secret:{name}")
        env_val = _env_secret(name)
        info = {"label": label, "configured": False, "source": None, "hint": None, "updated_at": None, "updated_by": None,
                "readable": True}
        if stored and stored["value"]:
            info.update(configured=True, source="ui", updated_at=stored["updated_at"], updated_by=stored["updated_by"])
            try:
                info["hint"] = hint(decrypt_secret(stored["value"], env.secret_key))
            except ValidationError:
                info["readable"] = False
        elif env_val:
            info.update(configured=True, source="env", hint=hint(env_val))
        out[name] = info
    return out


def config_view(db: Database) -> Dict[str, Any]:
    s = get_settings()
    sections = {}
    for name in SECTIONS:
        stored = _stored(db, f"config:{name}")
        sections[name] = {"value": get_section(db, name), "customized": bool(stored),
                          "updated_at": stored["updated_at"] if stored else None,
                          "updated_by": stored["updated_by"] if stored else None}
    warnings: List[str] = []
    if s.secret_key_ephemeral:
        warnings.append("SECRET_KEY não definido: chaves salvas pela interface ficarão ilegíveis após reiniciar o "
                        "servidor. Defina SECRET_KEY no .env.")
    try:
        from agents.llm.providers import langgraph_available, provider_status
        provider_info = {"providers_status": provider_status(effective_settings(db)), "langgraph": langgraph_available()}
    except Exception:  # noqa: BLE001
        provider_info = {"providers_status": [], "langgraph": False}
    return {"sections": sections, "secrets": secrets_view(db), "providers": PROVIDERS, **provider_info,
            "approver_role_choices": APPROVER_ROLE_CHOICES, "warnings": warnings}
