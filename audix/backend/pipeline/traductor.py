"""
Traducción de libros entre español e inglés, 100 % en la PC (sin internet ni costo).

El motor es Argos Translate y es opcional: si no está instalado, el resto de
Audix funciona igual y la traducción avisa qué falta. Para instalarlo, ver
`requirements-traduccion.txt` y `python -m backend.pipeline.traductor --instalar`.

La traducción es literal (frase por frase, sin contexto del libro entero):
sirve para entender o probar, no reemplaza a una traducción profesional.

Guarda cada capítulo apenas termina. Si el servidor se reinicia a mitad de
camino, al retomar se saltea lo que ya estaba traducido.

Probar la calidad con un texto (sin tocar ningún libro):
    python -m backend.pipeline.traductor --probar en es "The old man walked slowly."
"""

import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Callable

RAIZ = Path(__file__).resolve().parents[2]
IDIOMAS = {"es": "español", "en": "inglés"}

MAX_TROZO = 600  # caracteres por pedido al motor; las frases largas se parten

PALABRAS_FRECUENTES = {
    "es": {
        "el", "la", "los", "las", "de", "del", "que", "y", "en", "un", "una", "es", "se",
        "no", "con", "por", "para", "su", "al", "lo", "como", "más", "pero", "sus", "le",
        "ya", "o", "este", "sí", "porque", "esta", "entre", "cuando", "muy", "sin", "sobre",
        "también", "me", "hasta", "hay", "donde", "quien", "desde", "todo", "nos", "durante",
    },
    "en": {
        "the", "of", "and", "to", "in", "a", "is", "that", "it", "was", "for", "on", "are",
        "as", "with", "his", "they", "be", "at", "one", "have", "this", "from", "or", "had",
        "by", "not", "but", "what", "all", "were", "we", "when", "your", "can", "said",
        "there", "use", "an", "each", "which", "she", "do", "how", "their", "if", "will",
        "he", "her", "him", "you", "my", "would", "been", "than", "then", "them",
    },
}


class TraduccionNoDisponible(Exception):
    """El motor o el modelo del par de idiomas no está instalado."""


class TraduccionCancelada(Exception):
    """Se pidió cancelar la traducción mientras corría."""


def detectar_idioma(texto: str) -> str | None:
    """Devuelve 'es' o 'en' contando palabras frecuentes, o None si no queda claro."""
    palabras = re.findall(r"[a-záéíóúñü]+", texto.lower())
    if len(palabras) < 30:
        return None
    cuenta = Counter(palabras)
    puntos = {
        idioma: sum(cuenta[p] for p in conjunto)
        for idioma, conjunto in PALABRAS_FRECUENTES.items()
    }
    mejor, otro = sorted(puntos, key=puntos.get, reverse=True)
    if puntos[mejor] < len(palabras) * 0.08:
        return None
    if puntos[mejor] < puntos[otro] * 1.3:
        return None
    return mejor


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

def carpeta_modelos() -> Path:
    """Dónde viven los modelos: dentro de la carpeta de datos de Audix."""
    return Path(os.environ.get("AUDIX_DATA_DIR") or RAIZ / "data") / "modelos-traduccion"


def _preparar_carpetas() -> None:
    """
    Argos guarda sus modelos en la carpeta del usuario de Windows que lo ejecuta. El
    servicio corre con otra cuenta que quien instala, así que no vería esos modelos.
    Por eso todo se guarda en una carpeta fija dentro de los datos de Audix, y esto
    tiene que correr antes de importar argostranslate.
    """
    base = carpeta_modelos()
    base.mkdir(parents=True, exist_ok=True)
    os.environ["ARGOS_PACKAGES_DIR"] = str(base / "paquetes")
    os.environ["XDG_DATA_HOME"] = str(base / "datos")
    os.environ["XDG_CACHE_HOME"] = str(base / "cache")
    if sys.platform == "win32":
        os.environ["LOCALAPPDATA"] = str(base / "cache")  # donde MiniSBD guarda su modelo


def obtener_traductor(origen: str, destino: str) -> Callable[[str], str]:
    """Devuelve una función texto -> texto traducido, o levanta TraduccionNoDisponible."""
    _preparar_carpetas()
    try:
        from argostranslate import translate
    except ImportError as error:
        raise TraduccionNoDisponible(
            "Falta instalar el motor de traducción. Seguí los pasos de la guía "
            "(requirements-traduccion.txt)."
        ) from error

    traduccion = translate.get_translation_from_codes(origen, destino)
    if traduccion is None:
        raise TraduccionNoDisponible(
            f"Falta el modelo {IDIOMAS.get(origen, origen)} → {IDIOMAS.get(destino, destino)}. "
            "Ejecutá: python -m backend.pipeline.traductor --instalar"
        )
    return traduccion.translate


def instalar_modelos() -> None:
    """Descarga e instala los modelos es→en y en→es (una sola vez, necesita internet)."""
    _preparar_carpetas()
    from argostranslate import package

    package.update_package_index()
    disponibles = package.get_available_packages()
    for origen, destino in (("en", "es"), ("es", "en")):
        paquete = next(
            (p for p in disponibles if p.from_code == origen and p.to_code == destino), None
        )
        if paquete is None:
            print(f"No se encontró el modelo {origen} -> {destino}")
            continue
        print(f"Instalando {origen} -> {destino}...")
        package.install_from_path(paquete.download())

    # Una traducción de prueba descarga lo que falta (separador de oraciones) ahora,
    # con internet y a la vista, y no en medio del primer libro.
    for origen, destino in (("en", "es"), ("es", "en")):
        try:
            muestra = "Hello. How are you?" if origen == "en" else "Hola. ¿Cómo estás?"
            print(f"Prueba {origen} -> {destino}: {obtener_traductor(origen, destino)(muestra)}")
        except TraduccionNoDisponible as error:
            print(error)
    print(f"Listo. Los modelos quedaron en {carpeta_modelos()}")


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

def _partir_linea(linea: str, maximo: int = MAX_TROZO) -> list[str]:
    """Parte una línea larga en trozos de hasta `maximo`, cortando entre oraciones."""
    if len(linea) <= maximo:
        return [linea]
    oraciones = re.split(r"(?<=[.!?…])\s+", linea)
    trozos, actual = [], ""
    for oracion in oraciones:
        while len(oracion) > maximo:  # oración sin puntos: se corta en un espacio
            corte = oracion.rfind(" ", 0, maximo)
            corte = corte if corte > 0 else maximo
            if actual:
                trozos.append(actual)
                actual = ""
            trozos.append(oracion[:corte])
            oracion = oracion[corte:].lstrip()
        if actual and len(actual) + 1 + len(oracion) > maximo:
            trozos.append(actual)
            actual = oracion
        else:
            actual = f"{actual} {oracion}".strip()
    if actual:
        trozos.append(actual)
    return trozos


def traducir_texto(
    texto: str,
    traducir: Callable[[str], str],
    avance: Callable[[int], None] | None = None,
) -> str:
    """
    Traduce conservando párrafos y saltos de línea (los versos de una poesía no se unen).
    `avance` recibe la cantidad de caracteres originales ya procesados; si levanta
    una excepción, la traducción se interrumpe (así se cancela).
    """
    lineas_traducidas = []
    for linea in texto.split("\n"):
        if not linea.strip():
            lineas_traducidas.append("")
            continue
        partes = [traducir(trozo).strip() for trozo in _partir_linea(linea.strip())]
        lineas_traducidas.append(" ".join(p for p in partes if p))
        if avance:
            avance(len(linea) + 1)
    return "\n".join(lineas_traducidas)


# ---------------------------------------------------------------------------
# Libro completo
# ---------------------------------------------------------------------------

def _escribir_json(ruta: Path, datos: dict) -> None:
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporal, ruta)


def traducir_libro(
    carpeta_origen: Path,
    carpeta_trabajo: Path,
    origen: str,
    destino: str,
    traducir: Callable[[str], str],
    progreso: Callable[[int], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
    libro_origen_id: str = "",
) -> dict:
    """
    Traduce el libro de `carpeta_origen` dentro de `carpeta_trabajo` y deja ahí el
    nuevo índice en `indice.pendiente.json` (quien llama lo publica como `indice.json`
    al mover la carpeta, para que el libro no aparezca en la biblioteca a medias).

    Si `carpeta_trabajo` ya tiene capítulos traducidos de un intento anterior, los reutiliza.
    """
    indice = json.loads((carpeta_origen / "indice.json").read_text(encoding="utf-8"))
    capitulos = indice.get("capitulos", [])
    carpeta_trabajo.mkdir(parents=True, exist_ok=True)

    estado_ruta = carpeta_trabajo / "estado.json"
    estado = {"origen": libro_origen_id, "de": origen, "a": destino, "hechos": {}}
    if estado_ruta.exists():
        estado = json.loads(estado_ruta.read_text(encoding="utf-8"))
    else:
        _escribir_json(estado_ruta, estado)
    hechos: dict = estado["hechos"]  # número de capítulo -> {"titulo", "caracteres"}

    total = sum(c.get("caracteres", 0) for c in capitulos) or 1
    procesados = sum(
        c.get("caracteres", 0) for c in capitulos if str(c["numero"]) in hechos
    )

    def avisar() -> None:
        if progreso:
            progreso(min(99, int(procesados * 100 / total)))

    def revisar_cancelacion() -> None:
        if cancelado and cancelado():
            raise TraduccionCancelada()

    avisar()
    nuevos = []
    for capitulo in capitulos:
        clave = str(capitulo["numero"])
        archivo_nuevo = carpeta_trabajo / capitulo["archivo"]

        if clave not in hechos or not archivo_nuevo.exists():
            revisar_cancelacion()
            texto = (carpeta_origen / capitulo["archivo"]).read_text(encoding="utf-8")

            def avance(caracteres: int) -> None:
                nonlocal procesados
                procesados += caracteres
                revisar_cancelacion()
                avisar()

            antes = procesados
            traducido = traducir_texto(texto, traducir, avance)
            procesados = antes + capitulo.get("caracteres", len(texto))  # corrige redondeos
            titulo = capitulo.get("titulo", "")
            titulo_nuevo = traducir_texto(titulo, traducir) if titulo else ""

            temporal = archivo_nuevo.with_name(archivo_nuevo.name + ".tmp")
            temporal.write_text(traducido, encoding="utf-8")
            os.replace(temporal, archivo_nuevo)
            hechos[clave] = {"titulo": titulo_nuevo, "caracteres": len(traducido)}
            _escribir_json(estado_ruta, estado)
            avisar()

        nuevos.append({
            "numero": capitulo["numero"],
            "titulo": hechos[clave]["titulo"],
            "archivo": capitulo["archivo"],
            "caracteres": hechos[clave]["caracteres"],
        })

    portada = indice.get("portada")
    if portada and (carpeta_origen / portada).exists():
        shutil.copy(carpeta_origen / portada, carpeta_trabajo / portada)

    nuevo_indice = {
        "titulo": f"{indice.get('titulo', 'Libro')} ({destino.upper()})",
        "autor": indice.get("autor", ""),
        "portada": portada if portada and (carpeta_trabajo / portada).exists() else None,
        "idioma": destino,
        "traducido_de": {"libro": libro_origen_id, "idioma": origen},
        "capitulos": nuevos,
    }
    _escribir_json(carpeta_trabajo / "indice.pendiente.json", nuevo_indice)
    return nuevo_indice


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "--instalar":
        instalar_modelos()
    elif len(sys.argv) >= 5 and sys.argv[1] == "--probar":
        _, _, origen, destino, *palabras = sys.argv
        try:
            traducir = obtener_traductor(origen, destino)
        except TraduccionNoDisponible as error:
            print(error)
            sys.exit(1)
        print(traducir_texto(" ".join(palabras), traducir))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
