"""Testes da camada HTTP (FastAPI TestClient). Ignorados se FastAPI/httpx não estiverem instalados."""
import os
import unittest

from helpers import make_env

try:
    from fastapi.testclient import TestClient  # noqa: F401
    HAS_FASTAPI = True
except Exception:  # noqa: BLE001
    HAS_FASTAPI = False


def _client():
    if not HAS_FASTAPI:
        raise unittest.SkipTest("fastapi/httpx não instalados")
    env = make_env("full")
    os.environ["SCHEDULER_ENABLED"] = "false"
    os.environ["AUTO_LOAD_DEMO"] = "false"
    from goops_core.users import seed_demo_users
    seed_demo_users(env.db, "senha-demo-123")
    from fastapi.testclient import TestClient
    from backend.app.main import app
    return TestClient(app)


def _login(c, email="admin@goops.local"):
    r = c.post("/api/auth/login", json={"email": email, "password": "senha-demo-123"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["csrf_token"]


def test_http_auth_cookie_and_csrf():
    c = _client()
    assert c.get("/api/overview").status_code == 401
    _login(c)
    csrf = _login(c)   # novo login gera novo cookie CSRF: o token anterior deixa de valer
    assert "access_token" not in c.post("/api/auth/login", json={"email": "admin@goops.local", "password": "senha-demo-123"}).json()["data"]
    csrf = c.cookies.get("goops_csrf")
    assert c.get("/api/auth/me").json()["data"]["role"] == "admin"
    assert c.post("/api/data/retention", json={"dry_run": True}).status_code == 401          # sem CSRF
    assert c.post("/api/data/retention", json={"dry_run": True}, headers={"X-CSRF-Token": csrf}).status_code == 200


def test_http_endpoints_and_errors():
    c = _client()
    csrf = _login(c)
    h = {"X-CSRF-Token": csrf}
    for path in ("/api/health", "/api/overview", "/api/analytics/nps/overview", "/api/analytics/nps/evolution",
                 "/api/semantic/metrics", "/api/data/lineage", "/api/settings/config", "/api/scheduler", "/api/agents"):
        assert c.get(path).status_code == 200, path
    r = c.get("/api/analytics/nps/overview", params={"carrier": "DeltaFrete"})
    assert r.json()["data"]["metric"]["metric_key"] == "METRIC_NPS_001"
    assert c.post("/api/settings/config/llm", json={"value": {"levels": {"1": {"provider": "x"}}}}, headers=h).status_code == 422
    assert c.get("/api/incidents/INC-nao-existe").status_code == 404
    r = c.post("/api/settings/secrets/openai_api_key", json={"value": "sk-teste-12345678"}, headers=h)
    assert r.status_code == 200 and "sk-teste" not in r.text


def test_http_viewer_forbidden():
    c = _client()
    csrf = _login(c, "viewer@goops.local")
    assert c.post("/api/settings/config/cost", json={"value": {"limit_per_run_usd": 1, "limit_daily_usd": 1}},
                  headers={"X-CSRF-Token": csrf}).status_code == 403


def test_http_logout_revokes_session():
    c = _client()
    _login(c, "analyst@goops.local")
    token = c.cookies.get("goops_session")
    assert c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/logout").status_code == 200
    c.cookies.set("goops_session", token)            # reapresentar o cookie antigo não funciona mais
    assert c.get("/api/auth/me").status_code == 401


def test_http_forwarded_for_rate_key():
    from backend.app.security.ratelimit import client_key
    assert client_key("172.18.0.3", "203.0.113.9, 172.18.0.3") == "203.0.113.9"   # atrás do Next/proxy interno
    assert client_key("8.8.8.8", "1.2.3.4") == "8.8.8.8"               # cliente público não forja


def test_http_support_endpoints():
    c = _client()
    csrf = _login(c, "atendente@goops.local")
    h = {"X-CSRF-Token": csrf}
    assert c.get("/api/support/overview").json()["data"]["ready"]
    items = c.get("/api/support/contacts", params={"queue": "open"}).json()["data"]["items"]
    assert items
    cid = items[0]["id"]
    d = c.get(f"/api/support/contacts/{cid}").json()["data"]
    assert "events" in d and "suggested_reply" in d
    assert c.post(f"/api/support/contacts/{cid}/reply", json={"text": "Olá! Estamos verificando."}, headers=h).status_code == 200
    assert c.get("/api/support/prevention").status_code == 200
    assert c.post("/api/support/simulate", json={"count": 2}, headers=h).json()["data"]["received"] >= 2
    csrf_v = _login(c, "viewer@goops.local")
    assert c.get("/api/support/contacts").status_code == 403


def test_http_conversations_chat():
    c = _client()
    csrf = _login(c, "atendente@goops.local")
    items = c.get("/api/support/conversations").json()["data"]["items"]
    assert items and "handle" not in items[0]
    d = c.get(f"/api/support/conversations/{items[0]['id']}").json()["data"]
    assert d["messages"] and d["cases"]
    r = c.post(f"/api/support/conversations/{items[0]['id']}/note", json={"text": "nota de teste"}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200


def test_http_agents_instructions_and_custom_agents():
    c = _client()
    h = {"X-CSRF-Token": _login(c)}
    inv = c.get("/api/agents/investigation").json()["data"]
    assert inv["profile"]["does"] and {i["slot"] for i in inv["instructions"]} == {"investigation_narrative", "classify_comment"}
    assert c.get("/api/agents/monitor").json()["data"]["instructions"] == []          # 100% regras
    r = c.post("/api/agents/instructions/summarize_incident", headers=h,
               json={"text": "Resuma o incidente para a diretoria em 3 frases.", "note": "teste http"})
    assert r.status_code == 200 and r.json()["data"]["version"] >= 1
    assert c.get("/api/agents/instructions/summarize_incident/history").json()["data"][0]["note"] == "teste http"
    assert c.post("/api/agents/instructions/summarize_incident/reset", headers=h).json()["data"]["is_default"]
    opts = c.get("/api/agents/custom/options").json()["data"]
    assert "llm_task" in opts["templates"] and any(t["name"] == "metric_value" for t in opts["tools"])
    body = {"key": "cx_http_vigia", "domain": "cx", "name": "Vigia HTTP", "template": "llm_task", "interval_minutes": None,
            "config": {"instructions": "Resuma o NPS do mês e os incidentes abertos para o time de CX.",
                       "tools": ["nps_monthly", "open_incidents"], "output": "report"}}
    assert c.post("/api/agents/custom", headers=h, json=body).status_code == 200
    assert any(a["key"] == "cx_http_vigia" for a in c.get("/api/agents/custom").json()["data"])
    run = c.post("/api/agents/custom/cx_http_vigia/run", headers=h).json()["data"]
    assert run["generated_by"] == "deterministic" and run["report_md"]
    detail = c.get("/api/agents/custom/cx_http_vigia").json()["data"]
    assert detail["runs"] == 1 and detail["recent_runs"][0]["status"] == "success"
    assert c.post("/api/agents/custom/cx_http_vigia/delete", headers=h).status_code == 200
    # leitor não edita instruções
    c2 = _client()
    h2 = {"X-CSRF-Token": _login(c2, "viewer@goops.local")}
    assert c2.post("/api/agents/instructions/summarize_incident", headers=h2,
                   json={"text": "Resuma o incidente em 2 frases, por favor."}).status_code == 403


def test_http_instruction_draft_test_publish_and_agent_dry_run():
    c = _client()
    h = {"X-CSRF-Token": _login(c)}
    d = c.post("/api/agents/instructions/explain_metric/draft", headers=h,
               json={"text": "Explique esta métrica em linguagem simples para um gestor de CX.", "note": "http"}).json()["data"]
    assert d["draft"] and d["text"] != d["draft"]["text"]
    t = c.post("/api/agents/instructions/explain_metric/test", headers=h, json={"text": d["draft"]["text"]}).json()["data"]
    assert "<evidence>" in t["prompt"] and t["ran"] is False
    pub = c.post("/api/agents/instructions/explain_metric/publish", headers=h).json()["data"]
    assert pub["draft"] is None and pub["text"].startswith("Explique esta métrica em linguagem simples")
    assert c.get("/api/agents/supervisor").json()["data"]["instructions"][1]["version"] >= 1
    cfg = {"instructions": "Resuma o NPS do mês e os incidentes abertos para o time de CX.", "tools": ["nps_monthly"],
           "output": "incident", "checks": [{"type": "contains", "value": "NPS"}]}
    r = c.post("/api/agents/custom/test", headers=h, json={"domain": "cx", "name": "Teste", "config": cfg}).json()["data"]
    assert r["dry_run"] and r["trace"] and r["checks"][0]["ok"] is True
