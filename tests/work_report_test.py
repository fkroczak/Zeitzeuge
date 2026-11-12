"""Tages- und Wochenbericht (work_report.py, ohne Qt): eigener Beleg für Zeit ohne Matrix42-Buchung."""
from datetime import datetime

import work_report as wr

D = "2026-11-11"
NOW = datetime(2026, 11, 12, 18, 0)


def dt(t, day=D):
    return datetime.strptime(f"{day} {t}", "%Y-%m-%d %H:%M")


def item(start, end, text, customer="Intern", **extra):
    return {"start": f"{D} {start}:00", "end": f"{D} {end}:00", "customer": customer,
            "category": "Besprechung", "text": text, **extra}


def trace(start, end, kind, name, details=""):
    return {"start": f"{D} {start}:00", "end": f"{D} {end}:00", "type": kind,
            "customer_name": name, "details": details}


SPANS = [(dt("07:45"), dt("12:15")), (dt("12:45"), dt("16:30"))]
DOCS = [item("08:00", "09:00", "Vorbereitung Jahresgespräch"),
        item("09:00", "11:15", "Jahresgespräch"),
        item("11:15", "11:45", "Nachbereitung Jahresgespräch"),
        item("13:00", "14:30", "Drucker", customer="Müller GmbH", m42_entry="TE0000088403")]
BOOKINGS = [{"start": f"{D} 13:00:00", "end": f"{D} 14:30:00", "customer": "Müller GmbH", "ticket": "TCK1"},
            {"start": f"{D} 14:30:00", "end": f"{D} 16:30:00", "customer": "Weber AG", "ticket": "TCK2",
             "subject": "Server", "entry": "Updates"}]
TRACES = [trace("08:55", "11:20", "Termin", "Jahresgespräch", "Ort: Raum 2"),
          trace("11:21", "11:21", "Datei geöffnet", "Protokoll.docx"),
          trace("11:25", "11:25", "Datei geöffnet", "Ziele.xlsx"),
          trace("14:00", "15:00", "Matrix42-Buchung", "Weber AG"),
          trace("14:35", "14:42", "Telefonat", "Weber AG")]


def build(bookings=BOOKINGS):
    return wr.build_day(D, SPANS, DOCS, bookings, TRACES, from_itm=True, now=NOW)


def test_unbooked_morning_is_documented_with_evidence():
    day = build()
    assert day["personal_seconds"] == 8.25 * 3600
    assert day["booked_seconds"] == 3.5 * 3600
    # der Vormittag ohne Buchung (Jahresgespräch) steht als Lücke mit Belegen da
    first = day["gaps"][0]
    assert (first["start"], first["end"]) == (dt("07:45"), dt("12:15"))
    text = "\n".join(first["evidence"])
    assert "Tätigkeit 09:00–11:15: Intern · Besprechung · Jahresgespräch" in text
    assert "Termin · Jahresgespräch" in text
    assert day["gap_seconds"] == 4.75 * 3600


def test_booking_state_per_item():
    states = [(i["what"].split(" · ")[-1], i["level"]) for i in build()["items"]]
    assert states == [("Vorbereitung Jahresgespräch", "missing"), ("Jahresgespräch", "missing"),
                      ("Nachbereitung Jahresgespräch", "missing"), ("Drucker", "booked")]
    # ohne Matrix42-Nummer: gebucht ab der Hälfte, darunter teilweise
    half = item("14:00", "15:00", "x")
    assert wr.booking_state(half, BOOKINGS)[1] == "booked"
    part = item("12:00", "13:20", "x")
    assert wr.booking_state(part, BOOKINGS) == ("nur 20 min gebucht", "partly")
    assert wr.booking_state(part, None)[1] == "unknown"


def test_traces_merged_and_matrix42_left_out():
    rows = build()["traces"]
    assert [r["type"] for r in rows] == ["Termin", "Datei geöffnet", "Telefonat"]
    assert rows[1]["what"] == "Protokoll.docx, Ziele.xlsx"


def test_matrix42_not_read_claims_nothing():
    day = build(None)
    assert not day["m42_read"] and day["gaps"] == [] and day["gap_seconds"] == 0
    html = wr.document([day])
    assert "nicht gelesen" in html and "ohne Matrix42-Buchung</h2>" not in html


def test_html_day_and_week():
    day = build()
    html = wr.document([day], person="Max <B>")
    assert "Tagesbericht Mittwoch, 11.11.2026" in html and "Max &lt;B&gt;" in html
    assert "✗ nicht gebucht" in html and "TE0000088403" in html and "Unterschrift" in html
    other = wr.build_day("2026-11-10", [(dt("08:00", "2026-11-10"), dt("16:00", "2026-11-10"))],
                         [], [], [], from_itm=True, now=NOW)
    week = wr.document([other, day], week=True)
    assert "Wochenbericht KW 46" in week and week.count("page-break-before") == 2
    assert wr.file_name([other, day], week=True) == "Wochenbericht_KW46_2026.pdf"
    assert wr.file_name([day]) == "Tagesbericht_2026-11-11.pdf"
    assert not wr.has_content(wr.build_day("2026-11-15", [], [], None, [], now=NOW))


def test_chart_rows_and_range():
    data = wr.chart(build())
    names = [name for name, _bars in data["rows"]]
    assert names == ["Personalzeit", "Matrix42", "Tätigkeiten", "Termine & Mail", "Telefon", "PC & Dateien"]
    assert (data["start"], data["end"]) == (dt("07:00"), dt("17:00"))
    rows = dict(data["rows"])
    assert [b["style"] for b in rows["Matrix42"]] == ["booking", "booking", "gap", "gap"]
    assert [b["style"] for b in rows["Tätigkeiten"]] == ["doc_missing"] * 3 + ["doc_booked"]
    assert rows["Tätigkeiten"][1]["text"] == "Jahresgespräch"
    # Punkte (Datei, Mail) bekommen eine sichtbare Breite
    assert rows["PC & Dateien"][0]["end"] - rows["PC & Dateien"][0]["start"] >= wr.MIN_BAR
    assert wr.chart_row({"type": "PC: Word"}) == "PC-Arbeit"
    assert wr.chart_row({"type": "TeamViewer"}) == "Verbindungen"
    assert wr.chart_row({"type": "Teams-Anruf"}) == "Telefon"
    # ohne irgendetwas: 7–17 Uhr, nur die drei festen Zeilen
    empty = wr.chart(wr.build_day("2026-11-15", [], [], None, [], now=NOW))
    assert empty["start"].hour == 7 and len(empty["rows"]) == 3


def test_week_chart_one_row_per_day_same_hours():
    other = wr.build_day("2026-11-10", [(dt("06:30", "2026-11-10"), dt("15:00", "2026-11-10"))],
                         [], [], [], from_itm=True, now=NOW)
    data = wr.week_chart([other, build()])
    assert [name for name, _b in data["rows"]] == ["Di 10.11.", "Mi 11.11."]
    assert data["start"].hour == 6 and data["end"].hour == 17
    # alle Balken auf den ersten Tag verschoben, damit die Uhrzeiten untereinander stehen
    assert all(b["start"].date() == other["day"].date() for _n, bars in data["rows"] for b in bars)
    html = wr.document([other, build()], week=True, charts=True)
    assert html.count(wr.CHART_PREFIX) == 3 and "Selbstauskunft" in html
    assert set(wr.charts_for([other, build()], week=True)) == {
        wr.CHART_PREFIX + "2026-11-10", wr.CHART_PREFIX + D, wr.CHART_PREFIX + "woche"}


def test_status_colors_readable_on_light_and_dark():
    """Dieselben Farben in Timeline und Bericht: Balken heben sich in beiden Designs ab (3 : 1)."""
    from theme import contrast, readable_on
    for kind, key in wr.TYPE_STATUS.items():
        color = wr.STATUS_COLORS[key]
        assert contrast(readable_on(color).name(), color) >= 4.5, (kind, color)  # Schrift im Balken
        for ground in ("#FFFFFF", "#1A1A1A"):
            assert contrast(color, ground) >= 3.0, (kind, color, ground)


def test_unbooked_doc_type_is_orange_like_open():
    assert wr.STATUS_COLORS[wr.TYPE_STATUS[wr.DOC_UNBOOKED_TYPE]] == wr.STATUS_COLORS["doc_missing"]
    assert wr.DOC_UNBOOKED_TYPE in wr.SKIP_TYPES
