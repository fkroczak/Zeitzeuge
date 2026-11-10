"""Fahrzeit über OpenStreetMap (route.py) mit nachgebauten Antworten, ohne Netz."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pytest  # noqa: E402

import route  # noqa: E402


def fake(urls, duration=1260, known=("Büro", "Kunde")):
    def fetch(url):
        urls.append(url)
        if "nominatim" in url:
            hit = next((k for k in known if k in __import__("urllib.parse").parse.unquote_plus(url)), None)
            return [{"lat": "48.7", "lon": "9.1" if hit == "Büro" else "9.2"}] if hit else []
        return {"routes": [{"duration": duration}]}
    return fetch


def test_fahrzeit_aufgerundet(monkeypatch):
    monkeypatch.setattr(route.time, "sleep", lambda s: None)
    route._cache.clear()
    urls = []
    assert route.drive_minutes("Büro, Stuttgart", "Kunde, Esslingen", fake(urls)) == 25  # 21 Min. -> 25
    assert "9.1,48.7;9.2,48.7" in urls[-1]  # OSRM: Länge, Breite
    # Adressen kommen aus dem Speicher, nur die Route wird neu gefragt
    urls.clear()
    assert route.drive_minutes("Büro, Stuttgart", "Kunde, Esslingen", fake(urls, 60)) == 5
    assert len(urls) == 1 and "osrm" in urls[0]
    # keine Kennung des Nutzers in den Abfragen
    assert all("@" not in u for u in urls)


def test_fehler_verstaendlich(monkeypatch):
    monkeypatch.setattr(route.time, "sleep", lambda s: None)
    route._cache.clear()
    with pytest.raises(route.RouteError, match="nicht gefunden"):
        route.drive_minutes("Büro", "Nirgendwo 1", fake([]))
    with pytest.raises(route.RouteError, match="keine Adresse"):
        route.drive_minutes("Büro", "  ", fake([]))

    def offline(url):
        raise OSError("kein Netz")
    route._cache.clear()
    with pytest.raises(route.RouteError, match="nicht erreichbar"):
        route.drive_minutes("Büro", "Kunde", offline)
