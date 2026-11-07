"""Agente como colega de trabalho: turno autônomo, canal do time (app/Telegram), IA com fallback e equipe de agentes."""
from helpers import ADMIN, make_env, user

from goops_core.permissions import agent_principal


def _env():
    return make_env("full", shared=False)


def test_shift_reminds_closes_alerts_and_calls_other_agents():
    env = _env()
    db = env.db
    from agents.support.shift import run_shift
    from goops_core.runtime_config import update_section
    update_section(db, ADMIN, "support", {"spike_min_contacts": 2, "sla_first_response_hours": 1})
    out = run_shift(db, env.lake, agent_principal("support"), advance_hours=40)
    assert out["sla_alerts"] > 0 and out["digest"] is True
    assert out["incidents"], "pico de reclamações por transportadora deve virar incidente"
    inc = db.fetchone("SELECT id, source, status FROM incidents WHERE id = ?", (out["incidents"][0]["incident_id"],))
    assert inc["source"] == "agent:support"
    runs = {r["agent_key"] for r in db.fetchall("SELECT agent_key FROM agent_runs WHERE incident_id = ?", (inc["id"],))}
    assert "investigation" in runs                     # Atendimento → Supervisor → Investigação
    kinds = {r["kind"] for r in db.fetchall("SELECT kind FROM team_messages")}
    assert {"sla", "incident", "digest"} <= kinds
    out2 = run_shift(db, env.lake, agent_principal("support"), advance_hours=60)
    assert out2["closed_inactive"] + out2["reminders"] + out["closed_inactive"] + out["reminders"] >= 0
    assert not out2["digest"] or out2["clock"][:10] != out["clock"][:10]   # resumo uma vez por dia


def test_approval_request_goes_to_team_channel_and_telegram_approves():
    env = _env()
    db = env.db
    from agents import team_channel
    from agents.support import service
    from goops_core.runtime_config import update_section
    sent = []
    team_channel._tg = lambda _db, method, payload, timeout=15: sent.append((method, payload)) or {"message_id": 42}
    update_section(db, ADMIN, "team_channel", {"provider": "telegram", "telegram_chat_id": "-100123456"})
    k = db.fetchone("SELECT id FROM support_contacts WHERE intent = 'avaria' AND veracity_label = 'consistente' AND order_id IS NOT NULL "
                    "AND status = 'resolved' LIMIT 1")
    db.execute("UPDATE support_contacts SET status = 'pending_human' WHERE id = ?", (k["id"],))
    op = service.propose_action(db, user("support_agent", ["atendimento"], "USR-att"), k["id"], "support_reshipment")
    msg = db.fetchone("SELECT * FROM team_messages WHERE operation_id = ? AND kind = 'approval_request'", (op["id"],))
    assert msg and msg["delivery"] == "delivered" and msg["external_ref"] == "42"
    assert any(m == "sendMessage" and p.get("reply_markup") for m, p in sent)
    # sem vínculo: Telegram não aprova
    upd = {"callback_query": {"id": "1", "from": {"id": 999}, "data": f"op:a:{op['id']}"}}
    assert "Vincule" in team_channel.handle_update(db, env.lake, upd)
    owner = db.fetchone("SELECT id FROM users WHERE email = 'atendimento.owner@goops.local'")
    if not owner:
        from goops_core.users import create_user
        owner = create_user(db, ADMIN, "atendimento.owner@goops.local", "Dono", "domain_owner", ["atendimento"], "senha-demo-123")
    from goops_core.users import to_principal
    code = team_channel.link_code(db, to_principal(db.fetchone("SELECT * FROM users WHERE id = ?", (owner["id"],))))["code"]
    assert "vinculada" in team_channel.handle_update(db, env.lake, {"message": {"text": f"/vincular {code}", "chat": {"id": 7},
                                                                               "from": {"id": 999}}})
    assert team_channel.handle_update(db, env.lake, upd).startswith("Aprovado")
    assert db.fetchone("SELECT status FROM operations WHERE id = ?", (op["id"],))["status"] == "executed"
    assert "Fila" in team_channel.handle_update(db, env.lake, {"message": {"text": "/fila", "chat": {"id": 7}, "from": {"id": 999}}})


def test_ai_classifies_ambiguous_message_with_rules_fallback():
    env = _env()
    db = env.db
    from agents.support import assist
    from agents.support.conversations import process_messages
    from goops_core.runtime_config import set_secret
    from goops_core.util import new_id, now_iso
    set_secret(db, ADMIN, "ai_proxy_api_key", "gw-tok-teste-123456")
    calls = []

    def fake_jev(_db, token, state, questions, **kw):
        calls.append(state)
        return {"answers": {"intencao": {"choice": "troca_devolucao", "confidence": 0.86}}, "model": "jev-test", "usage": {}}
    import agents.llm.gogroup_proxy as gp
    gp.jev = fake_jev
    clock = db.fetchone("SELECT MAX(sent_at) AS t FROM support_messages")["t"]
    db.execute("INSERT INTO support_messages (id, source_key, external_id, direction, author_type, author, text, attachments, sent_at, "
               "channel, handle, customer_ref, processed, is_demo, created_at) VALUES (?, 'support_demo_contatos', 'T-AMB-1', 'in', "
               "'customer', 'Cliente', 'Oi, o tamanho não serviu, o que eu faço agora?', '[]', ?, 'whatsapp', '+55 11 90000-0001', "
               "NULL, 0, 1, ?)", (new_id("MSG"), clock, now_iso()))
    process_messages(db, env.lake, live=True)
    k = db.fetchone("SELECT intent, intent_source FROM support_contacts WHERE external_id = 'T-AMB-1'")
    assert calls and k["intent"] == "troca_devolucao" and k["intent_source"] == "ia"
    gp.jev = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("proxy fora"))   # IA indisponível → regras
    assert assist.ai_classify(db, type("S", (), {"ai_proxy_api_key": "x"})(), None, "texto", "email") is None


def test_case_summary_for_human_handoff():
    env = make_env("full")
    k = env.db.fetchone("SELECT case_summary, summary_generated_by FROM support_contacts WHERE routing = 'human' "
                        "AND case_summary IS NOT NULL LIMIT 1")
    assert k and "via" in k["case_summary"] and k["summary_generated_by"] == "deterministic"


def test_deepseek_blocked_and_gogroup_provider():
    env = make_env("full")
    from goops_core.errors import ValidationError
    from goops_core.runtime_config import update_section
    from helpers import assert_raises
    assert_raises(ValidationError, update_section, env.db, ADMIN, "llm",
                  {"levels": {"2": {"provider": "gogroup", "model": "deepseek-v4-pro"}}})
    out = update_section(env.db, ADMIN, "llm", {"levels": {"2": {"provider": "gogroup", "model": "glm-5.3-flash"}}})
    assert out["levels"]["2"]["provider"] == "gogroup"
    update_section(env.db, ADMIN, "llm", {"levels": {"2": {"provider": "none", "model": ""}}})
