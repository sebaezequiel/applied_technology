"""API de Audix: subida de libros y biblioteca.

Por ahora expone solo el estado del servicio y la lista de libros procesados.
La subida y el procesamiento se agregan en los próximos pasos.
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="Audix", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"estado": "ok"}


@app.get("/libros")
def listar_libros() -> list[dict]:
    libros = []
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
    indice = DATA_DIR / libro_id / "indice.json"
    if not indice.exists():
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    return json.loads(indice.read_text(encoding="utf-8"))
