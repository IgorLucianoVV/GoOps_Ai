"""CLI de operação do GoOps AI.

  python manage.py init                       # migrações + catálogos + usuários demo
  python manage.py demo-load [--scenario gocase|full|basic10] [--no-reset]
  python manage.py pipeline [--no-sync]       # Fonte -> Bronze -> Silver -> Gold -> Semântica
  python manage.py monitor [--no-investigate] # ciclo do Supervisor (Monitor + workflows)
  python manage.py status                     # resumo do ambiente
  python manage.py test                       # testes (pytest se disponível, senão executor stdlib)
  python manage.py validate-agents [--with-ai] # validação ponta a ponta dos agentes (ambiente isolado + relatório)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="GoOps AI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    d = sub.add_parser("demo-load")
    d.add_argument("--scenario", default="gocase", choices=["gocase", "full", "basic10"],
                   help="gocase = planilhas do case (padrão); full/basic10 = dados sintéticos")
    d.add_argument("--no-reset", action="store_true")
    p = sub.add_parser("pipeline")
    p.add_argument("--no-sync", action="store_true")
    m = sub.add_parser("monitor")
    m.add_argument("--no-investigate", action="store_true")
    sub.add_parser("status")
    sub.add_parser("test")
    v = sub.add_parser("validate-agents")
    v.add_argument("--with-ai", action="store_true", help="usa a configuração de IA (modelos e chaves) da aplicação")
    v.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.cmd == "validate-agents":
        # roda num banco e Lakehouse TEMPORÁRIOS: não altera os dados da aplicação
        from goops_core.config import get_settings
        from goops_core.logging_setup import setup_logging
        from agents.walkthrough import run_walkthrough, save
        setup_logging("ERROR")
        src = get_settings().database_url if args.with_ai else None
        report = run_walkthrough(copy_ai_from=src, progress=(lambda m: None) if args.quiet else print)
        paths = save(report)
        s = report["summary"]
        if not args.quiet:
            for a in report["agents"]:
                print(f"  {'OK ' if not a['failed'] else 'FALHA'} {a['name']}: {a['passed']}/{a['passed'] + a['failed']}")
                for c in a["cases"]:
                    if c["ok"] is False:
                        print(f"      ✗ {c['title']}")
        print(json.dumps({"aprovadas": s["passed"], "verificacoes": s["cases"], "relatorio": paths}, ensure_ascii=False))
        return 0 if s["failed"] == 0 else 1

    if args.cmd == "test":
        try:
            import pytest  # noqa: F401
            return subprocess.call([sys.executable, "-m", "pytest", "-q", str(ROOT / "backend" / "tests")], cwd=ROOT)
        except ImportError:
            return subprocess.call([sys.executable, str(ROOT / "infrastructure" / "scripts" / "run_tests_stdlib.py")])

    from goops_core.db import get_db
    from goops_core.logging_setup import setup_logging
    from goops_core.permissions import SYSTEM_PRINCIPAL
    from data_platform.bootstrap import bootstrap, load_demo
    from data_platform.storage import get_lakehouse

    setup_logging("WARNING")
    db, lake = get_db(), get_lakehouse()
    info = bootstrap(db)
    if args.cmd == "init":
        print(json.dumps(info, indent=2))
        if info.get("demo_password_generated"):
            print("Senha dos usuários de demonstração em var/demo_credentials.txt")
    elif args.cmd == "demo-load":
        res = load_demo(db, lake, args.scenario, reset=not args.no_reset)
        print(json.dumps({"status": res["status"], "error": res.get("error"),
                          "steps": [(s["step"], s["status"], s["ms"]) for s in res["steps"]]}, indent=2, ensure_ascii=False))
    elif args.cmd == "pipeline":
        from data_platform.pipelines.runner import run_pipeline
        res = run_pipeline(db, lake, SYSTEM_PRINCIPAL, sync=not args.no_sync)
        print(json.dumps({"status": res["status"], "error": res.get("error")}, indent=2))
    elif args.cmd == "monitor":
        from agents.supervisor.agent import Supervisor
        res = Supervisor(db, lake).run_monitoring_cycle(SYSTEM_PRINCIPAL, auto_investigate=not args.no_investigate)
        print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "status":
        from data_platform.catalog import list_datasets
        from goops_core.incidents import list_incidents
        print(json.dumps({"database": db.health(), "storage": lake.format,
                          "datasets": {d["key"]: d["row_count"] for d in list_datasets(db)},
                          "open_incidents": len(list_incidents(db, only_open=True))}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
