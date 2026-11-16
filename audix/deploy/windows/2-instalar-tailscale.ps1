#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Instala Tailscale y expone Audix con HTTPS para acceso desde cualquier lugar.

  Tailscale crea una red privada entre tus dispositivos (PC y Android).
  Con "tailscale serve" le agrega HTTPS automático (certificado válido incluido),
  así la PWA funciona con todas sus funciones (Service Worker, instalación, etc.).

  Tu URL quedará así:
    https://<nombre-de-tu-pc>.<tu-tailnet>.ts.net

  Solo vos (desde tus dispositivos con Tailscale) podés acceder.
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

function OK   { param([string]$m) Write-Host "  ✓ $m" -ForegroundColor Green  }
function INFO { param([string]$m) Write-Host "  · $m" -ForegroundColor Cyan   }
function WARN { param([string]$m) Write-Host "  ! $m" -ForegroundColor Yellow }
function ERR  { param([string]$m) Write-Host "  ✗ $m" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "══════════════════════════════════════════" -ForegroundColor Blue
Write-Host "   Audix · Instalación de Tailscale        " -ForegroundColor Blue
Write-Host "══════════════════════════════════════════" -ForegroundColor Blue
Write-Host ""

# ── 1. Verificar que Audix está corriendo ────────────────────────────────────
INFO "Verificando que el servicio Audix está corriendo..."
$svc = Get-Service -Name "Audix" -ErrorAction SilentlyContinue
if (-not $svc) {
    ERR "No encontré el servicio 'Audix'. Ejecutá primero 1-instalar-servicio.ps1"
}
if ($svc.Status -ne "Running") {
    WARN "El servicio Audix no está corriendo. Intentando iniciarlo..."
    Start-Service Audix
    Start-Sleep -Seconds 3
    $svc = Get-Service -Name "Audix"
    if ($svc.Status -ne "Running") {
        ERR "No se pudo iniciar Audix. Revisá los logs en C:\audix-data\logs\"
    }
}
OK "Audix corriendo"

# ── 2. Instalar Tailscale ────────────────────────────────────────────────────
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
    INFO "Tailscale no está instalado. Instalando con winget..."
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
            ERR "winget instaló Tailscale pero no encontré tailscale.exe. Reiniciá PowerShell como Admin e intentá de nuevo."
        }
        OK "Tailscale instalado: $TailscaleExe"
    } catch {
        Write-Host ""
        WARN "winget no está disponible o falló. Instalá Tailscale manualmente:"
        Write-Host "  1. Entrá a https://tailscale.com/download/windows" -ForegroundColor White
        Write-Host "  2. Descargá e instalá el instalador" -ForegroundColor White
        Write-Host "  3. Volvé a ejecutar este script" -ForegroundColor White
        Write-Host ""
        exit 1
    }
} else {
    OK "Tailscale ya instalado: $TailscaleExe"
}

# ── 3. Verificar que Tailscale está conectado ────────────────────────────────
INFO "Verificando conexión con Tailscale..."

$status = & $TailscaleExe status --json 2>&1 | ConvertFrom-Json -ErrorAction SilentlyContinue

if (-not $status -or $status.BackendState -ne "Running") {
    Write-Host ""
    Write-Host "  ┌─────────────────────────────────────────────────────┐" -ForegroundColor Yellow
    Write-Host "  │  Tailscale necesita que inicies sesión.             │" -ForegroundColor Yellow
    Write-Host "  │                                                     │" -ForegroundColor Yellow
    Write-Host "  │  1. Se va a abrir el navegador con la página        │" -ForegroundColor Yellow
    Write-Host "  │     de autenticación de Tailscale.                  │" -ForegroundColor Yellow
    Write-Host "  │  2. Creá una cuenta gratuita (o usá la que tengas). │" -ForegroundColor Yellow
    Write-Host "  │  3. Autorizá la máquina.                            │" -ForegroundColor Yellow
    Write-Host "  │  4. Volvé aquí y presioná Enter para continuar.     │" -ForegroundColor Yellow
    Write-Host "  └─────────────────────────────────────────────────────┘" -ForegroundColor Yellow
    Write-Host ""

    & $TailscaleExe login

    Write-Host "  Presioná Enter una vez que autorizaste la máquina en Tailscale..." -ForegroundColor Cyan
    Read-Host | Out-Null

    $status = & $TailscaleExe status --json 2>&1 | ConvertFrom-Json -ErrorAction SilentlyContinue
    if (-not $status -or $status.BackendState -ne "Running") {
        ERR "Tailscale no está conectado. Verificá que autorizaste la máquina en https://login.tailscale.com/admin/machines"
    }
}

$MiIP       = $status.TailscaleIPs | Where-Object { $_ -notmatch ":" } | Select-Object -First 1
$MiHostname = $status.Self.DNSName -replace "\.$", ""  # quitar punto final

OK "Tailscale conectado"
INFO "IP Tailscale: $MiIP"
INFO "Hostname:     $MiHostname"

# ── 4. Habilitar HTTPS en el admin (instrucción manual necesaria) ─────────────
Write-Host ""
Write-Host "  ┌─────────────────────────────────────────────────────────────┐" -ForegroundColor Cyan
Write-Host "  │  Paso manual: habilitar HTTPS en el panel de Tailscale.    │" -ForegroundColor Cyan
Write-Host "  │                                                             │" -ForegroundColor Cyan
Write-Host "  │  1. Abrí https://login.tailscale.com/admin/dns             │" -ForegroundColor Cyan
Write-Host "  │  2. Activá 'Enable MagicDNS' (si no está activo)           │" -ForegroundColor Cyan
Write-Host "  │  3. Activá 'Enable HTTPS'                                  │" -ForegroundColor Cyan
Write-Host "  │  4. Guardá los cambios                                     │" -ForegroundColor Cyan
Write-Host "  │                                                             │" -ForegroundColor Cyan
Write-Host "  │  Presioná Enter cuando lo hayas hecho.                     │" -ForegroundColor Cyan
Write-Host "  └─────────────────────────────────────────────────────────────┘" -ForegroundColor Cyan
Write-Host ""
Read-Host "  Enter para continuar" | Out-Null

# ── 5. Configurar tailscale serve ────────────────────────────────────────────
INFO "Configurando 'tailscale serve' para exponer Audix con HTTPS..."

# Limpiar configuración previa si existe
& $TailscaleExe serve reset 2>&1 | Out-Null

# Redirigir HTTPS → http://localhost:PuertoAudix
# --bg: persiste como servicio en segundo plano, sobrevive reinicios
& $TailscaleExe serve --bg "http://localhost:$PuertoAudix"

if ($LASTEXITCODE -ne 0) {
    ERR "Falló 'tailscale serve'. Verificá que HTTPS está habilitado en el panel de Tailscale (paso anterior)."
}

OK "'tailscale serve' configurado"

# ── 6. Obtener la URL final ──────────────────────────────────────────────────
Start-Sleep -Seconds 2
$ServeStatus = & $TailscaleExe serve status 2>&1

# Intentar extraer la URL del output
$URLFinal = ""
if ($MiHostname -ne "") {
    $URLFinal = "https://$MiHostname"
}

# ── 7. Instalar tailscale serve como tarea de inicio ─────────────────────────
# tailscale serve --bg ya persiste en el daemon de Tailscale,
# y el daemon de Tailscale arranca como servicio de Windows automáticamente.
INFO "Verificando que Tailscale arranca automáticamente con Windows..."
$TailscaleSvc = Get-Service -Name "Tailscale" -ErrorAction SilentlyContinue
if ($TailscaleSvc) {
    Set-Service -Name "Tailscale" -StartupType Automatic | Out-Null
    OK "Servicio Tailscale configurado para inicio automático"
} else {
    WARN "No encontré el servicio de Windows de Tailscale. El ícono en la barra del sistema también lo inicia."
}

# ── Resumen final ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "   ¡Todo listo! Audix accesible desde cualquier lugar.   " -ForegroundColor Green
Write-Host "══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
if ($URLFinal -ne "") {
    Write-Host "  Tu URL de Audix:  $URLFinal" -ForegroundColor White
    Write-Host ""
}
Write-Host "  Pasos para tu celular Android:" -ForegroundColor Cyan
Write-Host "    1. Instalá Tailscale desde Play Store (es gratis)."
Write-Host "    2. Iniciá sesión con la misma cuenta."
Write-Host "    3. Abrí Chrome y entrá a:  $URLFinal"
Write-Host "    4. Tres puntos → 'Añadir a pantalla de inicio' → instalar PWA."
Write-Host ""
Write-Host "  Desde ese momento podés usar Audix desde cualquier red,"
Write-Host "  siempre que tu PC esté encendida y conectada a internet."
Write-Host ""
Write-Host "  Comandos útiles:"
Write-Host "    Ver estado:    tailscale serve status"
Write-Host "    Ver conexión:  tailscale status"
Write-Host "    Desactivar:    tailscale serve reset"
Write-Host ""
