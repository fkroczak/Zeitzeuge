"""Beginn und Ende eines Doku-Balkens in der Timeline ziehen (↔ am Rand), Raster 5 min.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import faulthandler
import os
import sys
import tempfile
import traceback
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()


def unit_test():
    from journal import edge_at_minute

    def end(minute, start="09:00:00"):
        item = {"start": f"2026-11-19 {start}", "end": "2026-11-19 10:00:00"}
        return edge_at_minute(item, "end", minute)[11:16]

    def begin(minute, end="10:00:00"):
        item = {"start": "2026-11-19 09:00:00", "end": f"2026-11-19 {end}"}
        return edge_at_minute(item, "start", minute)[11:16]
    assert end(10 * 60 + 13) == "10:15" and end(10 * 60 + 12) == "10:10"
    assert end(9 * 60 + 1) == "09:05", "mindestens 5 min"
    assert end(9 * 60, start="09:02:00") == "09:10", "erste volle 5 min nach Beginn + 5"
    assert end(24 * 60 + 30) == "23:59"
    assert begin(8 * 60 + 33) == "08:35" and begin(10 * 60) == "09:55", "mindestens 5 min"
    assert begin(10 * 60, end="10:08:00") == "10:00" and begin(-20) == "00:00"


def gui_test():
    import main_timeline
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    app = QApplication(sys.argv)  # noqa: F841
    window = main_timeline.TimelineApp()
    window.tray.showMessage = lambda *a: None
    window.resize(1400, 800)
    window.show()
    day = date.today().strftime("%Y-%m-%d")
    item = window.journal.add({"start": f"{day} 09:00:00", "end": f"{day} 10:11:00",
                               "customer": "Volksbank", "category": "Fernwartung", "text": "Prüfung"})
    view = window.timeline
    QTest.qWait(2500)  # erstes Laden (Logs …) abwarten, das zeichnet noch einmal
    view.draw_timeline(view.current_date)
    view.show_range(8 * 60, 12 * 60)
    QApplication.processEvents()
    edits = []
    window.edit_doc = lambda i: edits.append(i)

    def doc_rect():
        return next(r for r, a in view.activity_rects.items()
                    if a.get("doc") and a["doc_item"]["id"] == item["id"])

    def end_now():
        return next(i for i in window.journal.items(day) if i["id"] == item["id"])["end"][11:16]

    def at(minute, y):
        return QPoint(int(view.mapFromScene(view._x(minute), 0).x()), y)

    vp = view.viewport()
    box = view.mapFromScene(doc_rect().sceneBoundingRect()).boundingRect()
    y = box.center().y()
    edge = QPoint(box.right() - 2, y)
    assert view._edge_grip_at(edge) == (doc_rect(), "end"), "rechter Rand greifbar"
    assert view._edge_grip_at(QPoint(box.left() + 2, y)) == (doc_rect(), "start"), "linker Rand"
    assert view._edge_grip_at(QPoint(box.center().x(), y)) is None, "Mitte nicht"
    QTest.mouseMove(vp, edge)
    assert vp.cursor().shape() == Qt.SizeHorCursor

    # Nach rechts ziehen: 10:28 -> 10:30
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, edge)
    QTest.mouseMove(vp, at(10 * 60 + 20, y))
    QTest.mouseMove(vp, at(10 * 60 + 28, y))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, at(10 * 60 + 28, y))
    assert end_now() == "10:30", end_now()
    assert not edits

    # Nach links, Esc bricht ab
    box = view.mapFromScene(doc_rect().sceneBoundingRect()).boundingRect()
    edge = QPoint(box.right() - 2, y)
    QTest.mouseMove(vp, edge)
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, edge)
    QTest.mouseMove(vp, at(9 * 60 + 40, y))
    QTest.keyClick(view, Qt.Key_Escape)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, at(9 * 60 + 40, y))
    assert end_now() == "10:30", end_now()

    # Nach links: 9:41 -> 9:40
    QTest.mouseMove(vp, edge)
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, edge)
    QTest.mouseMove(vp, at(9 * 60 + 41, y))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, at(9 * 60 + 41, y))
    assert end_now() == "09:40", end_now()

    # Beginn nach links ziehen: 8:32 -> 8:30, Ende bleibt
    box = view.mapFromScene(doc_rect().sceneBoundingRect()).boundingRect()
    left = QPoint(box.left() + 2, y)
    QTest.mouseMove(vp, left)
    assert vp.cursor().shape() == Qt.SizeHorCursor
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, left)
    QTest.mouseMove(vp, at(8 * 60 + 45, y))
    QTest.mouseMove(vp, at(8 * 60 + 32, y))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, at(8 * 60 + 32, y))
    begin_now = next(i for i in window.journal.items(day) if i["id"] == item["id"])["start"][11:16]
    assert begin_now == "08:30" and end_now() == "09:40", (begin_now, end_now())

    # Nur auf den Rand geklickt: bearbeiten wie bisher
    box = view.mapFromScene(doc_rect().sceneBoundingRect()).boundingRect()
    edge = QPoint(box.right() - 2, y)
    QTest.mouseMove(vp, edge)
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, edge)
    assert len(edits) == 1 and end_now() == "09:40"
    window.quit_app()
    print("Beginn/Ende ziehen: OK")


try:
    unit_test()
    gui_test()
except Exception:
    traceback.print_exc()
    sys.stdout.flush()
    import safe_io
    safe_io.hard_exit(1)
sys.stdout.flush()
import safe_io  # Ende ohne Qt-Aufräumen (Absturz unter Windows)
safe_io.hard_exit(0)
