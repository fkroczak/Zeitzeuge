"""
Vermutete Fahrten (ohne Qt): Zeiten, in denen du vermutlich unterwegs warst.

Zwei Hinweise, beide nur Vorschläge (Typ "Fahrt (vermutet)"):

1. Termin mit Ort (kein Teams, kein Link, nicht ganztags): Liegt davor eine Lücke ohne
   Arbeit am PC (PC aus, Ruhezustand, gesperrt oder einfach nichts aufgezeichnet), ist sie
   die Hinfahrt: vom letzten Eintrag davor bis zum Beginn des Termins. Ebenso die Rückfahrt
   vom Ende des Termins bis zum nächsten Eintrag.
2. Wechsel des Netzwerks mit einer Lücke dazwischen, wenn eins der Netze einem Kunden
   gehört (Kundenliste, Spur „Netzwerk“): die Lücke ist die Fahrt dorthin oder zurück.

Ist die Fahrzeit nicht bekannt, gilt für Hin- und Rückfahrt dieselbe, die kürzere der beiden
Lücken. Lücken unter MIN_MINUTES zählen nicht, längere als max_minutes werden auf max_minutes vor
dem Termin (bzw. danach) gekürzt. Bekannte Orte (Einstellung „Orte und Fahrzeiten“,
travel_places) und Kunden mit Fahrzeit (Kundenliste, berechnet über OpenStreetMap) haben eine
feste Fahrzeit, ebenso ein Termin, dessen Ort eine Adresse ist (route.py): Sie ersetzt max_minutes, 0 heißt keine Fahrt
(eigenes Büro, Besprechungsraum). Ein Ort passt, wenn sein Name im Ort oder im Betreff
bzw. Kunden des Termins steht. Andere Termine zählen als belegt: Eine Fahrt überlappt sie nie. Die Fahrt trägt den Betreff und die Teilnehmer-Domains
des Termins, damit Kunde und Nachfrage („Was hast du gemacht?“) passen.
"""

from datetime import timedelta

import timefmt

TIME_FMT = "%Y-%m-%d %H:%M:%S"
TYPE = "Fahrt (vermutet)"
MIN_MINUTES = 10
MAX_MINUTES = 90
# Typen, die zeigen, dass du gerade nicht unterwegs warst (am PC oder am Telefon)
AWAY_TYPES = ("PC gesperrt", "Ruhezustand", "PC aus", "Abgemeldet")
_ONLINE = ("teams", "zoom", "webex", "http", "skype", "online", "telefon")


def _t(text):
    return timefmt.parse(text[:19])


def _fmt(when):
    return timefmt.fmt(when)


def is_place(location, ignore=()):
    """Ist der Ort eines Termins ein echter Ort (keine Online-Besprechung, kein eigener Raum)?"""
    text = (location or "").strip().lower()
    if not text:
        return False
    if any(word in text for word in _ONLINE):
        return False
    return not any(i.lower() in text for i in ignore if i)


def place_minutes(appointment, places):
    """Fahrzeit des am besten passenden bekannten Orts oder None. Passt ein Ort mit 0 Minuten
    (Besprechungsraum, Büro), gilt immer 0, sonst der längste passende Name.
    places: [{"name": "Besprechungsraum", "minutes": 0}, …]"""
    text = f"{_location(appointment)} {appointment.get('customer_name') or ''}".lower()
    best = None
    for place in places or ():
        name = str(place.get("name") or "").strip().lower()
        if not name or name not in text:
            continue
        try:
            minutes = max(0, int(place.get("minutes") or 0))
        except (TypeError, ValueError):
            continue
        if minutes == 0:
            return 0
        if best is None or len(name) > len(best[0]):
            best = (name, minutes)
    return best[1] if best else None


def places_from_config(config, customers=()):
    """Bekannte Orte aus der Einstellung, dazu die alten travel_ignore_locations (= 0 Min.)
    und Kunden mit Fahrzeit (customers: Kundenliste, Name passt im Ort oder Betreff)."""
    places = [p for p in (config.get("travel_places") or []) if isinstance(p, dict)]
    known = {str(p.get("name", "")).strip().lower() for p in places}
    places += [{"name": n, "minutes": 0} for n in (config.get("travel_ignore_locations") or [])
               if n and n.strip().lower() not in known]
    known |= {str(p.get("name", "")).strip().lower() for p in places}
    for c in customers or ():
        minutes = c.get("travel_minutes")
        if minutes is not None and c.get("name") and c["name"].strip().lower() not in known:
            places.append({"name": c["name"], "minutes": minutes})
    return places


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
        if _location(appointment):
            entry["location"] = _location(appointment)
    return entry


def address_key(home, place):
    """Schlüssel für gemerkte Fahrzeiten und Kilometer (travel_address_minutes/_km)."""
    return f"{' '.join(str(home).split())} → {' '.join(str(place).split())}".casefold()


def guess_for(trips, start, end, config, customers=()):
    """Reise für eine Tätigkeit von start bis end vorbelegen: die vermutete Fahrt, die am meisten
    in die Zeit fällt, sonst die Hinfahrt, die bis zu 30 Min. vor Beginn endet.
    -> {location, departure "HH:MM", km (0 = unbekannt), label} oder None."""
    best, best_overlap = None, timedelta(0)
    for trip in trips:
        try:
            t_start, t_end = _t(trip["start"]), _t(trip["end"])
        except (KeyError, TypeError, ValueError):
            continue
        overlap = min(end, t_end) - max(start, t_start)
        if overlap > best_overlap:
            best, best_overlap = trip, overlap
    if best is None:
        before = [t for t in trips if t.get("travel") in ("Hinfahrt", "Fahrt")
                  and timedelta(0) <= start - _t(t["end"]) <= timedelta(minutes=30)]
        best = max(before, key=lambda t: t["end"]) if before else None
    if best is None:
        return None
    label = best.get("customer_name") or ""
    location = best.get("location") or ""
    if not location:  # Fahrt zu einem Kundennetz: „zu Müller GmbH“ / „von Müller GmbH“
        location = label[3:] if label.startswith("zu ") else label[4:] if label.startswith("von ") else label
    km = 0
    home = config.get("travel_home_address") or ""
    known = config.get("travel_address_km")
    if home and best.get("location") and isinstance(known, dict):
        km = known.get(address_key(home, best["location"])) or 0
    if not km:
        name = location.casefold()
        for c in customers or ():
            if isinstance(c, dict) and str(c.get("name", "")).casefold() == name and c.get("travel_km"):
                km = c["travel_km"]
                break
    return {"location": location, "departure": _t(best["start"]).strftime("%H:%M"),
            "km": int(km or 0), "label": f"{best.get('travel', 'Fahrt')} {_t(best['start']):%H:%M}–"
                                         f"{_t(best['end']):%H:%M}"}


def _free(spans, start, end):
    return not any(a < end and start < b for a, b in spans)


def suggest(entries, pc_entries=(), customer_net=None, ignore_locations=(),
            min_minutes=MIN_MINUTES, max_minutes=MAX_MINUTES, places=(), customer_minutes=None,
            address_minutes=None):
    """Vermutete Fahrten eines Tages. entries: alle Einträge (mit Outlook und Netzwerk),
    pc_entries: aktive Fenster. customer_net(name) -> Kundenname oder "" (Kundenliste).
    places: bekannte Orte mit Fahrzeit (place_minutes). address_minutes(termin) -> Fahrzeit
    zur Adresse im Ort des Termins (OpenStreetMap) oder None. customer_minutes(termin) ->
    Fahrzeit des Kunden, dem der Termin gehört (z. B. über die Mail-Domains), oder None.
    Reihenfolge: bekannter Ort, Adresse des Termins, Kunde."""
    busy = busy_spans(entries, pc_entries)
    appointments = []
    for e in entries:
        if e.get("type") == "Termin":
            try:
                appointments.append((_t(e["start"]), _t(e["end"]), e))
            except (KeyError, TypeError, ValueError):
                continue
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
        known = place_minutes(a, places)
        if known is None and address_minutes:
            known = address_minutes(a)
        if known is None and customer_minutes:
            known = customer_minutes(a)
        if known == 0:
            continue  # eigenes Büro, Besprechungsraum: keine Fahrt
        limit = timedelta(minutes=known if known is not None else max_minutes)
        label = a.get("customer_name") or "Termin"
        # andere Termine zählen als belegt (sonst Fahrt mitten in den Termin davor)
        others = busy + [(s, b) for s, b, e in appointments if e is not a]
        there = back = None
        before = [b for _s, b in others if b <= a_start and b.date() == a_start.date()]
        if before or known:
            start = max(before + [a_start - limit])
            if _free(others, start, a_start):
                there = start
        after = [s for s, _b in others if s >= a_end and s.date() == a_end.date()]
        if after or known:
            end = min(after + [a_end + limit])
            if _free(others, a_end, end):
                back = end
        if known is None and there is not None and back is not None:
            # Fahrzeit unbekannt: Hin und zurück ist derselbe Weg. Die kürzere Lücke ist die
            # bessere Schätzung, die längere enthält meist noch anderes (Pause, Einkauf …).
            way = min(a_start - there, back - a_end)
            if way >= timedelta(minutes=min_minutes):
                there, back = a_start - way, a_end + way
        if there is not None:
            add(there, a_start, label, a, "Hinfahrt")
        if back is not None:
            add(a_end, back, label, a, "Rückfahrt")

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
