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
├── data/               # Libros procesados (no se versiona)
└── tests/
```

## Puesta en marcha (Windows)

```powershell
cd audix
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Después abrí `frontend/index.html` con un servidor local (por ejemplo `python -m http.server 8080 -d frontend`).

## Usar desde el celular

La PWA y la API tienen que estar en la misma red Wi-Fi que el celular.

1. Averiguá la IP de tu PC: `ipconfig` y buscá la "Dirección IPv4" (por ejemplo `192.168.0.25`).
2. Levantá la API escuchando en la red:
   ```powershell
   .venv\Scripts\activate
   uvicorn backend.main:app --host 0.0.0.0 --reload
   ```
3. Levantá la PWA en la red:
   ```powershell
   python -m http.server 8080 --bind 0.0.0.0 -d frontend
   ```
4. En el celular, abrí `http://192.168.0.39:8080`.
5. Si no carga, revisá que Windows Defender Firewall permita conexiones en los puertos 8000 y 8080 (red privada).

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
- [ ] Soporte PDF (con y sin OCR)
