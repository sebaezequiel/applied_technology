import io
import json
import sys
from pathlib import Path

import pytest
from ebooklib import epub
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend import main  # noqa: E402


def crear_epub_bytes(titulo: str, tmp_path: Path) -> bytes:
    libro = epub.EpubBook()
    libro.set_identifier(f"id-{titulo}")
    libro.set_title(titulo)
    libro.set_language("es")
    libro.add_author("Autor de prueba")
    capitulo = epub.EpubHtml(title="Uno", file_name="cap1.xhtml", lang="es")
    capitulo.content = "<html><body><h1>Uno</h1><p>Texto del primer capítulo.</p></body></html>"
    libro.add_item(capitulo)
    libro.toc = (capitulo,)
    libro.add_item(epub.EpubNcx())
    libro.add_item(epub.EpubNav())
    libro.spine = ["nav", capitulo]
    ruta = tmp_path / "tmp.epub"
    epub.write_epub(str(ruta), libro)
    return ruta.read_bytes()


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
        {"id": "libro-prueba", "titulo": "Libro de prueba", "autor": "Autor", "capitulos": 1, "portada": None}
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


def test_importar_epub_lo_suma_a_la_biblioteca(cliente, tmp_path):
    contenido = crear_epub_bytes("Mi libro nuevo", tmp_path)
    respuesta = cliente.post(
        "/libros",
        files={"archivo": ("mi-libro.epub", contenido, "application/epub+zip")},
    )
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["id"] == "mi-libro-nuevo"
    assert datos["capitulos"] == 1

    ids = [libro["id"] for libro in cliente.get("/libros").json()]
    assert "mi-libro-nuevo" in ids

    texto = cliente.get("/libros/mi-libro-nuevo/capitulos/1").json()["texto"]
    assert "Texto del primer capítulo." in texto


def test_importar_titulo_repetido_crea_otra_carpeta(cliente, tmp_path):
    contenido = crear_epub_bytes("Repetido", tmp_path)
    archivo = {"archivo": ("repetido.epub", contenido, "application/epub+zip")}
    primera = cliente.post("/libros", files=archivo).json()
    segunda = cliente.post("/libros", files=archivo).json()
    assert primera["id"] == "repetido"
    assert segunda["id"] == "repetido-2"


def test_importar_rechaza_otros_formatos(cliente):
    respuesta = cliente.post(
        "/libros",
        files={"archivo": ("libro.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert respuesta.status_code == 400


def test_importar_epub_danado_devuelve_422(cliente):
    respuesta = cliente.post(
        "/libros",
        files={"archivo": ("roto.epub", io.BytesIO(b"esto no es un epub"), "application/epub+zip")},
    )
    assert respuesta.status_code == 422


def test_slug_quita_acentos_y_simbolos():
    assert main._slug("La colina De Watership") == "la-colina-de-watership"
    assert main._slug("Año ñandú: edición #2") == "ano-nandu-edicion-2"
    assert main._slug("¡¡¡") == "libro"


PNG_MINIMO = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_portada_inexistente_devuelve_404(cliente):
    assert cliente.get("/libros/libro-prueba/portada").status_code == 404


def test_subir_portada_y_verla(cliente):
    respuesta = cliente.put(
        "/libros/libro-prueba/portada",
        files={"archivo": ("tapa.png", PNG_MINIMO, "image/png")},
    )
    assert respuesta.status_code == 200
    assert respuesta.json() == {"portada": "/libros/libro-prueba/portada"}

    imagen = cliente.get("/libros/libro-prueba/portada")
    assert imagen.status_code == 200
    assert imagen.content == PNG_MINIMO
    assert cliente.get("/libros").json()[0]["portada"] == "/libros/libro-prueba/portada"


def test_cambiar_portada_reemplaza_la_anterior(cliente, tmp_path):
    cliente.put("/libros/libro-prueba/portada", files={"archivo": ("a.png", PNG_MINIMO, "image/png")})
    cliente.put("/libros/libro-prueba/portada", files={"archivo": ("b.jpg", b"\xff\xd8nuevo", "image/jpeg")})
    carpeta = tmp_path / "libro-prueba"
    assert sorted(p.name for p in carpeta.glob("portada.*")) == ["portada.jpg"]


def test_portada_con_formato_no_permitido_devuelve_400(cliente):
    respuesta = cliente.put(
        "/libros/libro-prueba/portada",
        files={"archivo": ("tapa.bmp", b"BM", "image/bmp")},
    )
    assert respuesta.status_code == 400


def test_importar_epub_con_portada_la_guarda(cliente, tmp_path):
    from ebooklib import epub as ebooklib_epub

    libro = ebooklib_epub.EpubBook()
    libro.set_identifier("con-tapa")
    libro.set_title("Con tapa")
    libro.set_language("es")
    libro.set_cover("tapa.png", PNG_MINIMO)
    capitulo = ebooklib_epub.EpubHtml(title="Uno", file_name="cap1.xhtml", lang="es")
    capitulo.content = "<html><body><h1>Uno</h1><p>Texto.</p></body></html>"
    libro.add_item(capitulo)
    libro.toc = (capitulo,)
    libro.add_item(ebooklib_epub.EpubNcx())
    libro.add_item(ebooklib_epub.EpubNav())
    libro.spine = ["nav", capitulo]
    ruta = tmp_path / "con-tapa.epub"
    ebooklib_epub.write_epub(str(ruta), libro)

    respuesta = cliente.post(
        "/libros",
        files={"archivo": ("con-tapa.epub", ruta.read_bytes(), "application/epub+zip")},
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["portada"] == "/libros/con-tapa/portada"
    assert cliente.get("/libros/con-tapa/portada").status_code == 200


def test_borrar_libro(cliente, tmp_path):
    assert cliente.delete("/libros/libro-prueba").status_code == 204
    assert not (tmp_path / "libro-prueba").exists()
    assert cliente.get("/libros/libro-prueba").status_code == 404


def test_borrar_libro_inexistente_devuelve_404(cliente):
    assert cliente.delete("/libros/no-existe").status_code == 404


def test_ids_con_rutas_raras_devuelven_404(cliente):
    assert cliente.get("/libros/a.b").status_code == 404
    assert cliente.get("/libros/Libro-Prueba").status_code == 404
    assert cliente.delete("/libros/a.b").status_code == 404


# ---------------------------------------------------------------------------
# Tests de los endpoints PDF
# ---------------------------------------------------------------------------

def crear_pdf_bytes_simple(titulo: str = "Test PDF") -> bytes:
    """
    Crea un PDF mínimo con capa de texto usando reportlab.
    Si reportlab no está disponible, genera un PDF mínimo hardcoded con texto simple.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        import io as _io

        buf = _io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(72, 750, titulo)
        c.setFont("Helvetica", 12)
        c.drawString(72, 700, "I")
        c.drawString(72, 670, "Este es el texto del primer capítulo.")
        c.drawString(72, 650, "Continúa en la siguiente línea.")
        c.showPage()
        c.drawString(72, 750, "II")
        c.drawString(72, 720, "Este es el texto del segundo capítulo.")
        c.save()
        return buf.getvalue()
    except ImportError:
        # PDF mínimo válido sin texto real (sirve para probar los errores)
        return b""


def test_detectar_pdf_rechaza_no_pdf(cliente):
    respuesta = cliente.post(
        "/libros/pdf/detectar",
        files={"archivo": ("libro.epub", b"PK\x03\x04", "application/epub+zip")},
    )
    assert respuesta.status_code == 400


def test_detectar_pdf_vacio_devuelve_400(cliente):
    respuesta = cliente.post(
        "/libros/pdf/detectar",
        files={"archivo": ("vacio.pdf", b"", "application/pdf")},
    )
    assert respuesta.status_code == 400


def test_importar_pdf_tipo_invalido_devuelve_400(cliente):
    respuesta = cliente.post(
        "/libros/pdf?tipo=inventado",
        files={"archivo": ("libro.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert respuesta.status_code == 400


def test_importar_pdf_vacio_devuelve_400(cliente):
    respuesta = cliente.post(
        "/libros/pdf?tipo=novela",
        files={"archivo": ("vacio.pdf", b"", "application/pdf")},
    )
    assert respuesta.status_code == 400


def test_importar_pdf_no_pdf_devuelve_400(cliente):
    respuesta = cliente.post(
        "/libros/pdf?tipo=novela",
        files={"archivo": ("libro.epub", b"PK\x03\x04", "application/pdf")},
    )
    assert respuesta.status_code == 400


def test_preview_pdf_tipo_invalido_devuelve_400(cliente):
    respuesta = cliente.post(
        "/libros/pdf/preview?tipo=cualquiera",
        files={"archivo": ("libro.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert respuesta.status_code == 400


def test_importar_pdf_con_reportlab(cliente, tmp_path):
    """Test de integración completo si reportlab está disponible."""
    pdf_bytes = crear_pdf_bytes_simple("Mi PDF de prueba")
    if not pdf_bytes:
        import pytest as _pytest
        _pytest.skip("reportlab no disponible; se omite test de integración PDF")

    respuesta = cliente.post(
        "/libros/pdf?tipo=novela",
        files={"archivo": ("mi-pdf.pdf", pdf_bytes, "application/pdf")},
    )
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["capitulos"] >= 1
    assert datos["portada"] is None


def test_preview_pdf_con_reportlab(cliente, tmp_path):
    """Preview sin guardar si reportlab está disponible."""
    pdf_bytes = crear_pdf_bytes_simple("Preview test")
    if not pdf_bytes:
        import pytest as _pytest
        _pytest.skip("reportlab no disponible; se omite test de integración PDF")

    respuesta = cliente.post(
        "/libros/pdf/preview?tipo=cuento",
        files={"archivo": ("preview.pdf", pdf_bytes, "application/pdf")},
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert "capitulos" in datos
    assert datos["tipo"] == "cuento"


def test_renombrar_libro_cambia_el_titulo(cliente, tmp_path):
    respuesta = cliente.patch("/libros/libro-prueba", json={"titulo": "  Título corregido  "})
    assert respuesta.status_code == 200
    assert respuesta.json()["titulo"] == "Título corregido"
    assert cliente.get("/libros/libro-prueba").json()["titulo"] == "Título corregido"
    indice = json.loads((tmp_path / "libro-prueba" / "indice.json").read_text(encoding="utf-8"))
    assert indice["titulo"] == "Título corregido"
    # El resto del índice no se toca
    assert indice["capitulos"][0]["archivo"] == "001.txt"


def test_renombrar_libro_con_titulo_vacio_devuelve_400(cliente):
    assert cliente.patch("/libros/libro-prueba", json={"titulo": "   "}).status_code == 400


def test_renombrar_libro_con_titulo_muy_largo_devuelve_400(cliente):
    assert cliente.patch("/libros/libro-prueba", json={"titulo": "x" * 201}).status_code == 400


def test_renombrar_libro_inexistente_devuelve_404(cliente):
    assert cliente.patch("/libros/no-existe", json={"titulo": "Nuevo"}).status_code == 404
