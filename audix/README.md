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

Desde el celular (misma Wi-Fi), abrí `http://192.168.0.39:8000`. La IP la ves con `ipconfig` en la "Dirección IPv4".

Si preferís a mano:

```powershell
cd audix
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Si no carga desde el celular, revisá que Windows Defender Firewall permita el puerto 8000 en red privada.

Sin HTTPS, el navegador no registra el service worker, así que la app funciona pero no queda disponible sin conexión. Para instalarla como app y usarla offline hace falta publicarla con HTTPS, lo vemos más adelante.

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
