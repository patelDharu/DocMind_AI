Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "           Starting DocMind AI Platform            " -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

Set-Location -Path "D:\docmind-ai"

Write-Host "[1/2] Launching FastAPI Backend on Port 8000..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'D:\docmind-ai'; .\venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000"

Start-Sleep -Seconds 3

Write-Host "[2/2] Launching Streamlit Frontend on Port 7860..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'D:\docmind-ai'; .\venv\Scripts\streamlit.exe run frontend/streamlit_app.py --server.port=7860 --server.address=0.0.0.0"

Start-Sleep -Seconds 2
Start-Process "http://localhost:7860"

Write-Host "Done! Browser opened at http://localhost:7860" -ForegroundColor Green
