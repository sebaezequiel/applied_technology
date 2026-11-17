"""
Registro de trabajos de importación en segundo plano.

Los trabajos viven en memoria: si el servidor se reinicia, la lista de trabajos
se vacía. Los libros que ya terminaron siguen en disco, porque se guardan al final.
"""

import threading
import time
import uuid

_lock = threading.Lock()
_trabajos: dict[str, dict] = {}


def crear(nombre: str, tipo: str) -> dict:
    trabajo = {
        "id": uuid.uuid4().hex[:12],
        "nombre": nombre,
        "tipo": tipo,
        "estado": "en_curso",  # en_curso | listo | error
        "progreso": 0,         # 0 a 100
        "error": None,
        "libro_id": None,
        "creado": time.time(),
    }
    with _lock:
        _trabajos[trabajo["id"]] = trabajo
    return dict(trabajo)


def actualizar(trabajo_id: str, **cambios) -> None:
    with _lock:
        if trabajo_id in _trabajos:
            _trabajos[trabajo_id].update(cambios)


def obtener(trabajo_id: str) -> dict | None:
    with _lock:
        trabajo = _trabajos.get(trabajo_id)
        return dict(trabajo) if trabajo else None


def listar() -> list[dict]:
    with _lock:
        return sorted((dict(t) for t in _trabajos.values()), key=lambda t: t["creado"])


def quitar(trabajo_id: str) -> bool:
    with _lock:
        return _trabajos.pop(trabajo_id, None) is not None
