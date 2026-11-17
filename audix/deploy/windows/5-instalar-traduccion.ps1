#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Instala la traduccion de libros (opcional): el motor Argos Translate y los
  modelos ingles-espanol y espanol-ingles. Corre todo en la PC, sin costo.

  Los modelos se guardan en <carpeta de datos>\modelos-traduccion, para que el
  servicio de Audix los encuentre (no en la carpeta de tu usuario).

.NOTAS
  - Ejecutar desde PowerShell como Administrador, con internet.
  - Descarga varios cientos de MB. Puede tardar unos minutos.
  - Al terminar reinicia el servicio Audix.
  - Para quitarla: .\5-instalar-traduccion.ps1 -Quitar

.EJEMPLO
  .\5-instalar-traduccion.ps1
#>

param(
    # Tiene que ser la misma carpeta de datos que usa el servicio.
    [string]$DataDir = "C:\audix-data",
    [string]$ServiceName = "Audix",
    [switch]$Quitar
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$AudixDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path "$AudixDir\requirements-traduccion.txt")) {
    Write-Host "  [ERROR] No encontre requirements-traduccion.txt en $AudixDir. Actualiza el repositorio (git pull)." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $DataDir)) {
    Write-Host "  [ERROR] No existe $DataDir. Ejecuta primero 1-instalar-servicio.ps1" -ForegroundColor Red
    exit 1
}

$PythonExe = ""
foreach ($Candidato in @("$AudixDir\.venv\Scripts\python.exe", "$AudixDir\venv\Scripts\python.exe",
                         "$AudixDir\..\.venv\Scripts\python.exe", "$AudixDir\..\venv\Scripts\python.exe")) {
    if (Test-Path $Candidato) { $PythonExe = $Candidato; break }
}
if ($PythonExe -eq "") {
    Write-Host "  [ERROR] No encontre el entorno virtual (.venv) de Audix." -ForegroundColor Red
    exit 1
}

if ($Quitar) {
    & $PythonExe -m pip uninstall -y argostranslate
    if (Test-Path "$DataDir\modelos-traduccion") { Remove-Item -Recurse -Force "$DataDir\modelos-traduccion" }
    Restart-Service $ServiceName
    Write-Host "  [OK] Traduccion quitada. El resto de Audix sigue igual." -ForegroundColor Green
    exit 0
}

$env:AUDIX_DATA_DIR = $DataDir
Push-Location $AudixDir
try {
    Write-Host "  1/3 Instalando el motor de traduccion..."
    & $PythonExe -m pip install -r requirements-traduccion.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] No se pudo instalar el motor (revisa el mensaje de arriba)." -ForegroundColor Red
        Write-Host "          Audix sigue funcionando igual; solo falta la traduccion." -ForegroundColor Yellow
        exit 1
    }

    Write-Host "  2/3 Descargando los modelos de idioma..."
    & $PythonExe -m backend.pipeline.traductor --instalar
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] No se pudieron instalar los modelos." -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host "  3/3 Reiniciando el servicio $ServiceName..."
Restart-Service $ServiceName

Write-Host ""
Write-Host "  [OK] Traduccion lista. Abri un libro, toca los tres puntitos y elegi Traducir." -ForegroundColor Green
Write-Host ""
