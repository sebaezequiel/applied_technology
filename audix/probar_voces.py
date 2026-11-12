import subprocess
import sys
from pathlib import Path

# Voces en español para comparar. Si alguna no existe, se saltea sola.
VOCES = [
    "es_ES-davefx-medium",
    "es_ES-sharvard-medium",
    "es_MX-ald-medium",
    "es_MX-claude-high",
]

# Uso: python probar_voces.py data\la-colina-de-watership\001.txt
texto = Path(sys.argv[1]).read_text(encoding="utf-8")[:1500]  # ~1 minuto de audio
carpeta_voces = Path("voces")
carpeta_salida = Path("pruebas_voces")
carpeta_voces.mkdir(exist_ok=True)
carpeta_salida.mkdir(exist_ok=True)

for voz in VOCES:
    modelo = carpeta_voces / f"{voz}.onnx"
    if not modelo.exists():
        descarga = subprocess.run(
            [sys.executable, "-m", "piper.download_voices", voz, "--download-dir", str(carpeta_voces)],
            capture_output=True, text=True,
        )
        if not modelo.exists():
            print(f"No se pudo descargar {voz}: {descarga.stderr.strip()}")
            continue

    salida = carpeta_salida / f"{voz}.wav"
    subprocess.run(
        [sys.executable, "-m", "piper", "-m", str(modelo), "-f", str(salida)],
        input=texto.encode("utf-8"), check=True,
    )
    print(f"Listo: {salida}")