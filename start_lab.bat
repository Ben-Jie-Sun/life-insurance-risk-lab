@echo off
cd /d "%~dp0"
echo Open http://127.0.0.1:8000 after the server starts.
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 run_server.py
) else (
  python run_server.py
)
pause
