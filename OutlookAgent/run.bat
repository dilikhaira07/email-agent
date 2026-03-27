@echo off
cd /d "%~dp0"
echo =======================================
echo   Email Agent — Syncing to Notion...
echo =======================================
python fetch_tasks.py
echo.
echo Done. Press any key to close.
pause >nul
