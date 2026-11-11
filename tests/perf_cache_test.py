"""Beschleunigungen beim Zeichnen: schnelles Zeitformat und gemerkte Fenster-Abschnitte."""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import activity_tracker as at  # noqa: E402
import datastore  # noqa: E402
import timefmt  # noqa: E402

D = "2026-10-22"


@pytest.mark.parametrize("text", ["2026-10-22 09:05:07", "2024-02-29 23:59:59", "2026-01-01 00:00:00",
                                  "２026-10-22 09:05:07"])  # Unicode-Ziffern: strptime nimmt sie auch
def test_zeitformat_gleich_wie_strptime(text):
    assert timefmt.parse(text) == datetime.strptime(text, timefmt.TIME_FMT)


@pytest.mark.parametrize("bad", ["2026-10-22T09:05:07", "2026-10-22", "2026-13-01 00:00:00",
                                 "2026-10-22 09:05", "2026-10-22 09:05:07.5", "", "2026-10-22 0a:05:07"])
def test_zeitformat_fehler_wie_strptime(bad):
    with pytest.raises(ValueError):
        datetime.strptime(bad, timefmt.TIME_FMT)
    with pytest.raises(ValueError):
        timefmt.parse(bad)


def seg(start, end, app="a.exe", title="x"):
    return {"start": f"{D} {start}", "end": f"{D} {end}", "app": app, "title": title}


def test_abschnitte_gemerkt_und_nach_schreiben_neu():
    folder = os.path.join(tempfile.mkdtemp(), "aktivitaet")
    store = datastore.register(datastore.Store(os.path.join(os.path.dirname(folder), "zeitzeuge.db")).unlock())
    try:
        store.append("aktivitaet", D, seg("09:00:00", "09:10:00"))
        first = at.read_segments(folder, D)
        assert len(first) == 1
        first[0]["title"] = "geändert"  # Aufrufer ändern ihre Kopie, nicht den Zwischenspeicher
        assert at.read_segments(folder, D)[0]["title"] == "x"

        calls = []
        real = store.rows
        store.rows = lambda *a: calls.append(a) or real(*a)
        at.read_segments(folder, D)
        assert calls == [], "unveränderter Tag wird nicht neu gelesen"

        store.append("aktivitaet", D, seg("09:10:00", "09:20:00", "b.exe"))
        assert [s["app"] for s in at.read_segments(folder, D)] == ["a.exe", "b.exe"]
        assert len(calls) == 1

        # Ein anderer Prozess schreibt in dieselbe Datei: auch das wird erkannt
        other = sqlite3.connect(store.path)
        other.execute("INSERT INTO meta (key, value) VALUES ('fremd', '1')")
        other.commit()
        other.close()
        at.read_segments(folder, D)
        assert len(calls) == 2
    finally:
        store.rows = real
        datastore.unregister(os.path.dirname(folder))


def test_zusammenfassen_unveraendert():
    segs = [seg("09:00:00", "09:00:40"), seg("09:01:30", "09:02:00"), seg("09:05:00", "09:05:10", "b.exe")]
    merged = at.merge_segments(segs, min_seconds=30, max_gap=60)
    assert [(m["app"], m["start"][11:], m["end"][11:]) for m in merged] == [("a.exe", "09:00:00", "09:02:00")]


@pytest.mark.parametrize("when", [datetime(2026, 10, 22, 9, 5, 7), datetime(2026, 1, 1, 0, 0, 0, 999999),
                                  datetime(999, 5, 6, 7, 8, 9)])
def test_zeit_schreiben_gleich_wie_strftime(when):
    assert timefmt.fmt(when) == when.strftime(timefmt.TIME_FMT)


def test_focus_blocks_gleich_mit_wiederholten_fenstern():
    # Gleiche Fenster (Programm + Titel) bekommen dieselbe Tätigkeit, auch über den Zwischenspeicher
    import focus
    segs = [seg(f"09:{m:02d}:00", f"09:{m:02d}:50", "teams.exe" if m % 3 == 1 else "outlook.exe", f"T{m % 2}")
            for m in range(30)]
    rules = [{"name": "Mail", "field": "app", "match": "outlook", "category": "E-Mail", "customer": "",
              "enabled": True}]
    blocks = focus.focus_blocks(segs, rules)
    assert [b["category"] for b in blocks] == ["E-Mail"], "Teams-Sprünge zählen zu Outlook"
    assert sum(len(b["windows"]) for b in blocks) == len(segs)


def test_spuren_vom_pc_zwischenspeicher():
    import local_sources as ls
    state = {"locked": False}
    reader = ls.LocalReader({"recent_files_dirs": [], "browser_paths": []}, None, funcs={
        "locked": lambda: state["locked"], "processes": lambda: [], "titles": lambda: {},
        "events": lambda: [], "wlan": lambda: "", "history": lambda path, since: [], "threaded": False})
    t = datetime(2026, 11, 3, 9, 0, 0)
    reader.sample(now=t)
    assert reader.entries() == []
    state["locked"] = True
    for i in range(1, 5):
        reader.sample(now=t.replace(second=0, minute=i))
    first = reader.entries()
    assert [e["type"] for e in first] == [ls.LOCKED], "Änderung kommt trotz Zwischenspeicher an"
    first[0]["customer_name"] = "geändert"  # Kopie, nicht der Zwischenspeicher
    assert reader.entries()[0]["customer_name"] == "gesperrt"
    reader.config["pcstate_enabled"] = False
    assert reader.entries() == [], "Schalter wirkt sofort"


def test_vergangene_tage_verdichten_und_loeschen():
    import retention
    folder = os.path.join(tempfile.mkdtemp(), "aktivitaet")
    store = datastore.register(datastore.Store(os.path.join(os.path.dirname(folder), "zeitzeuge.db")).unlock())
    try:
        store.append_many("aktivitaet", [(D, seg(f"09:0{i}:00", f"09:0{i}:30", title=f"t{i}")) for i in range(5)])
        store.append("aktivitaet", "2026-10-23", {**seg("08:00:00", "08:10:00"),
                                                  "start": "2026-10-23 08:00:00", "end": "2026-10-23 08:10:00"})
        before = at.read_segments(folder, D)
        assert at.compact_days(folder, today="2026-10-23") == 1, "heute wird nicht verdichtet"
        assert store.row_count("aktivitaet", D) == 0 and store.days("aktivitaet") == [D]
        assert store.row_count("aktivitaet", "2026-10-23") == 1
        assert at.read_segments(folder, D) == before, "gleiche Abschnitte, gleiche Reihenfolge"
        # Kommt danach noch eine Zeile für den Tag, wird sie gelesen und beim nächsten Mal angehängt
        store.append("aktivitaet", D, seg("10:00:00", "10:05:00", "late.exe"))
        assert [s["app"] for s in at.read_segments(folder, D)][-1] == "late.exe"
        at.compact_days(folder, today="2026-10-23")
        assert len(at.read_segments(folder, D)) == 6 and store.row_count("aktivitaet", D) == 0
        # Löschen nach Aufbewahrung: verdichtete Tage zählen und verschwinden
        info = retention.affected(store, "aktivitaet", None, "2026-10-23")
        assert info["days"] == [D] and info["rows"] == 6, info
        total, _other = retention.purge(store, "aktivitaet", None, "2026-10-23")
        assert total == 6 and store.days("aktivitaet") == [] and at.read_segments(folder, D) == []
        assert store.row_count("aktivitaet", "2026-10-23") == 1, "Tag ab Stichtag bleibt"
    finally:
        datastore.unregister(os.path.dirname(folder))


def test_spuren_vom_pc_je_tag_gespeichert():
    import local_sources as ls
    tmp = tempfile.mkdtemp()
    archive = os.path.join(tmp, "lokal_spuren.json")
    store = datastore.register(datastore.Store(os.path.join(tmp, "zeitzeuge.db")).unlock())
    try:
        old = {"files": [{"start": "2026-11-01 09:00:00", "end": "2026-11-01 09:00:00", "name": "a.docx"},
                         {"start": "2026-11-02 09:00:00", "end": "2026-11-02 09:00:00", "name": "b.docx"}]}
        store.put("lokal_spuren", "", old)  # früheres Format: ein Dokument für alle Tage
        funcs = {"locked": lambda: state["locked"], "processes": lambda: [], "titles": lambda: {},
                 "events": lambda: [], "wlan": lambda: "", "history": lambda path, since: [], "threaded": False}
        state = {"locked": False}
        reader = ls.LocalReader({"recent_files_dirs": [], "browser_paths": []}, archive, funcs=funcs)
        assert len(reader.entries()) == 2
        assert store.days("lokal_spuren") == ["2026-11-01", "2026-11-02"], "auf Tage verteilt, altes weg"
        writes = []
        real = store.put_many
        store.put_many = lambda name, by_day, delete=(): writes.append(sorted(by_day)) or real(name, by_day, delete)
        state["locked"] = True
        t = datetime(2026, 11, 3, 9, 0, 0)
        for i in range(4):
            reader.sample(now=t.replace(minute=i))
        assert writes and all(w == ["2026-11-03"] for w in writes), "nur der geänderte Tag"
        store.put_many = real
        again = ls.LocalReader({}, archive, funcs=funcs)
        assert sorted(e["type"] for e in again.entries()) == sorted([ls.LOCKED, ls.FILE_TYPE, ls.FILE_TYPE])
        assert again.prune("2026-11-02") == 1 and "2026-11-01" not in store.days("lokal_spuren")
    finally:
        datastore.unregister(tmp)


def test_regeln_vorfilter_gleiches_ergebnis():
    # Regeln, die bei Fenstern nie passen können (nur Typ/Kunde/Details), werden vorab
    # weggelassen: für jedes Fenster dieselbe erste passende Regel wie ohne Vorfilter
    import focus
    import rules
    compiled = rules._compile_rules(rules.default_rules() + [
        {"name": "Typ PC", "field": "type", "match": "PC", "category": "Alles am PC", "enabled": False},
        {"name": "und", "field": "app", "match": "excel", "category": "Tabellen", "enabled": True,
         "and": [{"field": "details", "match": "re:^$"}]},
        {"name": "nie", "field": "app", "match": "word", "category": "nie", "enabled": True,
         "and": [{"field": "customer", "match": "x"}]}])
    kept = rules.drop_impossible(compiled, focus.PC_CONSTANTS)
    assert len(kept) < len(compiled)
    assert all(c[1]["name"] != "nie" for c in kept), "Bedingung auf leeren Kunden passt nie"
    windows = [("OUTLOOK.EXE", "Posteingang"), ("mstsc.exe", "srv01 - Remotedesktopverbindung"),
               ("EXCEL.EXE", "Liste.xlsx"), ("WINWORD.EXE", "x"), ("ms-teams.exe", "Chat"),
               ("msedge.exe", "portal.azure.com"), ("devolutions.exe", "Passwort"), ("a.exe", "")]
    for app, title in windows:
        entry = {"app": app, "customer_name": title, "type": "PC", "details": ""}
        assert rules.match_entry(entry, kept, is_pc=True) == rules.match_entry(entry, compiled, is_pc=True)
    every = rules._compile_rules([{"name": "PC", "field": "type", "match": "PC", "category": "PC",
                                   "enabled": True}])
    assert rules.drop_impossible(every, focus.PC_CONSTANTS) == every, "passt immer: bleibt"


def test_stichwort_suche_gleiches_ergebnis():
    # Vorprüfung mit „in“ und fold ohne translate bei ASCII: gleiches Ergebnis wie vorher
    import customers

    def old_fold(text):
        return " ".join(str(text or "").casefold().translate(customers._UMLAUT).split())

    def old_keyword(idx, text):
        folded = old_fold(text)
        for path, _last, last_rx, name in idx.paths:
            if path in folded.replace("/", "\\") or (last_rx and last_rx.search(folded)):
                return name
        return next((name for rx, name, _w in idx.words if rx.search(folded)), "")

    idx = customers.Index([
        {"name": "Huber", "traces": [{"kind": "word", "value": "Huber"}]},
        {"name": "Huber Bau", "traces": [{"kind": "word", "value": "Huber Bau"}]},
        {"name": "Müller", "traces": [{"kind": "word", "value": "Müller"},
                                      {"kind": "path", "value": r"D:\Kunden\Mueller"}]},
        {"name": "Punkt", "traces": [{"kind": "word", "value": ".punkt"}]}])
    cases = {"Angebot Huber Bau GmbH": "Huber Bau", "Schuber Bau": "", "Huber-Server": "Huber",
             "Mail von MÜLLER": "Müller", "d:/kunden/mueller/x.docx": "Müller",
             "Datei Mueller.txt": "Müller", "abc.punkt": "Punkt", "Straße  ÄÖÜ": "", "nichts": "", "": ""}
    for text, want in cases.items():
        assert customers.fold(text) == old_fold(text), text
        assert idx.keyword(text) == old_keyword(idx, text) == want, text


def test_utc_umrechnung_je_tag_wie_einzeln():
    # Versatz je Tag gemerkt; an Tagen mit Umstellung einzeln gerechnet: immer wie exakt
    import time
    from datetime import timedelta
    import log_parsers as lp
    old = os.environ.get("TZ")
    # Windows hat kein time.tzset: dort nur die Zeitzone des Rechners prüfen
    zones = ("Europe/Berlin", "America/New_York", "Australia/Lord_Howe") if hasattr(time, "tzset") else (None,)
    try:
        for tz in zones:
            if tz:
                os.environ["TZ"] = tz
                time.tzset()
            lp._offsets.clear()
            t = datetime(2026, 1, 1)
            while t < datetime(2027, 1, 1):
                assert lp.utc_to_local(t) == lp._utc_to_local_exact(t), (tz, t)
                t += timedelta(minutes=37, seconds=11)
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        if hasattr(time, "tzset"):
            time.tzset()
        lp._offsets.clear()


def test_ticket_vorschlaege_mit_vorauswahl_gleich():
    # Fensterstücke außerhalb des Zeitraums werden am Text übersprungen: gleiches Ergebnis wie
    # ohne Vorauswahl (Grenzen mit Bruchteilen von Sekunden: ohne Vorauswahl)
    import random
    from datetime import timedelta
    import tickets
    rng = random.Random(3)
    base = datetime(2026, 11, 10, 7)
    segs = []
    for i in range(600):
        s = base + timedelta(seconds=rng.randint(0, 36000))
        e = s + timedelta(seconds=rng.randint(0, 900))
        segs.append({"start": s.strftime("%Y-%m-%d %H:%M:%S"), "end": e.strftime("%Y-%m-%d %H:%M:%S"),
                     "title": f"TCK{rng.randint(1, 30):010d} – Mail", "app": "Outlook"})
    segs += [{"start": "2026-11-10 9:00:00", "end": "2026-11-10 09:30:00", "title": "TCK0000000099"},
             {"start": "２026-11-10 09:00:00", "end": "2026-11-10 09:30:00", "title": "TCK0000000098"},
             {"start": None, "end": "x", "title": "TCK0000000097"}]

    def plain(start, end):  # Vorauswahl abgeschaltet: Grenzen mit Bruchteil, gleich danach zurück
        return tickets.suggest(start - timedelta(microseconds=1), end, segs)

    for start, minutes in ((datetime(2026, 11, 10, 9), 30), (datetime(2026, 11, 10, 12, 15), 5),
                           (datetime(2026, 11, 10, 17, 59, 59), 60)):
        end = start + timedelta(minutes=minutes)
        fast = tickets.suggest(start, end, segs)
        slow = plain(start, end)
        assert [t["ticket"] for t in fast] == [t["ticket"] for t in slow]
        assert all(abs(a["seconds"] - b["seconds"]) <= 1e-3 for a, b in zip(fast, slow))
