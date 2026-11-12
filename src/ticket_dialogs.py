"""Fenster „Neues Ticket“ und „Ticket schließen“ (Matrix42).

Zeitzeuge legt nie von selbst an und schließt nie von selbst: Du füllst das Fenster aus und
klickst „Ticket anlegen“ bzw. „Ticket schließen“. Die Abfragen schickt M42Reader.ticket_task
aus dem angemeldeten Edge (m42_tickets.py).
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox,
                               QFormLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QVBoxLayout)

import m42_booking as mb
import m42_tickets as mt

DEFAULT_CATEGORY = "Ticketeingang"


class _Task:
    """Antworten von reader.ticket_task an das Fenster verteilen (nur die eigenen Aufgaben)."""

    def _connect(self, reader):
        self.reader = reader
        reader.ticket_task_done.connect(self._on_task, Qt.QueuedConnection)

    def _on_task(self, result):
        handler = getattr(self, f"_on_{result.get('kind')}", None)
        if handler is not None and result.get("args", {}).get("owner") == id(self):
            handler(result)

    def _run(self, kind, **args):
        return self.reader.ticket_task(kind, owner=id(self), **args)

    def done(self, code):
        try:
            self.reader.ticket_task_done.disconnect(self._on_task)
        except (RuntimeError, TypeError):
            pass
        super().done(code)


class NewTicketDialog(_Task, QDialog):
    """Neues Ticket: Art, Melder (Ansprechperson beim Kunden), Kategorie, Betreff, Beschreibung.
    Nach dem Anlegen: self.created = {"ticket", "id", "type", "taken_over", "warning"}."""

    def __init__(self, reader, parent=None, subject="", description=""):
        super().__init__(parent)
        self.setWindowTitle("Neues Ticket")
        self.setMinimumWidth(560)
        self.created = None
        self.initiator = None
        self.categories = []
        self._busy = False
        self._connect(reader)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.type_edit = QComboBox(self)
        for value, name in mt.TYPES:
            self.type_edit.addItem(name, value)
        form.addRow("&Art:", self.type_edit)

        self.user_edit = QLineEdit(self)
        self.user_edit.setPlaceholderText("Name des Melders beim Kunden (mind. 2 Zeichen)")
        self.user_edit.setClearButtonEnabled(True)
        self.user_edit.textEdited.connect(self._user_typed)
        form.addRow("&Melder:", self.user_edit)
        self.users = QListWidget(self)
        self.users.setAccessibleName("Gefundene Melder")
        self.users.setMaximumHeight(120)
        self.users.itemActivated.connect(self._take_user)
        self.users.itemClicked.connect(self._take_user)
        self.users.hide()
        form.addRow("", self.users)
        self._user_timer = QTimer(self, singleShot=True, interval=400)
        self._user_timer.timeout.connect(self._search_users)

        self.category_edit = QComboBox(self)
        self.category_edit.setEditable(True)
        self.category_edit.setInsertPolicy(QComboBox.NoInsert)
        self.category_edit.lineEdit().setPlaceholderText("Kategorien werden geladen …")
        self.category_edit.currentIndexChanged.connect(self.validate)
        self.category_edit.editTextChanged.connect(self.validate)
        form.addRow("&Kategorie:", self.category_edit)

        self.subject_edit = QLineEdit(subject, self)
        self.subject_edit.textChanged.connect(self.validate)
        form.addRow("&Betreff:", self.subject_edit)
        self.description_edit = QPlainTextEdit(description, self)
        self.description_edit.setTabChangesFocus(True)
        self.description_edit.setMinimumHeight(120)
        form.addRow("Be&schreibung:", self.description_edit)
        self.take_over = QCheckBox("Mich als &Bearbeiter eintragen (übernehmen)", self)
        self.take_over.setChecked(True)
        form.addRow("", self.take_over)
        layout.addLayout(form)

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.status.setObjectName("hint")
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Ticket &anlegen")
        buttons.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.create)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._run("categories")
        self.validate()
        self.user_edit.setFocus()

    # ---- Melder

    def _user_typed(self, text):
        self.initiator = None
        self.validate()
        if len(text.strip()) >= 2:
            self._user_timer.start()
        else:
            self.users.clear()
            self.users.hide()

    def _search_users(self):
        self._searched = self.user_edit.text().strip()
        self.status.setText(f"Suche Melder „{self._searched}“ …")
        self._run("users", text=self._searched)

    def _on_users(self, result):
        if result["args"].get("text") != self.user_edit.text().strip() or self.initiator:
            return  # ältere Suche oder schon gewählt
        self.users.clear()
        for user in result.get("data") or []:
            item = QListWidgetItem(user["name"])
            item.setData(Qt.UserRole, user)
            self.users.addItem(item)
        self.users.setVisible(self.users.count() > 0)
        if not result.get("ok"):
            self.status.setText(f"⚠ Melder suchen ging nicht: {result.get('error', '')}")
        elif not self.users.count():
            self.status.setText("⚠ Kein Melder gefunden.")
        else:
            self.status.setText("Melder anklicken oder mit Pfeil runter und Enter wählen.")
            self.users.setCurrentRow(0)

    def _take_user(self, item):
        if item is None:
            return
        self.initiator = item.data(Qt.UserRole)
        self.user_edit.setText(self.initiator["name"])
        self.users.hide()
        self.status.clear()
        self.validate()
        self.category_edit.setFocus()

    def keyPressEvent(self, event):
        # Pfeil runter im Melder-Feld: in die Treffer (Enter dort wählt den Melder)
        if self.user_edit.hasFocus() and event.key() == Qt.Key_Down and self.users.isVisible():
            self.users.setFocus()
            return
        super().keyPressEvent(event)

    # ---- Kategorie

    def _on_categories(self, result):
        self.categories = result.get("data") or []
        current = self.category_edit.currentText()
        self.category_edit.clear()
        for cat in self.categories:
            self.category_edit.addItem(cat["path"], cat["id"])
        completer = QCompleter([c["path"] for c in self.categories], self)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.category_edit.setCompleter(completer)
        self.category_edit.lineEdit().setPlaceholderText("Kategorie suchen, z. B. Fileserver")
        index = self.category_edit.findText(current) if current else -1
        if index < 0:
            index = next((i for i, c in enumerate(self.categories)
                          if c["path"].split(" > ")[-1] == DEFAULT_CATEGORY), -1)
        self.category_edit.setCurrentIndex(index)
        if not result.get("ok"):
            self.status.setText(f"⚠ Kategorien laden ging nicht: {result.get('error', '')}")
        self.validate()

    def category(self):
        index = self.category_edit.findText(self.category_edit.currentText())
        return self.category_edit.itemData(index) if index >= 0 else None

    # ---- Anlegen

    def validate(self, *_):
        ok = bool(self.initiator and self.category() and self.subject_edit.text().strip()) and not self._busy
        self.ok_button.setEnabled(ok)
        return ok

    def request(self):
        return {"type": self.type_edit.currentData(), "initiator": (self.initiator or {}).get("id"),
                "category": self.category(), "subject": self.subject_edit.text().strip(),
                "description": self.description_edit.toPlainText(), "take_over": self.take_over.isChecked()}

    def create(self):
        if not self.validate():
            return
        self._busy = True
        self.validate()
        self.status.setText("Lege Ticket in Matrix42 an …")
        if not self._run("create", request=self.request()):
            self._busy = False
            self.validate()
            self.status.setText("⚠ Matrix42-Anmeldefenster ist offen. Bitte erst anmelden.")

    def _on_create(self, result):
        self._busy = False
        if not result.get("ok"):
            self.status.setText(f"⚠ Anlegen fehlgeschlagen: {result.get('error', '')}")
            if result.get("unclear"):  # nicht nochmal anlegen, bevor geklärt ist, ob es geklappt hat
                self.ok_button.setEnabled(False)
            else:
                self.validate()
            return
        self.created = result["data"]
        QApplication.clipboard().setText(self.created["ticket"])
        self.accept()


class CloseTicketDialog(_Task, QDialog):
    """Ticket mit Lösungstext schließen. row: Zeile aus der Ticketliste (m42_booking.ticket_row)."""

    def __init__(self, reader, row, parent=None, solution=""):
        super().__init__(parent)
        self.setWindowTitle("Ticket schließen")
        self.setMinimumWidth(520)
        self.row = row
        self.closed = False
        self._busy = False
        self._connect(reader)
        layout = QVBoxLayout(self)
        title = QLabel(mb.ticket_label(row), self)
        title.setWordWrap(True)
        title.setObjectName("card_title")
        layout.addWidget(title)
        label = QLabel("&Lösung:", self)
        layout.addWidget(label)
        self.solution_edit = QPlainTextEdit(solution, self)
        label.setBuddy(self.solution_edit)
        self.solution_edit.setTabChangesFocus(True)
        self.solution_edit.setMinimumHeight(120)
        self.solution_edit.setAccessibleName("Lösungstext")
        self.solution_edit.textChanged.connect(self.validate)
        layout.addWidget(self.solution_edit)
        self.notify = QCheckBox("Melder per &E-Mail informieren", self)
        self.notify.setChecked(True)
        layout.addWidget(self.notify)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.status.setObjectName("hint")
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Ticket &schließen")
        buttons.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.close_ticket)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.validate()
        self.solution_edit.setFocus()

    def validate(self, *_):
        ok = bool(self.solution_edit.toPlainText().strip()) and not self._busy
        self.ok_button.setEnabled(ok)
        return ok

    def close_ticket(self):
        if not self.validate():
            return
        self._busy = True
        self.validate()
        self.status.setText(f"Schließe {self.row['ticket']} in Matrix42 …")
        request = {"id": self.row["id"], "type": self.row.get("type", ""), "ticket": self.row["ticket"],
                   "solution": self.solution_edit.toPlainText(), "notify": self.notify.isChecked()}
        if not self._run("close", request=request):
            self._busy = False
            self.validate()
            self.status.setText("⚠ Matrix42-Anmeldefenster ist offen. Bitte erst anmelden.")

    def _on_close(self, result):
        self._busy = False
        if not result.get("ok"):
            self.status.setText(f"⚠ Schließen fehlgeschlagen: {result.get('error', '')}")
            if result.get("unclear"):
                self.ok_button.setEnabled(False)
            else:
                self.validate()
            return
        self.closed = True
        self.accept()
