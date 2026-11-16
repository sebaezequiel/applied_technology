#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Instala Tailscale y expone Audix con HTTPS para acceso desde cualquier lugar.

  Tailscale crea una red privada entre tus dispositivos (PC y Android).
  Con "tailscale serve" le agrega HTTPS automatico (certificado valido incluido),
  asi la PWA funciona con todas sus funciones (Service Worker, instalacion, etc.).

  Tu URL quedara asi:
    https://<nombre-de-tu-pc>.<tu-tailnet>.ts.net

  Solo vos (desde tus dispositivos con Tailscale) podes acceder.
  No hace falta abrir puertos ni tocar el router.

.NOTAS
  - Ejecutar desde PowerShell como Administrador.
  - Audix debe estar corriendo (haber ejecutado 1-instalar-servicio.ps1 antes).

.EJEMPLO
  .\2-instalar-tailscale.ps1
#>

param(
    [int]$PuertoAudix = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function OK   { param([string]$m) Write-Host "  [OK] $m" -ForegroundColor Green  }
function INFO { param([string]$m) Write-Host "  - $m" -ForegroundColor Cyan   }
function WARN { param([string]$m) Write-Host "  ! $m" -ForegroundColor Yellow }
function ERR  { param([string]$m) Write-Host "  [ERROR] $m" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Blue
Write-Host "   Audix - Instalacion de Tailscale        " -ForegroundColor Blue
Write-Host "==========================================" -ForegroundColor Blue
Write-Host ""

# -- 1. Verificar que Audix esta corriendo ------------------------------------
INFO "Verificando que el servicio Audix esta corriendo..."
$svc = Get-Service -Name "Audix" -ErrorAction SilentlyContinue
if (-not $svc) {
    ERR "No encontre el servicio 'Audix'. Ejecuta primero 1-instalar-servicio.ps1"
}
if ($svc.Status -ne "Running") {
    WARN "El servicio Audix no esta corriendo. Intentando iniciarlo..."
    Start-Service Audix
    Start-Sleep -Seconds 3
    $svc = Get-Service -Name "Audix"
    if ($svc.Status -ne "Running") {
        ERR "No se pudo iniciar Audix. Revisa los logs en C:\audix-data\logs\"
    }
}
OK "Audix corriendo"

# -- 2. Instalar Tailscale ----------------------------------------------------
INFO "Verificando Tailscale..."
$TailscaleExe = ""

# Buscar en rutas habituales
$Candidatos = @(
    "$env:ProgramFiles\Tailscale\tailscale.exe",
    "C:\Program Files\Tailscale\tailscale.exe"
)
foreach ($c in $Candidatos) {
    if (Test-Path $c) { $TailscaleExe = $c; break }
}

# Buscar en PATH
if ($TailscaleExe -eq "") {
    try {
        $TailscaleExe = (Get-Command tailscale -ErrorAction Stop).Source
    } catch {}
}

if ($TailscaleExe -eq "") {
    INFO "Tailscale no esta instalado. Instalando con winget..."
    try {
        winget install --id Tailscale.Tailscale --silent --accept-package-agreements --accept-source-agreements
        # Volver a buscar
        Start-Sleep -Seconds 5
        foreach ($c in $Candidatos) {
            if (Test-Path $c) { $TailscaleExe = $c; break }
        }
        if ($TailscaleExe -eq "") {
            try { $TailscaleExe = (Get-Command tailscale -ErrorAction Stop).Source } catch {}
        }
        if ($TailscaleExe -eq "") {
            ERR "winget instalo Tailscale pero no encontre tailscale.exe. Reinicia PowerShell como Admin e intenta de nuevo."
        }
        OK "Tailscale instalado: $TailscaleExe"
    } catch {
        Write-Host ""
        WARN "winget no esta disponible o fallo. Instala Tailscale manualmente:"
        Write-Host "  1. Entra a https://tailscale.com/download/windows" -ForegroundColor White
        Write-Host "  2. Descarga e instala el instalador" -ForegroundColor White
        Write-Host "  3. Volve a ejecutar este script" -ForegroundColor White
        Write-Host ""
        exit 1
    }
} else {
    OK "Tailscale ya instalado: $TailscaleExe"
}

# -- 3. Verificar que Tailscale esta conectado --------------------------------
INFO "Verificando conexion con Tailscale..."

$status = & $TailscaleExe status --json 2>&1 | ConvertFrom-Json -ErrorAction SilentlyContinue

if (-not $status -or $status.BackendState -ne "Running") {
    Write-Host ""
    Write-Host "  +-----------------------------------------------------+" -ForegroundColor Yellow
    Write-Host "  |  Tailscale necesita que inicies sesion.             |" -ForegroundColor Yellow
    Write-Host "  |                                                     |" -ForegroundColor Yellow
    Write-Host "  |  1. Se va a abrir el navegador con la pagina        |" -ForegroundColor Yellow
    Write-Host "  |     de autenticacion de Tailscale.                  |" -ForegroundColor Yellow
    Write-Host "  |  2. Crea una cuenta gratuita (o usa la que tengas). |" -ForegroundColor Yellow
    Write-Host "  |  3. Autoriza la maquina.                            |" -ForegroundColor Yellow
    Write-Host "  |  4. Volve aqui y presiona Enter para continuar.     |" -ForegroundColor Yellow
    Write-Host "  +-----------------------------------------------------+" -ForegroundColor Yellow
    Write-Host ""

    & $TailscaleExe login

    Write-Host "  Presiona Enter una vez que autorizaste la maquina en Tailscale..." -ForegroundColor Cyan
    Read-Host | Out-Null

    $status = & $TailscaleExe status --json 2>&1 | ConvertFrom-Json -ErrorAction SilentlyContinue
    if (-not $status -or $status.BackendState -ne "Running") {
        ERR "Tailscale no esta conectado. Verifica que autorizaste la maquina en https://login.tailscale.com/admin/machines"
    }
}

$MiIP       = $status.TailscaleIPs | Where-Object { $_ -notmatch ":" } | Select-Object -First 1
$MiHostname = $status.Self.DNSName -replace "\.$", ""  # quitar punto final

OK "Tailscale conectado"
INFO "IP Tailscale: $MiIP"
INFO "Hostname:     $MiHostname"

# -- 4. Habilitar HTTPS en el admin (instruccion manual necesaria) -------------
Write-Host ""
Write-Host "  +-------------------------------------------------------------+" -ForegroundColor Cyan
Write-Host "  |  Paso manual: habilitar HTTPS en el panel de Tailscale.    |" -ForegroundColor Cyan
Write-Host "  |                                                             |" -ForegroundColor Cyan
Write-Host "  |  1. Abri https://login.tailscale.com/admin/dns             |" -ForegroundColor Cyan
Write-Host "  |  2. Activa 'Enable MagicDNS' (si no esta activo)           |" -ForegroundColor Cyan
Write-Host "  |  3. Activa 'Enable HTTPS'                                  |" -ForegroundColor Cyan
Write-Host "  |  4. Guarda los cambios                                     |" -ForegroundColor Cyan
Write-Host "  |                                                             |" -ForegroundColor Cyan
Write-Host "  |  Presiona Enter cuando lo hayas hecho.                     |" -ForegroundColor Cyan
Write-Host "  +-------------------------------------------------------------+" -ForegroundColor Cyan
Write-Host ""
Read-Host "  Enter para continuar" | Out-Null

# -- 5. Configurar tailscale serve --------------------------------------------
INFO "Configurando 'tailscale serve' para exponer Audix con HTTPS..."

# Limpiar configuracion previa si existe
& $TailscaleExe serve reset 2>&1 | Out-Null

# Redirigir HTTPS -> http://localhost:PuertoAudix
# --bg: persiste como servicio en segundo plano, sobrevive reinicios
& $TailscaleExe serve --bg "http://localhost:$PuertoAudix"

if ($LASTEXITCODE -ne 0) {
    ERR "Fallo 'tailscale serve'. Verifica que HTTPS esta habilitado en el panel de Tailscale (paso anterior)."
}

OK "'tailscale serve' configurado"

# -- 6. Obtener la URL final --------------------------------------------------
Start-Sleep -Seconds 2
$ServeStatus = & $TailscaleExe serve status 2>&1

# Intentar extraer la URL del output
$URLFinal = ""
if ($MiHostname -ne "") {
    $URLFinal = "https://$MiHostname"
}

# -- 7. Instalar tailscale serve como tarea de inicio -------------------------
# tailscale serve --bg ya persiste en el daemon de Tailscale,
# y el daemon de Tailscale arranca como servicio de Windows automaticamente.
INFO "Verificando que Tailscale arranca automaticamente con Windows..."
$TailscaleSvc = Get-Service -Name "Tailscale" -ErrorAction SilentlyContinue
if ($TailscaleSvc) {
    Set-Service -Name "Tailscale" -StartupType Automatic | Out-Null
    OK "Servicio Tailscale configurado para inicio automatico"
} else {
    WARN "No encontre el servicio de Windows de Tailscale. El icono en la barra del sistema tambien lo inicia."
}

# -- Resumen final -------------------------------------------------------------
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "   Todo listo! Audix accesible desde cualquier lugar.   " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""
if ($URLFinal -ne "") {
    Write-Host "  Tu URL de Audix:  $URLFinal" -ForegroundColor White
    Write-Host ""
}
Write-Host "  Pasos para tu celular Android:" -ForegroundColor Cyan
Write-Host "    1. Instala Tailscale desde Play Store (es gratis)."
Write-Host "    2. Inicia sesion con la misma cuenta."
Write-Host "    3. Abri Chrome y entra a:  $URLFinal"
Write-Host "    4. Tres puntos -> 'Anadir a pantalla de inicio' -> instalar PWA."
Write-Host ""
Write-Host "  Desde ese momento podes usar Audix desde cualquier red,"
Write-Host "  siempre que tu PC este encendida y conectada a internet."
Write-Host ""
Write-Host "  Comandos utiles:"
Write-Host "    Ver estado:    tailscale serve status"
Write-Host "    Ver conexion:  tailscale status"
Write-Host "    Desactivar:    tailscale serve reset"
Write-Host ""
