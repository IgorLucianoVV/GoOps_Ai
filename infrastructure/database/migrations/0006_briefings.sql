-- GoOps AI: briefing diário automático (entrega em canais em modo simulado)
CREATE TABLE IF NOT EXISTS briefings (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    triggered_by TEXT NOT NULL,
    content_md TEXT NOT NULL,
    narrative_md TEXT,
    generated_by TEXT NOT NULL,
    data TEXT,
    deliveries TEXT
);
CREATE INDEX IF NOT EXISTS ix_briefings_created ON briefings (created_at);
