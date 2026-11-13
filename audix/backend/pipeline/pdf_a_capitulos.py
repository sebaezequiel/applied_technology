"""
Convierte un PDF en texto limpio, dividido por capítulos.

Uso desde la terminal:
    python pdf_a_capitulos.py libro.pdf
    python pdf_a_capitulos.py libro.pdf carpeta_salida --tipo novela
    python pdf_a_capitulos.py libro.pdf carpeta_salida --tipo apuntes

Tipos soportados: novela, cuento, poesia, apuntes
  - novela:  detecta capítulos por encabezados (CAPÍTULO N, romanos, números) o saltos de página.
  - cuento:  si hay encabezados los usa; si no, el texto completo es un solo capítulo.
  - poesia:  conserva los versos tal cual (no une líneas). Estrofas separadas por línea en blanco.
  - apuntes: divide por títulos. Títulos sin contenido debajo no forman capítulo.

Para cada PDF la función `detectar_origen` indica si tiene capa de texto o es escaneado.
El procesamiento de PDFs escaneados (OCR) queda pendiente.

Genera en la carpeta de salida:
    001.txt, 002.txt, ...  (un archivo por capítulo)
    indice.json            (título, autor y lista de capítulos)

La API usa las mismas funciones.
"""

import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None  # type: ignore

# --- Patrones de encabezados ---
# Capítulo en texto: "Capítulo I", "CAPÍTULO 3", "Cap. 2", etc.
_PATRON_CAPITULO = re.compile(
    r"^\s*(cap[íi]tulo\.?\s*\w+|cap\.\s*\w+)\s*$",
    re.IGNORECASE,
)
# Número romano solo (I, II, III, IV, ..., hasta XX)
_PATRON_ROMANO = re.compile(
    r"^\s*M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\s*$",
    re.IGNORECASE,
)
# Número arábigo solo (1, 2, 10...)
_PATRON_NUMERO = re.compile(r"^\s*\d{1,3}\s*$")

# Título numerado en apuntes: "1. Introducción", "2.3 Ejemplos", "3) Repaso"
_PATRON_TITULO_NUMERADO = re.compile(r"^\d{1,2}(\.\d{1,2})*[.)]?\s+[A-ZÁÉÍÓÚÑÜ]")

# Largo máximo de un título. Una línea más larga es casi seguro un párrafo.
_LARGO_MAXIMO_TITULO = 60


# ---------------------------------------------------------------------------
# Detección de origen
# ---------------------------------------------------------------------------

def detectar_origen(ruta: Path) -> str:
    """
    Devuelve 'texto' si el PDF tiene capa de texto en la mayoría de las páginas,
    o 'escaneado' si la mayoría de las páginas no tienen texto extraíble.
    Requiere pdfplumber.
    """
    if pdfplumber is None:
        raise RuntimeError("pdfplumber no está instalado. Ejecutá: pip install pdfplumber")
    total = 0
    con_texto = 0
    with pdfplumber.open(str(ruta)) as pdf:
        for pagina in pdf.pages:
            total += 1
            texto = pagina.extract_text() or ""
            if len(texto.strip()) > 20:
                con_texto += 1
    if total == 0:
        return "escaneado"
    return "texto" if (con_texto / total) >= 0.5 else "escaneado"


# ---------------------------------------------------------------------------
# Limpieza de texto
# ---------------------------------------------------------------------------

def _limpiar_prosa(lineas: list[str]) -> str:
    """Une líneas cortadas por el maquetado y reconstruye párrafos."""
    parrafos = []
    parrafo_actual = []

    for linea in lineas:
        linea_stripped = linea.strip()
        if not linea_stripped:
            if parrafo_actual:
                parrafos.append(" ".join(parrafo_actual))
                parrafo_actual = []
        else:
            # Si la línea anterior termina con guion, es una palabra cortada
            if parrafo_actual and parrafo_actual[-1].endswith("-"):
                parrafo_actual[-1] = parrafo_actual[-1][:-1] + linea_stripped
            else:
                parrafo_actual.append(linea_stripped)

    if parrafo_actual:
        parrafos.append(" ".join(parrafo_actual))

    return "\n\n".join(p for p in parrafos if p)


def _limpiar_poesia(lineas: list[str]) -> str:
    """Conserva los versos tal cual. Colapsa múltiples líneas en blanco a una."""
    resultado = []
    en_blanco = False
    for linea in lineas:
        if not linea.strip():
            if not en_blanco:
                resultado.append("")
                en_blanco = True
        else:
            resultado.append(linea.rstrip())
            en_blanco = False
    return "\n".join(resultado).strip()


# ---------------------------------------------------------------------------
# Filtros de líneas de cabecera/pie
# ---------------------------------------------------------------------------

def _encontrar_repetidas(paginas_lineas: list[list[str]], umbral: float = 0.6) -> set[str]:
    """
    Detecta líneas que aparecen en más del `umbral` de páginas (encabezados/pies repetidos).
    Solo considera líneas cortas (< 60 caracteres).
    """
    if not paginas_lineas:
        return set()
    from collections import Counter
    conteo: Counter = Counter()
    for lineas in paginas_lineas:
        vistas = set()
        for linea in lineas:
            limpia = linea.strip()
            if limpia and len(limpia) < 60:
                vistas.add(limpia)
        for linea in vistas:
            conteo[linea] += 1
    total_paginas = len(paginas_lineas)
    return {linea for linea, n in conteo.items() if n / total_paginas >= umbral}


# ---------------------------------------------------------------------------
# Detección de encabezados por tamaño de fuente (pdfplumber)
# ---------------------------------------------------------------------------

def _extraer_lineas_con_tamano(pagina) -> list[tuple[str, float]]:
    """
    Devuelve lista de (texto_linea, tamaño_fuente_promedio) para la página.
    Agrupa los chars por línea (mismo y≈).
    """
    words = pagina.extract_words(extra_attrs=["size"])
    if not words:
        return []

    # Agrupa por línea (tolerancia vertical de 3 pts)
    lineas: dict[float, list] = {}
    for word in words:
        y = round(word["top"] / 3) * 3
        if y not in lineas:
            lineas[y] = []
        lineas[y].append(word)

    resultado = []
    for y in sorted(lineas):
        palabras = sorted(lineas[y], key=lambda w: w["x0"])
        texto = " ".join(w["text"] for w in palabras)
        tamano = sum(w.get("size", 10) for w in palabras) / len(palabras)
        resultado.append((texto, tamano))
    return resultado


def _tamano_cuerpo(lineas_con_tamano: list[tuple[str, float]]) -> float:
    """Estima el tamaño de fuente del cuerpo de texto (moda)."""
    from collections import Counter
    tamanios = [round(t) for _, t in lineas_con_tamano if t > 0]
    if not tamanios:
        return 10.0
    return Counter(tamanios).most_common(1)[0][0]


# ---------------------------------------------------------------------------
# Divisor de capítulos
# ---------------------------------------------------------------------------

def _es_encabezado_novela(texto: str) -> bool:
    return bool(
        _PATRON_CAPITULO.match(texto)
        or _PATRON_ROMANO.match(texto)
        or _PATRON_NUMERO.match(texto)
    )


def _es_encabezado_apuntes(texto: str, tamano: float, tamano_cuerpo: float) -> bool:
    """
    Un título de apuntes es una línea corta que no parece parte de una oración:
    - Como máximo _LARGO_MAXIMO_TITULO caracteres
    - No termina en puntuación de oración (. , ; : ?)
    - Y además: letra más grande que el cuerpo, o toda en mayúsculas, o numerada ("2.1 Título")
    """
    t = texto.strip()
    if not t or len(t) > _LARGO_MAXIMO_TITULO or t[-1] in ".,;:?!¿":
        return False
    es_grande = tamano > tamano_cuerpo + 0.5
    es_mayuscula = t.isupper() and len(t) > 2
    es_numerado = bool(_PATRON_TITULO_NUMERADO.match(t))
    return es_grande or es_mayuscula or es_numerado


def _titulo_de_respaldo(lineas: list[str], numero: int) -> str:
    """
    Título para un capítulo sin encabezado. Usa la primera línea solo si es corta
    y no parece una oración; si no, usa "Capítulo N".
    """
    primera = next((linea.strip() for linea in lineas if linea.strip()), "")
    if primera and len(primera) <= _LARGO_MAXIMO_TITULO and primera[-1] not in ".,;:?!¿":
        return primera
    return f"Capítulo {numero}"


def _dividir_en_capitulos(
    paginas_lineas: list[list[str]],
    tipo: str,
    tamanos_por_pagina: list[list[tuple[str, float]]] | None = None,
) -> list[tuple[str, list[str]]]:
    """
    Recibe las líneas de cada página y devuelve lista de (titulo, lineas_del_capitulo).
    """
    repetidas = _encontrar_repetidas(paginas_lineas)

    # Aplana todo en una secuencia de (tipo_linea, texto, tamaño)
    lineas_globales: list[tuple[str, str, float]] = []  # tipo, texto, tamaño
    tamano_cuerpo_global = 10.0

    if tamanos_por_pagina:
        todos = [item for pagina in tamanos_por_pagina for item in pagina]
        tamano_cuerpo_global = _tamano_cuerpo(todos)

    for i, lineas_pag in enumerate(paginas_lineas):
        tamanos_pag = tamanos_por_pagina[i] if tamanos_por_pagina else []
        tamanos_dict = {t: s for t, s in tamanos_pag}

        for linea in lineas_pag:
            t = linea.strip()
            if not t or t in repetidas:
                continue
            tamano = tamanos_dict.get(t, tamano_cuerpo_global)

            if tipo in ("novela", "cuento") and _es_encabezado_novela(t):
                lineas_globales.append(("enc", t, tamano))
            elif tipo == "apuntes" and _es_encabezado_apuntes(t, tamano, tamano_cuerpo_global):
                lineas_globales.append(("enc", t, tamano))
            else:
                lineas_globales.append(("text", t, tamano))

        lineas_globales.append(("salto_pagina", "", 0.0))

    # Si no hay encabezados explícitos y es novela, usamos saltos de página
    n_encabezados = sum(1 for tipo_l, _, _ in lineas_globales if tipo_l == "enc")
    if tipo == "novela" and n_encabezados == 0:
        capitulos: list[tuple[str, list[str]]] = []
        bloque: list[str] = []
        num = 1
        for tipo_l, texto, _ in lineas_globales:
            if tipo_l == "salto_pagina":
                if bloque:
                    capitulos.append((f"Capítulo {num}", bloque))
                    num += 1
                    bloque = []
            else:
                bloque.append(texto)
        if bloque:
            capitulos.append((f"Capítulo {num}", bloque))
        return capitulos

    # Para cuento/poesia sin encabezados: todo es un capítulo
    if tipo in ("cuento", "poesia") and n_encabezados == 0:
        bloque = [t for tipo_l, t, _ in lineas_globales if tipo_l == "text"]
        return [("", bloque)]

    # Con encabezados: acumular texto bajo cada encabezado
    capitulos = []
    titulo_actual = ""
    bloque_actual: list[str] = []

    for tipo_l, texto, _ in lineas_globales:
        if tipo_l == "enc":
            if bloque_actual or titulo_actual:
                capitulos.append((titulo_actual, bloque_actual))
            titulo_actual = texto
            bloque_actual = []
        elif tipo_l == "text":
            bloque_actual.append(texto)
        # salto_pagina: se ignora cuando hay encabezados explícitos

    if bloque_actual or titulo_actual:
        capitulos.append((titulo_actual, bloque_actual))

    # Fusiona capítulos que solo tienen título y ningún texto
    # Un título sin texto debajo no es un capítulo: su texto pasa a ser la primera
    # línea del capítulo siguiente, que conserva su propio título.
    fusionados: list[tuple[str, list[str]]] = []
    pendientes: list[str] = []
    for titulo, lineas in capitulos:
        if not lineas:
            if titulo:
                pendientes.append(titulo)
            continue
        fusionados.append((titulo, pendientes + lineas))
        pendientes = []
    if pendientes and fusionados:
        titulo_ultimo, lineas_ultimo = fusionados[-1]
        fusionados[-1] = (titulo_ultimo, lineas_ultimo + pendientes)

    # Elimina capítulos que quedaron vacíos al final
    return [(t, l) for t, l in fusionados if l]


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def procesar_pdf(origen: Path, destino: Path, tipo: str = "novela") -> dict:
    """
    Extrae texto de un PDF con capa de texto y genera los archivos de salida.
    Devuelve el índice igual que `procesar_epub`.

    tipo: 'novela' | 'cuento' | 'poesia' | 'apuntes'
    """
    if pdfplumber is None:
        raise RuntimeError("pdfplumber no está instalado. Ejecutá: pip install pdfplumber")

    if tipo not in ("novela", "cuento", "poesia", "apuntes"):
        raise ValueError(f"Tipo desconocido: {tipo!r}. Usá: novela, cuento, poesia, apuntes")

    destino.mkdir(parents=True, exist_ok=True)

    paginas_lineas: list[list[str]] = []
    tamanos_por_pagina: list[list[tuple[str, float]]] = []
    titulo_pdf = origen.stem
    autor_pdf = ""

    with pdfplumber.open(str(origen)) as pdf:
        # Metadatos básicos
        meta = pdf.metadata or {}
        if meta.get("Title"):
            titulo_pdf = meta["Title"]
        if meta.get("Author"):
            autor_pdf = meta["Author"]

        for pagina in pdf.pages:
            lineas_tamano = _extraer_lineas_con_tamano(pagina)
            tamanos_por_pagina.append(lineas_tamano)
            paginas_lineas.append([t for t, _ in lineas_tamano])

    capitulos_raw = _dividir_en_capitulos(paginas_lineas, tipo, tamanos_por_pagina)

    capitulos = []
    for idx, (titulo, lineas) in enumerate(capitulos_raw, start=1):
        if tipo == "poesia":
            texto = _limpiar_poesia(lineas)
        else:
            texto = _limpiar_prosa(lineas)

        if not texto.strip():
            continue

        numero = len(capitulos) + 1
        archivo = f"{numero:03d}.txt"
        (destino / archivo).write_text(texto, encoding="utf-8")

        # Si el capítulo no tiene título, intenta tomarlo de la primera línea
        if not titulo:
            titulo = _titulo_de_respaldo(lineas, numero)

        capitulos.append({
            "numero": numero,
            "titulo": titulo or f"Capítulo {numero}",
            "archivo": archivo,
            "caracteres": len(texto),
        })

    indice = {
        "titulo": titulo_pdf,
        "autor": autor_pdf,
        "portada": None,
        "capitulos": capitulos,
    }
    (destino / "indice.json").write_text(
        json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return indice


def previsualizar_pdf(origen: Path, tipo: str = "novela") -> list[dict]:
    """
    Detecta los capítulos de un PDF sin escribir archivos en disco.
    Devuelve la lista de capítulos con titulo y caracteres estimados.
    Útil para la vista previa antes de confirmar la importación.
    """
    if pdfplumber is None:
        raise RuntimeError("pdfplumber no está instalado. Ejecutá: pip install pdfplumber")

    paginas_lineas: list[list[str]] = []
    tamanos_por_pagina: list[list[tuple[str, float]]] = []

    with pdfplumber.open(str(origen)) as pdf:
        for pagina in pdf.pages:
            lineas_tamano = _extraer_lineas_con_tamano(pagina)
            tamanos_por_pagina.append(lineas_tamano)
            paginas_lineas.append([t for t, _ in lineas_tamano])

    capitulos_raw = _dividir_en_capitulos(paginas_lineas, tipo, tamanos_por_pagina)

    resultado = []
    for idx, (titulo, lineas) in enumerate(capitulos_raw, start=1):
        if tipo == "poesia":
            texto = _limpiar_poesia(lineas)
        else:
            texto = _limpiar_prosa(lineas)
        if not texto.strip():
            continue
        if not titulo:
            titulo = _titulo_de_respaldo(lineas, len(resultado) + 1)
        resultado.append({"numero": len(resultado) + 1, "titulo": titulo, "caracteres": len(texto)})

    return resultado


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Convierte un PDF en texto por capítulos")
    parser.add_argument("origen", help="Ruta al archivo PDF")
    parser.add_argument("destino", nargs="?", help="Carpeta de salida (opcional)")
    parser.add_argument(
        "--tipo",
        choices=["novela", "cuento", "poesia", "apuntes"],
        default="novela",
        help="Tipo de documento (default: novela)",
    )
    args = parser.parse_args()

    origen = Path(args.origen)
    destino = Path(args.destino) if args.destino else origen.parent / origen.stem

    origen_tipo = detectar_origen(origen)
    if origen_tipo == "escaneado":
        print(f"Aviso: el PDF parece escaneado (sin capa de texto). El procesamiento por OCR no está disponible aún.")
        sys.exit(1)

    indice = procesar_pdf(origen, destino, tipo=args.tipo)

    total = sum(c["caracteres"] for c in indice["capitulos"])
    print(f"Libro: {indice['titulo']} ({indice['autor'] or 'autor desconocido'})")
    print(f"Capítulos extraídos: {len(indice['capitulos'])} | caracteres totales: {total:,}")
    print(f"Salida: {destino}")


if __name__ == "__main__":
    main()
