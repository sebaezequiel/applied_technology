@echo off
title Audix
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Primera vez: creando entorno virtual e instalando dependencias...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo.
echo Audix esta corriendo en esta PC: http://localhost:8000
echo Desde el celular (misma Wi-Fi) usa la IP de esta PC y el puerto 8000.
echo Para apagar Audix, cerra esta ventana.
echo.

start "" http://localhost:8000
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

pause
