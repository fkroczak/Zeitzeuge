"""Prüfung bei Feierabend (day_checks.py, ohne Qt)."""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import booking_rate as br  # noqa: E402
import day_checks as dc  # noqa: E402

D = "2026-10-19"


def t(hm):
    return datetime.strptime(f"{D} {hm}", "%Y-%m-%d %H:%M")


def span(a, b):
    return (t(a), t(b))


def booking(a, b, customer="Kunde", ticket="TCK1"):
    return {"start": f"{D} {a}:00", "end": f"{D} {b}:00", "customer": customer, "ticket": ticket}


def kinds(findings):
    return [f.kind for f in findings]


def test_pause_ok():
    # 8:00–12:00, 30 min Pause, 12:30–16:30 = 8 h Arbeit
    assert dc.pause_findings([span("08:00", "12:00"), span("12:30", "16:30")]) == []
    # bis 6 h braucht es keine Pause
    assert dc.pause_findings([span("08:00", "14:00")]) == []


def test_pause_missing_over_six_hours():
    found = dc.pause_findings([span("08:00", "14:30")])
    assert kinds(found) == ["pause"] and "nötig 30 min" in found[0].text, found


def test_short_breaks_do_not_count():
    # zwei 10-Minuten-Pausen sind keine Ruhepause (Blöcke ab 15 Minuten)
    found = dc.pause_findings([span("08:00", "10:00"), span("10:10", "13:00"), span("13:10", "16:00")])
    assert kinds(found) == ["pause"], found
    # zwei 15-Minuten-Pausen reichen
    assert dc.pause_findings([span("08:00", "10:00"), span("10:15", "13:00"),
                              span("13:15", "16:00")]) == []


def test_pause_over_nine_hours_needs_45():
    found = dc.pause_findings([span("07:00", "12:00"), span("12:30", "17:30")])  # 10 h, 30 min Pause
    assert kinds(found) == ["pause"] and "nötig 45 min" in found[0].text, found
    assert dc.pause_findings([span("07:00", "12:00"), span("12:45", "17:45")]) == []


def test_more_than_six_hours_in_a_row():
    # Pause insgesamt reicht (30 min), aber erst nach 6:30 h am Stück
    found = dc.pause_findings([span("07:00", "13:30"), span("14:00", "16:00")])
    assert kinds(found) == ["pause"] and "am Stück" in found[0].text, found


def test_pc_active_but_stamped_out():
    personal = [span("08:00", "16:00")]
    pc = [span("07:58", "08:30"), span("16:05", "16:20"), span("16:22", "16:40")]
    found = dc.pc_outside_findings(personal, pc, min_minutes=10)
    assert kinds(found) == ["pc_outside"], found
    assert "16:05" in found[0].text and "16:40" in found[0].text and "ausgestempelt" in found[0].text
    # an einem Tag ohne Stempelung (frei) nichts melden
    assert dc.pc_outside_findings([], pc) == []


def test_booking_outside_personal_time():
    personal = [span("08:00", "12:00"), span("12:30", "16:00")]
    bookings = [booking("08:00", "12:00"), booking("12:00", "12:30", "Mittag GmbH"),
                booking("15:30", "16:03")]  # 3 min drüber: Toleranz 5 min
    found = dc.booking_outside_findings(personal, bookings, min_minutes=5)
    assert kinds(found) == ["booking_outside"] and "Mittag GmbH" in found[0].text, found


def test_overlapping_bookings():
    bookings = [booking("08:00", "09:00"), booking("08:45", "10:00"), booking("10:00", "11:00")]
    found = dc.overlap_findings(bookings)
    assert len(found) == 1 and "15 min" in found[0].text, found


def test_rate_below_target():
    rate = br.DayRate(D, personal_seconds=8 * 3600, booked_seconds=6 * 3600, m42_read=True)
    assert kinds(dc.rate_finding(rate, 80)) == ["rate"]
    assert dc.rate_finding(rate, 75) == []
    assert dc.rate_finding(br.DayRate(D, personal_seconds=8 * 3600), 80) == []  # nicht gelesen


def test_check_day_without_itm_skips_stamp_checks():
    personal = [span("08:00", "17:00")]  # Arbeitszeit aus den Einstellungen, keine Pause
    found = dc.check_day(personal, [span("18:00", "19:00")], [booking("17:00", "18:00")],
                         from_itm=False)
    assert found == []
    found = dc.check_day(personal, [span("18:00", "19:00")], [booking("17:00", "18:00")],
                         from_itm=True)
    assert set(kinds(found)) == {"pause", "pc_outside", "booking_outside"}
    assert [f.start for f in found] == sorted(f.start for f in found)


def test_after_hours():
    spans = [span("08:00", "12:00")]
    assert not dc.after_hours(t("12:30"), spans, running=True)
    # ausgestempelt zur Mittagspause: mit Plan bis 17:00 noch kein Feierabend
    assert not dc.after_hours(t("12:30"), spans, False, planned_end=t("17:00"))
    assert dc.after_hours(t("17:00"), spans, False, planned_end=t("17:00"))
    # ohne Plan: eine Stunde nach dem Ausstempeln
    assert not dc.after_hours(t("12:30"), spans, False)
    assert dc.after_hours(t("13:00"), spans, False)
    # später ausgestempelt als geplant: gleich danach
    late = [span("08:00", "18:00")]
    assert dc.after_hours(t("18:01"), late, False, planned_end=t("17:00"))
    assert not dc.after_hours(t("12:00"), [], False)
