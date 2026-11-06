"""Ladeanzeige: zeigt gut sichtbar, was gerade geladen wird.

Zwei Teile, beide schwebend, damit Ein- und Ausblenden nichts verschiebt:
- in der Werkzeugleiste rechts neben „Arbeitszeit“ ein drehender Kreis mit Text,
  z. B. "Lädt: 3CX-Anrufe · KI-Vorschläge (Claude ordnet 25.10. ein) …"
  (Lage setzt place_busy_bar im Hauptfenster),
- ein dünner laufender Streifen über die ganze Fensterbreite, oben über der Timeline.
Erscheint erst nach kurzer Verzögerung, damit kurze Lesevorgänge nicht flackern.
"""
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget
from theme import SPACE_XS, SPACE_S


class _Stripe(QWidget):
    """Schmaler Balken mit wanderndem Abschnitt (unbestimmter Fortschritt).

    Liegt über dem Fensterinhalt und nimmt keine Mausklicks an."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(3)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.color = QColor("#0067C0")
        self._pos = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self.hide()

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
        x = (self._pos - 0.3) * w
        p.fillRect(QRectF(x, 0, w * 0.3, self.height()), self.color)
        p.end()


class _Spinner(QWidget):
    """Drehender Ring (Donut) mit einem Bogen in der Akzentfarbe."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.color = QColor("#0067C0")
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)

    def start(self):
        if not self._timer.isActive():
            self._timer.start(30)

    def stop(self):
        self._timer.stop()

    def _step(self):
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        track = QColor(self.color)
        track.setAlpha(50)
        pen = QPen(track, 2.5)
        p.setPen(pen)
        p.drawEllipse(rect)
        pen.setColor(self.color)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, -self._angle * 16, 100 * 16)  # Qt: Winkel in 1/16 Grad
        p.end()


class BusyBar(QWidget):
    SHOW_DELAY = 300  # ms: erst zeigen, wenn es wirklich etwas dauert

    def __init__(self, parent=None, placer=None, stripe_parent=None):
        super().__init__(parent)
        self.placer = placer  # setzt Lage und Breite (Kreis + Streifen) vor dem Einblenden
        self._text = ""
        self.setObjectName("busy_bar")
        row = QHBoxLayout(self)
        row.setContentsMargins(SPACE_XS, 0, SPACE_XS, 0)
        row.setSpacing(SPACE_S)
        self.spinner = _Spinner(self)
        row.addWidget(self.spinner, 0, Qt.AlignVCenter)
        self.label = QLabel(self)
        self.label.setObjectName("busy_text")
        self.label.setAccessibleName("Ladeanzeige")
        # Langer Text wird gekürzt (…), der ganze steht im Hinweis
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row.addWidget(self.label, 1)
        self.stripe = _Stripe(stripe_parent or self)
        self.items = []
        self._delay = QTimer(self)
        self._delay.setSingleShot(True)
        self._delay.timeout.connect(self._reveal)
        self.hide()

    def set_color(self, color):
        for part in (self.stripe, self.spinner):
            part.color = QColor(color)
            part.update()

    def set_items(self, items, delay=SHOW_DELAY):
        """Was gerade lädt, z. B. ["3CX-Anrufe", "ITM-Zeiterfassung"]. Leer = ausblenden.

        delay: so viele ms warten, bevor die Anzeige erscheint (0 = sofort)."""
        self.items = list(items)
        if not self.items:
            self._delay.stop()
            self.stripe.stop()
            self.spinner.stop()
            self.stripe.hide()
            self.hide()
            return
        self._text = "Lädt: " + "  ·  ".join(self.items) + " …"
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
        width = self.label.width() if self.isVisible() else self.width() - 32
        metrics = self.label.fontMetrics()
        text = self._text
        if metrics.horizontalAdvance(text) > width and width < 160:
            text = "Lädt …"  # sehr schmal: kurz statt "Lädt: 3C…"
            if metrics.horizontalAdvance(text) > width:
                text = ""  # noch schmaler: nur der Kreis, der Streifen läuft trotzdem
        self.label.setText(metrics.elidedText(text, Qt.ElideRight, max(width, 0)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_text()

    def _reveal(self):
        if self.items:
            if self.placer:
                self.placer()
            self.spinner.start()
            self.stripe.start()
            self.show()
            self.raise_()
            self.stripe.show()
            self.stripe.raise_()
            self._fit_text()
