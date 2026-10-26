"""
Kundenliste: Dialog „Kundenliste …“ und die Befehle dazu im Hauptfenster.

- CustomersDialog: Kunden anlegen, umbenennen, löschen; je Kunde Spuren (TeamViewer-ID,
  RDM-Eintrag, VPN-Verbindung, Telefonnummer, E-Mail-Domain) hinzufügen und entfernen.
- CustomersMixin: Teil von TimelineApp (über DocsMixin), Menü „Kundenliste …“,
  Rechtsklick „Kunde zuordnen …“, Index für Vorschläge und Anzeige.

Logik und Ablage in customers.py (ohne Qt).
"""
import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QMessageBox,
                               QPushButton, QVBoxLayout)

import customers as cl
import main_timeline as mt  # save_config zur Laufzeit von dort (Tests ersetzen es dort)


class CustomersDialog(QDialog):
    """Kunden und ihre Spuren bearbeiten. Übernimmt erst mit OK (apply)."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Kundenliste")
        self.setMinimumSize(620, 420)
        self.customers = copy.deepcopy(cl.customer_list(config))
        self.customers.sort(key=lambda c: c["name"].lower())

        layout = QVBoxLayout(self)
        info = QLabel("Ordne jedem Kunden seine Spuren zu: TeamViewer-ID, RDM-Eintrag, VPN, "
                      "Telefonnummer oder E-Mail-Domain. Zeitzeuge schlägt den Kunden dann "
                      "beim Eintragen vor und zeigt ihn in der Tagesliste.")
        info.setWordWrap(True)
        layout.addWidget(info)

        columns = QHBoxLayout()
        # Links: Kunden
        left = QVBoxLayout()
        label = QLabel("&Kunden:")
        self.customer_list = QListWidget()
        label.setBuddy(self.customer_list)
        left.addWidget(label)
        left.addWidget(self.customer_list, 1)
        row = QHBoxLayout()
        self.new_btn = QPushButton("&Neu …")
        self.rename_btn = QPushButton("&Umbenennen …")
        self.delete_btn = QPushButton("&Löschen")
        for b in (self.new_btn, self.rename_btn, self.delete_btn):
            b.setAutoDefault(False)
            row.addWidget(b)
        left.addLayout(row)
        columns.addLayout(left, 1)

        # Rechts: Spuren des gewählten Kunden
        right = QVBoxLayout()
        label = QLabel("&Spuren des Kunden:")
        self.trace_list = QListWidget()
        label.setBuddy(self.trace_list)
        right.addWidget(label)
        right.addWidget(self.trace_list, 1)
        self.remove_btn = QPushButton("Spur &entfernen")
        self.remove_btn.setAutoDefault(False)
        right.addWidget(self.remove_btn, 0, Qt.AlignLeft)
        form = QFormLayout()
        self.kind_edit = QComboBox()
        for key in cl.KIND_ORDER:
            self.kind_edit.addItem(cl.KINDS[key], key)
        form.addRow("&Art:", self.kind_edit)
        self.value_edit = QLineEdit()
        form.addRow("&Wert:", self.value_edit)
        self.add_btn = QPushButton("Spur &hinzufügen")
        self.add_btn.setAutoDefault(False)
        form.addRow("", self.add_btn)
        right.addLayout(form)
        self.message = QLabel()
        self.message.setObjectName("hint")
        self.message.setWordWrap(True)
        right.addWidget(self.message)
        columns.addLayout(right, 1)
        layout.addLayout(columns, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.customer_list.currentRowChanged.connect(self._show_traces)
        self.trace_list.currentRowChanged.connect(lambda _r: self._update_buttons())
        self.new_btn.clicked.connect(lambda: self.add_customer())
        self.rename_btn.clicked.connect(lambda: self.rename_customer())
        self.delete_btn.clicked.connect(lambda: self.delete_customer())
        self.add_btn.clicked.connect(lambda: self.add_trace())
        self.remove_btn.clicked.connect(self.remove_trace)
        self.kind_edit.currentIndexChanged.connect(self._update_placeholder)
        self.value_edit.textChanged.connect(lambda _t: self._update_buttons())
        self._update_placeholder()
        self._fill(0)

    PLACEHOLDERS = {"tv": "z. B. 1 076 789 144", "rdm": "Name des Eintrags in RDM",
                    "vpn": "Name der Verbindung, z. B. in Sophos Connect",
                    "phone": "z. B. +49 711 123456", "mail": "z. B. @kunde.de"}

    # ------------------------------------------------------------ Anzeige

    def _current(self):
        row = self.customer_list.currentRow()
        return self.customers[row] if 0 <= row < len(self.customers) else None

    def _fill(self, select=0):
        self.customer_list.blockSignals(True)
        self.customer_list.clear()
        for c in self.customers:
            n = len(c["traces"])
            self.customer_list.addItem(f"{c['name']} ({n} Spur{'en' if n != 1 else ''})")
        self.customer_list.blockSignals(False)
        if self.customers:
            self.customer_list.setCurrentRow(max(0, min(select, len(self.customers) - 1)))
        self._show_traces()

    def _show_traces(self, *_):
        self.trace_list.clear()
        current = self._current()
        for t in (current or {}).get("traces", []):
            self.trace_list.addItem(cl.display(t["kind"], t["value"]))
        self._update_buttons()

    def _update_placeholder(self, *_):
        self.value_edit.setPlaceholderText(self.PLACEHOLDERS.get(self.kind_edit.currentData(), ""))
        self._update_buttons()

    def _update_buttons(self):
        has = self._current() is not None
        self.rename_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)
        self.add_btn.setEnabled(has and bool(self.value_edit.text().strip()))
        self.remove_btn.setEnabled(has and self.trace_list.currentRow() >= 0)
        for w in (self.kind_edit, self.value_edit):
            w.setEnabled(has)

    def _say(self, text):
        self.message.setText(text)

    # ------------------------------------------------------------ Kunden

    def _ask_name(self, title, text=""):
        name, ok = QInputDialog.getText(self, title, "Name des Kunden:", text=text)
        return name.strip() if ok else ""

    def _exists(self, name, other_than=None):
        return any(c["name"].casefold() == name.casefold() and c is not other_than
                   for c in self.customers)

    def add_customer(self, name=None):
        name = (name if name is not None else self._ask_name("Neuer Kunde")).strip()
        if not name:
            return False
        if self._exists(name):
            self._say(f"⚠ „{name}“ gibt es schon.")
            return False
        self.customers.append({"name": name, "traces": []})
        self.customers.sort(key=lambda c: c["name"].lower())
        self._fill(next(i for i, c in enumerate(self.customers) if c["name"] == name))
        self._say(f"„{name}“ angelegt. Füge jetzt rechts die Spuren hinzu.")
        self.value_edit.setFocus()
        return True

    def rename_customer(self, name=None):
        current = self._current()
        if current is None:
            return False
        name = (name if name is not None else self._ask_name("Kunde umbenennen", current["name"])).strip()
        if not name or name == current["name"]:
            return False
        if self._exists(name, other_than=current):
            self._say(f"⚠ „{name}“ gibt es schon.")
            return False
        current["name"] = name
        self.customers.sort(key=lambda c: c["name"].lower())
        self._fill(self.customers.index(current))
        self._say(f"Umbenannt in „{name}“.")
        return True

    def delete_customer(self, ask=True):
        current = self._current()
        if current is None:
            return False
        if ask and current["traces"] and QMessageBox.question(
                self, "Kunde löschen",
                f"„{current['name']}“ mit {len(current['traces'])} Spuren löschen? "
                "Deine Tätigkeiten bleiben erhalten.") != QMessageBox.Yes:
            return False
        row = self.customers.index(current)
        del self.customers[row]
        self._fill(row)
        self._say(f"„{current['name']}“ gelöscht.")
        return True

    # ------------------------------------------------------------ Spuren

    def add_trace(self, kind=None, value=None):
        current = self._current()
        if current is None:
            return False
        kind = kind or self.kind_edit.currentData()
        value = self.value_edit.text() if value is None else value
        if not cl.normalize(kind, value):
            hints = {"tv": "nur Ziffern", "phone": "mindestens 3 Ziffern",
                     "mail": "z. B. @kunde.de"}
            self._say(f"⚠ Ungültige {cl.KINDS[kind]} ({hints.get(kind, 'leer')}).")
            return False
        key = cl.normalize(kind, value)
        before = next((c["name"] for c in self.customers if c is not current and any(
            t["kind"] == kind and cl.normalize(kind, t["value"]) == key for t in c["traces"])), "")
        cl._assign(self.customers, kind, value, current["name"])
        self._fill(self.customers.index(current))
        self.value_edit.clear()
        text = f"{cl.display(kind, cl.clean_value(kind, value))} hinzugefügt."
        if before:
            text += f" Sie gehörte bisher zu „{before}“."
        self._say(text)
        return True

    def remove_trace(self):
        current = self._current()
        row = self.trace_list.currentRow()
        if current is None or not 0 <= row < len(current["traces"]):
            return False
        t = current["traces"].pop(row)
        self._fill(self.customers.index(current))
        self.trace_list.setCurrentRow(min(row, self.trace_list.count() - 1))
        self._say(f"{cl.display(t['kind'], t['value'])} entfernt.")
        return True

    def apply(self):
        cl.apply_list(self.config, self.customers)


class CustomersMixin:
    """Befehle im Hauptfenster (über DocsMixin Teil von TimelineApp)."""

    def customer_index_list(self):
        return cl.customer_list(self.config)

    def customer_index(self):
        """Index der eigenen Kundenliste plus übernommener Daten eines anderen PCs."""
        imported = getattr(self, "imported", None)
        return cl.index(self.config,
                        imported.customers() if imported and hasattr(imported, "customers") else None,
                        imported.teamviewer_names() if imported else None)

    def edit_customers(self):
        dialog = CustomersDialog(self.config, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply()
            mt.save_config(self.config)
            self.timeline.draw_timeline(self.current_date)
            self.statusBar().showMessage("Kundenliste gespeichert", 3000)

    def assign_customer(self, entry):
        """Rechtsklick „Kunde zuordnen …“: Spur des Eintrags einem Kunden geben."""
        trace = cl.primary_trace(entry)
        if not trace:
            return
        kind, value = trace
        names = self.known_customers() if hasattr(self, "known_customers") else []
        current = self.customer_index().customer_for(entry)
        items = [current] + [n for n in names if n != current] if current else [""] + names
        name, ok = QInputDialog.getItem(
            self, "Kunde zuordnen", f"Kunde für {cl.display(kind, cl.clean_value(kind, value))}:",
            items, 0, True)
        if not ok or not name.strip():
            return
        cl.learn(self.config, kind, value, name.strip())
        mt.save_config(self.config)
        self.timeline.draw_timeline(self.current_date)
        self.statusBar().showMessage(
            f"{cl.display(kind, cl.clean_value(kind, value))} gehört jetzt zu „{name.strip()}“", 4000)
