"""Fenster während eines Updates: großer drehender Ring, was gerade passiert, Fortschritt.

Erscheint sofort beim Klick auf „Jetzt aktualisieren“ (app_update.py) und bleibt bis zum Beenden:
  Laden … 42 %  ->  Setup wird geprüft …  ->  Zeitzeuge wird beendet …
Danach zeigt das Setup seinen eigenen Fortschritt und startet Zeitzeuge wieder.
Abbrechen geht nur, solange geladen wird.
"""
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
                               QWidget)

from prompt_card import _floating, _theme_colors
from theme import SPACE_M, SPACE_S


class BigSpinner(QWidget):
    """Großer drehender Ring (Donut) mit Bogen in der Akzentfarbe."""

    def __init__(self, size=56, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.color = QColor("#0067C0")
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(16)

    def _step(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, _event):
        width = max(4.0, self.width() / 11)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(width, width, -width, -width)
        track = QColor(self.color)
        track.setAlpha(45)
        pen = QPen(track, width)
        p.setPen(pen)
        p.drawEllipse(rect)
        pen.setColor(self.color)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, -self._angle * 16, 110 * 16)  # Qt: Winkel in 1/16 Grad
        p.end()


class UpdateProgress(QDialog):
    """Karte in der Bildschirmmitte, über allen Fenstern. cancelled: Abbrechen gedrückt."""

    cancelled = Signal()
    WIDTH = 420

    def __init__(self, version, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        outer, card = _floating(self, f"Zeitzeuge: Update auf {version}", "prompt_window",
                                "prompt_card", self.WIDTH)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        _text, accent, _muted = _theme_colors(parent or self)
        outer.addWidget(card)
        box = QVBoxLayout(card)
        box.setContentsMargins(20, 22, 20, 18)
        box.setSpacing(SPACE_M)

        head = QHBoxLayout()
        head.setSpacing(SPACE_M + 4)
        self.spinner = BigSpinner(56)
        self.spinner.color = QColor(accent)
        head.addWidget(self.spinner, 0, Qt.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = QLabel(f"Update auf {version}")
        self.title.setObjectName("prompt_title")
        self.step = QLabel("Update wird geladen …")
        self.step.setWordWrap(True)
        self.step.setAccessibleName("Stand des Updates")
        hint = QLabel("Deine Daten bleiben erhalten. Zeitzeuge beendet sich gleich, "
                      "installiert das Update und startet von selbst wieder.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        texts.addWidget(self.title)
        texts.addWidget(self.step)
        texts.addSpacing(SPACE_S)
        texts.addWidget(hint)
        head.addLayout(texts, 1)
        box.addLayout(head)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setRange(0, 0)  # unbestimmt, bis die Größe bekannt ist
        self.bar.setAccessibleName("Fortschritt des Updates")
        c = QColor(accent)
        self.bar.setStyleSheet(
            f"QProgressBar {{ border: none; border-radius: 3px; "
            f"background: rgba({c.red()}, {c.green()}, {c.blue()}, 45); }}"
            f"QProgressBar::chunk {{ border-radius: 3px; background: {accent}; }}")
        box.addWidget(self.bar)

        foot = QHBoxLayout()
        foot.addStretch(1)
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self._cancel)
        foot.addWidget(self.cancel_button)
        box.addLayout(foot)

    def showEvent(self, event):
        super().showEvent(event)
        screen = (self.parentWidget().screen() if self.parentWidget() else None) \
            or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(area.center() - self.rect().center())

    def set_progress(self, done, total):
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(min(1000, done * 1000 // total))
            mb = 1024 * 1024
            self.step.setText(f"Update wird geladen … {done * 100 // total} %  "
                              f"({done / mb:.0f} von {total / mb:.0f} MB)")

    def set_step(self, text, can_cancel=False):
        """Nächster Schritt ohne messbaren Fortschritt (Ring dreht, Balken läuft)."""
        self.step.setText(text)
        self.bar.setRange(0, 0)
        self.cancel_button.setVisible(can_cancel)

    def _cancel(self):
        self.cancel_button.setEnabled(False)
        self.step.setText("Wird abgebrochen …")
        self.cancelled.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.cancel_button.isVisible() and self.cancel_button.isEnabled():
                self._cancel()
            return  # Esc schließt das Fenster nie einfach so
        super().keyPressEvent(event)

    def reject(self):
        pass  # nur über Abbrechen oder das Ende des Updates
