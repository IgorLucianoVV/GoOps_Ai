# Arquitetura

```
L0 Sources ─► L1 Bronze ─► L2 Silver ─► L3 Corporate Gold ─► L3 Domain Gold ─► L4 Semantic & Intelligence
 (conectores)  (JSONL       (normalização,   (base corporativa,     (CX, Logística,      (Metric Registry,
               append-only)  DQ, quarentena)  grão explícito)        Produtos)            agentes, incidentes)
```

## Componentes
| Pacote | Responsabilidade |
|---|---|
| `goops_core/` | Kernel compartilhado: config, banco de metadados (SQLite/PostgreSQL), migrações, segurança, permissões, políticas, auditoria, incidentes e operações |
| `data_platform/` | Conectores, ingestão, Bronze/Silver/Gold, Data Quality, Lineage, Dictionary, Semantic Registry, Analytics (NPS, NLP, estatística), pipeline, gerador de demo |
| `agents/` | Supervisor, Monitor, Investigation, Resolution, Validation, ferramentas governadas, Intelligent Cost Routing, grafo de workflow |
| `backend/app/` | API FastAPI (rotas finas sobre os serviços acima), autenticação, rate limit, tratamento de erros |
| `frontend/` | Next.js 14 + TypeScript + Tailwind + Recharts; consome exclusivamente a API |
| `infrastructure/` | Migrações SQL, Dockerfiles, scripts |

## Fluxos principais
1. **Pipeline** (`data_platform/pipelines/runner.py`): ingestion → silver → data_quality → gold_corporate → gold_domain → semantic → dictionary. Cada etapa é registrada em `pipeline_runs`.
2. **Ciclo operacional** (`agents/supervisor`): Monitor detecta → Supervisor prioriza → grafo `incident_resolution` (validate_inputs → investigate → plan_resolution → ⏸ await_approval → execute → validate_outcome → finalize).
3. **Indicadores**: o frontend nunca calcula; toda métrica passa por `semantic.registry.compute_metric` usando a definição ativa do catálogo.

## Armazenamento
- **Metadados/operação**: PostgreSQL (Docker) ou SQLite (dev/testes) com o mesmo SQL parametrizado.
- **Analítico**: Parquet (pyarrow) — fallback CSV + schema sidecar quando pyarrow não está disponível. Interface `Lakehouse` preparada para Iceberg/Delta.

## Extensibilidade
- Nova fonte: registrar em *Sources* (conector `http_json`) ou implementar `BaseConnector`.
- Nova entidade: adicionar mapeamento em `silver/mappings.py`, regras em `quality/engine.py`, builders Gold.
- Novo domínio: inserir em `domains`, criar builders em `gold/domains`, métricas de domínio no registry (Finance já está preparado como `planned`).
