"""Zeitstempel "YYYY-MM-DD HH:MM:SS" schnell lesen.

datetime.strptime ist langsam (Gebietsschema, reguläre Ausdrücke). Beim Zeichnen eines Tages
mit vielen Fensterwechseln fielen Hunderttausende Aufrufe an. fromisoformat liest dasselbe
Format etwa zehnmal schneller; gleiche Zeitstempel kommen oft vor und werden gemerkt.
"""
from datetime import datetime
from functools import lru_cache

TIME_FMT = "%Y-%m-%d %H:%M:%S"


@lru_cache(maxsize=65536)
def parse(text):
    """Wie datetime.strptime(text, TIME_FMT): gleiches Ergebnis, ValueError bei anderem Format."""
    if (len(text) == 19 and text[4] == "-" and text[7] == "-" and text[10] == " "
            and text[13] == ":" and text[16] == ":" and text.isascii()):
        return datetime.fromisoformat(text)
    return datetime.strptime(text, TIME_FMT)  # alles andere genau wie bisher (meist ValueError)
