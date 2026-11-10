"""Zwischenspeicher beim Zeichnen: einmal je Zeichnen rechnen, nie veraltete Daten.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

from PySide6.QtCore import QDate  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import timeline_only  # noqa: E402

app = QApplication(sys.argv)
D = QDate(2026, 11, 10)


class Tracker:
    def __init__(self):
        self.segs = []

    def segments_for(self, _date):
        return [dict(s) for s in self.segs]


def seg(a, b, app="a.exe", title="x"):
    return {"start": f"2026-11-10 {a}", "end": f"2026-11-10 {b}", "app": app, "title": title}


view = timeline_only.TimelineView([], {})
view._start_first_load = lambda: None  # keine Logs lesen
view.tracker = Tracker()
view.tracker.segs = [seg("09:00:00", "09:10:00")]

# Fensterstücke: neues Stück kommt sofort an, Aufrufer bekommen Kopien
first = view.pc_entries_for(D)
assert [e["end"][11:] for e in first] == ["09:10:00"], first
first[0]["customer_name"] = "geändert"
assert view.pc_entries_for(D)[0]["customer_name"] == "x"
view.tracker.segs.append(seg("09:10:30", "09:20:00"))
assert [e["end"][11:] for e in view.pc_entries_for(D)] == ["09:20:00"], "geänderte Fenster werden gesehen"

# Außerhalb des Zeichnens wird jedes Mal neu gelesen
calls = []
real = view._activities_for
view._activities_for = lambda date: calls.append(date) or real(date)
view.activities_for(D)
view.activities_for(D)
assert len(calls) == 2, calls

# Während des Zeichnens nur einmal, danach wieder frisch
seen = []
view.day_loaded.connect(lambda acts, pcs: (view.activities_for(D), view.activities_for(D), seen.append(1)))
calls.clear()
view.current_date = D
view.draw_timeline(D)
assert seen and len(calls) == 1, calls
assert view._draw_memo is None
view.activities_for(D)
assert len(calls) == 2, "nach dem Zeichnen nicht mehr gemerkt"
print("ok")
os._exit(0)
