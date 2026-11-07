"""Papéis, permissões e escopo por domínio/camada/sensibilidade.

Usuários e agentes são representados por um Principal. Agentes recebem permissões
explícitas e mínimas (AGENT_PERMISSIONS) — nunca herdam papel de administrador e
nunca possuem permissões de aprovação ou execução direta de ações críticas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional

from .errors import PermissionDenied

ROLES = ["admin", "data_owner", "data_steward", "domain_owner", "data_analyst", "support_agent", "viewer", "ai_agent"]

ROLE_LABELS = {
    "admin": "Administrador",
    "data_owner": "Responsável pelos dados",
    "data_steward": "Curador de dados",
    "domain_owner": "Responsável pelo domínio",
    "data_analyst": "Analista de dados",
    "support_agent": "Atendente",
    "viewer": "Leitor",
    "ai_agent": "Agente de IA",
}

_READ = {"data:read", "semantic:read", "analytics:read", "incidents:read", "agents:read", "operations:read"}

ROLE_PERMISSIONS = {
    "admin": {"*"},
    "data_owner": _READ | {"support:read", "support:write", "data:write", "data:sync", "data:pii", "semantic:write", "semantic:write_corporate",
                           "semantic:approve", "semantic:approve_corporate", "incidents:write", "operations:approve",
                           "operations:execute", "agents:execute", "agents:configure", "audit:read", "settings:read"},
    "data_steward": _READ | {"support:read", "data:write", "data:sync", "data:pii", "semantic:write", "incidents:write",
                             "audit:read", "settings:read"},
    "domain_owner": _READ | {"support:read", "support:write", "semantic:write", "semantic:approve", "incidents:write", "operations:approve",
                             "operations:execute", "agents:execute", "audit:read", "settings:read"},
    "data_analyst": _READ | {"support:read", "incidents:write", "agents:execute"},
    # Atendente: trabalha a caixa de contatos (responde, propõe ações), mas não aprova ações críticas.
    "support_agent": _READ | {"support:read", "support:write", "incidents:write"},
    "viewer": set(_READ),
    "ai_agent": set(),  # agentes recebem permissões explícitas via AGENT_PERMISSIONS
}

# Permissões mínimas por agente (princípio do menor privilégio).
AGENT_PERMISSIONS = {
    "supervisor": {"incidents:read", "incidents:write", "agents:read", "operations:read"},
    "monitor": {"analytics:read", "data:read", "semantic:read", "incidents:read", "incidents:write"},
    "investigation": {"analytics:read", "data:read", "semantic:read", "incidents:read", "incidents:write"},
    "resolution": {"analytics:read", "incidents:read", "incidents:write", "operations:propose",
                   "operations:execute_approved"},
    "assistant": {"analytics:read", "semantic:read", "incidents:read", "data:read"},  # executa com as permissões do usuário
    "validation": {"analytics:read", "data:read", "semantic:read", "incidents:read", "incidents:write",
                   "operations:read"},
    # Agente de Atendimento: triagem, veracidade, roteamento e resposta informativa. Propõe ações (nunca aprova) e
    # executa apenas as aprovadas ou as que a política dispensa de aprovação (ex.: chamado na transportadora).
    "support": {"analytics:read", "data:read", "support:read", "support:write", "incidents:read", "incidents:write",
                "operations:propose", "operations:execute_approved"},
}

PII_PERMISSION = "data:pii"


@dataclass(frozen=True)
class Principal:
    id: str
    name: str
    kind: str  # user | agent
    role: str
    domains: List[str] = field(default_factory=lambda: ["*"])
    extra_permissions: FrozenSet[str] = frozenset()

    @property
    def actor_label(self) -> str:
        return f"{self.kind}:{self.id}"

    def permissions(self) -> set:
        if self.kind == "agent":
            return set(AGENT_PERMISSIONS.get(self.id, set())) | set(self.extra_permissions)
        return set(ROLE_PERMISSIONS.get(self.role, set())) | set(self.extra_permissions)


def agent_principal(agent_key: str) -> Principal:
    return Principal(id=agent_key, name=f"{agent_key.title()} Agent", kind="agent", role="ai_agent",
                     domains=["corporate", "cx", "logistics", "products", "atendimento"])


SYSTEM_PRINCIPAL = Principal(id="system", name="GoOps System", kind="system", role="admin", domains=["*"])


def can_access_domain(principal: Principal, domain: Optional[str]) -> bool:
    if domain in (None, "", "corporate"):
        return True
    return "*" in principal.domains or domain in principal.domains


def has_permission(principal: Principal, permission: str, domain: Optional[str] = None) -> bool:
    """Verifica permissão e, quando um domínio é informado, o escopo de domínio do principal."""
    perms = principal.permissions()
    if "*" not in perms and permission not in perms:
        return False
    if domain is None:
        return True
    return can_access_domain(principal, domain)


def require_permission(principal: Principal, permission: str, domain: Optional[str] = None) -> None:
    if not has_permission(principal, permission, domain):
        scope = f" no domínio '{domain}'" if domain else ""
        raise PermissionDenied(f"{principal.actor_label} não possui a permissão '{permission}'{scope}.")
