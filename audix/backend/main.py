"""API de Audix: biblioteca, lectura de capítulos, importación, portadas y borrado.

Los libros se guardan en `data/`, donde el pipeline deja un `indice.json`,
un `.txt` por capítulo y, si el EPUB trae una, la `portada.<ext>`.
Para usar otra carpeta, definí AUDIX_DATA_DIR.

Todo menos los archivos de la PWA, /health y /sesion exige haber iniciado
sesión con la clave (ver `backend/seguridad.py`).
"""

import json
import os
import re
import shutil
import tempfile
import threading
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.pipeline.epub_a_capitulos import procesar_epub
from backend import seguridad, trabajos
from backend.pipeline.pdf_a_capitulos import procesar_pdf

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AUDIX_DATA_DIR") or RAIZ / "data")
FRONTEND_DIR = RAIZ / "frontend"
TAMANO_MAXIMO = 50 * 1024 * 1024  # 50 MB para EPUB / PDF
TAMANO_PORTADA = 5 * 1024 * 1024  # 5 MB para portadas
TIPOS_PDF = {"novela", "cuento", "poesia", "apuntes"}
EXTENSIONES_PORTADA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
ID_LIBRO = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

COOKIE_SESION = "audix_sesion"
RUTAS_PUBLICAS = {"/health", "/sesion"}
METODOS_QUE_CAMBIAN = {"POST", "PUT", "PATCH", "DELETE"}
CUERPO_MAXIMO = TAMANO_MAXIMO + 1024 * 1024  # el archivo más los campos del formulario

# Los archivos de la PWA son lo único que se entrega sin sesión: hace falta
# para poder mostrar la pantalla de acceso. Se listan al arrancar y se comparan
# por igualdad exacta, así ninguna ruta rebuscada pasa por archivo estático.
ARCHIVOS_PUBLICOS = {"/"} | {
    "/" + archivo.relative_to(FRONTEND_DIR).as_posix()
    for archivo in FRONTEND_DIR.rglob("*")
    if archivo.is_file()
}

CABECERAS_DE_SEGURIDAD = {
    # Solo se cargan scripts, estilos e imágenes propios; nada de otros sitios ni en línea.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

# Sin /docs ni /openapi.json: no hace falta publicar el mapa de la API.
app = FastAPI(title="Audix", version="0.5.0", docs_url=None, redoc_url=None, openapi_url=None)

freno = seguridad.Freno()


def _es_https(request: Request) -> bool:
    # Detrás de `tailscale serve` la conexión local es HTTP y el proxy avisa con esta cabecera.
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def _viene_de_otro_sitio(request: Request) -> bool:
    """True si un pedido que modifica datos fue disparado desde otra página web."""
    if request.headers.get("sec-fetch-site") == "cross-site":
        return True
    origen = request.headers.get("origin")
    if origen is None:
        return False  # no es un navegador (o es un pedido del mismo sitio sin Origin)
    propios = {request.headers.get("host"), request.headers.get("x-forwarded-host")}
    return urlsplit(origen).netloc not in propios


def _rechazo(estado: int, detalle: str) -> JSONResponse:
    return JSONResponse(status_code=estado, content={"detail": detalle})


@app.middleware("http")
async def proteger(request: Request, llamar):
    respuesta = _revisar(request)
    if respuesta is None:
        respuesta = await llamar(request)
    for nombre, valor in CABECERAS_DE_SEGURIDAD.items():
        respuesta.headers.setdefault(nombre, valor)
    if _es_https(request):
        respuesta.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if request.url.path not in ARCHIVOS_PUBLICOS:
        # Lo de la API (libros, sesión) no se guarda en cachés compartidas y
        # el navegador lo revalida siempre antes de reusarlo.
        respuesta.headers.setdefault("Cache-Control", "private, no-cache")
    return respuesta


def _revisar(request: Request):
    """Devuelve la respuesta de rechazo, o None si el pedido puede seguir."""
    ruta = request.url.path
    metodo = request.method

    if metodo in METODOS_QUE_CAMBIAN:
        if _viene_de_otro_sitio(request):
            return _rechazo(403, "Pedido rechazado: viene de otro sitio")
        largo = request.headers.get("content-length", "")
        if largo.isdigit() and int(largo) > CUERPO_MAXIMO:
            return _rechazo(413, "El archivo supera los 50 MB")

    if ruta in RUTAS_PUBLICAS:
        return None
    if metodo in {"GET", "HEAD"} and ruta in ARCHIVOS_PUBLICOS:
        return None
    if seguridad.sesion_valida(DATA_DIR, request.cookies.get(COOKIE_SESION)):
        return None
    return _rechazo(401, "Hace falta iniciar sesión")


def _dentro(carpeta: Path, nombre: str) -> Path:
    """Arma una ruta dentro de la carpeta del libro; rechaza nombres que intenten salir."""
    ruta = (carpeta / nombre).resolve()
    if carpeta.resolve() not in ruta.parents:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return ruta


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------

class Acceso(BaseModel):
    clave: str


@app.get("/sesion")
def estado_sesion(request: Request) -> dict:
    return {
        "configurada": seguridad.hay_clave(DATA_DIR),
        "activa": seguridad.sesion_valida(DATA_DIR, request.cookies.get(COOKIE_SESION)),
    }


@app.post("/sesion", status_code=204)
def iniciar_sesion(acceso: Acceso, request: Request) -> Response:
    if not seguridad.hay_clave(DATA_DIR):
        raise HTTPException(status_code=503, detail="Todavía no se creó la clave en la PC")

    espera = freno.segundos_de_espera()
    if espera:
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos. Probá de nuevo en {espera} segundos.",
            headers={"Retry-After": str(espera)},
        )
    if not seguridad.clave_correcta(DATA_DIR, acceso.clave):
        freno.anotar_fallo()
        raise HTTPException(status_code=401, detail="Clave incorrecta")
    freno.anotar_acierto()

    respuesta = Response(status_code=204)
    respuesta.set_cookie(
        COOKIE_SESION,
        seguridad.abrir_sesion(DATA_DIR),
        max_age=seguridad.DURACION_SESION,
        httponly=True,  # el JavaScript de la página no puede leerla
        secure=_es_https(request),  # por HTTPS no viaja nunca en claro
        samesite="strict",  # otros sitios no pueden usarla
        path="/",
    )
    return respuesta


@app.delete("/sesion", status_code=204)
def terminar_sesion(request: Request) -> Response:
    seguridad.cerrar_sesion(DATA_DIR, request.cookies.get(COOKIE_SESION))
    respuesta = Response(status_code=204)
    respuesta.delete_cookie(COOKIE_SESION, path="/")
    return respuesta


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
# PDF: importación en segundo plano
# ---------------------------------------------------------------------------

def _pedir_pdf(archivo: UploadFile, tipo: str) -> bytes:
    """Valida el tipo y el archivo PDF, y devuelve su contenido."""
    if tipo not in TIPOS_PDF:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Usá: {', '.join(sorted(TIPOS_PDF))}")
    if not archivo.filename or not archivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF (terminan en .pdf)")
    contenido = archivo.file.read(TAMANO_MAXIMO + 1)
    if len(contenido) > TAMANO_MAXIMO:
        raise HTTPException(status_code=413, detail="El archivo supera los 50 MB")
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    return contenido


def _procesar_pdf_en_segundo_plano(trabajo_id: str, ruta: Path, tipo: str) -> None:
    """Corre en un hilo aparte. Actualiza el progreso y guarda el libro al terminar."""
    carpeta_temporal = ruta.parent
    try:
        salida = carpeta_temporal / "salida"

        def avance(hechas: int, total: int) -> None:
            # Hasta que termina, el progreso no llega a 100.
            porcentaje = min(99, int(hechas * 100 / max(total, 1)))
            trabajos.actualizar(trabajo_id, progreso=porcentaje)

        indice = procesar_pdf(ruta, salida, tipo=tipo, progreso=avance)
        if not indice["capitulos"]:
            raise ValueError("No se encontró texto en el PDF.")

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        destino = _carpeta_libre(_slug(indice["titulo"]))
        shutil.move(str(salida), str(destino))
        trabajos.actualizar(trabajo_id, estado="listo", progreso=100, libro_id=destino.name)
    except Exception as error:
        trabajos.actualizar(trabajo_id, estado="error", error=str(error) or "Error desconocido")
    finally:
        shutil.rmtree(carpeta_temporal, ignore_errors=True)


@app.post("/libros/pdf", status_code=202)
def importar_pdf(archivo: UploadFile, tipo: str = "novela") -> dict:
    """
    Inicia la importación de un PDF en segundo plano.
    Responde enseguida con el trabajo; el progreso se consulta en GET /trabajos/{id}.
    """
    contenido = _pedir_pdf(archivo, tipo)
    trabajo = trabajos.crear(nombre=archivo.filename, tipo=tipo)

    # El archivo se guarda en una carpeta temporal que el hilo borra al terminar.
    carpeta_temporal = Path(tempfile.mkdtemp(prefix="audix-pdf-"))
    # Se conserva el nombre original: sirve de título si el PDF no tiene metadatos.
    ruta = carpeta_temporal / (Path(archivo.filename).name or "libro.pdf")
    ruta.write_bytes(contenido)

    threading.Thread(
        target=_procesar_pdf_en_segundo_plano,
        args=(trabajo["id"], ruta, tipo),
        daemon=True,
    ).start()
    return trabajo


@app.get("/trabajos")
def listar_trabajos() -> list[dict]:
    return trabajos.listar()


@app.get("/trabajos/{trabajo_id}")
def estado_trabajo(trabajo_id: str) -> dict:
    trabajo = trabajos.obtener(trabajo_id)
    if trabajo is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return trabajo


@app.delete("/trabajos/{trabajo_id}", status_code=204)
def quitar_trabajo(trabajo_id: str) -> Response:
    """Quita un trabajo de la lista (solo si ya no está en curso)."""
    trabajo = trabajos.obtener(trabajo_id)
    if trabajo is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if trabajo["estado"] == "en_curso":
        raise HTTPException(status_code=409, detail="El trabajo todavía está en curso")
    trabajos.quitar(trabajo_id)
    return Response(status_code=204)


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


def _es_imagen(contenido: bytes) -> bool:
    """Mira los primeros bytes: la extensión sola no prueba que sea una imagen."""
    return (
        contenido.startswith(b"\xff\xd8")
        or contenido.startswith(b"\x89PNG\r\n\x1a\n")
        or (contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP")
    )


@app.get("/libros/{libro_id}/portada")
def ver_portada(libro_id: str) -> FileResponse:
    datos = _leer_indice(libro_id)
    if not datos.get("portada"):
        raise HTTPException(status_code=404, detail="Este libro no tiene portada")
    return FileResponse(_dentro(_carpeta_libro(libro_id), datos["portada"]))


@app.put("/libros/{libro_id}/portada")
def cambiar_portada(libro_id: str, archivo: UploadFile) -> dict:
    carpeta = _carpeta_libro(libro_id)
    extension = Path(archivo.filename or "").suffix.lower()
    if extension not in EXTENSIONES_PORTADA:
        raise HTTPException(status_code=400, detail="La portada tiene que ser JPG, PNG o WebP")

    contenido = archivo.file.read(TAMANO_PORTADA + 1)
    if len(contenido) > TAMANO_PORTADA:
        raise HTTPException(status_code=413, detail="La portada supera los 5 MB")
    if not _es_imagen(contenido):
        raise HTTPException(status_code=400, detail="El archivo no es una imagen JPG, PNG o WebP")

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

    archivo = _dentro(_carpeta_libro(libro_id), capitulo["archivo"])
    return {**capitulo, "texto": archivo.read_text(encoding="utf-8")}


# La PWA se sirve desde la misma API, así alcanza un solo proceso y un solo puerto.
# Va al final: el mount en "/" tiene que quedar después de las rutas de la API.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
