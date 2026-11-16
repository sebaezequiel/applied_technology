#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Instala Audix como servicio de Windows con NSSM.
  Audix arranca automáticamente cuando enciende la PC,
  sin necesidad de que haya un usuario logueado.

.NOTAS
  - Ejecutar desde PowerShell como Administrador.
  - Tener el repositorio clonado y las dependencias instaladas.
  - Si ya existe el servicio, lo reconfigura.

.EJEMPLO
  .\1-instalar-servicio.ps1
  .\1-instalar-servicio.ps1 -ProyectoDir "D:\proyectos\applied_technology"
#>

param(
    # Directorio raíz del repositorio (donde está la carpeta audix\)
    # Si lo dejás vacío, el script intenta detectarlo automáticamente.
    [string]$ProyectoDir = "",

    # Carpeta donde Audix guarda los libros y el índice.
    # Tiene que ser la misma que ya usás en desarrollo.
    [string]$DataDir = "C:\audix-data",

    # Puerto en el que escucha Audix.
    [int]$Puerto = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Colores ──────────────────────────────────────────────────────────────────
function OK   { param([string]$m) Write-Host "  ✓ $m" -ForegroundColor Green  }
function INFO { param([string]$m) Write-Host "  · $m" -ForegroundColor Cyan   }
function WARN { param([string]$m) Write-Host "  ! $m" -ForegroundColor Yellow }
function ERR  { param([string]$m) Write-Host "  ✗ $m" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "══════════════════════════════════════════" -ForegroundColor Blue
Write-Host "   Audix · Instalación como servicio       " -ForegroundColor Blue
Write-Host "══════════════════════════════════════════" -ForegroundColor Blue
Write-Host ""

# ── 1. Detectar directorio del proyecto ──────────────────────────────────────
if ($ProyectoDir -eq "") {
    # Buscar hacia arriba desde el script
    $candidato = Split-Path -Parent $PSScriptRoot  # audix\deploy
    $candidato = Split-Path -Parent $candidato     # audix
    $candidato = Split-Path -Parent $candidato     # raíz del repo
    if (Test-Path "$candidato\audix\backend\main.py") {
        $ProyectoDir = $candidato
        INFO "Proyecto detectado: $ProyectoDir"
    } else {
        ERR "No pude detectar el directorio del proyecto. Ejecutá el script con -ProyectoDir 'C:\ruta\al\repo'"
    }
} else {
    if (-not (Test-Path "$ProyectoDir\audix\backend\main.py")) {
        ERR "No encontré audix\backend\main.py en '$ProyectoDir'. Verificá la ruta."
    }
    INFO "Directorio del proyecto: $ProyectoDir"
}

$BackendDir = Join-Path $ProyectoDir "audix\backend"

# ── 2. Detectar Python / entorno virtual ─────────────────────────────────────
INFO "Buscando Python..."

$PythonExe = ""

# Primero buscar venv dentro del proyecto
$VenvCandidatos = @(
    "$ProyectoDir\.venv\Scripts\python.exe",
    "$ProyectoDir\venv\Scripts\python.exe",
    "$ProyectoDir\audix\.venv\Scripts\python.exe",
    "$ProyectoDir\audix\venv\Scripts\python.exe"
)
foreach ($v in $VenvCandidatos) {
    if (Test-Path $v) {
        $PythonExe = $v
        OK "Venv encontrado: $PythonExe"
        break
    }
}

# Si no hay venv, usar Python del sistema
if ($PythonExe -eq "") {
    try {
        $PythonExe = (Get-Command python -ErrorAction Stop).Source
        WARN "No encontré un venv. Usando Python del sistema: $PythonExe"
        WARN "Se recomienda tener un venv con las dependencias."
    } catch {
        ERR "No encontré Python. Instalá Python 3.10+ y/o creá un venv con 'python -m venv .venv'."
    }
}

# Verificar que FastAPI esté disponible
$TestImport = & $PythonExe -c "import fastapi; import uvicorn" 2>&1
if ($LASTEXITCODE -ne 0) {
    ERR "Faltan dependencias. Activá tu venv y ejecutá: pip install -r audix/backend/requirements.txt"
}
OK "Dependencias verificadas (fastapi, uvicorn)"

# ── 3. Crear la carpeta de datos ──────────────────────────────────────────────
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir | Out-Null
    OK "Carpeta de datos creada: $DataDir"
} else {
    INFO "Carpeta de datos: $DataDir"
}

# ── 4. Descargar NSSM ─────────────────────────────────────────────────────────
INFO "Verificando NSSM..."
$NssmDir  = "$env:ProgramFiles\nssm"
$NssmExe  = "$NssmDir\nssm.exe"

if (-not (Test-Path $NssmExe)) {
    INFO "Descargando NSSM..."
    $NssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
    $Zip     = "$env:TEMP\nssm.zip"
    $Extract = "$env:TEMP\nssm-extract"

    try {
        Invoke-WebRequest -Uri $NssmUrl -OutFile $Zip -UseBasicParsing
        Expand-Archive -Path $Zip -DestinationPath $Extract -Force

        # Detectar arquitectura
        $Arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
        $NssmBin = Get-ChildItem -Path $Extract -Recurse -Filter "nssm.exe" |
                   Where-Object { $_.DirectoryName -like "*$Arch*" } |
                   Select-Object -First 1

        if (-not $NssmBin) {
            $NssmBin = Get-ChildItem -Path $Extract -Recurse -Filter "nssm.exe" | Select-Object -First 1
        }

        New-Item -ItemType Directory -Path $NssmDir -Force | Out-Null
        Copy-Item $NssmBin.FullName $NssmExe

        Remove-Item $Zip     -Force -ErrorAction SilentlyContinue
        Remove-Item $Extract -Recurse -Force -ErrorAction SilentlyContinue

        OK "NSSM instalado en: $NssmExe"
    } catch {
        ERR "No pude descargar NSSM. Chequeá tu conexión o descargalo manualmente desde https://nssm.cc y copiá nssm.exe a '$NssmDir'."
    }
} else {
    OK "NSSM ya está instalado"
}

# ── 5. Instalar / actualizar el servicio ─────────────────────────────────────
$ServiceName = "Audix"
INFO "Configurando el servicio '$ServiceName'..."

# Si ya existe, pararlo y eliminarlo para reconfigurar
$Existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Existing) {
    WARN "El servicio ya existe. Reconfigurando..."
    if ($Existing.Status -eq "Running") {
        & $NssmExe stop $ServiceName confirm | Out-Null
    }
    & $NssmExe remove $ServiceName confirm | Out-Null
}

# Instalar
& $NssmExe install $ServiceName $PythonExe
& $NssmExe set     $ServiceName AppParameters   "-m uvicorn main:app --host 0.0.0.0 --port $Puerto"
& $NssmExe set     $ServiceName AppDirectory    $BackendDir
& $NssmExe set     $ServiceName AppEnvironmentExtra "AUDIX_DATA_DIR=$DataDir"
& $NssmExe set     $ServiceName DisplayName     "Audix – Servidor de audiolibros"
& $NssmExe set     $ServiceName Description     "Backend FastAPI de Audix. Sirve la API y el frontend PWA."
& $NssmExe set     $ServiceName Start           SERVICE_AUTO_START
& $NssmExe set     $ServiceName ObjectName      LocalSystem

# Logs
$LogDir = "$DataDir\logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
& $NssmExe set $ServiceName AppStdout "$LogDir\audix.log"
& $NssmExe set $ServiceName AppStderr "$LogDir\audix-error.log"
& $NssmExe set $ServiceName AppRotateFiles     1
& $NssmExe set $ServiceName AppRotateOnline    1
& $NssmExe set $ServiceName AppRotateBytes     5000000  # 5 MB máximo por archivo

OK "Servicio configurado"

# ── 6. Iniciar el servicio ───────────────────────────────────────────────────
INFO "Iniciando servicio..."
& $NssmExe start $ServiceName
Start-Sleep -Seconds 3

$Svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Svc -and $Svc.Status -eq "Running") {
    OK "Servicio corriendo"
} else {
    WARN "El servicio no arrancó inmediatamente. Verificá el log en: $LogDir\audix-error.log"
}

# ── 7. Test rápido ───────────────────────────────────────────────────────────
INFO "Verificando que responde en http://localhost:$Puerto ..."
Start-Sleep -Seconds 2
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:$Puerto/libros" -UseBasicParsing -TimeoutSec 5
    if ($resp.StatusCode -eq 200) {
        OK "Audix responde correctamente"
    }
} catch {
    WARN "No respondió todavía. Dale unos segundos y probá: Invoke-WebRequest http://localhost:$Puerto/libros"
}

# ── Resumen ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════" -ForegroundColor Green
Write-Host "   Listo. Audix ya es un servicio de Windows." -ForegroundColor Green
Write-Host "══════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  URL local:    http://localhost:$Puerto"
Write-Host "  Datos:        $DataDir"
Write-Host "  Logs:         $LogDir"
Write-Host ""
Write-Host "  Comandos útiles:"
Write-Host "    Ver estado:  Get-Service Audix"
Write-Host "    Reiniciar:   Restart-Service Audix"
Write-Host "    Detener:     Stop-Service Audix"
Write-Host "    Ver log:     Get-Content '$LogDir\audix.log' -Tail 50"
Write-Host ""
Write-Host "  Próximo paso: ejecutá 2-instalar-tailscale.ps1"
Write-Host ""
