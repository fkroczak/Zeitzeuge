"""Fenster „Neues Ticket“, „Ticket bearbeiten“ und „Ticket schließen“ (Matrix42), im Stil von „Tätigkeit nachtragen“.

Aufbau wie EntryDialog (journal_dialogs.py): Kopf mit Kachel und Titel, Inhalt mit Beschriftung
über dem Feld, Chips, grauer Infokasten, Fußleiste mit Abbrechen und genau einer Hauptaktion.

Zeitzeuge legt nie von selbst an, ändert nie von selbst und schließt nie von selbst: Du füllst
das Fenster aus und klickst „Ticket anlegen“, „Speichern“ bzw. „Ticket schließen“. Die Abfragen schickt M42Reader.ticket_task
aus dem angemeldeten Edge (m42_tickets.py).
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QCompleter, QDialog, QFormLayout,
                               QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

import m42_booking as mb
import m42_tickets as mt
from flow_layout import FlowLayout
from prompt_card import _ElidedLabel, _icon_label, source_tile
import spellcheck
from theme import SPACE_M, SPACE_S, SPACE_XS, fit_bold

DEFAULT_CATEGORY = "Ticketeingang"
TYPE_CHIPS = [(mt.INCIDENT, "&Störung"), (mt.SERVICE_REQUEST, "Service&anfrage")]


def _label(text, buddy):
    label = QLabel(text)
    label.setObjectName("prompt_label")
    label.setBuddy(buddy)
    return label


class _CardDialog(QDialog):
    """Rahmen wie „Tätigkeit nachtragen“: Kopf, Inhalt (self.body_box), Fuß mit Hauptaktion.
    Dazu die Verteilung der Antworten von reader.ticket_task (nur die eigenen Aufgaben)."""

    def _frame(self, reader, title, subtitle, icon, main_text):
        self.reader = reader
        self.setWindowTitle(title)
        self.setObjectName("entry_dialog")  # gleiches Aussehen (theme.py)
        self.setFixedWidth(600)
        self._busy = False
        pal = self.palette()
        self.accent = pal.color(pal.ColorRole.Accent).name()
        self.muted = pal.color(pal.ColorRole.PlaceholderText).name()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QWidget()
        top.setObjectName("prompt_top")
        top.setAttribute(Qt.WA_StyledBackground)
        self.head_box = QVBoxLayout(top)
        self.head_box.setContentsMargins(16, 14, 16, SPACE_M)
        self.head_box.setSpacing(SPACE_S + 2)
        head = QHBoxLayout()
        head.setSpacing(SPACE_M)
        head.addWidget(source_tile(icon, self.accent), 0, Qt.AlignVCenter)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = _ElidedLabel(title)
        self.title.setObjectName("prompt_title")
        self.subtitle = _ElidedLabel(subtitle)
        self.subtitle.setObjectName("hint")
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        head.addLayout(texts, 1)
        self.head_box.addLayout(head)
        outer.addWidget(top)

        body = QWidget()
        body.setObjectName("prompt_body")
        self.body_box = QVBoxLayout(body)
        self.body_box.setContentsMargins(16, SPACE_M, 16, SPACE_M)
        self.body_box.setSpacing(SPACE_S + 2)
        outer.addWidget(body)

        foot = QWidget()
        foot.setObjectName("prompt_foot")
        foot.setProperty("flat", True)
        foot.setAttribute(Qt.WA_StyledBackground)
        foot_box = QHBoxLayout(foot)
        foot_box.setContentsMargins(16, SPACE_S + 2, 16, SPACE_S + 2)
        foot_box.setSpacing(SPACE_S)
        self.status = QLabel()
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        foot_box.addWidget(self.status, 1)
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        foot_box.addWidget(self.cancel_button)
        self.ok_button = QPushButton(main_text)
        self.ok_button.setDefault(True)
        self.ok_button.setToolTip(f"{main_text.replace('&', '')} (Strg+Enter)")
        fit_bold(self.ok_button)  # fett (Standardknopf): sonst fehlt der letzte Buchstabe
        foot_box.addWidget(self.ok_button)
        outer.addWidget(foot)
        reader.ticket_task_done.connect(self._on_task, Qt.QueuedConnection)

    def _info_card(self, icon, title):
        """Grauer Kasten wie „In dieser Zeit“: Überschrift mit Symbol, Zeilen Name | Wert."""
        card = QFrame()
        card.setObjectName("entry_context")
        box = QVBoxLayout(card)
        box.setContentsMargins(SPACE_M, SPACE_S + 2, SPACE_M, SPACE_S + 2)
        box.setSpacing(SPACE_XS + 2)
        head = QHBoxLayout()
        head.setSpacing(SPACE_S)
        head.addWidget(_icon_label(icon, self.muted, 14))
        label = QLabel(title)
        label.setObjectName("prompt_label")
        head.addWidget(label)
        head.addStretch(1)
        box.addLayout(head)
        rows = QFormLayout()
        rows.setHorizontalSpacing(SPACE_M)
        rows.setVerticalSpacing(SPACE_XS)
        box.addLayout(rows)
        return card, rows

    @staticmethod
    def _fill_rows(rows, pairs):
        while rows.rowCount():
            rows.removeRow(0)
        for name, text in pairs:
            key = QLabel(name)
            key.setObjectName("hint")
            value = QLabel(text)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            rows.addRow(key, value)

    def _ticket_line(self, row):
        """Zeile unter dem Titel wie die Zeitzeile: Nummer · Kunde · Status."""
        line = QFrame()
        line.setObjectName("prompt_time")
        line_box = QHBoxLayout(line)
        line_box.setContentsMargins(SPACE_M, SPACE_S, SPACE_M, SPACE_S)
        line_box.setSpacing(SPACE_S)
        for icon, text in (("tag", row["ticket"]), ("users", row.get("customer", "")),
                           ("clock", row.get("state", ""))):
            if text:
                line_box.addWidget(_icon_label(icon, self.muted, 16))
                line_box.addWidget(QLabel(text))
                line_box.addSpacing(SPACE_M)
        line_box.addStretch(1)
        self.head_box.addWidget(line)

    def _on_task(self, result):
        handler = getattr(self, f"_on_{result.get('kind')}", None)
        if handler is not None and result.get("args", {}).get("owner") == id(self):
            handler(result)

    def _run(self, kind, **args):
        return self.reader.ticket_task(kind, owner=id(self), **args)

    def _start(self, kind, text, **args):
        """Anlegen/Schließen abschicken: Knopf aus, bis die Antwort da ist."""
        self._busy = True
        self.validate()
        self.status.setText(text)
        if not self._run(kind, **args):
            self._busy = False
            self.validate()
            self.status.setText("⚠ Matrix42-Anmeldefenster ist offen. Bitte erst anmelden.")

    def _failed(self, result, what):
        self._busy = False
        self.status.setText(f"⚠ {what} fehlgeschlagen: {result.get('error', '')}")
        if result.get("unclear"):  # nicht nochmal, bevor geklärt ist, ob es geklappt hat
            self.ok_button.setEnabled(False)
        else:
            self.validate()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
            if self.ok_button.isEnabled():
                self.ok_button.click()
            return
        super().keyPressEvent(event)

    def done(self, code):
        try:
            self.reader.ticket_task_done.disconnect(self._on_task)
        except (RuntimeError, TypeError):
            pass
        super().done(code)


class NewTicketDialog(_CardDialog):
    """Neues Ticket: Art, Melder (Ansprechperson beim Kunden), Kategorie, Betreff, Beschreibung.
    Nach dem Anlegen: self.created = {"ticket", "id", "type", "taken_over", "warning"}."""

    def __init__(self, reader, parent=None, subject="", description=""):
        super().__init__(parent)
        self.created = None
        self.initiator = None
        self.categories = []
        self._frame(reader, "Neues Ticket", "Störung oder Serviceanfrage in Matrix42 anlegen", "doc",
                    "Ticket &anlegen")
        box = self.body_box

        # Melder | Kategorie nebeneinander wie Kunde | Kategorie
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("Name beim Kunden suchen")
        self.user_edit.setAccessibleName("Melder")
        self.user_edit.setClearButtonEnabled(True)
        self.user_edit.textEdited.connect(self._user_typed)
        self.category_edit = QComboBox()
        self.category_edit.setEditable(True)
        self.category_edit.setInsertPolicy(QComboBox.NoInsert)
        self.category_edit.lineEdit().setPlaceholderText("Kategorien werden geladen …")
        self.category_edit.lineEdit().setAccessibleName("Kategorie")
        self.category_edit.currentIndexChanged.connect(self.validate)
        self.category_edit.editTextChanged.connect(self.validate)
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACE_M)
        grid.setVerticalSpacing(SPACE_XS)
        for col, (name, widget) in enumerate((("&Melder", self.user_edit), ("Kate&gorie", self.category_edit))):
            grid.addWidget(_label(name, widget), 0, col)
            grid.addWidget(widget, 1, col)
            grid.setColumnStretch(col, 1)
        box.addLayout(grid)
        self.users = QListWidget()
        self.users.setAccessibleName("Gefundene Melder")
        self.users.setMaximumHeight(110)
        self.users.itemActivated.connect(self._take_user)
        self.users.itemClicked.connect(self._take_user)
        self.users.hide()
        box.addWidget(self.users)
        self._user_timer = QTimer(self, singleShot=True, interval=400)
        self._user_timer.timeout.connect(self._search_users)

        self.subject_edit = QLineEdit(subject)
        self.subject_edit.setPlaceholderText("Kurz und eindeutig, z. B. „Drucker im Empfang druckt nicht“")
        self.subject_edit.textChanged.connect(self.validate)
        box.addSpacing(2)
        box.addWidget(_label("&Betreff", self.subject_edit))
        box.addWidget(self.subject_edit)
        self.description_edit = QPlainTextEdit(description)
        spellcheck.attach(self.description_edit)
        self.description_edit.setPlaceholderText("Was ist los? Was hat der Kunde gemeldet?")
        self.description_edit.setTabChangesFocus(True)
        self.description_edit.setFixedHeight(96)
        box.addWidget(_label("Be&schreibung", self.description_edit))
        box.addWidget(self.description_edit)

        # Chips: Art (eine von beiden) und Übernehmen
        chips_host = QWidget()
        chips_host.setObjectName("chips")
        chips = FlowLayout(chips_host, spacing=6)
        self.type_group = QButtonGroup(self)
        self.type_group.setExclusive(True)
        self.type_chips = {}
        for value, name in TYPE_CHIPS:
            chip = QCheckBox(name)
            chip.setObjectName("chip_check")
            self.type_group.addButton(chip, value)
            self.type_chips[value] = chip
            chips.addWidget(chip)
        self.type_chips[mt.INCIDENT].setChecked(True)
        self.type_chips[mt.INCIDENT].setToolTip("Etwas funktioniert nicht (Incident)")
        self.type_chips[mt.SERVICE_REQUEST].setToolTip("Wunsch oder Auftrag des Kunden (Service Request)")
        self.take_over = QCheckBox("Ich &bearbeite es")
        self.take_over.setObjectName("chip_check")
        self.take_over.setToolTip("Dich gleich als Bearbeiter eintragen (übernehmen)")
        self.take_over.setChecked(True)
        chips.addWidget(self.take_over)
        box.addWidget(chips_host)

        # Infokasten zum Melder (Firma, Telefon, E-Mail aus Matrix42)
        box.addSpacing(SPACE_XS)
        self.user_card, self.user_rows = self._info_card("users", "Melder")
        self._fill_rows(self.user_rows, [("", "Noch kein Melder gewählt.")])
        box.addWidget(self.user_card)

        self.ok_button.clicked.connect(self.create)
        self._run("categories")
        self.validate()
        self.user_edit.setFocus()

    def ticket_type(self):
        return self.type_group.checkedId()

    # ---- Melder

    def _user_typed(self, text):
        self.initiator = None
        self._fill_rows(self.user_rows, [("", "Noch kein Melder gewählt.")])
        self.validate()
        if len(text.strip()) >= 2:
            self._user_timer.start()
        else:
            self.users.clear()
            self._show_users(False)

    def _show_users(self, on):
        if self.users.isVisible() != on:
            self.users.setVisible(on)
            QTimer.singleShot(0, self.adjustSize)

    def _search_users(self):
        text = self.user_edit.text().strip()
        self.status.setText(f"Suche Melder „{text}“ …")
        self._run("users", text=text)

    def _on_users(self, result):
        if result["args"].get("text") != self.user_edit.text().strip() or self.initiator:
            return  # ältere Suche oder schon gewählt
        self.users.clear()
        for user in result.get("data") or []:
            item = QListWidgetItem(user["name"])
            item.setData(Qt.UserRole, user)
            self.users.addItem(item)
        self._show_users(self.users.count() > 0)
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
        self.user_edit.setText(self.initiator["name"].split(" - ")[0])
        self.user_edit.setToolTip(self.initiator["name"])
        self._show_users(False)
        self.status.clear()
        company = self.initiator["name"].split(" - ", 1)[1] if " - " in self.initiator["name"] else ""
        self._fill_rows(self.user_rows, [("Name", self.initiator["name"].split(" - ")[0])] +
                        ([("Firma", company)] if company else []))
        self._run("user_details", user=self.initiator["id"])
        self.validate()
        self.category_edit.setFocus()

    def _on_user_details(self, result):
        if not self.initiator or result["args"].get("user") != self.initiator["id"] or not result.get("ok"):
            return
        d = result.get("data") or {}
        rows = [("Name", self.initiator["name"].split(" - ")[0]),
                ("Firma", (d.get("OrgUnit") or "").strip()), ("Telefon", d.get("Phone") or ""),
                ("E-Mail", d.get("Email") or "")]
        self._fill_rows(self.user_rows, [(k, v) for k, v in rows if v])

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
        return {"type": self.ticket_type(), "initiator": (self.initiator or {}).get("id"),
                "category": self.category(), "subject": self.subject_edit.text().strip(),
                "description": self.description_edit.toPlainText(), "take_over": self.take_over.isChecked()}

    def create(self):
        if self.validate():
            self._start("create", "Lege Ticket in Matrix42 an …", request=self.request())

    def _on_create(self, result):
        if not result.get("ok"):
            self._failed(result, "Anlegen")
            return
        self.created = result["data"]
        QApplication.clipboard().setText(self.created["ticket"])
        self.accept()


class CloseTicketDialog(_CardDialog):
    """Ticket mit Lösungstext schließen. row: Zeile aus der Ticketliste (m42_booking.ticket_row)."""

    def __init__(self, reader, row, parent=None, solution=""):
        super().__init__(parent)
        self.row = row
        self.closed = False
        self._frame(reader, "Ticket schließen", row.get("subject") or row["ticket"], "check",
                    "Ticket &schließen")
        self._ticket_line(row)

        self.solution_edit = QPlainTextEdit(solution)
        spellcheck.attach(self.solution_edit)
        self.solution_edit.setPlaceholderText("Was war die Lösung? z. B. „Treiber neu installiert, mit Kunde getestet“")
        self.solution_edit.setTabChangesFocus(True)
        self.solution_edit.setFixedHeight(110)
        self.solution_edit.setAccessibleName("Lösungstext")
        self.solution_edit.textChanged.connect(self.validate)
        self.body_box.addWidget(_label("&Lösung", self.solution_edit))
        self.body_box.addWidget(self.solution_edit)
        chips_host = QWidget()
        chips_host.setObjectName("chips")
        chips = FlowLayout(chips_host, spacing=6)
        self.notify = QCheckBox("Melder per &E-Mail informieren")
        self.notify.setObjectName("chip_check")
        self.notify.setChecked(True)
        chips.addWidget(self.notify)
        self.body_box.addWidget(chips_host)

        self.body_box.addSpacing(SPACE_XS)
        card, rows = self._info_card("doc", "Ticket")
        self._fill_rows(rows, [(k, v) for k, v in (
            ("Betreff", row.get("subject", "")), ("Melder", row.get("initiator", "")),
            ("Bearbeiter", row.get("recipient", "")), ("Angelegt", mb.ticket_date(row))) if v])
        self.body_box.addWidget(card)

        self.ok_button.clicked.connect(self.close_ticket)
        self.validate()
        self.solution_edit.setFocus()
        # Lösungstext von früher (Ticket wieder eröffnet) übernehmen, solange noch nichts getippt ist
        if not solution.strip() and self._run("close_info", id=row["id"], type=row.get("type", "")):
            self.status.setText("Suche bisherigen Lösungstext …")

    def _on_close_info(self, result):
        if self._busy:
            return
        self.status.clear()
        solution = (result.get("data") or {}).get("solution", "") if result.get("ok") else ""
        if solution and not self.solution_edit.toPlainText().strip():
            self.solution_edit.setPlainText(solution)
            self.solution_edit.moveCursor(QTextCursor.End)
            self.status.setText("Bisheriger Lösungstext übernommen.")

    def validate(self, *_):
        ok = bool(self.solution_edit.toPlainText().strip()) and not self._busy
        self.ok_button.setEnabled(ok)
        return ok

    def close_ticket(self):
        if self.validate():
            self._start("close", f"Schließe {self.row['ticket']} in Matrix42 …",
                        request={"id": self.row["id"], "type": self.row.get("type", ""),
                                 "ticket": self.row["ticket"], "solution": self.solution_edit.toPlainText(),
                                 "notify": self.notify.isChecked()})

    def _on_close(self, result):
        if not result.get("ok"):
            self._failed(result, "Schließen")
            return
        self.closed = True
        self.accept()


class EditTicketDialog(_CardDialog):
    """Bestehendes Ticket: Betreff, Kategorie und Beschreibung ändern. Lädt das Ticket erst frisch aus
    Matrix42; bis dahin ist nichts änderbar. Nach dem Speichern: self.saved = {"ticket", "subject", …}."""

    def __init__(self, reader, row, parent=None):
        super().__init__(parent)
        self.row = row
        self.saved = None
        self.loaded = None
        self.categories = []
        self._frame(reader, "Ticket bearbeiten", row.get("subject") or row["ticket"], "doc", "&Speichern")
        self._ticket_line(row)
        box = self.body_box

        self.subject_edit = QLineEdit(row.get("subject", ""))
        self.subject_edit.setAccessibleName("Betreff")
        self.subject_edit.textChanged.connect(self.validate)
        box.addWidget(_label("&Betreff", self.subject_edit))
        box.addWidget(self.subject_edit)
        self.category_edit = QComboBox()
        self.category_edit.setEditable(True)
        self.category_edit.setInsertPolicy(QComboBox.NoInsert)
        self.category_edit.lineEdit().setPlaceholderText("Kategorien werden geladen …")
        self.category_edit.lineEdit().setAccessibleName("Kategorie")
        self.category_edit.currentIndexChanged.connect(self.validate)
        self.category_edit.editTextChanged.connect(self.validate)
        box.addWidget(_label("Kate&gorie", self.category_edit))
        box.addWidget(self.category_edit)
        self.description_edit = QPlainTextEdit()
        self.description_edit.setAccessibleName("Beschreibung")
        self.description_edit.setPlaceholderText("Beschreibung wird geladen …")
        self.description_edit.setTabChangesFocus(True)
        self.description_edit.setMinimumHeight(140)
        self.description_edit.textChanged.connect(self.validate)
        spellcheck.attach(self.description_edit)
        box.addWidget(_label("B&eschreibung", self.description_edit))
        box.addWidget(self.description_edit)
        self.rich_hint = QLabel("Die Beschreibung hat Bilder, Tabellen oder Formatierungen. Text hinten anfügen "
                                "behält sie, jede andere Änderung ersetzt sie durch reinen Text.")
        self.rich_hint.setWordWrap(True)
        self.rich_hint.setObjectName("hint")
        self.rich_hint.hide()
        box.addWidget(self.rich_hint)

        self.ok_button.clicked.connect(self.save)
        for widget in self._fields():
            widget.setEnabled(False)
        self.validate()
        self.status.setText(f"Lade {row['ticket']} aus Matrix42 …")
        if not self._run("load", id=row["id"], type=row.get("type", "")):
            self.status.setText("⚠ Matrix42-Anmeldefenster ist offen. Bitte erst anmelden.")
        else:
            self._run("categories")

    def _fields(self):
        return (self.subject_edit, self.category_edit, self.description_edit)

    def _on_load(self, result):
        if not result.get("ok"):
            self.description_edit.setPlaceholderText("")
            self.status.setText(f"⚠ Laden fehlgeschlagen: {result.get('error', '')}")
            return
        self.loaded = result["data"]
        self.subject_edit.setText(self.loaded["subject"] or self.row.get("subject", ""))
        self.description_edit.setPlainText(self.loaded["description"])
        self.description_edit.setPlaceholderText("(keine Beschreibung)")
        self.rich_hint.setVisible(bool(self.loaded.get("rich")))
        self._select_category()
        for widget in self._fields():
            widget.setEnabled(True)
        self.status.clear()
        self.validate()
        self.description_edit.setFocus()
        self.description_edit.moveCursor(QTextCursor.End)

    def _on_categories(self, result):
        self.categories = result.get("data") or []
        self.category_edit.blockSignals(True)
        self.category_edit.clear()
        for cat in self.categories:
            self.category_edit.addItem(cat["path"], cat["id"])
        self.category_edit.blockSignals(False)
        completer = QCompleter([c["path"] for c in self.categories], self)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.category_edit.setCompleter(completer)
        self.category_edit.lineEdit().setPlaceholderText("Kategorie suchen, z. B. Fileserver")
        self._select_category()
        if not result.get("ok"):
            self.status.setText(f"⚠ Kategorien laden ging nicht: {result.get('error', '')}")
        self.validate()

    def _select_category(self):
        """Aktuelle Kategorie des Tickets auswählen, sobald Ticket und Liste da sind."""
        current = (self.loaded or {}).get("category")
        if current and self.categories:
            self.category_edit.setCurrentIndex(self.category_edit.findData(current))

    def category(self):
        """Gewählte Kategorie; None, solange die Liste fehlt oder der Text keine Kategorie ist."""
        index = self.category_edit.findText(self.category_edit.currentText())
        return self.category_edit.itemData(index) if index >= 0 else None

    def changed(self):
        if not self.loaded:
            return False
        category = self.category()
        return (self.subject_edit.text().strip() != self.loaded["subject"]
                or self.description_edit.toPlainText().strip() != self.loaded["description"].strip()
                or bool(category and category != self.loaded.get("category")))

    def validate(self, *_):
        ok = bool(self.loaded and self.subject_edit.text().strip() and self.changed()) and not self._busy
        if self.categories and self.category_edit.currentText().strip() and not self.category():
            ok = False  # getippter Text ist keine Kategorie
        self.ok_button.setEnabled(ok)
        return ok

    def request(self):
        return {"id": self.row["id"], "ticket": self.row["ticket"], "stamp": self.loaded["stamp"],
                "subject": self.subject_edit.text().strip(), "description": self.description_edit.toPlainText(),
                "category": self.category() or self.loaded.get("category")}

    def save(self):
        if self.validate():
            self._start("edit", f"Speichere {self.row['ticket']} in Matrix42 …", request=self.request())

    def _on_edit(self, result):
        if not result.get("ok"):
            self._failed(result, "Speichern")
            return
        self.saved = result["data"]
        self.accept()
