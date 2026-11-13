"""
OCR para PDFs escaneados, incluidos los de doble página.

Un escaneo de doble página es una hoja apaisada con dos páginas del libro.
Se parte en dos mitades (izquierda, después derecha) antes del OCR, así las
dos columnas de páginas no se mezclan línea por línea.

Requiere:
    pymupdf      para renderizar las páginas (no necesita Poppler)
    pytesseract  y el ejecutable de Tesseract, con el idioma español instalado
Si Tesseract no está en el PATH, se puede indicar con la variable de entorno
TESSERACT_CMD (por ejemplo, la ruta a tesseract.exe en Windows).
"""

import os
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

# Resolución de render para el OCR. 300 dpi es un buen equilibrio entre calidad y tiempo.
DPI_OCR = 300
# Proporción ancho/alto a partir de la cual una página se trata como doble página.
PROPORCION_DOBLE = 1.2
# Margen de búsqueda del lomo, como fracción del ancho, a cada lado del centro.
BUSQUEDA_LOMO = 0.05
# Recorte de bordes de cada mitad (fracción), para quitar marcas del escáner y espiral.
RECORTE_BORDES = 0.02
# Umbral para considerar que un píxel es tinta (0-255 en escala de grises).
UMBRAL_TINTA = 128

LENGUAJE = "spa"

if os.environ.get("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]


def es_doble_pagina(ancho: int, alto: int) -> bool:
    """Una página apaisada se considera doble página."""
    return alto > 0 and (ancho / alto) >= PROPORCION_DOBLE


def encontrar_lomo(imagen_gris: Image.Image) -> int:
    """
    Devuelve la coordenada x del lomo: la columna con menos tinta dentro de la
    franja central. Si la página izquierda está en blanco, el valle puede ser
    ancho, por eso se usa el centro como punto de partida.
    """
    ancho, _ = imagen_gris.size
    centro = ancho // 2
    desde = int(ancho * (0.5 - BUSQUEDA_LOMO))
    hasta = int(ancho * (0.5 + BUSQUEDA_LOMO))

    pixeles = imagen_gris.load()
    alto = imagen_gris.size[1]

    def tinta_columna(x: int) -> int:
        return sum(1 for y in range(0, alto, 4) if pixeles[x, y] < UMBRAL_TINTA)

    mejor_x, mejor_tinta = centro, tinta_columna(centro)
    # Paso de 4 px para que la búsqueda sea rápida en imágenes grandes
    for x in range(desde, hasta, 4):
        tinta = tinta_columna(x)
        if tinta < mejor_tinta:
            mejor_x, mejor_tinta = x, tinta
    return mejor_x


def dividir_doble_pagina(imagen: Image.Image) -> list[Image.Image]:
    """Parte una hoja apaisada en dos mitades, en orden de lectura (izquierda, derecha)."""
    gris = imagen.convert("L")
    ancho, alto = gris.size
    lomo = encontrar_lomo(gris)

    margen_x = int(ancho * RECORTE_BORDES)
    margen_y = int(alto * RECORTE_BORDES)

    izquierda = imagen.crop((margen_x, margen_y, lomo, alto - margen_y))
    derecha = imagen.crop((lomo, margen_y, ancho - margen_x, alto - margen_y))
    return [izquierda, derecha]


def ocr_imagen(imagen: Image.Image) -> str:
    """Texto de una imagen, con Tesseract en español. Página de texto en un bloque variable."""
    return pytesseract.image_to_string(imagen, lang=LENGUAJE, config="--psm 4").strip()


def paginas_del_pdf(ruta: Path):
    """
    Renderiza cada página del PDF y devuelve las imágenes listas para OCR.
    Una página de doble ancho se devuelve como dos imágenes, en orden de lectura.
    """
    documento = pymupdf.open(str(ruta))
    try:
        for pagina in documento:
            escala = DPI_OCR / 72
            pix = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), colorspace=pymupdf.csGRAY)
            imagen = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            if es_doble_pagina(imagen.width, imagen.height):
                yield from dividir_doble_pagina(imagen)
            else:
                yield imagen
    finally:
        documento.close()


def es_ruido_ocr(linea: str) -> bool:
    """
    Descarta líneas que el OCR produce a partir de marcas del escáner o del espiral:
    muy cortas, o con pocas letras en relación con su largo.
    """
    letras = sum(1 for c in linea if c.isalpha())
    return letras < 3 or letras / max(len(linea), 1) < 0.5


def extraer_lineas_escaneado(ruta: Path) -> list[list[str]]:
    """
    Hace OCR de todo el PDF y devuelve una lista de páginas, cada una con sus líneas.
    Las mitades sin texto (páginas en blanco) se descartan.
    """
    paginas: list[list[str]] = []
    for imagen in paginas_del_pdf(ruta):
        texto = ocr_imagen(imagen)
        lineas = [linea.strip() if not es_ruido_ocr(linea.strip()) else "" for linea in texto.splitlines()]
        if any(lineas):
            paginas.append(lineas)
    return paginas
