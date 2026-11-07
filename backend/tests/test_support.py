"""Atendimento ao Cliente (Desafio 1): triagem, veracidade, roteamento, ações com aprovação e prevenção de recontato."""
from datetime import datetime, timedelta

from helpers import ADMIN, assert_raises, make_env, user

from goops_core.errors import PermissionDenied, ValidationError


def _env():
    return make_env("full")


def test_pipeline_builds_support_inbox_and_gold():
    env = _env()
    step = next(s for s in env.pipeline["steps"] if s["step"] == "support")
    assert step["status"] == "success"
    out = step["output"]
    assert out["inserted"] > 1000 and out["triage"]["processed"] == out["inserted"]
    assert env.db.fetchone("SELECT COUNT(*) AS n FROM support_contacts WHERE status = 'new'")["n"] == 0
    channels = {r["channel"] for r in env.db.fetchall("SELECT DISTINCT channel FROM support_contacts")}
    assert channels == {"whatsapp", "email", "reclameaqui"}
    gold = env.lake.read_table("gold/domains/atendimento", "gold_support_contacts")
    assert len(gold) == env.db.fetchone("SELECT COUNT(*) AS n FROM support_contacts")["n"]
    assert "message" not in gold.columns and "customer_id" not in gold.columns   # minimização


def test_overview_and_metrics_agree():
    env = _env()
    from agents.support.overview import build_overview
    from data_platform.semantic.registry import compute_metric
    o = build_overview(env.db, ADMIN)
    assert o["ready"] and o["queue"]["open"] > 0
    assert 20 <= o["automation"]["auto_rate"] <= 70
    m = compute_metric(env.db, env.lake, ADMIN, "SUP_TAXA_AUTOMACAO")
    assert abs(m["result"]["value"] - o["automation"]["auto_rate"]) < 0.2
    assert m["metric"]["synthetic"] is True
    assert o["effort"]["saved_hours"] > 0 and o["effort"]["avg_systems_per_contact"] > 2
    acc = o["accuracy"]
    assert acc["intent_accuracy_pct"] >= 90 and acc["fake_flagged_pct"] >= 80


def test_claims_never_auto_resolved_and_reclameaqui_goes_to_human():
    env = _env()
    bad = env.db.fetchone("SELECT COUNT(*) AS n FROM support_contacts WHERE routing = 'auto' AND intent IN "
                          "('avaria', 'defeito', 'nao_recebido', 'produto_errado')")["n"]
    assert bad == 0
    ra_auto = env.db.fetchone("SELECT COUNT(*) AS n FROM support_contacts WHERE routing = 'auto' AND channel = 'reclameaqui'")["n"]
    assert ra_auto == 0
    inj = env.db.fetchall("SELECT routing FROM support_contacts WHERE injection_suspected = 1")
    assert all(r["routing"] == "human" for r in inj)


def test_veracity_rules():
    from agents.support.veracity import assess
    cfg = {"veracity_consistent_min": 70, "veracity_inconsistent_max": 39}
    delivered = datetime(2026, 5, 10)
    order = {"order_id": "1", "order_total": 100.0}
    base = {"order": order, "delivered_at": delivered, "eta": datetime(2026, 5, 12), "customer_orders": 3,
            "customer_claims_180d": 0, "product_line": "Copo", "carrier": "X"}
    photo_before = assess("avaria", received=delivered + timedelta(days=2), ctx=base,
                          attachments=[{"type": "image", "taken_at": "2026-04-20T10:00:00"}], cfg=cfg)
    assert photo_before["label"] == "inconsistente"
    assert any(f["factor"] == "Foto anterior à entrega" for f in photo_before["factors"])
    good = assess("avaria", received=delivered + timedelta(days=1), ctx=base,
                  attachments=[{"type": "image", "taken_at": "2026-05-11T09:00:00"}], cfg=cfg)
    assert good["label"] == "consistente"
    in_time = assess("atraso_entrega", received=datetime(2026, 5, 8), ctx={**base, "delivered_at": None}, attachments=[], cfg=cfg)
    assert in_time["label"] == "inconsistente"
    late = assess("atraso_entrega", received=datetime(2026, 5, 15), ctx={**base, "delivered_at": None}, attachments=[], cfg=cfg)
    assert late["label"] == "consistente"
    assert assess("elogio", received=delivered, ctx=base, attachments=[], cfg=cfg)["label"] == "nao_aplicavel"


def test_intent_classification_examples():
    from agents.support.triage import classify_intent, mask_pii
    assert classify_intent(None, "Quero cancelar o pedido #00004501, demorou demais")["intent"] == "cancelamento"
    assert classify_intent(None, "O rastreio diz que foi entregue mas eu NÃO recebi nada")["intent"] == "nao_recebido"
    assert classify_intent(None, "Cancelei o pedido e o estorno não foi feito.")["intent"] == "status_reembolso"
    assert classify_intent("Status", "Não recebi atualização desde a compra do meu pedido")["intent"] != "nao_recebido"
    assert mask_pii("ligue (85) 98877-1234 ou a@b.com") == "ligue [telefone] ou [e-mail]"


def test_config_rejects_unsafe_automation():
    env = _env()
    from goops_core.runtime_config import update_section
    assert_raises(ValidationError, update_section, env.db, ADMIN, "support", {"auto_intents": ["avaria"]})
    out = update_section(env.db, ADMIN, "support", {"human_channels": ["reclameaqui", "email"]})
    assert out["human_channels"] == ["email", "reclameaqui"]
    update_section(env.db, ADMIN, "support", {"human_channels": ["reclameaqui"]})


def test_action_requires_human_approval_and_resolves_contact():
    env = _env()
    from agents.support import service
    from goops_core.operations import decide_operation, get_operation
    attendant = user("support_agent", ["atendimento", "cx", "logistics"], "USR-att")
    owner = user("domain_owner", ["atendimento"], "USR-own")
    c = env.db.fetchone("SELECT id FROM support_contacts WHERE intent = 'avaria' AND veracity_label = 'consistente' "
                        "AND order_id IS NOT NULL ORDER BY received_at DESC LIMIT 1")
    op = service.propose_action(env.db, attendant, c["id"], "support_reshipment", "cliente enviou foto")
    assert op["status"] == "pending_approval" and op["contact_id"] == c["id"]
    assert env.db.fetchone("SELECT status FROM support_contacts WHERE id = ?", (c["id"],))["status"] == "pending_approval"
    assert_raises(PermissionDenied, decide_operation, env.db, attendant, op["id"], True)   # atendente não aprova
    decide_operation(env.db, owner, op["id"], True, "ok")
    assert get_operation(env.db, op["id"])["status"] == "executed"           # agente executa (simulado) após aprovação
    row = env.db.fetchone("SELECT status, resolution FROM support_contacts WHERE id = ?", (c["id"],))
    assert row["status"] == "resolved" and "simulada" in row["resolution"]
    detail = service.get_contact(env.db, env.lake, attendant, c["id"])
    assert any(e["event_type"] == "action_executed" for e in detail["events"])


def test_carrier_ticket_runs_without_approval():
    env = _env()
    ops = env.db.fetchall("SELECT status, proposed_by FROM operations WHERE action_type = 'support_carrier_ticket'")
    assert ops and all(o["status"] == "executed" for o in ops)
    assert all(o["proposed_by"] == "agent:support" for o in ops)


def test_permissions_and_pii_masking():
    env = _env()
    from agents.support import service
    from agents.support.overview import build_overview
    viewer = user("viewer")
    assert_raises(PermissionDenied, service.list_contacts, env.db, viewer)
    assert build_overview(env.db, viewer)["ready"]
    logistics_owner = user("domain_owner", ["logistics"])
    assert_raises(PermissionDenied, service.list_contacts, env.db, logistics_owner)
    page = service.list_contacts(env.db, ADMIN, q="telefone", limit=200)
    for it in service.list_contacts(env.db, ADMIN, limit=200)["items"]:
        assert "98877-" not in it["message"]
    assert "simulation_truth" not in service.get_contact(env.db, env.lake, user("support_agent", ["atendimento"]),
                                                         page["items"][0]["id"] if page["items"] else
                                                         service.list_contacts(env.db, ADMIN)["items"][0]["id"])


def test_human_correction_and_retriage():
    env = _env()
    from agents.support import service
    c = env.db.fetchone("SELECT id FROM support_contacts WHERE intent = 'onde_esta_pedido' AND order_id IS NOT NULL LIMIT 1")
    service.update_contact(env.db, ADMIN, c["id"], intent="avaria")
    out = service.retriage(env.db, env.lake, ADMIN, c["id"])
    assert out["intent"] == "avaria" and out["intent_source"] == "humano" and out["routing"] == "human"


def test_prevention_and_proactive_notice():
    env = _env()
    from agents.support import prevention
    r = prevention.recontact_analysis(env.db)
    assert r["repeats"] > 0 and r["avoidable"] > 0
    assert prevention.root_causes(env.db, env.lake)
    cand = prevention.proactive_candidates(env.db, env.lake)
    assert cand["count"] > 0 and cand["message_preview"]
    op = prevention.propose_proactive_notice(env.db, user("domain_owner", ["atendimento"]))
    assert op["status"] == "pending_approval"                 # toca a área crítica "clientes"


def test_simulate_incoming_contacts_are_triaged_live():
    env = _env()
    from data_platform.support.pipeline import simulate_incoming
    before = env.db.fetchone("SELECT COUNT(*) AS n FROM support_messages WHERE direction = 'in'")["n"]
    out = simulate_incoming(env.db, env.lake, ADMIN, 8)
    assert out["received"] >= 8 and out["triage"]["processed"] == out["received"]
    assert env.db.fetchone("SELECT COUNT(*) AS n FROM support_messages WHERE direction = 'in'")["n"] == before + out["received"]
    assert env.db.fetchone("SELECT COUNT(*) AS n FROM support_contacts WHERE external_id LIKE 'LIVE-%' "
                           "AND history_simulated = 1")["n"] == 0


def test_conversations_group_by_customer_and_channel():
    env = _env()
    db = env.db
    from agents.support.conversations import get_conversation, list_conversations
    # uma conversa por (canal, identidade); nenhuma mensagem sem conversa/atendimento
    dup = db.fetchone("SELECT COUNT(*) AS n FROM (SELECT channel, handle, COUNT(*) c FROM support_conversations "
                      "GROUP BY 1, 2 HAVING c > 1)")["n"]
    assert dup == 0
    assert db.fetchone("SELECT COUNT(*) AS n FROM support_messages WHERE processed = 0 OR conversation_id IS NULL")["n"] == 0
    assert db.fetchone("SELECT COUNT(*) AS n FROM support_conversations WHERE cases_count >= 2")["n"] > 0
    # respostas têm texto e lado (cliente × robô/atendente) e a ordem segue o relógio dos dados
    cv = db.fetchone("SELECT conversation_id FROM support_contacts WHERE history_simulated = 1 AND routing = 'human' "
                     "LIMIT 1")["conversation_id"]
    conv = get_conversation(db, ADMIN, cv)
    sides = {m["author_type"] for m in conv["messages"]}
    assert "customer" in sides and "human" in sides
    times = [m["sent_at"] for m in conv["messages"]]
    assert times == sorted(times)
    assert "@" not in conv["handle_display"] or "•" in conv["handle_display"]
    assert list_conversations(db, ADMIN, queue="open")["total"] > 0


def test_follow_up_message_continues_open_case_and_courtesy_does_not_reopen():
    env = _env()
    db = env.db
    # cliente mandou a foto pedida: mesma conversa e mesmo atendimento (não é recontato)
    row = db.fetchone("SELECT m.contact_id FROM support_messages m WHERE m.direction = 'in' AND m.text LIKE 'Segue a foto%' "
                      "AND m.external_id NOT LIKE 'LIVE-%' LIMIT 1")
    if row:
        k = db.fetchone("SELECT message_count, is_repeat FROM support_contacts WHERE id = ?", (row["contact_id"],))
        assert k["message_count"] >= 2
    from agents.support.conversations import is_courtesy
    assert is_courtesy("Obrigado!") and is_courtesy("Ok, valeu 👍") and not is_courtesy("Obrigado, mas não chegou")
    courtesy_cases = db.fetchone("SELECT COUNT(*) AS n FROM support_contacts WHERE message IN ('Obrigado!', 'Ok', "
                                 "'Ok, valeu 👍', 'Perfeito, obrigada', 'Beleza, obrigado')")["n"]
    total_courtesy = db.fetchone("SELECT COUNT(*) AS n FROM support_messages WHERE text IN ('Obrigado!', 'Ok', 'Ok, valeu 👍', "
                                 "'Perfeito, obrigada', 'Beleza, obrigado')")["n"]
    assert courtesy_cases < total_courtesy * 0.2


def test_reply_and_note_appear_in_chat():
    env = _env()
    db = env.db
    from agents.support import service
    from agents.support.conversations import add_note, get_conversation
    k = db.fetchone("SELECT id, conversation_id FROM support_contacts WHERE status = 'pending_human' LIMIT 1")
    add_note(db, ADMIN, k["conversation_id"], "Cliente VIP, priorizar.")
    service.send_reply(db, ADMIN, k["id"], "Olá! Já verificamos e vamos reenviar.", resolve=True)
    msgs = get_conversation(db, ADMIN, k["conversation_id"])["messages"]
    assert msgs[-1]["author_type"] == "system" and msgs[-2]["author_type"] == "human"
    assert any(m["author_type"] == "note" for m in msgs)


def test_feature_toggle_disables_support_step():
    env = make_env("full", shared=False)
    from goops_core.runtime_config import update_section
    from data_platform.ingestion.service import apply_features
    from data_platform.support.pipeline import build_support
    update_section(env.db, ADMIN, "features", {"support": False})
    apply_features(env.db)
    assert env.db.fetchone("SELECT status FROM domains WHERE key = 'atendimento'")["status"] == "inactive"
    assert "skipped" in build_support(env.db, env.lake, None, ADMIN)
