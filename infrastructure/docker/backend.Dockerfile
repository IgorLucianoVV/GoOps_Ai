FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY goops_core goops_core
COPY data_platform data_platform
COPY agents agents
COPY backend backend
COPY infrastructure/database infrastructure/database
COPY infrastructure/scripts infrastructure/scripts
COPY manage.py manage.py
COPY data data
RUN useradd --create-home goops && mkdir -p /app/var && chown -R goops /app/var
# O entrypoint ajusta a posse de /app/var (disco persistente pode montar como root) e roda a API como "goops".
COPY infrastructure/docker/entrypoint.sh /usr/local/bin/goops-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/goops-entrypoint && chmod 755 /usr/local/bin/goops-entrypoint
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/api/health' % os.environ.get('PORT', '8000'))"
ENTRYPOINT ["goops-entrypoint"]
# PORT: definido pela hospedagem (Render); 8000 no docker compose.
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
