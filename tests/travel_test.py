"""Vermutete Fahrten, beantwortete Mails und Teams-Chats aus Outlook."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import outlook_data  # noqa: E402
import travel  # noqa: E402

D = "2026-11-03"


def e(start, end, kind, name="", **extra):
    return {"start": f"{D} {start}:00", "end": f"{D} {end}:00", "type": kind, "customer_name": name, **extra}


def test_fahrt_zum_termin_mit_ort():
    entries = [
        e("08:00", "08:20", "Datei geöffnet", "Angebot.docx"),
        e("09:30", "11:00", "Termin", "Server-Tausch Müller", details="Ort: Hauptstr. 5, Stuttgart",
          email_domains=["mueller.de"]),
        e("12:05", "12:10", "Telefonat", "Anruf"),
        e("14:00", "15:00", "Termin", "Jour fixe", details="Ort: Microsoft Teams-Besprechung"),
    ]
    pc = [e("07:50", "08:40", "PC: Outlook", "Posteingang", app="outlook.exe")]
    trips = travel.suggest(entries, pc)
    assert [(t["start"][11:16], t["end"][11:16], t["travel"]) for t in trips] == [
        ("08:40", "09:30", "Hinfahrt"), ("11:00", "12:05", "Rückfahrt")], trips
    assert trips[0]["email_domains"] == ["mueller.de"] and trips[0]["type"] == travel.TYPE
    # Am PC gearbeitet bis kurz vor dem Termin: keine Fahrt
    pc2 = [e("07:50", "09:25", "PC: Outlook", "x", app="outlook.exe")]
    assert [t["travel"] for t in travel.suggest(entries, pc2)] == ["Rückfahrt"]
    # Eigener Raum: keine Fahrt
    assert travel.suggest(entries, pc, ignore_locations=["Hauptstr"]) == []


def test_fahrt_ins_kundennetz():
    entries = [e("07:30", "08:10", "Netzwerk", "ITM.local"), e("08:45", "11:00", "Netzwerk", "Kunde-Gast"),
               e("11:40", "16:00", "Netzwerk", "ITM.local")]
    nets = {"Kunde-Gast": "Müller GmbH"}
    trips = travel.suggest(entries, customer_net=lambda n: nets.get(n, ""))
    assert [(t["start"][11:16], t["end"][11:16], t["customer_name"]) for t in trips] == [
        ("08:10", "08:45", "zu Müller GmbH"), ("11:00", "11:40", "von Müller GmbH")], trips
    assert travel.suggest(entries, customer_net=lambda n: "") == []


def test_beantwortete_mails_und_chats():
    out = json.dumps({"ok": True, "eigene_domain": "itm.de", "termine": [], "mails": [],
                      "eingang": [{"zeit": f"{D} 09:00:00", "betreff": "Drucker", "antwort": f"{D} 09:20:00",
                                   "art": 102, "domains": ["kunde.de"]},
                                  {"zeit": f"{D} 09:05:00", "betreff": "Intern", "antwort": "", "art": 104,
                                   "domains": ["itm.de"]}],
                      "chats": [{"zeit": f"{D} 10:00:00", "eigen": True, "domains": ["kunde.de", "itm.de"]},
                                {"zeit": f"{D} 10:04:00", "eigen": False, "domains": ["kunde.de", "itm.de"]},
                                {"zeit": f"{D} 10:30:00", "eigen": True, "domains": ["kunde.de"]},
                                {"zeit": f"{D} 10:31:00", "eigen": True, "domains": ["itm.de"]}]})
    result = outlook_data.parse_output(out)
    days = outlook_data.split_days(result, outlook_data._time(f"{D} 00:00:00"), outlook_data._time(f"{D} 23:59:00"))
    config = {"outlook_enabled": True, "teams_chats_enabled": True}
    rows = [(x["start"][11:16], x["end"][11:16], x["type"], x["customer_name"])
            for x in outlook_data.day_entries(days[D], config)]
    assert rows == [("09:00", "09:03", "Mail beantwortet", "Drucker"),
                    ("10:00", "10:06", "Teams-Chat", "Chat mit kunde.de"),
                    ("10:30", "10:32", "Teams-Chat", "Chat mit kunde.de")], rows
    # Outlook aus, Teams-Chats an: nur die Chats
    only = outlook_data.day_entries(days[D], {"outlook_enabled": False, "teams_chats_enabled": True})
    assert {x["type"] for x in only} == {"Teams-Chat"}
    script = outlook_data.build_script(outlook_data._time(f"{D} 00:00:00"), outlook_data._time(f"{D} 23:59:00"),
                                       inbox=True, chats=True)
    assert "TeamsMessagesData" in script and "0x10810003" in script and "__" not in script
