"""Acceso a Audix: clave única, sesiones y freno a los intentos fallidos.

La clave no se guarda: se guarda su derivado con scrypt y una sal aleatoria.
Las sesiones son tokens al azar; en disco solo queda su SHA-256, así que leer
el archivo no alcanza para entrar.

Todo vive en `<datos>/_seguridad/`. El guion bajo impide que esa carpeta se
confunda con un libro (los ids de libro no lo admiten).

Para crear o cambiar la clave, en la PC:

    python -m backend.seguridad
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

NOMBRE_CARPETA = "_seguridad"
LARGO_MINIMO = 10
LARGO_MAXIMO = 200
DURACION_SESION = 30 * 24 * 3600  # 30 días
SESIONES_MAXIMAS = 10

# Parámetros de scrypt: ~32 MB de memoria por intento, caro de probar a fuerza bruta.
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MEMORIA = 128 * 1024 * 1024

_candado = threading.Lock()


class ClaveInvalida(ValueError):
    """La clave elegida no cumple los requisitos."""


def carpeta(datos: Path) -> Path:
    return Path(datos) / NOMBRE_CARPETA


def _leer(ruta: Path, vacio):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return vacio


def _guardar(ruta: Path, contenido) -> None:
    """Escribe a un temporal y lo renombra: nunca queda un archivo a medias."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(contenido), encoding="utf-8")
    os.replace(temporal, ruta)


def _derivar(clave: str, sal: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        clave.encode("utf-8"), salt=sal, n=n, r=r, p=p, maxmem=SCRYPT_MEMORIA, dklen=32
    )


# ---------- Clave ----------

def hay_clave(datos: Path) -> bool:
    registro = _leer(carpeta(datos) / "clave.json", None)
    return isinstance(registro, dict) and "hash" in registro and "sal" in registro


def guardar_clave(datos: Path, clave: str) -> None:
    """Crea o reemplaza la clave. Cierra todas las sesiones abiertas."""
    if len(clave) < LARGO_MINIMO:
        raise ClaveInvalida(f"La clave tiene que tener al menos {LARGO_MINIMO} caracteres")
    if len(clave) > LARGO_MAXIMO:
        raise ClaveInvalida(f"La clave no puede superar los {LARGO_MAXIMO} caracteres")
    sal = secrets.token_bytes(16)
    registro = {
        "sal": sal.hex(),
        "hash": _derivar(clave, sal, SCRYPT_N, SCRYPT_R, SCRYPT_P).hex(),
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
    }
    with _candado:
        _guardar(carpeta(datos) / "clave.json", registro)
        _guardar(carpeta(datos) / "sesiones.json", {})


def clave_correcta(datos: Path, clave: str) -> bool:
    registro = _leer(carpeta(datos) / "clave.json", None)
    if not isinstance(registro, dict) or not isinstance(clave, str) or len(clave) > LARGO_MAXIMO:
        return False
    try:
        esperado = bytes.fromhex(registro["hash"])
        calculado = _derivar(
            clave, bytes.fromhex(registro["sal"]), registro["n"], registro["r"], registro["p"]
        )
    except (KeyError, TypeError, ValueError):
        return False
    return hmac.compare_digest(calculado, esperado)


# ---------- Sesiones ----------

def _huella(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _sesiones_vigentes(datos: Path) -> dict:
    sesiones = _leer(carpeta(datos) / "sesiones.json", {})
    if not isinstance(sesiones, dict):
        return {}
    ahora = time.time()
    return {h: v for h, v in sesiones.items() if isinstance(v, (int, float)) and v > ahora}


def abrir_sesion(datos: Path) -> str:
    """Crea una sesión y devuelve su token (solo se entrega una vez, en la cookie)."""
    token = secrets.token_urlsafe(32)
    with _candado:
        sesiones = _sesiones_vigentes(datos)
        # Si hay demasiadas, se cierran las que vencen antes.
        while len(sesiones) >= SESIONES_MAXIMAS:
            del sesiones[min(sesiones, key=sesiones.get)]
        sesiones[_huella(token)] = time.time() + DURACION_SESION
        _guardar(carpeta(datos) / "sesiones.json", sesiones)
    return token


def sesion_valida(datos: Path, token) -> bool:
    if not token or not isinstance(token, str) or len(token) > 200:
        return False
    return _huella(token) in _sesiones_vigentes(datos)


def cerrar_sesion(datos: Path, token) -> None:
    if not token:
        return
    with _candado:
        sesiones = _sesiones_vigentes(datos)
        if sesiones.pop(_huella(token), None) is not None:
            _guardar(carpeta(datos) / "sesiones.json", sesiones)


# ---------- Freno a intentos fallidos ----------

class Freno:
    """Tras varios fallos seguidos, bloquea los intentos por un rato que se va duplicando.

    Es global y no por IP: Audix tiene un solo usuario y detrás de un proxy
    todas las conexiones llegan desde la misma dirección.
    """

    INTENTOS_LIBRES = 5
    ESPERA_INICIAL = 30
    ESPERA_MAXIMA = 15 * 60

    def __init__(self):
        self._candado = threading.Lock()
        self.reiniciar()

    def reiniciar(self) -> None:
        with self._candado:
            self._fallos = 0
            self._hasta = 0.0

    def segundos_de_espera(self) -> int:
        with self._candado:
            return max(0, int(self._hasta - time.time() + 0.999))

    def anotar_fallo(self) -> None:
        with self._candado:
            self._fallos += 1
            extra = self._fallos - self.INTENTOS_LIBRES
            if extra >= 0:
                espera = min(self.ESPERA_MAXIMA, self.ESPERA_INICIAL * (2 ** extra))
                self._hasta = time.time() + espera

    def anotar_acierto(self) -> None:
        self.reiniciar()


# ---------- Uso desde la PC ----------

def _principal() -> int:
    import getpass

    from backend.main import DATA_DIR

    print()
    print("Audix - crear o cambiar la clave de acceso")
    print(f"Carpeta de datos: {DATA_DIR}")
    if hay_clave(DATA_DIR):
        print("Ya hay una clave. Si seguis, se reemplaza y se cierran todas las sesiones.")
    print(f"La clave tiene que tener al menos {LARGO_MINIMO} caracteres. No se muestra al escribir.")
    print()
    clave = getpass.getpass("Clave nueva: ")
    if clave != getpass.getpass("Repetila:    "):
        print("Las claves no coinciden. No se cambio nada.")
        return 1
    try:
        guardar_clave(DATA_DIR, clave)
    except ClaveInvalida as error:
        print(f"{error}. No se cambio nada.")
        return 1
    print("Listo. Clave guardada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_principal())
