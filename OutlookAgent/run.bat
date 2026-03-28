@echo off
cd /d "%~dp0"
echo =======================================
echo   Email Agent — Running Canonical Sync...
echo =======================================
python -m OutlookAgent.fetch_tasks
echo.
echo Done. Press any key to close.
pause >nul
