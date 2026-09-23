#!/bin/bash
set -e

# Detect Python binary
if command -v python3 &>/dev/null; then
    PY_BIN="python3"
else
    PY_BIN="python"
fi

echo "=== Starting DocMind AI Backend (FastAPI on port 8000) using $PY_BIN ==="
$PY_BIN -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 &
FASTAPI_PID=$!

echo "=== Waiting for FastAPI backend to initialize... ==="
READY=0
for i in {1..40}; do
    if $PY_BIN -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" &>/dev/null; then
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

PORT="${PORT:-10000}"
echo "=== Starting DocMind AI Frontend (Streamlit on port $PORT) using $PY_BIN ==="
exec $PY_BIN -m streamlit run frontend/streamlit_app.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.maxUploadSize=25 \
    --server.maxMessageSize=50
