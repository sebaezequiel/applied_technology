#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Crea o cambia la clave de acceso de Audix.

  La clave se pide dos veces y no se muestra al escribir. No se guarda en
  claro: en disco queda solo un derivado (scrypt) dentro de la carpeta de datos.
  Cambiar la clave cierra todas las sesiones abiertas (celular incluido).

.NOTAS
  - Ejecutar desde PowerShell como Administrador.
  - No hace falta reiniciar el servicio: la clave nueva rige al instante.

.EJEMPLO
  .\3-crear-clave.ps1
#>

param(
    # Tiene que ser la misma carpeta de datos que usa el servicio.
    [string]$DataDir = "C:\audix-data"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$AudixDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path "$AudixDir\backend\seguridad.py")) {
    Write-Host "  [ERROR] No encontre backend\seguridad.py en $AudixDir. Actualiza el repositorio (git pull)." -ForegroundColor Red
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

$env:AUDIX_DATA_DIR = $DataDir
Push-Location $AudixDir
try {
    & $PythonExe -m backend.seguridad
    $Resultado = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($Resultado -eq 0) {
    Write-Host ""
    Write-Host "  [OK] Ya podes entrar a Audix con la clave nueva." -ForegroundColor Green
    Write-Host ""
}
exit $Resultado
