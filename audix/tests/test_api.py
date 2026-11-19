import io
import json
import sys
import threading
from pathlib import Path

import pytest
from ebooklib import epub
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend import main, seguridad  # noqa: E402

CLAVE = "clave-de-prueba-123"


def preparar_acceso(carpeta, monkeypatch):
    """Crea la clave en la carpeta de datos de prueba (con scrypt liviano, para que sea rápido)."""
    monkeypatch.setattr(seguridad, "SCRYPT_N", 2 ** 4)
    main.freno.reiniciar()
    seguridad.guardar_clave(carpeta, CLAVE)


def entrar(cliente):
    respuesta = cliente.post("/sesion", json={"clave": CLAVE})
    assert respuesta.status_code == 204
    return cliente


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
    preparar_acceso(tmp_path, monkeypatch)
    return entrar(TestClient(main.app))


def test_health(cliente):
    assert cliente.get("/health").json() == {"estado": "ok"}


def test_lista_libros(cliente):
    libros = cliente.get("/libros").json()
    assert libros == [
        {
            "id": "libro-prueba",
            "titulo": "Libro de prueba",
            "autor": "Autor",
            "capitulos": 1,
            "voz": {"motor": "sistema", "voz_id": None, "tono": "normal"},
            "audio": None,
            "portada": None,
        }
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
# Tests de los endpoints PDF (importación en segundo plano)
# ---------------------------------------------------------------------------

import time as _time


def crear_pdf_bytes_simple(titulo: str = "Test PDF") -> bytes:
    """PDF mínimo con capa de texto. Devuelve b'' si reportlab no está instalado."""
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
        c.showPage()
        c.drawString(72, 720, "II")
        c.drawString(72, 690, "Este es el texto del segundo capítulo.")
        c.save()
        return buf.getvalue()
    except ImportError:
        return b""


def esperar_trabajo(cliente, trabajo_id: str, limite: float = 60.0) -> dict:
    """Consulta el trabajo hasta que termine o se acabe el tiempo."""
    fin = _time.time() + limite
    while _time.time() < fin:
        datos = cliente.get(f"/trabajos/{trabajo_id}").json()
        if datos["estado"] != "en_curso":
            return datos
        _time.sleep(0.2)
    raise AssertionError("El trabajo no terminó a tiempo")


def test_importar_pdf_rechaza_no_pdf(cliente):
    respuesta = cliente.post(
        "/libros/pdf?tipo=novela",
        files={"archivo": ("libro.epub", b"PK\x03\x04", "application/pdf")},
    )
    assert respuesta.status_code == 400


def test_importar_pdf_vacio_devuelve_400(cliente):
    respuesta = cliente.post(
        "/libros/pdf?tipo=novela",
        files={"archivo": ("vacio.pdf", b"", "application/pdf")},
    )
    assert respuesta.status_code == 400


def test_importar_pdf_tipo_invalido_devuelve_400(cliente):
    respuesta = cliente.post(
        "/libros/pdf?tipo=inventado",
        files={"archivo": ("libro.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert respuesta.status_code == 400


def test_importar_pdf_responde_202_con_trabajo_en_curso(cliente):
    pdf_bytes = crear_pdf_bytes_simple("Trabajo")
    if not pdf_bytes:
        import pytest as _pytest
        _pytest.skip("reportlab no disponible")
    respuesta = cliente.post(
        "/libros/pdf?tipo=novela",
        files={"archivo": ("trabajo.pdf", pdf_bytes, "application/pdf")},
    )
    assert respuesta.status_code == 202
    trabajo = respuesta.json()
    assert trabajo["estado"] == "en_curso"
    assert trabajo["nombre"] == "trabajo.pdf"


def test_importacion_en_segundo_plano_termina_y_crea_el_libro(cliente, tmp_path):
    pdf_bytes = crear_pdf_bytes_simple("Libro en segundo plano")
    if not pdf_bytes:
        import pytest as _pytest
        _pytest.skip("reportlab no disponible")
    trabajo = cliente.post(
        "/libros/pdf?tipo=novela",
        files={"archivo": ("bg.pdf", pdf_bytes, "application/pdf")},
    ).json()

    final = esperar_trabajo(cliente, trabajo["id"])
    assert final["estado"] == "listo", final
    assert final["progreso"] == 100
    assert final["libro_id"]
    libro = cliente.get(f"/libros/{final['libro_id']}").json()
    assert libro["titulo"]


def test_trabajo_con_pdf_invalido_queda_en_error(cliente):
    trabajo = cliente.post(
        "/libros/pdf?tipo=novela",
        files={"archivo": ("roto.pdf", b"esto no es un pdf", "application/pdf")},
    ).json()
    final = esperar_trabajo(cliente, trabajo["id"])
    assert final["estado"] == "error"
    assert final["error"]


def test_listar_trabajos_incluye_el_creado(cliente):
    pdf_bytes = crear_pdf_bytes_simple("Listado")
    if not pdf_bytes:
        import pytest as _pytest
        _pytest.skip("reportlab no disponible")
    trabajo = cliente.post(
        "/libros/pdf?tipo=cuento",
        files={"archivo": ("lista.pdf", pdf_bytes, "application/pdf")},
    ).json()
    ids = [t["id"] for t in cliente.get("/trabajos").json()]
    assert trabajo["id"] in ids


def test_trabajo_inexistente_devuelve_404(cliente):
    assert cliente.get("/trabajos/no-existe").status_code == 404


def test_quitar_trabajo_terminado(cliente):
    trabajo = cliente.post(
        "/libros/pdf?tipo=novela",
        files={"archivo": ("roto2.pdf", b"nada", "application/pdf")},
    ).json()
    esperar_trabajo(cliente, trabajo["id"])
    assert cliente.delete(f"/trabajos/{trabajo['id']}").status_code == 204
    assert cliente.get(f"/trabajos/{trabajo['id']}").status_code == 404


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


# ---------------------------------------------------------------------------
# Voz: configuración por libro (voz del sistema / voz narrada)
# ---------------------------------------------------------------------------

def test_libro_viejo_sin_voz_usa_sistema_por_defecto(cliente):
    # El fixture "libro-prueba" no tiene clave "voz" en su indice.json, como
    # cualquier libro importado antes de este cambio.
    datos = cliente.get("/libros/libro-prueba").json()
    assert datos["voz"] == {"motor": "sistema", "voz_id": None, "tono": "normal"}


def test_catalogo_de_voces(cliente):
    catalogo = cliente.get("/voces").json()
    ids = [voz["id"] for voz in catalogo["voces"]]
    assert "es-AR-TomasNeural" in ids
    idiomas = {voz["id"]: voz["idioma"] for voz in catalogo["voces"]}
    assert idiomas["es-AR-TomasNeural"] == "Español"
    assert idiomas["en-US-AriaNeural"] == "Inglés"
    assert idiomas["en-GB-RyanNeural"] == "Inglés"
    assert catalogo["voz_predeterminada"] in ids
    assert {tono["id"] for tono in catalogo["tonos"]} == {"normal", "oscuro", "grave"}


def test_importar_epub_con_voz_narrada_guarda_la_config(cliente, tmp_path):
    contenido = crear_epub_bytes("Libro narrado", tmp_path)
    respuesta = cliente.post(
        "/libros?motor_voz=narracion&voz_id=es-AR-ElenaNeural&tono=oscuro",
        files={"archivo": ("libro.epub", contenido, "application/epub+zip")},
    )
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["voz"] == {"motor": "narracion", "voz_id": "es-AR-ElenaNeural", "tono": "oscuro"}
    assert cliente.get(f"/libros/{datos['id']}").json()["voz"] == datos["voz"]


def test_importar_epub_motor_de_voz_invalido_devuelve_400(cliente, tmp_path):
    contenido = crear_epub_bytes("Libro con voz inválida", tmp_path)
    respuesta = cliente.post(
        "/libros?motor_voz=inventado",
        files={"archivo": ("libro.epub", contenido, "application/epub+zip")},
    )
    assert respuesta.status_code == 400


def test_importar_epub_voz_narrada_sin_voz_id_usa_la_predeterminada(cliente, tmp_path):
    contenido = crear_epub_bytes("Sin voz elegida", tmp_path)
    respuesta = cliente.post(
        "/libros?motor_voz=narracion",
        files={"archivo": ("libro.epub", contenido, "application/epub+zip")},
    )
    datos = respuesta.json()
    assert datos["voz"]["motor"] == "narracion"
    assert datos["voz"]["voz_id"]  # alguna voz válida, la predeterminada


def test_cambiar_voz_de_un_libro(cliente):
    respuesta = cliente.patch(
        "/libros/libro-prueba/voz",
        json={"motor": "narracion", "voz_id": "es-ES-AlvaroNeural", "tono": "grave"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["voz"] == {"motor": "narracion", "voz_id": "es-ES-AlvaroNeural", "tono": "grave"}
    assert cliente.get("/libros/libro-prueba").json()["voz"]["motor"] == "narracion"

    # Y se puede volver a la voz del sistema en cualquier momento (el "rollback" por libro).
    vuelta = cliente.patch("/libros/libro-prueba/voz", json={"motor": "sistema", "tono": "normal"})
    assert vuelta.json()["voz"] == {"motor": "sistema", "voz_id": None, "tono": "normal"}


def test_cambiar_voz_invalida_devuelve_400(cliente):
    assert cliente.patch("/libros/libro-prueba/voz", json={"motor": "sistema", "tono": "inventado"}).status_code == 400
    assert cliente.patch("/libros/libro-prueba/voz", json={"motor": "narracion", "voz_id": "no-existe"}).status_code == 400


def test_cambiar_voz_de_libro_inexistente_devuelve_404(cliente):
    assert cliente.patch("/libros/no-existe/voz", json={"motor": "sistema"}).status_code == 404


# ---------------------------------------------------------------------------
# Audio narrado: generación por capítulo (mockeando edge-tts, sin red)
# ---------------------------------------------------------------------------

def _generador_de_audio_falso(textos_vistos=None, espera=None):
    """Sustituye a `generar_audio_capitulo`: no llama a ningún servicio, solo
    escribe un mp3 de prueba y devuelve marcas fijas. Sin red.

    `espera`, si se pasa, es un threading.Event: el hilo de generación no
    termina hasta que el test lo libera. Sirve para probar a propósito qué
    pasa mientras un trabajo todavía está en curso."""

    def generar(texto: str, voz_id: str, tono: str, destino_mp3) -> list[dict]:
        if espera is not None:
            espera.wait(timeout=5)
        if textos_vistos is not None:
            textos_vistos.append(texto)
        destino_mp3.write_bytes(b"mp3-de-prueba")
        return [{"texto": texto[:20], "inicio": 0.0, "fin": 1.0}]

    return generar


def test_generar_audio_en_libro_con_voz_de_sistema_devuelve_400(cliente):
    respuesta = cliente.post("/libros/libro-prueba/capitulos/1/audio")
    assert respuesta.status_code == 400


def test_generar_audio_de_capitulo_inexistente_devuelve_404(cliente):
    cliente.patch("/libros/libro-prueba/voz", json={"motor": "narracion"})
    assert cliente.post("/libros/libro-prueba/capitulos/99/audio").status_code == 404


def test_generar_audio_arranca_trabajo_y_queda_cacheado(cliente, monkeypatch):
    monkeypatch.setattr(main, "generar_audio_capitulo", _generador_de_audio_falso())
    cliente.patch("/libros/libro-prueba/voz", json={"motor": "narracion", "voz_id": "es-AR-TomasNeural"})

    primera = cliente.post("/libros/libro-prueba/capitulos/1/audio")
    assert primera.status_code == 200
    cuerpo = primera.json()
    assert cuerpo["listo"] is False
    assert cuerpo["trabajo"]["estado"] == "en_curso"

    final = esperar_trabajo(cliente, cuerpo["trabajo"]["id"])
    assert final["estado"] == "listo"

    # Ya generado: una segunda llamada lo avisa de una, sin trabajo nuevo.
    segunda = cliente.post("/libros/libro-prueba/capitulos/1/audio")
    assert segunda.json() == {"listo": True, "trabajo": None}

    audio = cliente.get("/libros/libro-prueba/capitulos/1/audio")
    assert audio.status_code == 200
    assert audio.content == b"mp3-de-prueba"

    marcas = cliente.get("/libros/libro-prueba/capitulos/1/audio/marcas")
    assert marcas.status_code == 200
    assert marcas.json() == [{"texto": "Primer capítulo.", "inicio": 0.0, "fin": 1.0}]


def test_audio_y_marcas_sin_generar_devuelven_404(cliente):
    cliente.patch("/libros/libro-prueba/voz", json={"motor": "narracion"})
    assert cliente.get("/libros/libro-prueba/capitulos/1/audio").status_code == 404
    assert cliente.get("/libros/libro-prueba/capitulos/1/audio/marcas").status_code == 404


def test_generar_audio_dos_veces_seguidas_no_duplica_el_trabajo(cliente, monkeypatch):
    import threading

    vistos = []
    espera = threading.Event()
    monkeypatch.setattr(main, "generar_audio_capitulo", _generador_de_audio_falso(vistos, espera))
    cliente.patch("/libros/libro-prueba/voz", json={"motor": "narracion"})

    primera = cliente.post("/libros/libro-prueba/capitulos/1/audio").json()
    segunda = cliente.post("/libros/libro-prueba/capitulos/1/audio").json()
    espera.set()  # recién ahora deja terminar al hilo, ya hicimos las dos llamadas
    # La segunda ve que ya hay un trabajo en curso para ese mismo capítulo y no arranca otro.
    assert segunda["trabajo"]["id"] == primera["trabajo"]["id"]

    esperar_trabajo(cliente, primera["trabajo"]["id"])
    assert len(vistos) == 1


def test_cambiar_voz_borra_el_audio_ya_generado_si_cambia_de_verdad(cliente, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "generar_audio_capitulo", _generador_de_audio_falso())
    cliente.patch("/libros/libro-prueba/voz", json={"motor": "narracion", "voz_id": "es-AR-TomasNeural"})
    trabajo = cliente.post("/libros/libro-prueba/capitulos/1/audio").json()["trabajo"]
    esperar_trabajo(cliente, trabajo["id"])
    assert (tmp_path / "libro-prueba" / "audio" / "001.mp3").exists()

    # Cambiar el tono es cambiar de verdad: el audio viejo ya no corresponde.
    cliente.patch("/libros/libro-prueba/voz", json={"motor": "narracion", "voz_id": "es-AR-TomasNeural", "tono": "oscuro"})
    assert not (tmp_path / "libro-prueba" / "audio" / "001.mp3").exists()

    # Guardar la misma configuración de nuevo no borra nada (no cambió nada de verdad).
    cliente.patch("/libros/libro-prueba/voz", json={"motor": "narracion", "voz_id": "es-AR-TomasNeural", "tono": "oscuro"})
    trabajo2 = cliente.post("/libros/libro-prueba/capitulos/1/audio").json()["trabajo"]
    esperar_trabajo(cliente, trabajo2["id"])
    cliente.patch("/libros/libro-prueba/voz", json={"motor": "narracion", "voz_id": "es-AR-TomasNeural", "tono": "oscuro"})
    assert (tmp_path / "libro-prueba" / "audio" / "001.mp3").exists()


# ---------------------------------------------------------------------------
# Audio automático: al importar, el libro entero se genera en segundo plano
# ---------------------------------------------------------------------------

def _crear_libro_en_disco(carpeta_datos, libro_id: str, capitulos: int, motor: str = "narracion") -> Path:
    carpeta = carpeta_datos / libro_id
    carpeta.mkdir()
    indice = {"titulo": libro_id, "autor": "A", "capitulos": [], "voz": {"motor": motor, "voz_id": None, "tono": "normal"}}
    if motor == "narracion":
        indice["voz"]["voz_id"] = "es-AR-TomasNeural"
    for numero in range(1, capitulos + 1):
        (carpeta / f"{numero:03d}.txt").write_text(f"Texto del capítulo {numero}.", encoding="utf-8")
        indice["capitulos"].append(
            {"numero": numero, "titulo": f"Cap {numero}", "archivo": f"{numero:03d}.txt", "caracteres": 20}
        )
    (carpeta / "indice.json").write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")
    return carpeta


def _esperar_audio(cliente, libro_id: str, limite: float = 10.0) -> dict:
    """Espera a que el hilo de audio termine con el libro y devuelve su estado."""
    fin = _time.time() + limite
    while _time.time() < fin:
        estado = cliente.get(f"/libros/{libro_id}/audio").json()
        if not estado["generando"]:
            return estado
        _time.sleep(0.05)
    raise AssertionError("El audio no terminó a tiempo")


@pytest.fixture
def audio_automatico(monkeypatch):
    """Enciende la generación en segundo plano, sin esperas ni red."""
    monkeypatch.setattr(main, "AUDIO_AUTOMATICO", True)
    monkeypatch.setattr(main, "ESPERA_ENTRE_REINTENTOS", 0)
    monkeypatch.setattr(main, "ESPERA_ENTRE_RONDAS", 0)
    main._errores_audio.clear()
    yield
    main._errores_audio.clear()


def test_importar_sin_elegir_voz_usa_narracion_y_no_genera_con_la_opcion_apagada(cliente, tmp_path):
    contenido = crear_epub_bytes("Narrado por defecto", tmp_path)
    datos = cliente.post(
        "/libros", files={"archivo": ("libro.epub", contenido, "application/epub+zip")}
    ).json()
    assert datos["voz"]["motor"] == "narracion"
    assert datos["voz"]["voz_id"] == "es-AR-TomasNeural"
    assert datos["audio"] == {"listos": 0, "total": 1, "generando": False, "error": None}


def test_importar_epub_genera_el_audio_del_libro_en_segundo_plano(cliente, tmp_path, monkeypatch, audio_automatico):
    textos = []
    monkeypatch.setattr(main, "generar_audio_capitulo", _generador_de_audio_falso(textos))
    contenido = crear_epub_bytes("Libro con audio", tmp_path)
    datos = cliente.post(
        "/libros", files={"archivo": ("libro.epub", contenido, "application/epub+zip")}
    ).json()

    estado = _esperar_audio(cliente, datos["id"])
    assert estado["listos"] == [1]
    assert estado["error"] is None
    assert len(textos) == 1
    assert cliente.get(f"/libros/{datos['id']}/capitulos/1/audio/marcas").status_code == 200
    # La biblioteca y el detalle muestran el avance.
    assert cliente.get(f"/libros/{datos['id']}").json()["audio"]["listos"] == 1
    en_lista = next(l for l in cliente.get("/libros").json() if l["id"] == datos["id"])
    assert en_lista["audio"]["listos"] == 1


def test_el_audio_se_genera_en_orden_y_solo_lo_que_falta(cliente, tmp_path, monkeypatch, audio_automatico):
    carpeta = _crear_libro_en_disco(tmp_path, "libro-largo", 3)
    # El capítulo 2 ya tenía audio (de una corrida anterior que se cortó).
    (carpeta / "audio").mkdir()
    (carpeta / "audio" / "002.mp3").write_bytes(b"viejo")
    (carpeta / "audio" / "002.json").write_text("[]", encoding="utf-8")

    textos = []
    monkeypatch.setattr(main, "generar_audio_capitulo", _generador_de_audio_falso(textos))
    main._encolar_audio("libro-largo")

    estado = _esperar_audio(cliente, "libro-largo")
    assert estado["listos"] == [1, 2, 3]
    assert textos == ["Texto del capítulo 1.", "Texto del capítulo 3."]
    assert (carpeta / "audio" / "002.mp3").read_bytes() == b"viejo"


def test_al_arrancar_se_retoma_el_audio_pendiente(cliente, tmp_path, monkeypatch, audio_automatico):
    _crear_libro_en_disco(tmp_path, "pendiente", 2)
    _crear_libro_en_disco(tmp_path, "con-voz-de-sistema", 2, motor="sistema")
    textos = []
    monkeypatch.setattr(main, "generar_audio_capitulo", _generador_de_audio_falso(textos))

    main._reanudar_audio_pendiente()  # es lo que corre el servidor al arrancar

    assert _esperar_audio(cliente, "pendiente")["listos"] == [1, 2]
    assert len(textos) == 2  # el libro con voz del sistema no se toca
    assert not (tmp_path / "con-voz-de-sistema" / "audio").exists()


def test_un_capitulo_que_falla_se_reintenta(cliente, tmp_path, monkeypatch, audio_automatico):
    _crear_libro_en_disco(tmp_path, "inestable", 1)
    intentos = []

    def generar(texto, voz_id, tono, destino_mp3):
        intentos.append(1)
        if len(intentos) < 3:
            raise RuntimeError("sin conexión")
        destino_mp3.write_bytes(b"mp3")
        return [{"texto": texto, "inicio": 0.0, "fin": 1.0}]

    monkeypatch.setattr(main, "generar_audio_capitulo", generar)
    main._encolar_audio("inestable")

    estado = _esperar_audio(cliente, "inestable")
    assert estado["listos"] == [1]
    assert estado["error"] is None
    assert len(intentos) == 3


def test_si_siempre_falla_queda_el_error_y_se_puede_reintentar(cliente, tmp_path, monkeypatch, audio_automatico):
    _crear_libro_en_disco(tmp_path, "sin-internet", 2)
    monkeypatch.setattr(main, "RONDAS_CON_FALLOS_MAXIMAS", 2)
    en_linea = {"si": False}

    def generar(texto, voz_id, tono, destino_mp3):
        if not en_linea["si"]:
            raise RuntimeError("sin conexión")
        destino_mp3.write_bytes(b"mp3")
        return [{"texto": texto, "inicio": 0.0, "fin": 1.0}]

    monkeypatch.setattr(main, "generar_audio_capitulo", generar)
    main._encolar_audio("sin-internet")
    estado = _esperar_audio(cliente, "sin-internet")
    assert estado["listos"] == []
    assert "sin conexión" in estado["error"]

    # Vuelve internet: pedirlo de nuevo retoma desde donde estaba.
    en_linea["si"] = True
    assert cliente.post("/libros/sin-internet/audio").status_code == 202
    estado = _esperar_audio(cliente, "sin-internet")
    assert estado["listos"] == [1, 2]
    assert estado["error"] is None


def test_cambiar_la_voz_regenera_el_audio_en_segundo_plano(cliente, tmp_path, monkeypatch, audio_automatico):
    _crear_libro_en_disco(tmp_path, "cambiante", 2)
    vistos = []

    def generar(texto, voz_id, tono, destino_mp3):
        vistos.append((voz_id, tono))
        destino_mp3.write_bytes(b"mp3")
        return [{"texto": texto, "inicio": 0.0, "fin": 1.0}]

    monkeypatch.setattr(main, "generar_audio_capitulo", generar)
    main._encolar_audio("cambiante")
    assert _esperar_audio(cliente, "cambiante")["listos"] == [1, 2]

    cliente.patch("/libros/cambiante/voz", json={"motor": "narracion", "voz_id": "es-AR-ElenaNeural", "tono": "oscuro"})
    estado = _esperar_audio(cliente, "cambiante")
    assert estado["listos"] == [1, 2]
    assert vistos[-2:] == [("es-AR-ElenaNeural", "oscuro")] * 2


def test_pasar_un_libro_viejo_a_narracion_genera_su_audio(cliente, tmp_path, monkeypatch, audio_automatico):
    textos = []
    monkeypatch.setattr(main, "generar_audio_capitulo", _generador_de_audio_falso(textos))
    cliente.patch("/libros/libro-prueba/voz", json={"motor": "narracion"})
    assert _esperar_audio(cliente, "libro-prueba")["listos"] == [1]
    assert textos == ["Primer capítulo."]


def test_pedir_el_audio_de_un_libro_con_voz_de_sistema_devuelve_400(cliente):
    assert cliente.post("/libros/libro-prueba/audio").status_code == 400


def test_estado_del_audio_de_un_libro_inexistente_devuelve_404(cliente):
    assert cliente.get("/libros/no-existe/audio").status_code == 404


def test_borrar_el_libro_mientras_se_genera_no_deja_carpeta_huerfana(cliente, tmp_path, monkeypatch, audio_automatico):
    _crear_libro_en_disco(tmp_path, "efimero", 1)
    espera = threading.Event()
    monkeypatch.setattr(main, "generar_audio_capitulo", _generador_de_audio_falso(espera=espera))
    main._encolar_audio("efimero")
    _time.sleep(0.1)  # el hilo ya está generando el capítulo

    assert cliente.delete("/libros/efimero").status_code == 204
    espera.set()
    fin = _time.time() + 5
    while "efimero" in main._libros_con_audio_en_cola and _time.time() < fin:
        _time.sleep(0.05)

    assert not (tmp_path / "efimero").exists()


def test_importar_con_voz_en_ingles_se_acepta(cliente, tmp_path):
    contenido = crear_epub_bytes("Libro en inglés", tmp_path)
    respuesta = cliente.post(
        "/libros?motor_voz=narracion&voz_id=en-US-GuyNeural&tono=grave",
        files={"archivo": ("libro.epub", contenido, "application/epub+zip")},
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["voz"] == {"motor": "narracion", "voz_id": "en-US-GuyNeural", "tono": "grave"}
