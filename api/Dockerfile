FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

COPY rules_engine rules_engine
COPY extraction extraction
COPY standards_mapper standards_mapper
COPY regulatory_pathway regulatory_pathway
COPY cli.py cli.py
COPY api api

RUN useradd --create-home app
USER app

# Railway injects PORT. One worker keeps the in-memory rate limits and spend cap consistent.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-server-header"]
