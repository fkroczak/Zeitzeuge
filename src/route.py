"""
Fahrzeit zwischen zwei Adressen über OpenStreetMap (ohne Qt).

1. Adresse -> Koordinaten mit Nominatim (nominatim.openstreetmap.org)
2. Koordinaten -> Fahrzeit mit dem Auto über OSRM (router.project-osrm.org)

Beide Dienste sind frei und ohne Schlüssel, aber nur für wenige Abfragen gedacht. Zeitzeuge
fragt darum nur auf Knopfdruck („Berechnen“ beim Kunden) und speichert das Ergebnis als
Fahrzeit beim Kunden. Nach außen gehen nur die beiden Adressen, kein Name, keine Kennung.
"""

import json
import math
import re
import threading
import time
import urllib.parse
import urllib.request

GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
ROUTE_URL = "https://router.project-osrm.org/route/v1/driving/{a};{b}?overview=false"
USER_AGENT = "Zeitzeuge (Zeiterfassung)"  # Nominatim verlangt eine Kennung der Anwendung
TIMEOUT = 15
ROUND_TO = 5  # Minuten: auf volle 5 Minuten aufrunden (Parken, Weg zum Eingang)

_cache = {}  # Adresse -> (lat, lon), solange Zeitzeuge läuft
_lock = threading.Lock()
_last_request = [0.0]  # Nominatim: höchstens eine Abfrage pro Sekunde


class RouteError(Exception):
    """Fahrzeit nicht ermittelt; Text für die Anzeige."""


def _get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept-Language": "de"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def geocode(address, fetch=_get_json):
    """(lat, lon) einer Adresse. RouteError, wenn OpenStreetMap sie nicht kennt."""
    key = " ".join(str(address or "").split())
    if not key:
        raise RouteError("keine Adresse angegeben")
    with _lock:
        if key.casefold() in _cache:
            return _cache[key.casefold()]
        wait = 1.0 - (time.monotonic() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()
    query = urllib.parse.urlencode({"q": key, "format": "json", "limit": 1})
    try:
        found = fetch(f"{GEOCODE_URL}?{query}")
    except Exception as e:
        raise RouteError(f"OpenStreetMap nicht erreichbar ({e})") from e
    if not found:
        raise RouteError(f"Adresse „{key}“ nicht gefunden")
    point = (float(found[0]["lat"]), float(found[0]["lon"]))
    with _lock:
        _cache[key.casefold()] = point
    return point


def drive_minutes(start, target, fetch=_get_json):
    """Fahrzeit mit dem Auto in Minuten (aufgerundet auf ROUND_TO) zwischen zwei Adressen."""
    a, b = geocode(start, fetch), geocode(target, fetch)
    url = ROUTE_URL.format(a=f"{a[1]},{a[0]}", b=f"{b[1]},{b[0]}")  # OSRM: Länge, Breite
    try:
        data = fetch(url)
    except Exception as e:
        raise RouteError(f"Routenplaner nicht erreichbar ({e})") from e
    routes = data.get("routes") if isinstance(data, dict) else None
    if not routes:
        raise RouteError("keine Route gefunden")
    minutes = float(routes[0].get("duration", 0)) / 60
    return max(ROUND_TO, int(math.ceil(minutes / ROUND_TO) * ROUND_TO))


_STREET = re.compile(r"(stra(ss|ß)e|str\.|weg|platz|gasse|allee|ring|damm|ufer|chaussee|steig|pfad"
                     r"|markt)\s*\d", re.IGNORECASE)
_POSTCODE = re.compile(r"(^|\D)\d{4,5}\s+\w")


def looks_like_address(text):
    """Sieht der Ort eines Termins wie eine Postadresse aus (Straße mit Nummer oder PLZ Ort)?
    Nur dann fragt Zeitzeuge OpenStreetMap; „Besprechungsraum 2“ oder „bei Müller“ nicht."""
    text = " ".join(str(text or "").split())
    return bool(text) and bool(_STREET.search(text) or _POSTCODE.search(text))
