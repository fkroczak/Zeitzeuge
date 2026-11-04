"""Nachfragen ohne Doppelte: erkannte Tätigkeiten zu Themen zusammenfassen.

Ein Thema ist alles, was zur selben Arbeit gehört, z. B. VPN „Kanzlei Schmidt - SSL VPN“,
RDP „Kanzlei Schmidt - DC01“ und ein Telefonat mit der Kanzlei kurz danach. Zeitzeuge fragt
dafür einmal, nicht dreimal.

Regeln (rein, ohne Qt):
- Gleicher Kunde und Abstand höchstens gap_minutes: ein Thema.
- Ohne bekannten Kunden (VPN ohne Namen, Arbeitsblock am PC): gehört zum Thema, mit dem es sich
  mindestens zur Hälfte überschneidet.
- Arbeitsblöcke am PC sind nur Beleg: Überschneiden sie sich zur Hälfte mit einer Verbindung oder
  einem Telefonat, gehören sie dazu, auch bei anderem Namen (Fenster „DC01“ zur RDM-Verbindung
  „Kanzlei Schmidt - DC01“).
- Verschiedene bekannte Kunden werden nie zusammengelegt.

Dazu: Wiedererkennen. Wurde ein Thema beantwortet, ignoriert oder zurückgestellt, merkt sich
Zeitzeuge Zeitraum und Kunden (nicht nur einen Schlüssel). Ändert sich ein Eintrag später
(Logs kommen nach, Name wird aufgelöst, eingetragene Zeit kürzer als erkannt), wird trotzdem
nicht noch einmal gefragt.
"""
import re

import timefmt

TIME_FMT = "%Y-%m-%d %H:%M:%S"
_PHONE_SUFFIX = re.compile(r"\s*\([+\d\s/-]{3,}\)\s*$")


def _t(text):
    return timefmt.parse(text)


def customer_key(entry, index=None):
    """Kunde eines Eintrags als Vergleichswert ('' = unbekannt).

    Erst die Kundenliste (index), sonst der Name: „Kanzlei Schmidt - DC01“ (RDM: Kunde - Gerät)
    und „Kanzlei Schmidt (0251 123456)“ (3CX) werden beide zu „kanzlei schmidt“.
    """
    if entry.get("colleague"):
        return ""  # Kollege ist nie der Kunde
    if entry.get("pc_block"):
        name = entry.get("customer_name") or ""  # Kunde aus der Regel, sonst leer
    else:
        name = ""
        if index is not None:
            try:
                name = index.customer_for(entry) or ""
            except Exception:  # Kundenliste darf das Nachfragen nie verhindern
                name = ""
        name = name or entry.get("customer_name") or ""
    if entry.get("tv_id") and re.fullmatch(r"(TeamViewer )?[\d\s]+", name):
        return ""  # unbenannte TeamViewer-ID: kein Kunde bekannt
    name = _PHONE_SUFFIX.sub("", name)
    name = name.split(" - ")[0].split(" – ")[0]
    if re.fullmatch(r"[+\d\s/-]*", name):  # nur eine Nummer
        return ""
    return " ".join(name.casefold().split())


def overlap(a, b):
    """Gemeinsame Sekunden zweier Einträge/Zeiträume (start/end als Text)."""
    start, end = max(a["start"], b["start"]), min(a["end"], b["end"])
    return (_t(end) - _t(start)).total_seconds() if start < end else 0.0


def _length(e):
    return max(1.0, (_t(e["end"]) - _t(e["start"])).total_seconds())


def _gap(a, b):
    """Abstand in Sekunden (0, wenn sie sich überschneiden)."""
    if a["end"] >= b["start"] and b["end"] >= a["start"]:
        return 0.0
    first, second = (a, b) if a["end"] < b["start"] else (b, a)
    return (_t(second["start"]) - _t(first["end"])).total_seconds()


def _evidence(e):
    """Arbeitsblöcke am PC und Zugangsdaten belegen nur, sie bilden selten ein eigenes Thema."""
    return bool(e.get("pc_block"))


def build_topics(entries, index=None, gap_minutes=15):
    """Offene Einträge -> Themen (Timeline-Format). Ein Eintrag gehört zu genau einem Thema.

    Ein Thema mit mehreren Teilen übernimmt die Felder des längsten Teils (Typ, Kunde, tv_id …),
    Beginn und Ende umfassen alle Teile, "parts" listet sie.
    """
    gap = gap_minutes * 60
    items = sorted(entries, key=lambda e: (e["start"], e["end"]))
    groups = []  # [{"parts": [...], "customer": key, "start", "end"}]
    for e in items:
        key = customer_key(e, index)
        best = None
        for g in groups:
            if key and g["customer"] and key != g["customer"]:
                continue  # verschiedene bekannte Kunden: nie zusammen
            same_customer = key and key == g["customer"]
            if same_customer and _gap(g, e) <= gap:
                best = g
                break
            shared = overlap(g, e)
            if shared >= 0.5 * min(_length(e), _length(g)) and (not key or not g["customer"]
                                                                  or _evidence(e)):
                best = g
                break
        if best is None and _evidence(e):
            # Arbeitsblock mit anderem Namen, aber deutlich in einer Verbindung: dazu
            for g in groups:
                if overlap(g, e) >= 0.5 * _length(e):
                    best = g
                    break
        if best is None:
            groups.append({"parts": [e], "customer": key, "start": e["start"], "end": e["end"]})
        else:
            best["parts"].append(e)
            best["start"], best["end"] = min(best["start"], e["start"]), max(best["end"], e["end"])
            if not best["customer"] and key and not _evidence(e):
                best["customer"] = key
    return [_topic(g) for g in groups]


def _topic(group):
    parts = group["parts"]
    if len(parts) == 1:
        return parts[0]
    # Hauptteil: längster echter Eintrag (Verbindung, Telefonat …), Arbeitsblöcke nur zur Not
    main = max(parts, key=lambda p: (not _evidence(p), _length(p)))
    topic = dict(main)
    topic.update({"start": group["start"], "end": group["end"], "parts": parts, "topic": True})
    topic.pop("duration_s", None)  # Dauer gilt fürs ganze Thema
    topic.pop("running", None)
    return topic


def answer_span(entry, index=None):
    """Was gemerkt wird, wenn ein Thema beantwortet, ignoriert oder zurückgestellt wird."""
    return {"start": entry["start"], "end": entry["end"], "customer": customer_key(entry, index)}


def matches_span(entry, span, index=None, share=0.5):
    """Gehört entry zu einem gemerkten Zeitraum? Mindestens share von entry liegt darin
    und die Kunden passen (gleich oder einer unbekannt)."""
    try:
        if overlap(entry, span) < share * _length(entry):
            return False
    except (KeyError, TypeError, ValueError):
        return False
    key, other = customer_key(entry, index), span.get("customer") or ""
    return not key or not other or key == other


def parts_text(entry):
    """„dazu Telefonat, VPN-Verbindung“ für Themen mit mehreren Teilen ('' sonst).

    PC-Arbeitsblöcke führen unter "parts" nur (Programm, Sekunden)-Paare, die zählen nicht."""
    parts = [p for p in entry.get("parts") or [] if isinstance(p, dict)]
    if len(parts) < 2:
        return ""
    main = entry.get("type")
    names = []
    for p in parts:
        name = "Arbeit am PC" if p.get("pc_block") else p.get("type", "")
        if name and name != main and name not in names:
            names.append(name)
    return f"dazu {', '.join(names)}" if names else f"{len(parts)} Einträge"
