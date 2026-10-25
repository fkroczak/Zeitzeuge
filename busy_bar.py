"""Ladeanzeige oben im Fenster: zeigt gut sichtbar, was gerade geladen wird.

Ein laufender Streifen in der Akzentfarbe plus Text, z. B.
"Lädt: 3CX-Anrufe · KI-Vorschläge (Claude ordnet 25.10. ein) …".
Erscheint erst nach kurzer Verzögerung, damit kurze Lesevorgänge nicht flackern.
"""
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class _Stripe(QWidget):
    """Schmaler Balken mit wanderndem Abschnitt (unbestimmter Fortschritt)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)
        self.color = QColor("#0067C0")
        self._pos = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)

    def start(self):
        if not self._timer.isActive():
            self._timer.start(30)

    def stop(self):
        self._timer.stop()

    def _step(self):
        self._pos = (self._pos + 0.012) % 1.4
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        track = QColor(self.color)
        track.setAlpha(45)
        p.fillRect(self.rect(), track)
        w = self.width()
        seg = w * 0.3
        x = (self._pos - 0.3) * w
        p.fillRect(QRectF(x, 0, seg, self.height()), self.color)
        p.end()


class BusyBar(QWidget):
    SHOW_DELAY = 300  # ms: erst zeigen, wenn es wirklich etwas dauert

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("busy_bar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(12, 5, 12, 5)
        self.label = QLabel(self)
        self.label.setObjectName("busy_text")
        self.label.setAccessibleName("Ladeanzeige")
        row.addWidget(self.label, 1)
        outer.addLayout(row)
        self.stripe = _Stripe(self)
        outer.addWidget(self.stripe)
        self.items = []
        self._delay = QTimer(self)
        self._delay.setSingleShot(True)
        self._delay.timeout.connect(self._reveal)
        self.hide()

    def set_color(self, color):
        self.stripe.color = QColor(color)
        self.stripe.update()

    def set_items(self, items, delay=SHOW_DELAY):
        """Was gerade lädt, z. B. ["3CX-Anrufe", "ITM-Zeiterfassung"]. Leer = ausblenden.

        delay: so viele ms warten, bevor die Anzeige erscheint (0 = sofort)."""
        self.items = list(items)
        if not self.items:
            self._delay.stop()
            self.stripe.stop()
            self.hide()
            return
        self.label.setText("⏳  Lädt: " + "  ·  ".join(self.items) + " …")
        self.setToolTip("Zeitzeuge liest gerade im Hintergrund. Du kannst weiterarbeiten.")
        if self.isVisible():
            return
        if delay <= 0:
            self._delay.stop()
            self._reveal()
        elif not self._delay.isActive() or self._delay.remainingTime() > delay:
            self._delay.start(delay)

    def _reveal(self):
        if self.items:
            self.stripe.start()
            self.show()
