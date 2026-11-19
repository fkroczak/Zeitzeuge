"""Arbeitszeit-Ansicht heute: rechts bleibt jetzt + 30 min sichtbar, die Ansicht wächst mit.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

from PySide6.QtWidgets import QApplication  # noqa: E402

import timeline_only  # noqa: E402

app = QApplication(sys.argv)
view = timeline_only.TimelineView([], {})
view._start_first_load = lambda: None  # keine Logs lesen
view.resize(1200, 400)
view.show()
QApplication.processEvents()

now = [9 * 60]  # eingestempelt seit 8:44, läuft bis jetzt
view._work_minutes = lambda date: (8 * 60 + 44, now[0])


def right_edge():
    return view._minute_at(view.viewport().width() - view.RIGHT - 4)


view.show_work_time()
assert abs(right_edge() - (9 * 60 + 30)) < 3, right_edge()

# Zwei Stunden später: rechts wieder jetzt + 30 min, links weiter Beginn - 30 min
now[0] = 11 * 60
view._follow_work_time()
assert abs(right_edge() - (11 * 60 + 30)) < 3, right_edge()
assert abs(view._minute_at(view.LEFT) - (8 * 60 + 14)) < 3, view._minute_at(view.LEFT)

# Unter 5 min Unterschied: nicht neu einpassen
before = view.zoom_level
now[0] += 3
view._follow_work_time()
assert view.zoom_level == before

# Selbst gezoomt: Ansicht bleibt, wie sie ist
view.set_zoom(view.zoom_level * 1.25)
level = view.zoom_level
now[0] += 60
view._follow_work_time()
assert view.zoom_level == level and view._follow_range is None

# 15 min später ohne Eingabe: wieder Arbeitszeit, rechts jetzt + 30 min
clock = [timeline_only.time.monotonic()]
timeline_only.time.monotonic = lambda: clock[0]
view._stop_follow()
clock[0] += 14 * 60
view._follow_work_time()
assert view.zoom_level == level
clock[0] += 61
view._follow_work_time()
assert view._follow_range is not None
assert abs(right_edge() - (now[0] + 30)) < 3, right_edge()

# "Ganzer Tag" gewählt: bleibt ganzer Tag
view.show_whole_day()
clock[0] += 60 * 60
view._follow_work_time()
assert view.fit_day and view._follow_range is None
print("ok")
