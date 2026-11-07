"""Health, autenticação, overview, auditoria, configurações (editáveis em tela) e agendador."""
from __future__ import annotations

import secrets as pysecrets

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Query, Response

from goops_core.audit import list_audit, record_audit
from goops_core.config import get_settings
from goops_core.db import Database
from goops_core.permissions import AGENT_PERMISSIONS, ROLE_LABELS, ROLE_PERMISSIONS, Principal
from goops_core.policies import ACTION_CATALOG, CRITICAL_AREAS, evaluate_action_policy
from goops_core.runtime_config import config_view, get_section, reset_section, set_secret, update_section
from goops_core.users import authenticate, create_user, list_users, reset_password, revoke_session, update_user
from data_platform.semantic.registry import create_domain, list_domains, update_domain
from data_platform.storage import Lakehouse
from agents.routing.router import efficiency_metrics, test_model
from agents.scheduler import scheduler_status, trigger

from ...schemas.requests import (ConfigUpdate, DomainCreate, DomainUpdate, LoginRequest, ModelDiscover, ModelTest, PasswordReset,
                                 SecretUpdate, UserCreate, UserUpdate)
from ...services.overview import build_overview
from ..deps import CSRF_COOKIE, SESSION_COOKIE, current_principal, db_dep, lake_dep, ok, require

router = APIRouter()


@router.get("/health", tags=["health"])
def health(db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)):
    s = get_settings()
    return ok({"status": "ok", "env": s.app_env, "database": db.health(), "storage_format": lake.format,
               "demo_mode": s.demo_mode, "execution_mode": s.action_execution_mode})


@router.post("/auth/login", tags=["auth"])
def login(body: LoginRequest, response: Response, db: Database = Depends(db_dep)):
    s = get_settings()
    result = authenticate(db, body.email, body.password)
    csrf = pysecrets.token_urlsafe(24)
    max_age = s.token_ttl_minutes * 60
    response.set_cookie(SESSION_COOKIE, result["access_token"], max_age=max_age, httponly=True, samesite="lax",
                        secure=s.is_production, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, samesite="lax", secure=s.is_production,
                        path="/")
    data = {"user": result["user"], "csrf_token": csrf}
    if body.issue_token:
        data["access_token"], data["token_type"] = result["access_token"], "bearer"
    return ok(data)


@router.post("/auth/logout", tags=["auth"])
def logout(response: Response, goops_session: Optional[str] = Cookie(default=None), db: Database = Depends(db_dep)):
    revoke_session(db, goops_session)   # o token deixa de valer no servidor, não só no navegador
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return ok({"logged_out": True})


@router.get("/auth/me", tags=["auth"])
def me(p: Principal = Depends(current_principal)):
    return ok({"id": p.id, "name": p.name, "role": p.role, "role_label": ROLE_LABELS.get(p.role), "domains": p.domains,
               "permissions": sorted(p.permissions())})


@router.post("/auth/password", tags=["auth"])
def change_own_password(body: PasswordReset, p: Principal = Depends(current_principal), db: Database = Depends(db_dep)):
    return ok(reset_password(db, p, p.id, body.password))


@router.get("/overview", tags=["overview"])
def overview(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep),
             lake: Lakehouse = Depends(lake_dep)):
    return ok(build_overview(db, lake, p))


@router.get("/audit", tags=["audit"])
def audit(entity_type: str = Query(default=None), entity_id: str = Query(default=None),
          actor_id: str = Query(default=None), limit: int = Query(default=200, ge=1, le=1000),
          p: Principal = Depends(require("audit:read")), db: Database = Depends(db_dep)):
    return ok(list_audit(db, entity_type, entity_id, actor_id, limit))


# ------------------------------------------------------------------ settings (visão geral)
@router.get("/settings", tags=["settings"])
def settings_view(p: Principal = Depends(require("settings:read")), db: Database = Depends(db_dep)):
    s = get_settings()
    overrides = get_section(db, "policies")
    return ok({
        "environment": {"app_env": s.app_env, "demo_mode": s.demo_mode, "storage_format": s.storage_format,
                        "execution_mode": s.action_execution_mode, "secret_key_ephemeral": s.secret_key_ephemeral,
                        "database_dialect": db.dialect},
        "roles": [{"role": r, "label": ROLE_LABELS[r], "permissions": sorted(ROLE_PERMISSIONS.get(r, set()))}
                  for r in ROLE_LABELS],
        "agent_permissions": {k: sorted(v) for k, v in AGENT_PERMISSIONS.items()},
        "domains": list_domains(db),
        "routing": efficiency_metrics(db),
        "policies": {"critical_areas": sorted(CRITICAL_AREAS),
                     "actions": [{"action_type": k, "title": v["title"], **evaluate_action_policy(k, overrides)}
                                 for k, v in ACTION_CATALOG.items()]},
    })


# ------------------------------------------------------------------ configuração em tela
@router.get("/settings/config", tags=["settings"])
def config_get(p: Principal = Depends(require("settings:read")), db: Database = Depends(db_dep)):
    return ok(config_view(db))


@router.post("/settings/config/{section}", tags=["settings"])
def config_update(section: str, body: ConfigUpdate, p: Principal = Depends(require("settings:write")),
                  db: Database = Depends(db_dep)):
    out = update_section(db, p, section, body.value)
    if section == "features":
        from data_platform.ingestion.service import apply_features
        apply_features(db)
    return ok(out)


@router.get("/features", tags=["settings"])
def features(p: Principal = Depends(current_principal), db: Database = Depends(db_dep)):
    """Recursos opcionais ligados (para a interface mostrar/ocultar)."""
    v = get_section(db, "features")
    return ok({k: v[k] for k in ("sector_stock", "whatif", "briefing_enabled", "briefing_ai")})


@router.post("/settings/config/{section}/reset", tags=["settings"])
def config_reset(section: str, p: Principal = Depends(require("settings:write")), db: Database = Depends(db_dep)):
    return ok(reset_section(db, p, section))


@router.post("/settings/secrets/{name}", tags=["settings"])
def secret_update(name: str, body: SecretUpdate, p: Principal = Depends(require("settings:write")),
                  db: Database = Depends(db_dep)):
    return ok(set_secret(db, p, name, body.value))


@router.post("/settings/models/test", tags=["settings"])
def model_test(body: ModelTest, p: Principal = Depends(require("settings:write")), db: Database = Depends(db_dep)):
    result = test_model(db, body.level)
    record_audit(db, p, "settings.model_test", "settings", f"level_{body.level}", {"ok": result.get("ok")})
    return ok(result)


@router.post("/settings/models/discover", tags=["settings"])
def model_discover(body: ModelDiscover, p: Principal = Depends(require("settings:write")), db: Database = Depends(db_dep)):
    """Busca no provedor a lista de modelos visíveis para a chave cadastrada (fallback: catálogo de referência)."""
    from agents.llm.providers import discover_models
    from goops_core.runtime_config import effective_settings
    result = discover_models(body.provider, effective_settings(db))
    record_audit(db, p, "settings.model_discover", "settings", body.provider,
                 {"source": result["source"], "count": len(result["models"])})
    return ok(result)


# ------------------------------------------------------------------ usuários e domínios
@router.get("/settings/users", tags=["settings"])
def users(p: Principal = Depends(require("settings:read")), db: Database = Depends(db_dep)):
    return ok(list_users(db))


@router.post("/settings/users", tags=["settings"], status_code=201)
def users_create(body: UserCreate, p: Principal = Depends(require("settings:write")), db: Database = Depends(db_dep)):
    return ok(create_user(db, p, body.email, body.name, body.role, body.domains, body.password))


@router.post("/settings/users/{user_id}", tags=["settings"])
def users_update(user_id: str, body: UserUpdate, p: Principal = Depends(require("settings:write")),
                 db: Database = Depends(db_dep)):
    return ok(update_user(db, p, user_id, name=body.name, role=body.role, domains=body.domains, active=body.active))


@router.post("/settings/users/{user_id}/password", tags=["settings"])
def users_password(user_id: str, body: PasswordReset, p: Principal = Depends(require("settings:write")),
                   db: Database = Depends(db_dep)):
    return ok(reset_password(db, p, user_id, body.password))


@router.post("/settings/domains", tags=["settings"], status_code=201)
def domains_create(body: DomainCreate, p: Principal = Depends(require("settings:write")), db: Database = Depends(db_dep)):
    return ok(create_domain(db, p, body.key, body.name, body.description, body.owner))


@router.post("/settings/domains/{key}", tags=["settings"])
def domains_update(key: str, body: DomainUpdate, p: Principal = Depends(require("settings:write")),
                   db: Database = Depends(db_dep)):
    return ok(update_domain(db, p, key, body.name, body.description, body.owner, body.status))


# ------------------------------------------------------------------ agendador
@router.get("/scheduler", tags=["scheduler"])
def scheduler(p: Principal = Depends(require("settings:read")), db: Database = Depends(db_dep)):
    return ok(scheduler_status(db))


@router.post("/scheduler/run/{job}", tags=["scheduler"])
def scheduler_run(job: str, p: Principal = Depends(current_principal), db: Database = Depends(db_dep),
                  lake: Lakehouse = Depends(lake_dep)):
    return ok(trigger(db, lake, p, job))
