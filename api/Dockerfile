# Harara scheduler API. Build from the repo root:
#     docker build -f api/Dockerfile -t harara-api .
#     docker run -p 8000:8000 -e ALLOWED_ORIGINS=http://localhost:3000 harara-api
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# Only the deterministic core and the HTTP layer are needed at runtime.
COPY src/ src/
COPY api/ api/

EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
