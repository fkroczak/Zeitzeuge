"""Fenster-Filter (Black-/Whitelist) und robustes Schreiben im Aktivitätsprotokoll.

foreground_window und idle_seconds werden ersetzt, damit der Test überall läuft.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import activity_tracker as at  # noqa: E402

window = {"info": None, "idle": 0}


@pytest.fixture(autouse=True)
def fake_window(monkeypatch):
    """Vordergrundfenster und Leerlauf vortäuschen; nach dem Test wieder die echten Funktionen."""
    window.update(info=None, idle=0)
    monkeypatch.setattr(at, "foreground_window", lambda: window["info"])
    monkeypatch.setattr(at, "idle_seconds", lambda: window["idle"])


T0 = datetime(2026, 10, 22, 9, 0, 0)


def run(tracker, steps):
    """steps: [(Sekunden ab T0, (app, titel) oder None oder Exception)] -> gespeicherte Abschnitte."""
    for sec, info in steps:
        window["info"] = info
        if isinstance(info, Exception):
            def boom(err=info):
                raise err
            at.foreground_window = boom
        else:
            at.foreground_window = lambda: window["info"]
        tracker.sample(T0 + timedelta(seconds=sec))
    at.foreground_window = lambda: window["info"]
    tracker.stop()
    return [(s["app"], s["title"], s["start"][11:], s["end"][11:])
            for s in at.read_segments(tracker.folder, "2026-10-22")]


STEPS = [
    (0, ("outlook.exe", "Posteingang")),
    (60, ("KeePass.exe", "Datenbank.kdbx - KeePass")),
    (120, ("steam.exe", "Spiel")),
    (180, ("chrome.exe", "Online-Banking - Sparkasse - Google Chrome")),
    (240, ("chrome.exe", "Ticket 4711 - Google Chrome")),
    (300, None),
]


def test_blacklist(check):
    """1. Blacklist (Standard): ignore blendet aus, skip lässt eine Lücke"""
    tr = at.ActivityTracker(tempfile.mkdtemp(), ignore=["KeePass", "Online-Banking"], skip=["steam.exe"])
    got = run(tr, STEPS)
    print("Blacklist:", *got, sep="\n  ")
    check(got == [("outlook.exe", "Posteingang", "09:00:00", "09:01:00"),
                  ("KeePass.exe", "(ausgeblendet)", "09:01:00", "09:02:00"),
                  ("chrome.exe", "(ausgeblendet)", "09:03:00", "09:04:00"),
                  ("chrome.exe", "Ticket 4711 - Google Chrome", "09:04:00", "09:05:00")],
          f"Blacklist falsch: {got}")

    # Alte Aufrufweise (nur ignore) bleibt gültig
    tr = at.ActivityTracker(tempfile.mkdtemp(), idle_limit=300, ignore=["keepass"])
    check(tr.filter("KeePass.exe", "x") == ("KeePass.exe", "(ausgeblendet)"), "ignore alt")


def test_programmname_und_regex(check):
    """2. Programmname mit/ohne .exe, Groß/Klein, Regex"""
    tr = at.ActivityTracker(tempfile.mkdtemp(), skip=["CHROME", "re:^spiel\\b", "re:(kaputt"])
    check(tr.filter("chrome.exe", "x") is None, "Programmname ohne .exe")
    check(tr.filter("game.exe", "Spiel 2") is None, "Regex auf Titel")
    check(tr.filter("game.exe", "Kein Spiel") == ("game.exe", "Kein Spiel"), "Regex ^ falsch")
    check(len(tr.errors) == 1 and tr.errors[0][0] == 3, f"ungültige Regex nicht gemeldet: {tr.errors}")


def test_whitelist_mask(check):
    """3. Whitelist "mask": andere Fenster zählen als (andere)/(nicht erfasst)"""
    tr = at.ActivityTracker(tempfile.mkdtemp(), ignore=["Online-Banking"], skip=["steam"],
                            allow=["outlook.exe", "chrome", "keepass"], mode="whitelist")
    got = run(tr, STEPS + [(310, ("notepad.exe", "Privat.txt")), (370, None)])
    print("Whitelist mask:", *got, sep="\n  ")
    check(got == [("outlook.exe", "Posteingang", "09:00:00", "09:01:00"),
                  ("KeePass.exe", "Datenbank.kdbx - KeePass", "09:01:00", "09:02:00"),
                  ("chrome.exe", "(ausgeblendet)", "09:03:00", "09:04:00"),
                  ("chrome.exe", "Ticket 4711 - Google Chrome", "09:04:00", "09:05:00"),
                  ("(andere)", "(nicht erfasst)", "09:05:10", "09:06:10")],
          f"Whitelist mask falsch: {got}")


def test_whitelist_skip(check):
    """4. Whitelist "skip": andere Fenster werden zur Lücke"""
    tr = at.ActivityTracker(tempfile.mkdtemp(), allow=["outlook"], mode="whitelist",
                            whitelist_other="skip")
    got = run(tr, STEPS)
    check(got == [("outlook.exe", "Posteingang", "09:00:00", "09:01:00")], f"Whitelist skip: {got}")


def test_set_filters_wirkt_sofort(check):
    """5. set_filters wirkt sofort, auch auf das laufende Fenster"""
    tr = at.ActivityTracker(tempfile.mkdtemp())
    window["info"] = ("chrome.exe", "Mein Konto - Bank")
    tr.sample(T0)
    tr.sample(T0 + timedelta(seconds=30))
    tr.set_filters(ignore=["Bank"])
    check(tr.current and tr.current["title"] == "(ausgeblendet)", "set_filters: laufendes Fenster")
    tr.sample(T0 + timedelta(seconds=60))
    check(tr.current["title"] == "(ausgeblendet)" and tr.current["start"] == T0,
          "set_filters: Abschnitt neu begonnen")
    tr.set_filters(skip=["chrome"])
    check(tr.current is None, "set_filters: skip verwirft laufendes Fenster")
    tr.set_filters(mode="unsinn", whitelist_other="egal")
    check(tr.mode == "blacklist" and tr.whitelist_other == "mask", "ungültige Werte")
    check(at.tracking_filters({"tracking_mode": "whitelist"})["mode"] == "whitelist", "tracking_filters")


def test_ausnahme_in_foreground_window(check):
    """6. Ausnahme in foreground_window: kein Absturz, Abschnitt endet"""
    tr = at.ActivityTracker(tempfile.mkdtemp())
    got = run(tr, [(0, ("outlook.exe", "A")), (60, OSError("Zugriff verweigert")),
                   (120, ("outlook.exe", "A")), (180, None)])
    check(got == [("outlook.exe", "A", "09:00:00", "09:01:00"), ("outlook.exe", "A", "09:02:00", "09:03:00")],
          f"Ausnahme in foreground_window: {got}")


def test_schreibfehler_nachholen(check):
    """7. Schreibfehler (Ordner nicht anlegbar): kein Absturz, Zeilen bleiben und werden nachgeholt"""
    base = tempfile.mkdtemp()
    blocker = os.path.join(base, "aktivitaet")
    with open(blocker, "w") as f:
        f.write("ich bin eine Datei, kein Ordner")
    tr = at.ActivityTracker(blocker)
    got = run(tr, [(0, ("outlook.exe", "A")), (60, ("excel.exe", "B")), (120, None)])
    check(got == [], "Schreibfehler: es wurde trotzdem geschrieben?")
    check(len(tr.pending) == 2, f"Schreibfehler: Zeilen verloren ({tr.pending})")
    check(len(tr.segments_for("2026-10-22")) == 2, "ungespeicherte Zeilen fehlen in der Ansicht")
    os.remove(blocker)
    check(tr.flush() and not tr.pending, "Nachholen nach Schreibfehler klappt nicht")
    check(len(at.read_segments(blocker, "2026-10-22")) == 2, "nachgeholte Zeilen fehlen")


def test_kaputte_zeilen_und_haeufigste_programme(check):
    """8. Kaputte Zeilen beim Lesen überspringen, 9. häufigste Programme der letzten 7 Tage"""
    folder = tempfile.mkdtemp()
    with open(os.path.join(folder, "2026-10-22.jsonl"), "w", encoding="utf-8") as f:
        f.write('{"start": "2026-10-22 09:00:00", "end": "2026-10-22 09:30:00", "app": "a.exe", "title": "x"}\n')
        f.write('{"start": "2026-10-22 09:\n')         # halb geschrieben
        f.write('5\n[1, 2]\n{"start": 1}\n')           # falsche Form
        f.write('{"start": "2026-10-22 10:00:00", "end": "2026-10-22 11:00:00", "app": "b.exe", "title": "y"}\n')
    segs = at.read_segments(folder, "2026-10-22")
    check([s["app"] for s in segs] == ["a.exe", "b.exe"], f"kaputte Zeilen: {segs}")
    check(at.read_segments(os.path.join(folder, "fehlt"), "2026-10-22") == [], "fehlender Ordner")

    # 9. Häufigste Programme der letzten 7 Tage (im selben Ordner)
    with open(os.path.join(folder, "2026-10-20.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"start": "2026-10-20 08:00:00", "end": "2026-10-20 10:00:00",
                            "app": "B.EXE", "title": "z"}) + "\n")
        f.write(json.dumps({"start": "2026-10-20 10:00:00", "end": "2026-10-20 12:00:00",
                            "app": "(andere)", "title": "(nicht erfasst)"}) + "\n")
    with open(os.path.join(folder, "2026-10-01.jsonl"), "w", encoding="utf-8") as f:  # zu alt
        f.write(json.dumps({"start": "2026-10-01 08:00:00", "end": "2026-10-01 18:00:00",
                            "app": "alt.exe", "title": "z"}) + "\n")
    top = at.top_apps(folder, days=7, today=datetime(2026, 10, 22, 12))
    check(top == [("b.exe", 3 * 3600), ("a.exe", 1800)], f"top_apps: {top}")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
