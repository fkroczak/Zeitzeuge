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
