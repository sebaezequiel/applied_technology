"""API de Audix: biblioteca y lectura de capítulos.

Los libros se leen desde la carpeta `data/`, donde el pipeline deja un
`indice.json` y un `.txt` por capítulo. Para usar otra carpeta, definí la
variable de entorno AUDIX_DATA_DIR.
"""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

DATA_DIR = Path(
    os.environ.get("AUDIX_DATA_DIR")
    or Path(__file__).resolve().parent.parent / "data"
)

app = FastAPI(title="Audix", version="0.2.0")

# La PWA corre en otro puerto (por ejemplo 8080) y necesita permiso para consultar la API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _leer_indice(libro_id: str) -> dict:
    indice = DATA_DIR / libro_id / "indice.json"
    if not indice.exists():
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    return json.loads(indice.read_text(encoding="utf-8"))


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
