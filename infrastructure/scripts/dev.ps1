# Execução local no Windows (sem Docker). Requer Python 3.11+ e Node 20+.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent | Split-Path -Parent)
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Criado .env a partir de .env.example — defina DEMO_ADMIN_PASSWORD." }
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements-dev.txt
.\.venv\Scripts\python manage.py init
.\.venv\Scripts\python manage.py demo-load --scenario full
Start-Process -NoNewWindow .\.venv\Scripts\python -ArgumentList "-m","uvicorn","backend.app.main:app","--reload","--port","8000"
Set-Location frontend
npm install
npm run dev
