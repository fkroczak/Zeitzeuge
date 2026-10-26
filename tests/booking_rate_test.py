"""Buchungsquote: Stufen, Quote je Tag, 7-Tage-Wert (booking_rate.py, ohne Qt)."""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import booking_rate as br  # noqa: E402


def dt(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M")


def b(day, start, end):
    return {"start": f"{day} {start}:00", "end": f"{day} {end}:00"}


def test_levels():
    assert br.level(None) == "none"
    assert br.level(49.9) == "low"
    assert br.level(50) == "mid"
    assert br.level(79.9) == "mid"
    assert br.level(80) == "ok"
    assert br.level(100) == "ok"
    assert br.level(100.1) == "over"
    # Ziel einstellbar: gelb bis unter das Ziel
    assert br.level(85, target=90) == "mid"
    assert br.level(90, target=90) == "ok"
    # Ziel unter 50: rot nur bis zum Ziel
    assert br.level(45, target=40) == "ok"


def test_level_text_has_symbol_and_words():
    for lvl in ("low", "mid", "ok", "over", "none"):
        text = br.level_text(lvl)
        assert any(c.isalpha() for c in text) and not text[0].isalpha(), text
    assert "80 %" in br.level_text("mid")
    assert br.percent_text(None) == "–"
    assert br.percent_text(72.4) == "72 %"


def test_day_rate_merges_overlapping_bookings():
    day = "2026-10-19"
    now = dt("2026-10-26 12:00")
    spans = [(dt(f"{day} 08:00"), dt(f"{day} 12:00")), (dt(f"{day} 12:30"), dt(f"{day} 16:30"))]
    bookings = [b(day, "08:00", "10:00"), b(day, "09:00", "11:00"),  # 1 h doppelt
                b(day, "12:30", "16:00")]
    rate = br.day_rate(day, spans, bookings, now, from_itm=True)
    assert rate.personal_seconds == 8 * 3600
    assert rate.booked_seconds == 6.5 * 3600
    assert round(rate.percent, 2) == 81.25
    # Lücken: 11:00–12:00 und 16:00–16:30
    assert [(a.strftime("%H:%M"), e.strftime("%H:%M")) for a, e in rate.gaps] == \
        [("11:00", "12:00"), ("16:00", "16:30")]
    assert rate.gap_seconds == 1.5 * 3600


def test_itm_gewertet_wins_when_stamped_out():
    day = "2026-10-19"
    now = dt("2026-10-26 12:00")
    spans = [(dt(f"{day} 08:00"), dt(f"{day} 17:00"))]
    rate = br.day_rate(day, spans, [b(day, "08:00", "16:15")], now, from_itm=True,
                       day={"gewertet": 495})  # 9 h - 45 min Pause
    assert rate.personal_seconds == 495 * 60
    assert rate.percent == 100


def test_today_counts_until_now_and_while_stamped_in():
    day = "2026-10-26"
    now = dt(f"{day} 12:00")
    itm = {"zeiten": [{"start": f"{day} 08:00:00", "end": None}], "gewertet": 120}
    spans, running = br.itm_spans(itm, now)
    assert running and spans == [(dt(f"{day} 08:00"), now)]
    # Buchung reicht bis 13:00 (vorgebucht): zählt nur bis jetzt; "gewertet" gilt nicht, solange eingestempelt
    rate = br.day_rate(day, spans, [b(day, "08:00", "13:00")], now, from_itm=True, day=itm, running=True)
    assert rate.personal_seconds == 4 * 3600
    assert rate.booked_seconds == 4 * 3600


def test_not_read_is_not_zero():
    day = "2026-10-19"
    now = dt("2026-10-26 12:00")
    spans = [(dt(f"{day} 08:00"), dt(f"{day} 16:00"))]
    rate = br.day_rate(day, spans, None, now, from_itm=True)
    assert not rate.m42_read and rate.percent is None and rate.stamped
    empty = br.day_rate(day, spans, [], now, from_itm=True)
    assert empty.percent == 0  # gelesen, aber nichts gebucht: das sind wirklich 0 %


def test_future_day_has_no_personal_time():
    rate = br.day_rate("2026-10-30", [(dt("2026-10-30 08:00"), dt("2026-10-30 16:00"))], [],
                       dt("2026-10-26 12:00"), from_itm=False)
    assert rate.personal_seconds == 0 and rate.percent is None


def _rate(day, hours, booked, read=True, itm=True):
    r = br.DayRate(day, personal_seconds=hours * 3600, booked_seconds=booked * 3600,
                   m42_read=read, from_itm=itm)
    return r


def test_seven_days_last_stamped_days():
    rates = [_rate(f"2026-10-{d:02d}", 8, 8) for d in range(10, 17)]   # alt, fällt raus
    rates += [_rate("2026-10-26", 0, 0)]                              # heute nicht gestempelt
    rates += [_rate("2026-10-25", 0, 0), _rate("2026-10-24", 0, 0)]   # Wochenende
    rates += [_rate(f"2026-10-{d:02d}", 8, 4) for d in (19, 20, 21, 22, 23)]
    rates += [_rate("2026-10-17", 4, 4), _rate("2026-10-18", 0, 0)]
    seven = br.seven_days(rates)
    dates = [r.date for r in seven.window]
    assert dates == ["2026-10-23", "2026-10-22", "2026-10-21", "2026-10-20", "2026-10-19",
                     "2026-10-17", "2026-10-16"], dates
    # (5 * 4 + 4 + 8) / (5 * 8 + 4 + 8)
    assert round(seven.percent, 4) == round(100 * 32 / 52, 4)


def test_seven_days_unread_days_do_not_count():
    rates = [_rate("2026-10-23", 8, 8), _rate("2026-10-22", 8, 0, read=False)]
    seven = br.seven_days(rates)
    assert seven.percent == 100
    assert [r.date for r in seven.unread] == ["2026-10-22"]
    assert len(seven.window) == 2
    assert br.seven_days([_rate("2026-10-22", 8, 0, read=False)]).percent is None


def test_without_itm_only_days_with_bookings_count():
    # Arbeitszeit aus den Einstellungen: Urlaubstag ohne Buchung zählt nicht als 0 %
    rates = [_rate("2026-10-23", 8, 6, itm=False), _rate("2026-10-22", 8, 0, itm=False)]
    seven = br.seven_days(rates)
    assert [r.date for r in seven.window] == ["2026-10-23"] and seven.percent == 75


def test_week_and_lookback_dates():
    assert br.week_dates("2026-10-22")[0] == "2026-10-19"
    assert br.week_dates("2026-10-22")[-1] == "2026-10-25"
    back = br.lookback_dates("2026-10-26", 3)
    assert back == ["2026-10-26", "2026-10-25", "2026-10-24"]
    assert br.duration(80 * 60) == "1:20 h" and br.duration(45 * 60) == "45 min"
