"""Mehrzeiligkeit der Timeline: überlappende Einträge kommen in eine weitere Zeile."""
from datetime import datetime

from timeline_only import stack_lanes


def t(text):
    return datetime.strptime(f"2026-10-19 {text}", "%Y-%m-%d %H:%M")


def test_overlapping_entries_get_next_lane():
    spans = [(t("08:10"), t("08:55")), (t("08:38"), t("08:53")), (t("09:10"), t("09:54")),
             (t("10:49"), t("11:19")), (t("11:00"), t("14:15")), (t("14:19"), t("16:39"))]
    lanes, count = stack_lanes(spans)
    assert count == 2
    assert lanes == [0, 1, 0, 0, 1, 0]


def test_touching_entries_stay_in_one_lane():
    lanes, count = stack_lanes([(t("09:31"), t("09:43")), (t("09:30"), t("09:31"))])
    assert (lanes, count) == ([0, 0], 1)


def test_lane_is_reused_and_capped():
    spans = [(t("08:00"), t("12:00"))] * 4 + [(t("13:00"), t("14:00"))]
    lanes, count = stack_lanes(spans, max_lanes=3)
    assert count == 3 and lanes[:4] == [0, 1, 2, 2] and lanes[4] == 0
    assert stack_lanes([]) == ([], 0)


def test_now_pill_keeps_white_time_readable():
    from theme import contrast
    from timeline_only import now_pill_color
    for line in ("#E11D48", "#F28B82", "#FACC15"):  # hell, dunkel, eigene Farbe
        assert contrast("#FFFFFF", now_pill_color(line).name()) >= 4.5, line
    assert now_pill_color("#E11D48").name().upper() == "#E11D48"  # kräftig genug: unverändert
