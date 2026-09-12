#!/bin/bash
set -e

echo "=== Starting DocMind AI Backend (FastAPI on port 8000) ==="
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 &

echo "=== Waiting for FastAPI backend to initialize... ==="
for i in {1..30}; do
    if curl -s http://127.0.0.1:8000/health > /dev/null; then
        echo "=== FastAPI backend is healthy! ==="
        break
    fi
    sleep 1
done

echo "=== Starting DocMind AI Frontend (Streamlit on port 7860) ==="
exec streamlit run frontend/streamlit_app.py \
    --server.port=7860 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false
