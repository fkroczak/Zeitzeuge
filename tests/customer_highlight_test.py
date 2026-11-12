"""Kundenfilter (Chip „Nach Kunde“) in der Timeline: Balken des Kunden mit Rahmen,
die übrigen blasser; Stärke im Menü Ansicht → Kunde hervorheben."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QBrush, QPen  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import timeline_only  # noqa: E402

app = QApplication.instance() or QApplication([])
_views = []  # Views am Leben halten (sonst ist die Szene schon gelöscht)


def bars(config):
    view = timeline_only.TimelineView([], config)
    view._start_first_load = lambda: None
    _views.append(view)
    view.highlight = lambda e: e.get("customer_name") == "Jugendhilfe Olsberg"
    mine = view._add_block(0, 0, 20, 10, QPen(Qt.NoPen), QBrush(Qt.red))
    other = view._add_block(0, 0, 20, 10, QPen(Qt.NoPen), QBrush(Qt.red))
    label = view.scene.addSimpleText("x")
    work = view._add_block(0, 0, 20, 10, QPen(Qt.NoPen), QBrush(Qt.red))
    view._dim_unless_highlighted({"customer_name": "Jugendhilfe Olsberg"}, mine)
    view._dim_unless_highlighted({"customer_name": "ITM"}, other, label)
    view._dim_unless_highlighted({"customer_name": "08:21 – 12:21", "work": True}, work)
    return mine, other, label, work


def test_default_frame():
    mine, other, label, work = bars({})
    assert mine.pen().style() == Qt.SolidLine and mine.opacity() == 1
    assert other.opacity() == label.opacity() == timeline_only.CUSTOMER_HL_STYLES["frame"]
    assert work.opacity() == 1 and work.pen().style() == Qt.NoPen  # Personalzeit bleibt


def test_strong():
    _mine, other, _label, _work = bars({"customer_highlight": "strong"})
    assert other.opacity() == timeline_only.CUSTOMER_HL_STYLES["strong"]


def test_off():
    mine, other, label, _work = bars({"customer_highlight": "off"})
    assert mine.pen().style() == Qt.NoPen and other.opacity() == label.opacity() == 1
