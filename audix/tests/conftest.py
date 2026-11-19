import os

# Los tests no deben generar audio de verdad al importar libros: cada test que
# lo necesite lo enciende a propósito (y reemplaza el generador por uno falso).
os.environ.setdefault("AUDIX_AUDIO_AUTOMATICO", "0")
