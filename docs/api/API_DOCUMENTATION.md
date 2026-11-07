# API interna — GoOps AI

Base: `/api` · OpenAPI interativo: `/api/docs` · JSON: `/api/openapi.json`

**Envelope**: sucesso `{"data": ..., "meta": {...}}`; erro `{"error": {"code", "message", "details"}}`.
Códigos: 401 autenticação, 403 permissão/política, 404 não encontrado, 409 conflito ou dados ainda não processados, 422 validação, 429 rate limit.
**Autenticação**: `POST /api/auth/login` define cookie httpOnly `goops_session` e cookie `goops_csrf`; requisições POST via navegador devem enviar `X-CSRF-Token`. Clientes de API: `{"issue_token": true}` no login e `Authorization: Bearer <token>`.
**Filtros NPS** (query): `start`, `end` (AAAA-MM-DD), `state`, `product_line`, `carrier`, `shipping_type` (repetíveis).
Rotas de execução de ações são **simuladas** (`execution_mode: simulated`).

| Método | Rota | Permissão | Handler |
|---|---|---|---|
| GET | `/api/health` | pública | `core.health` |
| POST | `/api/auth/login` | pública | `core.login` |
| POST | `/api/auth/logout` | pública | `core.logout` |
| GET | `/api/auth/me` | autenticado (verificação interna) | `core.me` |
| POST | `/api/auth/password` | autenticado (verificação interna) | `core.change_own_password` |
| GET | `/api/overview` | analytics:read | `core.overview` |
| GET | `/api/audit` | audit:read | `core.audit` |
| GET | `/api/settings` | settings:read | `core.settings_view` |
| GET | `/api/settings/config` | settings:read | `core.config_get` |
| POST | `/api/settings/config/{section}` | settings:write | `core.config_update` |
| POST | `/api/settings/config/{section}/reset` | settings:write | `core.config_reset` |
| POST | `/api/settings/secrets/{name}` | settings:write | `core.secret_update` |
| POST | `/api/settings/models/test` | settings:write | `core.model_test` |
| GET | `/api/settings/users` | settings:read | `core.users` |
| POST | `/api/settings/users` | settings:write | `core.users_create` |
| POST | `/api/settings/users/{user_id}` | settings:write | `core.users_update` |
| POST | `/api/settings/users/{user_id}/password` | settings:write | `core.users_password` |
| POST | `/api/settings/domains` | settings:write | `core.domains_create` |
| POST | `/api/settings/domains/{key}` | settings:write | `core.domains_update` |
| GET | `/api/scheduler` | settings:read | `core.scheduler` |
| POST | `/api/scheduler/run/{job}` | autenticado (verificação interna) | `core.scheduler_run` |
| GET | `/api/sources` | data:read | `data.sources` |
| POST | `/api/sources` | data:write | `data.sources_create` |
| GET | `/api/sources/{source_id}` | data:read | `data.source_detail` |
| POST | `/api/sources/{source_id}` | data:write | `data.source_update` |
| POST | `/api/sources/{source_id}/cursor/reset` | data:write | `data.source_cursor_reset` |
| POST | `/api/sources/{source_id}/test` | data:read | `data.source_test` |
| POST | `/api/sources/{source_id}/sync` | data:sync | `data.source_sync` |
| GET | `/api/data/ingestion-runs` | data:read | `data.ingestion_runs` |
| GET | `/api/data/layers` | data:read | `data.layers` |
| GET | `/api/data/datasets` | data:read | `data.datasets` |
| GET | `/api/data/datasets/{key}` | data:read | `data.dataset_detail` |
| GET | `/api/data/quality` | data:read | `data.quality` |
| GET | `/api/data/quality/quarantine` | data:read | `data.quarantine` |
| GET | `/api/data/lineage` | data:read | `data.lineage` |
| GET | `/api/data/dictionary` | data:read | `data.dictionary` |
| POST | `/api/data/pipeline/run` | data:sync | `data.pipeline_run` |
| GET | `/api/data/pipeline/runs` | data:read | `data.pipeline_runs` |
| POST | `/api/data/retention` | data:write | `data.retention` |
| POST | `/api/demo/load` | settings:write | `data.demo_load` |
| GET | `/api/mapping/schema` | data:read | `data.mapping_schema` |
| GET | `/api/mapping/profiles` | data:read | `data.mapping_profiles` |
| POST | `/api/mapping/profiles` | data:write | `data.mapping_save` |
| GET | `/api/mapping/profiles/{profile_key}/{entity}/versions` | data:read | `data.mapping_versions` |
| POST | `/api/mapping/preview` | data:read | `data.mapping_preview` |
| GET | `/api/semantic/metrics` | semantic:read | `semantic.metrics` |
| POST | `/api/semantic/metrics` | semantic:read | `semantic.metrics_create` |
| GET | `/api/semantic/metrics/{key}` | semantic:read | `semantic.metric_detail` |
| GET | `/api/semantic/metrics/{key}/versions` | semantic:read | `semantic.metric_versions` |
| POST | `/api/semantic/metrics/{key}/versions` | semantic:read | `semantic.metric_propose` |
| POST | `/api/semantic/metrics/{key}/approve` | semantic:read | `semantic.metric_approve` |
| GET | `/api/semantic/metrics/{key}/value` | analytics:read | `semantic.metric_value` |
| GET | `/api/semantic/metrics/{key}/explain` | semantic:read | `semantic.metric_explain` |
| GET | `/api/semantic/approvals` | semantic:read | `semantic.approvals` |
| GET | `/api/semantic/domains` | semantic:read | `semantic.domains` |
| GET | `/api/semantic/audit` | audit:read | `semantic.semantic_audit` |
| GET | `/api/analytics/nps/overview` | analytics:read | `analytics.nps_overview` |
| GET | `/api/analytics/nps/evolution` | analytics:read | `analytics.nps_evolution` |
| GET | `/api/analytics/nps/distribution` | analytics:read | `analytics.nps_distribution` |
| GET | `/api/analytics/nps/by-state` | analytics:read | `analytics.nps_by_state` |
| GET | `/api/analytics/nps/by-product` | analytics:read | `analytics.nps_by_product` |
| GET | `/api/analytics/nps/by-carrier` | analytics:read | `analytics.nps_by_carrier` |
| GET | `/api/analytics/nps/correlation` | analytics:read | `analytics.nps_correlation` |
| GET | `/api/analytics/nps/comments` | analytics:read | `analytics.nps_comments` |
| GET | `/api/analytics/nps/filters` | analytics:read | `analytics.nps_filter_options` |
| GET | `/api/analytics/cx` | analytics:read | `analytics.cx` |
| GET | `/api/analytics/logistics` | analytics:read | `analytics.logistics` |
| GET | `/api/analytics/products` | analytics:read | `analytics.products` |
| GET | `/api/analytics/regional` | analytics:read | `analytics.regional` |
| GET | `/api/incidents` | incidents:read | `ops.incidents` |
| POST | `/api/incidents` | incidents:write | `ops.incidents_create` |
| GET | `/api/incidents/{incident_id}` | incidents:read | `ops.incident_detail` |
| GET | `/api/incidents/{incident_id}/timeline` | incidents:read | `ops.incident_timeline` |
| POST | `/api/incidents/{incident_id}/investigate` | agents:execute | `ops.incident_investigate` |
| POST | `/api/incidents/{incident_id}/approve` | operations:approve | `ops.incident_approve` |
| POST | `/api/incidents/{incident_id}/reject` | operations:approve | `ops.incident_reject` |
| POST | `/api/incidents/{incident_id}/close` | incidents:write | `ops.incident_close` |
| GET | `/api/agents` | agents:read | `ops.agents` |
| GET | `/api/agents/routing/metrics` | agents:read | `ops.routing_metrics` |
| GET | `/api/agents/custom` | agents:read | `ops.custom_agents` |
| GET | `/api/agents/custom/options` | agents:read | `ops.custom_agent_options` |
| POST | `/api/agents/custom` | agents:execute + semantic:write no setor | `ops.custom_agent_save` |
| GET | `/api/agents/custom/{key}` | agents:read | `ops.custom_agent_detail` |
| POST | `/api/agents/custom/{key}/run` | agents:execute | `ops.custom_agent_run` |
| POST | `/api/agents/custom/{key}/delete` | semantic:write no setor | `ops.custom_agent_delete` |
| GET | `/api/agents/instructions/{slot}/history` | agents:read | `ops.instruction_history` |
| POST | `/api/agents/instructions/{slot}` | agents:configure | `ops.instruction_save` (publica direto; a UI usa rascunho) |
| POST | `/api/agents/instructions/{slot}/draft` | agents:configure | `ops.instruction_draft` |
| POST | `/api/agents/instructions/{slot}/draft/discard` | agents:configure | `ops.instruction_draft_discard` |
| POST | `/api/agents/instructions/{slot}/test` | agents:configure | `ops.instruction_test` |
| POST | `/api/agents/instructions/{slot}/publish` | agents:configure | `ops.instruction_publish` |
| POST | `/api/agents/custom/test` | agents:execute + semantic:write no setor | `ops.custom_agent_test` (sem efeito colateral) |
| POST | `/api/agents/custom/{key}/enabled` | semantic:write no setor | `ops.custom_agent_enabled` |
| POST | `/api/agents/instructions/{slot}/reset` | agents:configure | `ops.instruction_reset` |
| POST | `/api/agents/instructions/{slot}/restore` | agents:configure | `ops.instruction_restore` |
| GET | `/api/agents/{agent_key}` | agents:read | `ops.agent_detail` |
| GET | `/api/agents/{agent_key}/runs` | agents:read | `ops.agent_runs` |
| POST | `/api/agents/{agent_key}/execute` | agents:execute | `ops.agent_execute` |
| GET | `/api/workflows` | agents:read | `ops.workflows` |
| GET | `/api/operations` | operations:read | `ops.operations` |
| POST | `/api/operations/{operation_id}/approve` | operations:approve | `ops.operation_approve` |
| POST | `/api/operations/{operation_id}/reject` | operations:approve | `ops.operation_reject` |
| POST | `/api/operations/{operation_id}/execute` | operations:execute | `ops.operation_execute` |
| GET | `/api/operations/{operation_id}/history` | operations:read | `ops.operation_hist` |
