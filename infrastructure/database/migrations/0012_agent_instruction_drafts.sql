-- GoOps AI: rascunho de instrução de IA (um por tarefa). Só vale para os agentes depois de "Publicar".
CREATE TABLE IF NOT EXISTS agent_instruction_drafts (
    slot TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    note TEXT,
    last_test TEXT,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
