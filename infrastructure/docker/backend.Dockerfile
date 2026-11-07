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
USER goops
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
