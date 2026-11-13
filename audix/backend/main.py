"""API de Audix: biblioteca, lectura de capítulos, importación, portadas y borrado.

Los libros se guardan en `data/`, donde el pipeline deja un `indice.json`,
un `.txt` por capítulo y, si el EPUB trae una, la `portada.<ext>`.
Para usar otra carpeta, definí AUDIX_DATA_DIR.
"""

import json
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.pipeline.epub_a_capitulos import procesar_epub
from backend.pipeline.pdf_a_capitulos import detectar_origen, previsualizar_pdf, procesar_pdf

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AUDIX_DATA_DIR") or RAIZ / "data")
FRONTEND_DIR = RAIZ / "frontend"
TAMANO_MAXIMO = 50 * 1024 * 1024  # 50 MB para EPUB / PDF
TAMANO_PORTADA = 5 * 1024 * 1024  # 5 MB para portadas
TIPOS_PDF = {"novela", "cuento", "poesia", "apuntes"}
EXTENSIONES_PORTADA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
ID_LIBRO = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

app = FastAPI(title="Audix", version="0.4.0")

# La PWA corre en el navegador del celular o de la PC, con IP de red local.
# Por eso se permiten orígenes de localhost y de redes privadas (192.168.x.x, 10.x.x.x, 172.16-31.x.x).
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?",
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


def _carpeta_libro(libro_id: str) -> Path:
    """Devuelve la carpeta del libro. Rechaza ids raros para no salir de DATA_DIR."""
    if not ID_LIBRO.match(libro_id):
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    carpeta = DATA_DIR / libro_id
    if not (carpeta / "indice.json").exists():
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    return carpeta


def _leer_indice(libro_id: str) -> dict:
    return json.loads((_carpeta_libro(libro_id) / "indice.json").read_text(encoding="utf-8"))


def _guardar_indice(carpeta: Path, indice: dict) -> None:
    (carpeta / "indice.json").write_text(
        json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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


def _url_portada(libro_id: str, datos: dict):
    return f"/libros/{libro_id}/portada" if datos.get("portada") else None


@app.get("/health")
def health() -> dict:
    return {"estado": "ok"}


# ---------------------------------------------------------------------------
# PDF: detectar origen y vista previa
# ---------------------------------------------------------------------------

@app.post("/libros/pdf/detectar")
def detectar_pdf(archivo: UploadFile) -> dict:
    """
    Recibe un PDF y devuelve si tiene capa de texto o es escaneado.
    No guarda el archivo en disco.
    """
    if not archivo.filename or not archivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF (terminan en .pdf)")

    contenido = archivo.file.read(TAMANO_MAXIMO + 1)
    if len(contenido) > TAMANO_MAXIMO:
        raise HTTPException(status_code=413, detail="El archivo supera los 50 MB")
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")

    with tempfile.TemporaryDirectory() as temporal:
        ruta = Path(temporal) / "libro.pdf"
        ruta.write_bytes(contenido)
        try:
            origen = detectar_origen(ruta)
        except Exception as error:
            raise HTTPException(
                status_code=422,
                detail=f"No se pudo analizar el PDF: {error}",
            ) from error

    return {"origen": origen}


@app.post("/libros/pdf/preview")
def preview_pdf(archivo: UploadFile, tipo: str = "novela") -> dict:
    """
    Recibe un PDF y devuelve la lista de capítulos detectados (sin guardar).
    Parámetro: tipo = novela | cuento | poesia | apuntes
    """
    if tipo not in TIPOS_PDF:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Usá: {', '.join(sorted(TIPOS_PDF))}")

    if not archivo.filename or not archivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF (terminan en .pdf)")

    contenido = archivo.file.read(TAMANO_MAXIMO + 1)
    if len(contenido) > TAMANO_MAXIMO:
        raise HTTPException(status_code=413, detail="El archivo supera los 50 MB")
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")

    with tempfile.TemporaryDirectory() as temporal:
        ruta = Path(temporal) / "libro.pdf"
        ruta.write_bytes(contenido)
        try:
            capitulos = previsualizar_pdf(ruta, tipo=tipo)
        except Exception as error:
            raise HTTPException(
                status_code=422,
                detail=f"No se pudo leer el PDF: {error}",
            ) from error

    return {"tipo": tipo, "capitulos": capitulos}


@app.post("/libros/pdf", status_code=201)
def importar_pdf(archivo: UploadFile, tipo: str = "novela") -> dict:
    """
    Importa un PDF con capa de texto.
    Parámetro: tipo = novela | cuento | poesia | apuntes
    """
    if tipo not in TIPOS_PDF:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Usá: {', '.join(sorted(TIPOS_PDF))}")

    if not archivo.filename or not archivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF (terminan en .pdf)")

    contenido = archivo.file.read(TAMANO_MAXIMO + 1)
    if len(contenido) > TAMANO_MAXIMO:
        raise HTTPException(status_code=413, detail="El archivo supera los 50 MB")
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")

    with tempfile.TemporaryDirectory() as temporal:
        ruta = Path(temporal) / "libro.pdf"
        ruta.write_bytes(contenido)
        salida = Path(temporal) / "salida"

        try:
            indice = procesar_pdf(ruta, salida, tipo=tipo)
        except Exception as error:
            raise HTTPException(
                status_code=422,
                detail=f"No se pudo procesar el PDF: {error}",
            ) from error

        if not indice["capitulos"]:
            raise HTTPException(
                status_code=422,
                detail="No se encontró texto en el PDF. Si es un escaneado, revisá que tenga páginas con contenido legible.",
            )

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        destino = _carpeta_libre(_slug(indice["titulo"]))
        shutil.move(str(salida), str(destino))

    return {
        "id": destino.name,
        "titulo": indice["titulo"],
        "autor": indice["autor"],
        "capitulos": len(indice["capitulos"]),
        "portada": None,
    }


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
            "portada": _url_portada(indice.parent.name, datos),
        })
    return libros


@app.post("/libros", status_code=201)
def importar_libro(archivo: UploadFile) -> dict:
    if not archivo.filename or not archivo.filename.lower().endswith(".epub"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos EPUB (terminan en .epub)")

    contenido = archivo.file.read(TAMANO_MAXIMO + 1)
    if len(contenido) > TAMANO_MAXIMO:
        raise HTTPException(status_code=413, detail="El archivo supera los 50 MB")
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")

    with tempfile.TemporaryDirectory() as temporal:
        origen = Path(temporal) / "libro.epub"
        origen.write_bytes(contenido)
        salida = Path(temporal) / "salida"

        try:
            indice = procesar_epub(origen, salida)
        except Exception as error:
            raise HTTPException(
                status_code=422,
                detail=f"No se pudo leer el EPUB. ¿Está completo y no protegido? Detalle: {error}",
            ) from error

        if not indice["capitulos"]:
            raise HTTPException(
                status_code=422,
                detail="El EPUB no tiene texto para leer (puede ser una imagen escaneada o estar vacío).",
            )

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        destino = _carpeta_libre(_slug(indice["titulo"]))
        shutil.move(str(salida), str(destino))

    return {
        "id": destino.name,
        "titulo": indice["titulo"],
        "autor": indice["autor"],
        "capitulos": len(indice["capitulos"]),
        "portada": _url_portada(destino.name, indice),
    }


@app.get("/libros/{libro_id}")
def detalle_libro(libro_id: str) -> dict:
    datos = _leer_indice(libro_id)
    return {"id": libro_id, **datos, "portada": _url_portada(libro_id, datos)}


class CambioTitulo(BaseModel):
    titulo: str


@app.patch("/libros/{libro_id}")
def renombrar_libro(libro_id: str, cambio: CambioTitulo) -> dict:
    """Cambia el título del libro (útil si la importación lo leyó mal)."""
    titulo = cambio.titulo.strip()
    if not titulo:
        raise HTTPException(status_code=400, detail="El título no puede estar vacío")
    if len(titulo) > 200:
        raise HTTPException(status_code=400, detail="El título es demasiado largo (máximo 200 caracteres)")
    carpeta = _carpeta_libro(libro_id)
    datos = _leer_indice(libro_id)
    datos["titulo"] = titulo
    _guardar_indice(carpeta, datos)
    return {"id": libro_id, **datos, "portada": _url_portada(libro_id, datos)}


@app.delete("/libros/{libro_id}", status_code=204)
def borrar_libro(libro_id: str) -> Response:
    shutil.rmtree(_carpeta_libro(libro_id))
    return Response(status_code=204)


@app.get("/libros/{libro_id}/portada")
def ver_portada(libro_id: str) -> FileResponse:
    datos = _leer_indice(libro_id)
    if not datos.get("portada"):
        raise HTTPException(status_code=404, detail="Este libro no tiene portada")
    return FileResponse(_carpeta_libro(libro_id) / datos["portada"])


@app.put("/libros/{libro_id}/portada")
def cambiar_portada(libro_id: str, archivo: UploadFile) -> dict:
    carpeta = _carpeta_libro(libro_id)
    extension = Path(archivo.filename or "").suffix.lower()
    if extension not in EXTENSIONES_PORTADA:
        raise HTTPException(status_code=400, detail="La portada tiene que ser JPG, PNG o WebP")

    contenido = archivo.file.read(TAMANO_PORTADA + 1)
    if len(contenido) > TAMANO_PORTADA:
        raise HTTPException(status_code=413, detail="La portada supera los 5 MB")

    for anterior in carpeta.glob("portada.*"):
        anterior.unlink()
    nombre = f"portada{'.jpg' if extension == '.jpeg' else extension}"
    (carpeta / nombre).write_bytes(contenido)

    indice = _leer_indice(libro_id)
    indice["portada"] = nombre
    _guardar_indice(carpeta, indice)
    return {"portada": _url_portada(libro_id, indice)}


@app.get("/libros/{libro_id}/capitulos/{numero}")
def texto_capitulo(libro_id: str, numero: int) -> dict:
    datos = _leer_indice(libro_id)
    capitulo = next(
        (c for c in datos.get("capitulos", []) if c["numero"] == numero), None
    )
    if capitulo is None:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    archivo = _carpeta_libro(libro_id) / capitulo["archivo"]
    return {**capitulo, "texto": archivo.read_text(encoding="utf-8")}


# La PWA se sirve desde la misma API, así alcanza un solo proceso y un solo puerto.
# Va al final: el mount en "/" tiene que quedar después de las rutas de la API.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
