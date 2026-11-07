"""Usuários, autenticação e seed de usuários de demonstração."""
from __future__ import annotations

import secrets
import time
from typing import List, Optional

from .audit import record_audit
from .config import ROOT_DIR, get_settings
from .db import Database
from .errors import AuthenticationError, Conflict, NotFound, ValidationError
from .permissions import ROLES, SYSTEM_PRINCIPAL, Principal, require_permission
from .security import create_token, decode_token, hash_password, verify_password
from .util import jdump, jload, new_id, now_iso

DEMO_USERS = [
    ("admin@goops.local", "Administrador (demo)", "admin", ["*"]),
    ("owner@goops.local", "Responsável pelos dados (demo)", "data_owner", ["*"]),
    ("steward@goops.local", "Curador de dados (demo)", "data_steward", ["*"]),
    ("cx.owner@goops.local", "Responsável pelo domínio CX (demo)", "domain_owner", ["cx"]),
    ("logistics.owner@goops.local", "Responsável pelo domínio Logística (demo)", "domain_owner", ["logistics"]),
    ("analyst@goops.local", "Analista de dados (demo)", "data_analyst", ["cx", "logistics", "products"]),
    ("atendimento.owner@goops.local", "Responsável pelo Atendimento (demo)", "domain_owner", ["atendimento", "cx"]),
    ("atendente@goops.local", "Atendente (demo)", "support_agent", ["atendimento", "cx", "logistics"]),
    ("viewer@goops.local", "Leitor (demo)", "viewer", ["*"]),
]


def _public(row: dict) -> dict:
    return {"id": row["id"], "email": row["email"], "name": row["name"], "role": row["role"],
            "domains": jload(row["domains"], ["*"]), "active": bool(row["active"]), "is_demo": bool(row["is_demo"]),
            "created_at": row["created_at"]}


def to_principal(row: dict) -> Principal:
    return Principal(id=row["id"], name=row["name"], kind="user", role=row["role"], domains=jload(row["domains"], ["*"]))


def create_user(db: Database, actor: Principal, email: str, name: str, role: str, domains: List[str],
                password: str, is_demo: bool = False) -> dict:
    if actor.kind != "system":
        require_permission(actor, "settings:write")
    if role not in ROLES or role == "ai_agent":
        raise ValidationError("Papel inválido para usuário.")
    if "@" not in email:
        raise ValidationError("E-mail inválido.")
    if db.fetchone("SELECT id FROM users WHERE email = ?", (email.lower(),)):
        raise Conflict("E-mail já cadastrado.")
    user_id = new_id("USR")
    db.execute("INSERT INTO users (id, email, name, role, domains, password_hash, active, is_demo, created_at) "
               "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
               (user_id, email.lower(), name, role, jdump(domains or ["*"]), hash_password(password), int(is_demo), now_iso()))
    record_audit(db, actor, "user.create", "user", user_id, {"email": email, "role": role})
    return get_user(db, user_id)


def get_user(db: Database, user_id: str) -> dict:
    row = db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    if not row:
        raise NotFound("Usuário não encontrado.")
    return _public(row)


def list_users(db: Database) -> List[dict]:
    return [_public(r) for r in db.fetchall("SELECT * FROM users ORDER BY created_at")]


def authenticate(db: Database, email: str, password: str) -> dict:
    row = db.fetchone("SELECT * FROM users WHERE email = ? AND active = 1", ((email or "").lower(),))
    if not row or not verify_password(password or "", row["password_hash"]):
        raise AuthenticationError("Credenciais inválidas.")
    settings = get_settings()
    token = create_token({"sub": row["id"], "role": row["role"], "tv": int(row.get("token_version") or 0),
                          "sid": secrets.token_urlsafe(12)}, settings.secret_key, settings.token_ttl_minutes)
    record_audit(db, to_principal(row), "auth.login", "user", row["id"], {})
    return {"access_token": token, "token_type": "bearer", "user": _public(row)}


def principal_from_token(db: Database, token: str) -> Principal:
    payload = decode_token(token, get_settings().secret_key)
    row = db.fetchone("SELECT * FROM users WHERE id = ? AND active = 1", (payload.get("sub"),))
    if not row:
        raise AuthenticationError("Usuário inativo ou inexistente.")
    if int(payload.get("tv", 0)) != int(row.get("token_version") or 0):
        raise AuthenticationError("Sessão encerrada (senha, papel ou status alterados). Entre novamente.")
    if payload.get("sid") and db.fetchone("SELECT sid FROM revoked_sessions WHERE sid = ?", (payload["sid"],)):
        raise AuthenticationError("Sessão encerrada. Entre novamente.")
    return to_principal(row)


def revoke_session(db: Database, token: Optional[str]) -> bool:
    """Logout: registra a sessão (sid) como encerrada até o token expirar. Token inválido é ignorado."""
    if not token:
        return False
    try:
        payload = decode_token(token, get_settings().secret_key)
    except AuthenticationError:
        return False
    if not payload.get("sid"):
        return False
    now = int(time.time())
    with db.connect() as c:
        c.execute("DELETE FROM revoked_sessions WHERE expires_at < ?", (now,))
        if not c.fetchone("SELECT sid FROM revoked_sessions WHERE sid = ?", (payload["sid"],)):
            c.execute("INSERT INTO revoked_sessions (sid, expires_at, revoked_at) VALUES (?, ?, ?)",
                      (payload["sid"], int(payload.get("exp", now)), now_iso()))
    return True


def _bump_token_version(db: Database, user_id: str) -> None:
    db.execute("UPDATE users SET token_version = COALESCE(token_version, 0) + 1 WHERE id = ?", (user_id,))


def seed_demo_users(db: Database, password: Optional[str] = None) -> Optional[str]:
    """Cria os usuários de demonstração (idempotente). Retorna a senha gerada, se houver."""
    existing = db.fetchone("SELECT id, password_hash FROM users WHERE is_demo = 1 ORDER BY created_at LIMIT 1")
    if existing:
        for email, name, _role, _domains in DEMO_USERS:   # bancos antigos: nomes de demo em português
            db.execute("UPDATE users SET name = ? WHERE email = ? AND is_demo = 1 AND name LIKE '%(demo)'", (name, email))
        # Usuários de demonstração adicionados em versões novas (ex.: Atendimento) recebem a MESMA senha de demo já em
        # uso (copia o hash; a senha em claro não é conhecida nem necessária).
        for email, name, role, domains in DEMO_USERS:
            if not db.fetchone("SELECT id FROM users WHERE email = ?", (email,)):
                if domains != ["*"]:
                    valid = {r["key"] for r in db.fetchall("SELECT key FROM domains")}
                    domains = [d for d in domains if d in valid] or ["corporate"]
                db.execute("INSERT INTO users (id, email, name, role, domains, password_hash, active, is_demo, created_at) "
                           "VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?)",
                           (new_id("USR"), email, name, role, jdump(domains), existing["password_hash"], now_iso()))
        return None
    pwd = password or get_settings().demo_admin_password
    generated = None
    if not pwd:
        pwd = generated = secrets.token_urlsafe(12)
        cred_file = ROOT_DIR / "var" / "demo_credentials.txt"
        cred_file.parent.mkdir(parents=True, exist_ok=True)
        cred_file.write_text(
            "Credenciais de DEMONSTRAÇÃO geradas localmente (não usar em produção)\n"
            + "\n".join(f"{e} / {pwd}  [{r}]" for e, _, r, _ in DEMO_USERS) + "\n", encoding="utf-8")
    for email, name, role, domains in DEMO_USERS:
        create_user(db, SYSTEM_PRINCIPAL, email, name, role, domains, pwd, is_demo=True)
    return generated


def _active_admins(db: Database) -> int:
    return db.fetchone("SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND active = 1")["n"]


def update_user(db: Database, actor: Principal, user_id: str, *, name: Optional[str] = None, role: Optional[str] = None,
                domains: Optional[List[str]] = None, active: Optional[bool] = None) -> dict:
    """Altera papel, domínios, nome ou status. Impede remover o último administrador ativo e auto-desativação."""
    require_permission(actor, "settings:write")
    current = db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
    if not current:
        raise NotFound("Usuário não encontrado.")
    if role is not None and (role not in ROLES or role == "ai_agent"):
        raise ValidationError("Papel inválido para usuário.")
    if domains is not None:
        valid = {r["key"] for r in db.fetchall("SELECT key FROM domains")} | {"*"}
        bad = [d for d in domains if d not in valid]
        if not domains or bad:
            raise ValidationError(f"Domínios inválidos: {bad or 'lista vazia'}")
    if active is False and user_id == actor.id:
        raise ValidationError("Você não pode desativar o próprio usuário.")
    losing_admin = current["role"] == "admin" and current["active"] and (
        (role is not None and role != "admin") or active is False)
    if losing_admin and _active_admins(db) <= 1:
        raise Conflict("Não é possível remover o último administrador ativo.")
    sets, params = [], []
    for col, val in (("name", name), ("role", role), ("domains", jdump(domains) if domains is not None else None),
                     ("active", int(active) if active is not None else None)):
        if val is not None:
            sets.append(f"{col} = ?"); params.append(val)
    if not sets:
        return get_user(db, user_id)
    sets.append("updated_at = ?"); params.append(now_iso())
    db.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", (*params, user_id))
    if role is not None or domains is not None or active is False:
        _bump_token_version(db, user_id)   # permissões mudaram: sessões antigas deixam de valer
    record_audit(db, actor, "user.update", "user", user_id,
                 {"role": role, "domains": domains, "active": active, "name": name})
    return get_user(db, user_id)


def reset_password(db: Database, actor: Principal, user_id: str, new_password: str) -> dict:
    if actor.id != user_id:
        require_permission(actor, "settings:write")
    if not db.fetchone("SELECT id FROM users WHERE id = ?", (user_id,)):
        raise NotFound("Usuário não encontrado.")
    try:
        hashed = hash_password(new_password)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    db.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?", (hashed, now_iso(), user_id))
    _bump_token_version(db, user_id)
    record_audit(db, actor, "user.password_reset", "user", user_id, {})
    return {"ok": True}
