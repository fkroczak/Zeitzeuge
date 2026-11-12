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


def test_schaetzung_kunde_und_kategorie():
    """Zeitraum wie „Kennwortauswertung für die Jugendhilfe“: Anruf beim Kunden, Kollege am
    Telefon, Exporte in Excel/Explorer, interner Termin, Büronetz."""
    d = "2026-11-10"

    def x(a, b, **kw):
        return {"start": f"{d} {a}:00", "end": f"{d} {b}:00", **kw}
    acts = [x("13:45", "15:30", type="Netzwerk", customer_name="itm-gruppe.local"),
            x("15:00", "15:30", type="Termin", customer_name="Ausbildungsnachweise prüfen"),
            x("14:50", "15:14", type="Telefonat", customer_name="Joerg Spiekermann (00492962971452)",
              direction="Ausgehend"),
            x("14:00", "14:10", type="Telefonat", customer_name="Sven Brüggemann (787)",
              direction="Eingehend", colleague=True),
            x("14:20", "14:24", type="Datei geöffnet",
              customer_name="Benutzer mit Fehlversuchen (Top 50)-data-2026-11-10.csv"),
            x("14:30", "14:32", type="Datei geöffnet", customer_name="Kennwortstatus_20261110_1430.csv")]
    pcs = [x("13:45", "14:17", type="PC: Chrome", app="chrome.exe", customer_name="Neuer Tab"),
           x("14:17", "14:31", type="PC: Outlook", app="outlook.exe", customer_name="Posteingang"),
           x("14:31", "14:42", type="PC: Excel", app="excel.exe", customer_name="Kennwortstatus_20261110_1430.csv")]
    index = cl.Index([{"name": "Jugendhilfe Olsberg", "traces": [{"kind": "phone", "value": "02962 971452"}]}])
    cats = ["Fernwartung", "Telefonsupport", "Cloud-/M365-Administration", "Zugangsdaten / Sicherheit",
            "E-Mail / Kommunikation", "Beratung / Abstimmung", "Interne Tätigkeit"]
    s, e = datetime(2026, 11, 10, 13, 45), datetime(2026, 11, 10, 15, 30)
    found = rc.estimate(s, e, acts, pcs, index, cats)
    name, pct, why = found["customers"][0]
    assert name == "Jugendhilfe Olsberg" and 50 <= pct < 100 and why.startswith("Anruf Joerg"), found
    assert found["categories"][0][0] == "Zugangsdaten / Sicherheit", found
    assert all(c in cats for c, _p, _w in found["categories"])
    rows = dict(rc.estimate_rows(found))
    assert rows["Kunde (vermutet)"].startswith("Jugendhilfe Olsberg ")
    # Bisherige Buchungen beim Kunden ziehen die Kategorie mit
    history = [{"customer": "Jugendhilfe Olsberg", "category": "Cloud-/M365-Administration",
                "start": f"{d} 08:00:00", "end": f"{d} 12:00:00"}]
    later = rc.estimate(s, e, acts, pcs, index, cats, history=history)
    assert [c for c, _p, _w in later["categories"]] == ["Zugangsdaten / Sicherheit",
                                                         "Cloud-/M365-Administration"], later
    # Keine Spur zu einem Kunden: kein Kunde, Kategorie nur aus der eigenen Liste
    none = rc.estimate(s, e, acts, pcs, cl.Index([]), ["Interne Tätigkeit"])
    assert none == {"customers": [], "categories": []}


def test_kategorie_aus_text():
    """Fernwartung laut Quellen, dein Text sagt aber Drucker und 3CX eingerichtet."""
    d = "2026-11-10"
    acts = [{"start": f"{d} 16:02:00", "end": f"{d} 16:29:00", "type": "Telefonat",
             "customer_name": "Nada Urbaitis-Hodroj (015152292043)", "direction": "Eingehend"},
            {"start": f"{d} 16:05:00", "end": f"{d} 16:17:00", "type": "TeamViewer",
             "customer_name": "TeamViewer 1 142 855 164", "tv_id": "1142855164"}]
    cats = ["Fernwartung", "Telefonsupport", "Server-/Netzwerkadministration", "Interne Tätigkeit"]
    s, e = datetime(2026, 11, 10, 16, 2), datetime(2026, 11, 10, 16, 29)
    before = [c for c, _p, _w in rc.estimate(s, e, acts, [], cl.Index([]), cats)["categories"]]
    assert set(before) == {"Telefonsupport", "Fernwartung"}, before
    text = "- Rücksprache mit Kunden\n- Aufschalten auf Kundensystem\n- Einrichtung Drucker\n" \
           "- Einrichtung 3CX\n- Diverse Anpassungen\n- Tests OK"
    top = rc.estimate(s, e, acts, [], cl.Index([]), cats, text=text)["categories"][0]
    assert top[0] == "Server-/Netzwerkadministration" and "Drucker" in top[2], top
    # Gelernt: „Lexware“ stand bisher zweimal bei Interne Tätigkeit
    history = [{"category": "Interne Tätigkeit", "text": "Lexware Update"},
               {"category": "Interne Tätigkeit", "text": "Lexware Stand geprüft"}]
    top = rc.estimate(s, e, acts, [], cl.Index([]), cats, history=history,
                      text="Lexware aktualisiert")["categories"][0]
    assert top[0] == "Interne Tätigkeit" and "lexware" in top[2], top


def test_dateien_und_web_nicht_unter_verbindungen():
    link = ("ms-screensketch:edit?&filePath=C%3A%5CUsers%5Cx%5COneDrive%5CBilder%5C"
            "Screenshot%202026-11-12%20101208.png&source=1")
    acts = [e("10:00", "10:05", type="Datei geöffnet", customer_name=r"C:\Users\x\Screenshot 1.png"),
            e("10:10", "10:15", type="Datei geöffnet", customer_name=link),
            e("10:00", "10:30", type="Browser", customer_name="claude.ai"),
            e("10:00", "11:00", type="Netzwerk", customer_name="Büro")]
    rows = dict(rc.context(S, E, acts, []))
    assert "Verbindungen" not in rows
    assert rows["Dateien"] == "Screenshot 1.png · Screenshot 2026-11-12 101208.png"
    assert rows["Web"] == "claude.ai 30 min"
    assert rows["Netzwerk"] == "Büro 1:00 h"


def test_lange_namen_gekuerzt():
    rows = dict(rc.context(S, E, [], [e("10:00", "10:30", type="PC: " + "X" * 80, app="x.exe")]))
    assert rows["Rechner"].startswith("X" * 39 + "…")
    assert rc._short("Claude - Anleitung Kennwort ändern - Claude Desktop") == "Claude - Anleitung Kennwort ändern…"
