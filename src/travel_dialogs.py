"""Einstellungen „Orte und Fahrzeiten“ (Fahrten vermutet): Schalter, Startadresse (Büro),
längste Fahrt und Orte mit fester Fahrzeit. Kunden-Adressen stehen in der Kundenliste."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from card_dialog import modernize
from theme import prose
import travel

HINT = ("Hat ein Outlook-Termin einen Ort (kein Teams, kein Link), ist die Zeit davor ohne Arbeit "
        "am PC vermutlich die Hinfahrt, die Zeit danach die Rückfahrt. Ebenso eine Lücke beim "
        "Wechsel in ein Kundennetz. Zeitzeuge fragt danach und schlägt „Fahrt / Reise“ vor.\n\n"
        "Kunden mit Adresse: In der Kundenliste berechnet „Berechnen“ die Fahrzeit vom Büro über "
        "OpenStreetMap (nur die beiden Adressen gehen nach außen). Ebenso, wenn im Ort des "
        "Termins selbst eine Adresse steht. Ohne bekannte Fahrzeit gilt für Hin- und Rückfahrt "
        "dieselbe Dauer (die kürzere Lücke).\n\n"
        "Unten trägst du weitere Orte und Kunden mit ihrer Fahrzeit ein. Steht der Name im Ort, im "
        "Betreff oder beim Kunden des Termins, gilt genau diese Fahrzeit. 0 Minuten heißt keine "
        "Fahrt, z. B. für euren Besprechungsraum oder das eigene Büro.")


class TravelSettingsDialog(QDialog):
    def __init__(self, config, customers=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Orte und Fahrzeiten")
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)

        self.enabled_box = QCheckBox("Fahrten vermuten und vorschlagen")
        self.enabled_box.setChecked(bool(config.get("travel_enabled", True)))
        layout.addWidget(self.enabled_box)
        hint = QLabel(HINT)
        hint.setWordWrap(True)
        prose(hint)
        layout.addWidget(hint)

        home = QHBoxLayout()
        home_label = QLabel("&Startadresse (Büro):")
        self.home_edit = QLineEdit(str(config.get("travel_home_address") or ""))
        self.home_edit.setPlaceholderText("Straße Nr., PLZ Ort")
        home_label.setBuddy(self.home_edit)
        home.addWidget(home_label)
        home.addWidget(self.home_edit, 1)
        layout.addLayout(home)
        self.route_box = QCheckBox("Fahrzeit zur &Adresse im Termin-Ort berechnen (OpenStreetMap)")
        self.route_box.setToolTip("Steht im Ort eines Outlook-Termins eine Adresse (Straße Nr. oder "
                                  "PLZ Ort), berechnet Zeitzeuge die Fahrzeit vom Büro dorthin. Nach "
                                  "außen gehen nur die beiden Adressen. Ändert sich die Adresse im "
                                  "Termin, wird neu berechnet.")
        self.route_box.setChecked(bool(config.get("travel_route_appointments", True)))
        layout.addWidget(self.route_box)

        row = QHBoxLayout()
        row.addWidget(QLabel("Unbekannte Orte: Fahrt höchstens"))
        self.max_spin = QSpinBox()
        self.max_spin.setRange(travel.MIN_MINUTES, 240)
        self.max_spin.setSuffix(" Min.")
        self.max_spin.setValue(int(config.get("travel_max_minutes", travel.MAX_MINUTES)))
        row.addWidget(self.max_spin)
        row.addStretch(1)
        layout.addLayout(row)

        layout.addWidget(QLabel("<b>Orte und Kunden mit Fahrzeit</b>"))
        add = QHBoxLayout()
        self.name_edit = QComboBox()  # Kunden zur Auswahl, eigener Ort frei eintippbar
        self.name_edit.setEditable(True)
        self.name_edit.addItems(list(customers))
        self.name_edit.setCurrentText("")
        self.name_edit.lineEdit().setPlaceholderText("Ort oder Kunde, z. B. Besprechungsraum")
        self.name_edit.setAccessibleName("Ort oder Kunde")
        add.addWidget(self.name_edit, 1)
        self.minutes_spin = QSpinBox()
        self.minutes_spin.setRange(0, 600)
        self.minutes_spin.setSuffix(" Min.")
        self.minutes_spin.setValue(15)
        self.minutes_spin.setAccessibleName("Fahrzeit in Minuten (0 = keine Fahrt)")
        add.addWidget(self.minutes_spin)
        add_button = QPushButton("&Hinzufügen")
        add_button.setAutoDefault(False)
        add_button.clicked.connect(self.add_place)
        add.addWidget(add_button)
        layout.addLayout(add)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Ort oder Kunde", "Fahrzeit (Min.)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(160)
        layout.addWidget(self.table)
        for place in travel.places_from_config(config):
            self._add_row(str(place.get("name", "")), place.get("minutes", 0))
        remove = QPushButton("&Entfernen")
        remove.setAutoDefault(False)
        remove.clicked.connect(self.remove_selected)
        row = QHBoxLayout()
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        modernize(self, "Orte und Fahrzeiten", "Woher Zeitzeuge Fahrten vor und nach Terminen vermutet.",
                  "map_pin", scroll=True)
        self.resize(self.width(), 640)

    def _add_row(self, name, minutes):
        try:
            minutes = max(0, int(minutes or 0))
        except (TypeError, ValueError):
            minutes = 0
        for r in range(self.table.rowCount()):  # gleicher Name: Fahrzeit ersetzen
            if self.table.item(r, 0).text().strip().lower() == name.strip().lower():
                self.table.item(r, 1).setData(Qt.EditRole, minutes)
                return
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(name))
        item = QTableWidgetItem()
        item.setData(Qt.EditRole, minutes)  # Zahl: Bearbeiten mit Drehfeld
        self.table.setItem(r, 1, item)

    def add_place(self):
        name = self.name_edit.currentText().strip()
        if not name:
            return
        self._add_row(name, self.minutes_spin.value())
        self.name_edit.setCurrentText("")
        self.name_edit.setFocus()

    def remove_selected(self):
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)

    def places(self):
        result = []
        for r in range(self.table.rowCount()):
            name = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            if not name:
                continue
            try:
                minutes = max(0, int(self.table.item(r, 1).data(Qt.EditRole) or 0))
            except (TypeError, ValueError, AttributeError):
                minutes = 0
            result.append({"name": name, "minutes": minutes})
        return result

    def values(self):
        return {"travel_enabled": self.enabled_box.isChecked(),
                "travel_home_address": " ".join(self.home_edit.text().split()),
                "travel_route_appointments": self.route_box.isChecked(),
                "travel_max_minutes": self.max_spin.value(),
                "travel_places": self.places(),
                "travel_ignore_locations": []}  # steckt jetzt in travel_places (0 Min.)
