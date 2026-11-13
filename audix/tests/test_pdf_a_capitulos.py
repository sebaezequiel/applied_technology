"""
Tests del pipeline pdf_a_capitulos.

Los tests crean PDFs mínimos con pdfplumber/reportlab o trabajan directamente
con las funciones internas (sin necesidad de un archivo PDF real).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "pipeline"))

from pdf_a_capitulos import (  # noqa: E402
    _clave_repetida,
    _dividir_en_capitulos,
    _encontrar_repetidas,
    _es_encabezado_novela,
    _limpiar_poesia,
    _limpiar_prosa,
)


# ---------------------------------------------------------------------------
# _limpiar_prosa
# ---------------------------------------------------------------------------

def test_limpiar_prosa_une_lineas():
    lineas = ["Primera línea", "segunda línea", "", "Nuevo párrafo."]
    resultado = _limpiar_prosa(lineas)
    assert "Primera línea segunda línea" in resultado
    assert "Nuevo párrafo." in resultado


def test_limpiar_prosa_une_palabra_cortada_con_guion():
    lineas = ["Estaba muy can-", "sado de leer."]
    resultado = _limpiar_prosa(lineas)
    assert "cansado" in resultado


def test_limpiar_prosa_separa_parrafos():
    lineas = ["Párrafo uno.", "", "Párrafo dos."]
    resultado = _limpiar_prosa(lineas)
    assert resultado == "Párrafo uno.\n\nPárrafo dos."


def test_limpiar_prosa_vacio():
    assert _limpiar_prosa([]) == ""
    assert _limpiar_prosa(["", "", ""]) == ""


# ---------------------------------------------------------------------------
# _limpiar_poesia
# ---------------------------------------------------------------------------

def test_limpiar_poesia_conserva_versos():
    lineas = ["Verso uno", "verso dos", "", "verso tres"]
    resultado = _limpiar_poesia(lineas)
    assert resultado == "Verso uno\nverso dos\n\nverso tres"


def test_limpiar_poesia_no_une_lineas():
    lineas = ["Primera", "segunda"]
    resultado = _limpiar_poesia(lineas)
    # Las líneas NO deben unirse
    assert "Primera\nsegunda" in resultado
    assert "Primera segunda" not in resultado


def test_limpiar_poesia_colapsa_blancos_multiples():
    lineas = ["Verso", "", "", "Estrofa dos"]
    resultado = _limpiar_poesia(lineas)
    # Solo una línea en blanco entre estrofas
    assert "\n\n\n" not in resultado


# ---------------------------------------------------------------------------
# _es_encabezado_novela
# ---------------------------------------------------------------------------

def test_detecta_capitulo_explicito():
    assert _es_encabezado_novela("Capítulo I")
    assert _es_encabezado_novela("CAPÍTULO 3")
    assert _es_encabezado_novela("Cap. 2")


def test_detecta_romano():
    assert _es_encabezado_novela("I")
    assert _es_encabezado_novela("IV")
    assert _es_encabezado_novela("XII")
    assert _es_encabezado_novela("XX")


def test_detecta_numero_arabigo():
    assert _es_encabezado_novela("1")
    assert _es_encabezado_novela("12")


def test_no_detecta_texto_normal():
    assert not _es_encabezado_novela("Estaba sentado junto a la ventana")
    assert not _es_encabezado_novela("—Me alegra que hayas venido")


# ---------------------------------------------------------------------------
# _encontrar_repetidas
# ---------------------------------------------------------------------------

def test_encuentra_lineas_repetidas():
    paginas = [
        ["Título del libro", "Texto de la página uno."],
        ["Título del libro", "Texto de la página dos."],
        ["Título del libro", "Texto de la página tres."],
    ]
    repetidas = _encontrar_repetidas(paginas, umbral=0.6)
    assert _clave_repetida("Título del libro") in repetidas
    assert "Texto de la página uno." not in repetidas


def test_no_marca_texto_largo_como_repetido():
    linea_larga = "Esta es una línea muy larga que supera los sesenta caracteres y no debería marcarse."
    paginas = [[linea_larga], [linea_larga], [linea_larga]]
    repetidas = _encontrar_repetidas(paginas)
    assert linea_larga not in repetidas


def test_sin_paginas():
    assert _encontrar_repetidas([]) == set()


# ---------------------------------------------------------------------------
# _dividir_en_capitulos
# ---------------------------------------------------------------------------

def test_novela_con_encabezados_romanos():
    paginas = [
        ["I", "Texto del primer capítulo."],
        ["II", "Texto del segundo capítulo."],
    ]
    caps = _dividir_en_capitulos(paginas, "novela")
    assert len(caps) == 2
    assert caps[0][0] == "I"
    assert caps[1][0] == "II"


def test_novela_sin_encabezados_usa_salto_de_pagina():
    paginas = [
        ["Texto de la primera página."],
        ["Texto de la segunda página."],
    ]
    caps = _dividir_en_capitulos(paginas, "novela")
    assert len(caps) == 2


def test_cuento_sin_encabezados_es_un_solo_capitulo():
    paginas = [
        ["Había una vez un lobo."],
        ["Y vivió feliz para siempre."],
    ]
    caps = _dividir_en_capitulos(paginas, "cuento")
    assert len(caps) == 1


def test_poesia_sin_encabezados_es_un_solo_capitulo():
    paginas = [
        ["Verso uno", "verso dos"],
        ["verso tres", "verso cuatro"],
    ]
    caps = _dividir_en_capitulos(paginas, "poesia")
    assert len(caps) == 1


def test_descarta_lineas_repetidas_en_capitulos():
    paginas = [
        ["Encabezado de página", "I", "Texto del capítulo uno."],
        ["Encabezado de página", "II", "Texto del capítulo dos."],
        ["Encabezado de página", "III", "Texto del capítulo tres."],
    ]
    caps = _dividir_en_capitulos(paginas, "novela")
    # El encabezado repetido no debe aparecer en el contenido
    for _, lineas in caps:
        assert "Encabezado de página" not in lineas


def test_fusiona_capitulo_sin_texto():
    # Si un encabezado no tiene texto debajo, se fusiona con el siguiente
    paginas = [
        ["I"],          # sin texto
        ["II", "Aquí empieza el texto."],
    ]
    caps = _dividir_en_capitulos(paginas, "novela")
    # Debería haber un solo capítulo con ambos títulos fusionados
    assert len(caps) == 1


# ---------------------------------------------------------------------------
# Títulos: solo encabezados reales, nunca párrafos
# ---------------------------------------------------------------------------

from pdf_a_capitulos import _es_encabezado_apuntes, _titulo_de_respaldo  # noqa: E402


def test_apuntes_no_toma_oracion_en_mayusculas_como_titulo():
    texto = "¿POR QUÉ TRIUNFÓ LA ESCUELA? o la modernidad dijo: Esto es educación y la escuela respondió"
    assert not _es_encabezado_apuntes(texto, 10, 10)


def test_apuntes_no_toma_oracion_normal_como_titulo():
    texto = "Dada la situación de la mayor parte de nuestras escuelas elementales"
    assert not _es_encabezado_apuntes(texto, 10, 10)


def test_apuntes_reconoce_titulo_numerado_y_mayusculas_cortas():
    assert _es_encabezado_apuntes("2.1 Ejemplos de uso", 10, 10)
    assert _es_encabezado_apuntes("INTRODUCCIÓN", 10, 10)


def test_apuntes_no_toma_titulo_largo_aunque_sea_numerado():
    texto = "1. " + "palabra " * 20
    assert not _es_encabezado_apuntes(texto, 10, 10)


def test_titulo_de_respaldo_usa_primera_linea_corta():
    assert _titulo_de_respaldo(["LOS PERROS DE TÍNDALOS", "texto"], 1) == "LOS PERROS DE TÍNDALOS"


def test_titulo_de_respaldo_no_usa_oracion():
    lineas = ["Dada la situación de la mayor parte de nuestras escuelas elementales."]
    assert _titulo_de_respaldo(lineas, 3) == "Capítulo 3"


def test_titulo_sin_texto_pasa_al_texto_del_siguiente():
    paginas = [
        ["I"],
        ["II", "Aquí empieza el texto."],
    ]
    caps = _dividir_en_capitulos(paginas, "novela")
    assert len(caps) == 1
    assert caps[0][0] == "II"
    assert caps[0][1][0] == "I"  # el título sin texto queda como línea, no se pierde


def test_encabezado_con_numero_de_pagina_cambiante_se_detecta_como_repetido():
    paginas = [
        ["10 SILVIA GRINBERG, ESTHER LEVY", "Texto uno."],
        ["12 SILVIA GRINBERG, ESTHER LEVY", "Texto dos."],
        ["14 SILVIA GRINBERG, ESTHER LEVY", "Texto tres."],
    ]
    repetidas = _encontrar_repetidas(paginas)
    assert _clave_repetida("16 SILVIA GRINBERG, ESTHER LEVY") in repetidas
