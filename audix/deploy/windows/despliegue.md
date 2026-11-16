# Audix - Despliegue en Windows (acceso remoto, free tier)

Despues de seguir esta guia, Audix va a:
- Arrancar automaticamente cuando enciendas la PC (sin que abras nada).
- Ser accesible desde tu Android estes donde estes, con una URL HTTPS fija.
- Funcionar como PWA instalada en tu telefono, igual que hoy en la red local.

**Herramientas usadas (todas gratuitas)**
| Herramienta | Para que |
|---|---|
| [NSSM](https://nssm.cc) | Convierte Audix en un servicio de Windows |
| [Tailscale](https://tailscale.com) | Red privada con HTTPS automatico entre tus dispositivos |

---

## Requisitos previos

- Windows 10 u 11 (64 bits).
- Python 3.10+ con las dependencias de Audix instaladas (`pip install -r audix/backend/requirements.txt`).
- El repositorio clonado (la carpeta `applied_technology/`).
- Conexion a internet durante la instalacion.

---

## Paso 1 - Audix como servicio de Windows

Abri PowerShell **como Administrador** y ejecuta:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
cd C:\ruta\al\repo\applied_technology\audix\deploy\windows
.\1-instalar-servicio.ps1
```

> Si el repo esta en otra carpeta, reemplaza `C:\ruta\al\repo` con la ruta real.

El script:
1. Detecta automaticamente donde esta Python y el venv.
2. Descarga NSSM (un pequeno utilitario).
3. Instala Audix como servicio con inicio automatico.
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

## Paso 2 - Tailscale (acceso desde fuera de tu red)

En la misma PowerShell **como Administrador**:

```powershell
.\2-instalar-tailscale.ps1
```

El script:
1. Instala Tailscale (si no esta).
2. Te pide que crees una cuenta gratuita en tailscale.com e inicies sesion.
3. Te pide que actives HTTPS en el panel web (un clic, instrucciones en pantalla).
4. Configura `tailscale serve` para exponer Audix en `https://<tu-pc>.ts.net`.

Al final te muestra tu URL definitiva, algo asi:
```
https://mi-pc.cola-de-peces.ts.net
```
Esa URL es tuya para siempre (mientras uses esa cuenta).

---

## Paso 3 - Instalar la PWA en el Android

1. Instala **Tailscale** desde la Play Store (gratis).
2. Inicia sesion con la **misma cuenta** que usaste en la PC.
3. Abri Chrome en el celular y entra a `https://<tu-pc>.ts.net`.
4. Menu (tres puntos) -> **Anadir a pantalla de inicio** -> Instalar.

Listo. El icono de Audix aparece en tu pantalla como si fuera una app nativa.

---

## Que pasa cuando apagas y encendes la PC

| Evento | Comportamiento |
|---|---|
| Reinicio normal | Audix y Tailscale arrancan solos, sin que hagas nada. |
| Corte de luz / apagado forzado | Idem, arrancan solos al volver. |
| PC apagada | Audix no responde (esperado). |

---

## Comandos utiles del dia a dia

```powershell
# Ver estado del servicio
Get-Service Audix

# Reiniciar (por ejemplo, despues de hacer cambios en el codigo)
Restart-Service Audix

# Ver ultimas lineas del log
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

# 2. Reiniciar el servicio para que tome el codigo nuevo
Restart-Service Audix
```

---

## Preguntas frecuentes

**Puedo compartirle la URL a alguien mas?**
No directamente: Tailscale es una red privada y solo entran dispositivos con tu cuenta. Si en el futuro queres acceso publico, se puede activar *Tailscale Funnel* (tambien gratis), pero primero habria que agregar login a Audix.

**Consume internet mientras la PC esta encendida pero no la uso?**
Tailscale consume practicamente nada en modo idle (mantiene el tunel activo con keep-alives minimos).

**Y si la PC cambia de IP local?**
No importa. Tailscale trabaja por encima de la IP de tu red y se adapta solo.

**El audio del Web Speech API funciona igual que antes?**
Si. El audio se genera en el celular (la API corre en el navegador del telefono), no en la PC. Solo los textos viajan por Tailscale.
