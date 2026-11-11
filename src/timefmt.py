"""Zeitstempel "YYYY-MM-DD HH:MM:SS" schnell lesen.

datetime.strptime ist langsam (Gebietsschema, reguläre Ausdrücke). Beim Zeichnen eines Tages
mit vielen Fensterwechseln fielen Hunderttausende Aufrufe an. fromisoformat liest dasselbe
Format etwa zehnmal schneller; gleiche Zeitstempel kommen oft vor und werden gemerkt.
"""
import re
from datetime import datetime, timezone
from functools import lru_cache

TIME_FMT = "%Y-%m-%d %H:%M:%S"


@lru_cache(maxsize=65536)
def parse(text):
    """Wie datetime.strptime(text, TIME_FMT): gleiches Ergebnis, ValueError bei anderem Format."""
    if (len(text) == 19 and text[4] == "-" and text[7] == "-" and text[10] == " "
            and text[13] == ":" and text[16] == ":" and text.isascii()):
        return datetime.fromisoformat(text)
    return datetime.strptime(text, TIME_FMT)  # alles andere genau wie bisher (meist ValueError)


def fmt(when):
    """Wie when.strftime(TIME_FMT), aber etwa fünfmal schneller (isoformat statt strftime)."""
    if when.tzinfo is None and when.year >= 1000:
        return when.isoformat(" ", "seconds")
    return when.strftime(TIME_FMT)  # mit Zeitzone oder ungewöhnlichem Jahr genau wie bisher


def parse_or_none(text):
    """Die ersten 19 Zeichen wie strptime(…, TIME_FMT) lesen; None bei allem anderen."""
    try:
        return datetime.strptime(str(text)[:19], TIME_FMT)
    except (TypeError, ValueError):
        return None


def has_times(entry):
    """Hat der Eintrag lesbare "start" und "end" (wie parse)?"""
    try:
        parse(entry["start"]), parse(entry["end"])
        return True
    except (KeyError, TypeError, ValueError):
        return False


_SYSTEM_TIME = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})")


def event_time(text):
    """SystemTime eines Windows-Ereignisses (UTC, "2026-11-11T07:15:00.123Z") -> Ortszeit
    ohne Zeitzone, None, wenn unlesbar."""
    m = _SYSTEM_TIME.match(text or "")
    if not m:
        return None
    when = datetime.strptime(f"{m.group(1)} {m.group(2)}", TIME_FMT).replace(tzinfo=timezone.utc)
    return when.astimezone().replace(tzinfo=None)
