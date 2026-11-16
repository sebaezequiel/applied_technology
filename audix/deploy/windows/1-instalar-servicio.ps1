#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Instala Audix como servicio de Windows con NSSM.
  Audix arranca automaticamente cuando enciende la PC,
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
    # Directorio raiz del repositorio (donde esta la carpeta audix\)
    # Si lo dejas vacio, el script intenta detectarlo automaticamente.
    [string]$ProyectoDir = "",

    # Carpeta donde Audix guarda los libros y el indice.
    # Tiene que ser la misma que ya usas en desarrollo.
    [string]$DataDir = "C:\audix-data",

    # Puerto en el que escucha Audix.
    [int]$Puerto = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -- Colores ------------------------------------------------------------------
function OK   { param([string]$m) Write-Host "  [OK] $m" -ForegroundColor Green  }
function INFO { param([string]$m) Write-Host "  - $m" -ForegroundColor Cyan   }
function WARN { param([string]$m) Write-Host "  ! $m" -ForegroundColor Yellow }
function ERR  { param([string]$m) Write-Host "  [ERROR] $m" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Blue
Write-Host "   Audix - Instalacion como servicio       " -ForegroundColor Blue
Write-Host "==========================================" -ForegroundColor Blue
Write-Host ""

# -- 1. Detectar directorio del proyecto --------------------------------------
if ($ProyectoDir -eq "") {
    # Buscar hacia arriba desde el script
    $candidato = Split-Path -Parent $PSScriptRoot  # audix\deploy
    $candidato = Split-Path -Parent $candidato     # audix
    $candidato = Split-Path -Parent $candidato     # raiz del repo
    if (Test-Path "$candidato\audix\backend\main.py") {
        $ProyectoDir = $candidato
        INFO "Proyecto detectado: $ProyectoDir"
    } else {
        ERR "No pude detectar el directorio del proyecto. Ejecuta el script con -ProyectoDir 'C:\ruta\al\repo'"
    }
} else {
    if (-not (Test-Path "$ProyectoDir\audix\backend\main.py")) {
        ERR "No encontre audix\backend\main.py en '$ProyectoDir'. Verifica la ruta."
    }
    INFO "Directorio del proyecto: $ProyectoDir"
}

$AudixDir = Join-Path $ProyectoDir "audix"

# -- 2. Detectar Python / entorno virtual -------------------------------------
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
        WARN "No encontre un venv. Usando Python del sistema: $PythonExe"
        WARN "Se recomienda tener un venv con las dependencias."
    } catch {
        ERR "No encontre Python. Instala Python 3.10+ y/o crea un venv con 'python -m venv .venv'."
    }
}

# Verificar que FastAPI este disponible
$TestImport = & $PythonExe -c "import fastapi; import uvicorn" 2>&1
if ($LASTEXITCODE -ne 0) {
    ERR "Faltan dependencias. Activa tu venv y ejecuta: pip install -r audix/backend/requirements.txt"
}
OK "Dependencias verificadas (fastapi, uvicorn)"

# -- 3. Crear la carpeta de datos ----------------------------------------------
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir | Out-Null
    OK "Carpeta de datos creada: $DataDir"
} else {
    INFO "Carpeta de datos: $DataDir"
}

# Si la carpeta todavia no tiene libros, se copian los de audix\data
# (donde los deja iniciar-audix.bat). Los originales no se tocan.
$DatosViejos = Join-Path $AudixDir "data"
$LibrosNuevos = @(Get-ChildItem -Path $DataDir -Directory -ErrorAction SilentlyContinue |
                  Where-Object { Test-Path (Join-Path $_.FullName "indice.json") })
if ($LibrosNuevos.Count -eq 0 -and (Test-Path $DatosViejos) -and
    ((Resolve-Path $DatosViejos).Path -ne (Resolve-Path $DataDir).Path)) {
    $LibrosViejos = @(Get-ChildItem -Path $DatosViejos -Directory |
                      Where-Object { Test-Path (Join-Path $_.FullName "indice.json") })
    foreach ($Libro in $LibrosViejos) {
        Copy-Item -Path $Libro.FullName -Destination (Join-Path $DataDir $Libro.Name) -Recurse
    }
    if ($LibrosViejos.Count -gt 0) {
        OK "Se copiaron $($LibrosViejos.Count) libros desde $DatosViejos"
    }
}

# Solo el sistema y los administradores pueden leer la carpeta de datos
# (libros, registros y el archivo de la clave). Se usan identificadores fijos
# porque los nombres de los grupos cambian segun el idioma de Windows.
& icacls.exe $DataDir /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" | Out-Null
if ($LASTEXITCODE -eq 0) {
    OK "Carpeta de datos restringida a administradores"
} else {
    WARN "No se pudieron restringir los permisos de $DataDir"
}

# -- 4. Descargar NSSM ---------------------------------------------------------
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
        ERR "No pude descargar NSSM. Chequea tu conexion o descargalo manualmente desde https://nssm.cc y copia nssm.exe a '$NssmDir'."
    }
} else {
    OK "NSSM ya esta instalado"
}

# -- 5. Instalar / actualizar el servicio -------------------------------------
$ServiceName = "Audix"
INFO "Configurando el servicio '$ServiceName'..."

# Si ya existe se reconfigura en el lugar. No se borra y se vuelve a crear:
# Windows tarda en borrar un servicio y la creacion siguiente falla.
$Existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Existing) {
    INFO "El servicio ya existe. Actualizando su configuracion..."
    if ($Existing.Status -ne "Stopped") {
        & $NssmExe stop $ServiceName | Out-Null
    }
    & $NssmExe set $ServiceName Application $PythonExe
} else {
    & $NssmExe install $ServiceName $PythonExe
}

# --host 127.0.0.1: Audix solo atiende conexiones de esta misma PC.
# Desde afuera se entra unicamente por Tailscale (HTTPS); la red local
# (Wi-Fi de casa o de la oficina) no puede conectarse al puerto.
& $NssmExe set     $ServiceName AppParameters   "-m uvicorn backend.main:app --host 127.0.0.1 --port $Puerto"
& $NssmExe set     $ServiceName AppDirectory    $AudixDir
& $NssmExe set     $ServiceName AppEnvironmentExtra "AUDIX_DATA_DIR=$DataDir"
& $NssmExe set     $ServiceName DisplayName     "Audix - Servidor de audiolibros"
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
& $NssmExe set $ServiceName AppRotateBytes     5000000  # 5 MB maximo por archivo

OK "Servicio configurado"

# -- 6. Iniciar el servicio ---------------------------------------------------
INFO "Iniciando servicio..."
& $NssmExe start $ServiceName
Start-Sleep -Seconds 3

$Svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Svc -and $Svc.Status -eq "Running") {
    OK "Servicio corriendo"
} else {
    WARN "El servicio no arranco inmediatamente. Verifica el log en: $LogDir\audix-error.log"
}

# -- 7. Test rapido -----------------------------------------------------------
INFO "Verificando que responde en http://127.0.0.1:$Puerto ..."
Start-Sleep -Seconds 2
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Puerto/health" -UseBasicParsing -TimeoutSec 5
    if ($resp.StatusCode -eq 200) {
        OK "Audix responde correctamente"
    }
} catch {
    WARN "No respondio todavia. Dale unos segundos y proba: Invoke-WebRequest http://127.0.0.1:$Puerto/health -UseBasicParsing"
}

# -- Resumen ------------------------------------------------------------------
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "   Listo. Audix ya es un servicio de Windows." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  URL local:    http://localhost:$Puerto"
Write-Host "  Datos:        $DataDir"
Write-Host "  Logs:         $LogDir"
Write-Host ""
Write-Host "  Comandos utiles:"
Write-Host "    Ver estado:  Get-Service Audix"
Write-Host "    Reiniciar:   Restart-Service Audix"
Write-Host "    Detener:     Stop-Service Audix"
Write-Host "    Ver log:     Get-Content '$LogDir\audix.log' -Tail 50"
Write-Host ""
Write-Host "  Proximos pasos:"
Write-Host "    .\3-crear-clave.ps1          (obligatorio: sin clave no entra nadie)"
Write-Host "    .\2-instalar-tailscale.ps1   (solo la primera vez)"
Write-Host "    .\4-cuenta-servicio.ps1      (recomendado: baja los privilegios del servicio)"
Write-Host ""
