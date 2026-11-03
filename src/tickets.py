"""
Ticketnummern und Ticket-Format (reine Logik, ohne Qt).

- suggest(): Ticketnummern aus dem PC-Verlauf (Fenstertitel) und den Matrix42-Buchungen
  im Zeitraum einer Tätigkeit, längste zuerst. Nur Vorschläge, nie automatisch eingesetzt.
- format_ticket_text(): Text im Format der ITM-Ticket-Dokumentation
  ("- " Haupttätigkeit, "-- " Untertätigkeiten).
"""
import re
from datetime import datetime, timedelta

TIME_FMT = "%Y-%m-%d %H:%M:%S"
# Matrix42: TCK0000049374 (wie m42_data.TITLE_RE)
DEFAULT_PATTERNS = [r"TCK\d+"]
MARGIN_MINUTES = 5  # so viel vor Beginn und nach Ende zählt noch dazu


# ------------------------------------------------------------ Ticketnummern

def compile_patterns(patterns):
    """Muster als Regex (Groß-/Kleinschreibung egal). Ungültige werden übersprungen.
    -> (Liste kompilierter Muster, [(Zeile, Fehlertext)])"""
    result, errors = [], []
    for no, text in enumerate(patterns or [], 1):
        text = (text or "").strip()
        if not text:
            continue
        try:
            result.append(re.compile(rf"(?<![A-Za-z0-9])(?:{text})(?![0-9])", re.I))
        except re.error as e:
            errors.append((no, str(e)))
    return result, errors


def find_tickets(text, compiled):
    """Ticketnummern in einem Text. Hat das Muster eine Gruppe, zählt die erste Gruppe."""
    found = []
    for rx in compiled:
        for m in rx.finditer(text or ""):
            value = (m.group(1) if rx.groups and m.group(1) else m.group(0)).strip()
            if value and value.upper() not in (f.upper() for f in found):
                found.append(value.upper() if value[:3].upper() == "TCK" else value)
    return found


def _t(text):
    return datetime.strptime(text[:19], TIME_FMT)


def _overlap(a_start, a_end, b_start, b_end):
    return max(0.0, (min(a_end, b_end) - max(a_start, b_start)).total_seconds())


def _minutes(seconds):
    return f"{max(1, int(round(seconds / 60)))} min"


def suggest(start, end, segments=(), bookings=(), patterns=None, margin_minutes=MARGIN_MINUTES):
    """Ticketnummern im Zeitraum [start - Rand, end + Rand], längste zuerst.

    start, end: datetime. segments: [{start, end, title, app}] (aktive Fenster).
    bookings: Matrix42-Buchungen [{start, end, ticket, …}].
    -> [{"ticket", "seconds", "sources", "label"}], z. B.
       label "TCK0000049374 (Outlook, 12 min)".
    """
    compiled, _errors = compile_patterns(DEFAULT_PATTERNS if patterns is None else patterns)
    if not compiled:
        return []
    lo, hi = start - timedelta(minutes=margin_minutes), end + timedelta(minutes=margin_minutes)
    found = {}  # Schlüssel (groß) -> {"ticket", "seconds", "sources": {Quelle: Sekunden}}

    def add(ticket, seconds, source):
        entry = found.setdefault(ticket.upper(), {"ticket": ticket, "seconds": 0.0, "sources": {}})
        entry["seconds"] += seconds
        entry["sources"][source] = entry["sources"].get(source, 0.0) + seconds

    for seg in segments or ():
        try:
            secs = _overlap(_t(seg["start"]), _t(seg["end"]), lo, hi)
        except (KeyError, TypeError, ValueError):
            continue
        if secs <= 0:
            continue
        for ticket in find_tickets(seg.get("title", ""), compiled):
            add(ticket, secs, seg.get("app") or "PC")
    for b in bookings or ():
        try:
            secs = _overlap(_t(b["start"]), _t(b["end"]), lo, hi)
        except (KeyError, TypeError, ValueError):
            continue
        if secs <= 0:
            continue
        text = " ".join(str(b.get(k) or "") for k in ("ticket", "title"))
        for ticket in find_tickets(text, compiled):
            add(ticket, secs, "Matrix42")
    result = []
    for entry in sorted(found.values(), key=lambda e: (-e["seconds"], e["ticket"])):
        sources = sorted(entry["sources"], key=lambda s: -entry["sources"][s])
        entry["sources"] = sources
        entry["label"] = f"{entry['ticket']} ({', '.join(sources[:2])}, {_minutes(entry['seconds'])})"
        result.append(entry)
    return result


# ------------------------------------------------------------ Ticket-Format "- " / "-- "

STYLES = {"": "Wie eingegeben", "dash": "„- “ Haupttätigkeit, „-- “ Untertätigkeiten"}
_MARK = re.compile(r"^\s*(--|-|–|•|\*)\s+")
# Satzende mitten in einer Zeile: ". " vor einem Großbuchstaben, aber nicht nach Abkürzungen
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])")
_ABBREV = {"z", "b", "d", "h", "u", "a", "ca", "bzw", "inkl", "ggf", "evtl", "usw", "vgl",
           "etc", "nr", "tel", "str", "dr", "hr", "fr", "bspw", "zzgl", "max", "min", "mind"}


def _sentences(line):
    parts, last = [], 0
    for m in _SENTENCE.finditer(line):
        word = re.search(r"([A-Za-zÄÖÜäöüß]+)[.!?]$", line[last:m.start()])
        if word and word.group(1).lower() in _ABBREV:
            continue
        parts.append(line[last:m.start()])
        last = m.end()
    parts.append(line[last:])
    return [p.strip() for p in parts if p.strip()]


def format_ticket_text(text, style=""):
    """Text fürs Ticket. style "" = unverändert, "dash" = erste Zeile (bzw. erster Satz)
    "- …", weitere "-- …". Vorhandene Marken "- " / "-- " bleiben, wie sie sind."""
    text = text or ""
    if style != "dash" or not text.strip():
        return text
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) == 1 and not _MARK.match(lines[0]):
        lines = _sentences(lines[0].strip())
    result = []
    for i, line in enumerate(lines):
        m = _MARK.match(line)
        body = line[m.end():].strip() if m else line.strip()
        if m and m.group(1) == "--" or (not m and line[:1] in " \t" and i):
            level = "--"
        elif m and m.group(1) in "-–":
            level = "-"
        else:  # ohne Marke: erste Zeile Haupttätigkeit, weitere Untertätigkeiten
            level = "-" if i == 0 else "--"
        result.append(f"{level} {body}")
    return "\n".join(result)
