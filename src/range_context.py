"""Was die Quellen zu einem Zeitraum sagen (ohne Qt), für „Zeitraum nachtragen“.

Wie in „Companion“: Markierst du in der Timeline einen Zeitraum, zeigt der Dialog, was in
dieser Zeit los war, nach Quelle getrennt:

    Rechner   Excel 25 min · Outlook 10 min · DC01 – Remotedesktop 5 min
    Kalender  Workshop Anforderungen (10:00–11:00)
    Anrufe    Kanzlei Schmidt (0251 123456) 4 min
    Verbindungen  RDP Müller GmbH - TS01 35 min

suggestion() liefert dazu einen Vorschlag (Kunde, Text), wenn ein Termin oder Anruf den
Zeitraum überwiegend füllt.
"""
from datetime import datetime

TIME_FMT = "%Y-%m-%d %H:%M:%S"
CALENDAR_TYPES = {"Termin", "Teams-Besprechung"}
SKIP_TYPES = {"Mail gesendet", "Mail beantwortet"}


def _t(text):
    return datetime.strptime(text, TIME_FMT)


def _overlap(entry, start, end):
    """Sekunden, die entry im Zeitraum liegt."""
    try:
        s, e = _t(entry["start"]), _t(entry["end"])
    except (KeyError, ValueError):
        return 0.0
    return max(0.0, (min(e, end) - max(s, start)).total_seconds())


def _min(seconds):
    m = int(round(seconds / 60))
    return f"{m} min" if m < 60 else f"{m // 60}:{m % 60:02d} h"


def _source(entry):
    kind = entry.get("type") or ""
    if "app" in entry or kind.startswith("PC:"):
        return "Rechner"
    if kind in CALENDAR_TYPES:
        return "Kalender"
    if entry.get("direction") or "Telefonat" in kind or "Anruf" in kind:
        return "Anrufe"
    return "Verbindungen"


def context(start, end, activities, pc_entries, limit=3):
    """[(Quelle, Text)] für den Zeitraum start–end (datetime), wichtigste Quelle zuerst."""
    if end <= start:
        return []
    groups = {}
    for e in list(pc_entries or ()) + list(activities or ()):
        if e.get("type") in SKIP_TYPES or e.get("doc") or e.get("open") or e.get("work"):
            continue
        sec = _overlap(e, start, end)
        if sec < 30:
            continue
        src = _source(e)
        if src == "Rechner":
            label = (e.get("type") or "PC: ?")[4:].strip() or e.get("app", "")
        elif src == "Kalender":
            label = f"{e.get('customer_name') or 'Termin'} ({e['start'][11:16]}–{e['end'][11:16]})"
        else:
            label = (f"{e.get('type', '')} " if src == "Verbindungen" else "") + (e.get("customer_name") or "")
        bucket = groups.setdefault(src, {})
        bucket[label.strip()] = bucket.get(label.strip(), 0) + sec
    result = []
    for src in ("Rechner", "Kalender", "Anrufe", "Verbindungen"):
        items = sorted(groups.get(src, {}).items(), key=lambda x: -x[1])
        if not items:
            continue
        parts = [label if src == "Kalender" else f"{label} {_min(sec)}" for label, sec in items[:limit]]
        if len(items) > limit:
            parts.append(f"+{len(items) - limit} weitere")
        result.append((src, " · ".join(parts)))
    return result


def suggestion(start, end, activities, index=None):
    """(Kunde, Text) aus einem Termin oder Anruf, der mindestens die Hälfte füllt, sonst None."""
    total = (end - start).total_seconds()
    if total <= 0:
        return None
    best, best_sec = None, 0.0
    for e in activities or ():
        if _source(e) not in ("Kalender", "Anrufe"):
            continue
        sec = _overlap(e, start, end)
        if sec > best_sec:
            best, best_sec = e, sec
    if best is None or best_sec < total / 2:
        return None
    customer = index.customer_for(best) if index else ""
    if _source(best) == "Kalender":
        return customer, best.get("customer_name") or "Termin"
    return customer, "Telefonat"
