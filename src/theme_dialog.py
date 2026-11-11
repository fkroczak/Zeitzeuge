"""„Eigene Farben“ im Einstellungsfenster (Seite „Darstellung“, unter der Kachel Eigene Farben).

Oben die Grundlage (Hell/Dunkel), darunter eine Skizze von Zeitzeuge (theme_mockup).
Klick auf einen Bereich der Skizze zeigt darunter die Farbvorschläge (theme.SWATCHES),
„Andere Farbe …“ und „Standardfarbe“. Klick auf einen Balken der Timeline ändert die Farbe
dieser Zeile wie Rechtsklick auf die Legende (config["row_colors"], Anrufe config["call_colors"]). Man wählt nur wenige Grundfarben (theme.CUSTOM_KEYS),
alle übrigen leitet theme.custom_theme ab. Jede Änderung ist sofort im Hauptfenster zu sehen.
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QColorDialog, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout,
                               QWidget)

from theme import BAR_SWATCHES, CUSTOM_KEYS, SPACE_S, SWATCHES, default_custom_colors
from theme_mockup import BAR_NAMES, ThemeMockup
from timeline_only import DEFAULT_CALL_COLORS


def swatch_icon(color, selected=False, size=22):
    """Farbfeld; die gewählte Farbe mit Haken."""
    pix = QPixmap(size * 2, size * 2)
    pix.setDevicePixelRatio(2)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    fill = QColor(color)
    p.setPen(QPen(QColor("#888888"), 1))
    p.setBrush(fill)
    p.drawRoundedRect(3, 3, size - 6, size - 6, 4, 4)
    if selected:
        p.setPen(QPen(QColor("#FFFFFF" if fill.lightness() < 128 else "#000000"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawLine(7, size // 2, size // 2 - 1, size - 8)
        p.drawLine(size // 2 - 1, size - 8, size - 7, 7)
    p.end()
    return QIcon(pix)


class CustomColorsPanel(QWidget):
    """Eigene Farben direkt im Einstellungsfenster (Seite „Darstellung“, unter der Kachel).

    Grundlage Hell/Dunkel, die Skizze von Zeitzeuge (theme_mockup) und darunter die Farbvorschläge
    für den angeklickten Bereich. Jede Änderung gilt sofort; „Standardfarbe“ und „Alle Farben
    zurücksetzen“ holen die Farben des Standard-Designs zurück."""

    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        self.setObjectName("custom_colors")
        stored = main.config.get("custom_colors") or {}
        base = stored.get("base") or ("dark" if main.dark_mode else "light")
        self.colors = {**default_custom_colors(base), **stored}
        self.area = "accent"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, SPACE_S, 0, 0)
        layout.setSpacing(SPACE_S)
        top = QHBoxLayout()
        top.setSpacing(6)
        label = QLabel("Grundlage")
        label.setObjectName("prompt_label")
        top.addWidget(label)
        self.base_buttons = {}
        for key, text in (("light", "He&ll"), ("dark", "D&unkel")):
            button = QToolButton()
            button.setObjectName("chip")
            button.setText(text)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setChecked(self.colors["base"] == key)
            button.setAccessibleName(f"Grundlage {text.replace('&', '')}")
            button.clicked.connect(lambda _c=False, k=key: self.set_base(k))
            top.addWidget(button)
            self.base_buttons[key] = button
        top.addStretch(1)
        layout.addLayout(top)
        hint = QLabel("Klick auf einen Bereich der Skizze (Tastatur: Pfeiltasten, dann Eingabe). "
                      "Rahmen, Auswahl und Hover passt Zeitzeuge daran an. Gilt sofort.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.mockup = ThemeMockup(self, skeleton=True)
        self.mockup.setMaximumWidth(620)
        self.mockup.setAccessibleName("Skizze von Zeitzeuge: Bereich für die Farbe wählen")
        self.mockup.picked.connect(lambda key, _pos: self.select(key))
        layout.addWidget(self.mockup)

        self.area_label = QLabel()
        self.area_label.setObjectName("prompt_label")
        layout.addWidget(self.area_label)
        row = QHBoxLayout()
        row.setSpacing(2)
        self.swatch_row = QHBoxLayout()
        self.swatch_row.setSpacing(2)
        row.addLayout(self.swatch_row)
        row.addSpacing(SPACE_S)
        self.other_button = QPushButton("&Andere Farbe …")
        self.other_button.setAutoDefault(False)
        self.other_button.clicked.connect(self.pick_other)
        row.addWidget(self.other_button)
        self.default_button = QPushButton("&Standardfarbe")
        self.default_button.setAutoDefault(False)
        self.default_button.clicked.connect(self.reset_area)
        row.addWidget(self.default_button)
        row.addStretch(1)
        layout.addLayout(row)
        self.reset_button = QPushButton("Alle Farben &zurücksetzen")
        self.reset_button.setObjectName("quiet_button")
        self.reset_button.setAutoDefault(False)
        self.reset_button.setToolTip("Alle Farben des Standard-Designs übernehmen")
        self.reset_button.clicked.connect(lambda: self._load(default_custom_colors(self.colors["base"])))
        layout.addWidget(self.reset_button, 0, Qt.AlignLeft)

        self.mockup.set_colors(self.colors)
        self.mockup.set_bar_colors(self.bar_colors())
        self.select(self.area)

    # ---- Bereich wählen: Farbvorschläge darunter

    def select(self, key):
        self.area = key
        bar = key in BAR_NAMES
        self.area_label.setText(f"Balken {BAR_NAMES[key]}" if bar else dict(CUSTOM_KEYS)[key])
        while self.swatch_row.count():
            widget = self.swatch_row.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        current = self.current(key)
        self.swatches = []
        for color in (BAR_SWATCHES if bar else SWATCHES[self.colors["base"]][key]):
            button = QToolButton()
            button.setObjectName("swatch")
            button.setAutoRaise(True)
            button.setIcon(swatch_icon(color, color.upper() == current))
            button.setIconSize(QSize(24, 24))
            button.setToolTip(color)
            button.setAccessibleName(f"Farbe {color}")
            button.clicked.connect(lambda _c=False, c=color: self.set_color(self.area, c))
            self.swatch_row.addWidget(button)
            self.swatches.append((color, button))
        if bar:
            self.default_button.setEnabled(self._bar_default(key)[1])
        else:
            self.default_button.setEnabled(current != default_custom_colors(self.colors["base"])[key].upper())

    def current(self, key):
        return QColor(self.bar_colors()[key] if key in BAR_NAMES else self.colors[key]).name().upper()

    def set_color(self, key, color):
        if key in BAR_NAMES:
            self._set_bar(key, color)
        else:
            self._set(key, color)
        self.select(key)

    def pick_other(self):
        title = f"Balken {BAR_NAMES[self.area]}" if self.area in BAR_NAMES else dict(CUSTOM_KEYS)[self.area]
        color = QColorDialog.getColor(QColor(self.current(self.area)), self, title)
        if color.isValid():
            self.set_color(self.area, color.name())

    def reset_area(self):
        if self.area in BAR_NAMES:
            self._set_bar(self.area, None)
            self.select(self.area)
        else:
            self.set_color(self.area, default_custom_colors(self.colors["base"])[self.area])

    def set_base(self, base):
        # Neue Grundlage: Farben des passenden Standard-Designs, sonst passt Schrift nicht zum Grund
        self.base_buttons[base].setChecked(True)
        self._load(default_custom_colors(base))

    # ---- Balken der Timeline (Zeilenfarben, gelten sofort wie per Rechtsklick auf die Legende)

    def bar_colors(self):
        """Aktuelle Farbe je Balken der Skizze, wie die Timeline sie zeichnet."""
        out = {}
        for key in BAR_NAMES:
            parts = key.split(":")
            out[key] = (self.main.call_color(parts[2]) if parts[1] == "call"
                        else self.main.row_color(parts[1]))
        return out

    def _bar_default(self, key):
        """Standardfarbe des Balkens und ob gerade eine eigene Farbe gilt."""
        parts = key.split(":")
        cfg = self.main.config
        if parts[1] == "call":
            own = parts[2] in (cfg.get("call_colors") or {}) or "call" in (cfg.get("row_colors") or {})
            return DEFAULT_CALL_COLORS[parts[2]], own
        return None, parts[1] in (cfg.get("row_colors") or {})

    def _set_bar(self, key, color):
        """color None = Standardfarbe."""
        parts = key.split(":")
        if parts[1] == "call":
            self.main.set_call_color(parts[2], color or DEFAULT_CALL_COLORS[parts[2]])
        else:
            self.main.set_row_color(parts[1], color)
        self.mockup.set_bar_colors(self.bar_colors())

    # ---- Grundfarben

    def _apply(self):
        cfg = self.main.config
        cfg["custom_colors"] = dict(self.colors)
        cfg["custom_theme"] = True
        self.main.set_theme("custom")

    def _load(self, colors):
        self.colors = dict(colors)
        self.mockup.set_colors(self.colors)
        self._apply()
        self.select(self.area)

    def _set(self, key, value):
        self.colors[key] = QColor(value).name().upper()
        self.mockup.set_colors(self.colors)
        self._apply()
