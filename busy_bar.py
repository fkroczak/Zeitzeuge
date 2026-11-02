"""Ladeanzeige in der Werkzeugleiste: zeigt gut sichtbar, was gerade geladen wird.

Ein laufender Streifen in der Akzentfarbe plus Text, z. B.
"Lädt: 3CX-Anrufe · KI-Vorschläge (Claude ordnet 25.10. ein) …".
Sie liegt schwebend im freien Platz rechts neben den Werkzeugen (siehe
place_busy_bar im Hauptfenster), Ein- und Ausblenden verschiebt also nichts.
Erscheint erst nach kurzer Verzögerung, damit kurze Lesevorgänge nicht flackern.
"""
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


class _Stripe(QWidget):
    """Schmaler Balken mit wanderndem Abschnitt (unbestimmter Fortschritt)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
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

    def __init__(self, parent=None, placer=None):
        super().__init__(parent)
        self.placer = placer  # setzt Lage und Breite vor dem Einblenden
        self._text = ""
        self.setObjectName("busy_bar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(10, 0, 10, 0)
        self.label = QLabel(self)
        self.label.setObjectName("busy_text")
        self.label.setAccessibleName("Ladeanzeige")
        # Langer Text wird gekürzt (…), der ganze steht im Hinweis
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
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
        self._text = "⏳  Lädt: " + "  ·  ".join(self.items) + " …"
        self._fit_text()
        self.setToolTip(self._text + "\n\nZeitzeuge liest gerade im Hintergrund. "
                        "Du kannst weiterarbeiten.")
        if self.isVisible():
            return
        if delay <= 0:
            self._delay.stop()
            self._reveal()
        elif not self._delay.isActive() or self._delay.remainingTime() > delay:
            self._delay.start(delay)

    def text(self):
        """Ganzer Text der Anzeige (auf dem Bildschirm evtl. gekürzt)."""
        return self._text

    def _fit_text(self):
        width = self.label.width() if self.isVisible() else self.width() - 20
        metrics = self.label.fontMetrics()
        text = self._text
        if metrics.horizontalAdvance(text) > width and width < 160:
            text = "⏳  Lädt …"  # sehr schmal: kurz statt "Lädt: 3C…"
            if metrics.horizontalAdvance(text) > width:
                text = "⏳"  # noch schmaler: nur Sanduhr, der Streifen läuft trotzdem
        self.label.setText(metrics.elidedText(text, Qt.ElideRight, max(width, 0)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_text()

    def _reveal(self):
        if self.items:
            if self.placer:
                self.placer()
            self.stripe.start()
            self.show()
            self.raise_()
            self._fit_text()
