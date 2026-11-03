"""Regeln mit mehreren Bedingungen, Treffer und Vorschau, Stichwörter der Kundenliste (ohne Qt)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import customer_discovery as cd  # noqa: E402
import customers as cl  # noqa: E402
import focus  # noqa: E402
import rules  # noqa: E402

D = "2026-10-20"


def pc(start, end, app, title):
    return {"start": f"{D} {start}:00", "end": f"{D} {end}:00", "app": app, "customer_name": title}


CODE_RULE = {"name": "VS Code im Projekt zeiterfassung", "field": "app", "match": "code",
             "category": "Entwicklung", "customer": "", "enabled": True,
             "and": [{"field": "title", "match": "zeiterfassung"}]}
OUTLOOK_RULE = {"name": "Outlook", "field": "app", "match": "outlook", "category": "E-Mail",
                "customer": "", "enabled": True}
WINDOWS = [
    pc("09:00", "09:30", "Code.exe", "main.py - zeiterfassung - Visual Studio Code"),
    pc("09:30", "09:40", "Code.exe", "notizen.md - privat - Visual Studio Code"),
    pc("09:40", "09:50", "OUTLOOK.EXE", "Posteingang - Outlook"),
]


def test_alle_bedingungen_muessen_passen():
    compiled = rules._compile_rules([CODE_RULE])
    assert rules.match_entry(WINDOWS[0], compiled, is_pc=True)[1]["category"] == "Entwicklung"
    assert rules.match_entry(WINDOWS[1], compiled, is_pc=True) is None  # anderes Projekt


def test_fehler_in_weiterer_bedingung():
    bad = dict(CODE_RULE, **{"and": [{"field": "title", "match": "re:(kaputt"}]})
    errors = rules.rule_errors([bad])
    assert errors and errors[0][1].startswith("Bedingung 2:")
    assert rules._compile_rules([bad]) == []  # ungültig: wird übersprungen


def test_treffer_je_regel_und_vorschau():
    rule_list = [CODE_RULE, OUTLOOK_RULE, dict(OUTLOOK_RULE, name="doppelt")]
    assert rules.hit_counts(rule_list, [], WINDOWS) == [1, 1, 0]  # die erste passende zählt
    count, examples = rules.preview(rule_list[2], [], WINDOWS)
    assert count == 1 and examples == ["OUTLOOK.EXE: Posteingang - Outlook"]
    assert rules.preview(dict(CODE_RULE, category=""), [], WINDOWS)[0] == 1  # ohne Kategorie auch


def test_alte_regeln_ohne_und_bleiben_gleich():
    compiled = rules._compile_rules([OUTLOOK_RULE])
    assert rules.match_entry(WINDOWS[2], compiled, is_pc=True)[1]["name"] == "Outlook"


KUNDEN = [
    {"name": "Tuxhorn GmbH", "traces": [{"kind": "word", "value": "Tuxhorn"}]},
    {"name": "Röring GmbH", "traces": [{"kind": "word", "value": "Röring"},
                                       {"kind": "phone", "value": "0251 777"}]},
    {"name": "Stadtwerke Nordhafen", "traces": [{"kind": "word", "value": "SWN-"},
                                                {"kind": "word", "value": "Nordhafen"}]},
]


def test_stichwort_findet_kunden():
    ix = cl.Index(KUNDEN)
    assert ix.keyword("UniFi - Tuxhorn-Standort - Google Chrome") == "Tuxhorn GmbH"
    assert ix.keyword("Angebot Roering.docx") == "Röring GmbH"            # Umlaut egal
    assert ix.keyword("Ticket SWN-4711 Störung") == "Stadtwerke Nordhafen"
    assert ix.keyword("Schuxhorn") == ""                                   # nur am Wortanfang
    # Stichwort greift nur, wenn keine genauere Spur passt
    call = {"type": "Telefonat", "customer_name": "Info Tuxhorn (0251 777)", "phone": "0251 777"}
    assert ix.customer_for(call) == "Röring GmbH"
    assert ix.customer_for({"type": "Telefonat", "customer_name": "Info Tuxhorn (0251 1)",
                            "phone": "0251 1"}) == "Tuxhorn GmbH"
    # Kollegen und eigene Einträge nie
    assert ix.customer_for({"type": "Telefonat", "customer_name": "Tuxhorn Kollege", "colleague": True}) == ""
    assert ix.customer_for({"doc": True, "customer_name": "Tuxhorn"}) == ""


def test_stichwort_in_regel_bloecken_und_arbeitsbloecken():
    ix = cl.Index(KUNDEN)
    windows = [pc("10:00", "10:30", "chrome.exe", "Tuxhorn - UniFi Site Manager"),
               pc("10:30", "11:00", "OUTLOOK.EXE", "AW: Nordhafen Zählerdaten - Outlook")]
    blocks = rules.classify([], windows, [OUTLOOK_RULE, dict(OUTLOOK_RULE, name="Web", match="chrome",
                                                             category="Recherche")], keywords=ix)
    assert [(b["category"], b["customer_name"]) for b in blocks] == [
        ("Recherche", "Tuxhorn GmbH"), ("E-Mail", "Stadtwerke Nordhafen")]
    segs = [{"start": w["start"], "end": w["end"], "app": w["app"], "title": w["customer_name"]}
            for w in windows]
    found = focus.focus_blocks(segs, [OUTLOOK_RULE], keywords=ix)
    assert [b["customer_name"] for b in found] == ["Tuxhorn GmbH", "Stadtwerke Nordhafen"]


DAYS = ["2026-10-19", "2026-10-20", "2026-10-21"]


def _window(day, start, end, title):
    return {"start": f"{day} {start}:00", "end": f"{day} {end}:00", "app": "chrome.exe",
            "customer_name": title}


def _booking(day, start, end, customer):
    return {"start": f"{day} {start}:00", "end": f"{day} {end}:00", "customer": customer}


def test_stichwort_aus_buchungen_lernen():
    windows = [_window(d, "09:00", "09:25", "Tuxhorn - UniFi Site Manager") for d in DAYS]
    bookings = [_booking(d, "09:00", "09:30", "Tuxhorn Blockheizkraftwerke GmbH, Borken") for d in DAYS]
    found = cd.discover(windows, bookings, [])
    assert [(x["kind"], x["value"]) for x in found["learn"]] == [("word", "tuxhorn")]
    assert found["learn"][0]["customer"] == "Tuxhorn Blockheizkraftwerke GmbH, Borken"
    # Ort und allgemeine Wörter nie („Borken“, „Blockheizkraftwerke“ steht nicht im Titel)
    assert not any(x["value"] in ("borken", "gmbh") for x in found["learn"] + found["suggest"])


def test_wenig_zeit_ist_nur_vorschlag_und_bekanntes_kommt_nicht_wieder():
    windows = [_window(DAYS[0], "09:00", "09:15", "Creacam WAN-Störung")]
    bookings = [_booking(DAYS[0], "09:00", "09:30", "Creacam Frästechnik GmbH & Co.KG")]
    found = cd.discover(windows, bookings, [])
    assert found["learn"] == [] and [x["value"] for x in found["suggest"]] == ["creacam"]
    known = [{"name": "Creacam", "traces": [{"kind": "word", "value": "creacam"}]}]
    assert cd.discover(windows, bookings, known)["suggest"] == []


def test_stichwort_eines_anderen_kunden_lernt_nicht():
    # „Tuxhorn“ im Titel, gebucht aber auf Creacam: kein Stichwort für irgendwen
    windows = [_window(d, "09:00", "09:30", "Tuxhorn Angebot") for d in DAYS]
    bookings = [_booking(d, "09:00", "09:30", "Creacam GmbH") for d in DAYS]
    bookings += [_booking(DAYS[0], "12:00", "12:30", "Tuxhorn GmbH")]
    found = cd.discover(windows, bookings, [])
    assert found["learn"] == [] and found["suggest"] == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
