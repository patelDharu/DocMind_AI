@echo off
title DocMind AI Launcher
echo ===================================================
echo             Starting DocMind AI Platform
echo ===================================================

cd /d "D:\docmind-ai"

echo [1/2] Starting FastAPI Backend (Port 8000)...
start "DocMind Backend" cmd /k ".\venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Streamlit Frontend (Port 7860)...
start "DocMind Frontend" cmd /k ".\venv\Scripts\streamlit.exe run frontend/streamlit_app.py --server.port=7860 --server.address=0.0.0.0"

echo.
echo Opening browser at http://localhost:7860 ...
start http://localhost:7860

echo ===================================================
echo DocMind AI is now running!
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://localhost:7860
echo ===================================================
