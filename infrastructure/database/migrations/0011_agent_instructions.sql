-- GoOps AI: instruções de IA editáveis dos agentes nativos (versionadas; a versão mais recente é a vigente)
CREATE TABLE IF NOT EXISTS agent_instructions (
    id TEXT PRIMARY KEY,
    slot TEXT NOT NULL,
    version INTEGER NOT NULL,
    text TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_agent_instructions_slot_version ON agent_instructions (slot, version);
