"""Fenster „Neues Ticket“, „Ticket ansehen“, „Ticket bearbeiten“ und „Ticket schließen“ (Matrix42), im Stil von „Tätigkeit nachtragen“.

Aufbau wie EntryDialog (journal_dialogs.py): Kopf mit Kachel und Titel, Inhalt mit Beschriftung
über dem Feld, Chips, grauer Infokasten, Fußleiste mit Abbrechen und genau einer Hauptaktion.

Zeitzeuge legt nie von selbst an, ändert nie von selbst und schließt nie von selbst: Du füllst
das Fenster aus und klickst „Ticket anlegen“, „Speichern“ bzw. „Ticket schließen“. Die Abfragen schickt M42Reader.ticket_task
aus dem angemeldeten Edge (m42_tickets.py).
"""
import base64
import html
from urllib.parse import unquote_to_bytes

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QTextCursor, QTextDocument, QTextDocumentFragment
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QCompleter, QDialog, QFormLayout,
                               QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

import icons
import m42_booking as mb
import m42_tickets as mt
import skeleton
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

    def _ticket_line(self, row, pen_tip=""):
        """Zeile unter dem Titel wie die Zeitzeile: Nummer · Kunde · Status. pen_tip: rechts ein Stift
        (wie bei Datum und Uhrzeit), self.pen_button."""
        line = QFrame()
        line.setObjectName("prompt_time")
        line_box = QHBoxLayout(line)
        line_box.setContentsMargins(SPACE_M, SPACE_S, SPACE_M, SPACE_S)
        line_box.setSpacing(SPACE_S)
        self.state_label = None
        for icon, text in (("tag", row["ticket"]), ("users", row.get("customer", "")),
                           ("clock", row.get("state", ""))):
            if text:
                line_box.addWidget(_icon_label(icon, self.muted, 16))
                label = QLabel(text)
                line_box.addWidget(label)
                line_box.addSpacing(SPACE_M)
                if icon == "clock":
                    self.state_label = label
        line_box.addStretch(1)
        if pen_tip:
            self.pen_button = QToolButton()
            self.pen_button.setObjectName("prompt_tool")
            self.pen_button.setIcon(icons.icon("edit", self.muted))
            self.pen_button.setToolTip(pen_tip)
            self.pen_button.setAccessibleName(pen_tip)
            self.pen_button.setCursor(Qt.PointingHandCursor)
            line_box.addWidget(self.pen_button)
        self.head_box.addWidget(line)

    def _add_take_over(self, row):
        """Knopf „Übernehmen“ (Bearbeiter = ich, Status „In Bearbeitung“) links in der Fußleiste; fehlt,
        wenn das Ticket geschlossen oder schon meins und in Bearbeitung ist (nur zugewiesen: Knopf da).
        Danach: self.taken_over = Anzeigename (oder "")."""
        self.taken_over = None
        self.take_over_button = QPushButton("Über&nehmen")
        self.take_over_button.setAutoDefault(False)
        self.take_over_button.setToolTip("Ticket in Matrix42 übernehmen: du wirst Bearbeiter")
        self.take_over_button.clicked.connect(self._take_over)
        # erst einfügen, dann zeigen: ein Knopf ohne Eltern würde sonst kurz als eigenes Fenster aufblitzen
        self.cancel_button.parentWidget().layout().insertWidget(1, self.take_over_button)
        self.take_over_button.setVisible(mb.can_take_over(row, getattr(self.reader, "user_id", "") or ""))

    def _take_over(self):
        self.take_over_button.setEnabled(False)
        self.status.setText(f"Übernehme {self.row['ticket']} …")
        if not self._run("take_over", id=self.row["id"], type=self.row.get("type", ""), ticket=self.row["ticket"]):
            self.take_over_button.setEnabled(True)
            self.status.setText("⚠ Matrix42-Anmeldefenster ist offen. Bitte erst anmelden.")

    def _on_take_over(self, result):
        if not result.get("ok"):
            self.take_over_button.setEnabled(not result.get("unclear"))
            self.status.setText(f"⚠ Übernehmen fehlgeschlagen: {result.get('error', '')}")
            return
        self.taken_over = (result.get("data") or {}).get("user") or ""
        self.take_over_button.hide()
        self.row = dict(self.row, state=mb.WORKING_STATE, recipient=self.taken_over or self.row.get("recipient", ""),
                        recipient_id=getattr(self.reader, "user_id", "") or self.row.get("recipient_id", ""))
        if getattr(self, "state_label", None) is not None:
            self.state_label.setText(mb.WORKING_STATE)
        self.status.setText(f"{self.row['ticket']} übernommen, du bist jetzt Bearbeiter ({mb.WORKING_STATE}).")
        self._took_over()

    def _took_over(self):
        """Nach dem Übernehmen (Fenster können mehr zeigen)."""

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


class _MelderSearch:
    """Melder (Ansprechperson beim Kunden) suchen und wählen, für „Neues Ticket“ und „Ticket bearbeiten“.
    Braucht self.user_edit, self.users, self.user_rows (siehe _melder_widgets); nach der Wahl steht
    er in self.initiator ({"id", "name"}) und _melder_chosen() wird gerufen."""
    NO_MELDER = "Noch kein Melder gewählt."

    def _melder_widgets(self):
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("Name beim Kunden suchen")
        self.user_edit.setAccessibleName("Melder")
        self.user_edit.setClearButtonEnabled(True)
        self.user_edit.textEdited.connect(self._user_typed)
        self.users = QListWidget()
        self.users.setAccessibleName("Gefundene Melder")
        self.users.setMaximumHeight(110)
        self.users.itemActivated.connect(self._take_user)
        self.users.itemClicked.connect(self._take_user)
        self.users.hide()
        self._user_timer = QTimer(self, singleShot=True, interval=400)
        self._user_timer.timeout.connect(self._search_users)

    def _melder_chosen(self):
        """Nach der Wahl (Fenster setzen hier z. B. den Fokus weiter)."""

    def _user_typed(self, text):
        self.initiator = None
        self._fill_rows(self.user_rows, [("", self.NO_MELDER)])
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
        self._melder_chosen()

    def _on_user_details(self, result):
        if not self.initiator or result["args"].get("user") != self.initiator["id"] or not result.get("ok"):
            return
        d = result.get("data") or {}
        rows = [("Name", self.initiator["name"].split(" - ")[0]),
                ("Firma", (d.get("OrgUnit") or "").strip()), ("Telefon", d.get("Phone") or ""),
                ("E-Mail", d.get("Email") or "")]
        self._fill_rows(self.user_rows, [(k, v) for k, v in rows if v])

    def _melder_keys(self, event):
        """Pfeil runter im Melder-Feld: in die Treffer (Enter dort wählt den Melder). True = erledigt."""
        if self.user_edit.hasFocus() and event.key() == Qt.Key_Down and self.users.isVisible():
            self.users.setFocus()
            return True
        return False


class NewTicketDialog(_MelderSearch, _CardDialog):
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
        self._melder_widgets()
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
        box.addWidget(self.users)

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
        self._fill_rows(self.user_rows, [("", self.NO_MELDER)])
        box.addWidget(self.user_card)

        self.ok_button.clicked.connect(self.create)
        self._run("categories")
        self.validate()
        self.user_edit.setFocus()

    def ticket_type(self):
        return self.type_group.checkedId()

    def _melder_chosen(self):
        self.category_edit.setFocus()

    def keyPressEvent(self, event):
        if not self._melder_keys(event):
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


class EditTicketDialog(_MelderSearch, _CardDialog):
    """Bestehendes Ticket: Betreff, Kategorie und Beschreibung ändern. Lädt das Ticket erst frisch aus
    Matrix42; bis dahin ist nichts änderbar. Nach dem Speichern: self.saved = {"ticket", "subject", …}."""

    def __init__(self, reader, row, parent=None):
        super().__init__(parent)
        self.row = row
        self.saved = None
        self.loaded = None
        self.categories = []
        self._frame(reader, "Ticket bearbeiten", row.get("subject") or row["ticket"], "doc", "&Speichern")
        self._ticket_line(row, "Melder (Ticketeröffner) ändern")
        self._add_take_over(row)
        box = self.body_box
        self.initiator = None

        # Melder: erst mit dem Stift sichtbar
        self._melder_widgets()
        self.user_edit.setText(row.get("initiator", ""))
        self.melder_box = QWidget()
        melder = QVBoxLayout(self.melder_box)
        melder.setContentsMargins(0, 0, 0, 0)
        melder.setSpacing(SPACE_XS)
        melder.addWidget(_label("&Melder", self.user_edit))
        melder.addWidget(self.user_edit)
        melder.addWidget(self.users)
        self.user_card, self.user_rows = self._info_card("users", "Neuer Melder")
        self._fill_rows(self.user_rows, [("", self.NO_MELDER)])
        melder.addWidget(self.user_card)
        self.melder_box.hide()
        box.addWidget(self.melder_box)
        self.pen_button.clicked.connect(self.edit_melder)

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
        self.description_edit.setTabChangesFocus(True)
        self.description_edit.setMinimumHeight(140)
        self.description_edit.textChanged.connect(self.validate)
        spellcheck.attach(self.description_edit)
        box.addWidget(_label("B&eschreibung", self.description_edit))
        box.addWidget(self.description_edit)
        self.description_skeleton = skeleton.Lines(self.description_edit, lines=4)
        self.rich_hint = QLabel("Die Beschreibung hat Bilder, Tabellen oder Formatierungen. Text hinten anfügen "
                                "behält sie, jede andere Änderung ersetzt sie durch reinen Text.")
        self.rich_hint.setWordWrap(True)
        self.rich_hint.setObjectName("hint")
        self.rich_hint.hide()
        box.addWidget(self.rich_hint)

        # Nur zugewiesen: Matrix42 speichert erst nach „Übernehmen“ (Status dann „In Bearbeitung“)
        self.assigned_hint = QLabel(f"Das Ticket ist {row.get('state') or 'zugewiesen'} und noch nicht übernommen. "
                                    "Matrix42 speichert Änderungen erst, wenn du es übernimmst "
                                    f"(Status danach {mb.WORKING_STATE}).")
        self.assigned_hint.setWordWrap(True)
        self.assigned_hint.setObjectName("hint")
        if not self.needs_take_over():  # nur verstecken, siehe card_dialog.modernize
            self.assigned_hint.hide()
        box.addWidget(self.assigned_hint)

        self.ok_button.clicked.connect(self.save)
        for widget in self._fields():
            widget.setEnabled(False)
        self.validate()
        self.status.setText(f"Lade {row['ticket']} aus Matrix42 …")
        if not self._run("load", id=row["id"], type=row.get("type", "")):
            self.status.setText("⚠ Matrix42-Anmeldefenster ist offen. Bitte erst anmelden.")
            self.description_skeleton.done()
            self.description_skeleton = None
        else:
            self._run("categories")

    def _fields(self):
        return (self.subject_edit, self.category_edit, self.description_edit, self.pen_button)

    def needs_take_over(self):
        """Zugewiesen, noch nicht übernommen: Speichern erst nach „Übernehmen“."""
        return mb.is_assigned(self.row) and self.take_over_button.isVisibleTo(self)

    def _took_over(self):
        """Übernommen: Hinweis weg; Matrix42 hat das Ticket dabei gespeichert (neue Versionsmarke),
        also die Marke frisch holen, ohne Getipptes zu überschreiben."""
        self.assigned_hint.hide()
        if self.loaded and self._run("load", id=self.row["id"], type=self.row.get("type", ""), stamp_only=True):
            self._stamp_pending = True
        self.validate()

    def edit_melder(self):
        """Stift: Melder-Feld zeigen (Name markiert, gleich überschreibbar)."""
        self.melder_box.show()
        self.user_edit.setFocus()
        self.user_edit.selectAll()
        QTimer.singleShot(0, self.adjustSize)

    def _melder_chosen(self):
        self.subject_edit.setFocus()

    def _user_typed(self, text):
        super()._user_typed(text)
        self.validate()

    def new_initiator(self):
        """Gewählter Melder, wenn er ein anderer ist als im Ticket, sonst None."""
        if self.initiator and self.initiator["id"] != (self.loaded or {}).get("initiator"):
            return self.initiator["id"]
        return None

    def keyPressEvent(self, event):
        if not self._melder_keys(event):
            super().keyPressEvent(event)

    def _on_load(self, result):
        if result.get("args", {}).get("stamp_only"):
            self._stamp_pending = False
            if result.get("ok") and self.loaded:
                self.loaded["stamp"] = result["data"]["stamp"]
            elif not result.get("ok"):
                self.status.setText(f"⚠ Ticket nach dem Übernehmen nicht neu geladen: {result.get('error', '')}. "
                                    "Bitte das Fenster schließen und neu öffnen.")
            self.validate()
            return
        if self.description_skeleton is not None:
            self.description_skeleton.done()
            self.description_skeleton = None
        if not result.get("ok"):
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
                or bool(category and category != self.loaded.get("category"))
                or bool(self.new_initiator()))

    def validate(self, *_):
        ok = bool(self.loaded and self.subject_edit.text().strip() and self.changed()) and not self._busy
        if self.categories and self.category_edit.currentText().strip() and not self.category():
            ok = False  # getippter Text ist keine Kategorie
        if self.needs_take_over() or getattr(self, "_stamp_pending", False):
            ok = False  # erst übernehmen (bzw. warten, bis die neue Versionsmarke da ist)
        self.ok_button.setEnabled(ok)
        self.ok_button.setToolTip("Erst übernehmen, dann speichern" if self.needs_take_over()
                                  else "Speichern (Strg+Enter)")
        return ok

    def request(self):
        return {"id": self.row["id"], "ticket": self.row["ticket"], "stamp": self.loaded["stamp"],
                "subject": self.subject_edit.text().strip(), "description": self.description_edit.toPlainText(),
                "category": self.category() or self.loaded.get("category"), "initiator": self.new_initiator(),
                "type": self.loaded.get("type") or self.row.get("type", "")}

    def save(self):
        if self.validate():
            self._start("edit", f"Speichere {self.row['ticket']} in Matrix42 …", request=self.request())

    def _on_edit(self, result):
        if not result.get("ok"):
            self._failed(result, "Speichern")
            return
        self.saved = result["data"]
        self.accept()


def _timeline_image(name, ratio=1.0):
    """Bilder des Verlaufs (m42_tickets.journal_html): „dot:<Art>“ runder Punkt mit Zeichen,
    „line“ Stück der senkrechten Linie (Hintergrund der Spalte, wiederholt)."""
    from PySide6.QtGui import QColor, QFont, QPainter, QPen
    width, height = (30, 4) if name == "line" else (30, 22)
    image = QImage(int(width * ratio), int(height * ratio), QImage.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio)
    image.fill(QColor("white"))
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.fillRect(10, 0, 2, height, QColor("#E4E4E7"))  # Linie (unter dem Punkt geht sie weiter)
    if name.startswith("dot:"):
        sign, color = mt.JOURNAL_KINDS.get(name[4:], mt.JOURNAL_KINDS["change"])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(1, 1, 20, 20)
        p.setPen(QPen(QColor("white")))
        font = QFont(p.font())
        font.setPixelSize(11)
        font.setBold(True)
        p.setFont(font)
        p.drawText(1, 1, 20, 20, Qt.AlignCenter, sign)
    p.end()
    return image


class _DescriptionView(QTextBrowser):
    """Beschreibung: Klartext oder HTML mit Bildern wie in Matrix42. Bilder kommen nur aus der
    Beschreibung selbst (data:), nie aus dem Netz, und werden auf die Breite verkleinert."""

    def __init__(self):
        super().__init__()
        self.setOpenLinks(False)  # Links im Browser bzw. Mailprogramm, nicht im Feld
        self.anchorClicked.connect(self._open_link)

    @staticmethod
    def _open_link(url):
        from PySide6.QtGui import QDesktopServices
        if url.scheme() in ("http", "https", "mailto", "tel"):
            QDesktopServices.openUrl(url)

    def loadResource(self, kind, url):
        if kind == QTextDocument.ImageResource and url.scheme() == "zz":
            return _timeline_image(url.path(), self.devicePixelRatioF())
        if kind != QTextDocument.ImageResource or url.scheme() != "data":
            return None  # nichts nachladen (kein Netz, keine Dateien)
        head, _, payload = url.toString().partition(",")
        try:
            raw = base64.b64decode(payload) if head.endswith(";base64") else unquote_to_bytes(payload)
        except ValueError:
            return None
        image = QImage.fromData(raw)
        width = max(100, self.viewport().width() - 24)
        if not image.isNull() and image.width() > width:
            image = image.scaledToWidth(width, Qt.SmoothTransformation)
        return image

    def show_html(self, text):
        """HTML wie eine E-Mail: dunkle Schrift auf weißem Papier, auch im dunklen Design."""
        # am Feld selbst, sonst gewinnt das Stylesheet des Designs (theme.py)
        self.setStyleSheet("QTextBrowser { background-color: white; color: black; }")
        self.setHtml(mt.view_html(text))  # Bilder ohne feste Größe, damit loadResource sie einpasst


# „Ticket ansehen“: was das große Feld zeigt (Schlüssel, Chip, Hinweis)
VIEW_CHIPS = [("description", "B&eschreibung", "Beschreibung des Tickets"),
              ("journal", "&Verlauf", "E-Mails, Kommentare und Änderungen nach Tagen, das Neueste oben. "
                                     "Klick auf „ganze E-Mail“ klappt sie auf.")]


class ViewTicketDialog(_CardDialog):
    """Ticket ansehen: Eckdaten, Beschreibung oder Verlauf (Zeitstrahl nach Tagen) und Kontakt des Melders
    (Telefon und E-Mail anklickbar). Ändert nichts. Nach dem Schließen sagt self.action, ob
    gleich „Bearbeiten“ ("edit") oder „Schließen“ ("close") folgen soll, sonst None.
    „Übernehmen“ macht dich zum Bearbeiter (self.taken_over, siehe _CardDialog._add_take_over)."""

    def __init__(self, reader, row, parent=None):
        super().__init__(parent)
        self.row = row
        self.loaded = None
        self.action = None
        self._frame(reader, "Ticket ansehen", row.get("subject") or row["ticket"], "eye", "&Bearbeiten …")
        self.setFixedWidth(720)
        self._ticket_line(row)
        box = self.body_box
        self.cancel_button.hide()  # kein „Fertig“: schließen über ✕ oder Esc
        self.ok_button.setToolTip("Betreff, Kategorie oder Beschreibung ändern (Strg+Enter)")
        self.ok_button.clicked.connect(lambda: self._leave("edit"))
        self.close_ticket_button = QPushButton("Ticket &schließen …")
        self.close_ticket_button.setAutoDefault(False)
        self.close_ticket_button.clicked.connect(lambda: self._leave("close"))
        self.cancel_button.parentWidget().layout().insertWidget(1, self.close_ticket_button)
        self.close_ticket_button.setVisible(not mb.is_closed(row))  # erst nach dem Einfügen (s. o.)
        self._add_actions(row)
        self._add_take_over(row)

        cards = QHBoxLayout()
        cards.setSpacing(SPACE_S + 2)
        ticket_card, ticket_rows = self._info_card("tag", "Ticket")
        self.ticket_rows = ticket_rows
        self._fill_rows(ticket_rows, self._ticket_pairs(row.get("recipient", "")))
        contact_card, self.contact_rows = self._info_card("phone", "Kontakt")
        self._show_contact([])
        self._contact_loading = True  # bis der Kontakt da ist: Umrisse für Telefon und E-Mail
        for _ in range(2):
            self.contact_rows.addRow(skeleton.Bar(56, 14), skeleton.Bar(150, 14))
        cards.addWidget(ticket_card, 1)
        cards.addWidget(contact_card, 1)
        box.addLayout(cards)
        # Wer beim Kunden zuständig ist (Verwalter / Delegierter Verwalter aus Matrix42), sobald das Ticket da ist
        self.managers_card, self.manager_rows = self._info_card("users", "Zuständig beim Kunden")
        self.managers_card.setToolTip("Verwalter und Delegierter Verwalter, wie beim Kunden in Matrix42 hinterlegt")
        self.manager_rows.addRow(skeleton.Bar(56, 14), skeleton.Bar(220, 14))
        self.managers = None  # Antwort von "managers", sobald da
        box.addWidget(self.managers_card)

        self.description_view = _DescriptionView()
        self.description_view.setAccessibleName("Beschreibung")
        self.description_view.setTabChangesFocus(True)
        self.description_view.setMinimumHeight(260)
        self.description_skeleton = skeleton.Lines(self.description_view, lines=6)
        # Was im Feld steht: Beschreibung oder Verlauf (alles, nur Nachrichten, nur Änderungen)
        chips_host = QWidget()
        chips_host.setObjectName("chips")
        chips = FlowLayout(chips_host, spacing=6)
        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        self.view_chips = {}
        for key, text, tip in VIEW_CHIPS:
            chip = QCheckBox(text)
            chip.setObjectName("chip_check")
            chip.setToolTip(tip)
            self.view_group.addButton(chip)
            self.view_chips[key] = chip
            chips.addWidget(chip)
            chip.toggled.connect(lambda on, k=key: on and self._show_view(k))
        self.journal = None  # Verlauf, sobald geladen (erst beim ersten Anklicken)
        self.expanded = set()  # aufgeklappte Einträge im Verlauf
        self.description_view.anchorClicked.connect(self._journal_link)
        self._journal_loading = False
        self._description_html = None  # was unter „Beschreibung“ steht (zum Zurückschalten)
        self.view_chips["description"].setChecked(True)
        box.addWidget(chips_host)
        box.addWidget(self.description_view)

        self.ok_button.setEnabled(False)
        self.status.setText(f"Lade {row['ticket']} aus Matrix42 …")
        if not self._run("load", id=row["id"], type=row.get("type", "")):
            self.status.setText("⚠ Matrix42-Anmeldefenster ist offen. Bitte erst anmelden.")
            self._description_done()
            self._show_contact([])
            self.managers_card.hide()

    def _add_actions(self, row):
        """Knopf „Aktionen“ mit Kommentieren, E-Mail senden, Pausieren, Weiterleiten (ticket_action_dialog)."""
        from PySide6.QtWidgets import QMenu
        self.melder_mail = ""
        self.actions_button = QPushButton("&Aktionen")
        self.actions_button.setAutoDefault(False)
        self.actions_button.setToolTip("Kommentieren, E-Mail senden, Pausieren oder Weiterleiten")
        menu = QMenu(self.actions_button)
        for kind, icon, text in (("comment", "comment", "&Kommentieren …"), ("mail", "mail", "&E-Mail senden …"),
                                 ("pause", "pause", "&Pausieren …"), ("forward", "forward", "&Weiterleiten …")):
            action = menu.addAction(icons.icon(icon, self.muted), text)
            action.triggered.connect(lambda _=False, k=kind: self._ticket_action(k))
        self.actions_button.setMenu(menu)
        self.cancel_button.parentWidget().layout().insertWidget(1, self.actions_button)
        self.actions_button.setVisible(not mb.is_closed(row))

    def _ticket_action(self, kind):
        from ticket_action_dialog import TicketActionDialog
        contact = {"email": self.melder_mail, "initiator_id": (self.loaded or {}).get("initiator") or ""}
        dialog = TicketActionDialog(self.reader, self.row, kind, self, contact)
        if dialog.exec() != QDialog.Accepted:
            return
        self.status.setText(dialog.done_text)
        self.journal = None  # neu laden: der Eintrag steht jetzt im Verlauf
        self.view_chips["journal"].setText("&Verlauf")
        if self.view_chips["journal"].isChecked():
            self._show_view("journal")

    def _show_view(self, key):
        """Beschreibung oder Verlauf ins Feld; den Verlauf beim ersten Mal aus Matrix42 laden."""
        view = self.description_view
        view.setAccessibleName(dict((k, t.replace("&", "")) for k, t, _tip in VIEW_CHIPS)[key])
        if key == "description":
            if self._description_html is not None:
                self._fill_description()
            return
        if self.journal is None:
            view.setStyleSheet("")
            view.setPlainText("")
            view.setPlaceholderText("Lade Verlauf aus Matrix42 …")
            if not self._journal_loading:
                self._journal_loading = True
                if not self._run("journal", id=self.row["id"]):
                    self._journal_loading = False
                    view.setPlaceholderText("⚠ Matrix42-Anmeldefenster ist offen. Bitte erst anmelden.")
            return
        self._render_journal()
        view.moveCursor(QTextCursor.Start)

    def _render_journal(self):
        view = self.description_view
        origin = "/".join((getattr(self.reader, "page_url", "") or "").split("/")[:3])
        text = mt.journal_html(self.journal["entries"], self.expanded, origin)
        if text:
            view.show_html(text)
        else:
            view.setStyleSheet("")
            view.setPlainText("")
            view.setPlaceholderText("(keine Einträge)")

    def _journal_link(self, url):
        """„▸ ganze E-Mail“ / „mehr“: Eintrag auf- oder zuklappen, Position im Verlauf bleibt."""
        if url.scheme() == "zz" and url.path().startswith("attachment:"):
            file_id = url.path().partition(":")[2]
            self.status.setText("Lade Anhang aus Matrix42 …")
            if not self._run("attachment", file=file_id):
                self.status.setText("⚠ Matrix42-Anmeldefenster ist offen. Bitte erst anmelden.")
            return
        if url.scheme() != "zz" or not url.path().startswith("toggle:") or self.journal is None:
            return
        self.expanded ^= {url.path().partition(":")[2]}
        bar = self.description_view.verticalScrollBar()
        top = bar.value()
        self._render_journal()
        bar.setValue(top)

    def _on_attachment(self, result):
        """Anhang geladen: öffnen (Programme nicht, dann nur den Ordner zeigen)."""
        import os
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if not result.get("ok"):
            self.status.setText(f"⚠ Anhang nicht geladen: {result.get('error', '')}")
            return
        data = result["data"]
        if data.get("risky"):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(data["path"])))
            self.status.setText(f"„{data['name']}“ könnte ein Programm sein: nicht geöffnet, nur der Ordner.")
            return
        if QDesktopServices.openUrl(QUrl.fromLocalFile(data["path"])):
            self.status.setText(f"„{data['name']}“ geöffnet.")
        else:
            self.status.setText(f"⚠ Kein Programm für „{data['name']}“, liegt in {os.path.dirname(data['path'])}.")

    def _on_journal(self, result):
        self._journal_loading = False
        if not result.get("ok"):
            self.description_view.setPlaceholderText(f"⚠ Verlauf nicht gelesen: {result.get('error', '')}")
            return
        self.journal = result["data"]
        entries = self.journal["entries"]
        self.view_chips["journal"].setText(f"&Verlauf ({len(entries)})")
        if not self.journal.get("complete"):
            self.status.setText(f"Verlauf: die neuesten {len(entries)} Einträge, ältere in Matrix42.")
        current = next((k for k, chip in self.view_chips.items() if chip.isChecked()), "description")
        if current != "description":
            self._show_view(current)

    def _fill_description(self):
        if self._description_html:
            self.description_view.show_html(self._description_html)
        else:
            self.description_view.setStyleSheet("")
            self.description_view.setPlainText((self.loaded or {}).get("description") or "")
        self.description_view.setPlaceholderText("(keine Beschreibung)")

    def _description_done(self):
        if self.description_skeleton is not None:
            self.description_skeleton.done()
            self.description_skeleton = None

    def validate(self, *_):
        return self.ok_button.isEnabled()

    def _ticket_pairs(self, recipient):
        row = self.row
        return [(k, v) for k, v in (
            ("Art", mb.ticket_kind(row)), ("Status", row.get("state", "")), ("Melder", row.get("initiator", "")),
            ("Bearbeiter", recipient), ("Angelegt", mb.ticket_date(row))) if v]

    def _took_over(self):
        self._fill_rows(self.ticket_rows, self._ticket_pairs(self.taken_over or "ich"))

    def _leave(self, action):
        self.action = action
        self.accept()

    def _show_contact(self, rows):
        """Kontaktzeilen (Name, Wert, Link); Links öffnen Telefon-App bzw. E-Mail-Programm."""
        rows = rows or [("Melder", self.row.get("initiator") or "–", "")]
        self._contact_loading = False
        while self.contact_rows.rowCount():
            self.contact_rows.removeRow(0)
        for name, text, link in rows:
            if link.startswith("mailto:") and not self.melder_mail:
                self.melder_mail = text
            key = QLabel(name)
            key.setObjectName("hint")
            value = QLabel()
            value.setWordWrap(True)
            if link:
                value.setTextFormat(Qt.RichText)
                value.setText(f'<a href="{html.escape(link, quote=True)}">{html.escape(text)}</a>')
                value.setOpenExternalLinks(True)
                value.setTextInteractionFlags(Qt.TextBrowserInteraction)
                value.setToolTip(f"{'E-Mail schreiben an' if link.startswith('mailto:') else 'Anrufen:'} {text}")
            else:
                value.setTextFormat(Qt.PlainText)
                value.setText(text)
                value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setAccessibleName(f"{name}: {text}")
            self.contact_rows.addRow(key, value)

    def _on_load(self, result):
        self._description_done()
        if not result.get("ok"):
            self.status.setText(f"⚠ Laden fehlgeschlagen: {result.get('error', '')}")
            self.managers_card.hide()
            self.ok_button.setEnabled(True)  # Bearbeiten zeigt den Fehler genauso, schadet nicht
            if not self._find_melder():  # Kontakt trotzdem: Melder über den Namen suchen
                self._show_contact([])
            return
        self.loaded = result["data"]
        if self.loaded.get("subject"):
            self.subtitle.setText(self.loaded["subject"])
        self._description_html = self.loaded.get("html") or ""  # Bilder, Tabellen, Formatierung wie in Matrix42
        if self.view_chips["description"].isChecked():
            self._fill_description()
        self.ok_button.setEnabled(True)
        self.status.clear()
        if self.managers is None:
            if not (self.loaded.get("ou") and self._run("managers", ou=self.loaded["ou"])):
                self.managers_card.hide()
        contact = self.loaded.get("contact") or {}
        if contact.get("Phone") or contact.get("Email"):  # kam mit dem Ticket
            self._show_contact(mt.contact_rows(contact, self.row.get("initiator", ""),
                                               self.loaded.get("callback", "")))
        elif self.loaded.get("initiator"):
            self.status.setText("Lade Kontakt des Melders …")
            self._run("user_details", user=self.loaded["initiator"])
        else:
            self._show_contact(mt.contact_rows({}, self.row.get("initiator", ""), self.loaded.get("callback", "")))
            self._find_melder()

    def _on_managers(self, result):
        """Verwalter des Kunden: Name, Telefon und E-Mail (anklickbar); „nicht hinterlegt“, wenn keiner da ist."""
        self.managers = (result.get("data") or {}) if result.get("ok") else {}
        rows = self.manager_rows
        while rows.rowCount():
            rows.removeRow(0)
        if not result.get("ok"):
            pairs = [("Verwalter", html.escape(f"nicht gelesen ({result.get('error', '')})"))]
        else:
            pairs = mt.manager_rows(self.managers.get("people"), (self.loaded or {}).get("initiator", ""))
            if not pairs:
                pairs = [("Verwalter", "beim Kunden nicht hinterlegt")]
            elif len(pairs) == 1:  # zeigen, was fehlt: oft ist unklar, wer zuständig ist
                missing = "Delegierter Verwalter" if pairs[0][0] == "Verwalter" else "Verwalter"
                pairs.append((missing, "nicht hinterlegt"))
        for name, text in pairs:
            key = QLabel(name)
            key.setObjectName("hint")
            value = QLabel()
            value.setWordWrap(True)
            value.setTextFormat(Qt.RichText)
            value.setText(text)
            value.setOpenExternalLinks(True)
            value.setTextInteractionFlags(Qt.TextBrowserInteraction)
            value.setAccessibleName(f"{name}: {QTextDocumentFragment.fromHtml(text).toPlainText()}")
            if "nicht" in text and "<a" not in text:
                value.setObjectName("hint")
            rows.addRow(key, value)

    def _find_melder(self):
        """Ohne Id des Melders (Ticket nicht ladbar): Melder aus der Liste per Name suchen."""
        return bool(self.row.get("initiator")) and self._run("melder", name=self.row["initiator"])

    def _on_melder(self, result):
        data = (result.get("data") or {}) if result.get("ok") else {}
        if not data.get("user"):  # nicht gefunden oder nicht eindeutig: lieber keine falsche Nummer zeigen
            if self._contact_loading:
                self._show_contact([])
            return
        self._show_contact(mt.contact_rows(data.get("details"), self.row.get("initiator", ""),
                                           (self.loaded or {}).get("callback", "")))

    def _on_user_details(self, result):
        if not self.loaded or result["args"].get("user") != self.loaded.get("initiator"):
            return
        self.status.clear()
        if not result.get("ok"):
            self.status.setText(f"⚠ Kontakt nicht gelesen: {result.get('error', '')}")
        self._show_contact(mt.contact_rows(result.get("data") if result.get("ok") else {},
                                           self.row.get("initiator", ""), self.loaded.get("callback", "")))
