import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "pipeline"))

from epub_a_capitulos import limpiar  # noqa: E402


def test_une_palabra_cortada_con_guion():
    assert limpiar("una palabra cor- tada al final") == "una palabra cortada al final"


def test_quita_guion_invisible():
    assert limpiar("pa­labra") == "palabra"


def test_colapsa_espacios_y_saltos():
    assert limpiar("hola   mundo\n\n\n\nfin") == "hola mundo\n\nfin"
