"""Validação ponta a ponta dos agentes: roda em processo separado (ambiente isolado) e todas as verificações passam."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_validate_agents_end_to_end_all_checks_pass(tmp_path):
    env = {**os.environ, "SECRET_KEY": os.environ.get("SECRET_KEY", "test-secret-key-not-for-production")}
    proc = subprocess.run([sys.executable, str(ROOT / "manage.py"), "validate-agents", "--quiet"], cwd=str(ROOT),
                          capture_output=True, text=True, timeout=600, env=env)
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    report = json.loads(Path(out["relatorio"]["json"]).read_text(encoding="utf-8"))
    failed = [(a["key"], c["title"], c["observed"]) for a in report["agents"] for c in a["cases"] if c["ok"] is False]
    assert not failed, failed
    keys = {a["key"] for a in report["agents"]}
    assert {"monitor", "investigation", "resolution", "supervisor", "support", "validation", "sector", "custom", "ai"} <= keys
    assert report["isolated"] and report["summary"]["generated_cases"] >= 5 and report["summary"]["cases"] >= 30
    assert proc.returncode == 0
