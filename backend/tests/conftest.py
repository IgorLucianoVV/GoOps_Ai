import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("APP_ENV", "test")
for k in ("LLM_SMALL_PROVIDER", "LLM_ECONOMY_PROVIDER", "LLM_ADVANCED_PROVIDER"):
    os.environ[k] = "none"
os.environ.setdefault("LOGIN_RATE_LIMIT_PER_MINUTE", "100000")
