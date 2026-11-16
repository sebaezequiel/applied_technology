#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Crea una cuenta de servicio local sin privilegios de administrador para Audix
  y configura el servicio para que la use en lugar de LocalSystem.
  Si Audix tiene alguna vulnerabilidad, el dano queda contenido a esa cuenta.

.NOTAS
  - Ejecutar desde PowerShell como Administrador.
  - Ejecutar DESPUES de 1-instalar-servicio.ps1 (el servicio ya tiene que existir).
  - Se puede volver a ejecutar: regenera la contrasena y reconfigura el servicio.
  - Si el servicio no responde con la cuenta nueva, vuelve solo a LocalSystem.

.EJEMPLO
  .\4-cuenta-servicio.ps1
  .\4-cuenta-servicio.ps1 -ProyectoDir "D:\proyectos\applied_technology"
  .\4-cuenta-servicio.ps1 -NombreUsuario "mi-audix-svc"
#>

param(
    [string]$ProyectoDir   = "",
    [string]$DataDir       = "C:\audix-data",
    [string]$NombreUsuario = "audix-svc"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ServiceName = "Audix"
$NssmExe     = "$env:ProgramFiles\nssm\nssm.exe"
$Descripcion = "Cuenta de servicio para Audix."   # 30 caracteres (maximo 48)
$SidAdmins   = "S-1-5-32-544"                      # Administrators: el SID funciona en cualquier idioma de Windows
$Puerto      = 8000

function OK   { param([string]$m) Write-Host "  [OK] $m" -ForegroundColor Green  }
function INFO { param([string]$m) Write-Host "  - $m"    -ForegroundColor Cyan   }
function WARN { param([string]$m) Write-Host "  ! $m"    -ForegroundColor Yellow }
function ERR  { param([string]$m) Write-Host "  [ERROR] $m" -ForegroundColor Red; exit 1 }

# -- Funciones auxiliares -----------------------------------------------------

function New-ClaveAleatoria {
    # Usa un generador criptografico (Get-Random NO lo es).
    param([int]$Largo = 32)
    $chars  = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#%^&*-_'
    $limite = 256 - (256 % $chars.Length)   # descarta bytes para evitar sesgo
    $rng    = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buf    = New-Object byte[] 1
    $sb     = New-Object System.Text.StringBuilder
    try {
        while ($sb.Length -lt $Largo) {
            $rng.GetBytes($buf)
            if ($buf[0] -lt $limite) {
                [void]$sb.Append($chars[$buf[0] % $chars.Length])
            }
        }
    } finally {
        $rng.Dispose()
    }
    return $sb.ToString()
}

function Set-CuentaDelServicio {
    # Cambia la cuenta del servicio por WMI. La clave viaja como argumento de la
    # llamada, NO en la linea de comandos (asi no queda visible en la lista de procesos).
    param(
        [string]$Cuenta,
        [string]$Clave = $null
    )
    $svcWmi  = Get-CimInstance -ClassName Win32_Service -Filter "Name='$ServiceName'"
    $cambios = @{ StartName = $Cuenta }
    if ($Clave) { $cambios['StartPassword'] = $Clave }
    $r = Invoke-CimMethod -InputObject $svcWmi -MethodName Change -Arguments $cambios
    return [int]$r.ReturnValue   # 0 = OK
}

function Set-DenegarInicioInteractivo {
    # Impide iniciar sesion en la PC (local o por escritorio remoto) con la cuenta de servicio.
    # Edita los derechos de usuario con secedit. Devuelve $true si quedo aplicado.
    param([string]$Sid)
    $tmp = Join-Path $env:TEMP ("audix-secedit-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $inf = Join-Path $tmp "cfg.inf"
    $sdb = Join-Path $tmp "cfg.sdb"
    try {
        & secedit.exe /export /cfg $inf /areas USER_RIGHTS /quiet | Out-Null
        if ($LASTEXITCODE -ne 0) { return $false }

        $lineas = New-Object System.Collections.ArrayList
        $lineas.AddRange(@(Get-Content -Path $inf -Encoding Unicode))

        foreach ($derecho in @("SeDenyInteractiveLogonRight", "SeDenyRemoteInteractiveLogonRight")) {
            $idx = -1
            for ($i = 0; $i -lt $lineas.Count; $i++) {
                if ($lineas[$i] -match "^\s*$derecho\s*=") { $idx = $i; break }
            }
            if ($idx -ge 0) {
                $valor = ($lineas[$idx] -split '=', 2)[1].Trim()
                if ($valor -notlike "*$Sid*") {
                    $nuevo = if ($valor) { "$valor,*$Sid" } else { "*$Sid" }
                    $lineas[$idx] = "$derecho = $nuevo"
                }
            } else {
                $ph = $lineas.IndexOf("[Privilege Rights]")
                if ($ph -lt 0) { return $false }
                $lineas.Insert($ph + 1, "$derecho = *$Sid")
            }
        }

        Set-Content -Path $inf -Value $lineas -Encoding Unicode
        & secedit.exe /configure /db $sdb /cfg $inf /areas USER_RIGHTS /quiet | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

function Test-SaludAudix {
    param([int]$Intentos = 10)
    for ($i = 0; $i -lt $Intentos; $i++) {
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Puerto/health" -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
    }
    return $false
}

function Restore-LocalSystem {
    & $NssmExe stop $ServiceName | Out-Null
    Start-Sleep -Seconds 2
    $ret = Set-CuentaDelServicio -Cuenta "LocalSystem"
    & $NssmExe start $ServiceName | Out-Null
    return $ret
}

function Show-LogErrores {
    $LogFile = "$DataDir\logs\audix-error.log"
    if (Test-Path $LogFile) {
        Write-Host ""
        Write-Host "Ultimas lineas del log de errores:" -ForegroundColor Yellow
        Get-Content $LogFile -Tail 15 | ForEach-Object { Write-Host "  $_" }
        Write-Host ""
    }
}

# -- Cabecera -----------------------------------------------------------------
Write-Host ""
Write-Host "==========================================" -ForegroundColor Blue
Write-Host "   Audix - Cuenta de servicio dedicada    " -ForegroundColor Blue
Write-Host "==========================================" -ForegroundColor Blue
Write-Host ""

# -- 1. Detectar directorio del proyecto ---------------------------------------
if ($ProyectoDir -eq "") {
    $candidato = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
    if (Test-Path "$candidato\audix\backend\main.py") {
        $ProyectoDir = $candidato
        INFO "Proyecto detectado: $ProyectoDir"
    } else {
        ERR "No pude detectar el directorio del proyecto. Usa -ProyectoDir 'C:\ruta\al\repo'"
    }
} else {
    if (-not (Test-Path "$ProyectoDir\audix\backend\main.py")) {
        ERR "No encontre audix\backend\main.py en '$ProyectoDir'."
    }
    INFO "Directorio del proyecto: $ProyectoDir"
}

$AudixDir = Join-Path $ProyectoDir "audix"

# -- 2. Verificar que el servicio y NSSM existen -------------------------------
if (-not (Test-Path $NssmExe)) {
    ERR "No encontre NSSM en '$NssmExe'. Ejecuta primero .\1-instalar-servicio.ps1"
}
$Svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $Svc) {
    ERR "El servicio '$ServiceName' no existe. Ejecuta primero .\1-instalar-servicio.ps1"
}
OK "NSSM y servicio encontrados"

# -- 3. Obtener la ruta de Python que usa el servicio --------------------------
INFO "Leyendo configuracion del servicio..."
$NssmOutput = (& $NssmExe get $ServiceName Application 2>&1)
$PythonExe  = ""
foreach ($Linea in $NssmOutput) {
    $L = "$Linea".Trim()
    if ($L -like "*python*.exe") { $PythonExe = $L; break }
}
if ($PythonExe -eq "") {
    WARN "No pude leer la ruta de Python desde NSSM. Buscando en el proyecto..."
    $VenvCandidatos = @(
        "$ProyectoDir\.venv\Scripts\python.exe",
        "$ProyectoDir\venv\Scripts\python.exe",
        "$AudixDir\.venv\Scripts\python.exe",
        "$AudixDir\venv\Scripts\python.exe"
    )
    foreach ($v in $VenvCandidatos) {
        if (Test-Path $v) { $PythonExe = $v; break }
    }
}
if ($PythonExe -eq "") {
    ERR "No se detecto Python del servicio. Revisa la configuracion con: nssm get Audix Application"
}
INFO "Python del servicio: $PythonExe"

$VenvRaiz = Split-Path -Parent (Split-Path -Parent $PythonExe)

# Un venv apunta a un Python "base" en otra carpeta (campo home de pyvenv.cfg).
# Si el Python se instalo por usuario (AppData o el perfil), la cuenta de servicio
# no puede leerlo y el servicio no arranca. Hay que darle lectura a esa carpeta.
$PyHome = ""
$PyvenvCfg = Join-Path $VenvRaiz "pyvenv.cfg"
if (Test-Path $PyvenvCfg) {
    foreach ($l in Get-Content $PyvenvCfg) {
        if ($l -match '^\s*home\s*=\s*(.+?)\s*$') { $PyHome = $Matches[1]; break }
    }
}
if ($PyHome) { INFO "Python base del venv: $PyHome" }

# -- 4. Generar la contrasena ---------------------------------------------------
INFO "Generando contrasena aleatoria..."
$Password = New-ClaveAleatoria -Largo 32
OK "Contrasena generada (32 caracteres, se usa una sola vez y no se guarda)"

# -- 5. Crear o actualizar el usuario local ------------------------------------
INFO "Configurando usuario local '$NombreUsuario'..."
$SecPass = ConvertTo-SecureString $Password -AsPlainText -Force
$UsuarioExistente = Get-LocalUser -Name $NombreUsuario -ErrorAction SilentlyContinue
if ($UsuarioExistente) {
    Set-LocalUser -Name $NombreUsuario -Password $SecPass -Description $Descripcion
    if (-not $UsuarioExistente.Enabled) {
        Enable-LocalUser -Name $NombreUsuario
        WARN "El usuario estaba deshabilitado (por 4-revertir-cuenta): se volvio a habilitar"
    }
    INFO "Usuario ya existia: se actualizo la contrasena"
} else {
    New-LocalUser `
        -Name                 $NombreUsuario `
        -Password             $SecPass `
        -Description          $Descripcion `
        -PasswordNeverExpires `
        -UserMayNotChangePassword `
        -AccountNeverExpires | Out-Null
    OK "Usuario '$NombreUsuario' creado"
}
$uSid = (Get-LocalUser -Name $NombreUsuario).SID.Value
Remove-Variable SecPass -ErrorAction SilentlyContinue

# Asegurarse de que NO sea administrador (se busca el grupo por SID, no por nombre,
# porque el nombre cambia segun el idioma de Windows)
$GrupoAdmin = Get-LocalGroup -SID (New-Object System.Security.Principal.SecurityIdentifier($SidAdmins))
$EsAdmin = Get-LocalGroupMember -Group $GrupoAdmin.Name -ErrorAction SilentlyContinue |
           Where-Object { $_.SID.Value -eq $uSid }
if ($EsAdmin) {
    Remove-LocalGroupMember -Group $GrupoAdmin.Name -Member $NombreUsuario
    OK "Se quito del grupo de administradores"
} else {
    OK "No es administrador"
}

# -- 5b. Bloquear inicio de sesion interactivo ---------------------------------
INFO "Bloqueando inicio de sesion local y por escritorio remoto..."
if (Set-DenegarInicioInteractivo -Sid $uSid) {
    OK "La cuenta no puede iniciar sesion en esta PC"
} else {
    WARN "No pude aplicar el bloqueo de inicio de sesion. No es critico: la contrasena es aleatoria."
}

# -- 6. Permisos de lectura sobre el codigo ------------------------------------
# Solo la carpeta audix (no todo el repo, para no exponer .git ni otros proyectos).
INFO "Dando lectura y ejecucion sobre $AudixDir..."
& icacls.exe $AudixDir /grant:r "${NombreUsuario}:(OI)(CI)RX" /T /Q | Out-Null
if ($LASTEXITCODE -eq 0) { OK "Lectura y ejecucion en: $AudixDir" }
else { WARN "No pude aplicar permisos en $AudixDir" }

# Venv fuera de audix: darle acceso tambien
if ($VenvRaiz -and (Test-Path $VenvRaiz) -and
    -not $VenvRaiz.StartsWith($AudixDir, [System.StringComparison]::OrdinalIgnoreCase)) {
    INFO "El venv esta fuera de audix ($VenvRaiz). Dando acceso..."
    & icacls.exe $VenvRaiz /grant:r "${NombreUsuario}:(OI)(CI)RX" /T /Q | Out-Null
    if ($LASTEXITCODE -eq 0) { OK "Lectura y ejecucion en venv: $VenvRaiz" }
    else { WARN "No pude aplicar permisos en $VenvRaiz" }
}

# Python base (si esta en el perfil del usuario, la cuenta de servicio no lo ve)
if ($PyHome -and (Test-Path $PyHome)) {
    INFO "Dando lectura al Python base: $PyHome..."
    & icacls.exe $PyHome /grant:r "${NombreUsuario}:(OI)(CI)RX" /T /Q | Out-Null
    if ($LASTEXITCODE -eq 0) { OK "Lectura en Python base" }
    else { WARN "No pude aplicar permisos en $PyHome. Es probable que el servicio no arranque." }
}

# -- 7. Permisos sobre la carpeta de datos -------------------------------------
# Escritura completa: el servicio crea libros, sesiones, logs y la clave.
INFO "Dando acceso de escritura a la carpeta de datos..."
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir | Out-Null
}
# Se quita la herencia y se da acceso solo a SYSTEM, Administrators y la cuenta de servicio
& icacls.exe $DataDir /inheritance:r `
    /grant:r "*S-1-5-18:(OI)(CI)F" `
    /grant:r "*${SidAdmins}:(OI)(CI)F" `
    /grant:r "${NombreUsuario}:(OI)(CI)M" | Out-Null
if ($LASTEXITCODE -eq 0) { OK "Acceso de escritura a: $DataDir" }
else { WARN "No pude restringir $DataDir. Revisa los permisos manualmente." }

# -- 8. Cambiar la cuenta del servicio -----------------------------------------
INFO "Reconfigurando el servicio '$ServiceName'..."
if ((Get-Service -Name $ServiceName).Status -ne "Stopped") {
    & $NssmExe stop $ServiceName | Out-Null
    Start-Sleep -Seconds 2
}

$ret = Set-CuentaDelServicio -Cuenta ".\$NombreUsuario" -Clave $Password
$Password = $null
if ($ret -ne 0) {
    & $NssmExe start $ServiceName | Out-Null
    ERR "No pude cambiar la cuenta del servicio (codigo WMI $ret). Se mantuvo la cuenta anterior."
}
OK "Servicio configurado para correr como '.\$NombreUsuario'"

# -- 9. Iniciar y verificar. Si falla, volver a LocalSystem automaticamente ----
INFO "Iniciando el servicio y comprobando /health..."
& $NssmExe start $ServiceName | Out-Null

if (Test-SaludAudix -Intentos 10) {
    OK "Audix responde correctamente en /health"
} else {
    WARN "Audix no responde con '$NombreUsuario'. Volviendo a LocalSystem..."
    Show-LogErrores
    $retRb = Restore-LocalSystem
    if ($retRb -eq 0 -and (Test-SaludAudix -Intentos 10)) {
        WARN "Audix volvio a funcionar como LocalSystem."
    } else {
        WARN "Audix no responde ni como LocalSystem. Revisa el log: $DataDir\logs\audix-error.log"
    }
    WARN "Causas probables: el venv o el Python base no son legibles para '$NombreUsuario'."
    exit 1
}

# -- Resumen -------------------------------------------------------------------
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "   Listo. Audix corre como '$NombreUsuario'." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  El servicio ya no usa LocalSystem."
Write-Host "  '$NombreUsuario': sin permisos de administrador, sin inicio de sesion interactivo,"
Write-Host "  solo lectura sobre el codigo y escritura en $DataDir."
Write-Host "  Para revertir: .\4-revertir-cuenta.ps1"
Write-Host ""
