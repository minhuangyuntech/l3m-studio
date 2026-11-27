@echo off
cd /d "%~dp0"
echo Starting L3M Studio Web Server at http://127.0.0.1:18765 ...
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:18765"
backend\.venv\Scripts\python.exe backend\main.py --host 127.0.0.1 --port 18765
