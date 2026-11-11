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
from PySide6.QtTest import QTest  # noqa: E402
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

# Arbeitsblöcke für mehrere Tage gemerkt (Hin- und Herspringen), geänderte Stücke neu
import focus  # noqa: E402
computed = []
real_focus = focus.focus_blocks
focus.focus_blocks = lambda *a, **k: computed.append(1) or real_focus(*a, **k)
D2 = D.addDays(-1)
view.config.update(customers=[], teamviewer_names={})  # wie in der App (sonst neuer Kundenindex)
orig_segments_for = Tracker.segments_for
view.tracker.segments_for = lambda d: [dict(x, start=d + x["start"][10:], end=d + x["end"][10:])
                                       for x in view.tracker.segs]
for day in (D, D2, D, D2):
    view.pc_blocks_for(day)
assert len(computed) == 2, f"je Tag einmal gerechnet: {computed}"
view.tracker.segs.append(seg("09:30:00", "09:45:00", "b.exe", "y"))
view.pc_blocks_for(D)
assert len(computed) == 3, "neue Fensterstücke: neu gerechnet"
focus.focus_blocks = real_focus
view.tracker.segments_for = lambda d: orig_segments_for(view.tracker, d)
view.tracker.segs = [seg("09:00:00", "09:10:00"), seg("09:10:30", "09:20:00")]

# Vortag im Hintergrund vorbereiten: danach trifft das Zeichnen die Zwischenspeicher,
# Ergebnis gleich wie selbst gerechnet
view._pc_cache.clear()
view._block_cache = None
view._prefetch(D2)
assert ("2026-11-09", 5, 15) in view._pc_cache and ("2026-11-09", 30, 60) in view._pc_cache
assert view._block_cache, "Arbeitsblöcke des Vortags gemerkt"
prepared = view.pc_blocks_for(D2)
view._pc_cache.clear()
view._block_cache = None
assert view.pc_blocks_for(D2) == prepared, "vorbereitet = selbst gerechnet"
view.loading = False
view._schedule_prefetch(D)
assert view._prefetch_date == D2 and view._prefetch_timer.isActive()
view._prefetch_timer.stop()

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

# Aufzeichnung meldet eine Änderung: nur diese Quelle neu, ein Zeichnen für mehrere Meldungen
draws = []
view.draw_timeline = lambda date: draws.append(date)
view._tv_index = object()  # Logs gelten als gelesen
view.loading = False
view._local_index = view._sophos_index = "alt"
view._remote_cache["x"] = []
view.reload_source("local")
view.reload_source("vpn")
assert view._local_index is None and view._sophos_index is None and not view._remote_cache
assert not view.loading, "keine Logs neu lesen"
QTest.qWait(300)
assert len(draws) == 1, draws
view._local_index = "alt"
view.reload_source("local", draw=False)  # anderer Tag angezeigt: nur verwerfen
QTest.qWait(300)
assert view._local_index is None and len(draws) == 1
print("ok")
os._exit(0)
