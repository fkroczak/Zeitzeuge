"""Maus in der Timeline: links ziehen = Tätigkeit eintragen, rechts ziehen = Zoom,
einfacher Rechtsklick = Menü.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import timeline_only  # noqa: E402

app = QApplication(sys.argv)
view = timeline_only.TimelineView([], {})
view._start_first_load = lambda: None  # keine Logs lesen
view.resize(1200, 400)
view.show()
view.show_whole_day()
QApplication.processEvents()

requests, menus = [], []
view.doc_request.connect(lambda action, entry: requests.append((action, entry)))
timeline_only.exec_entry_menu = lambda parent, entry, pos: menus.append(entry)


def at(minute):
    return QPoint(int(view.mapFromScene(view._x(minute), 0).x()), 200)


def drag(button, a, b):
    vp = view.viewport()
    QTest.mousePress(vp, button, Qt.NoModifier, at(a))
    QTest.mouseMove(vp, at((a + b) / 2))
    QTest.mouseMove(vp, at(b))
    QTest.mouseRelease(vp, button, Qt.NoModifier, at(b))


# Links ziehen: Zeiteintrag mit dem markierten Zeitraum, Ansicht bleibt
drag(Qt.LeftButton, 9 * 60, 10 * 60 + 30)
assert view.fit_day, "links ziehen darf nicht zoomen"
assert len(requests) == 1 and requests[0][0] == "add_range", requests
span = requests[0][1]
assert abs(span["start_min"] - 540) <= 1 and abs(span["end_min"] - 630) <= 1, span
assert view._drag_item is None and view._drag_start is None

# Rechts ziehen: genau diesen Zeitraum zeigen, kein Eintrag, kein Menü
drag(Qt.RightButton, 13 * 60, 15 * 60)
assert not view.fit_day, "rechts ziehen soll zoomen"
assert len(requests) == 1 and not menus, (requests, menus)
left = view._minute_at(view.LEFT)
assert abs(left - 13 * 60) < 3, left

# Einfacher Rechtsklick: Menü an dieser Stelle
view.show_whole_day()
QApplication.processEvents()
QTest.mouseClick(view.viewport(), Qt.RightButton, Qt.NoModifier, at(8 * 60))
assert len(menus) == 1 and abs(menus[0]["minute"] - 480) <= 2, menus

# ESC bricht das Ziehen ab
vp = view.viewport()
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, at(600))
QTest.mouseMove(vp, at(660))
QTest.keyClick(view, Qt.Key_Escape)
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, at(660))
assert len(requests) == 1 and view._drag_item is None, requests

print("Timeline-Maus OK")
view.shutdown()
os._exit(0)
