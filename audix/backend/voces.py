"""
Catálogo de voces e identidades para la narración con IA (motor `edge-tts`)
y los tonos de lectura que se pueden aplicar.

Lo que se guarda por libro es solo el id de la voz y el nombre del tono
(ver `indice.json`, clave "voz"); este módulo traduce esos ids a los
parámetros que entiende `edge-tts` y a nombres que puede ver la persona.
"""

MOTORES = {"sistema", "narracion"}

# Nombre amigable por voz. El id es el que usa el servicio de Microsoft.
VOCES_NARRACION = {
    "es-AR-TomasNeural": "Tomás (Argentina, masculino)",
    "es-AR-ElenaNeural": "Elena (Argentina, femenino)",
    "es-ES-AlvaroNeural": "Álvaro (España, masculino)",
    "es-ES-ElviraNeural": "Elvira (España, femenino)",
    "es-MX-JorgeNeural": "Jorge (México, masculino)",
    "es-MX-DaliaNeural": "Dalia (México, femenino)",
    # Inglés: voces de narración (categorías "Novel" y "News" de edge-tts).
    "en-US-AriaNeural": "Aria (Estados Unidos, femenina)",
    "en-US-GuyNeural": "Guy (Estados Unidos, masculino)",
    "en-GB-SoniaNeural": "Sonia (Reino Unido, femenina)",
    "en-GB-RyanNeural": "Ryan (Reino Unido, masculino)",
}

# Idioma de cada voz según su id (el prefijo "es-AR", "en-US", etc.), para agrupar en la PWA.
NOMBRES_DE_IDIOMA = {"es": "Español", "en": "Inglés"}

VOZ_NARRACION_PREDETERMINADA = "es-AR-TomasNeural"

# Cada tono ajusta el tono (pitch) y la velocidad base de la voz.
# "oscuro" y "grave" bajan el tono para libros de terror, thriller o dark
# fantasy, donde la alegría de la voz por defecto no pega con el texto.
TONOS = {
    "normal": {"pitch": "+0Hz", "rate": "+0%", "nombre": "Normal"},
    "oscuro": {"pitch": "-15Hz", "rate": "-4%", "nombre": "Oscuro"},
    "grave": {"pitch": "-30Hz", "rate": "-8%", "nombre": "Grave"},
}

TONO_PREDETERMINADO = "normal"


def configuracion_por_defecto() -> dict:
    """La que tienen (implícitamente) los libros importados antes de esta función."""
    return {"motor": "sistema", "voz_id": None, "tono": TONO_PREDETERMINADO}


def validar(motor: str, voz_id: str | None, tono: str) -> dict:
    """Valida una configuración de voz y devuelve la versión normalizada a guardar."""
    if motor not in MOTORES:
        raise ValueError(f"Motor inválido. Usá: {', '.join(sorted(MOTORES))}")
    if tono not in TONOS:
        raise ValueError(f"Tono inválido. Usá: {', '.join(sorted(TONOS))}")

    if motor == "sistema":
        return {"motor": "sistema", "voz_id": None, "tono": tono}

    voz_id = voz_id or VOZ_NARRACION_PREDETERMINADA
    if voz_id not in VOCES_NARRACION:
        raise ValueError(f"Voz inválida. Usá: {', '.join(sorted(VOCES_NARRACION))}")
    return {"motor": "narracion", "voz_id": voz_id, "tono": tono}


def voz_del_libro(indice: dict) -> dict:
    """Lee la configuración de voz de un indice.json; si no tiene (libro viejo), la de siempre."""
    voz = indice.get("voz")
    if not voz or voz.get("motor") not in MOTORES:
        return configuracion_por_defecto()
    return {
        "motor": voz.get("motor", "sistema"),
        "voz_id": voz.get("voz_id"),
        "tono": voz.get("tono", TONO_PREDETERMINADO),
    }


def lista_para_frontend() -> dict:
    """Catálogo que la PWA necesita para pintar los selectores de importación."""
    return {
        "voces": [
            {"id": id_, "nombre": nombre, "idioma": NOMBRES_DE_IDIOMA.get(id_.split("-")[0], id_.split("-")[0])}
            for id_, nombre in VOCES_NARRACION.items()
        ],
        "tonos": [{"id": id_, "nombre": datos["nombre"]} for id_, datos in TONOS.items()],
        "voz_predeterminada": VOZ_NARRACION_PREDETERMINADA,
    }
