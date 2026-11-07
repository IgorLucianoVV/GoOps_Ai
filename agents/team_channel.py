"""Canal do time: os agentes conversam com as pessoas onde elas já estão.

* **app** (sempre): mural "Canal do time" no GoOps, com botões de aprovar/rejeitar.
* **telegram**: bot real (API pública do Telegram, long polling — não precisa de servidor público). Avisa, pede
  aprovação com botões e recebe pedidos (/fila, /resumo, /caso <id>). Cada pessoa vincula a sua conta com
  /vincular <código> (gerado em Canal do time); a aprovação usa as permissões DESSA pessoa no GoOps.
* **slack**: webhook de entrada (só avisos; a aprovação abre o GoOps — botões interativos exigem app com URL pública).

Segurança: tokens no cofre de configurações (ou TELEGRAM_BOT_TOKEN / SLACK_WEBHOOK_URL); chamadas só para
api.telegram.org e para a URL do webhook do Slack (hooks.slack.com); mensagens recebidas são DADOS.
"""
from __future__ import annotations

import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from goops_core.db import Database
from goops_core.errors import NotFound, PermissionDenied, ValidationError
from goops_core.permissions import Principal, require_permission
from goops_core.runtime_config import get_section, get_secret
from goops_core.util import jdump, new_id, now_iso

log = logging.getLogger("goops.team")
TG = "https://api.telegram.org"


def _cfg(db: Database) -> Dict[str, Any]:
    return get_section(db, "team_channel")


def _secret(db: Database, name: str) -> Optional[str]:
    try:
        return get_secret(db, name)
    except Exception:  # noqa: BLE001
        return None


def _tg(db: Database, method: str, payload: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
    token = _secret(db, "telegram_bot_token")
    if not token:
        raise ValidationError("Token do bot do Telegram não configurado.")
    import requests
    r = requests.post(f"{TG}/bot{token}/{method}", json=payload, timeout=timeout)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not body.get("ok"):
        raise ValidationError(f"Telegram recusou ({body.get('description') or r.status_code}).")
    return body.get("result") or {}


def _buttons(op_id: str) -> Dict[str, Any]:
    return {"inline_keyboard": [[{"text": "✅ Aprovar", "callback_data": f"op:a:{op_id}"},
                                 {"text": "❌ Rejeitar", "callback_data": f"op:r:{op_id}"}]]}


def notify(db: Database, kind: str, text: str, *, operation_id: Optional[str] = None, contact_id: Optional[str] = None,
           incident_id: Optional[str] = None, dedupe_key: Optional[str] = None, link: Optional[str] = None) -> Optional[dict]:
    """Publica no canal do time (mural do app + provedor externo). Nunca levanta erro para quem chama."""
    cfg = _cfg(db)
    flag = {"approval_request": "notify_approvals", "approval_reminder": "notify_approvals", "sla": "notify_sla",
            "incident": "notify_incidents", "digest": "notify_digest"}.get(kind)
    if dedupe_key and db.fetchone("SELECT id FROM team_messages WHERE dedupe_key = ?", (dedupe_key,)):
        return None
    full = text + (f"\n{cfg.get('app_base_url', '').rstrip('/')}{link}" if link else "")
    provider = cfg.get("provider", "app")
    delivery, err, ext = "app_only", None, None
    if provider != "app" and (flag is None or cfg.get(flag, True)):
        try:
            if provider == "telegram":
                if not cfg.get("telegram_chat_id"):
                    raise ValidationError("Informe o ID do chat do Telegram (grupo do time).")
                payload: Dict[str, Any] = {"chat_id": cfg["telegram_chat_id"], "text": full, "disable_web_page_preview": True}
                if operation_id and kind in ("approval_request", "approval_reminder"):
                    payload["reply_markup"] = _buttons(operation_id)
                ext = str(_tg(db, "sendMessage", payload).get("message_id") or "") or None
            elif provider == "slack":
                url = _secret(db, "slack_webhook_url")
                if not url or not url.startswith("https://hooks.slack.com/"):
                    raise ValidationError("Webhook do Slack ausente ou inválido (https://hooks.slack.com/...).")
                import requests
                r = requests.post(url, json={"text": full}, timeout=10, allow_redirects=False)
                if r.status_code >= 300:
                    raise ValidationError(f"Slack respondeu HTTP {r.status_code}.")
            delivery = "delivered"
        except Exception as exc:  # noqa: BLE001
            delivery, err = "failed", (getattr(exc, "message", None) or type(exc).__name__)[:300]
            log.warning("team channel delivery failed: %s", err)
    mid = new_id("TM")
    try:
        db.execute("INSERT INTO team_messages (id, kind, text, operation_id, contact_id, incident_id, provider, delivery, "
                   "delivery_error, external_ref, dedupe_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (mid, kind, text, operation_id, contact_id, incident_id, provider, delivery, err, ext, dedupe_key, now_iso()))
    except Exception:  # noqa: BLE001 - corrida no dedupe
        return None
    return {"id": mid, "delivery": delivery, "error": err}


def feed(db: Database, actor: Principal, limit: int = 100) -> Dict[str, Any]:
    require_permission(actor, "operations:read")
    rows = db.fetchall(f"SELECT * FROM team_messages ORDER BY created_at DESC LIMIT {max(1, min(int(limit), 300))}")
    ops = {}
    ids = [r["operation_id"] for r in rows if r["operation_id"]]
    if ids:
        q = ",".join("?" * len(ids))
        ops = {o["id"]: o for o in db.fetchall(f"SELECT id, status, title, approved_by FROM operations WHERE id IN ({q})", ids)}
    for r in rows:
        r["operation"] = ops.get(r["operation_id"])
    cfg = _cfg(db)
    link = db.fetchone("SELECT external_user, linked_at, link_code, code_expires_at FROM team_links WHERE user_id = ?", (actor.id,))
    return {"items": rows, "provider": cfg.get("provider", "app"),
            "telegram_ready": bool(_secret(db, "telegram_bot_token") and cfg.get("telegram_chat_id")),
            "me": {"linked": bool(link and link.get("external_user")), "linked_at": link.get("linked_at") if link else None}}


def link_code(db: Database, actor: Principal) -> Dict[str, Any]:
    if actor.kind != "user":
        raise PermissionDenied("Somente pessoas vinculam contas.")
    code = secrets.token_hex(3).upper()
    exp = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    db.execute("INSERT INTO team_links (user_id, provider, link_code, code_expires_at) VALUES (?, 'telegram', ?, ?) "
               "ON CONFLICT (user_id) DO UPDATE SET link_code = excluded.link_code, code_expires_at = excluded.code_expires_at",
               (actor.id, code, exp))
    return {"code": code, "expires_at": exp, "instructions": f"Envie /vincular {code} ao bot do Telegram em até 15 minutos."}


def test_channel(db: Database, actor: Principal) -> Dict[str, Any]:
    require_permission(actor, "settings:write")
    out = notify(db, "info", f"👋 Teste do canal do time enviado por {actor.name}. O Agente de Atendimento vai avisar e "
                             "pedir aprovações por aqui.")
    return out or {}


# ------------------------------------------------------------------ eventos dos agentes → canal
def on_operation_proposed(db: Database, actor: Principal, op: dict) -> None:
    if op.get("status") != "pending_approval":
        return
    who = actor.name if actor.kind == "user" else "Agente de Atendimento" if op.get("contact_id") else "Agente de Resolução"
    link = f"/atendimento/{op['contact_id']}" if op.get("contact_id") else "/operations"
    notify(db, "approval_request", f"🙋 {who} pede aprovação: {op['title']}\n{op.get('description') or ''}\n"
                                   f"Risco {op.get('risk')} · impacta {', '.join(op.get('impacted_areas') or [])}",
           operation_id=op["id"], contact_id=op.get("contact_id"), incident_id=op.get("incident_id"),
           dedupe_key=f"approval:{op['id']}", link=link)


def on_operation_decided(db: Database, actor: Principal, op: dict) -> None:
    rows = db.fetchall("SELECT external_ref FROM team_messages WHERE operation_id = ? AND provider = 'telegram' "
                       "AND external_ref IS NOT NULL", (op["id"],))
    cfg = _cfg(db)
    mark = "✅ Aprovada" if op["status"] == "approved" else "❌ Rejeitada"
    for r in rows:
        try:
            _tg(db, "editMessageReplyMarkup", {"chat_id": cfg.get("telegram_chat_id"), "message_id": int(r["external_ref"]),
                                               "reply_markup": {"inline_keyboard": []}})
        except Exception:  # noqa: BLE001
            pass
    notify(db, "info", f"{mark} por {actor.name}: {op['title']}", operation_id=op["id"], contact_id=op.get("contact_id"),
           dedupe_key=f"decided:{op['id']}")


def register_hooks() -> None:
    from goops_core.operations import register_hook
    register_hook("proposed", on_operation_proposed)
    register_hook("decided", on_operation_decided)


# ------------------------------------------------------------------ Telegram: recebendo pedidos e aprovações
def _user_by_tg(db: Database, tg_user: Any) -> Optional[dict]:
    link = db.fetchone("SELECT user_id FROM team_links WHERE provider = 'telegram' AND external_user = ?", (str(tg_user),))
    if not link:
        return None
    return db.fetchone("SELECT * FROM users WHERE id = ? AND active = 1", (link["user_id"],))


def handle_update(db: Database, lake, upd: Dict[str, Any]) -> Optional[str]:
    """Processa uma atualização do Telegram. Retorna o texto de resposta (para testes)."""
    from goops_core.users import to_principal
    if "callback_query" in upd:
        cq = upd["callback_query"]
        data = str(cq.get("data") or "")
        reply = "Ação não reconhecida."
        user = _user_by_tg(db, (cq.get("from") or {}).get("id"))
        if not data.startswith("op:"):
            pass
        elif not user:
            reply = "Vincule sua conta primeiro: gere o código em GoOps › Canal do time e envie /vincular CÓDIGO."
        else:
            _, act, op_id = data.split(":", 2)
            from agents.supervisor.agent import Supervisor
            try:
                out = Supervisor(db, lake).decide(op_id, to_principal(user), act == "a", "via Telegram")
                reply = f"{'Aprovado' if act == 'a' else 'Rejeitado'}: {out['operation']['title']}"
            except Exception as exc:  # noqa: BLE001
                reply = getattr(exc, "message", None) or "Não foi possível registrar a decisão."
        try:
            _tg(db, "answerCallbackQuery", {"callback_query_id": cq.get("id"), "text": reply[:190]})
        except Exception:  # noqa: BLE001
            pass
        return reply
    msg = upd.get("message") or {}
    text = str(msg.get("text") or "").strip()
    chat = (msg.get("chat") or {}).get("id")
    tg_user = (msg.get("from") or {}).get("id")
    if not text or chat is None:
        return None
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    if cmd in ("/start", "/ajuda", "/help"):
        reply = ("Sou o Agente de Atendimento do GoOps. Comandos: /fila (atendimentos aguardando), /resumo (o dia), "
                 "/caso <id> (detalhes), /vincular <código> (para aprovar ações por aqui).")
    elif cmd == "/vincular":
        code = arg.strip().upper()
        row = db.fetchone("SELECT user_id, code_expires_at FROM team_links WHERE link_code = ?", (code,)) if code else None
        if not row or (row["code_expires_at"] or "") < datetime.now(timezone.utc).isoformat():
            reply = "Código inválido ou expirado. Gere outro em GoOps › Canal do time."
        else:
            db.execute("UPDATE team_links SET external_user = ?, linked_at = ?, link_code = NULL WHERE user_id = ?",
                       (str(tg_user), now_iso(), row["user_id"]))
            u = db.fetchone("SELECT name FROM users WHERE id = ?", (row["user_id"],))
            reply = f"Conta vinculada: {u['name'] if u else row['user_id']}. Você poderá aprovar ações conforme seu papel no GoOps."
    elif cmd == "/fila":
        from agents.support.shift import queue_text
        reply = queue_text(db)
    elif cmd == "/resumo":
        from agents.support.shift import digest_text
        reply = digest_text(db)
    elif cmd == "/caso":
        user = _user_by_tg(db, tg_user)
        if not user:
            reply = "Vincule sua conta para consultar casos (/vincular <código>)."
        else:
            c = db.fetchone("SELECT external_id, intent, status, case_summary FROM support_contacts WHERE id = ? OR external_id = ?",
                            (arg.strip(), arg.strip()))
            reply = (f"{c['external_id']} · {c['status']}\n{c['case_summary'] or ''}" if c else "Caso não encontrado.")
    else:
        reply = "Não entendi. Use /ajuda."
    try:
        _tg(db, "sendMessage", {"chat_id": chat, "text": reply[:3500]})
    except Exception:  # noqa: BLE001
        pass
    return reply


_POLLER: Optional[threading.Thread] = None
_STOP = threading.Event()


def start_poller(db: Database, lake) -> None:
    global _POLLER
    if _POLLER and _POLLER.is_alive():
        return
    _STOP.clear()

    def loop() -> None:
        offset = 0
        while not _STOP.is_set():
            try:
                if _cfg(db).get("provider") != "telegram" or not _secret(db, "telegram_bot_token"):
                    _STOP.wait(15)
                    continue
                res = _tg(db, "getUpdates", {"offset": offset, "timeout": 25,
                                             "allowed_updates": ["message", "callback_query"]}, timeout=35)
                for upd in res or []:
                    offset = max(offset, int(upd.get("update_id", 0)) + 1)
                    try:
                        handle_update(db, lake, upd)
                    except Exception:  # noqa: BLE001
                        log.exception("telegram update failed")
            except Exception as exc:  # noqa: BLE001
                log.warning("telegram poll: %s", getattr(exc, "message", type(exc).__name__))
                _STOP.wait(10)

    _POLLER = threading.Thread(target=loop, name="goops-telegram", daemon=True)
    _POLLER.start()


def stop_poller() -> None:
    _STOP.set()
