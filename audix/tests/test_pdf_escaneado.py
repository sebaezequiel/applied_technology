"""
Tests del pipeline de PDFs escaneados.

Los tests de división de doble página usan imágenes sintéticas, así que no
necesitan Tesseract. El test de OCR completo se omite si Tesseract no está.
"""

import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.pipeline import pdf_escaneado as pe  # noqa: E402
from backend.pipeline.pdf_a_capitulos import detectar_origen  # noqa: E402


def pagina_sintetica(ancho: int, alto: int, lomo: int) -> Image.Image:
    """Hoja blanca con bloques de 'texto' a ambos lados del lomo."""
    imagen = Image.new("L", (ancho, alto), 255)
    dibujo = ImageDraw.Draw(imagen)
    for y in range(200, alto - 200, 40):
        dibujo.rectangle([lomo - 500, y, lomo - 60, y + 15], fill=0)
        dibujo.rectangle([lomo + 60, y, lomo + 500, y + 15], fill=0)
    return imagen


def test_doble_pagina_por_proporcion():
    assert pe.es_doble_pagina(3300, 2550)      # apaisada, doble página
    assert not pe.es_doble_pagina(2550, 3300)  # vertical, página simple
    assert not pe.es_doble_pagina(0, 0)


def test_encuentra_el_lomo_donde_esta_el_valle_de_tinta():
    ancho, alto = 1600, 1200
    lomo = 780  # cerca del centro (800)
    imagen = pagina_sintetica(ancho, alto, lomo)
    x = pe.encontrar_lomo(imagen)
    assert abs(x - lomo) <= 20


def test_dividir_doble_pagina_devuelve_izquierda_y_derecha_en_orden():
    ancho, alto = 1600, 1200
    imagen = pagina_sintetica(ancho, alto, 800).convert("RGB")
    izquierda, derecha = pe.dividir_doble_pagina(imagen)
    # Las dos mitades suman aproximadamente el ancho original, sin el borde
    assert izquierda.width > 600 and derecha.width > 600
    assert izquierda.width + derecha.width < ancho
    # La izquierda termina donde empieza la derecha (el lomo queda entre ambas)
    assert izquierda.height == alto - 2 * int(alto * pe.RECORTE_BORDES)


def test_detectar_origen_reconoce_escaneado_sin_capa_de_texto(tmp_path):
    import pymupdf

    imagen = pagina_sintetica(1650, 1275, 825).convert("RGB")
    ruta_png = tmp_path / "pagina.png"
    imagen.save(ruta_png)
    documento = pymupdf.open()
    pagina = documento.new_page(width=792, height=612)
    pagina.insert_image(pagina.rect, filename=str(ruta_png))
    ruta_pdf = tmp_path / "escaneado.pdf"
    documento.save(str(ruta_pdf))
    documento.close()

    assert detectar_origen(ruta_pdf) == "escaneado"


def test_ocr_de_pagina_simple_si_hay_tesseract():
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
    except Exception:
        pytest.skip("Tesseract no está disponible en este entorno")

    imagen = Image.new("L", (1200, 300), 255)
    dibujo = ImageDraw.Draw(imagen)
    dibujo.text((40, 100), "Hola escuela", fill=0)
    texto = pe.ocr_imagen(imagen)
    assert "Hola" in texto
