"""
Genera el audio narrado de un capítulo con `edge-tts` y las marcas de tiempo
para que el lector pueda mostrar, igual que con la voz del sistema, qué
frase se está escuchando en cada momento.

Cómo se sincroniza el texto con el audio
-----------------------------------------
`edge-tts` puede devolver, además del audio, el instante exacto (en el
audio) en el que empieza y termina cada **oración** que detecta (modo
``SentenceBoundary``). Eso da una sincronía exacta, pero las oraciones de
una novela pueden ser mucho más largas que lo que entra en las tres líneas
que muestra el lector.

Por eso cada oración se vuelve a partir con `partir_en_trozos` (el mismo
criterio que ya usa `lector.js` con la voz del sistema: hasta 120
caracteres, cortando en el signo de puntuación de mayor prioridad) y su
ventana de tiempo se reparte entre esos trozos en proporción a los
caracteres de cada uno. Dentro de una oración la voz habla a ritmo
bastante constante, así que el reparto queda preciso; y como se vuelve a
anclar en cada oración, un trozo algo más largo o corto no arrastra el
error al resto del capítulo.
"""

import re
from pathlib import Path

import edge_tts

from backend import voces

# ---------------------------------------------------------------------------
# Partir en trozos cortos (mismo criterio que frontend/lector.js)
# ---------------------------------------------------------------------------

TROZOS_MAXIMOS = 120
PAUSAS_POR_PRIORIDAD = [re.compile(r"[.!?…]"), re.compile(r"[;:]"), re.compile(r",")]


def _ultima_pausa(texto: str, marca: re.Pattern) -> int:
    """Posición (después del signo) de la última pausa de ese tipo que entra en el límite."""
    mejor = -1
    hasta = min(len(texto), TROZOS_MAXIMOS)
    for i in range(hasta):
        es_final = (i + 1 == len(texto)) or texto[i + 1].isspace()
        if marca.match(texto[i]) and es_final:
            mejor = i + 1
    return mejor


def _ultimo_espacio(texto: str) -> int:
    """Último recurso: el último espacio que entra en el límite."""
    for i in range(min(len(texto) - 1, TROZOS_MAXIMOS), 0, -1):
        if texto[i].isspace():
            return i
    return min(len(texto), TROZOS_MAXIMOS)


def _cortar_en_pausas(texto: str) -> list[str]:
    trozos = []
    resto = texto.strip()
    while len(resto) > TROZOS_MAXIMOS:
        corte = -1
        for marca in PAUSAS_POR_PRIORIDAD:
            corte = _ultima_pausa(resto, marca)
            if corte > 0:
                break
        if corte <= 0:
            corte = _ultimo_espacio(resto)
        trozos.append(resto[:corte].strip())
        resto = resto[corte:].strip()
    if resto:
        trozos.append(resto)
    return trozos


def partir_en_trozos(texto: str) -> list[str]:
    """Cada salto de línea es una pausa fuerte; dentro de cada párrafo se aplica la prioridad."""
    trozos = []
    for parrafo in re.split(r"\n+", texto):
        parrafo = parrafo.strip()
        if parrafo:
            trozos.extend(_cortar_en_pausas(parrafo))
    return trozos


# ---------------------------------------------------------------------------
# Normalización de texto antes de mandarlo a la voz
# ---------------------------------------------------------------------------

# edge-tts ya descarta caracteres de control (frecuentes en PDF escaneado),
# pero no toca signos que la voz pronuncia mal o que no aportan nada hablados.
# Esta lista está pensada para crecer: si aparece otro caracter que la voz
# lee mal, el arreglo es agregar una línea aquí.
_REEMPLAZOS = [
    (re.compile(r"[—–]"), ", "),       # rayas de diálogo y guion medio -> pausa breve
    (re.compile(r"\.{3,}|…"), "."),    # puntos suspensivos -> un punto (pausa, no "punto punto punto")
    (re.compile(r"[*_#`]+"), ""),      # restos de formato (markdown, énfasis de EPUB)
    (re.compile(r"[ \t]+"), " "),      # espacios repetidos
]


def normalizar_para_voz(texto: str) -> str:
    resultado = texto
    for patron, reemplazo in _REEMPLAZOS:
        resultado = patron.sub(reemplazo, resultado)
    return resultado


# ---------------------------------------------------------------------------
# Generación con edge-tts
# ---------------------------------------------------------------------------

def _generar_oraciones(texto: str, voz_id: str, tono: dict) -> tuple[bytes, list[dict]]:
    """Una sola llamada a edge-tts por capítulo. Devuelve el audio y, por cada
    oración que detectó el servicio, su texto y su ventana de tiempo exacta
    (en segundos, dentro del audio devuelto)."""
    comunicar = edge_tts.Communicate(
        texto,
        voz_id,
        rate=tono["rate"],
        pitch=tono["pitch"],
        boundary="SentenceBoundary",
    )
    audio = bytearray()
    oraciones = []
    for fragmento in comunicar.stream_sync():
        if fragmento["type"] == "audio":
            audio.extend(fragmento["data"])
        elif fragmento["type"] == "SentenceBoundary":
            # offset/duration vienen en unidades de 100ns (igual que SubMaker de edge-tts).
            oraciones.append({
                "texto": fragmento["text"],
                "inicio": fragmento["offset"] / 10_000_000,
                "fin": (fragmento["offset"] + fragmento["duration"]) / 10_000_000,
            })
    if not audio:
        raise RuntimeError("El servicio de voz no devolvió audio para este capítulo.")
    return bytes(audio), oraciones


def _marcas_desde_oraciones(oraciones: list[dict]) -> list[dict]:
    marcas = []
    for oracion in oraciones:
        sub_trozos = partir_en_trozos(oracion["texto"]) or [oracion["texto"].strip()]
        total_caracteres = sum(len(t) for t in sub_trozos) or 1
        duracion = max(oracion["fin"] - oracion["inicio"], 0)
        cursor = oracion["inicio"]
        for trozo in sub_trozos:
            fin = cursor + duracion * (len(trozo) / total_caracteres)
            marcas.append({"texto": trozo, "inicio": round(cursor, 3), "fin": round(fin, 3)})
            cursor = fin
    return marcas


def generar_audio_capitulo(texto: str, voz_id: str, tono_id: str, destino_mp3: Path) -> list[dict]:
    """Genera el mp3 de un capítulo en `destino_mp3` y devuelve las marcas de
    tiempo por trozo (misma forma que usa el lector para la voz del sistema).
    Quien llama decide dónde cachear esto (ver `backend/main.py`)."""
    tono = voces.TONOS.get(tono_id, voces.TONOS[voces.TONO_PREDETERMINADO])
    texto_normalizado = normalizar_para_voz(texto)
    audio, oraciones = _generar_oraciones(texto_normalizado, voz_id, tono)
    destino_mp3.write_bytes(audio)
    return _marcas_desde_oraciones(oraciones)
