import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.pipeline import audio_narrado as an  # noqa: E402


def test_normaliza_rayas_y_puntos_suspensivos():
    texto = "Era de noche—muy tarde ya… demasiado tarde."
    normalizado = an.normalizar_para_voz(texto)
    assert "—" not in normalizado
    assert "…" not in normalizado
    assert normalizado == "Era de noche, muy tarde ya. demasiado tarde."


def test_normaliza_restos_de_formato():
    assert an.normalizar_para_voz("Un *énfasis* y un #encabezado#") == "Un énfasis y un encabezado"


def test_partir_en_trozos_respeta_el_limite():
    texto = (
        "El viento aullaba sin parar, sin tregua, sin piedad alguna, mientras las "
        "ventanas temblaban como si algo oscuro y antiguo quisiera entrar a toda "
        "costa en la casa abandonada."
    )
    trozos = an.partir_en_trozos(texto)
    assert len(trozos) > 1
    for trozo in trozos:
        assert len(trozo) <= an.TROZOS_MAXIMOS or " " not in trozo.strip()
    # Ningún trozo se come texto: unidos (con un espacio) reconstruyen el original.
    assert " ".join(trozos) == texto


def test_partir_en_trozos_corta_en_el_signo_de_mayor_prioridad():
    texto = "Uno, dos, tres: cuatro. Cinco."
    trozos = an.partir_en_trozos(texto)
    # Con el texto corto no hace falta cortar nada.
    assert trozos == [texto]


def test_partir_en_trozos_separa_parrafos():
    trozos = an.partir_en_trozos("Primer párrafo.\n\nSegundo párrafo.")
    assert trozos == ["Primer párrafo.", "Segundo párrafo."]


def test_marcas_desde_oraciones_reparte_el_tiempo_proporcionalmente():
    oracion_larga = (
        "El viento aullaba sin parar, sin tregua, sin piedad alguna, mientras las "
        "ventanas temblaban como si algo oscuro y antiguo quisiera entrar a toda "
        "costa en la casa abandonada."
    )
    marcas = an._marcas_desde_oraciones([{"texto": oracion_larga, "inicio": 10.0, "fin": 20.0}])
    assert len(marcas) > 1
    assert marcas[0]["inicio"] == 10.0
    assert marcas[-1]["fin"] == 20.0
    # Cada trozo empieza donde termina el anterior: no hay huecos ni superposición.
    for anterior, siguiente in zip(marcas, marcas[1:]):
        assert anterior["fin"] == siguiente["inicio"]


def test_marcas_desde_oraciones_oracion_corta_no_se_subdivide():
    marcas = an._marcas_desde_oraciones([{"texto": "Hola.", "inicio": 0.0, "fin": 1.0}])
    assert marcas == [{"texto": "Hola.", "inicio": 0.0, "fin": 1.0}]
