"""
Dialoge zum Eintragen von Tätigkeiten.

- EntryDialog: Tätigkeit nachtragen oder ändern (Zeit, Kunde, Kategorie, Text).
- PromptWindow: kleines Fenster, mit dem Zeitzeuge nach einer erkannten Tätigkeit
  nachfragt ("TeamViewer 10:05–10:42 beendet. Was hast du gemacht?").
"""

from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QLocale, Qt, QTime, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QLabel, QMenu, QPlainTextEdit,
                               QPushButton, QSpinBox, QTimeEdit, QVBoxLayout, QWidget)

from billing import hours_text
import customers as customer_list
from grouping import format_tv_id
from journal import TIME_FMT, describe, suggest_category, suggest_customer
import snippets as snippet_logic
from tickets import format_ticket_text


class _EntryForm(QWidget):
    """Gemeinsame Felder: Datum, Von, Bis, Kunde, Kategorie, Text."""

    def __init__(self, start, end, customers, categories, customer="", category="", text="",
                 tv_id=None, parent=None, show_date=True, snippets=(), recent_texts=None,
                 ticket="", ticket_suggestions=(), show_ticket=True, trace=None, rule_subject=None):
        super().__init__(parent)
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
        else:  # Nachfrage: der Tag steht fest, ein Feld weniger
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
        if show_ticket or ticket or self.ticket_suggestions:
            label = QLabel("T&icket:")
            label.setBuddy(self.ticket_edit)
            form.addRow(label, ticket_row)
        else:  # kleines Nachfrage-Fenster: ohne Vorschlag keine Zeile
            self.ticket_edit.hide()
        self._update_ticket_take()

    def _update_ticket_take(self, *_args):
        self.ticket_take.setVisible(bool(self.ticket_suggestions)
                                    and not self.ticket_edit.currentText().strip())

    def _take_ticket(self):
        if self.ticket_suggestions:
            self.ticket_edit.setCurrentText(self.ticket_suggestions[0]["ticket"])
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
        }


class EntryDialog(QDialog):
    """Tätigkeit nachtragen oder ändern."""

    def __init__(self, start, end, customers, categories, customer="", category="", text="",
                 tv_id=None, title="Tätigkeit nachtragen", info="", can_delete=False, parent=None,
                 trace=None, rule_subject=None, **form_options):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.deleted = False
        layout = QVBoxLayout(self)
        if info:
            label = QLabel(info)
            label.setWordWrap(True)
            label.setObjectName("hint")
            layout.addWidget(label)
        self.form = _EntryForm(start, end, customers, categories, customer, category, text,
                               tv_id, self, trace=trace, rule_subject=rule_subject, **form_options)
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
            tv_id=entry.get("tv_id"), parent=self, show_date=False,
            trace=trace, rule_subject=rule_subject,
            **{"show_ticket": False, **form_options})
        layout.addWidget(self.form)

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


PROMPT_THRESHOLDS = {"connections": 1, "calls": 1, "rules": 1}


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
    """Einstellungen: Nachfragen nach erkannten Tätigkeiten und Erinnerungen."""

    MODES = [("window", "Kleines Fenster unten rechts"), ("tray", "Nur Meldung im Infobereich"),
             ("off", "Aus (nur in der Zeile „Doku“ zeigen)")]
    SOURCES = [("connections", "&Verbindungen (TeamViewer, RDP, SSH, VPN …)"),
               ("calls", "&Telefonate"),
               ("rules", "Blöcke der &Zuordnung ohne KI (z. B. Outlook, M365-Admin)")]

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Nachfragen und Erinnerungen")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        info = QLabel("Hat Zeitzeuge eine Tätigkeit erkannt, die du noch nicht dokumentiert hast, "
                      "fragt es kurz nach: „Was hast du gemacht?“. So fehlt am Ende des Tages "
                      "nichts im Ticket.")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.mode = QComboBox()
        for key, text in self.MODES:
            self.mode.addItem(text, key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(config.get("prompt_mode", "window"))))
        form.addRow("&Nachfragen als:", self.mode)

        # Je Art: an/aus und ab welcher Dauer gefragt wird
        self.sources, self.thresholds = {}, {}
        sources = config.get("prompt_sources", ["connections", "calls"])
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
        self.config["prompt_end_of_day"] = self.end_of_day.isChecked()
        self.config["prompt_on_quit"] = self.on_quit.isChecked()
        self.config["day_checks_enabled"] = self.day_checks.isChecked()
