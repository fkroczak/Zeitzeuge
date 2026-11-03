"""PC-Aktivität zu Arbeitsblöcken (focus.py): kurze Sprünge, Pausen, Splitter, Regeln."""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from focus import focus_blocks  # noqa: E402
from rules import default_rules  # noqa: E402

D = "2026-10-21 "


def seg(start, end, app, title=""):
    if len(start) == 5:
        start += ":00"
    if len(end) == 5:
        end += ":00"
    return {"start": D + start, "end": D + end, "app": app, "title": title}


def spans(blocks):
    return [(b["start"][11:16], b["end"][11:16], b["label"]) for b in blocks]


def test_short_jump_back_to_main_activity_is_absorbed():
    # Outlook – 40 s Teams – Outlook: ein Block „Outlook“, Teams als Anteil
    blocks = focus_blocks([seg("09:00", "09:10", "outlook.exe"),
                           seg("09:10", "09:10:40", "teams.exe"),
                           seg("09:10:40", "09:25", "outlook.exe")])
    assert spans(blocks) == [("09:00", "09:25", "Outlook")], spans(blocks)
    parts = dict(blocks[0]["parts"])
    assert parts["Teams"] == 40 and blocks[0]["switches"] == 2
    assert "Outlook 97 %" in blocks[0]["details"], blocks[0]["details"]


def test_long_switch_starts_new_block():
    blocks = focus_blocks([seg("09:00", "09:20", "outlook.exe"),
                           seg("09:20", "09:45", "excel.exe")])
    assert spans(blocks) == [("09:00", "09:20", "Outlook"), ("09:20", "09:45", "Excel")]


def test_pause_splits_blocks():
    blocks = focus_blocks([seg("09:00", "09:20", "outlook.exe"),
                           seg("09:40", "10:00", "outlook.exe")])
    assert len(blocks) == 2


def test_short_block_is_merged_into_neighbour():
    # 2 min Chrome zwischen zwei langen, verschiedenen Blöcken: kein Splitter
    blocks = focus_blocks([seg("09:00", "09:20", "outlook.exe"),
                           seg("09:20", "09:22", "chrome.exe"),
                           seg("09:22", "09:50", "excel.exe")])
    assert len(blocks) == 2, spans(blocks)
    assert all(b["end"] > b["start"] for b in blocks)
    covered = sum(p[1] for b in blocks for p in b["parts"])
    assert covered == 50 * 60  # keine Zeit geht verloren


def test_rules_group_windows_by_activity_and_customer():
    # Remotedesktop mit Servername: Kunde aus dem Fenstertitel, kurzer Browser-Sprung gehört dazu
    blocks = focus_blocks([seg("10:00", "10:15", "mstsc.exe", "DC01 - Remotedesktopverbindung"),
                           seg("10:15", "10:16", "chrome.exe", "Doku - Chrome"),
                           seg("10:16", "10:40", "mstsc.exe", "DC01 - Remotedesktopverbindung")],
                          default_rules())
    assert spans(blocks) == [("10:00", "10:40", "DC01 · Fernwartung")], spans(blocks)
    assert blocks[0]["category"] == "Fernwartung" and blocks[0]["customer_name"] == "DC01"


def test_mail_programs_share_activity():
    # Outlook und Thunderbird gehören zur selben Tätigkeit (Regel E-Mail)
    blocks = focus_blocks([seg("08:00", "08:10", "outlook.exe"),
                           seg("08:10", "08:20", "thunderbird.exe")], default_rules())
    assert spans(blocks) == [("08:00", "08:20", "E-Mail / Kommunikation")]


def test_flickering_day_becomes_few_blocks_and_keeps_time():
    rnd = random.Random(4)
    apps = ["outlook.exe", "teams.exe", "chrome.exe", "excel.exe"]
    segments, minute = [], 8 * 60
    while minute < 17 * 60:
        length = rnd.choice([0.3, 0.5, 1, 1, 2, 6, 12])
        start = f"{int(minute // 60):02d}:{int(minute % 60):02d}:{int(minute * 60 % 60):02d}"
        minute += length
        end = f"{int(minute // 60):02d}:{int(minute % 60):02d}:{int(minute * 60 % 60):02d}"
        segments.append(seg(start, end, rnd.choice(apps)))
    blocks = focus_blocks(segments)
    assert len(blocks) <= len(segments) / 4, (len(blocks), len(segments))
    assert all(b["end"] >= b["start"] for b in blocks)
    for a, b in zip(blocks, blocks[1:]):
        assert a["end"] <= b["start"], "Blöcke überschneiden sich"
    assert sum(p[1] for b in blocks for p in b["parts"]) == sum(
        (int(s["end"][11:13]) * 3600 + int(s["end"][14:16]) * 60 + int(s["end"][17:19]))
        - (int(s["start"][11:13]) * 3600 + int(s["start"][14:16]) * 60 + int(s["start"][17:19]))
        for s in segments)


def test_empty():
    assert focus_blocks([]) == []
