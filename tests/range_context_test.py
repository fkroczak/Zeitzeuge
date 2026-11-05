"""Zeitraum nachtragen: was die Quellen sagen (range_context.py), ohne Qt."""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import customers as cl  # noqa: E402
import range_context as rc  # noqa: E402

D = "2026-10-21"


def e(a, b, **kw):
    return {"start": f"{D} {a}:00", "end": f"{D} {b}:00", **kw}


ACTS = [e("10:00", "11:00", type="Termin", customer_name="Workshop Nordhafen", email_domains=["nordhafen.de"]),
        e("10:05", "10:09", type="Telefonat", customer_name="Kanzlei Schmidt (0251 1)", direction="Eingehend"),
        e("10:20", "10:50", type="RDP-Verbindung", customer_name="srv01"),
        e("10:30", "10:31", type="Mail gesendet", customer_name="Angebot"),
        e("09:00", "09:30", type="TeamViewer", customer_name="außerhalb")]
PCS = [e("10:00", "10:25", type="PC: Excel", app="excel.exe", customer_name="Liste.xlsx"),
       e("10:25", "10:40", type="PC: Outlook", app="outlook.exe", customer_name="Posteingang"),
       e("10:40", "10:41", type="PC: Teams", app="teams.exe", customer_name="Chat")]
S, E = datetime(2026, 10, 21, 10, 0), datetime(2026, 10, 21, 11, 0)


def test_quellen_nach_art():
    rows = dict(rc.context(S, E, ACTS, PCS))
    assert list(rows) == ["Rechner", "Kalender", "Anrufe", "Verbindungen"]
    assert rows["Rechner"] == "Excel 25 min · Outlook 15 min · Teams 1 min"
    assert rows["Kalender"] == "Workshop Nordhafen (10:00–11:00)"
    assert rows["Anrufe"] == "Kanzlei Schmidt (0251 1) 4 min"
    assert rows["Verbindungen"] == "RDP-Verbindung srv01 30 min"
    assert "außerhalb" not in str(rows) and "Angebot" not in str(rows)  # andere Zeit, Mail
    assert rc.context(E, S, ACTS, PCS) == []


def test_vorschlag_aus_termin():
    index = cl.Index([{"name": "Stadtwerke Nordhafen", "traces": [{"kind": "mail", "value": "nordhafen.de"}]}])
    assert rc.suggestion(S, E, ACTS, index) == ("Stadtwerke Nordhafen", "Workshop Nordhafen")
    # Termin füllt weniger als die Hälfte: kein Vorschlag
    assert rc.suggestion(datetime(2026, 10, 21, 10, 40), datetime(2026, 10, 21, 12, 0), ACTS, index) is None
