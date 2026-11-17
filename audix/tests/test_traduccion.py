import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend import main, seguridad, trabajos  # noqa: E402
from backend.pipeline import traductor  # noqa: E402

CLAVE = "clave-de-prueba-123"


def preparar_acceso(carpeta, monkeypatch):
    monkeypatch.setattr(seguridad, "SCRYPT_N", 2 ** 4)  # scrypt liviano para que sea rápido
    main.freno.reiniciar()
    seguridad.guardar_clave(carpeta, CLAVE)


def entrar(cliente):
    assert cliente.post("/sesion", json={"clave": CLAVE}).status_code == 204
    return cliente

TEXTO_EN = (
    "The old man walked slowly along the road and he said that it was the best day "
    "of the year. They were all at the market when the rain began, and she had not "
    "brought her coat with her, but there was nothing to be done about it."
)
TEXTO_ES = (
    "El viejo caminaba despacio por el camino y dijo que era el mejor día del año. "
    "Todos estaban en el mercado cuando empezó la lluvia, y ella no había traído su "
    "abrigo, pero no había nada que hacer con eso."
)


def falso(texto: str) -> str:
    """Traductor de mentira: marca lo traducido para poder comprobarlo."""
    return f"<{texto}>"


def crear_libro(carpeta: Path, titulo: str, texto: str, capitulos: int = 2) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    lista = []
    for numero in range(1, capitulos + 1):
        archivo = f"{numero:03d}.txt"
        contenido = f"{texto}\n\nSegundo párrafo {numero}."
        (carpeta / archivo).write_text(contenido, encoding="utf-8")
        lista.append({
            "numero": numero, "titulo": f"Chapter {numero}",
            "archivo": archivo, "caracteres": len(contenido),
        })
    (carpeta / "indice.json").write_text(
        json.dumps({"titulo": titulo, "autor": "Autor", "portada": None, "capitulos": lista}),
        encoding="utf-8",
    )


def esperar_trabajo(cliente, trabajo_id, estado_final=("listo", "error")):
    for _ in range(200):
        trabajo = cliente.get(f"/trabajos/{trabajo_id}")
        if trabajo.status_code == 404 or trabajo.json()["estado"] in estado_final:
            return trabajo
        time.sleep(0.05)
    raise AssertionError("El trabajo no terminó a tiempo")


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    crear_libro(tmp_path / "book-en", "Book", TEXTO_EN)
    crear_libro(tmp_path / "libro-es", "Libro", TEXTO_ES)
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(traductor, "obtener_traductor", lambda origen, destino: falso)
    preparar_acceso(tmp_path, monkeypatch)
    for trabajo in trabajos.listar():
        trabajos.quitar(trabajo["id"])
    return entrar(TestClient(main.app, base_url="https://testserver"))


# --- Detección de idioma -----------------------------------------------------

def test_detecta_ingles_y_espanol():
    assert traductor.detectar_idioma(TEXTO_EN) == "en"
    assert traductor.detectar_idioma(TEXTO_ES) == "es"


def test_texto_corto_o_ambiguo_no_se_adivina():
    assert traductor.detectar_idioma("Hola mundo") is None
    assert traductor.detectar_idioma("xyz " * 100) is None


def test_detalle_del_libro_incluye_el_idioma(cliente):
    assert cliente.get("/libros/book-en").json()["idioma"] == "en"
    assert cliente.get("/libros/libro-es").json()["idioma"] == "es"


# --- Texto -------------------------------------------------------------------

def test_traducir_texto_conserva_parrafos_y_versos():
    resultado = traductor.traducir_texto("Uno\nDos\n\nTres", falso)
    assert resultado == "<Uno>\n<Dos>\n\n<Tres>"


def test_lineas_largas_se_parten_entre_oraciones():
    linea = " ".join(f"Frase número {n} de prueba." for n in range(80))
    trozos = traductor._partir_linea(linea, maximo=200)
    assert len(trozos) > 1
    assert all(len(t) <= 200 for t in trozos)
    assert " ".join(trozos) == linea


def test_oracion_sin_puntos_tambien_se_parte():
    trozos = traductor._partir_linea("palabra " * 200, maximo=100)
    assert all(len(t) <= 100 for t in trozos)


# --- API ---------------------------------------------------------------------

def test_traducir_crea_un_libro_nuevo_y_no_toca_el_original(cliente, tmp_path):
    original = (tmp_path / "book-en" / "001.txt").read_text(encoding="utf-8")

    respuesta = cliente.post("/libros/book-en/traducir", json={"destino": "es"})
    assert respuesta.status_code == 202
    trabajo = esperar_trabajo(cliente, respuesta.json()["id"]).json()
    assert trabajo["estado"] == "listo"
    assert trabajo["progreso"] == 100

    nuevo = cliente.get(f"/libros/{trabajo['libro_id']}").json()
    assert nuevo["titulo"] == "Book (ES)"
    assert nuevo["idioma"] == "es"
    assert nuevo["traducido_de"] == {"libro": "book-en", "idioma": "en"}
    assert [c["titulo"] for c in nuevo["capitulos"]] == ["<Chapter 1>", "<Chapter 2>"]
    capitulo = cliente.get(f"/libros/{nuevo['id']}/capitulos/1").json()
    assert capitulo["texto"].startswith("<The old man")
    assert capitulo["caracteres"] == len(capitulo["texto"])

    assert (tmp_path / "book-en" / "001.txt").read_text(encoding="utf-8") == original
    assert len(cliente.get("/libros").json()) == 3
    assert not list(tmp_path.glob(".traduciendo-*"))  # limpió la carpeta de trabajo


def test_traducir_al_mismo_idioma_devuelve_400(cliente):
    assert cliente.post("/libros/book-en/traducir", json={"destino": "en"}).status_code == 400


def test_idioma_de_destino_invalido_devuelve_400(cliente):
    assert cliente.post("/libros/book-en/traducir", json={"destino": "fr"}).status_code == 400


def test_libro_inexistente_devuelve_404(cliente):
    assert cliente.post("/libros/no-existe/traducir", json={"destino": "es"}).status_code == 404


def test_sin_motor_instalado_devuelve_503_con_el_motivo(cliente, monkeypatch):
    def sin_motor(origen, destino):
        raise traductor.TraduccionNoDisponible("Falta instalar el motor de traducción.")

    monkeypatch.setattr(traductor, "obtener_traductor", sin_motor)
    respuesta = cliente.post("/libros/book-en/traducir", json={"destino": "es"})
    assert respuesta.status_code == 503
    assert "Falta instalar" in respuesta.json()["detail"]
    assert trabajos.listar() == []


def test_requiere_sesion(tmp_path, monkeypatch):
    crear_libro(tmp_path / "book-en", "Book", TEXTO_EN)
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    preparar_acceso(tmp_path, monkeypatch)
    anonimo = TestClient(main.app, base_url="https://testserver")
    assert anonimo.post("/libros/book-en/traducir", json={"destino": "es"}).status_code == 401


def test_no_se_puede_traducir_dos_veces_a_la_vez(cliente, monkeypatch):
    import threading
    soltar = threading.Event()

    def lento(texto):
        soltar.wait(5)
        return texto

    monkeypatch.setattr(traductor, "obtener_traductor", lambda o, d: lento)
    primero = cliente.post("/libros/book-en/traducir", json={"destino": "es"})
    assert primero.status_code == 202
    assert cliente.post("/libros/book-en/traducir", json={"destino": "es"}).status_code == 409
    soltar.set()
    esperar_trabajo(cliente, primero.json()["id"])


def test_cancelar_descarta_lo_traducido(cliente, tmp_path, monkeypatch):
    import threading
    arranco = threading.Event()
    soltar = threading.Event()

    def lento(texto):
        arranco.set()
        soltar.wait(5)
        return texto

    monkeypatch.setattr(traductor, "obtener_traductor", lambda o, d: lento)
    trabajo = cliente.post("/libros/book-en/traducir", json={"destino": "es"}).json()
    assert arranco.wait(5)

    cancelado = cliente.post(f"/trabajos/{trabajo['id']}/cancelar")
    assert cancelado.status_code == 202
    soltar.set()

    assert esperar_trabajo(cliente, trabajo["id"]).status_code == 404  # el trabajo desaparece
    assert not list(tmp_path.glob(".traduciendo-*"))
    assert len(cliente.get("/libros").json()) == 2  # no quedó libro nuevo


def test_no_se_cancela_una_importacion_ni_un_trabajo_inexistente(cliente):
    importacion = trabajos.crear(nombre="x.pdf", tipo="novela")
    assert cliente.post(f"/trabajos/{importacion['id']}/cancelar").status_code == 409
    assert cliente.post("/trabajos/nadie/cancelar").status_code == 404


def test_error_conserva_lo_traducido_y_al_reintentar_lo_reutiliza(cliente, tmp_path, monkeypatch):
    llamadas = []

    def falla_en_el_segundo(texto):
        llamadas.append(texto)
        if texto.startswith("Segundo párrafo 2"):
            raise RuntimeError("se cortó")
        return f"<{texto}>"

    monkeypatch.setattr(traductor, "obtener_traductor", lambda o, d: falla_en_el_segundo)
    trabajo = cliente.post("/libros/book-en/traducir", json={"destino": "es"}).json()
    assert esperar_trabajo(cliente, trabajo["id"]).json()["estado"] == "error"
    assert (tmp_path / ".traduciendo-book-en-es" / "001.txt").exists()

    llamadas.clear()
    monkeypatch.setattr(traductor, "obtener_traductor", lambda o, d: falso)
    trabajos.quitar(trabajo["id"])
    nuevo = cliente.post("/libros/book-en/traducir", json={"destino": "es"}).json()
    assert esperar_trabajo(cliente, nuevo["id"]).json()["estado"] == "listo"
    assert llamadas == []  # no volvió a llamar al motor viejo


def test_reanudar_retoma_lo_que_quedo_a_medias(cliente, tmp_path):
    # Simula un reinicio: el capítulo 1 ya estaba traducido en la carpeta de trabajo.
    trabajo_dir = tmp_path / ".traduciendo-book-en-es"
    trabajo_dir.mkdir()
    (trabajo_dir / "001.txt").write_text("<ya hecho>", encoding="utf-8")
    (trabajo_dir / "estado.json").write_text(json.dumps({
        "origen": "book-en", "de": "en", "a": "es",
        "hechos": {"1": {"titulo": "<Chapter 1>", "caracteres": 10}},
    }), encoding="utf-8")

    main.reanudar_traducciones()
    (trabajo,) = trabajos.listar()
    assert trabajo["clase"] == "traduccion"
    listo = esperar_trabajo(cliente, trabajo["id"]).json()
    assert listo["estado"] == "listo"

    nuevo = cliente.get(f"/libros/{listo['libro_id']}").json()
    assert cliente.get(f"/libros/{nuevo['id']}/capitulos/1").json()["texto"] == "<ya hecho>"
    assert cliente.get(f"/libros/{nuevo['id']}/capitulos/2").json()["texto"].startswith("<The old man")


def test_reanudar_descarta_carpetas_sin_libro_original(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    huerfana = tmp_path / ".traduciendo-borrado-es"
    huerfana.mkdir()
    (huerfana / "estado.json").write_text(
        json.dumps({"origen": "borrado", "de": "en", "a": "es", "hechos": {}}), encoding="utf-8"
    )
    main.reanudar_traducciones()
    assert not huerfana.exists()


def test_la_portada_se_copia_al_libro_traducido(cliente, tmp_path):
    (tmp_path / "book-en" / "portada.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    indice = json.loads((tmp_path / "book-en" / "indice.json").read_text(encoding="utf-8"))
    indice["portada"] = "portada.png"
    (tmp_path / "book-en" / "indice.json").write_text(json.dumps(indice), encoding="utf-8")

    trabajo = cliente.post("/libros/book-en/traducir", json={"destino": "es"}).json()
    listo = esperar_trabajo(cliente, trabajo["id"]).json()
    assert cliente.get(f"/libros/{listo['libro_id']}/portada").status_code == 200


def test_los_modelos_se_guardan_dentro_de_la_carpeta_de_datos(tmp_path, monkeypatch):
    for variable in ("ARGOS_PACKAGES_DIR", "XDG_DATA_HOME", "XDG_CACHE_HOME", "LOCALAPPDATA"):
        monkeypatch.setenv(variable, "antes")  # monkeypatch los restaura al terminar
    monkeypatch.setenv("AUDIX_DATA_DIR", str(tmp_path))

    traductor._preparar_carpetas()

    base = tmp_path / "modelos-traduccion"
    assert base.is_dir()
    for variable in ("ARGOS_PACKAGES_DIR", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        assert Path(__import__("os").environ[variable]).is_relative_to(base)


def test_sin_el_motor_instalado_el_error_explica_que_falta(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIX_DATA_DIR", str(tmp_path))
    monkeypatch.setitem(sys.modules, "argostranslate", None)  # simula que no está instalado
    with pytest.raises(traductor.TraduccionNoDisponible, match="Falta instalar"):
        traductor.obtener_traductor("en", "es")
