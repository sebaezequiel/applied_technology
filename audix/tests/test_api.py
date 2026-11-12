import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend import main  # noqa: E402


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    libro = tmp_path / "libro-prueba"
    libro.mkdir()
    (libro / "001.txt").write_text("Primer capítulo.", encoding="utf-8")
    (libro / "indice.json").write_text(
        json.dumps({
            "titulo": "Libro de prueba",
            "autor": "Autor",
            "capitulos": [
                {"numero": 1, "titulo": "Uno", "archivo": "001.txt", "caracteres": 16},
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    return TestClient(main.app)


def test_health(cliente):
    assert cliente.get("/health").json() == {"estado": "ok"}


def test_lista_libros(cliente):
    libros = cliente.get("/libros").json()
    assert libros == [
        {"id": "libro-prueba", "titulo": "Libro de prueba", "autor": "Autor", "capitulos": 1}
    ]


def test_detalle_libro(cliente):
    datos = cliente.get("/libros/libro-prueba").json()
    assert datos["titulo"] == "Libro de prueba"
    assert datos["capitulos"][0]["archivo"] == "001.txt"


def test_texto_de_capitulo(cliente):
    datos = cliente.get("/libros/libro-prueba/capitulos/1").json()
    assert datos["texto"] == "Primer capítulo."
    assert datos["titulo"] == "Uno"


def test_libro_inexistente_devuelve_404(cliente):
    assert cliente.get("/libros/no-existe").status_code == 404


def test_capitulo_inexistente_devuelve_404(cliente):
    assert cliente.get("/libros/libro-prueba/capitulos/99").status_code == 404
