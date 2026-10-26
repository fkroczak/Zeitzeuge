"""Einstellungen: Abrechnungstakt (Standard und Ausnahmen je Kunde). Logik in billing.py."""

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QSpinBox, QTableWidget,
                               QVBoxLayout)

import billing

MODE_ITEMS = [("up", "Angefangener Takt zählt (aufrunden)"),
              ("nearest", "Auf den nächsten Takt runden"),
              ("off", "Ohne Takt (echte Dauer)")]


def _mode_combo(mode, name):
    combo = QComboBox()
    for key, text in MODE_ITEMS:
        combo.addItem(text, key)
    combo.setCurrentIndex(max(0, combo.findData(mode)))
    combo.setAccessibleName(name)
    return combo


def _step_spin(step, name):
    spin = QSpinBox()
    spin.setRange(1, 480)
    spin.setSuffix(" min")
    spin.setValue(int(step))
    spin.setAccessibleName(name)
    return spin


class BillingDialog(QDialog):
    """Abrechnungstakt: Standard für alle Kunden und Ausnahmen je Kunde."""

    def __init__(self, config, customers=(), parent=None):
        super().__init__(parent)
        self.config = config
        self.customers = [c for c in customers if c]
        rules = billing.Billing.from_config(config)
        self.setWindowTitle("Abrechnung")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        info = QLabel("Zeitzeuge zeigt beim Kopieren und in der Ansicht „Dokumentation“ auch die "
                      "abgerechnete Zeit. Standard: Jede angefangene Viertelstunde wird abgerechnet. "
                      "Jede Tätigkeit wird für sich gerundet.")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        step, mode = rules.default
        self.step = _step_spin(step, "Abrechnungstakt für alle Kunden")
        form.addRow("&Takt für alle Kunden:", self.step)
        self.mode = _mode_combo(mode, "Rundung für alle Kunden")
        form.addRow("&Rundung:", self.mode)
        self.example = QLabel()
        self.example.setObjectName("hint")
        form.addRow("", self.example)
        layout.addLayout(form)

        head = QLabel("&Ausnahmen je Kunde:")
        layout.addWidget(head)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Kunde", "Takt", "Rundung"])
        self.table.setAccessibleName("Ausnahmen je Kunde")
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(30)
        head.setBuddy(self.table)
        layout.addWidget(self.table)

        row = QHBoxLayout()
        add = QPushButton("Kunde &hinzufügen")
        add.clicked.connect(lambda: self.add_row())
        self.remove_button = QPushButton("Ausnahme &entfernen")
        self.remove_button.clicked.connect(self.remove_row)
        row.addWidget(add)
        row.addWidget(self.remove_button)
        row.addStretch(1)
        layout.addLayout(row)
        self.error = QLabel()
        self.error.setObjectName("hint")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        layout.addWidget(buttons)
        for key, (s, m) in rules.customers.items():
            self.add_row(rules.names[key], s, m)
        self.step.valueChanged.connect(self.validate)
        self.mode.currentIndexChanged.connect(self.validate)
        self.validate()

    def add_row(self, customer="", step=None, mode=None):
        step = step or self.step.value()
        mode = mode or self.mode.currentData()
        r = self.table.rowCount()
        self.table.insertRow(r)
        name = QComboBox()
        name.setEditable(True)
        name.setInsertPolicy(QComboBox.NoInsert)
        name.addItems([""] + self.customers)
        name.setCurrentText(customer)
        name.lineEdit().setPlaceholderText("Kunde wie im Eintragen-Dialog")
        name.setAccessibleName(f"Kunde, Zeile {r + 1}")
        name.lineEdit().setAccessibleName(f"Kunde, Zeile {r + 1}")
        name.currentTextChanged.connect(self.validate)
        spin = _step_spin(step, f"Takt, Zeile {r + 1}")
        combo = _mode_combo(mode, f"Rundung, Zeile {r + 1}")
        combo.currentIndexChanged.connect(lambda _i, s=spin, c=combo: s.setEnabled(c.currentData() != "off"))
        spin.setEnabled(mode != "off")
        self.table.setCellWidget(r, 0, name)
        self.table.setCellWidget(r, 1, spin)
        self.table.setCellWidget(r, 2, combo)
        if not customer:
            name.setFocus()
        self.validate()

    def remove_row(self):
        r = self.table.currentRow()
        if r < 0:
            r = self.table.rowCount() - 1
        if r >= 0:
            self.table.removeRow(r)
        self.validate()

    def rows(self):
        """[(Kunde, Takt, Modus)] aus der Tabelle (leere Kunden fehlen)."""
        result = []
        for r in range(self.table.rowCount()):
            name = self.table.cellWidget(r, 0).currentText().strip()
            if name:
                result.append((name, self.table.cellWidget(r, 1).value(),
                               self.table.cellWidget(r, 2).currentData()))
        return result

    def validate(self, *_):
        self.step.setEnabled(self.mode.currentData() != "off")
        rules = self.result()
        self.example.setText("Beispiel: 12 min" + (rules.note(12 * 60) or " werden als 12 min abgerechnet"))
        names = [n.casefold() for n, _s, _m in self.rows()]
        dupes = sorted({n for n in names if names.count(n) > 1})
        self.error.setText("⚠ Fehler: Jeder Kunde darf nur einmal vorkommen." if dupes else "")
        self.error.setVisible(bool(dupes))
        self.ok_button.setEnabled(not dupes)
        self.remove_button.setEnabled(self.table.rowCount() > 0)

    def result(self):
        return billing.Billing(self.step.value(), self.mode.currentData(),
                               {n: {"step": s, "mode": m} for n, s, m in self.rows()})

    def apply(self):
        self.result().to_config(self.config)
