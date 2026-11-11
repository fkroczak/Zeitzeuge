"""Hinweise im Stil der Nachfrage statt Windows-Sprechblasen (prompt_card.py).

- NoticeCard: Karte unten rechts mit Kopf, kurzer Liste und genau einer Hauptaktion
  (Feierabend: „Tagesabschluss öffnen“, „Nachtragen“, „Wochenabschluss“).
- NoticeStrip: eine Zeile wie die Leiste der Nachfrage, mit Aktion daneben („Anmelden“, „Prüfen“)
  und ✕ (Anmeldung nötig, ITM prüfen, Leser-Störung, Probleme, „Zeitzeuge läuft weiter“).

Beide nehmen den Fokus nicht weg, blenden nach timeout Sekunden aus (0 = bleibt) und halten an,
solange die Maus darüber ist. Signal acted: Hauptaktion gewählt, closed: geschlossen/ausgeblendet.
Farbe nur für den Zustand: Warnung (gelb) oder Info (blau) an der Kachel links.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QToolButton,
                               QVBoxLayout, QWidget)

import icons
import theme
from prompt_card import _AutoHide, _Dock, _ElidedLabel, _TimerBar, _floating, _icon_label, _theme_colors
from theme import fit_text, SPACE_M, SPACE_S, SPACE_XS


def _tile(kind, size, round_):
    tile = QLabel()
    tile.setObjectName("notice_warn" if kind == "warn" else "notice_info")
    tile.setProperty("round", round_)
    tile.setFixedSize(size, size)
    tile.setContentsMargins((size - 18) // 2, (size - 18) // 2, 0, 0)
    tile.setPixmap(icons.icon("alert" if kind == "warn" else "info", _tile_color(kind)).pixmap(18, 18))
    return tile


def _tile_color(kind):
    """Icon-Farbe passend zur Kachel (Token rate_mid_text bzw. seltext des aktuellen Designs)."""
    window = QApplication.palette().color(QPalette.Window)
    tokens = theme.THEMES["dark" if window.lightness() < 128 else "light"]
    return tokens["rate_mid_text" if kind == "warn" else "seltext"]


class _Notice(_AutoHide, _Dock):
    acted = Signal()
    closed = Signal()

    def _finish(self, signal):
        if getattr(self, "_done", False):
            return
        self._done = True
        self._hide_timer.stop()
        signal.emit()
        self.close()
        self.deleteLater()

    def _timed_out(self):
        self._finish(self.closed)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._finish(self.closed)
            return
        super().keyPressEvent(event)



class NoticeCard(_Notice, QDialog):
    """Karte mit Titel, Satz, kurzer Liste (höchstens 4) und einer Hauptaktion."""

    WIDTH = 440

    def __init__(self, title, text, items=(), action="", kind="warn", timeout=15, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        outer, card = _floating(self, f"Zeitzeuge: {title}", "prompt_window", "prompt_card", self.WIDTH)
        _text, _accent, muted = _theme_colors(parent or self)
        outer.addWidget(card)
        box = QVBoxLayout(card)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)

        top = QWidget()
        top.setObjectName("prompt_top")
        top.setAttribute(Qt.WA_StyledBackground)
        head_box = QVBoxLayout(top)
        head_box.setContentsMargins(16, SPACE_M, 16, SPACE_M)
        head_box.setSpacing(SPACE_S)
        app_row = QHBoxLayout()
        app_name = QLabel("Zeitzeuge")
        app_name.setObjectName("hint")
        app_row.addWidget(app_name)
        app_row.addStretch(1)
        close = QToolButton()
        close.setObjectName("prompt_tool")
        close.setIcon(icons.icon("close", muted))
        close.setFocusPolicy(Qt.TabFocus)  # kein Fokusrahmen beim Erscheinen
        close.setAccessibleName("Hinweis schließen")
        close.setToolTip("Schließen (Esc)")
        close.clicked.connect(lambda: self._finish(self.closed))
        app_row.addWidget(close)
        head_box.addLayout(app_row)
        head = QHBoxLayout()
        head.setSpacing(SPACE_M)
        head.addWidget(_tile(kind, 36, False), 0, Qt.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("prompt_title")
        self.title.setWordWrap(True)
        self.text = QLabel(text)
        self.text.setObjectName("hint")
        self.text.setWordWrap(True)
        self.text.setVisible(bool(text))
        texts.addWidget(self.title)
        texts.addWidget(self.text)
        head.addLayout(texts, 1)
        head_box.addLayout(head)
        box.addWidget(top)

        if items:
            body = QWidget()
            body.setObjectName("prompt_body")
            rows = QVBoxLayout(body)
            rows.setContentsMargins(16, SPACE_S + 2, 16, SPACE_S + 2)
            rows.setSpacing(SPACE_XS + 2)
            for item in list(items)[:4]:
                line = QHBoxLayout()
                line.setSpacing(SPACE_S)
                line.addWidget(_icon_label("alert", muted, 14), 0, Qt.AlignTop)
                label = QLabel(item)
                label.setWordWrap(True)
                line.addWidget(label, 1)
                rows.addLayout(line)
            if len(items) > 4:
                more = QLabel(f"und {len(items) - 4} weitere")
                more.setObjectName("hint")
                rows.addWidget(more)
            box.addWidget(body)

        foot = QWidget()
        foot.setObjectName("prompt_foot")
        foot.setAttribute(Qt.WA_StyledBackground)
        foot_box = QHBoxLayout(foot)
        foot_box.setContentsMargins(16, SPACE_S + 2, 16, SPACE_S + 2)
        foot_box.setSpacing(SPACE_S)
        foot_box.addStretch(1)
        later = QPushButton("Schließen")
        later.setAutoDefault(False)
        later.clicked.connect(lambda: self._finish(self.closed))
        foot_box.addWidget(later)
        self.action_button = None
        if action:
            self.action_button = QPushButton(action)
            fit_text(self.action_button)  # nie schmaler als der Text
            self.action_button.setDefault(True)
            self.action_button.clicked.connect(lambda: self._finish(self.acted))
            foot_box.addWidget(self.action_button)
        box.addWidget(foot)
        bar = _TimerBar()
        box.addWidget(bar)
        self._setup_autohide(timeout, True, bar)


class NoticeStrip(_Notice, QWidget):
    """Eine Zeile: Kachel, Titel und Satz, Aktion, ✕."""

    WIDTH = 460

    def __init__(self, title, text, action="", kind="warn", timeout=15, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        outer, strip = _floating(self, f"Zeitzeuge: {title}", "prompt_strip_window", "prompt_strip", self.WIDTH)
        _text, _accent, muted = _theme_colors(parent or self)
        outer.addWidget(strip)
        col = QVBoxLayout(strip)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(SPACE_M, SPACE_S + 2, SPACE_S, SPACE_S + 2)
        row.setSpacing(SPACE_M)
        row.addWidget(_tile(kind, 30, True))
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.title = _ElidedLabel(title)
        self.title.setObjectName("prompt_strip_title")
        self.text = _ElidedLabel(text)
        self.text.setObjectName("hint")
        texts.addWidget(self.title)
        texts.addWidget(self.text)
        row.addLayout(texts, 1)
        self.action_button = None
        if action:
            self.action_button = QPushButton(action)
            self.action_button.setObjectName("strip_action")
            fit_text(self.action_button)
            self.action_button.setAutoDefault(False)
            self.action_button.clicked.connect(lambda: self._finish(self.acted))
            row.addWidget(self.action_button)
        close = QToolButton()
        close.setObjectName("prompt_tool")
        close.setIcon(icons.icon("close", muted))
        close.setFocusPolicy(Qt.TabFocus)  # kein Fokusrahmen beim Erscheinen
        close.setAccessibleName("Hinweis schließen")
        close.setToolTip("Schließen (Esc)")
        close.clicked.connect(lambda: self._finish(self.closed))
        row.addWidget(close)
        col.addLayout(row)
        bar = _TimerBar()
        bar_row = QHBoxLayout()
        bar_row.setContentsMargins(24, 0, 24, 2)
        bar_row.addWidget(bar)
        col.addLayout(bar_row)
        self._setup_autohide(timeout, True, bar)
