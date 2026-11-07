# Governança de dados

- **Bronze imutável**: arquivos por execução, nunca sobrescritos (`FileExistsError`); reset só via comando explícito de demo, auditado.
- **Data Quality**: regras declarativas e versionadas (`quality/engine.py`). `error` → quarentena (tabela `quarantine` + arquivo); `warning` → `_dq_flags`; `info` → medição. Duplicidades, conflitos de versão, IDs numéricos e órfãos também são medidos.
- **Nada é descartado sem rastreabilidade**: registros inválidos ficam em quarentena com motivo e payload.
- **Deduplicação controlada**: versão mais recente por chave natural; duplicatas exatas e conflitos registrados.
- **Papéis**: Administrator, Data Owner, Data Steward, Domain Owner, Data Analyst, Viewer, AI Agent (ver SECURITY.md).
- **Sensibilidade**: datasets/campos marcados `pii`; colunas `customer_id` e `comment` são mascaradas para papéis sem `data:pii`.
- **Data Dictionary**: curado (`dictionary/catalog.py`) + derivado do schema real a cada pipeline.
- **Auditoria**: `audit_log` append-only para ações de usuários, agentes e sistema (segredos redigidos).
