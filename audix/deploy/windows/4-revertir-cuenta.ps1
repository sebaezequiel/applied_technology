#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Revierte el servicio Audix a LocalSystem y deshabilita la cuenta de servicio.
  Usar si 4-cuenta-servicio.ps1 dejo el servicio sin arrancar.

.NOTAS
  - Ejecutar desde PowerShell como Administrador.

.EJEMPLO
  .\4-revertir-cuenta.ps1
  .\4-revertir-cuenta.ps1 -NombreUsuario "mi-audix-svc" -BorrarUsuario
#>

param(
    [string]$NombreUsuario = "audix-svc",
    [string]$DataDir       = "C:\audix-data",

    # Si se indica, borra el usuario local ademas de deshabilitarlo
    [switch]$BorrarUsuario
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function OK   { param([string]$m) Write-Host "  [OK] $m" -ForegroundColor Green  }
function INFO { param([string]$m) Write-Host "  - $m"    -ForegroundColor Cyan   }
function WARN { param([string]$m) Write-Host "  ! $m"    -ForegroundColor Yellow }
function ERR  { param([string]$m) Write-Host "  [ERROR] $m" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Blue
Write-Host "   Audix - Revertir a LocalSystem         " -ForegroundColor Blue
Write-Host "==========================================" -ForegroundColor Blue
Write-Host ""

# -- 1. Verificar NSSM y servicio ----------------------------------------------
$ServiceName = "Audix"
$NssmDir = "$env:ProgramFiles\nssm"
$NssmExe = "$NssmDir\nssm.exe"

if (-not (Test-Path $NssmExe)) {
    ERR "No encontre NSSM en '$NssmExe'."
}

$Svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $Svc) {
    ERR "El servicio '$ServiceName' no existe."
}

OK "NSSM y servicio encontrados"

# -- 2. Detener el servicio ---------------------------------------------------
INFO "Deteniendo el servicio '$ServiceName'..."
if ($Svc.Status -ne "Stopped") {
    & $NssmExe stop $ServiceName | Out-Null
    Start-Sleep -Seconds 2
}
OK "Servicio detenido"

# -- 3. Volver a LocalSystem --------------------------------------------------
INFO "Reconfigurando a LocalSystem..."
& $NssmExe set $ServiceName ObjectName LocalSystem | Out-Null
OK "ObjectName vuelto a LocalSystem"

# -- 4. Restaurar permisos de DataDir (sin la cuenta de servicio) -------------
INFO "Restaurando permisos de $DataDir..."
if (Test-Path $DataDir) {
    & icacls.exe $DataDir /inheritance:r `
        /grant:r "*S-1-5-18:(OI)(CI)F" `
        /grant:r "*S-1-5-32-544:(OI)(CI)F" | Out-Null
    if ($LASTEXITCODE -eq 0) {
        OK "Permisos de $DataDir restaurados (SYSTEM + Administrators)"
    } else {
        WARN "No pude restaurar los permisos de $DataDir"
    }
} else {
    INFO "La carpeta $DataDir no existe, nada que restaurar"
}

# -- 5. Deshabilitar (o borrar) el usuario -----------------------------------
$UsuarioExistente = Get-LocalUser -Name $NombreUsuario -ErrorAction SilentlyContinue
if ($UsuarioExistente) {
    if ($BorrarUsuario) {
        Remove-LocalUser -Name $NombreUsuario
        OK "Usuario '$NombreUsuario' eliminado"
    } else {
        Disable-LocalUser -Name $NombreUsuario
        OK "Usuario '$NombreUsuario' deshabilitado (no eliminado)"
        INFO "Para eliminarlo: Remove-LocalUser -Name '$NombreUsuario'"
    }
} else {
    INFO "El usuario '$NombreUsuario' no existe, nada que hacer"
}

# -- 6. Iniciar el servicio ---------------------------------------------------
INFO "Iniciando el servicio con LocalSystem..."
& $NssmExe start $ServiceName | Out-Null
Start-Sleep -Seconds 4

$Svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Svc -and $Svc.Status -eq "Running") {
    OK "Servicio corriendo como LocalSystem"
} else {
    WARN "El servicio no arranco. Revisa el log en: $DataDir\logs\audix-error.log"
}

# Test rapido
$Puerto = 8000
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Puerto/health" -UseBasicParsing -TimeoutSec 5
    if ($resp.StatusCode -eq 200) {
        OK "Audix responde en /health"
    }
} catch {
    WARN "No respondio todavia. Espera unos segundos."
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "   Listo. Audix vuelve a usar LocalSystem. " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
