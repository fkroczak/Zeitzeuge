"""
Vermutete Fahrten (ohne Qt): Zeiten, in denen du vermutlich unterwegs warst.

Zwei Hinweise, beide nur Vorschläge (Typ "Fahrt (vermutet)"):

1. Termin mit Ort (kein Teams, kein Link, nicht ganztags): Liegt davor eine Lücke ohne
   Arbeit am PC (PC aus, Ruhezustand, gesperrt oder einfach nichts aufgezeichnet), ist sie
   die Hinfahrt: vom letzten Eintrag davor bis zum Beginn des Termins. Ebenso die Rückfahrt
   vom Ende des Termins bis zum nächsten Eintrag.
2. Wechsel des Netzwerks mit einer Lücke dazwischen, wenn eins der Netze einem Kunden
   gehört (Kundenliste, Spur „Netzwerk“): die Lücke ist die Fahrt dorthin oder zurück.

Lücken unter MIN_MINUTES zählen nicht, längere als max_minutes werden auf max_minutes vor
dem Termin (bzw. danach) gekürzt. Die Fahrt trägt den Betreff und die Teilnehmer-Domains
des Termins, damit Kunde und Nachfrage („Was hast du gemacht?“) passen.
"""

from datetime import datetime, timedelta

TIME_FMT = "%Y-%m-%d %H:%M:%S"
TYPE = "Fahrt (vermutet)"
MIN_MINUTES = 10
MAX_MINUTES = 90
# Typen, die zeigen, dass du gerade nicht unterwegs warst (am PC oder am Telefon)
AWAY_TYPES = ("PC gesperrt", "Ruhezustand", "PC aus", "Abgemeldet")
_ONLINE = ("teams", "zoom", "webex", "http", "skype", "online", "telefon")


def _t(text):
    return datetime.strptime(text[:19], TIME_FMT)


def _fmt(when):
    return when.strftime(TIME_FMT)


def is_place(location, ignore=()):
    """Ist der Ort eines Termins ein echter Ort (keine Online-Besprechung, kein eigener Raum)?"""
    text = (location or "").strip().lower()
    if not text:
        return False
    if any(word in text for word in _ONLINE):
        return False
    return not any(i.lower() in text for i in ignore if i)


def busy_spans(entries, pc_entries=()):
    """Zeiten, in denen du sicher nicht gefahren bist: PC aktiv, Verbindungen, Telefonate …"""
    spans = []
    for e in list(entries) + list(pc_entries):
        kind = e.get("type") or ""
        if kind in AWAY_TYPES or kind == TYPE or kind in ("Netzwerk", "WLAN", "Termin", "Teams-Besprechung"):
            continue
        if e.get("work") or e.get("m42_gap") or e.get("open"):
            continue
        try:
            spans.append((_t(e["start"]), _t(e["end"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(spans)


def _trip(start, end, label, appointment, kind):
    details = f"{kind}: {label}"
    if appointment and appointment.get("details"):
        details += f" · {appointment['details']}"
    entry = {"start": _fmt(start), "end": _fmt(end), "type": TYPE,
             "customer_name": label, "details": details, "travel": kind, "is_suggestion": True}
    if appointment:
        entry["email_domains"] = list(appointment.get("email_domains") or [])
    return entry


def _free(spans, start, end):
    return not any(a < end and start < b for a, b in spans)


def suggest(entries, pc_entries=(), customer_net=None, ignore_locations=(),
            min_minutes=MIN_MINUTES, max_minutes=MAX_MINUTES):
    """Vermutete Fahrten eines Tages. entries: alle Einträge (mit Outlook und Netzwerk),
    pc_entries: aktive Fenster. customer_net(name) -> Kundenname oder "" (Kundenliste)."""
    busy = busy_spans(entries, pc_entries)
    trips = []

    def add(start, end, label, appointment, kind):
        if (end - start).total_seconds() < min_minutes * 60:
            return
        if any(_t(t["start"]) < end and start < _t(t["end"]) for t in trips):
            return  # schon als Fahrt erkannt
        trips.append(_trip(start, end, label, appointment, kind))

    for a in entries:
        if a.get("type") != "Termin" or not is_place(_location(a), ignore_locations):
            continue
        try:
            a_start, a_end = _t(a["start"]), _t(a["end"])
        except (KeyError, TypeError, ValueError):
            continue
        label = a.get("customer_name") or "Termin"
        before = [b for _s, b in busy if b <= a_start and b.date() == a_start.date()]
        if before:
            start = max(max(before), a_start - timedelta(minutes=max_minutes))
            if _free(busy, start, a_start):
                add(start, a_start, label, a, "Hinfahrt")
        after = [s for s, _b in busy if s >= a_end and s.date() == a_end.date()]
        if after:
            end = min(min(after), a_end + timedelta(minutes=max_minutes))
            if _free(busy, a_end, end):
                add(a_end, end, label, a, "Rückfahrt")

    if customer_net:
        nets = sorted((e for e in entries if e.get("type") in ("Netzwerk", "WLAN")), key=lambda e: e["start"])
        for prev, nxt in zip(nets, nets[1:]):
            if prev.get("customer_name") == nxt.get("customer_name"):
                continue
            try:
                start, end = _t(prev["end"]), _t(nxt["start"])
            except (KeyError, TypeError, ValueError):
                continue
            if not timedelta(minutes=min_minutes) <= end - start <= timedelta(minutes=max_minutes * 2):
                continue
            target = customer_net(nxt.get("customer_name", ""))
            source = customer_net(prev.get("customer_name", ""))
            if not (target or source) or not _free(busy, start, end):
                continue
            label = f"zu {target}" if target else f"von {source}"
            add(start, end, label, None, "Fahrt")
    return sorted(trips, key=lambda t: t["start"])


def _location(entry):
    """Ort steht in den Details eines Termins als „Ort: …“."""
    for part in (entry.get("details") or "").split(" · "):
        if part.startswith("Ort: "):
            return part[5:]
    return entry.get("location", "")
