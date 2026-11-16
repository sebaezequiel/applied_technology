#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Crea una cuenta de servicio local sin privilegios de administrador para Audix.
  El servicio deja de correr como LocalSystem y pasa a usar esta cuenta limitada.
  Si Audix tiene alguna vulnerabilidad, el danio queda contenido a esa cuenta.

.NOTAS
  - Ejecutar desde PowerShell como Administrador.
  - Ejecutar DESPUES de 1-instalar-servicio.ps1 (el servicio ya tiene que existir).
  - Se puede volver a ejecutar: regenera la contrasena y reconfigura el servicio.

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

function OK   { param([string]$m) Write-Host "  [OK] $m" -ForegroundColor Green  }
function INFO { param([string]$m) Write-Host "  - $m"    -ForegroundColor Cyan   }
function WARN { param([string]$m) Write-Host "  ! $m"    -ForegroundColor Yellow }
function ERR  { param([string]$m) Write-Host "  [ERROR] $m" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Blue
Write-Host "   Audix - Cuenta de servicio dedicada    " -ForegroundColor Blue
Write-Host "==========================================" -ForegroundColor Blue
Write-Host ""

# -- 1. Detectar directorio del proyecto ---------------------------------------
if ($ProyectoDir -eq "") {
    $candidato = Split-Path -Parent $PSScriptRoot
    $candidato = Split-Path -Parent $candidato
    $candidato = Split-Path -Parent $candidato
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

# -- 2. Verificar que el servicio existe ---------------------------------------
$ServiceName = "Audix"
$NssmDir = "$env:ProgramFiles\nssm"
$NssmExe = "$NssmDir\nssm.exe"

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

# nssm get puede devolver varias lineas; buscar la que sea una ruta a python.exe
$NssmOutput = (& $NssmExe get $ServiceName Application 2>&1)
$PythonExe  = ""
foreach ($Linea in $NssmOutput) {
    $L = "$Linea".Trim()
    if ($L -like "*python*.exe") {
        $PythonExe = $L
        break
    }
}

# Si NSSM no devuelve nada util, buscar el venv en las ubicaciones habituales
if ($PythonExe -eq "") {
    WARN "No pude leer la ruta de Python desde NSSM. Buscando en el proyecto..."
    $VenvCandidatos = @(
        "$ProyectoDir\.venv\Scripts\python.exe",
        "$ProyectoDir\venv\Scripts\python.exe",
        "$ProyectoDir\audix\.venv\Scripts\python.exe",
        "$ProyectoDir\audix\venv\Scripts\python.exe"
    )
    foreach ($v in $VenvCandidatos) {
        if (Test-Path $v) { $PythonExe = $v; break }
    }
}

if ($PythonExe -eq "") {
    WARN "No se detecto la ruta de Python. Los permisos del venv se aplicaran manualmente si hace falta."
}

INFO "Python del servicio: $PythonExe"

# Calcular la raiz del venv (dos niveles arriba de python.exe: venv\Scripts\python.exe)
$VenvScripts = if ($PythonExe -ne "") { Split-Path -Parent $PythonExe } else { "" }
$VenvRaiz    = if ($VenvScripts -ne "") { Split-Path -Parent $VenvScripts } else { "" }

# -- 4. Generar una contrasena fuerte al azar ----------------------------------
INFO "Generando contrasena..."
$Chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#%^&*-_'
$Password = -join ((1..32) | ForEach-Object { $Chars[(Get-Random -Maximum $Chars.Length)] })
$SecPass  = ConvertTo-SecureString $Password -AsPlainText -Force
OK "Contrasena generada (32 caracteres, solo se usa una vez)"

# -- 5. Crear el usuario local (si ya existe, cambia la contrasena) ------------
INFO "Configurando usuario local '$NombreUsuario'..."
$UsuarioExistente = Get-LocalUser -Name $NombreUsuario -ErrorAction SilentlyContinue
if ($UsuarioExistente) {
    Set-LocalUser -Name $NombreUsuario -Password $SecPass
    INFO "Usuario ya existia: se actualizo la contrasena"
} else {
    New-LocalUser `
        -Name                 $NombreUsuario `
        -Password             $SecPass `
        -PasswordNeverExpires `
        -UserMayNotChangePassword `
        -Description          "Cuenta de servicio para Audix. No es una cuenta interactiva."
    OK "Usuario '$NombreUsuario' creado"
}

# Asegurarse de que NO sea administrador
$AdminGroup = "Administrators"
$EsAdmin = Get-LocalGroupMember -Group $AdminGroup -ErrorAction SilentlyContinue |
           Where-Object { $_.Name -like "*$NombreUsuario" }
if ($EsAdmin) {
    Remove-LocalGroupMember -Group $AdminGroup -Member $NombreUsuario -ErrorAction SilentlyContinue
    OK "Se quito del grupo de administradores"
}

# -- 6. Permisos sobre la carpeta del proyecto ---------------------------------
# Lectura y ejecucion: el usuario puede leer el codigo y lanzar Python
# Se agrega sin borrar los permisos ya existentes
INFO "Dando acceso de lectura al directorio del proyecto..."
& icacls.exe $ProyectoDir /grant:r "${NombreUsuario}:(OI)(CI)RX" /T /Q
if ($LASTEXITCODE -eq 0) {
    OK "Lectura y ejecucion en: $ProyectoDir"
} else {
    WARN "No pude aplicar permisos en $ProyectoDir"
}

# Si el venv esta fuera del directorio del proyecto (por ej. en el perfil del usuario)
# tambien hay que dar acceso a el
$VenvFueraDelProyecto = $VenvRaiz -and
                        (Test-Path $VenvRaiz) -and
                        (-not $VenvRaiz.StartsWith($ProyectoDir, [System.StringComparison]::OrdinalIgnoreCase))
if ($VenvFueraDelProyecto) {
    INFO "El venv esta fuera del proyecto ($VenvRaiz). Dando acceso..."
    & icacls.exe $VenvRaiz /grant:r "${NombreUsuario}:(OI)(CI)RX" /T /Q
    if ($LASTEXITCODE -eq 0) {
        OK "Lectura y ejecucion en venv: $VenvRaiz"
    } else {
        WARN "No pude aplicar permisos en $VenvRaiz. Es posible que el servicio no arranque."
        WARN "Si falla, copia el venv dentro de $ProyectoDir y vuelve a ejecutar este script."
    }
}

# -- 7. Permisos sobre la carpeta de datos -------------------------------------
# Escritura completa: el servicio necesita crear sesiones, logs y la clave
INFO "Dando acceso de escritura a la carpeta de datos..."
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir | Out-Null
}

# Reemplazar los permisos de DataDir:
#   SYSTEM              -> control total  (S-1-5-18)
#   Administrators      -> control total  (S-1-5-32-544)
#   audix-svc           -> modificacion   (leer + escribir + crear + borrar dentro)
& icacls.exe $DataDir /inheritance:r `
    /grant:r "*S-1-5-18:(OI)(CI)F" `
    /grant:r "*S-1-5-32-544:(OI)(CI)F" `
    /grant:r "${NombreUsuario}:(OI)(CI)M" | Out-Null
if ($LASTEXITCODE -eq 0) {
    OK "Acceso de escritura a: $DataDir"
} else {
    WARN "No pude restringir $DataDir. Revisa los permisos manualmente."
}

# -- 8. Configurar el servicio para usar la cuenta ----------------------------
INFO "Reconfigurando el servicio '$ServiceName'..."

$EstadoAntes = (Get-Service -Name $ServiceName).Status
if ($EstadoAntes -ne "Stopped") {
    & $NssmExe stop $ServiceName | Out-Null
    Start-Sleep -Seconds 2
}

# ObjectName: ".\usuario" significa usuario local de esta PC
& $NssmExe set $ServiceName ObjectName ".\$NombreUsuario" $Password

if ($LASTEXITCODE -eq 0) {
    OK "Servicio configurado para correr como '.\$NombreUsuario'"
} else {
    WARN "NSSM devolvio un codigo distinto de 0. Puede ser una advertencia, no necesariamente un error."
}

# La contrasena ya no hace falta en memoria
Remove-Variable Password -ErrorAction SilentlyContinue
Remove-Variable SecPass  -ErrorAction SilentlyContinue

# -- 9. Iniciar el servicio y verificar ----------------------------------------
INFO "Iniciando el servicio..."
& $NssmExe start $ServiceName | Out-Null
Start-Sleep -Seconds 4

$Svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Svc -and $Svc.Status -eq "Running") {
    OK "Servicio corriendo"
} else {
    WARN "El servicio no arranco. Revisando el log..."
    $LogDir = "$DataDir\logs"
    if (Test-Path "$LogDir\audix-error.log") {
        Write-Host ""
        Write-Host "Ultimas lineas del log de errores:" -ForegroundColor Yellow
        Get-Content "$LogDir\audix-error.log" -Tail 15 | ForEach-Object { Write-Host "  $_" }
        Write-Host ""
    }
    WARN "Posibles causas:"
    WARN "  - El venv no es accesible para '$NombreUsuario'. Copia el venv al directorio del proyecto."
    WARN "  - Faltan permisos en alguna carpeta del PATH de Python."
    WARN ""
    WARN "Para revertir y volver a LocalSystem: .\4-revertir-cuenta.ps1"
    exit 1
}

# Test de salud
$Puerto = 8000
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Puerto/health" -UseBasicParsing -TimeoutSec 5
    if ($resp.StatusCode -eq 200) {
        OK "Audix responde correctamente en /health"
    }
} catch {
    WARN "Audix arranco pero no respondio a /health todavia."
    WARN "Espera unos segundos y prueba: Invoke-WebRequest http://127.0.0.1:$Puerto/health -UseBasicParsing"
}

# -- Resumen -------------------------------------------------------------------
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "   Listo. Audix corre como '$NombreUsuario'." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  El servicio ya no usa LocalSystem."
Write-Host "  '$NombreUsuario' solo puede leer el codigo y escribir en $DataDir."
Write-Host "  Si falla algo, revertir es simple:"
Write-Host ""
Write-Host "    .\4-revertir-cuenta.ps1"
Write-Host ""
