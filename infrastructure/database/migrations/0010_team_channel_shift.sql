-- Agente como colega de trabalho: canal do time (app, Telegram ou Slack), vínculo de usuários ao canal,
-- resumo do caso para quem assume e controles do turno autônomo do Agente de Atendimento.
CREATE TABLE IF NOT EXISTS team_messages (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,                     -- approval_request | approval_reminder | sla | incident | digest | info | reply
    text TEXT NOT NULL,
    operation_id TEXT,
    contact_id TEXT,
    incident_id TEXT,
    provider TEXT NOT NULL,                 -- app | telegram | slack
    delivery TEXT NOT NULL,                 -- delivered | failed | app_only
    delivery_error TEXT,
    external_ref TEXT,                      -- id da mensagem no Telegram (para editar após a decisão)
    dedupe_key TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_team_messages_created ON team_messages (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS ux_team_messages_dedupe ON team_messages (dedupe_key);

CREATE TABLE IF NOT EXISTS team_links (
    user_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    external_user TEXT,                     -- id do usuário no Telegram
    link_code TEXT,
    code_expires_at TEXT,
    linked_at TEXT
);

ALTER TABLE support_contacts ADD COLUMN case_summary TEXT;
ALTER TABLE support_contacts ADD COLUMN summary_generated_by TEXT;
