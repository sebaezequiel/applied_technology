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

## Procesar un EPUB sin la API

```powershell
python backend\pipeline\epub_a_capitulos.py "C:\ruta\libro.epub" data\libro
```

## Estado

- [x] Script EPUB -> capítulos
- [ ] API de subida y biblioteca
- [ ] Reproductor con voz del sistema (Web Speech API)
- [ ] Racha y mascota según estado
- [ ] Soporte PDF (con y sin OCR)
