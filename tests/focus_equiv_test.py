"""focus_blocks Schritte 2 und 4 (Sprünge zuordnen, kurze Blöcke aufnehmen): neu = alt, bitgleich.

Die alten Verfahren (für jeden Sprung den Rest absuchen; kürzesten suchen, aufnehmen, ganze
Liste neu verbinden) waren quadratisch. Hier stehen sie als Vergleich und werden mit
Zufallsdaten gegen die neuen geprüft."""
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import focus  # noqa: E402
from focus import _absorb, _join_same, _seconds  # noqa: E402


def old_absorb_short(blocks, min_block_seconds, max_gap_seconds):
    while True:
        short = [b for b in blocks if not b.get("keep")
                 and _seconds(b["start"], b["end"]) < min_block_seconds]
        if not short or len(blocks) < 2:
            break
        b = min(short, key=lambda b: _seconds(b["start"], b["end"]))
        i = blocks.index(b)
        candidates = []
        if i > 0 and _seconds(blocks[i - 1]["end"], b["start"]) <= max_gap_seconds:
            candidates.append(blocks[i - 1])
        if i + 1 < len(blocks) and _seconds(b["end"], blocks[i + 1]["start"]) <= max_gap_seconds:
            candidates.append(blocks[i + 1])
        if not candidates:
            if _seconds(b["start"], b["end"]) < 60:
                blocks.pop(i)
            else:
                b["keep"] = True
            continue
        target = max(candidates, key=lambda c: _seconds(c["start"], c["end"]))
        _absorb(target, b)
        blocks.pop(i)
        blocks = _join_same(blocks, max_gap_seconds)
    return blocks


def old_attach_jumps(pieces, jump_seconds, max_gap_seconds):
    for i in range(1, len(pieces)):
        p, prev = pieces[i], pieces[i - 1]
        if p["seconds"] >= jump_seconds or p["key"] == prev["key"]:
            continue
        if _seconds(prev["end"], p["start"]) > max_gap_seconds:
            continue
        nxt = next((pieces[j] for j in range(i + 1, len(pieces))
                    if pieces[j]["seconds"] >= jump_seconds or pieces[j]["key"] == prev["key"]), None)
        returns = (nxt is not None and nxt["key"] == prev["key"]
                   and _seconds(p["end"], nxt["start"]) <= max_gap_seconds)
        same_customer = bool(p["key"][1]) and p["key"][1] == prev["key"][1]
        if returns or same_customer:
            p["key"] = prev["key"]
            p["jump"] = True


def _segments(rng, n, overlap=False):
    t = datetime(2026, 11, 10, 7, 0, 0)
    apps = ["outlook.exe", "teams.exe", "mstsc.exe", "excel.exe"]
    titles = ["Kunde A", "Kunde B", "Kunde C", "Intern", "Ticket 4711", ""]
    out = []
    for _ in range(n):
        length = rng.choice([3, 8, 20, 45, 90, 200, 400, 900])
        e = t + timedelta(seconds=length)
        out.append({"start": f"{t:%Y-%m-%d %H:%M:%S}", "end": f"{e:%Y-%m-%d %H:%M:%S}",
                    "app": rng.choice(apps), "title": rng.choice(titles)})
        gap = rng.choice([0, 1, 5, 30, 200, 400, 1200])
        t = e + timedelta(seconds=gap) - (timedelta(seconds=rng.randint(0, 60)) if overlap else timedelta())
    return out


def _compare(monkeypatch, segments, rules, keywords=None, **kw):
    new = focus.focus_blocks(segments, rules, keywords=keywords, **kw)
    monkeypatch.setattr(focus, "_absorb_short", old_absorb_short)
    monkeypatch.setattr(focus, "_attach_jumps", old_attach_jumps)
    old = focus.focus_blocks(segments, rules, keywords=keywords, **kw)
    monkeypatch.undo()
    assert repr(new) == repr(old)


RULES = [{"field": "title", "match": "Kunde", "category": "Fernwartung", "customer": ""},
         {"field": "app", "match": "outlook", "category": "E-Mail / Kommunikation"}]


def test_same_as_old_random(monkeypatch):
    rng = random.Random(7)
    for i in range(60):
        segs = _segments(rng, rng.randint(0, 120), overlap=i % 3 == 0)
        _compare(monkeypatch, segs, RULES if i % 2 else [])


def test_same_as_old_settings(monkeypatch):
    rng = random.Random(11)
    segs = _segments(rng, 300)
    for kw in ({"jump_seconds": 30}, {"min_block_seconds": 600}, {"max_gap_seconds": 60},
               {"min_block_seconds": 60, "max_gap_seconds": 1000}):
        _compare(monkeypatch, segs, RULES, **kw)


def test_many_small_blocks_fast():
    """3000 kurze Blöcke wechselnder Kunden: früher Sekunden, jetzt Bruchteile."""
    import time
    rng = random.Random(3)
    t = datetime(2026, 11, 10, 7, 0, 0)
    segs = []
    for i in range(3000):
        e = t + timedelta(seconds=rng.randint(3, 15))
        segs.append({"start": f"{t:%Y-%m-%d %H:%M:%S}", "end": f"{e:%Y-%m-%d %H:%M:%S}",
                     "app": "msedge.exe", "title": f"Kunde {rng.randrange(40)} – Dokument"})
        t = e + timedelta(seconds=rng.randint(0, 2))
    rules = [{"field": "title", "match": "re:Kunde (\\d+)", "category": "Fernwartung",
              "customer": "Kunde {1}"}]
    start = time.perf_counter()
    blocks = focus.focus_blocks(segs, rules)
    assert blocks
    assert time.perf_counter() - start < 2.0
