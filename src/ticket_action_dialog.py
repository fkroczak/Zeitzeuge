"""Fenster „Kommentieren“, „E-Mail senden“, „Pausieren“ und „Weiterleiten“ für ein Ticket (Matrix42).

Aufbau wie die übrigen Ticketfenster (ticket_dialogs._CardDialog). Zeitzeuge schickt erst, wenn du
den Hauptknopf klickst. Die Abfragen stehen in m42_ticket_actions.py.
"""
from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QTime, Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QTimeEdit, QWidget)

import m42_ticket_actions as ma
import spellcheck
from flow_layout import FlowLayout
import m42_tickets as mt
from ticket_dialogs import _CardDialog, _label, show_contact

# Art -> (Titel, Symbol, Hauptknopf, Platzhalter für den Text)
KINDS = {"comment": ("Kommentieren", "comment", "&Kommentar speichern",
                     "Was ist passiert? z. B. „Mit Kunde telefoniert, Neustart hat geholfen“"),
         "mail": ("E-Mail senden", "mail", "E-Mail &senden", "Text der E-Mail"),
         "pause": ("Ticket pausieren", "pause", "&Pausieren", "Warum ruht das Ticket? z. B. „Warten auf Rückruf“"),
         "forward": ("Ticket weiterleiten", "forward", "&Weiterleiten", "Hinweis für den neuen Bearbeiter (optional)")}
DEFAULT_PAUSE_REASON = 421  # Warten auf Kunde


def quick_pause_times(now=None):
    """Schnellwahl für die Wiedervorlage -> [(Text, datetime)]."""
    now = (now or datetime.now()).replace(second=0, microsecond=0)

    def workday(days, hour=8):
        day = now.date() + timedelta(days=days)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        return datetime(day.year, day.month, day.day, hour, 0)
    monday = now.date() + timedelta(days=7 - now.weekday())
    out = [("in 1 Std.", now + timedelta(hours=1)), ("in 2 Std.", now + timedelta(hours=2))]
    if now.hour < 15:
        out.append(("heute 16:00", now.replace(hour=16, minute=0)))
    return out + [("morgen 8:00", workday(1)), ("übermorgen", workday(2)),
                  ("nächsten Montag", datetime(monday.year, monday.month, monday.day, 8, 0)),
                  ("in 1 Woche", workday(7))]


def default_pause_until(now=None):
    """Nächster Werktag 8:00."""
    day = (now or datetime.now()).date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, 8, 0)


class TicketActionDialog(_CardDialog):
    """kind: "comment", "mail", "pause" oder "forward". row: Zeile der Ticketliste.
    contact: {"email", "initiator_id", "rows"} des Melders (für „E-Mail senden“; rows: Kontaktzeilen wie in
    „Ticket ansehen“, fehlen sie, sucht das Fenster den Melder per Name), dazu "managers": Verwalter des
    Kunden [{role, id, name, email}], die sich per Schalter ins CC nehmen lassen. Danach self.done_text."""

    def __init__(self, reader, row, kind, parent=None, contact=None):
        super().__init__(parent)
        self.row, self.kind = row, kind
        self.contact = contact or {}
        self.done_text = ""
        title, icon, main, placeholder = KINDS[kind]
        self._frame(reader, title, row.get("subject") or row["ticket"], icon, main)
        self._ticket_line(row)
        box = self.body_box
        getattr(self, f"_build_{kind}")()

        self.text_edit = QPlainTextEdit()
        spellcheck.attach(self.text_edit)
        self.text_edit.setPlaceholderText(placeholder)
        self.text_edit.setTabChangesFocus(True)
        self.text_edit.setFixedHeight(200 if kind == "mail" else 110)
        label = {"mail": "&Text", "forward": "&Hinweis"}.get(kind, "&Kommentar")
        self.text_edit.setAccessibleName(label.replace("&", ""))
        self.text_edit.textChanged.connect(self.validate)
        box.addWidget(_label(label, self.text_edit))
        box.addWidget(self.text_edit)
        if kind == "comment":
            self._chips(self.public)
        if kind == "pause":
            self._chips(self.no_escalation)

        self.ok_button.clicked.connect(self.send)
        self.validate()
        (self.to_edit if kind == "mail" and not self.to_edit.text() else
         self.user_edit if kind == "forward" else self.text_edit).setFocus()

    def _chips(self, *checks):
        host = QWidget()
        host.setObjectName("chips")
        chips = FlowLayout(host, spacing=6)
        for check in checks:
            check.setObjectName("chip_check")
            chips.addWidget(check)
        self.body_box.addWidget(host)

    # ---------------------------------------------------------------- Aufbau je Art

    def _build_comment(self):
        self.public = QCheckBox("Ö&ffentlich (Melder sieht den Kommentar)")
        self.public.setChecked(True)  # wie in Matrix42 vorbelegt

    def _build_mail(self):
        # Wer ist der Melder? Karte wie „Kontakt“ in „Ticket ansehen“
        card, self.melder_rows = self._info_card("phone", "Melder")
        rows = self.contact.get("rows") or []
        show_contact(self.melder_rows, rows or [("Name", self.row.get("initiator") or "–", "")])
        self.body_box.addWidget(card)
        if not (rows and self.contact.get("email")) and self.row.get("initiator"):
            self._run("melder", name=self.row["initiator"])
        self.to_edit = QLineEdit(self.contact.get("email", ""))
        self.cc_edit = QLineEdit()
        self.subject_edit = QLineEdit(ma.mail_subject(self.row["ticket"], self.row.get("subject", "")))
        for edit, label, tip in ((self.to_edit, "&An", "E-Mail-Adressen, mehrere mit ; trennen"),
                                 (self.cc_edit, "&CC", "optional, mehrere mit ; trennen"),
                                 (self.subject_edit, "&Betreff", "")):
            edit.setAccessibleName(label.replace("&", ""))
            if tip:
                edit.setPlaceholderText(tip)
            edit.textChanged.connect(self.validate)
            self.body_box.addWidget(_label(label, edit))
            self.body_box.addWidget(edit)
            if edit is self.cc_edit:
                self._manager_chips()
        self._run("mail_info")  # Signatur schon mal holen

    def _manager_chips(self):
        """Verwalter des Kunden mit einem Klick ins CC (nur mit E-Mail und nicht schon Empfänger)."""
        self.cc_checks = []
        own = (self.contact.get("email") or "").casefold()
        people = [p for p in self.contact.get("managers") or []
                  if "@" in (p.get("email") or "") and p["email"].casefold() != own]
        if not people:
            return
        for p in people:
            check = QCheckBox(f"CC: {p.get('name') or p['email']} ({p.get('role') or 'Verwalter'})")
            check.setToolTip(p["email"])
            check.toggled.connect(lambda on, mail=p["email"]: self._toggle_cc(mail, on))
            self.cc_checks.append(check)
        self._chips(*self.cc_checks)

    def _toggle_cc(self, mail, on):
        addresses = [a for a in ma.mail_addresses(self.cc_edit.text()) if a.casefold() != mail.casefold()]
        if on:
            addresses.append(mail)
        self.cc_edit.setText("; ".join(addresses))

    def _build_pause(self):
        until = default_pause_until()
        self.date_edit = QDateEdit(QDate(until.year, until.month, until.day))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("ddd dd.MM.yyyy")
        self.date_edit.setAccessibleName("Wiedervorlage am")
        self.time_edit = QTimeEdit(QTime(until.hour, until.minute))
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setAccessibleName("Wiedervorlage um")
        for edit in (self.date_edit, self.time_edit):
            edit.dateTimeChanged.connect(self.validate)
        line = QHBoxLayout()
        line.addWidget(self.date_edit, 1)
        line.addWidget(self.time_edit)
        self.body_box.addWidget(_label("&Wiedervorlage (Datum und Uhrzeit frei wählbar)", self.date_edit))
        self.body_box.addLayout(line)
        quick_host = QWidget()
        quick_host.setObjectName("chips")
        quick = FlowLayout(quick_host, spacing=6)
        self.quick_buttons = []
        for text, when in quick_pause_times():
            button = QPushButton(text)
            button.setObjectName("chip_button")
            button.setAutoDefault(False)
            button.setToolTip(f"Wiedervorlage {when:%d.%m.%Y %H:%M}")
            button.clicked.connect(lambda _=False, w=when: self.set_until(w))
            quick.addWidget(button)
            self.quick_buttons.append(button)
        self.body_box.addWidget(quick_host)
        self.reason_combo = QComboBox()
        self.reason_combo.setAccessibleName("Grund")
        self._fill_reasons(ma.PAUSE_REASONS)
        self.body_box.addWidget(_label("&Grund", self.reason_combo))
        self.body_box.addWidget(self.reason_combo)
        self.no_escalation = QCheckBox("&Nicht eskalieren, solange pausiert")
        self.no_escalation.setChecked(True)
        self._run("pause_reasons")

    def set_until(self, when):
        self.date_edit.setDate(QDate(when.year, when.month, when.day))
        self.time_edit.setTime(QTime(when.hour, when.minute))

    def _fill_reasons(self, reasons):
        current = self.reason_combo.currentData() or DEFAULT_PAUSE_REASON
        self.reason_combo.clear()
        for value, text in reasons:
            self.reason_combo.addItem(text, value)
        index = self.reason_combo.findData(current)
        self.reason_combo.setCurrentIndex(max(0, index))

    def _build_forward(self):
        self.role_combo = QComboBox()
        self.role_combo.setAccessibleName("Team")
        self.role_combo.addItem("– kein Team –", None)
        self.role_combo.currentIndexChanged.connect(self.validate)
        self.body_box.addWidget(_label("&Team", self.role_combo))
        self.body_box.addWidget(self.role_combo)
        self.user = None
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("Kollegen suchen (optional, wenn ein Team gewählt ist)")
        self.user_edit.setAccessibleName("Person")
        self.user_edit.setClearButtonEnabled(True)
        self.user_edit.textEdited.connect(self._user_typed)
        self.users = QListWidget()
        self.users.setAccessibleName("Gefundene Personen")
        self.users.setMaximumHeight(110)
        self.users.itemActivated.connect(self._take_user)
        self.users.itemClicked.connect(self._take_user)
        self.users.hide()
        self._user_timer = QTimer(self, singleShot=True, interval=400)
        self._user_timer.timeout.connect(self._search_users)
        self.body_box.addWidget(_label("&Person", self.user_edit))
        self.body_box.addWidget(self.user_edit)
        self.body_box.addWidget(self.users)
        self._run("roles")

    # ---------------------------------------------------------------- Weiterleiten: Person suchen

    def _user_typed(self, text):
        self.user = None
        self.validate()
        if len(text.strip()) >= 2:
            self._user_timer.start()
        else:
            self.users.clear()
            self.users.hide()

    def _search_users(self):
        self.status.setText(f"Suche „{self.user_edit.text().strip()}“ …")
        self._run("forward_users", text=self.user_edit.text().strip(), role=self.role_combo.currentData())

    def _on_forward_users(self, result):
        if result["args"].get("text") != self.user_edit.text().strip() or self.user:
            return
        self.users.clear()
        for user in result.get("data") or []:
            item = QListWidgetItem(user["name"])
            item.setData(Qt.UserRole, user)
            self.users.addItem(item)
        self.users.setVisible(self.users.count() > 0)
        if not result.get("ok"):
            self.status.setText(f"⚠ Suchen ging nicht: {result.get('error', '')}")
        elif not self.users.count():
            self.status.setText("⚠ Niemanden gefunden.")
        else:
            self.status.setText("Person anklicken oder mit Pfeil runter und Enter wählen.")
            self.users.setCurrentRow(0)

    def _take_user(self, item):
        if item is None:
            return
        self.user = item.data(Qt.UserRole)
        self.user_edit.setText(self.user["name"])
        self.users.hide()
        self.status.clear()
        self.validate()
        self.text_edit.setFocus()

    def keyPressEvent(self, event):
        if (self.kind == "forward" and self.user_edit.hasFocus() and event.key() == Qt.Key_Down
                and self.users.isVisible()):
            self.users.setFocus()
            return
        super().keyPressEvent(event)

    # ---------------------------------------------------------------- Antworten beim Öffnen

    def _on_roles(self, result):
        if not result.get("ok"):
            self.status.setText(f"⚠ Teams nicht gelesen: {result.get('error', '')}")
            return
        for role in result.get("data") or []:
            self.role_combo.addItem(role["name"], role["id"])

    def _on_pause_reasons(self, result):
        if result.get("ok") and result.get("data"):
            self._fill_reasons(result["data"])

    def _on_melder(self, result):
        """Melder per Name gefunden: Kontakt zeigen und „An“ vorbelegen, wenn noch leer."""
        data = (result.get("data") or {}) if result.get("ok") else {}
        if not data.get("user"):  # nicht gefunden oder nicht eindeutig: lieber nichts Falsches zeigen
            return
        rows = mt.contact_rows(data.get("details"), self.row.get("initiator", ""))
        mail = show_contact(self.melder_rows, rows)
        if mail and not self.contact.get("email"):
            self.contact = dict(self.contact, email=mail, initiator_id=(data["user"] or {}).get("id", ""))
            if not self.to_edit.text().strip():
                self.to_edit.setText(mail)

    def _on_mail_info(self, result):
        if result.get("ok") and not (result.get("data") or {}).get("signature"):
            self.status.setText("Hinweis: keine E-Mail-Signatur in Matrix42 gefunden, die E-Mail geht ohne.")

    # ---------------------------------------------------------------- Prüfen und Senden

    def until(self):
        d, t = self.date_edit.date(), self.time_edit.time()
        return datetime(d.year(), d.month(), d.day(), t.hour(), t.minute())

    def validate(self, *_):
        text = self.text_edit.toPlainText().strip() if hasattr(self, "text_edit") else ""
        ok = not self._busy
        if self.kind == "comment":
            ok = ok and bool(text)
        elif self.kind == "mail":
            ok = ok and bool(text) and bool(ma.mail_addresses(self.to_edit.text())) and \
                bool(self.subject_edit.text().strip())
        elif self.kind == "pause":
            ok = ok and bool(text) and self.until() > datetime.now()
        elif self.kind == "forward":
            ok = ok and bool(self.user or self.role_combo.currentData())
        self.ok_button.setEnabled(ok)
        return ok

    def request(self):
        row = self.row
        req = {"id": row["id"], "type": row.get("type", ""), "ticket": row["ticket"],
               "text": self.text_edit.toPlainText()}
        if self.kind == "comment":
            req["public"] = self.public.isChecked()
        elif self.kind == "mail":
            known = {self.contact["email"]: self.contact["initiator_id"]} \
                if self.contact.get("email") and self.contact.get("initiator_id") else {}
            for p in self.contact.get("managers") or []:  # Verwalter im CC: als Benutzer bekannt
                if p.get("email") and p.get("id") and p["email"].casefold() not in {k.casefold() for k in known}:
                    known[p["email"]] = p["id"]
            req.update(to=self.to_edit.text(), cc=self.cc_edit.text(), subject=self.subject_edit.text(),
                       known_users=known)
        elif self.kind == "pause":
            req.update(until=self.until().isoformat(), reason=self.reason_combo.currentData(),
                       no_escalation=self.no_escalation.isChecked())
        elif self.kind == "forward":
            req.update(user=(self.user or {}).get("id"), role=self.role_combo.currentData())
        return req

    def send(self):
        if self.validate():
            text = {"comment": "Speichere Kommentar", "mail": "Sende E-Mail", "pause": "Pausiere",
                    "forward": "Leite weiter"}[self.kind]
            self._start(self.kind, f"{text} ({self.row['ticket']}) …", request=self.request())

    def _finished(self, result):
        what = {"comment": "Kommentieren", "mail": "E-Mail senden", "pause": "Pausieren",
                "forward": "Weiterleiten"}[self.kind]
        if not result.get("ok"):
            self._failed(result, what)
            return
        self.done_text = {"comment": "Kommentar gespeichert.", "mail": "E-Mail gesendet.",
                          "pause": f"Pausiert bis {self.until():%d.%m. %H:%M}." if self.kind == "pause" else "",
                          "forward": "Weitergeleitet."}[self.kind]
        self.accept()

    _on_comment = _on_mail = _on_pause = _on_forward = _finished

