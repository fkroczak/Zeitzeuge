"""timefmt.seconds und merge_segments (Sekunden statt datetime): gleiches Ergebnis wie vorher."""
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import activity_tracker as at  # noqa: E402
import timefmt  # noqa: E402

F = "%Y-%m-%d %H:%M:%S"


def _exact(text):
    d = timefmt.parse(text)
    return float(d.toordinal() * 86400 + d.hour * 3600 + d.minute * 60 + d.second)


def test_seconds_wie_parse():
    rng = random.Random(3)
    for _ in range(20000):
        text = (datetime(1999, 1, 1) + timedelta(seconds=rng.randrange(10 ** 9))).strftime(F)
        assert timefmt.seconds(text) == _exact(text)


def test_seconds_fehler_wie_parse():
    for text in ["2026-13-01 00:00:00", "2026-11-12 24:00:00", "2026-11-12 07:60:00", "2026-02-30 00:00:00",
                 "2026-11-12T07:00:00", "", "x", "2026-11-12 07:00:0x", "２026-11-12 07:00:00",
                 "2026-11-12 7:00:00"]:
        expected = got = None
        try:
            expected = _exact(text)
        except ValueError as e:
            expected = type(e)
        try:
            got = timefmt.seconds(text)
        except ValueError as e:
            got = type(e)
        assert got == expected, text


def _old_merge(segments, min_seconds=30, max_gap=60):
    merged = []
    for s in sorted(segments, key=lambda s: s["start"]):
        if (merged and merged[-1]["app"] == s["app"] and merged[-1]["title"] == s["title"]
                and at._seconds(merged[-1]["end"], s["start"]) <= max_gap):
            merged[-1]["end"] = max(merged[-1]["end"], s["end"])
        else:
            merged.append(dict(s))
    return [m for m in merged if at._seconds(m["start"], m["end"]) >= min_seconds]


def test_merge_segments_wie_vorher():
    rng = random.Random(5)
    for _ in range(1500):
        t = datetime(2026, 3, 29) + timedelta(minutes=rng.randrange(3000))  # auch Zeitumstellung
        segs = []
        for i in range(rng.randrange(60)):  # auch überlappend und rückwärts
            s = t + timedelta(seconds=rng.randrange(-30, 40))
            e = s + timedelta(seconds=rng.randrange(-5, 200))
            segs.append({"start": s.strftime(F), "end": e.strftime(F), "app": rng.choice("ab"),
                         "title": rng.choice("xy"), "n": i})
            t = s
        for min_s, gap in ((30, 60), (5, 15), (0, 0)):
            assert at.merge_segments([dict(x) for x in segs], min_s, gap) == \
                _old_merge([dict(x) for x in segs], min_s, gap)


def test_read_segments_ohne_kopie_bleibt_unveraendert(tmp_path):
    folder = str(tmp_path / "activity")
    os.makedirs(folder)
    import datastore
    store, name = datastore.locate(folder, "row_files")
    row = {"start": "2026-11-10 09:00:00", "end": "2026-11-10 09:05:00", "app": "a.exe", "title": "x"}
    store.append_many(name, [("2026-11-10", row)])
    shared = at.read_segments(folder, "2026-11-10", copy=False)
    assert shared == [row]
    copy = at.read_segments(folder, "2026-11-10")
    copy[0]["title"] = "geändert"
    assert at.read_segments(folder, "2026-11-10", copy=False)[0]["title"] == "x"
