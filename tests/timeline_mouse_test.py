"""Maus in der Timeline: links ziehen = Tätigkeit eintragen, rechts ziehen = Zoom,
einfacher Rechtsklick = Menü.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
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

# Zeilen in der Legende verschieben: VPN nach ganz oben ziehen
from PySide6.QtCore import QDate  # noqa: E402
today = QDate.currentDate().toString("yyyy-MM-dd")
view.activities = [
    {"start": f"{today} 09:00:00", "end": f"{today} 10:00:00", "type": "VPN-Verbindung", "customer_name": "Kunde"},
    {"start": f"{today} 11:00:00", "end": f"{today} 11:10:00", "type": "Telefonat", "customer_name": "Anruf"},
]
view._remote_cache.clear()
view.draw_timeline(QDate.currentDate())
QApplication.processEvents()
keys = list(view._legend_keys)
assert "vpn" in keys and "call" in keys and "work" in keys, keys
orders = []
view.row_order_changed.connect(orders.append)


def legend_point(key):
    y, h, _n, _c = view._legend[view._legend_keys.index(key)]
    return QPoint(20, int(view.mapFromScene(0, y + h / 2).y()))


first = next(k for k in view._legend_keys if k in timeline_only.MOVABLE_ROWS)
top = legend_point(first)
QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, legend_point("vpn"))
QTest.mouseMove(vp, top - QPoint(0, 4))
QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, top - QPoint(0, 4))
assert orders and orders[-1].index("vpn") < orders[-1].index(first), orders
assert not requests[1:], "Ziehen in der Legende ist kein Zeiteintrag"
view.config["timeline_row_order"] = orders[-1]
view.draw_timeline(QDate.currentDate())
movable = [k for k in view._legend_keys if k in timeline_only.MOVABLE_ROWS]
assert movable[0] == "vpn", movable
# Neue Zeilen kommen an ihren Standardplatz, unbekannte fallen weg
order = timeline_only.row_order({"timeline_row_order": ["vpn", "gibtsnicht", "work"]})
assert order[0] == "vpn" and order.index("work") < order.index("doc") and "gibtsnicht" not in order, order
assert order.index("tv") == 1, order  # fehlende Zeile hinter ihren Vorgänger
assert sorted(timeline_only.row_order({})) == sorted(timeline_only.MOVABLE_ROWS)
assert timeline_only.moved(["a", "b", "c"], "c", "a", False) == ["c", "a", "b"]
assert timeline_only.moved(["a", "b", "c"], "a", "c", True) == ["b", "c", "a"]

print("Timeline-Maus OK")
view.shutdown()
os._exit(0)
