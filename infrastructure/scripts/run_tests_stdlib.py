"""Executor mínimo de testes (para ambientes sem pytest). Uso: python infrastructure/scripts/run_tests_stdlib.py"""
import importlib.util
import sys
import time
import traceback
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "backend" / "tests"
sys.path[:0] = [str(ROOT), str(TESTS)]
import conftest  # noqa: E402,F401

passed, failed, skipped = 0, [], 0
for path in sorted(TESTS.glob("test_*.py")):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in [n for n in dir(mod) if n.startswith("test_")]:
        t0 = time.time()
        try:
            getattr(mod, name)()
            passed += 1
            print(f"PASS {path.stem}::{name} ({time.time() - t0:.1f}s)")
        except unittest.SkipTest as exc:
            skipped += 1
            print(f"SKIP {path.stem}::{name} ({exc})")
        except Exception:
            failed.append(f"{path.stem}::{name}")
            print(f"FAIL {path.stem}::{name}\n{traceback.format_exc()}")
print(f"\n{passed} passed, {len(failed)} failed, {skipped} skipped")
sys.exit(1 if failed else 0)
