#!/bin/bash
set -e

echo "=== Starting DocMind AI Backend (FastAPI on port 8000) ==="
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 &
FASTAPI_PID=$!

echo "=== Waiting for FastAPI backend to initialize... ==="
READY=0
for i in {1..35}; do
    if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
        echo "=== FastAPI backend is healthy! (PID: $FASTAPI_PID) ==="
        READY=1
        break
    fi
    if ! kill -0 $FASTAPI_PID 2>/dev/null; then
        echo "=== ERROR: FastAPI process exited unexpectedly! ==="
        wait $FASTAPI_PID
        exit 1
    fi
    sleep 1
done

PORT="${PORT:-7860}"
echo "=== Starting DocMind AI Frontend (Streamlit on port $PORT) ==="
exec streamlit run frontend/streamlit_app.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.maxUploadSize=25
