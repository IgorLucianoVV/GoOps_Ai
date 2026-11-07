-- GoOps AI: setores dinâmicos — conjuntos de dados configuráveis, painéis e agentes criados pela interface
CREATE TABLE IF NOT EXISTS custom_datasets (
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    definition TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dashboards (
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    name TEXT NOT NULL,
    widgets TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_by TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_agents (
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    name TEXT NOT NULL,
    template TEXT NOT NULL,
    config TEXT NOT NULL,
    interval_minutes INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    last_status TEXT,
    last_result TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
