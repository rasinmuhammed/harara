# Hugging Face Space (Docker SDK) for the Harara scheduler API.
#
# HF builds ./Dockerfile at the Space repo root and serves the app on the port
# set by `app_port` in the Space README frontmatter (7860 here). Containers on
# Spaces run as uid 1000, so we create that user and install under $HOME.
#
# Local parity:
#     docker build -t harara-api .
#     docker run -p 7860:7860 -e ALLOWED_ORIGINS=http://localhost:3000 harara-api
FROM python:3.11-slim

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/home/user/app \
    HARARA_FORECAST_SOURCE=open-meteo
WORKDIR /home/user/app

COPY --chown=user api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir --user -r api/requirements.txt

# Only the deterministic core and the HTTP layer are needed at runtime.
COPY --chown=user src/ src/
COPY --chown=user api/ api/

EXPOSE 7860
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]
