-- GoOps AI: perfis de mapeamento Fonte -> Silver editáveis pela interface (versionados)
CREATE TABLE IF NOT EXISTS mapping_profiles (
    id TEXT PRIMARY KEY,
    profile_key TEXT NOT NULL,
    entity TEXT NOT NULL,
    version INTEGER NOT NULL,
    definition TEXT NOT NULL,
    description TEXT,
    based_on TEXT,
    updated_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (profile_key, entity)
);

CREATE TABLE IF NOT EXISTS mapping_profile_versions (
    id TEXT PRIMARY KEY,
    profile_key TEXT NOT NULL,
    entity TEXT NOT NULL,
    version INTEGER NOT NULL,
    definition TEXT NOT NULL,
    change_note TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (profile_key, entity, version)
);
