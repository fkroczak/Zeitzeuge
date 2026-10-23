"""Tätigkeiten nachtragen: Ablage, offene erkennen, ignorieren und Vorschläge (ohne Oberfläche).

Nachfrage und Erinnerung in der Oberfläche prüft journal_gui_test.py.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import journal  # noqa: E402
from journal import Journal, entry_key, ticket_line  # noqa: E402

DAY = "2026-10-20"
TV = {"start": f"{DAY} 10:00:00", "end": f"{DAY} 10:40:00", "type": "TeamViewer",
      "customer_name": "TeamViewer 123 456 789", "tv_id": "123456789"}
CALL = {"start": f"{DAY} 11:00:00", "end": f"{DAY} 11:03:00", "type": "Telefonat",
        "customer_name": "Max (0711 1234)", "direction": "Eingehend"}
VPN = {"start": f"{DAY} 12:00:00", "end": f"{DAY} 13:00:00", "type": "VPN-Verbindung",
       "customer_name": "Kunde X", "running": True}
NOW = datetime(2026, 10, 20, 18, 0)


def test_ablage(tmp_path):
    """Offene erkennen, eintragen, neu laden, verschieben, löschen, ungültige Zeit, ignorieren."""
    day, tv, call, vpn, now = DAY, TV, CALL, VPN, NOW
    folder = str(tmp_path)
    j = Journal(folder)

    open_ = j.open_items([tv, call, vpn], day, min_minutes=5, now=now)
    assert open_ == [tv], open_  # Anruf zu kurz, VPN läuft noch

    # Schwelle je Art: Telefonate ab 1 min, Verbindungen ab 60 min
    def limit(e):
        return 1 if e["type"] == "Telefonat" else 60
    assert j.open_items([tv, call], day, min_minutes=limit, now=now) == [call]
    # Telefonat mit 40 s (Balken 1 min breit) zählt nach echter Dauer
    short = dict(call, end=f"{day} 11:01:00", duration_s=40)
    assert j.open_items([short], day, min_minutes=1, now=now) == []
    assert j.open_items([short], day, min_minutes=0, now=now) == [short]

    item = j.add({"start": f"{day} 10:00:00", "end": f"{day} 10:30:00", "customer": "Müller GmbH",
                  "category": "Fernwartung", "text": "Drucker eingerichtet"})
    assert j.open_items([tv], day, now=now) == [], "zu 3/4 dokumentiert gilt als erledigt"
    assert ticket_line(item) == "10:00–10:30 (30 min)  Müller GmbH · Fernwartung: Drucker eingerichtet"

    # Neu laden von der Platte
    j2 = Journal(folder)
    assert [i["text"] for i in j2.items(day)] == ["Drucker eingerichtet"]
    assert j2.customers(today=datetime(2026, 10, 21)) == ["Müller GmbH"]

    # Ändern auf einen anderen Tag verschiebt die Datei
    moved = j2.update(item, {"start": "2026-10-21 08:00:00", "end": "2026-10-21 08:30:00"})
    assert j2.items(day) == [] and j2.items("2026-10-21")[0]["id"] == moved["id"]
    j2.delete(moved)
    assert j2.items("2026-10-21") == []

    # Ende vor Beginn wird abgelehnt
    with pytest.raises(ValueError):
        j2.add({"start": f"{day} 10:00:00", "end": f"{day} 09:00:00"})  # sonst: ungültige Zeit gespeichert

    # Ignorieren
    j2.ignore(tv)
    assert j2.is_ignored(tv) and j2.open_items([tv], day, now=now) == []
    assert entry_key(tv) == f"TeamViewer|123456789|{day} 10:00"


def test_kaputte_tagesdatei(tmp_path):
    """Kaputte Tagesdatei: beiseitelegen, nicht überschreiben."""
    folder = str(tmp_path)
    bad = os.path.join(folder, "2026-10-19.json")
    with open(bad, "w", encoding="utf-8") as f:
        f.write('{"items": [ {kaputt')
    j3 = Journal(folder)
    assert j3.items("2026-10-19") == []
    assert any(n.startswith("2026-10-19.json.defekt-") for n in os.listdir(folder)), os.listdir(folder)


def test_vorschlaege():
    """Vorschläge für Kunde und Kategorie."""
    tv, call = TV, CALL
    cats = ["Fernwartung", "Telefonsupport", "Zugangsdaten / Sicherheit"]
    assert journal.suggest_category(tv, cats) == "Fernwartung"
    assert journal.suggest_category(call, cats) == "Telefonsupport"
    assert journal.suggest_customer(call) == "Max"
    assert journal.suggest_customer({"customer_name": "+49 711 1234"}) == ""
    assert journal.suggest_customer(tv, {"123456789": "Müller GmbH"}) == "Müller GmbH"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
