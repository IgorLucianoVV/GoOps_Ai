Os repositórios de persistência ficam nos pacotes de domínio compartilhados (`goops_core/*`, `data_platform/*`,
`agents/*`), pois são usados tanto pela API quanto pelos agentes e pelo pipeline. A API apenas os orquestra.
