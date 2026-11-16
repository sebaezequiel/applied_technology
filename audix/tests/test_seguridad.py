import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend import main, seguridad  # noqa: E402

CLAVE = "clave-de-prueba-123"


@pytest.fixture
def datos(tmp_path, monkeypatch):
    """Carpeta de datos con un libro y la clave creada. Sin sesión iniciada."""
    libro = tmp_path / "libro-prueba"
    libro.mkdir()
    (libro / "001.txt").write_text("Primer capítulo.", encoding="utf-8")
    (libro / "indice.json").write_text(
        json.dumps({
            "titulo": "Libro de prueba",
            "autor": "Autor",
            "capitulos": [{"numero": 1, "titulo": "Uno", "archivo": "001.txt", "caracteres": 16}],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(seguridad, "SCRYPT_N", 2 ** 4)
    main.freno.reiniciar()
    seguridad.guardar_clave(tmp_path, CLAVE)
    return tmp_path


@pytest.fixture
def anonimo(datos):
    return TestClient(main.app)


@pytest.fixture
def cliente(datos):
    cliente = TestClient(main.app)
    assert cliente.post("/sesion", json={"clave": CLAVE}).status_code == 204
    return cliente


# ---------- Sin sesión no se entra a nada ----------

@pytest.mark.parametrize("metodo, ruta", [
    ("GET", "/libros"),
    ("GET", "/libros/libro-prueba"),
    ("GET", "/libros/libro-prueba/capitulos/1"),
    ("GET", "/libros/libro-prueba/portada"),
    ("POST", "/libros"),
    ("POST", "/libros/pdf"),
    ("PATCH", "/libros/libro-prueba"),
    ("PUT", "/libros/libro-prueba/portada"),
    ("DELETE", "/libros/libro-prueba"),
    ("GET", "/trabajos"),
    ("GET", "/trabajos/abc"),
    ("DELETE", "/trabajos/abc"),
    ("GET", "/ruta-que-no-existe"),
    ("GET", "/docs"),
    ("GET", "/openapi.json"),
])
def test_sin_sesion_responde_401(anonimo, metodo, ruta):
    assert anonimo.request(metodo, ruta).status_code == 401


def test_sin_sesion_no_se_borra_el_libro(anonimo, datos):
    anonimo.delete("/libros/libro-prueba")
    assert (datos / "libro-prueba" / "indice.json").exists()


def test_la_pwa_y_health_se_ven_sin_sesion(anonimo):
    for ruta in ("/", "/index.html", "/app.js", "/styles.css", "/sw.js", "/health"):
        assert anonimo.get(ruta).status_code == 200, ruta


def test_rutas_rebuscadas_no_pasan_por_archivo_estatico(anonimo):
    for ruta in ("/trabajos/..%2Fapp.js", "/trabajos/..%5Capp.js", "/app.js/", "/libros;/app.js"):
        assert anonimo.get(ruta).status_code in (401, 404), ruta
    assert anonimo.get("/trabajos/..%5Capp.js").status_code == 401


def test_la_documentacion_de_la_api_no_existe(cliente):
    assert cliente.get("/docs").status_code == 404
    assert cliente.get("/openapi.json").status_code == 404


# ---------- Inicio y cierre de sesión ----------

def test_estado_de_sesion(anonimo):
    assert anonimo.get("/sesion").json() == {"configurada": True, "activa": False}
    anonimo.post("/sesion", json={"clave": CLAVE})
    assert anonimo.get("/sesion").json() == {"configurada": True, "activa": True}


def test_clave_incorrecta(anonimo):
    respuesta = anonimo.post("/sesion", json={"clave": "otra-clave-cualquiera"})
    assert respuesta.status_code == 401
    assert "set-cookie" not in respuesta.headers
    assert anonimo.get("/libros").status_code == 401


def test_clave_correcta_da_acceso(cliente):
    assert cliente.get("/libros").status_code == 200


def test_la_cookie_no_la_lee_javascript_ni_otros_sitios(anonimo):
    cookie = anonimo.post("/sesion", json={"clave": CLAVE}).headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "secure" not in cookie  # la prueba va por HTTP


def test_por_https_la_cookie_es_secure(datos):
    cliente = TestClient(main.app, base_url="https://audix.example")
    cookie = cliente.post("/sesion", json={"clave": CLAVE}).headers["set-cookie"].lower()
    assert "secure" in cookie


def test_detras_del_proxy_https_la_cookie_es_secure(anonimo):
    respuesta = anonimo.post(
        "/sesion", json={"clave": CLAVE}, headers={"X-Forwarded-Proto": "https"}
    )
    assert "secure" in respuesta.headers["set-cookie"].lower()
    assert "strict-transport-security" in respuesta.headers


def test_cerrar_sesion(cliente):
    assert cliente.delete("/sesion").status_code == 204
    assert cliente.get("/libros").status_code == 401


def test_cerrar_sesion_invalida_el_token_en_el_servidor(datos):
    cliente = TestClient(main.app)
    cliente.post("/sesion", json={"clave": CLAVE})
    token = cliente.cookies.get(main.COOKIE_SESION)
    cliente.delete("/sesion")

    ladron = TestClient(main.app, cookies={main.COOKIE_SESION: token})
    assert ladron.get("/libros").status_code == 401


def test_token_inventado_no_sirve(datos):
    cliente = TestClient(main.app, cookies={main.COOKIE_SESION: "x" * 43})
    assert cliente.get("/libros").status_code == 401


def test_sesion_vencida_no_sirve(cliente, datos, monkeypatch):
    futuro = time.time() + seguridad.DURACION_SESION + 60
    monkeypatch.setattr(seguridad.time, "time", lambda: futuro)
    assert cliente.get("/libros").status_code == 401


def test_cambiar_la_clave_cierra_las_sesiones(cliente, datos):
    seguridad.guardar_clave(datos, "otra-clave-bien-larga")
    assert cliente.get("/libros").status_code == 401
    assert cliente.post("/sesion", json={"clave": CLAVE}).status_code == 401
    assert cliente.post("/sesion", json={"clave": "otra-clave-bien-larga"}).status_code == 204


def test_sin_clave_creada_no_entra_nadie(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    main.freno.reiniciar()
    cliente = TestClient(main.app)
    assert cliente.get("/sesion").json() == {"configurada": False, "activa": False}
    assert cliente.get("/libros").status_code == 401
    assert cliente.post("/sesion", json={"clave": ""}).status_code == 503
    assert cliente.post("/sesion", json={"clave": CLAVE}).status_code == 503


# ---------- Freno a la fuerza bruta ----------

def test_muchos_fallos_bloquean_incluso_la_clave_correcta(anonimo):
    for _ in range(seguridad.Freno.INTENTOS_LIBRES):
        assert anonimo.post("/sesion", json={"clave": "mala-mala-mala"}).status_code == 401

    bloqueado = anonimo.post("/sesion", json={"clave": CLAVE})
    assert bloqueado.status_code == 429
    assert int(bloqueado.headers["retry-after"]) > 0
    assert anonimo.get("/libros").status_code == 401


def test_el_bloqueo_se_levanta_con_el_tiempo(anonimo, monkeypatch):
    for _ in range(seguridad.Freno.INTENTOS_LIBRES):
        anonimo.post("/sesion", json={"clave": "mala-mala-mala"})
    futuro = time.time() + seguridad.Freno.ESPERA_INICIAL + 1
    monkeypatch.setattr(seguridad.time, "time", lambda: futuro)
    assert anonimo.post("/sesion", json={"clave": CLAVE}).status_code == 204


def test_la_espera_se_duplica_y_tiene_tope():
    freno = seguridad.Freno()
    esperas = []
    for _ in range(seguridad.Freno.INTENTOS_LIBRES + 12):
        freno.anotar_fallo()
        esperas.append(freno.segundos_de_espera())
    assert esperas[:4] == [0, 0, 0, 0]
    assert esperas[4] == 30 and esperas[5] == 60 and esperas[6] == 120
    assert max(esperas) == seguridad.Freno.ESPERA_MAXIMA


# ---------- Pedidos disparados desde otros sitios ----------

def test_pedido_de_otro_sitio_se_rechaza(cliente, datos):
    respuesta = cliente.delete("/libros/libro-prueba", headers={"Origin": "https://sitio-malo.example"})
    assert respuesta.status_code == 403
    assert (datos / "libro-prueba").exists()

    respuesta = cliente.delete("/libros/libro-prueba", headers={"Sec-Fetch-Site": "cross-site"})
    assert respuesta.status_code == 403
    assert (datos / "libro-prueba").exists()


def test_pedido_del_mismo_sitio_pasa(cliente):
    respuesta = cliente.patch(
        "/libros/libro-prueba", json={"titulo": "Nuevo"}, headers={"Origin": "http://testserver"}
    )
    assert respuesta.status_code == 200


def test_pedido_del_mismo_sitio_detras_del_proxy_pasa(cliente):
    respuesta = cliente.patch(
        "/libros/libro-prueba",
        json={"titulo": "Nuevo"},
        headers={
            "Origin": "https://pc.ejemplo.ts.net",
            "Host": "localhost:8000",
            "X-Forwarded-Host": "pc.ejemplo.ts.net",
        },
    )
    assert respuesta.status_code == 200


def test_no_hay_permisos_para_otros_origenes(cliente):
    respuesta = cliente.get("/libros", headers={"Origin": "http://192.168.0.20:8000"})
    assert "access-control-allow-origin" not in respuesta.headers


# ---------- Cabeceras y archivos ----------

def test_cabeceras_de_seguridad(anonimo):
    for ruta in ("/", "/libros", "/sesion"):
        cabeceras = anonimo.get(ruta).headers
        assert "script-src 'self'" in cabeceras["content-security-policy"]
        assert "frame-ancestors 'none'" in cabeceras["content-security-policy"]
        assert cabeceras["x-content-type-options"] == "nosniff"
        assert cabeceras["x-frame-options"] == "DENY"
        assert cabeceras["referrer-policy"] == "no-referrer"


def test_la_api_no_queda_en_caches_compartidas(cliente):
    assert "private" in cliente.get("/libros").headers["cache-control"]


def test_cuerpo_demasiado_grande_se_rechaza_antes_de_leerlo(cliente):
    respuesta = cliente.post(
        "/libros", content=b"x", headers={"Content-Length": str(main.CUERPO_MAXIMO + 1)}
    )
    assert respuesta.status_code == 413


def test_portada_que_no_es_imagen_se_rechaza(cliente, datos):
    respuesta = cliente.put(
        "/libros/libro-prueba/portada",
        files={"archivo": ("tapa.png", b"<html><script>alert(1)</script></html>", "image/png")},
    )
    assert respuesta.status_code == 400
    assert not list((datos / "libro-prueba").glob("portada.*"))


def test_un_indice_manipulado_no_lee_fuera_del_libro(cliente, datos):
    (datos / "secreto.txt").write_text("no deberia leerse", encoding="utf-8")
    indice = datos / "libro-prueba" / "indice.json"
    contenido = json.loads(indice.read_text(encoding="utf-8"))
    contenido["capitulos"][0]["archivo"] = "../secreto.txt"
    contenido["portada"] = "../secreto.txt"
    indice.write_text(json.dumps(contenido), encoding="utf-8")

    assert cliente.get("/libros/libro-prueba/capitulos/1").status_code == 404
    assert cliente.get("/libros/libro-prueba/portada").status_code == 404


# ---------- Módulo de seguridad ----------

def test_la_clave_no_se_guarda_en_claro(datos):
    for archivo in seguridad.carpeta(datos).iterdir():
        assert CLAVE not in archivo.read_text(encoding="utf-8")


def test_el_token_no_se_guarda_en_claro(datos):
    token = seguridad.abrir_sesion(datos)
    assert token not in (seguridad.carpeta(datos) / "sesiones.json").read_text(encoding="utf-8")
    assert seguridad.sesion_valida(datos, token)


def test_clave_corta_se_rechaza(tmp_path):
    with pytest.raises(seguridad.ClaveInvalida):
        seguridad.guardar_clave(tmp_path, "corta")
    assert not seguridad.hay_clave(tmp_path)


def test_la_misma_clave_no_da_el_mismo_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(seguridad, "SCRYPT_N", 2 ** 4)
    seguridad.guardar_clave(tmp_path, CLAVE)
    primero = (seguridad.carpeta(tmp_path) / "clave.json").read_text(encoding="utf-8")
    seguridad.guardar_clave(tmp_path, CLAVE)
    assert primero != (seguridad.carpeta(tmp_path) / "clave.json").read_text(encoding="utf-8")


def test_se_limita_la_cantidad_de_sesiones(datos):
    tokens = [seguridad.abrir_sesion(datos) for _ in range(seguridad.SESIONES_MAXIMAS + 3)]
    assert not seguridad.sesion_valida(datos, tokens[0])
    assert seguridad.sesion_valida(datos, tokens[-1])


def test_la_carpeta_de_seguridad_no_es_un_libro(cliente):
    assert cliente.get("/libros/_seguridad").status_code == 404
    assert [libro["id"] for libro in cliente.get("/libros").json()] == ["libro-prueba"]
