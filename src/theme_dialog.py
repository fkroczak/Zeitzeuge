"""Dialog „Eigene Farben“ (Menü Ansicht → Design).

Man wählt nur wenige Grundfarben (theme.CUSTOM_KEYS), alle übrigen Farben leitet
theme.custom_theme ab. Jede Änderung ist sofort im Hauptfenster zu sehen;
Abbrechen stellt das vorherige Design wieder her.
"""
import copy

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

import icons
from theme import ACCENT_PRESETS, CUSTOM_KEYS, SPACE_S, default_custom_colors


class CustomColorsDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Eigene Farben")
        self.setMinimumWidth(780)  # Knöpfe der Akzentfarben nebeneinander, ohne abgeschnittenen Text
        self._before = {k: copy.deepcopy(main.config.get(k))
                        for k in ("custom_theme", "custom_colors", "dark_mode")}
        stored = main.config.get("custom_colors") or {}
        base = stored.get("base") or ("dark" if main.dark_mode else "light")
        self.colors = {**default_custom_colors(base), **stored}

        layout = QVBoxLayout(self)
        hint = QLabel("Wähle die Grundfarben. Alles andere (Rahmen, Auswahl, Hover) "
                      "passt Zeitzeuge daran an. Änderungen sind sofort zu sehen.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self.base_box = QComboBox()
        self.base_box.addItem("Dunkel (wie Chrome)", "dark")
        self.base_box.addItem("Hell", "light")
        self.base_box.setCurrentIndex(0 if self.colors["base"] == "dark" else 1)
        self.base_box.setAccessibleName("Grundlage")
        self.base_box.currentIndexChanged.connect(self._base_changed)
        form.addRow("&Grundlage:", self.base_box)

        self.buttons = {}
        for key, text in CUSTOM_KEYS:
            button = QPushButton()
            button.setAccessibleName(text)
            button.clicked.connect(lambda _c=False, k=key: self._pick(k))
            self.buttons[key] = button
            form.addRow(text + ":", button)

        presets = QWidget()
        row = QHBoxLayout(presets)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACE_S)
        for name, light, dark in ACCENT_PRESETS:
            b = QPushButton(name)
            b.setToolTip(f"Akzentfarbe {name}")
            b.clicked.connect(lambda _c=False, lt=light, dk=dark: self._set(
                "accent", dk if self.colors["base"] == "dark" else lt))
            row.addWidget(b)
        row.addStretch()
        form.addRow("Akzent schnell:", presets)
        layout.addLayout(form)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        reset = box.addButton("&Zurücksetzen", QDialogButtonBox.ResetRole)
        reset.setToolTip("Grundfarben des Standard-Designs übernehmen")
        reset.clicked.connect(lambda: self._load(default_custom_colors(self.colors["base"])))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

        self._refresh_buttons()
        self._apply()

    def _refresh_buttons(self):
        for key, button in self.buttons.items():
            value = QColor(self.colors[key]).name().upper()
            button.setText(value)
            button.setIcon(icons.dot(value, 16))

    def _apply(self):
        cfg = self.main.config
        cfg["custom_colors"] = dict(self.colors)
        cfg["custom_theme"] = True
        self.main.set_theme("custom", save=False)

    def _load(self, colors):
        self.colors = dict(colors)
        self._refresh_buttons()
        self._apply()

    def _set(self, key, value):
        self.colors[key] = QColor(value).name().upper()
        self._refresh_buttons()
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
