@echo off
echo Demarrage du backend Talan sur le port 8001...
cd /d "%~dp0backend"
if exist venv\Scripts\uvicorn.exe (
    venv\Scripts\uvicorn.exe app.main:app --reload --host 0.0.0.0 --port 8001
) else (
    python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
)
pause
