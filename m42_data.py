"""
Matrix42-Buchungen: Einträge aus dem Kalender umwandeln und mit dem Tag abgleichen.

Rein funktional, ohne Qt und ohne Edge (das Lesen steht in m42_reader.py). So lädt
das Hauptfenster beim Start nichts von der Browser-Steuerung.
"""
import re
from datetime import date, datetime, timedelta

import safe_io

TIME_FMT = "%Y-%m-%d %H:%M:%S"
TITLE_RE = re.compile(r"^\s*(.*?)\s+-\s+(TCK\d+)\s+-\s+(.*?)\s*$")


def parse_title(title):
    """'Systems - TCK0000049374 - Praktikanten' -> (Kunde, Ticket, Betreff)."""
    m = TITLE_RE.match(title or "")
    if not m:
        return (title or "").strip(), "", ""
    return re.sub(r"\s+", " ", m.group(1)), m.group(2), m.group(3)


def _hm(text):
    h, m = text.strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h <= 24 and 0 <= m < 60):
        raise ValueError(text)
    return h, m


def booking_from_event(event):
    """Eintrag aus der Seite -> Buchung {start, end, customer, ticket, subject, entry, title}.
    None, wenn Zeit oder Tag fehlen."""
    day, span = event.get("date"), event.get("time") or ""
    parts = re.split(r"\s*[-–]\s*", span)
    if not day or len(parts) != 2:
        return None
    try:
        start_d = datetime.strptime(day, "%Y-%m-%d")
        (h1, m1), (h2, m2) = _hm(parts[0]), _hm(parts[1])
    except ValueError:
        return None
    start = start_d + timedelta(hours=h1, minutes=m1)
    end = start_d + timedelta(hours=h2, minutes=m2)
    if end <= start:  # über Mitternacht
        end += timedelta(days=1)
    customer, ticket, subject = parse_title(event.get("title"))
    return {"start": start.strftime(TIME_FMT), "end": end.strftime(TIME_FMT),
            "customer": customer, "ticket": ticket, "subject": subject,
            "entry": (event.get("description") or "").strip(),
            "title": (event.get("title") or "").strip()}


def bookings_by_day(days, events):
    """Ergebnis einer Woche -> {Tag: [Buchungen]} für alle gezeigten Tage (auch leere)."""
    result = {d: [] for d in days if d}
    for event in events:
        b = booking_from_event(event)
        if b and b["start"][:10] in result:
            result[b["start"][:10]].append(b)
    for items in result.values():
        items.sort(key=lambda b: b["start"])
    return result


def week_start(day):
    """Montag der Woche (YYYY-MM-DD)."""
    d = date.fromisoformat(day)
    return (d - timedelta(days=d.weekday())).isoformat()


# ------------------------------------------------------------------ Abgleich


def _dt(text):
    return datetime.fromisoformat(text)


def _merge(spans):
    out = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def gaps(work_spans, bookings, min_minutes=5):
    """Zeiten in work_spans [(start, end) als datetime], die keine Buchung abdeckt.
    Lücken unter min_minutes zählen nicht. -> [(start, end)]"""
    booked = _merge([(_dt(b["start"]), _dt(b["end"])) for b in bookings])
    result = []
    for ws, we in work_spans:
        cur = ws
        for bs, be in booked:
            if be <= cur or bs >= we:
                continue
            if bs > cur:
                result.append((cur, min(bs, we)))
            cur = max(cur, be)
            if cur >= we:
                break
        if cur < we:
            result.append((cur, we))
    return [(a, b) for a, b in result if (b - a).total_seconds() >= min_minutes * 60]


def covered_seconds(entry, bookings):
    """Wie viele Sekunden eines Eintrags eine Buchung abdeckt."""
    s, e = _dt(entry["start"]), _dt(entry["end"])
    total = 0
    for bs, be in _merge([(_dt(b["start"]), _dt(b["end"])) for b in bookings]):
        total += max(0, (min(e, be) - max(s, bs)).total_seconds())
    return total


def unbooked(entries, bookings, min_minutes=5, share=0.5):
    """Verbindungen/Telefonate, die höchstens zur Hälfte in einer Buchung liegen."""
    result = []
    for e in entries:
        length = (_dt(e["end"]) - _dt(e["start"])).total_seconds()
        if length < min_minutes * 60:
            continue
        if covered_seconds(e, bookings) < share * length:
            result.append(e)
    return result


def load_store(path):
    data = safe_io.read_json(path, {}, expect=dict)
    days = data.get("tage") if isinstance(data.get("tage"), dict) else {}
    read = data.get("gelesen") if isinstance(data.get("gelesen"), dict) else {}
    days = {k: [b for b in v if isinstance(b, dict) and "start" in b and "end" in b]
            for k, v in days.items() if isinstance(k, str) and isinstance(v, list)}
    return days, read
