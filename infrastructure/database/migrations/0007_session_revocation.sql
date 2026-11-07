-- Revogação de sessões: versão do token por usuário (troca de senha, papel ou desativação invalida tokens antigos)
-- e lista de sessões encerradas no logout (até expirarem).
ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS revoked_sessions (
    sid TEXT PRIMARY KEY,
    expires_at INTEGER NOT NULL,
    revoked_at TEXT NOT NULL
);
