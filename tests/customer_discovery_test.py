"""Kollegen in der Anrufliste und Kundenliste aus Matrix42 lernen (ohne Qt)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import colleagues  # noqa: E402
import customer_discovery as cd  # noqa: E402
import customers as cl  # noqa: E402
import day_close  # noqa: E402
import journal  # noqa: E402
import prompt_topics  # noqa: E402

CALLS = [
    {"name": "Sven Kollege", "number": "787"},
    {"name": "Sven Kollege", "number": "025429179180"},    # über die Zentrale
    {"name": "Eva Kollegin", "number": "025429179180"},
    {"name": "Eva Kollegin", "number": "736"},
    {"name": "Tom Kollege", "number": "015112345678"},      # Handy, ruft auch intern an
    {"name": "Tom Kollege", "number": "711"},
    {"name": "Info Kunde", "number": "025429175950"},
    {"name": "Musik", "number": "810"},
]


def test_kollegen_erkennen():
    found = colleagues.detect(CALLS)
    assert found.is_colleague("787")
    assert found.is_colleague("025429179180")             # Zentrale
    assert found.is_colleague("+49 2542 917918 54")       # Durchwahl hinter der Zentrale
    assert found.is_colleague("0151 12345678")            # Handy eines Kollegen
    assert not found.is_colleague("025429175950")         # Kunde mit ähnlicher Vorwahl
    assert not found.is_colleague("")


def test_kollegen_von_hand_und_abschaltbar():
    found = colleagues.detect([], ["0251 999", "0800 1*"])
    assert found.is_colleague("0251999") and found.is_colleague("08001234")
    assert not found.is_colleague("0251998")
    off = colleagues.detect(CALLS, auto=False)
    assert not off.is_colleague("025429179180")
    assert off.is_colleague("787")  # Durchwahl bleibt immer intern


def test_anruf_eines_kollegen_ist_kein_kunde():
    call = {"start": "2026-10-20 10:00:00", "end": "2026-10-20 10:05:00", "type": "Telefonat",
            "customer_name": "Sven Kollege (787)", "phone": "787", "colleague": True}
    assert journal.suggest_customer(call) == ""
    assert prompt_topics.customer_key(call) == ""
    # der Kollege bleibt sichtbar: Name steht weiter im Eintrag
    assert "Sven Kollege" in call["customer_name"]


def test_name_ohne_leerzeichen_gleich():
    assert day_close.same_customer("LESANA Münsterlandpflege", "LESANA Münsterland Pflege GmbH")
    assert not day_close.same_customer("Auto Huber", "Bäckerei Huber")


def _call(day, hm, number, minutes=5, name="Anrufer"):
    h, m = map(int, hm.split(":"))
    end_m = h * 60 + m + minutes
    return {"start": f"{day} {hm}:00", "end": f"{day} {end_m // 60:02d}:{end_m % 60:02d}:00",
            "type": "Telefonat", "phone": number, "customer_name": name, "duration_s": minutes * 60}


def _booking(day, start, end, customer):
    return {"start": f"{day} {start}:00", "end": f"{day} {end}:00", "customer": customer}


DAYS = ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22"]


def test_telefonnummer_aus_buchungen_lernen():
    entries = [_call(d, "09:00", "0251 123456") for d in DAYS]
    entries += [_call(d, "11:00", "0711 5555") for d in DAYS[:2]]  # zu selten
    bookings = [_booking(d, "09:05", "09:35", "Creacam Frästechnik GmbH") for d in DAYS]
    bookings += [_booking(d, "11:00", "11:15", "Andere GmbH") for d in DAYS[:2]]
    found = cd.discover(entries, bookings, [])
    assert [(x["kind"], x["customer"]) for x in found["learn"]] == [("phone", "Creacam Frästechnik GmbH")]
    assert found["learn"][0]["hits"] == 4


def test_kollegen_und_uneindeutiges_lernen_nicht():
    col = colleagues.detect(CALLS)
    entries = [_call(d, "09:00", "787") for d in DAYS]
    entries += [_call(d, "13:00", "0251 777") for d in DAYS]
    bookings = [_booking(d, "09:00", "09:30", "Müller GmbH") for d in DAYS]
    # die Nummer fällt mal auf Müller, mal auf Schmidt: nicht sicher genug
    bookings += [_booking(d, "13:00", "13:30", "Müller GmbH" if i % 2 else "Schmidt AG")
                 for i, d in enumerate(DAYS)]
    assert cd.discover(entries, bookings, [], col)["learn"] == []


def test_namenloses_vpn_lernt_nicht():
    vpn = [{"start": f"{d} 09:00:00", "end": f"{d} 10:00:00", "type": "VPN-Verbindung",
            "customer_name": "FortiClient", "vpn_source": "FortiClient"} for d in DAYS]
    bookings = [_booking(d, "09:00", "10:00", "Kunde A") for d in DAYS]
    assert cd.discover(vpn, bookings, [])["learn"] == []


def test_schreibweise_aus_matrix42_vorschlagen_und_umbenennen():
    customers = [{"name": "Holger Tenbrink", "traces": [{"kind": "phone", "value": "02563 1234"}]}]
    entries = [_call(d, "14:00", "02563 1234") for d in DAYS]
    bookings = [_booking(d, "14:00", "14:30", "H.Tenbrink Montage GmbH") for d in DAYS]
    found = cd.discover(entries, bookings, customers)
    assert found["learn"] == []
    assert [(x["name"], x["to"]) for x in found["rename"]] == [("Holger Tenbrink", "H.Tenbrink Montage GmbH")]
    config = {"customers": customers}
    assert cd.rename_customer(config, "Holger Tenbrink", "H.Tenbrink Montage GmbH")
    assert cl.customer_for({"type": "Telefonat", "phone": "025631234"}, config) == "H.Tenbrink Montage GmbH"
    # entschieden: kommt nicht wieder
    cd.mark(config, found["rename"][0], "umbenannt")
    again = cd.discover(entries, bookings, customers, ignored=cd.decided(config))
    assert again["rename"] == []


def test_automatisch_uebernehmen_nur_einmal():
    entries = [_call(d, "09:00", "0251 123456") for d in DAYS]
    bookings = [_booking(d, "09:05", "09:35", "Creacam GmbH") for d in DAYS]
    config = {}
    applied = cd.auto_apply(config, cd.discover(entries, bookings, []))
    assert len(applied) == 1
    assert cl.customer_for({"type": "Telefonat", "phone": "0251123456"}, config) == "Creacam GmbH"
    # Spur von Hand entfernt: Zeitzeuge lernt sie nicht von selbst wieder
    cl.forget(config, "phone", "0251123456")
    again = cd.discover(entries, bookings, cl.customer_list(config), ignored=cd.decided(config))
    assert again["learn"] == []


def test_bekannter_kunde_behaelt_seine_schreibweise():
    customers = [{"name": "Creacam", "traces": []}]
    entries = [_call(d, "09:00", "0251 123456") for d in DAYS]
    bookings = [_booking(d, "09:05", "09:35", "Creacam Frästechnik GmbH & Co.KG") for d in DAYS]
    found = cd.discover(entries, bookings, customers)
    assert found["learn"][0]["customer"] == "Creacam"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
