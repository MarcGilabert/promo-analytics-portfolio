FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY copilot/requirements.txt copilot/requirements.txt
RUN pip install -r copilot/requirements.txt

COPY . .

# Cloud Run inyecta PORT (8080 por defecto)
CMD streamlit run copilot/app.py \
    --server.port=${PORT:-8080} \
    --server.address=0.0.0.0 \
    --server.headless=true
