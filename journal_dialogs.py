"""
Dialoge zum Eintragen von Tätigkeiten.

- EntryDialog: Tätigkeit nachtragen oder ändern (Zeit, Kunde, Kategorie, Text).
- PromptWindow: kleines Fenster, mit dem Zeitzeuge nach einer erkannten Tätigkeit
  nachfragt ("TeamViewer 10:05–10:42 beendet. Was hast du gemacht?").
"""

from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QLocale, Qt, QTime, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QLabel, QPlainTextEdit, QSpinBox,
                               QTimeEdit, QVBoxLayout, QWidget)

import customers as customer_list
from grouping import format_tv_id
from journal import TIME_FMT, describe, suggest_category, suggest_customer


class _EntryForm(QWidget):
    """Gemeinsame Felder: Datum, Von, Bis, Kunde, Kategorie, Text."""

    def __init__(self, start, end, customers, categories, customer="", category="", text="",
                 tv_id=None, parent=None, show_date=True, trace=None, rule_subject=None):
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
            text = (f"Name für TeamViewer-ID {format_tv_id(trace[1])} merken" if trace[0] == "tv"
                    else f"Kunde für {customer_list.display(*trace)} &merken")
            self.remember_tv = QCheckBox(text)
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

        self.error = QLabel()
        self.error.setObjectName("hint")
        self.error.setWordWrap(True)
        form.addRow("", self.error)

        for edit in (self.start_edit, self.end_edit):
            edit.timeChanged.connect(self.validate)
        self.validate_hook = None
        self.validate()

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
        self.duration.setText(f"{minutes // 60}:{minutes % 60:02d} h" if ok else "")
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
        }


class EntryDialog(QDialog):
    """Tätigkeit nachtragen oder ändern."""

    def __init__(self, start, end, customers, categories, customer="", category="", text="",
                 tv_id=None, title="Tätigkeit nachtragen", info="", can_delete=False, parent=None,
                 trace=None, rule_subject=None):
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
                               tv_id, self, trace=trace, rule_subject=rule_subject)
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
                 customer=None, category=None, trace=None, rule_subject=None):
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
            trace=trace, rule_subject=rule_subject)
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
