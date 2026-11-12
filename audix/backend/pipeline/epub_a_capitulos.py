"""
Convierte un EPUB en texto limpio, dividido por capítulos.

Uso:
    python epub_a_capitulos.py libro.epub
    python epub_a_capitulos.py libro.epub carpeta_salida

Genera en la carpeta de salida:
    001.txt, 002.txt, ...  (un archivo por capítulo)
    indice.json            (título, autor y lista de capítulos)
"""

import json
import re
import sys
from pathlib import Path

import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import ITEM_DOCUMENT, epub

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

BLOQUES = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "div"]


def limpiar(texto: str) -> str:
    texto = texto.replace("­", "")  # guiones invisibles de corte de línea
    # une palabras cortadas con guion al final de línea: "cor- tada" -> "cortada"
    texto = re.sub(r"(\w)-\s+([a-záéíóúñü])", r"\1\2", texto)
    texto = re.sub(r"[ \t\xa0]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n\n", texto)
    return texto.strip()


def extraer_capitulo(contenido: str):
    soup = BeautifulSoup(contenido, "lxml")
    for etiqueta in soup(["script", "style", "nav", "head"]):
        etiqueta.decompose()

    titulo = ""
    for etiqueta in ["h1", "h2", "h3"]:
        encabezado = soup.find(etiqueta)
        if encabezado and encabezado.get_text(strip=True):
            titulo = encabezado.get_text(" ", strip=True)
            break

    partes = []
    for bloque in soup.find_all(BLOQUES):
        if bloque.find(BLOQUES):  # solo tomamos bloques hoja, para no repetir texto
            continue
        texto = bloque.get_text(" ", strip=True)
        if texto:
            partes.append(texto)

    if not partes:  # plan B: texto suelto sin etiquetas de bloque
        partes = [soup.get_text(" ", strip=True)]

    return titulo, limpiar("\n\n".join(partes))


def metadato(libro, nombre: str) -> str:
    valores = libro.get_metadata("DC", nombre)
    return valores[0][0] if valores else ""


def main():
    if len(sys.argv) < 2:
        print("Uso: python epub_a_capitulos.py libro.epub [carpeta_salida]")
        sys.exit(1)

    origen = Path(sys.argv[1])
    destino = Path(sys.argv[2]) if len(sys.argv) > 2 else origen.parent / origen.stem

    libro = epub.read_epub(str(origen))
    documentos = {
        item.get_id(): item for item in libro.get_items_of_type(ITEM_DOCUMENT)
    }

    destino.mkdir(parents=True, exist_ok=True)
    capitulos = []

    for idref, _lineal in libro.spine:
        item = documentos.get(idref)
        if item is None:
            continue

        contenido = item.get_content().decode("utf-8", errors="replace")
        titulo, texto = extraer_capitulo(contenido)
        if not texto:
            continue

        numero = len(capitulos) + 1
        archivo = f"{numero:03d}.txt"
        (destino / archivo).write_text(texto, encoding="utf-8")

        capitulos.append({
            "numero": numero,
            "titulo": titulo or f"Capítulo {numero}",
            "archivo": archivo,
            "caracteres": len(texto),
        })

    indice = {
        "titulo": metadato(libro, "title") or origen.stem,
        "autor": metadato(libro, "creator"),
        "capitulos": capitulos,
    }
    (destino / "indice.json").write_text(
        json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = sum(c["caracteres"] for c in capitulos)
    print(f"Libro: {indice['titulo']} ({indice['autor'] or 'autor desconocido'})")
    print(f"Capítulos extraídos: {len(capitulos)} | caracteres totales: {total:,}")
    print(f"Salida: {destino}")


if __name__ == "__main__":
    main()
