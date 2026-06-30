FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Cloud Run injects $PORT (8080). The agent serves the A2A card + JSON-RPC there.
CMD ["sh", "-c", "uvicorn gam_sentinel.agent:a2a_app --host 0.0.0.0 --port ${PORT:-8080}"]
