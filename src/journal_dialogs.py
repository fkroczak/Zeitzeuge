"""
Dialoge zum Eintragen von Tätigkeiten.

- EntryDialog: Tätigkeit nachtragen oder ändern (Zeit, Kunde, Kategorie, Text).
- PromptWindow: kleines Fenster, mit dem Zeitzeuge nach einer erkannten Tätigkeit
  nachfragt ("TeamViewer 10:05–10:42 beendet. Was hast du gemacht?").
"""

from datetime import datetime, timedelta

import re

from PySide6.QtCore import QDate, QLocale, QModelIndex, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QDateEdit, QDialog, QDialogButtonBox,
                               QFormLayout, QFrame, QHBoxLayout, QLabel, QMenu, QPlainTextEdit,
                               QPushButton, QSpinBox, QTimeEdit, QToolButton, QVBoxLayout,
                               QWidget)

from theme import prose, SPACE_M, SPACE_S, SPACE_XS
from billing import hours_text
import customers as customer_list
from grouping import format_tv_id
from journal import TIME_FMT, describe, suggest_category, suggest_customer
import snippets as snippet_logic
from m42_booking import ticket_label as mb_ticket_label
from tickets import format_ticket_text


class _EntryForm(QWidget):
    """Gemeinsame Felder: Datum, Von, Bis, Kunde, Kategorie, Text."""

    def __init__(self, start, end, customers, categories, customer="", category="", text="",
                 tv_id=None, parent=None, show_date=True, snippets=(), recent_texts=None,
                 ticket="", ticket_suggestions=(), show_ticket=True, trace=None, rule_subject=None,
                 goodwill=False, travel=False, no_surcharge=False, ticket_search=None,
                 ticket_lookup=None):
        super().__init__(parent)
        # ticket_search: Funktion (Suchtext, Fenster) -> Ticket-dict oder None (Matrix42-Suche)
        # ticket_lookup: Funktion (Elternobjekt) -> TicketLookup, Suche beim Tippen im Feld Ticket
        self.ticket_search = ticket_search
        self.ticket_lookup = ticket_lookup
        # trace: (Art, Wert) der Spur, zu der der Kunde gemerkt werden kann (customers.py).
        # rule_subject: Name, zu dem eine geänderte Kategorie als Regel gemerkt werden kann.
        if trace is None and tv_id:
            trace = ("tv", tv_id)
        self.trace = trace
        self.rule_subject = rule_subject
        self._suggested_customer = (customer or "").strip()
        self._suggested_category = (category or "").strip()
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)

        self.date_edit = QDateEdit(QDate(start.year, start.month, start.day))
        self.date_edit.setLocale(QLocale(QLocale.German, QLocale.Germany))  # "Mi" statt "Wed"
        self.date_edit.setDisplayFormat("ddd dd.MM.yyyy")
        self.date_edit.setCalendarPopup(True)
        if show_date:
            form.addRow("&Datum:", self.date_edit)
        else:
            self.date_edit.hide()

        times = QHBoxLayout()
        self.start_edit = QTimeEdit(QTime(start.hour, start.minute))
        self.end_edit = QTimeEdit(QTime(end.hour, end.minute) if end.date() == start.date()
                                  else QTime(23, 59))
        for edit in (self.start_edit, self.end_edit):
            edit.setDisplayFormat("HH:mm")
        self.start_edit.setAccessibleName("Von")
        self.end_edit.setAccessibleName("Bis")
        bis = QLabel("&bis")
        bis.setBuddy(self.end_edit)
        times.addWidget(self.start_edit)
        times.addWidget(bis)
        times.addWidget(self.end_edit)
        self.duration = QLabel()
        self.duration.setObjectName("hint")
        times.addWidget(self.duration, 1)
        von = QLabel("&Von:")
        von.setBuddy(self.start_edit)
        form.addRow(von, times)

        self.customer_edit = QComboBox()
        self.customer_edit.setEditable(True)
        self.customer_edit.setInsertPolicy(QComboBox.NoInsert)
        self.customer_edit.addItems([""] + [c for c in customers if c])
        self.customer_edit.setCurrentText(customer)
        self.customer_edit.lineEdit().setPlaceholderText(
            f"Kunde für {customer_list.display(*trace)}" if trace else "Kunde oder System")
        self.customer_edit.lineEdit().setAccessibleName("Kunde")
        form.addRow("&Kunde:", self.customer_edit)

        # Kunde zur Spur merken (Kundenliste). TeamViewer wie bisher immer sichtbar,
        # andere Spuren erst, wenn du den vorgeschlagenen Kunden änderst.
        self.remember_tv = None
        if trace:
            label = (f"Name für TeamViewer-ID {format_tv_id(trace[1])} merken" if trace[0] == "tv"
                     else f"Kunde für {customer_list.display(*trace)} &merken")
            self.remember_tv = QCheckBox(label)
            self.remember_tv.setChecked(True)
            form.addRow("", self.remember_tv)
            if trace[0] != "tv":
                self.customer_edit.currentTextChanged.connect(self._update_learning)

        self.category_edit = QComboBox()
        self.category_edit.setEditable(True)
        self.category_edit.addItems([""] + list(categories))
        self.category_edit.setCurrentText(category)
        self.category_edit.lineEdit().setAccessibleName("Kategorie")
        form.addRow("Kate&gorie:", self.category_edit)

        # Kategorie geändert: als Regel für die Zuordnung ohne KI merken (nur wenn angehakt)
        self.learn_rule = None
        if rule_subject:
            self.learn_rule = QCheckBox()
            self.learn_rule.setChecked(False)
            self.learn_rule.setToolTip("Legt eine Regel in „Zuordnung ohne KI“ an. "
                                       "Zeitzeuge schlägt die Kategorie dann selbst vor.")
            form.addRow("", self.learn_rule)
            self.category_edit.currentTextChanged.connect(self._update_learning)
        self._update_learning()

        # Wie in der Matrix42-Zeiterfassung: Kulanz (nicht berechnen) und Reise (Anfahrt)
        self.goodwill_box = QCheckBox("K&ulanz")
        self.goodwill_box.setToolTip("Nicht berechnen. Wird beim Buchen in Matrix42 als Kulanz übernommen.")
        self.goodwill_box.setChecked(bool(goodwill))
        self.travel_box = QCheckBox("&Reise / Anfahrt")
        self.travel_box.setToolTip("Fahrzeit. Wird beim Buchen in Matrix42 als Reise übernommen.")
        self.travel_box.setChecked(bool(travel))
        self.surcharge_box = QCheckBox("&Zuschlag ignorieren")
        self.surcharge_box.setToolTip("Keine Zuschläge (z. B. außerhalb der Servicezeit). "
                                      "Wird beim Buchen in Matrix42 übernommen.")
        self.surcharge_box.setChecked(bool(no_surcharge))
        flags = QHBoxLayout()
        flags.addWidget(self.goodwill_box)
        flags.addWidget(self.travel_box)
        flags.addWidget(self.surcharge_box)
        flags.addStretch(1)
        form.addRow("", flags)

        self.text_edit = QPlainTextEdit(text)
        self.text_edit.setPlaceholderText("Was hast du gemacht? z. B. „Drucker neu eingerichtet, "
                                          "Treiber aktualisiert“")
        self.text_edit.setTabChangesFocus(True)
        self.text_edit.setFixedHeight(80)
        form.addRow("&Tätigkeit:", self.text_edit)
        self._add_text_helpers(form, snippets, recent_texts, ticket, ticket_suggestions, show_ticket)

        self.error = QLabel()
        self.error.setObjectName("hint")
        self.error.setWordWrap(True)
        form.addRow("", self.error)

        for edit in (self.start_edit, self.end_edit):
            edit.timeChanged.connect(self.validate)
        self.validate_hook = None
        self.billing = None  # billing.Billing: "abgerechnet …" neben der Dauer (set_billing)
        self.customer_edit.currentTextChanged.connect(lambda _t: self.validate())
        self.validate()

    def set_billing(self, billing):
        self.billing = billing
        self.validate()

    # ---- Textbausteine, zuletzt benutzte Texte, Ticket (snippets.py, tickets.py)

    def _add_text_helpers(self, form, snippets, recent_texts, ticket, suggestions, show_ticket):
        self.snippets = list(snippets or [])
        self.recent_texts = recent_texts  # Funktion Kunde -> [Texte] oder None
        self.insert_button = QPushButton("Text &einfügen")
        self.insert_button.setAutoDefault(False)
        self.insert_button.setAccessibleName("Textbaustein oder zuletzt benutzten Text einfügen")
        self.insert_button.setToolTip("Textbaustein oder zuletzt benutzten Text zum Kunden "
                                      "an der Cursorposition einfügen")
        self.insert_menu = QMenu(self.insert_button)
        self.insert_menu.aboutToShow.connect(self._fill_insert_menu)
        self.insert_button.setMenu(self.insert_menu)
        row = QHBoxLayout()
        row.addWidget(self.insert_button)
        row.addStretch(1)
        form.addRow("", row)

        # Ticket: nur Vorschläge, nie automatisch eingesetzt
        self.ticket_suggestions = list(suggestions or [])
        self.ticket_edit = QComboBox()
        self.ticket_edit.setEditable(True)
        self.ticket_edit.setInsertPolicy(QComboBox.NoInsert)
        self.ticket_edit.addItem("")
        for s in self.ticket_suggestions:
            self.ticket_edit.addItem(s["ticket"])
            self.ticket_edit.setItemData(self.ticket_edit.count() - 1, s["label"], Qt.ToolTipRole)
        self.ticket_edit.setCurrentText(ticket)
        self.ticket_edit.setAccessibleName("Ticket")
        self.ticket_edit.lineEdit().setAccessibleName("Ticket")
        top = self.ticket_suggestions[0]["label"] if self.ticket_suggestions else ""
        self.ticket_edit.lineEdit().setPlaceholderText(f"Gefunden: {top}" if top
                                                       else "Ticketnummer, z. B. TCK0000049374")
        self.ticket_take = QPushButton("&Übernehmen")
        self.ticket_take.setAutoDefault(False)
        self.ticket_take.setAccessibleName("Gefundenes Ticket übernehmen")
        self.ticket_take.setToolTip(f"{top} ins Feld „Ticket“ übernehmen" if top else "")
        self.ticket_take.clicked.connect(self._take_ticket)
        self.ticket_edit.currentTextChanged.connect(self._update_ticket_take)
        ticket_row = QHBoxLayout()
        ticket_row.addWidget(self.ticket_edit, 1)
        ticket_row.addWidget(self.ticket_take)
        self.ticket_search_button = None
        if self.ticket_search:
            self.ticket_search_button = QPushButton("Su&chen …")
            self.ticket_search_button.setAutoDefault(False)
            self.ticket_search_button.setAccessibleName("Ticket in Matrix42 suchen")
            self.ticket_search_button.setToolTip("Ticket in Matrix42 nach Kunde, Benutzer, "
                                                 "Ticketnummer oder Titel suchen")
            self.ticket_search_button.clicked.connect(self._search_ticket)
            ticket_row.addWidget(self.ticket_search_button)
        self.ticket_status = QLabel()
        self.ticket_status.setObjectName("hint")
        self.ticket_status.setWordWrap(True)
        self.ticket_status.hide()
        self._setup_ticket_lookup()
        if show_ticket or ticket or self.ticket_suggestions or self.ticket_search:
            label = QLabel("T&icket:")
            label.setBuddy(self.ticket_edit)
            form.addRow(label, ticket_row)
            form.addRow("", self.ticket_status)
        else:  # kleines Nachfrage-Fenster: ohne Vorschlag keine Zeile
            self.ticket_edit.hide()
        self._update_ticket_take()

    # Suche beim Tippen: „Lesana Telefon“ ins Feld Ticket, Treffer aus Matrix42 darunter
    LOOKUP_DELAY_MS = 500
    TICKET_NUMBER = re.compile(r"^[A-Za-z]{2,5}\d{4,}$")

    def _setup_ticket_lookup(self):
        self._lookup = self.ticket_lookup(self) if self.ticket_lookup else None
        if self._lookup is None:
            return
        self.ticket_edit.lineEdit().setPlaceholderText(
            self.ticket_edit.lineEdit().placeholderText() + " · oder Kunde/Titel tippen (Matrix42)")
        self._lookup_model = QStandardItemModel(self)
        self._completer = QCompleter(self._lookup_model, self)
        self._completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self._completer.setWidget(self.ticket_edit.lineEdit())
        self._completer.activated[QModelIndex].connect(self._pick_lookup)
        self._lookup_timer = QTimer(self)
        self._lookup_timer.setSingleShot(True)
        self._lookup_timer.setInterval(self.LOOKUP_DELAY_MS)
        self._lookup_timer.timeout.connect(self._start_lookup)
        self._lookup.found.connect(self._on_lookup)
        self.ticket_edit.lineEdit().textEdited.connect(self._ticket_typed)

    def _ticket_typed(self, text):
        text = text.strip()
        if len(text) < 3 or self.TICKET_NUMBER.match(text):  # Nummer: nichts zu suchen
            self._lookup_timer.stop()
            self._completer.popup().hide()
            self.ticket_status.hide()
            return
        self._lookup_timer.start()

    def _start_lookup(self):
        text = self.ticket_edit.currentText().strip()
        self.ticket_status.setText(f"Suche „{text}“ in Matrix42 …")
        self.ticket_status.show()
        self._lookup.lookup(text)

    def _on_lookup(self, text, rows, error):
        if text != self.ticket_edit.currentText().strip():
            return  # inzwischen weitergetippt: die neuere Suche kommt noch
        self._lookup_model.clear()
        for row in rows:
            item = QStandardItem(mb_ticket_label(row))
            item.setData(row, Qt.UserRole)
            item.setToolTip(mb_ticket_label(row))
            self._lookup_model.appendRow(item)
        if rows:
            self.ticket_status.setText(f"{len(rows)} Ticket{'s' if len(rows) != 1 else ''} in Matrix42. "
                                       "Auswählen übernimmt die Nummer.")
            self._completer.complete()
        else:
            self.ticket_status.setText(f"Kein Ticket in Matrix42 gefunden{': ' + error if error else '.'}")

    def _pick_lookup(self, index):
        row = index.data(Qt.UserRole) or {}
        if not row.get("ticket"):
            return
        # erst nach dem Completer setzen, der sonst den ganzen Eintrag ins Feld schreibt
        QTimer.singleShot(0, lambda: self._take_found_ticket(row))

    def _take_found_ticket(self, row):
        self.ticket_edit.setCurrentText(row["ticket"])
        if not self.customer_edit.currentText().strip() and row.get("customer"):
            self.customer_edit.setCurrentText(row["customer"])
        self.ticket_status.hide()
        self.text_edit.setFocus()

    def _update_ticket_take(self, *_args):
        self.ticket_take.setVisible(bool(self.ticket_suggestions)
                                    and not self.ticket_edit.currentText().strip())

    def _take_ticket(self):
        if self.ticket_suggestions:
            self.ticket_edit.setCurrentText(self.ticket_suggestions[0]["ticket"])
            self.text_edit.setFocus()

    def _search_ticket(self):
        """Matrix42-Suche öffnen, vorbelegt mit dem Kunden; gewähltes Ticket übernehmen."""
        typed = self.ticket_edit.currentText().strip()
        text = typed if typed and not self.TICKET_NUMBER.match(typed) else ""
        row = self.ticket_search(text or self.customer_edit.currentText().strip(), self.window())
        if not row or not row.get("ticket"):
            return
        self.ticket_edit.setCurrentText(row["ticket"])
        if not self.customer_edit.currentText().strip() and row.get("customer"):
            self.customer_edit.setCurrentText(row["customer"])
        self.text_edit.setFocus()

    def _fill_insert_menu(self):
        """Menü beim Öffnen neu füllen: Bausteine und die letzten Texte zum gewählten Kunden."""
        menu = self.insert_menu
        menu.clear()
        number = 0

        def add(text, group_size):
            nonlocal number
            if group_size and group_size % 5 == 0:
                menu.addSeparator()  # höchstens 5 Einträge je Gruppe
            number += 1
            mark = f"&{number} " if number < 10 else ""
            menu.addAction(mark + snippet_logic.menu_label(text), lambda t=text: self.insert_text(t))

        if self.snippets:
            menu.addSection("Textbausteine")
            for i, text in enumerate(self.snippets):
                add(text, i)
        customer = self.customer_edit.currentText().strip()
        recent = self.recent_texts(customer) if self.recent_texts and customer else []
        if recent:
            menu.addSection(f"Zuletzt zu {customer.replace('&', '&&')}")
            for i, text in enumerate(recent[:5]):
                add(text, i)
        if not self.snippets and not recent:
            menu.addAction("Keine Textbausteine (Einstellungen → Textbausteine)").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Als Ticket-Doku &gliedern („- “ / „-- “)", self.outline_text)

    def insert_text(self, snippet):
        """Baustein an der Cursorposition bzw. als neue Zeile einfügen."""
        cursor = self.text_edit.textCursor()
        text, pos = snippet_logic.insert(self.text_edit.toPlainText(), cursor.position(), snippet)
        self.text_edit.setPlainText(text)
        cursor = self.text_edit.textCursor()
        cursor.setPosition(pos)
        self.text_edit.setTextCursor(cursor)
        self.text_edit.setFocus()

    def outline_text(self):
        """Erste Zeile „- “, weitere „-- “ (Format der Ticket-Dokumentation)."""
        self.text_edit.setPlainText(format_ticket_text(self.text_edit.toPlainText(), "dash"))
        self.text_edit.moveCursor(self.text_edit.textCursor().MoveOperation.End)
        self.text_edit.setFocus()

    def _customer_changed(self):
        text = self.customer_edit.currentText().strip()
        return bool(text) and text != self._suggested_customer

    def _category_changed(self):
        text = self.category_edit.currentText().strip()
        return bool(text) and text != self._suggested_category

    def _update_learning(self, *_):
        if self.remember_tv and self.trace and self.trace[0] != "tv":
            self.remember_tv.setVisible(self._customer_changed())
        if self.learn_rule:
            category = self.category_edit.currentText().strip()
            self.learn_rule.setText(f"Als &Regel merken: „{self.rule_subject}“ → {category}")
            self.learn_rule.setVisible(self._category_changed())

    def remember_customer(self):
        """Kunde zur Spur merken? (TeamViewer: Haken; sonst nur, wenn der Kunde geändert ist)"""
        if not (self.remember_tv and self.remember_tv.isChecked()):
            return False
        return self.trace[0] == "tv" or self._customer_changed()

    def wants_rule(self):
        """Geänderte Kategorie als Regel merken? (Haken, standardmäßig aus)"""
        return bool(self.learn_rule and self.learn_rule.isChecked() and self._category_changed())

    def times(self):
        day = self.date_edit.date().toPython()
        start = datetime.combine(day, self.start_edit.time().toPython().replace(second=0))
        end = datetime.combine(day, self.end_edit.time().toPython().replace(second=0))
        return start, end

    def validate(self):
        start, end = self.times()
        ok = end > start
        self.error.setText("" if ok else "⚠ Fehler: „Bis“ muss nach „Von“ liegen.")
        self.error.setVisible(not ok)
        minutes = int((end - start).total_seconds() // 60)
        text = f"{minutes // 60}:{minutes % 60:02d} h" if ok else ""
        customer = self.customer_edit.currentText().strip()
        if ok and self.billing and self.billing.active(customer):
            text += f", abgerechnet {hours_text(self.billing.minutes(minutes * 60, customer))}"
        self.duration.setText(text)
        if self.validate_hook:
            self.validate_hook(ok)
        return ok

    def item(self):
        start, end = self.times()
        return {
            "start": start.strftime(TIME_FMT),
            "end": end.strftime(TIME_FMT),
            "customer": self.customer_edit.currentText().strip(),
            "category": self.category_edit.currentText().strip(),
            "text": self.text_edit.toPlainText().strip(),
            "ticket": self.ticket_edit.currentText().strip(),
            "goodwill": self.goodwill_box.isChecked(),
            "travel": self.travel_box.isChecked(),
            "no_surcharge": self.surcharge_box.isChecked(),
        }


class EntryDialog(QDialog):
    """Tätigkeit nachtragen oder ändern."""

    def __init__(self, start, end, customers, categories, customer="", category="", text="",
                 tv_id=None, title="Tätigkeit nachtragen", info="", can_delete=False, parent=None,
                 trace=None, rule_subject=None, context_for=None, **form_options):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.deleted = False
        layout = QVBoxLayout(self)
        if info:
            label = QLabel(info)
            label.setWordWrap(True)
            prose(label)
            label.setObjectName("hint")
            layout.addWidget(label)
        self.form = _EntryForm(start, end, customers, categories, customer, category, text,
                               tv_id, self, trace=trace, rule_subject=rule_subject, **form_options)
        # Zeitraum nachtragen (Companion): was die Quellen in dieser Zeit sagen, Feinjustieren
        self.context_for = context_for
        self.context_rows = None
        if context_for:
            self.setMinimumWidth(560)
            layout.addWidget(self._context_card())
            self.form.start_edit.timeChanged.connect(lambda _t: self.update_context())
            self.form.end_edit.timeChanged.connect(lambda _t: self.update_context())
            self.update_context()
        layout.addWidget(self.form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("&Speichern")
        if can_delete:
            delete = self.buttons.addButton("&Löschen", QDialogButtonBox.DestructiveRole)
            delete.clicked.connect(self._delete)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.form.validate_hook = self.buttons.button(QDialogButtonBox.Ok).setEnabled
        self.form.validate()
        self.form.text_edit.setFocus()

    def _context_card(self):
        card = QFrame()
        card.setObjectName("card")
        box = QVBoxLayout(card)
        box.setContentsMargins(SPACE_M, SPACE_M, SPACE_M, SPACE_M)
        box.setSpacing(SPACE_S)
        head = QLabel("Was die Quellen in dieser Zeit sagen")
        head.setObjectName("card_title")
        box.addWidget(head)
        self.context_rows = QFormLayout()
        self.context_rows.setHorizontalSpacing(SPACE_M)
        self.context_rows.setVerticalSpacing(SPACE_XS)
        box.addLayout(self.context_rows)
        return card

    def update_context(self):
        if self.context_rows is None:
            return
        while self.context_rows.rowCount():
            self.context_rows.removeRow(0)
        start, end = self.form.times()
        rows = self.context_for(start, end) if end > start else []
        for source, text in rows or [("", "Keine Spuren in dieser Zeit.")]:
            name = QLabel(source)
            name.setObjectName("hint")
            value = QLabel(text)
            value.setWordWrap(True)
            self.context_rows.addRow(name, value)

    def _delete(self):
        self.deleted = True
        self.accept()

    def item(self):
        return self.form.item()

    def remember_tv(self):
        """Kunde zur Spur merken (Name stammt aus der Zeit, als es nur TeamViewer gab)."""
        return self.form.remember_customer()

    def wants_rule(self):
        return self.form.wants_rule()


class PromptWindow(QDialog):
    """Nachfrage nach einer erkannten Tätigkeit. Bleibt oben, nimmt aber nicht den Fokus weg.

    Signal answered(action, entry, item): action = "save" | "later" | "ignore".
    """
    answered = Signal(str, dict, dict)

    def __init__(self, entry, customers, categories, tv_names=None, pending=0, parent=None,
                 customer=None, category=None, trace=None, rule_subject=None, **form_options):
        super().__init__(parent, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.entry = entry
        self.setWindowTitle("Zeitzeuge: Was hast du gemacht?")
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)

        if entry.get("idle"):  # Leerlauf (Companion): Frage statt „Erkannt:“
            start_t = datetime.strptime(entry["start"], TIME_FMT)
            end_t = datetime.strptime(entry["end"], TIME_FMT)
            minutes = int(round((end_t - start_t).total_seconds() / 60))
            head = QLabel(f"Du warst <b>{minutes} Min. nicht am Rechner</b> "
                          f"({start_t:%H:%M}–{end_t:%H:%M}). Was hast du gemacht?")
        else:
            head = QLabel(f"<b>Erkannt:</b> {describe(entry)}")
        head.setWordWrap(True)
        head.setTextFormat(Qt.RichText)
        layout.addWidget(head)
        self.pending_label = QLabel()
        self.pending_label.setObjectName("hint")
        layout.addWidget(self.pending_label)
        self.set_pending(pending)

        start = datetime.strptime(entry["start"], TIME_FMT)
        end = datetime.strptime(entry["end"], TIME_FMT)
        self.form = _EntryForm(
            start, end, customers, categories,
            customer=suggest_customer(entry, tv_names) if customer is None else customer,
            category=suggest_category(entry, categories) if category is None else category,
            tv_id=entry.get("tv_id"), parent=self,
            trace=trace, rule_subject=rule_subject,
            **{"show_ticket": False, **form_options})
        layout.addWidget(self.form)
        if entry.get("idle"):
            self._add_quick_choices(layout)
            self.setMinimumWidth(620)  # Platz für die Schnellauswahl

        buttons = QDialogButtonBox()
        self.save_btn = buttons.addButton("&Speichern", QDialogButtonBox.AcceptRole)
        self.save_btn.setDefault(True)
        later = buttons.addButton("S&päter fragen", QDialogButtonBox.RejectRole)
        later.setToolTip("In 15 Minuten noch einmal fragen")
        ignore = buttons.addButton("&Nicht dokumentieren", QDialogButtonBox.DestructiveRole)
        ignore.setToolTip("Für diesen Eintrag nicht mehr fragen (z. B. privat oder intern)")
        self.save_btn.clicked.connect(lambda: self._answer("save"))
        later.clicked.connect(lambda: self._answer("later"))
        ignore.clicked.connect(lambda: self._answer("ignore"))
        layout.addWidget(buttons)
        self.form.validate_hook = self.save_btn.setEnabled
        self.form.validate()
        self.form.text_edit.setFocus()  # gleich losschreiben
        self._done = False

    def _add_quick_choices(self, layout):
        """Abwesenheit: typische Tätigkeiten mit einem Klick (idle_watch.QUICK_CHOICES)."""
        from idle_watch import QUICK_CHOICES
        row = QHBoxLayout()
        row.setSpacing(SPACE_S)
        row.addWidget(QLabel("Was war?"))
        self.quick_buttons = []
        for label, category, text, flags in QUICK_CHOICES:
            button = QToolButton()  # Chip wie in Companion; gewählt = gefüllt
            button.setObjectName("chip")
            button.setText(label)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(f"{category}: {text}" + (" (gleich speichern)" if flags.get("save") else ""))
            button.clicked.connect(lambda _c=False, a=(category, text, flags): self.quick_choice(*a))
            row.addWidget(button)
            self.quick_buttons.append(button)
        row.addStretch(1)
        layout.insertLayout(2, row)  # gleich unter der Frage, über dem Formular
        note = QLabel("🔒 Bleibt verschlüsselt auf diesem PC.")
        note.setObjectName("hint")
        layout.addWidget(note)

    def quick_choice(self, category, text, flags=None):
        flags = flags or {}
        self.form.category_edit.setCurrentText(category)
        # Eigenen Text nicht überschreiben, den einer anderen Schnellauswahl schon
        current = self.form.text_edit.toPlainText().strip()
        if not current or current == getattr(self, "_quick_text", None):
            self.form.text_edit.setPlainText(text)
            self._quick_text = text
        self.form.travel_box.setChecked(bool(flags.get("travel")))
        if flags.get("save"):
            self._answer("save")
        else:
            self.form.text_edit.setFocus()
            self.form.text_edit.selectAll()

    def set_pending(self, pending):
        self.pending_label.setText(f"Außerdem noch {pending} weitere offen." if pending else "")
        self.pending_label.setVisible(bool(pending))

    def _answer(self, action):
        if action == "save" and not self.form.validate():
            return
        self._done = True
        self.answered.emit(action, self.entry, self.form.item() if action == "save" else {})
        self.close()

    def item(self):
        return self.form.item()

    def remember_tv(self):
        """Kunde zur Spur merken (Name stammt aus der Zeit, als es nur TeamViewer gab)."""
        return self.form.remember_customer()

    def wants_rule(self):
        return self.form.wants_rule()

    def reject(self):  # Esc oder Fenster schließen = später fragen
        if not self._done:
            self._done = True
            self.answered.emit("later", self.entry, {})
        super().reject()

    def closeEvent(self, event):
        if not self._done:
            self._done = True
            self.answered.emit("later", self.entry, {})
        super().closeEvent(event)


def default_span(date, minute=None):
    """Startwerte für "Tätigkeit nachtragen": heute die letzte halbe Stunde, sonst 30 min ab minute."""
    if minute is None:
        now = datetime.now()
        if date == now.date():
            end = now.replace(second=0, microsecond=0)
            return end - timedelta(minutes=30), end
        minute = 9 * 60
    minute = max(0, min(int(minute) // 5 * 5, 23 * 60 + 25))
    start = datetime.combine(date, datetime.min.time()) + timedelta(minutes=minute)
    return start, start + timedelta(minutes=30)


PROMPT_THRESHOLDS = {"connections": 1, "calls": 1, "pc": 15, "meetings": 5, "mails": 0,
                     "credentials": 0, "rules": 1}
# Standard: wonach gefragt wird (Zugangsdaten und Regel-Blöcke nur auf Wunsch)
PROMPT_SOURCES = ["connections", "calls", "pc", "meetings", "mails"]


def prompt_thresholds(config):
    """Mindestdauer (Minuten) fürs Nachfragen je Art: Verbindungen, Telefonate, Regel-Blöcke."""
    saved = config.get("prompt_thresholds")
    result = dict(PROMPT_THRESHOLDS)
    if isinstance(saved, dict):
        for key, value in saved.items():
            if key in result and isinstance(value, (int, float)) and value >= 0:
                result[key] = value
    return result


class DocPromptDialog(QDialog):
    """Einstellungen: Nachfragen nach erkannten Tätigkeiten, Erinnerungen und Benachrichtigungen."""

    MODES = [("window", "Kleines Fenster unten rechts"), ("tray", "Nur Meldung im Infobereich"),
             ("off", "Aus (nur in der Zeile „Doku“ zeigen)")]
    SOURCES = [("connections", "&Verbindungen (TeamViewer, RDP, SSH, VPN …)"),
               ("calls", "&Telefonate (3CX, Teams)"),
               ("pc", "Arbeitsblöcke am P&C (z. B. M365-Admin, Remotedesktop, Ticketsystem)"),
               ("meetings", "Teams-Bespr&echungen, an denen du teilgenommen hast"),
               ("mails", "&Mails an Kunden aus der Kundenliste"),
               ("credentials", "Angezeigte Zugangs&daten (RDM)"),
               ("rules", "Blöcke der &Zuordnung ohne KI (z. B. Outlook, M365-Admin)")]

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Nachfragen und Benachrichtigungen")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        info = QLabel("Erkennt Zeitzeuge eine Tätigkeit ohne Dokumentation, fragt es nach: "
                      "„Was hast du gemacht?“. So fehlt abends nichts im Ticket. Was zusammengehört "
                      "(gleicher Kunde, gleiche Zeit), fragt es nur einmal ab.")
        info.setWordWrap(True)
        prose(info)
        layout.addWidget(info)

        form = QFormLayout()
        self.mode = QComboBox()
        for key, text in self.MODES:
            self.mode.addItem(text, key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(config.get("prompt_mode", "window"))))
        form.addRow("&Nachfragen als:", self.mode)

        # Je Art: an/aus und ab welcher Dauer gefragt wird
        self.sources, self.thresholds = {}, {}
        sources = config.get("prompt_sources", PROMPT_SOURCES)
        limits = prompt_thresholds(config)
        for i, (key, text) in enumerate(self.SOURCES):
            box = QCheckBox(text)
            box.setChecked(key in sources)
            spin = QSpinBox()
            spin.setRange(0, 240)
            spin.setPrefix("ab ")
            spin.setSuffix(" min")
            spin.setSpecialValueText("immer")
            spin.setValue(int(limits[key]))
            spin.setToolTip("Kürzere Tätigkeiten dieser Art nicht nachfragen")
            spin.setAccessibleName(f"Mindestdauer für {text.replace('&', '').split(' (')[0]}")
            spin.setEnabled(box.isChecked())
            box.toggled.connect(spin.setEnabled)
            row = QHBoxLayout()
            row.addWidget(box, 1)
            row.addWidget(spin)
            self.sources[key], self.thresholds[key] = box, spin
            form.addRow("Fragen bei:" if i == 0 else "", row)

        # Abwesenheit am PC: bei der ersten Eingabe danach fragen (idle_watch.py)
        idle_minutes = int(config.get("idle_prompt_minutes", 15) or 0)
        self.idle_box = QCheckBox("&Abwesenheit am PC (keine Maus/Tastatur)")
        self.idle_box.setToolTip("Bei der ersten Eingabe danach fragen, was in der Zeit war, "
                                 "z. B. Telefonat, Besprechung, Vor Ort, Pause")
        self.idle_box.setChecked(idle_minutes > 0)
        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(5, 240)
        self.idle_spin.setPrefix("ab ")
        self.idle_spin.setSuffix(" min")
        self.idle_spin.setValue(idle_minutes if idle_minutes > 0 else 15)
        self.idle_spin.setAccessibleName("Mindestdauer für Abwesenheit am PC")
        self.idle_spin.setEnabled(self.idle_box.isChecked())
        self.idle_box.toggled.connect(self.idle_spin.setEnabled)
        idle_row = QHBoxLayout()
        idle_row.addWidget(self.idle_box, 1)
        idle_row.addWidget(self.idle_spin)
        form.addRow("", idle_row)

        self.snooze = QSpinBox()
        self.snooze.setRange(1, 480)
        self.snooze.setSuffix(" min")
        self.snooze.setValue(config.get("prompt_snooze_minutes", 15))
        form.addRow("„&Später fragen“ nach:", self.snooze)

        self.end_of_day = QCheckBox("Nach &Feierabend an Offenes erinnern")
        self.end_of_day.setChecked(config.get("prompt_end_of_day", True))
        form.addRow("", self.end_of_day)
        self.on_quit = QCheckBox("Beim &Beenden an Offenes erinnern")
        self.on_quit.setChecked(config.get("prompt_on_quit", True))
        form.addRow("", self.on_quit)
        self.day_checks = QCheckBox("Bei Feierabend &prüfen: Pausen, Stempelung, Buchungen")
        self.day_checks.setToolTip("Mehr als 6 Stunden ohne 30 Minuten Pause, PC aktiv aber "
                                   "ausgestempelt, Buchung außerhalb der Personalzeit, "
                                   "Buchungen überschneiden sich, Quote unter Ziel")
        self.day_checks.setChecked(config.get("day_checks_enabled", True))
        form.addRow("", self.day_checks)

        # Meldungen unten rechts (Windows-Benachrichtigungen), die nur informieren
        self.close_hint = QCheckBox("Hinweis „Zeitzeuge &läuft weiter“ beim Schließen des Fensters")
        self.close_hint.setToolTip("Erscheint einmal je Start, wenn du das Fenster schließt und "
                                   "Zeitzeuge im Infobereich weiter aufzeichnet")
        self.close_hint.setChecked(config.get("tray_hint_on_close", True))
        form.addRow("Benachrichtigungen:", self.close_hint)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply(self):
        self.config["prompt_mode"] = self.mode.currentData()
        self.config["prompt_sources"] = [k for k, box in self.sources.items() if box.isChecked()]
        self.config["prompt_thresholds"] = {k: spin.value() for k, spin in self.thresholds.items()}
        self.config["prompt_snooze_minutes"] = self.snooze.value()
        self.config["idle_prompt_minutes"] = self.idle_spin.value() if self.idle_box.isChecked() else 0
        self.config["prompt_end_of_day"] = self.end_of_day.isChecked()
        self.config["prompt_on_quit"] = self.on_quit.isChecked()
        self.config["day_checks_enabled"] = self.day_checks.isChecked()
        self.config["tray_hint_on_close"] = self.close_hint.isChecked()
