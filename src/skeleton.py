"""Platzhalter-Umrisse, bis die echten Daten da sind.

Beim Start steht das Fenster sofort: Timeline, Tagesliste und Kennzahlen zeigen graue
Umrisse (Zeilen, Balken, Werte), die sanft pulsieren. Die Daten werden derweil gelesen und
ersetzen die Umrisse in einem Zug. So sieht man gleich, wo was hinkommt, statt auf ein
leeres oder eingefrorenes Fenster zu schauen.

pulse().watch(widget) lässt ein Widget im Takt neu malen, unwatch beendet das. Gemalt wird
mit color(...) und bar(...); ohne beobachtete Widgets läuft kein Zeitgeber.
"""
import math
import time

from PySide6.QtCore import QObject, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QSizePolicy, QWidget

try:
    from shiboken6 import isValid as _alive
except ImportError:  # pragma: no cover
    def _alive(_obj):
        return True

INTERVAL_MS = 60      # Takt des Pulsierens (ruhig, kaum Last)
PERIOD_S = 1.6        # ein Atemzug
MAX_SECONDS = 60      # Sicherheitsnetz: danach steht der Platzhalter still


class _Pulse(QObject):
    def __init__(self):
        super().__init__()
        self._widgets = []
        self._t0 = time.monotonic()
        self._started = None
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def watch(self, widget):
        if widget not in self._widgets:
            self._widgets.append(widget)
        if not self._timer.isActive():
            self._started = time.monotonic()
            self._timer.start()

    def unwatch(self, widget):
        if widget in self._widgets:
            self._widgets.remove(widget)
        if not self._widgets:
            self._timer.stop()

    def watching(self):
        return len(self._widgets)

    def level(self):
        """0 … 1, weich auf und ab."""
        phase = (time.monotonic() - self._t0) / PERIOD_S
        return 0.5 - 0.5 * math.cos(phase * 2 * math.pi)

    def _tick(self):
        if time.monotonic() - (self._started or 0) > MAX_SECONDS:
            self._timer.stop()
            return
        for w in list(self._widgets):
            if not _alive(w):
                self._widgets.remove(w)
                continue
            if w.isVisible():
                w.update()
        if not self._widgets:
            self._timer.stop()


_pulse = []


def pulse():
    if not _pulse:
        _pulse.append(_Pulse())
    return _pulse[0]


def color(text_color, strength=1.0):
    """Farbe der Umrisse: Schriftfarbe, sehr durchscheinend, im Takt etwas kräftiger."""
    c = QColor(text_color)
    level = pulse().level()
    c.setAlpha(int((16 + 18 * level) * strength))
    return c


def bar(painter, rect, fill, radius=4.0):
    """Abgerundeter Balken ohne Rand."""
    painter.setPen(Qt.NoPen)
    painter.setBrush(fill)
    painter.drawRoundedRect(QRectF(rect), radius, radius)


def text_color(widget):
    return widget.palette().color(QPalette.WindowText)


class Bar(QWidget):
    """Platzhalter für einen Wert (z. B. „7:25 h“ in einer Kennzahl-Kachel)."""

    def __init__(self, width, height, parent=None):
        super().__init__(parent)
        self._size = QSize(width, height)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        pulse().watch(self)

    def sizeHint(self):
        return self._size

    def minimumSizeHint(self):
        return QSize(min(self._size.width(), 24), self._size.height())

    def done(self):
        pulse().unwatch(self)
        self.hide()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        bar(painter, QRectF(0, h * 0.15, self.width(), h * 0.7), color(text_color(self), 1.3), h * 0.3)
        painter.end()
