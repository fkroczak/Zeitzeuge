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


def test_aufnahme_punkt_pulsiert_ruhig():
    """Roter Punkt „Aufzeichnung aktiv“: weich zwischen schwach und voll, ein Atemzug ≈ 2,4 s
    (vorher hartes An/Aus alle 0,6 s)."""
    import icons
    period = icons.BREATH_PERIOD
    assert period >= 2.0
    assert icons.breath(0) == 1.0  # Start: voll
    assert icons.breath(period / 2) == icons.BREATH_LOW  # Mitte: am schwächsten
    values = [icons.breath(period * i / 40) for i in range(41)]
    assert min(values) >= icons.BREATH_LOW and max(values) <= 1.0
    # weich: von einem Takt (80 ms) zum nächsten höchstens ein kleiner Schritt
    import app_tray
    steps = [abs(icons.breath(t * app_tray.PULSE_MS / 1000) - icons.breath((t + 1) * app_tray.PULSE_MS / 1000))
             for t in range(60)]
    assert max(steps) <= 0.1 + 1e-9, steps
    assert len({round(v, 2) for v in values}) <= 21  # wenige Stufen: Icons bleiben im Zwischenspeicher
