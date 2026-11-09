"""Dialog „Eigene Farben“ (Menü Ansicht → Design).

Oben die Grundlage (Hell/Dunkel), darunter eine Skizze von Zeitzeuge (theme_mockup).
Klick auf einen Bereich der Skizze öffnet dort ein Menü mit Farbvorschlägen (theme.SWATCHES),
„Andere Farbe …“ und „Standardfarbe“. Man wählt nur wenige Grundfarben (theme.CUSTOM_KEYS),
alle übrigen leitet theme.custom_theme ab. Jede Änderung ist sofort im Hauptfenster zu sehen;
Abbrechen stellt das vorherige Design wieder her.
"""
import copy

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
                               QHBoxLayout, QLabel, QMenu, QToolButton, QVBoxLayout, QWidget,
                               QWidgetAction)

from theme import CUSTOM_KEYS, SPACE_S, SWATCHES, default_custom_colors
from theme_mockup import ThemeMockup

SWATCH_COLUMNS = 4


def swatch_icon(color, selected=False, size=22):
    """Farbfeld fürs Menü; die gewählte Farbe mit Ring."""
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


class CustomColorsDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Eigene Farben")
        self.setMinimumWidth(720)  # Skizze gut lesbar
        self._before = {k: copy.deepcopy(main.config.get(k))
                        for k in ("custom_theme", "custom_colors", "dark_mode")}
        stored = main.config.get("custom_colors") or {}
        base = stored.get("base") or ("dark" if main.dark_mode else "light")
        self.colors = {**default_custom_colors(base), **stored}

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        label = QLabel("&Grundlage:")
        self.base_box = QComboBox()
        self.base_box.addItem("Dunkel", "dark")
        self.base_box.addItem("Hell", "light")
        self.base_box.setCurrentIndex(0 if self.colors["base"] == "dark" else 1)
        self.base_box.setAccessibleName("Grundlage")
        self.base_box.currentIndexChanged.connect(self._base_changed)
        label.setBuddy(self.base_box)
        top.addWidget(label)
        top.addWidget(self.base_box)
        top.addStretch()
        layout.addLayout(top)
        hint = QLabel("Klick auf einen Bereich, um seine Farbe zu ändern (Tastatur: Pfeiltasten, "
                      "dann Eingabe). Rahmen, Auswahl und Hover passt Zeitzeuge daran an.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.mockup = ThemeMockup(self)
        self.mockup.picked.connect(self.show_color_menu)
        layout.addWidget(self.mockup, 1)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        reset = box.addButton("&Zurücksetzen", QDialogButtonBox.ResetRole)
        reset.setToolTip("Alle Farben des Standard-Designs übernehmen")
        reset.clicked.connect(lambda: self._load(default_custom_colors(self.colors["base"])))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

        self.mockup.set_colors(self.colors)
        self._apply()

    # ---- Menü mit Farben für einen Bereich

    def color_menu(self, key):
        """Menü für eine Grundfarbe: Vorschläge als Farbfelder, andere Farbe, Standardfarbe."""
        menu = QMenu(self)
        title = menu.addAction(dict(CUSTOM_KEYS)[key])
        title.setEnabled(False)
        grid_box = QWidget(menu)
        grid = QGridLayout(grid_box)
        grid.setContentsMargins(SPACE_S, 0, SPACE_S, SPACE_S // 2)
        grid.setSpacing(2)
        current = QColor(self.colors[key]).name().upper()
        menu.swatches = []
        for i, color in enumerate(SWATCHES[self.colors["base"]][key]):
            button = QToolButton(grid_box)
            button.setAutoRaise(True)
            button.setIcon(swatch_icon(color, color.upper() == current))
            button.setIconSize(QSize(22, 22))
            button.setToolTip(color)
            button.setAccessibleName(f"Farbe {color}")
            button.clicked.connect(lambda _c=False, c=color: (self._set(key, c), menu.close()))
            grid.addWidget(button, i // SWATCH_COLUMNS, i % SWATCH_COLUMNS)
            menu.swatches.append((color, button))
        swatches = QWidgetAction(menu)
        swatches.setDefaultWidget(grid_box)
        menu.addAction(swatches)
        menu.addSeparator()
        menu.addAction("&Andere Farbe …", lambda: self._pick(key))
        default = default_custom_colors(self.colors["base"])[key]
        menu.addAction("&Standardfarbe", lambda: self._set(key, default)).setEnabled(
            current != default.upper())
        return menu

    def show_color_menu(self, key, global_pos):
        self.color_menu(key).popup(global_pos)

    # ---- Farben setzen

    def _apply(self):
        cfg = self.main.config
        cfg["custom_colors"] = dict(self.colors)
        cfg["custom_theme"] = True
        self.main.set_theme("custom", save=False)

    def _load(self, colors):
        self.colors = dict(colors)
        self.mockup.set_colors(self.colors)
        self._apply()

    def _set(self, key, value):
        self.colors[key] = QColor(value).name().upper()
        self.mockup.set_colors(self.colors)
        self._apply()

    def _base_changed(self):
        # Neue Grundlage: Farben des passenden Standard-Designs, sonst passt Schrift nicht zum Grund
        self._load(default_custom_colors(self.base_box.currentData()))

    def _pick(self, key):
        color = QColorDialog.getColor(QColor(self.colors[key]), self, dict(CUSTOM_KEYS)[key])
        if color.isValid():
            self._set(key, color.name())

    def accept(self):
        self.main.set_theme("custom")
        super().accept()

    def reject(self):
        self.main.config.update(self._before)
        self.main.set_theme("custom" if self._before["custom_theme"] else
                            ("dark" if self._before["dark_mode"] else "light"))
        super().reject()
