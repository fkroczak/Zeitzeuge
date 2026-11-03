"""Nachfragen ohne Doppelte (prompt_topics.py, journal.py): Themen und Wiedererkennen."""
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("ZEITZEUGE_DATA", tempfile.mkdtemp())

from prompt_topics import answer_span, build_topics, customer_key, matches_span  # noqa: E402

D = "2026-10-21 "


def e(start, end, kind, who, **extra):
    return {"start": D + start + ":00", "end": D + end + ":00", "type": kind, "customer_name": who,
            "details": "", **extra}


VPN = e("09:00", "10:05", "VPN-Verbindung", "Kanzlei Schmidt - SSL VPN")
RDP = e("09:02", "09:58", "RDP-Verbindung", "Kanzlei Schmidt - DC01")
CALL = e("10:10", "10:14", "Telefonat", "Kanzlei Schmidt (0251 123456)", direction="Eingehend")
OTHER = e("09:30", "09:40", "Telefonat", "Praxis Weber (0521 987654)", direction="Ausgehend")
PC = e("09:05", "09:55", "PC: Fernwartung", "DC01", pc_block=True, app="mstsc.exe", category="Fernwartung")


def test_customer_key_normalises_rdm_and_phone_names():
    assert customer_key(VPN) == customer_key(RDP) == customer_key(CALL) == "kanzlei schmidt"
    assert customer_key(e("08:00", "08:10", "TeamViewer", "TeamViewer 1 123 456 789",
                          tv_id="1123456789")) == ""
    assert customer_key(e("08:00", "08:10", "Telefonat", "0171 5550123")) == ""


def test_same_customer_same_time_is_one_topic():
    # VPN, RDP und Telefonat danach (6 min Abstand): eine Nachfrage statt drei
    topics = build_topics([VPN, RDP, CALL])
    assert len(topics) == 1, topics
    t = topics[0]
    assert t["topic"] and len(t["parts"]) == 3
    assert t["start"] == VPN["start"] and t["end"] == CALL["end"]
    assert t["type"] == "VPN-Verbindung"  # längster Teil gibt Typ und Kunde vor


def test_other_customer_at_same_time_stays_separate():
    topics = build_topics([VPN, RDP, OTHER])
    assert len(topics) == 2
    assert {customer_key(t) for t in topics} == {"kanzlei schmidt", "praxis weber"}


def test_pc_block_is_evidence_for_the_connection():
    # Fenster „DC01“ (Kunde aus dem Fenstertitel) gehört zur RDM-Verbindung „Kanzlei Schmidt - DC01“
    topics = build_topics([RDP, PC])
    assert len(topics) == 1 and topics[0]["type"] == "RDP-Verbindung"


def test_pc_block_alone_is_its_own_topic():
    topics = build_topics([e("13:00", "13:40", "PC: Cloud-/M365-Administration", "", pc_block=True,
                             app="msedge.exe", category="Cloud-/M365-Administration")])
    assert len(topics) == 1 and topics[0]["pc_block"]


def test_far_apart_same_customer_is_asked_twice():
    later = e("15:00", "15:30", "RDP-Verbindung", "Kanzlei Schmidt - DC01")
    assert len(build_topics([RDP, later])) == 2


def test_span_recognises_changed_entries():
    span = answer_span(build_topics([VPN, RDP])[0])
    # Logs kommen nach: Start 1 min früher, anderer Name derselben Kanzlei
    changed = e("08:59", "10:05", "VPN-Verbindung", "Kanzlei Schmidt - SSL VPN 2")
    assert matches_span(changed, span)
    assert not matches_span(OTHER, span), "anderer Kunde zur selben Zeit bleibt offen"
    assert not matches_span(e("14:00", "14:30", "RDP-Verbindung", "Kanzlei Schmidt - DC01"), span)


def test_journal_answered_topic_is_not_asked_again_even_if_shorter():
    import journal
    folder = tempfile.mkdtemp()
    os.environ["ZEITZEUGE_DATA"] = folder
    j = journal.Journal(folder)
    now = datetime(2026, 10, 21, 18, 0)
    topic = build_topics([VPN, RDP])[0]
    assert j.open_items([VPN, RDP], "2026-10-21", min_minutes=1, now=now) == [VPN, RDP]
    # Eingetragen wird nur 09:00–09:20 (ein Drittel), gemerkt wird das ganze Thema
    j.add({"start": D + "09:00:00", "end": D + "09:20:00", "customer": "Kanzlei Schmidt",
           "category": "Fernwartung", "text": "x", "answered": answer_span(topic)})
    assert j.open_items([VPN, RDP], "2026-10-21", min_minutes=1, now=now) == []
    # Telefonat mit einer anderen Kanzlei zur gleichen Zeit bleibt offen
    assert j.open_items([OTHER], "2026-10-21", min_minutes=1, now=now) == [OTHER]


def test_journal_ignore_topic_covers_parts_and_changed_entries():
    import journal
    folder = tempfile.mkdtemp()
    j = journal.Journal(folder)
    topic = build_topics([VPN, RDP])[0]
    j.ignore(topic)
    assert j.is_ignored(VPN) and j.is_ignored(RDP) and j.is_ignored(topic)
    assert j.is_ignored(e("08:59", "10:04", "VPN-Verbindung", "Kanzlei Schmidt - SSL VPN"))
    assert not j.is_ignored(OTHER)
