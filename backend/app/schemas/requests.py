"""Schemas Pydantic de entrada (validação de payloads)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)
    issue_token: bool = False  # True apenas para clientes de API (o navegador usa cookie httpOnly)


class SourceCreate(BaseModel):
    key: str = Field(min_length=3, max_length=60, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=3, max_length=120)
    entity: Literal["orders", "nps", "deliveries"]
    connector: Literal["http_json", "demo"]
    config: Dict[str, Any] = Field(default_factory=dict)


class SyncRequest(BaseModel):
    full_refresh: bool = False


class PipelineRequest(BaseModel):
    sync: bool = True


class DemoLoadRequest(BaseModel):
    scenario: Literal["gocase", "full", "basic10"] = "gocase"
    reset: bool = True


class Condition(BaseModel):
    field: str
    op: str
    value: Optional[Any] = None


class MetricCreate(BaseModel):
    metric_key: str = Field(min_length=4, max_length=60)
    scope: Literal["corporate", "domain"]
    domain: Optional[str] = None
    name: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=3, max_length=2000)
    formula_text: str = Field(min_length=3, max_length=2000)
    formula_definition: Dict[str, Any]
    unit: str = Field(min_length=1, max_length=60)
    dimensions: List[str] = Field(default_factory=list)
    source_datasets: List[str]
    filters: List[Dict[str, Any]] = Field(default_factory=list)
    owner: str = Field(min_length=2, max_length=120)
    equivalent_to: Optional[str] = None
    related_corporate_metric: Optional[str] = None


class MetricChange(BaseModel):
    changes: Dict[str, Any]
    change_note: str = Field(min_length=5, max_length=2000)


class VersionReview(BaseModel):
    version: str = Field(pattern=r"^\d+\.\d+$")
    approve: bool = True
    note: str = Field(default="", max_length=2000)


class IncidentCreate(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=5, max_length=4000)
    category: Literal["orders", "payments", "inventory", "logistics", "customer_service", "customer_experience", "products"]
    domain: Literal["corporate", "cx", "logistics", "products"]
    severity: Literal["low", "medium", "high", "critical"]


class Decision(BaseModel):
    note: str = Field(default="", max_length=2000)


class CloseRequest(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


class AgentExecute(BaseModel):
    incident_id: Optional[str] = None
    auto_investigate: Optional[bool] = None


class UserCreate(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    name: str = Field(min_length=2, max_length=120)
    role: Literal["admin", "data_owner", "data_steward", "domain_owner", "data_analyst", "viewer"]
    domains: List[str] = Field(default_factory=lambda: ["*"])
    password: str = Field(min_length=8, max_length=200)


class ConfigUpdate(BaseModel):
    value: Dict[str, Any]


class SecretUpdate(BaseModel):
    value: Optional[str] = Field(default=None, max_length=500)


class ModelTest(BaseModel):
    level: int = Field(ge=1, le=3)


class UserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    role: Optional[Literal["admin", "data_owner", "data_steward", "domain_owner", "data_analyst", "viewer"]] = None
    domains: Optional[List[str]] = None
    active: Optional[bool] = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=200)


class DomainCreate(BaseModel):
    key: str = Field(min_length=2, max_length=31, pattern=r"^[a-z][a-z0-9_]+$")
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    owner: Optional[str] = Field(default=None, max_length=120)


class DomainUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    owner: Optional[str] = Field(default=None, max_length=120)
    status: Optional[Literal["active", "planned", "inactive"]] = None


class SourceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=120)
    config: Optional[Dict[str, Any]] = None
    status: Optional[Literal["active", "inactive"]] = None


class RetentionRequest(BaseModel):
    dry_run: bool = True


class MappingSave(BaseModel):
    profile_key: str = Field(min_length=3, max_length=41, pattern=r"^[a-z][a-z0-9_]+$")
    entity: Literal["orders", "nps", "deliveries"]
    definition: Dict[str, Any]
    change_note: str = Field(min_length=5, max_length=500)
    description: str = Field(default="", max_length=300)
    based_on: Optional[str] = Field(default=None, max_length=41)


class MappingPreview(BaseModel):
    entity: Literal["orders", "nps", "deliveries"]
    definition: Dict[str, Any]
    source_key: Optional[str] = None
    sample: Optional[List[Dict[str, Any]]] = None
    limit: int = Field(default=200, ge=1, le=1000)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    history: List[ChatMessage] = Field(default_factory=list)
    model_id: Optional[str] = Field(default=None, max_length=200)


class ModelDiscover(BaseModel):
    provider: str = Field(..., min_length=2, max_length=40, pattern=r"^[a-z_]+$")
