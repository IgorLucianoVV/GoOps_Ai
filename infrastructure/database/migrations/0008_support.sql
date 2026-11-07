-- Atendimento ao Cliente (Desafio 1): caixa unificada de contatos (WhatsApp, e-mail, Reclame Aqui),
-- triagem por agente, veracidade da reclamação, roteamento automático × humano e prevenção de recontato.
CREATE TABLE IF NOT EXISTS support_contacts (
    id TEXT PRIMARY KEY,
    source_key TEXT NOT NULL,
    external_id TEXT NOT NULL,
    channel TEXT NOT NULL,                 -- whatsapp | email | reclameaqui
    customer_id TEXT,
    order_id TEXT,
    order_link TEXT,                        -- texto | cliente | nenhum
    subject TEXT,
    message TEXT NOT NULL,
    attachments TEXT,                       -- JSON: [{type, taken_at}]
    received_at TEXT NOT NULL,
    status TEXT NOT NULL,                   -- new | auto_resolved | pending_human | awaiting_customer | pending_approval | resolved
    intent TEXT,
    intent_confidence REAL,
    intent_source TEXT,                     -- regras | llm
    sentiment TEXT,                         -- positivo | neutro | negativo | muito_negativo
    urgency TEXT,                           -- baixa | media | alta | critica
    priority_score INTEGER,
    is_claim INTEGER NOT NULL DEFAULT 0,
    veracity_score INTEGER,
    veracity_label TEXT,                    -- consistente | inconclusiva | inconsistente | nao_aplicavel
    veracity_factors TEXT,                  -- JSON
    routing TEXT,                           -- auto | human
    routing_reasons TEXT,                   -- JSON
    suggested_actions TEXT,                 -- JSON
    suggested_reply TEXT,
    reply_generated_by TEXT,
    systems_touched TEXT,                   -- JSON: sistemas que o atendimento manual exigiria
    manual_minutes REAL,                    -- tempo manual estimado do contato
    saved_minutes REAL,                     -- tempo poupado pela automação
    is_repeat INTEGER NOT NULL DEFAULT 0,
    repeat_of TEXT,
    contact_number INTEGER NOT NULL DEFAULT 1,
    avoidable INTEGER NOT NULL DEFAULT 0,   -- poderia ter sido evitado (ex.: aviso proativo de atraso)
    avoidable_reason TEXT,
    injection_suspected INTEGER NOT NULL DEFAULT 0,
    assigned_to TEXT,
    resolution TEXT,
    first_response_at TEXT,
    resolved_at TEXT,
    history_simulated INTEGER NOT NULL DEFAULT 0,  -- desfecho histórico simulado (demo)
    is_demo INTEGER NOT NULL DEFAULT 0,
    simulation_truth TEXT,                  -- JSON (somente demo): gabarito para medir a acurácia; nunca usado na triagem
    triaged_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_support_contacts_ext ON support_contacts (source_key, external_id);
CREATE INDEX IF NOT EXISTS ix_support_contacts_status ON support_contacts (status, received_at);
CREATE INDEX IF NOT EXISTS ix_support_contacts_customer ON support_contacts (customer_id, received_at);
CREATE INDEX IF NOT EXISTS ix_support_contacts_order ON support_contacts (order_id);

CREATE TABLE IF NOT EXISTS support_events (
    id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    data TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_support_events_contact ON support_events (contact_id, created_at);

-- Ações operacionais (troca, reenvio, chamado na transportadora...) ligadas a um contato reutilizam a tabela operations
-- (mesmo fluxo de política, aprovação humana, execução simulada e auditoria).
ALTER TABLE operations ADD COLUMN contact_id TEXT;
