"""Menü im Infobereich: öffnet immer an derselben Stelle über dem Symbol."""
from PySide6.QtCore import QPoint, QRect, QSize

import main_timeline  # noqa: F401  (app_tray nur über main_timeline laden)
from app_tray import tray_menu_pos

AVAIL = QRect(0, 0, 1920, 1032)  # Taskleiste unten, 48 px
MENU = QSize(260, 280)


def test_menu_centered_above_icon():
    assert tray_menu_pos(QRect(1700, 1040, 24, 24), MENU, AVAIL) == QPoint(1582 - 1, 752)


def test_menu_stays_on_screen_at_right_edge():
    pos = tray_menu_pos(QRect(1900, 1040, 24, 24), MENU, AVAIL)
    assert pos.x() + MENU.width() - 1 == AVAIL.right() and pos.y() == 752


def test_taskbar_on_top():
    assert tray_menu_pos(QRect(1700, 0, 24, 24), MENU, QRect(0, 40, 1920, 1040)).y() == 40


def test_unknown_icon_position_leaves_it_to_qt():
    assert tray_menu_pos(QRect(), MENU, AVAIL) is None
