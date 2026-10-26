"""Matrix42: Kalendereinträge umwandeln und Abgleich gebucht / nicht gebucht (m42_data.py)."""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import m42_data as m  # noqa: E402

D = "2026-10-19"


def ev(time, title="Systems - TCK0000049374 - Praktikanten / Azubi Oktober 2026", te="TE1", day=D):
    return {"date": day, "time": time, "title": title, "description": te}


def dt(hm, day=D):
    return datetime.fromisoformat(f"{day} {hm}:00")


def test_title():
    assert m.parse_title("Kropff-Federath'sche Stiftung - Jugendhilfe Olsber  - TCK0000049378 - "
                         "Salto Schließanlage auf weiteres Notebook") == (
        "Kropff-Federath'sche Stiftung - Jugendhilfe Olsber", "TCK0000049378",
        "Salto Schließanlage auf weiteres Notebook")
    assert m.parse_title("Menken & Drees  - TCK0000048982 - Installation Freckmann&Partner")[0] == "Menken & Drees"
    assert m.parse_title("Urlaub") == ("Urlaub", "", "")


def test_booking_from_event():
    b = m.booking_from_event(ev("08:10 - 08:55"))
    assert b == {"start": f"{D} 08:10:00", "end": f"{D} 08:55:00", "customer": "Systems",
                 "ticket": "TCK0000049374", "subject": "Praktikanten / Azubi Oktober 2026",
                 "entry": "TE1", "title": "Systems - TCK0000049374 - Praktikanten / Azubi Oktober 2026"}
    assert m.booking_from_event(ev("23:30 - 00:15"))["end"] == "2026-10-20 00:15:00"  # über Mitternacht
    assert m.booking_from_event(ev("")) is None
    assert m.booking_from_event(ev("08:10")) is None
    assert m.booking_from_event(ev("8:xx - 9:00")) is None
    assert m.booking_from_event(dict(ev("08:10 - 08:55"), date=None)) is None


def test_bookings_by_day():
    days = ["2026-10-19", "2026-10-20", "2026-10-25"]
    out = m.bookings_by_day(days, [ev("14:20 - 16:40"), ev("08:10 - 08:55"),
                                   ev("08:20 - 09:20", day="2026-10-20"), ev("bad")])
    assert [b["start"][11:16] for b in out["2026-10-19"]] == ["08:10", "14:20"]
    assert len(out["2026-10-20"]) == 1 and out["2026-10-25"] == []


def test_week_start():
    assert m.week_start("2026-10-25") == "2026-10-19"
    assert m.week_start("2026-10-19") == "2026-10-19"


def test_gaps():
    bookings = [m.booking_from_event(ev(t)) for t in ("08:10 - 08:55", "08:38 - 08:53",
                                                     "09:10 - 09:55", "14:20 - 16:40")]
    work = [(dt("08:00"), dt("12:00")), (dt("12:30"), dt("17:00"))]
    out = [(a.strftime("%H:%M"), b.strftime("%H:%M")) for a, b in m.gaps(work, bookings, 5)]
    # 08:00–08:10 (10 min), 08:55–09:10, 09:55–12:00, 12:30–14:20, 16:40–17:00
    assert out == [("08:00", "08:10"), ("08:55", "09:10"), ("09:55", "12:00"),
                   ("12:30", "14:20"), ("16:40", "17:00")], out
    assert m.gaps(work, bookings, 15) == [g for g in m.gaps(work, bookings, 5)
                                          if (g[1] - g[0]).total_seconds() >= 900]
    assert m.gaps([], bookings) == []
    assert [(a.hour, b.hour) for a, b in m.gaps(work, [])] == [(8, 12), (12, 17)]


def test_unbooked():
    bookings = [m.booking_from_event(ev("09:00 - 10:00"))]
    inside = {"start": f"{D} 09:10:00", "end": f"{D} 09:50:00"}
    half = {"start": f"{D} 09:40:00", "end": f"{D} 10:30:00"}   # 20 von 50 min gebucht
    outside = {"start": f"{D} 11:00:00", "end": f"{D} 11:30:00"}
    short = {"start": f"{D} 12:00:00", "end": f"{D} 12:02:00"}
    assert m.unbooked([inside, half, outside, short], bookings, 5) == [half, outside]
