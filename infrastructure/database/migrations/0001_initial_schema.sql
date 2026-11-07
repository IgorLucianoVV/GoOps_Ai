-- GoOps AI - schema inicial de metadados (compatível com SQLite e PostgreSQL)
-- Convenções: ids TEXT gerados pela aplicação; datas ISO-8601 em TEXT; JSON em TEXT; flags INTEGER 0/1.

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    domains TEXT NOT NULL DEFAULT '["*"]',
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    details TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_entity ON audit_log (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_log (ts);

CREATE TABLE IF NOT EXISTS domains (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    owner TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    entity TEXT NOT NULL,
    connector TEXT NOT NULL,
    config TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    cursor TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_sync_at TEXT
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id TEXT PRIMARY KEY,
    source_key TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    records_ingested INTEGER NOT NULL DEFAULT 0,
    records_failed INTEGER NOT NULL DEFAULT 0,
    pages INTEGER NOT NULL DEFAULT 0,
    schema_version TEXT,
    bronze_path TEXT,
    cursor_before TEXT,
    cursor_after TEXT,
    error TEXT,
    triggered_by TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_ingestion_source ON ingestion_runs (source_key, started_at);

CREATE TABLE IF NOT EXISTS ingestion_failures (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_key TEXT NOT NULL,
    record_ref TEXT,
    error TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    triggered_by TEXT NOT NULL,
    steps TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS datasets (
    key TEXT PRIMARY KEY,
    layer TEXT NOT NULL,
    scope TEXT NOT NULL,
    domain TEXT,
    name TEXT NOT NULL,
    description TEXT,
    grain TEXT,
    path TEXT,
    format TEXT,
    row_count INTEGER,
    schema_def TEXT,
    schema_version TEXT,
    sensitivity TEXT NOT NULL DEFAULT 'internal',
    is_demo INTEGER NOT NULL DEFAULT 0,
    last_built_at TEXT,
    last_pipeline_run_id TEXT
);

CREATE TABLE IF NOT EXISTS transformations (
    id TEXT PRIMARY KEY,
    pipeline_run_id TEXT,
    dataset_key TEXT NOT NULL,
    inputs TEXT NOT NULL,
    transform TEXT NOT NULL,
    rule_version TEXT,
    rows_in INTEGER,
    rows_out INTEGER,
    executed_at TEXT NOT NULL,
    actor TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_transformations_dataset ON transformations (dataset_key, executed_at);

CREATE TABLE IF NOT EXISTS lineage_edges (
    id TEXT PRIMARY KEY,
    upstream TEXT NOT NULL,
    downstream TEXT NOT NULL,
    transform TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (upstream, downstream)
);

CREATE TABLE IF NOT EXISTS dq_rules (
    rule_key TEXT PRIMARY KEY,
    dataset TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    version TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS dq_results (
    id TEXT PRIMARY KEY,
    pipeline_run_id TEXT NOT NULL,
    rule_key TEXT NOT NULL,
    dataset TEXT NOT NULL,
    severity TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    checked INTEGER NOT NULL,
    failed INTEGER NOT NULL,
    status TEXT NOT NULL,
    sample TEXT,
    executed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_dq_results_run ON dq_results (pipeline_run_id);

CREATE TABLE IF NOT EXISTS quarantine (
    id TEXT PRIMARY KEY,
    pipeline_run_id TEXT NOT NULL,
    dataset TEXT NOT NULL,
    record_key TEXT,
    reasons TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_quarantine_run ON quarantine (pipeline_run_id, dataset);

CREATE TABLE IF NOT EXISTS data_dictionary (
    id TEXT PRIMARY KEY,
    dataset_key TEXT NOT NULL,
    field TEXT NOT NULL,
    business_name TEXT NOT NULL,
    description TEXT,
    data_type TEXT NOT NULL,
    origin TEXT,
    format TEXT,
    required INTEGER NOT NULL DEFAULT 0,
    validation TEXT,
    relationships TEXT,
    sensitivity TEXT NOT NULL DEFAULT 'internal',
    UNIQUE (dataset_key, field)
);

CREATE TABLE IF NOT EXISTS semantic_metrics (
    id TEXT PRIMARY KEY,
    metric_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    formula_text TEXT NOT NULL,
    formula_definition TEXT NOT NULL,
    unit TEXT NOT NULL,
    scope TEXT NOT NULL,
    domain TEXT,
    dimensions TEXT NOT NULL,
    source_datasets TEXT NOT NULL,
    filters TEXT,
    equivalent_to TEXT,
    related_corporate_metric TEXT,
    version TEXT NOT NULL,
    status TEXT NOT NULL,
    owner TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS semantic_metric_versions (
    id TEXT PRIMARY KEY,
    metric_key TEXT NOT NULL,
    version TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    change_note TEXT,
    status TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    proposed_at TEXT NOT NULL,
    reviewed_by TEXT,
    reviewed_at TEXT,
    review_note TEXT,
    UNIQUE (metric_key, version)
);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    domain TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    source TEXT NOT NULL,
    fingerprint TEXT,
    signal TEXT,
    related_metrics TEXT,
    evidence TEXT,
    agents TEXT,
    root_cause TEXT,
    hypotheses TEXT,
    recommendation TEXT,
    result TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_incidents_status ON incidents (status, severity);

CREATE TABLE IF NOT EXISTS incident_events (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    ts TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    data TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_incident_events ON incident_events (incident_id, seq);

CREATE TABLE IF NOT EXISTS operations (
    id TEXT PRIMARY KEY,
    incident_id TEXT,
    action_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    params TEXT,
    impacted_areas TEXT,
    risk TEXT NOT NULL,
    expected_impact TEXT,
    requires_approval INTEGER NOT NULL,
    approver_roles TEXT,
    status TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    approved_by TEXT,
    approved_at TEXT,
    decision_note TEXT,
    executed_by TEXT,
    executed_at TEXT,
    execution_mode TEXT,
    result TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_operations_status ON operations (status);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id TEXT PRIMARY KEY,
    workflow TEXT NOT NULL,
    incident_id TEXT,
    status TEXT NOT NULL,
    current_node TEXT,
    state TEXT,
    steps TEXT,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    agent_key TEXT NOT NULL,
    incident_id TEXT,
    workflow_run_id TEXT,
    task TEXT,
    status TEXT NOT NULL,
    input TEXT,
    output TEXT,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    cost_usd REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_agent_runs ON agent_runs (agent_key, started_at);

CREATE TABLE IF NOT EXISTS routing_decisions (
    id TEXT PRIMARY KEY,
    agent_run_id TEXT,
    agent_key TEXT NOT NULL,
    task TEXT NOT NULL,
    requested_level INTEGER NOT NULL,
    used_level INTEGER NOT NULL,
    used_llm INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id TEXT PRIMARY KEY,
    agent_run_id TEXT,
    agent_key TEXT NOT NULL,
    task TEXT NOT NULL,
    level INTEGER NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    latency_ms INTEGER,
    success INTEGER NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL
);
