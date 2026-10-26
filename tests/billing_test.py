"""Abrechnungstakt (billing.py): Rundung, Ausnahmen je Kunde, Ticketzeile, Buchungszeiten."""
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import billing  # noqa: E402
from billing import Billing, billed_minutes, booking_item, booking_span, hours_text  # noqa: E402
import config_defaults  # noqa: E402
from journal import ticket_line  # noqa: E402

D = "2026-10-20"


def item(start, end, customer="Müller GmbH", text="Drucker eingerichtet"):
    return {"start": f"{D} {start}:00", "end": f"{D} {end}:00", "customer": customer,
            "category": "Fernwartung", "text": text}


@pytest.mark.parametrize("minutes, up, nearest", [
    (1, 15, 15), (7, 15, 15), (8, 15, 15), (12, 15, 15), (15, 15, 15), (16, 30, 15),
    (22, 30, 15), (23, 30, 30), (30, 30, 30), (31, 45, 30), (60, 60, 60), (61, 75, 60),
])
def test_takt_aufrunden_und_naechster(minutes, up, nearest):
    assert billed_minutes(minutes * 60) == up  # Standard: 15 min, angefangener Takt zählt
    assert billed_minutes(minutes * 60, 15, "nearest") == nearest


def test_mindesttakt_null_und_aus():
    assert billed_minutes(0) == 0 and billed_minutes(-5) == 0
    assert billed_minutes(20) == 15  # 20 Sekunden: ein Takt
    assert billed_minutes(20, 15, "nearest") == 15
    assert billed_minutes(12 * 60, 15, "off") == 12
    assert billed_minutes(20, 15, "off") == 1
    assert billed_minutes(12 * 60, 0, "up") == 12  # ungültiger Takt = ohne Takt
    assert billed_minutes(12 * 60, "x", "up") == 12
    assert billed_minutes(12 * 60, 10, "up") == 20
    assert billed_minutes(12 * 60, 6, "up") == 12


def test_sekunden_werden_auf_minuten_gerundet():
    # 15:20 min zählt als 15 min (kein zweiter Takt wegen Sekunden), 15:31 als 16 min
    assert billed_minutes(15 * 60 + 20) == 15
    assert billed_minutes(15 * 60 + 31) == 30


def test_hours_text():
    assert hours_text(15) == "0:15 h" and hours_text(210) == "3:30 h" and hours_text(0) == "0:00 h"


def test_ausnahmen_je_kunde_und_config():
    config = config_defaults.default_config()
    assert (config["billing_step_minutes"], config["billing_mode"]) == (15, "up")
    config["billing_customers"] = {"Müller GmbH": {"step": 30, "mode": "nearest"},
                                   "Intern": {"mode": "off"}, "Kaputt": {"step": -3, "mode": "x"},
                                   "": {"step": 5}}
    b = Billing.from_config(config)
    assert b.rule("müller  gmbh ") == (30, "nearest")  # groß/klein und Leerzeichen egal
    assert b.rule("Intern") == (15, "off") and not b.active("Intern")
    assert b.rule("Kaputt") == (15, "up")  # Ungültiges fällt auf den Standard zurück
    assert b.rule("Unbekannt") == (15, "up")
    assert b.minutes(40 * 60, "Müller GmbH") == 30
    assert b.minutes(40 * 60, "Intern") == 40
    assert b.minutes(40 * 60, "Andere") == 45
    assert b.describe("Intern") == "ohne Abrechnungstakt"
    assert b.describe() == "15-Minuten-Takt, angefangener Takt zählt"
    # Zurückschreiben in die Config
    out = b.to_config({})
    assert out["billing_customers"]["Müller GmbH"] == {"step": 30, "mode": "nearest"}
    assert "" not in out["billing_customers"]
    assert Billing.from_config({}).default == (15, "up")
    assert Billing.from_config({"billing_customers": "kaputt"}).customers == {}


def test_je_taetigkeit_gerundet():
    b = Billing()
    items = [item("10:05", "10:17"), item("11:00", "11:04"), item("14:00", "14:40")]
    assert [b.item_minutes(i) for i in items] == [15, 15, 45]
    assert b.total_minutes(items) == 75  # je Tätigkeit gerundet, nicht 56 -> 60
    assert b.item_minutes({"start": "kaputt"}) == 0


def test_ticketzeile_mit_und_ohne_takt():
    i = item("10:05", "10:17")
    plain = "10:05–10:17 (12 min)  Müller GmbH · Fernwartung: Drucker eingerichtet"
    assert ticket_line(i) == plain  # ohne Regeln wie bisher
    assert ticket_line(i, billing=Billing()) == ("10:05–10:17 (12 min → abgerechnet 0:15 h)  "
                                         "Müller GmbH · Fernwartung: Drucker eingerichtet")
    assert ticket_line(i, billing=Billing(mode="off")) == plain  # abschaltbar
    long = item("09:00", "12:10")
    assert ticket_line(long, billing=Billing()).startswith("09:00–12:10 (3:10 h → abgerechnet 3:15 h)")


def test_buchungszeiten_im_takt():
    b = Billing()
    i = item("10:05", "10:17")
    start, end = booking_span(i, b)
    assert (start, end) == (datetime(2026, 10, 20, 10, 5), datetime(2026, 10, 20, 10, 20))
    booked = booking_item(i, b)
    assert booked["end"] == f"{D} 10:20:00" and booked["text"] == i["text"]
    assert i["end"] == f"{D} 10:17:00"  # Original bleibt
    # Sekunden im Beginn fallen weg
    j = {"start": f"{D} 10:05:40", "end": f"{D} 10:47:10", "customer": "X"}
    assert booking_span(j, b) == (datetime(2026, 10, 20, 10, 5), datetime(2026, 10, 20, 10, 50))
    # Ohne Takt: echte Zeiten
    assert booking_span(i, Billing(mode="off"))[1] == datetime(2026, 10, 20, 10, 17)
    assert booking_span(i, None)[1] == datetime(2026, 10, 20, 10, 17)
    # Kunde mit 30-Minuten-Takt
    b30 = Billing(customers={"Müller GmbH": {"step": 30}})
    assert booking_span(i, b30)[1] == datetime(2026, 10, 20, 10, 35)


def test_notiz_und_modi():
    b = Billing()
    assert b.note(12 * 60) == " → abgerechnet 0:15 h"
    assert b.note(0) == ""
    assert Billing(mode="off").note(12 * 60) == ""
    assert not Billing(mode="off").any_active()
    assert Billing(mode="off", customers={"A": {"mode": "up"}}).any_active()
    assert set(billing.MODES) == {"up", "nearest", "off"}
