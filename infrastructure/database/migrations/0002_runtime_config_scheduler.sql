-- GoOps AI v2: configuração em tela, agendador, retenção, rate limit compartilhado
ALTER TABLE incidents ADD COLUMN summary TEXT;
ALTER TABLE ingestion_runs ADD COLUMN purged_at TEXT;
ALTER TABLE users ADD COLUMN updated_at TEXT;
ALTER TABLE sources ADD COLUMN updated_at TEXT;

CREATE TABLE IF NOT EXISTS scheduler_runs (
    id TEXT PRIMARY KEY,
    job TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    triggered_by TEXT NOT NULL,
    output TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS ix_scheduler_runs ON scheduler_runs (job, started_at);

CREATE TABLE IF NOT EXISTS rate_limit_hits (
    bucket TEXT PRIMARY KEY,
    hits INTEGER NOT NULL,
    window_start TEXT NOT NULL
);
