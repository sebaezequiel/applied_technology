# Audix

Aplicación personal para convertir libros (EPUB, y en el futuro PDF) en audiolibros, con una mascota-hurón que cambia según tu racha de escucha.

## Estructura

```
audix/
├── backend/            # API y pipeline de procesamiento (Python)
│   ├── main.py         # API FastAPI (subida de libros, biblioteca)
│   └── pipeline/
│       └── epub_a_capitulos.py   # EPUB -> texto por capítulo
├── frontend/           # PWA instalable (HTML, CSS, JS)
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   ├── manifest.webmanifest
│   ├── sw.js
│   └── icons/
├── iniciar-audix.bat   # Arranca API + PWA con doble clic
├── data/               # Libros procesados (no se versiona)
└── tests/
```

## Puesta en marcha (Windows)

Doble clic en `iniciar-audix.bat`. La primera vez crea el entorno virtual e instala las dependencias, y abre la app en el navegador de la PC.

La primera vez creá la clave de acceso (sin clave no entra nadie):

```powershell
cd audix
.venv\Scripts\activate
python -m backend.seguridad
```

Si preferís arrancar a mano:

```powershell
cd audix
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Audix escucha solo en la propia PC (`127.0.0.1`). Para usarla desde el celular, dentro o fuera de casa, con HTTPS y como app instalada, seguí [deploy/windows/despliegue.md](deploy/windows/despliegue.md).

## Seguridad

- Todo pide iniciar sesión con la clave, salvo los archivos de la PWA y `/health`.
- La clave se guarda derivada con scrypt; la sesión va en una cookie `HttpOnly`, `Secure` y `SameSite=Strict` que dura 30 días.
- Cinco claves erradas seguidas bloquean los intentos (30 segundos, y se duplica hasta 15 minutos).
- El servidor no acepta conexiones de la red local ni pedidos disparados desde otros sitios web.

El detalle y lo que queda a tu cargo está en la guía de despliegue.

## Procesar un EPUB sin la API

```powershell
python backend\pipeline\epub_a_capitulos.py "C:\ruta\libro.epub" data\libro
```

## Tests

```powershell
python -m pytest -q tests
node --test tests\racha.test.js
```

## Estado

- [x] Script EPUB -> capítulos
- [x] API de biblioteca y lectura de capítulos
- [x] Reproductor con voz del sistema (Web Speech API)
- [x] Racha y mascota según estado (dormido, despertándose, auriculares, celebrando)
- [x] Importar EPUB desde la app (botón Importar, también desde el celular)
- [x] Portadas tomadas del EPUB, con opción de cambiarlas desde la app
- [x] Borrar libros desde la app, con barra de progreso al importar
- [ ] Soporte PDF (con y sin OCR)
