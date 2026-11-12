"""API de Audix: biblioteca, lectura de capítulos e importación de EPUB.

Los libros se guardan en `data/`, donde el pipeline deja un `indice.json`
y un `.txt` por capítulo. Para usar otra carpeta, definí AUDIX_DATA_DIR.
"""

import json
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.pipeline.epub_a_capitulos import procesar_epub

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AUDIX_DATA_DIR") or RAIZ / "data")
FRONTEND_DIR = RAIZ / "frontend"
TAMANO_MAXIMO = 50 * 1024 * 1024  # 50 MB

app = FastAPI(title="Audix", version="0.3.0")

# La PWA corre en el navegador del celular o de la PC, con IP de red local.
# Por eso se permiten orígenes de localhost y de redes privadas (192.168.x.x, 10.x.x.x, 172.16-31.x.x).
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _leer_indice(libro_id: str) -> dict:
    indice = DATA_DIR / libro_id / "indice.json"
    if not indice.exists():
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    return json.loads(indice.read_text(encoding="utf-8"))


def _slug(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-")
    return slug or "libro"


def _carpeta_libre(nombre_base: str) -> Path:
    candidato = DATA_DIR / nombre_base
    contador = 2
    while candidato.exists():
        candidato = DATA_DIR / f"{nombre_base}-{contador}"
        contador += 1
    return candidato


@app.get("/health")
def health() -> dict:
    return {"estado": "ok"}


@app.get("/libros")
def listar_libros() -> list[dict]:
    libros = []
    if not DATA_DIR.exists():
        return libros
    for indice in sorted(DATA_DIR.glob("*/indice.json")):
        datos = json.loads(indice.read_text(encoding="utf-8"))
        libros.append({
            "id": indice.parent.name,
            "titulo": datos.get("titulo", indice.parent.name),
            "autor": datos.get("autor", ""),
            "capitulos": len(datos.get("capitulos", [])),
        })
    return libros


@app.post("/libros", status_code=201)
def importar_libro(archivo: UploadFile) -> dict:
    if not archivo.filename or not archivo.filename.lower().endswith(".epub"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos EPUB")

    contenido = archivo.file.read(TAMANO_MAXIMO + 1)
    if len(contenido) > TAMANO_MAXIMO:
        raise HTTPException(status_code=413, detail="El archivo supera los 50 MB")

    with tempfile.TemporaryDirectory() as temporal:
        origen = Path(temporal) / "libro.epub"
        origen.write_bytes(contenido)
        salida = Path(temporal) / "salida"

        try:
            indice = procesar_epub(origen, salida)
        except Exception as error:
            raise HTTPException(
                status_code=422,
                detail=f"No se pudo procesar el EPUB: {error}",
            ) from error

        if not indice["capitulos"]:
            raise HTTPException(status_code=422, detail="El EPUB no tiene texto para leer")

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        destino = _carpeta_libre(_slug(indice["titulo"]))
        shutil.move(str(salida), str(destino))

    return {
        "id": destino.name,
        "titulo": indice["titulo"],
        "autor": indice["autor"],
        "capitulos": len(indice["capitulos"]),
    }


@app.get("/libros/{libro_id}")
def detalle_libro(libro_id: str) -> dict:
    return {"id": libro_id, **_leer_indice(libro_id)}


@app.get("/libros/{libro_id}/capitulos/{numero}")
def texto_capitulo(libro_id: str, numero: int) -> dict:
    datos = _leer_indice(libro_id)
    capitulo = next(
        (c for c in datos.get("capitulos", []) if c["numero"] == numero), None
    )
    if capitulo is None:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    archivo = DATA_DIR / libro_id / capitulo["archivo"]
    return {**capitulo, "texto": archivo.read_text(encoding="utf-8")}


# La PWA se sirve desde la misma API, así alcanza un solo proceso y un solo puerto.
# Va al final: el mount en "/" tiene que quedar después de las rutas de la API.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
