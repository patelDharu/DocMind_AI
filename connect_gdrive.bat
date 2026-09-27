@echo off
title DocMind AI - Connect Google Drive MCP
cd /d "D:\docmind-ai"

echo ============================================================
echo      Starting DocMind AI Google Drive Connector
echo ============================================================
echo.

.\venv\Scripts\python.exe connect_gdrive.py

echo.
pause
