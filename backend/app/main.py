"""GoOps AI — API (FastAPI).

Executar (na raiz do repositório):  uvicorn backend.app.main:app --reload --port 8000
Documentação OpenAPI: /api/docs
"""
from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from goops_core.config import get_settings
from goops_core.errors import GoOpsError

from .api.routes import analytics, core, data, ops, semantic, sectors, support
from .core.runtime import startup
from .security.ratelimit import DatabaseLimiter, SlidingWindowLimiter, client_key

log = logging.getLogger("goops.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup()
    if os.environ.get("SCHEDULER_ENABLED", "true").lower() == "true":
        from goops_core.db import get_db
        from data_platform.storage import get_lakehouse
        from agents.scheduler import start_scheduler
        start_scheduler(get_db(), get_lakehouse())  # jobs habilitados/intervalos são configurados na tela Settings
        from agents.team_channel import start_poller
        start_poller(get_db(), get_lakehouse())     # bot do Telegram (só age se o canal do time for "telegram")
    yield
    from agents.scheduler import stop_scheduler
    from agents.team_channel import stop_poller
    stop_scheduler()
    stop_poller()


settings = get_settings()
app = FastAPI(title="GoOps AI API", version="0.1.0", lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json", redoc_url=None,
              description="Plataforma de inteligência operacional: Data Lakehouse governado, métricas semânticas e "
                          "agentes de IA supervisionados. Respostas no envelope {data, meta}; erros em {error}.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_origin_regex=None if settings.is_production else r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
                   allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"])
if os.environ.get("RATE_LIMIT_BACKEND", "memory").lower() == "database":
    from goops_core.db import get_db
    limiter = DatabaseLimiter(get_db(), settings.rate_limit_per_minute)
else:
    limiter = SlidingWindowLimiter(settings.rate_limit_per_minute)
# Força bruta de senha: limite próprio e baixo para o login (por IP), independente do limite geral.
login_limiter = SlidingWindowLimiter(int(os.environ.get("LOGIN_RATE_LIMIT_PER_MINUTE", "10")))


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    peer = request.client.host if request.client else "unknown"
    client = client_key(peer, request.headers.get("x-forwarded-for"))
    allowed = True
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        allowed = await run_in_threadpool(limiter.allow, client)
    if allowed and request.url.path == "/api/auth/login" and request.method == "POST":
        allowed = login_limiter.allow(client)
    if not allowed:
        return JSONResponse(status_code=429, content={"error": {"code": "rate_limited",
                                                                "message": "Muitas requisições. Tente novamente."}})
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(GoOpsError)
async def goops_error(request: Request, exc: GoOpsError):
    return JSONResponse(status_code=exc.status, content={"error": exc.to_dict()})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error",
                                                            "message": "Payload inválido.", "details": details}})


@app.exception_handler(FileNotFoundError)
async def not_built(request: Request, exc: FileNotFoundError):
    return JSONResponse(status_code=409, content={"error": {"code": "data_not_ready", "message": str(exc)}})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": {"code": "internal_error",
                                                            "message": "Erro interno. Consulte os logs do servidor."}})


for r in (core.router, data.router, semantic.router, analytics.router, ops.router, sectors.router, support.router, support.team):
    app.include_router(r, prefix="/api")
