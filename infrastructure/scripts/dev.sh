#!/usr/bin/env bash
# Execução local (Linux/macOS) sem Docker. Requer Python 3.11+ e Node 20+.
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -f .env ] || { cp .env.example .env; echo "Criado .env — defina DEMO_ADMIN_PASSWORD."; }
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
python manage.py init && python manage.py demo-load --scenario full
uvicorn backend.app.main:app --reload --port 8000 &
cd frontend && npm install && npm run dev
