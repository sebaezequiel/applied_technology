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
echo Solo se puede abrir desde esta PC. Para usarla desde el celular,
echo segui la guia deploy\windows\despliegue.md (Tailscale, con HTTPS).
echo Si todavia no creaste la clave: python -m backend.seguridad
echo Para apagar Audix, cerra esta ventana.
echo.

start "" http://localhost:8000
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

pause
