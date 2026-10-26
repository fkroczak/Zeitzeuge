"""Outlook: Ausgabe des PowerShell-Skripts prüfen, Einträge bilden, Ablage, Leser (ohne Outlook)."""
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import datastore  # noqa: E402
import outlook_data as od  # noqa: E402

# So sieht die Ausgabe von ConvertTo-Json -Compress aus (gekürzt, Namen erfunden)
SAMPLE = {
    "ok": True, "fehler": "", "text": "", "eigene_domain": "itm-gruppe.de",
    "termine": [
        {"start": "2026-10-26 09:00:00", "ende": "2026-10-26 10:00:00", "betreff": "Abstimmung Firewall",
         "ort": "Microsoft Teams-Besprechung https://teams.microsoft.com/l/meetup-join/abc", "teams": True,
         "ganztags": False, "status": 3, "belegt": 2, "privat": False,
         "domains": ["itm-gruppe.de", "kunde-nord.de"]},
        {"start": "2026-10-26 11:00:00", "ende": "2026-10-26 11:30:00", "betreff": "Vor Ort  Server",
         "ort": "Musterstraße 1", "teams": False, "ganztags": False, "status": 0, "belegt": 2,
         "privat": False, "domains": "mail.itm-gruppe.de"},          # ein Element: kein Array
        {"start": "2026-10-26 00:00:00", "ende": "2026-10-27 00:00:00", "betreff": "Urlaub Kollege",
         "ort": "", "teams": False, "ganztags": True, "status": 0, "belegt": 0, "privat": False,
         "domains": []},
        {"start": "2026-10-26 13:00:00", "ende": "2026-10-26 14:00:00", "betreff": "Abgesagt",
         "ort": "", "teams": True, "ganztags": False, "status": 5, "belegt": 2, "privat": False,
         "domains": []},
        {"start": "2026-10-26 17:00:00", "ende": "2026-10-26 18:00:00", "betreff": "Arzt",
         "ort": "Praxis", "teams": False, "ganztags": False, "status": 0, "belegt": 3, "privat": True,
         "domains": ["praxis.de"]},
        {"start": "kaputt", "ende": "2026-10-26 18:00:00", "betreff": "x"},
        "keine Zuordnung",
    ],
    "mails": [
        {"zeit": "2026-10-26 10:15:30", "betreff": "AW: Firewall", "empfaenger": 3,
         "domains": ["kunde-nord.de", "itm-gruppe.de"]},
        {"zeit": "2026-10-26 10:40:00", "betreff": "Intern", "empfaenger": 1, "domains": ["itm-gruppe.de"]},
        {"zeit": "2026-10-25 22:00:00", "betreff": "Gestern", "empfaenger": 1, "domains": ["kunde-sued.de"]},
        {"zeit": None, "betreff": "ohne Zeit"},
    ],
    "kalender_fehler": "", "mails_fehler": "",
}
NOW = datetime(2026, 10, 26, 12, 0)
CONFIG = {"outlook_enabled": True, "outlook_calendar_enabled": True, "outlook_mails_enabled": True,
          "outlook_mails_external_only": True, "outlook_own_domains": [], "outlook_mail_minutes": 3}


@contextlib.contextmanager
def temp_dir():
    """Temp-Ordner; die Datenbank darin vor dem Löschen schließen (Windows sperrt offene Dateien)."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            yield tmp
        finally:
            datastore.unregister(tmp)


def test_ausgabe_lesen():
    text = "WARNUNG: irgendwas\r\n﻿" + json.dumps(SAMPLE)
    r = od.parse_output(text)
    assert r["ok"] and r["eigene_domain"] == ["itm-gruppe.de"]
    assert len(r["termine"]) == 5  # kaputte Einträge fallen weg
    first = r["termine"][0]
    assert first["teams"] and first["location"] == "Microsoft Teams-Besprechung"  # ohne Link
    assert r["termine"][1]["domains"] == ["mail.itm-gruppe.de"]
    assert r["termine"][1]["subject"] == "Vor Ort Server"
    assert r["termine"][3]["canceled"] and r["termine"][2]["all_day"]
    assert [m["start"] for m in r["mails"]] == ["2026-10-26 10:15:30", "2026-10-26 10:40:00",
                                                 "2026-10-25 22:00:00"]
    # Ein einzelner Termin kommt von PowerShell manchmal als Objekt statt als Liste
    one = dict(SAMPLE, termine=SAMPLE["termine"][0], mails=None)
    r1 = od.parse_output(json.dumps(one))
    assert len(r1["termine"]) == 1 and r1["mails"] == []


def test_ausgabe_kaputt():
    for text in ("", "Fehler: Zugriff verweigert", "[1, 2]", "{kaputt"):
        r = od.parse_output(text)
        assert not r["ok"] and r["fehler"] == "fehler"
    r = od.parse_output('{"ok": false, "fehler": "nicht_geoeffnet"}')
    assert od.status_text(r) == od.ERRORS["nicht_geoeffnet"]
    assert "unbekannt" in od.status_text({"ok": False, "fehler": "neu"})


def test_eigene_domains():
    assert od.own_domains({"outlook_own_domains": "@ITM-gruppe.de; itm.de"}) == ["itm-gruppe.de", "itm.de"]
    assert od.own_domains({}, ["itm-gruppe.de"]) == ["itm-gruppe.de"]
    assert od.own_domains({"outlook_own_domains": ["firma.de"]}, ["itm-gruppe.de"]) == ["firma.de"]
    assert od.external(["kunde.de", "itm-gruppe.de", "mail.itm-gruppe.de", "xitm-gruppe.de"],
                       ["itm-gruppe.de"]) == ["kunde.de", "xitm-gruppe.de"]


def test_eintraege():
    r = od.parse_output(json.dumps(SAMPLE))
    days = od.split_days(r, datetime(2026, 10, 25), datetime(2026, 10, 27), NOW)
    assert set(days) == {"2026-10-25", "2026-10-26"}
    entries = od.day_entries(days["2026-10-26"], CONFIG)
    kinds = [(e["start"][11:16], e["type"], e["customer_name"]) for e in entries]
    assert kinds == [
        ("09:00", "Teams-Besprechung", "Abstimmung Firewall"),
        ("10:15", "Mail gesendet", "AW: Firewall"),        # interne Mail fehlt
        ("11:00", "Termin", "Vor Ort Server"),
        ("17:00", "Termin", "Privater Termin"),             # ganztags und abgesagt fehlen
    ]
    meeting, mail, onsite, private = entries
    assert meeting["email_domains"] == ["kunde-nord.de"] and "Teilnehmer: kunde-nord.de" in meeting["details"]
    assert mail["end"] == "2026-10-26 10:18:30" and mail["email_domains"] == ["kunde-nord.de"]
    assert mail["details"] == "an kunde-nord.de (3 Empfänger)"
    assert onsite["email_domains"] == []                # Subdomain der eigenen Firma
    assert private["email_domains"] == [] and "Praxis" not in private["details"]

    # Mails auch intern, 5 Minuten; Kalender aus
    cfg = dict(CONFIG, outlook_mails_external_only=False, outlook_mail_minutes=5,
               outlook_calendar_enabled=False)
    entries = od.day_entries(days["2026-10-26"], cfg)
    assert [(e["customer_name"], e["details"], e["end"][11:]) for e in entries] == [
        ("AW: Firewall", "an kunde-nord.de (3 Empfänger)", "10:20:30"),
        ("Intern", "an intern", "10:45:00")]
    assert od.day_entries(None, CONFIG) == []


def test_skript():
    script = od.build_script(datetime(2026, 10, 12), datetime(2026, 10, 27), calendar=True, mails=False,
                             calendar_path="\\\\o'brien@firma.de\\Kalender", start_outlook=False)
    assert "__" not in script.replace("__VON__", "")  # alle Platzhalter ersetzt
    assert "'2026-10-12 00:00'" in script and "'2026-10-27 00:00'" in script
    assert "if ($false) {\n      try {\n        $sent" in script
    assert "o''brien@firma.de" in script  # Anführungszeichen für PowerShell verdoppelt
    assert "IncludeRecurrences = $true" in script and "Restrict" in script


def test_lesen_ohne_outlook():
    start, end = datetime(2026, 10, 26), datetime(2026, 10, 27)

    def timeout(_script):
        raise subprocess.TimeoutExpired("powershell", 1)

    def missing(_script):
        raise FileNotFoundError("powershell.exe")

    assert od.read_outlook(start, end, CONFIG, runner=timeout)["fehler"] == "zeitlimit"
    assert od.read_outlook(start, end, CONFIG, runner=missing)["fehler"] == "kein_powershell"
    assert od.read_outlook(start, end, CONFIG, runner=lambda s: json.dumps(SAMPLE))["ok"]
    if not od.outlook_installed():  # CI: kein Outlook, also nie PowerShell starten
        r = od.read_outlook(start, end, CONFIG)
        assert not r["ok"] and r["fehler"] in ("nur_windows", "kein_outlook")


@pytest.mark.skipif(sys.platform != "win32" or not shutil.which("powershell"),
                    reason="Windows PowerShell nötig")
def test_skript_laeuft_in_powershell():
    """Das echte Skript in powershell.exe: ohne laufendes Outlook kommt sauber JSON zurück."""
    script = od.build_script(datetime(2026, 10, 25), datetime(2026, 10, 27), start_outlook=False)
    r = od.parse_output(od.run_powershell(script, timeout=60))
    assert r["fehler"] != "fehler", r  # Syntaxfehler oder unlesbare Ausgabe
    assert r["ok"] or r["fehler"] == "nicht_geoeffnet"


def test_ablage():
    with temp_dir() as tmp:
        path = os.path.join(tmp, "outlook.json")
        r = od.parse_output(json.dumps(SAMPLE))
        days = od.split_days(r, datetime(2026, 10, 25), datetime(2026, 10, 27), NOW)
        assert sorted(od.save_days(path, days)) == ["2026-10-25", "2026-10-26"]
        assert od.save_days(path, days) == []  # unverändert: nichts geschrieben
        doc = od.load_day(path, "2026-10-26")
        assert len(doc["termine"]) == 5 and len(doc["mails"]) == 2

        # Gesendete Elemente nicht lesbar: gespeicherte Mails bleiben, Termine werden ersetzt
        broken = dict(r, termine=r["termine"][:1], mails=[], mails_fehler="Ordner fehlt")
        days = od.split_days(broken, datetime(2026, 10, 26), datetime(2026, 10, 27), NOW)
        od.save_days(path, days)
        doc = od.load_day(path, "2026-10-26")
        assert len(doc["termine"]) == 1 and len(doc["mails"]) == 2
        # Mails abgeschaltet: ebenso
        days = od.split_days(dict(r, mails=[]), datetime(2026, 10, 26), datetime(2026, 10, 27), NOW,
                             mails=False)
        od.save_days(path, days)
        assert len(od.load_day(path, "2026-10-26")["mails"]) == 2
        assert od.load_day(path, "2026-01-01") is None
        # verschlüsselt: der Betreff steht nicht im Klartext in der Datei
        datastore.unregister(tmp)
        with open(os.path.join(tmp, datastore.DB_NAME), "rb") as f:
            assert b"Firewall" not in f.read()


def test_leser_ohne_outlook_und_mit_beispiel():
    from outlook_reader import OutlookReader, day_entries
    with temp_dir() as tmp:
        ofile, tfile = os.path.join(tmp, "outlook.json"), os.path.join(tmp, "teams_anrufe.json")
        cfg = dict(CONFIG, outlook_days_back=1, teams_calls_enabled=False)
        calls = []

        def runner(script):
            calls.append(script)
            return json.dumps({"ok": False, "fehler": "nicht_geoeffnet"})

        reader = OutlookReader(cfg, ofile, tfile, runner=runner, mic_func=lambda: [])
        reader.step(NOW)
        assert reader.status == od.ERRORS["nicht_geoeffnet"] and reader.health()[0] == "busy"
        assert len(calls) == 1
        reader.step(NOW)  # nicht jede halbe Minute neu
        assert len(calls) == 1

        reader.runner = lambda s: json.dumps(SAMPLE)
        reader.read_now()
        seen = []
        reader.day_read.connect(seen.append)
        reader.step(NOW)
        assert reader.status.startswith("Outlook gelesen") and reader.health()[0] == "ok"
        assert "2026-10-26" in seen
        assert [e["type"] for e in day_entries(cfg, ofile, tfile, "2026-10-26")] == [
            "Teams-Besprechung", "Mail gesendet", "Termin", "Termin"]
        # Abgeschaltet: nichts anzeigen
        assert day_entries(dict(cfg, outlook_enabled=False), ofile, tfile, "2026-10-26") == []
        # Älterer Tag beim Blättern: einmal nachlesen
        reader.want("2026-10-01")
        reader.want("2026-10-01")
        assert reader._wanted == ["2026-10-01"]
        reader.stop()
        assert reader.stopped and not reader.alive()


def test_zeile_regeln_und_ki():
    """Neue Einträge: Zeile, Typ-Text, Regeln ohne KI und KI-Eingabe."""
    import ai_classifier
    import rules
    import teams_calls
    from timeline_only import row_kind, type_label

    r = od.parse_output(json.dumps(SAMPLE))
    entries = od.day_entries(od.split_days(r, datetime(2026, 10, 26), datetime(2026, 10, 27), NOW)
                             ["2026-10-26"], CONFIG)
    call = teams_calls.call_entries([{"start": "2026-10-26 14:00:00", "end": "2026-10-26 14:20:00",
                                      "source": "mikrofon", "app": "Teams"}])[0]
    assert [row_kind(e) for e in entries] == ["outlook"] * 4
    assert row_kind(call) == "call" and type_label(call) == "Teams-Anruf"
    assert type_label(entries[1]) == "Mail gesendet"

    blocks = rules.classify(entries + [call], [], rules.default_rules(), min_minutes=1)
    cats = [(b["start"][11:16], b["category"]) for b in blocks]
    assert ("09:00", "Beratung / Abstimmung") in cats and ("14:00", "Telefonsupport") in cats
    assert ("10:15", "E-Mail / Kommunikation") in cats

    text = ai_classifier.build_day_text(entries + [call])
    head, outlook = text.split("\n\nTermine und gesendete Mails aus Outlook")
    assert "14:00-14:20 | Teams-Anruf" in head and "anruf |" not in head
    assert "09:00-10:00 | Teams-Besprechung | Abstimmung Firewall" in outlook
    assert "Teilnehmer: kunde-nord.de" in outlook
    # Ohne Outlook-Einträge bleibt der Text wie bisher
    assert "Outlook" not in ai_classifier.build_day_text([call])
