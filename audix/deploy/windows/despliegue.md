# Audix: despliegue en Windows con acceso remoto

Después de seguir esta guía, Audix:

- Arranca sola cuando encendés la PC.
- Se usa desde el celular en cualquier red, con una dirección HTTPS fija.
- Pide una clave para entrar y no es visible para nadie fuera de tus dispositivos.

Todo es gratuito:

| Herramienta | Para qué |
|---|---|
| [NSSM](https://nssm.cc) | Corre Audix como servicio de Windows |
| [Tailscale](https://tailscale.com) (plan Personal) | Red privada entre tus dispositivos, con HTTPS |

## Requisitos

- Windows 10 u 11 de 64 bits.
- El repositorio clonado y el entorno virtual creado (alcanza con haber abierto `iniciar-audix.bat` una vez).
- PowerShell abierto **como administrador** para los tres scripts.

## Instalación

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
cd C:\ruta\al\repo\applied_technology\audix\deploy\windows

.\1-instalar-servicio.ps1     # Audix como servicio
.\3-crear-clave.ps1           # clave de acceso (obligatoria)
.\2-instalar-tailscale.ps1    # acceso remoto con HTTPS
```

Los scripts se escriben con `.\` adelante; sin eso PowerShell no los ejecuta.

**1. Servicio.** Instala Audix como servicio con inicio automático. Los libros, los registros y la clave quedan en `C:\audix-data`, que solo pueden leer los administradores. Si esa carpeta no tiene libros, copia los que haya en `audix\data`. Se puede volver a ejecutar las veces que haga falta.

**3. Clave.** Pide la clave dos veces, sin mostrarla. Mínimo 10 caracteres. Usá una que no uses en ningún otro lado; lo ideal es generarla y guardarla en un gestor de contraseñas (Bitwarden es gratuito).

**2. Tailscale.** Instala Tailscale, te hace iniciar sesión y publica Audix dentro de tu red privada. Antes de seguir te pide activar MagicDNS y HTTPS en <https://login.tailscale.com/admin/dns>. Al final muestra tu dirección, del tipo `https://tu-pc.xxxxx.ts.net`.

## En el celular

1. Instalá Tailscale desde Play Store e iniciá sesión con la misma cuenta.
2. Abrí en Chrome la dirección `https://tu-pc.xxxxx.ts.net` e ingresá la clave.
3. Menú de Chrome, "Agregar a pantalla principal", para instalarla como app.

La sesión dura 30 días en cada dispositivo. Para cerrarla antes, usá "Cerrar sesión" en la pantalla de inicio.

## Seguridad

Qué protege a Audix, de afuera hacia adentro:

| Capa | Qué hace |
|---|---|
| Tailscale | La dirección solo responde a dispositivos conectados a tu cuenta. No hay puertos abiertos en el router ni dirección pública. El tráfico va cifrado. |
| Solo `127.0.0.1` | El servicio no acepta conexiones de la red local (Wi-Fi de casa o de la oficina). La única entrada es Tailscale. |
| Clave | Sin sesión, la API responde 401 a todo. La clave se guarda derivada con scrypt y una sal al azar, nunca en claro. |
| Freno a intentos | Cinco claves erradas seguidas bloquean los intentos 30 segundos; cada fallo siguiente duplica la espera, hasta 15 minutos. |
| Sesión | Token al azar en una cookie `HttpOnly` (el JavaScript no la lee), `Secure` (solo por HTTPS) y `SameSite=Strict` (otros sitios no la usan). En disco queda solo su hash. |
| Otros sitios | Se rechazan los pedidos de cambio que vengan de otra página web, y no se da permiso a ningún otro origen. |
| Navegador | Política de contenido estricta: solo corren los scripts propios de Audix. No se puede incrustar en otra página. |
| Archivos | Límite de tamaño antes de leer el archivo, portadas verificadas por contenido y no solo por extensión, y ninguna ruta puede salir de la carpeta del libro. |
| Disco | `C:\audix-data` solo la leen el sistema y los administradores. |

### Lo que depende de vos

- **La cuenta de Tailscale es la llave de la red.** Entrás con Google, así que activá la verificación en dos pasos en esa cuenta de Google.
- **Aprobación de dispositivos.** En <https://login.tailscale.com/admin/settings/device-management> activá "Device approval": ningún dispositivo nuevo entra a tu red sin que lo apruebes.
- **No actives Tailscale Funnel.** Funnel publica la dirección en internet para cualquiera. Con `tailscale serve`, que es lo que usa esta guía, queda solo en tu red.
- **Si perdés el celular**, quitalo en <https://login.tailscale.com/admin/machines> y ejecutá `.\3-crear-clave.ps1`: cambiar la clave cierra todas las sesiones.
- **Vencimiento de la llave de la PC.** Tailscale pide volver a iniciar sesión en cada dispositivo cada 180 días. Si un día la dirección deja de responder, abrí Tailscale en la PC y volvé a entrar.

### Límites conocidos

- El servicio corre con la cuenta `LocalSystem` de Windows, que tiene privilegios altos. Un fallo grave en Audix o en una de sus bibliotecas al procesar un archivo malicioso tendría ese alcance. Importá solo archivos de origen confiable.
- La clave protege la app, no el disco: quien tenga una cuenta de administrador en la PC puede leer los libros.
- En una PC de trabajo, estas medidas no reemplazan el permiso de la empresa para instalar software de acceso remoto.

## Uso diario

```powershell
Get-Service Audix                                         # estado
Restart-Service Audix                                     # reiniciar
Get-Content C:\audix-data\logs\audix-error.log -Tail 40   # registro de errores
& "C:\Program Files\Tailscale\tailscale.exe" status       # conexión de Tailscale
& "C:\Program Files\Tailscale\tailscale.exe" serve status # dirección publicada
```

## Actualizar Audix

```powershell
cd C:\ruta\al\repo\applied_technology
git pull
Restart-Service Audix
```

Si la actualización cambia los scripts de esta carpeta, volvé a ejecutar `.\1-instalar-servicio.ps1`.

## Problemas frecuentes

| Síntoma | Qué hacer |
|---|---|
| "no se puede ejecutar porque contiene una instrucción #requires" | Abrí PowerShell como administrador. |
| `tailscale` no se reconoce como comando | Usá la ruta completa, como en los ejemplos de arriba, o abrí una ventana nueva. |
| `netMap is nil` o `NoState` | Tailscale todavía está arrancando. `Restart-Service Tailscale`, esperá 15 segundos y repetí. |
| La pantalla dice que no se creó la clave | Ejecutá `.\3-crear-clave.ps1` y recargá. |
| "Demasiados intentos" | Esperá el tiempo indicado. Si olvidaste la clave, creá otra con `.\3-crear-clave.ps1`. |
| La dirección no responde | Revisá que la PC esté encendida, `Get-Service Audix` y el estado de Tailscale en la PC y en el celular. |
