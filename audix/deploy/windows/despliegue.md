# Audix — Despliegue en Windows (acceso remoto, free tier)

Después de seguir esta guía, Audix va a:
- Arrancar automáticamente cuando enciendas la PC (sin que abras nada).
- Ser accesible desde tu Android estés donde estés, con una URL HTTPS fija.
- Funcionar como PWA instalada en tu teléfono, igual que hoy en la red local.

**Herramientas usadas (todas gratuitas)**
| Herramienta | Para qué |
|---|---|
| [NSSM](https://nssm.cc) | Convierte Audix en un servicio de Windows |
| [Tailscale](https://tailscale.com) | Red privada con HTTPS automático entre tus dispositivos |

---

## Requisitos previos

- Windows 10 u 11 (64 bits).
- Python 3.10+ con las dependencias de Audix instaladas (`pip install -r audix/backend/requirements.txt`).
- El repositorio clonado (la carpeta `applied_technology/`).
- Conexión a internet durante la instalación.

---

## Paso 1 — Audix como servicio de Windows

Abrí PowerShell **como Administrador** y ejecutá:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
cd C:\ruta\al\repo\applied_technology\audix\deploy\windows
.\1-instalar-servicio.ps1
```

> Si el repo está en otra carpeta, reemplazá `C:\ruta\al\repo` con la ruta real.

El script:
1. Detecta automáticamente dónde está Python y el venv.
2. Descarga NSSM (un pequeño utilitario).
3. Instala Audix como servicio con inicio automático.
4. Guarda los logs en `C:\audix-data\logs\`.

**Verificar que funciona:**
```powershell
Get-Service Audix
# Tiene que decir "Running"

Invoke-WebRequest http://localhost:8000/libros
# Tiene que devolver un JSON
```

**Si algo sale mal:**
```powershell
Get-Content C:\audix-data\logs\audix-error.log -Tail 30
```

---

## Paso 2 — Tailscale (acceso desde fuera de tu red)

En la misma PowerShell **como Administrador**:

```powershell
.\2-instalar-tailscale.ps1
```

El script:
1. Instala Tailscale (si no está).
2. Te pide que crees una cuenta gratuita en tailscale.com e inicies sesión.
3. Te pide que actives HTTPS en el panel web (un clic, instrucciones en pantalla).
4. Configura `tailscale serve` para exponer Audix en `https://<tu-pc>.ts.net`.

Al final te muestra tu URL definitiva, algo así:
```
https://mi-pc.cola-de-peces.ts.net
```
Esa URL es tuya para siempre (mientras uses esa cuenta).

---

## Paso 3 — Instalar la PWA en el Android

1. Instalá **Tailscale** desde la Play Store (gratis).
2. Iniciá sesión con la **misma cuenta** que usaste en la PC.
3. Abrí Chrome en el celular y entrá a `https://<tu-pc>.ts.net`.
4. Menú (tres puntos) → **Añadir a pantalla de inicio** → Instalar.

Listo. El ícono de Audix aparece en tu pantalla como si fuera una app nativa.

---

## Qué pasa cuando apagás y encendés la PC

| Evento | Comportamiento |
|---|---|
| Reinicio normal | Audix y Tailscale arrancan solos, sin que hagas nada. |
| Corte de luz / apagado forzado | Ídem, arrancan solos al volver. |
| PC apagada | Audix no responde (esperado). |

---

## Comandos útiles del día a día

```powershell
# Ver estado del servicio
Get-Service Audix

# Reiniciar (por ejemplo, después de hacer cambios en el código)
Restart-Service Audix

# Ver últimas líneas del log
Get-Content C:\audix-data\logs\audix.log -Tail 50 -Wait

# Ver estado de Tailscale
tailscale status

# Tu URL actual
tailscale serve status
```

---

## Actualizar Audix (cuando mergees un PR)

```powershell
# 1. Ir al repo y bajar los cambios
cd C:\ruta\al\repo\applied_technology
git pull

# 2. Reiniciar el servicio para que tome el código nuevo
Restart-Service Audix
```

---

## Preguntas frecuentes

**¿Puedo compartirle la URL a alguien más?**
No directamente: Tailscale es una red privada y solo entran dispositivos con tu cuenta. Si en el futuro querés acceso público, se puede activar *Tailscale Funnel* (también gratis), pero primero habría que agregar login a Audix.

**¿Consume internet mientras la PC está encendida pero no la uso?**
Tailscale consume prácticamente nada en modo idle (mantiene el túnel activo con keep-alives mínimos).

**¿Y si la PC cambia de IP local?**
No importa. Tailscale trabaja por encima de la IP de tu red y se adapta solo.

**¿El audio del Web Speech API funciona igual que antes?**
Sí. El audio se genera en el celular (la API corre en el navegador del teléfono), no en la PC. Solo los textos viajan por Tailscale.
