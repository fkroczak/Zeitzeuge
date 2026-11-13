"""Platzhalter-Umrisse, bis die echten Daten da sind.

Beim Start steht das Fenster sofort: Timeline, Tagesliste und Kennzahlen zeigen graue
Umrisse (Zeilen, Balken, Werte), die sanft pulsieren. Die Daten werden derweil gelesen und
ersetzen die Umrisse in einem Zug. So sieht man gleich, wo was hinkommt, statt auf ein
leeres oder eingefrorenes Fenster zu schauen.

Lines(textfeld) legt Textzeilen-Umrisse über ein Textfeld, bis done() kommt (z. B. Beschreibung,
die aus Matrix42 geladen wird); table_rows(...) malt Umrisse von Tabellenzeilen.

pulse().watch(widget) lässt ein Widget im Takt neu malen, unwatch beendet das. Gemalt wird
mit color(...) und bar(...); ohne beobachtete Widgets läuft kein Zeitgeber.
"""
import math
import time

from PySide6.QtCore import QEvent, QObject, QRectF, QSize, Qt, QTimer
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


LINE_WIDTHS = (0.94, 0.82, 0.88, 0.6, 0.9, 0.74, 0.5)


class Lines(QWidget):
    """Umrisse von Textzeilen über einem Textfeld (QPlainTextEdit o. ä.), bis done().
    Liegt auf dem Viewport, lässt Klicks durch und folgt seiner Größe."""

    def __init__(self, target, lines=4):
        host = target.viewport() if hasattr(target, "viewport") else target
        super().__init__(host)
        self._lines = lines
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(host.rect())
        host.installEventFilter(self)
        self.show()
        pulse().watch(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            self.setGeometry(obj.rect())
        return False

    def done(self):
        pulse().unwatch(self)
        if self.parent() is not None:
            self.parent().removeEventFilter(self)
        self.hide()
        self.deleteLater()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        fill = color(text_color(self), 1.3)
        width = self.width() - 16
        for i in range(self._lines):
            y = 10 + i * 20
            if y + 10 > self.height():
                break
            bar(painter, QRectF(8, y, width * LINE_WIDTHS[i % len(LINE_WIDTHS)], 10), fill, 5)
        painter.end()


def table_rows(painter, table, rows=8, row_height=28):
    """Umrisse von Tabellenzeilen in den Viewport einer Tabelle malen (Spalten wie die echten)."""
    fill = color(text_color(table), 1.3)
    cols = table.columnCount()
    height = table.viewport().height()
    for r in range(rows):
        y = r * row_height + (row_height - 10) / 2
        if y + 10 > height:
            break
        for c in range(cols):
            if table.isColumnHidden(c):
                continue
            x, w = table.columnViewportPosition(c), table.columnWidth(c)
            share = LINE_WIDTHS[(r + c) % len(LINE_WIDTHS)]
            if w > 20:
                bar(painter, QRectF(x + 8, y, max(12.0, (w - 16) * share), 10), fill, 5)
