-- Atendimento conversacional (padrão de mercado: uma conversa contínua por cliente e canal — como no WhatsApp —,
-- com ATENDIMENTOS dentro dela). support_contacts passa a representar o atendimento (unidade de trabalho:
-- triagem, veracidade, ações, SLA); support_messages guarda cada fala (cliente, robô, atendente, sistema, nota interna).
CREATE TABLE IF NOT EXISTS support_conversations (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    handle TEXT NOT NULL,                  -- identidade no canal (telefone, e-mail, consumidor do Reclame Aqui)
    customer_id TEXT,
    status TEXT NOT NULL,                  -- open | closed (há atendimento em aberto?)
    current_case_id TEXT,
    cases_count INTEGER NOT NULL DEFAULT 0,
    last_message_at TEXT,
    last_inbound_at TEXT,
    last_message_preview TEXT,
    last_author_type TEXT,
    unread INTEGER NOT NULL DEFAULT 0,      -- mensagens do cliente desde a última resposta
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_support_conv ON support_conversations (channel, handle);
CREATE INDEX IF NOT EXISTS ix_support_conv_last ON support_conversations (status, last_message_at);

CREATE TABLE IF NOT EXISTS support_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT,
    contact_id TEXT,                        -- atendimento ao qual a fala pertence
    source_key TEXT,
    external_id TEXT,
    direction TEXT NOT NULL,                -- in | out | system
    author_type TEXT NOT NULL,              -- customer | bot | human | system | note
    author TEXT,
    text TEXT NOT NULL,
    attachments TEXT,
    sent_at TEXT NOT NULL,                  -- relógio dos dados (ordem do chat)
    channel TEXT,
    handle TEXT,
    customer_ref TEXT,
    subject TEXT,
    processed INTEGER NOT NULL DEFAULT 1,   -- 0 = mensagem recebida ainda não agrupada/triada
    is_demo INTEGER NOT NULL DEFAULT 0,
    simulation_truth TEXT,
    generated_by TEXT,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_support_msg_ext ON support_messages (source_key, external_id);
CREATE INDEX IF NOT EXISTS ix_support_msg_conv ON support_messages (conversation_id, sent_at);
CREATE INDEX IF NOT EXISTS ix_support_msg_pending ON support_messages (processed, sent_at);

ALTER TABLE support_contacts ADD COLUMN conversation_id TEXT;
ALTER TABLE support_contacts ADD COLUMN case_number INTEGER NOT NULL DEFAULT 1;
ALTER TABLE support_contacts ADD COLUMN message_count INTEGER NOT NULL DEFAULT 1;
ALTER TABLE support_contacts ADD COLUMN chase_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE support_contacts ADD COLUMN follow_up_of TEXT;
ALTER TABLE support_contacts ADD COLUMN last_inbound_at TEXT;
CREATE INDEX IF NOT EXISTS ix_support_contacts_conv ON support_contacts (conversation_id, received_at);
