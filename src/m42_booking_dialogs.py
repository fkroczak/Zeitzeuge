"""Fenster „In Matrix42 buchen“: Buchung einer Tätigkeit prüfen und absenden.

Zeitzeuge bucht nie von selbst. Das Fenster zeigt Ticket, Zeit, Tätigkeitsart und Text
vorbelegt aus der Tätigkeit (m42_booking.plan), du prüfst und klickst „In Matrix42 buchen“.
Die Abfragen schickt M42Reader.book aus dem angemeldeten Edge.
"""
from datetime import datetime

from PySide6.QtCore import QEvent, QObject, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QTimeEdit, QVBoxLayout)

from theme import fit_bold, prose
import m42_booking as mb


def _hm(minutes):
    return f"{minutes // 60}:{minutes % 60:02d} h"


class _TicketSearch:
    """Ticket in Matrix42 suchen: Suche und Trefferliste, gleich in Buchen- und Suchdialog.
    Braucht search_edit, search_button, status, results und reader."""

    def _search_list(self):
        return None  # Ticketliste (Widget-ID) für die Suche, None = Standard

    def search(self):
        text = self.search_edit.text().strip()
        if len(text) < 3:
            self.status.setText("⚠ Bitte mindestens 3 Zeichen zum Suchen eingeben.")
            return
        if self.reader is None:
            self.status.setText("⚠ Matrix42 ist nicht eingeschaltet (Einstellungen → Datenquellen).")
            return
        self.search_button.setEnabled(False)
        self.status.setText(f"Suche „{text}“ in Matrix42 …")
        self.reader.search_tickets(text, self._search_list())

    def _fill_results(self, rows):
        """Treffer zeigen: offene zuerst, erledigte grau; lange Zeilen gekürzt (ganz im Hinweis)."""
        self.results.clear()
        self.results.setTextElideMode(Qt.ElideRight)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        grey = self.results.palette().color(QPalette.Disabled, QPalette.Text)
        for row in rows:
            item = QListWidgetItem(mb.ticket_list_label(row))
            item.setToolTip(mb.ticket_tooltip(row))
            item.setData(Qt.UserRole, row)
            if mb.is_closed(row):
                item.setForeground(grey)
            self.results.addItem(item)


class BookingDialog(_TicketSearch, QDialog):
    """Buchung prüfen und absenden. Nach Erfolg: self.result_entry = "TE…"."""

    def __init__(self, plan, reader=None, overlaps=(), activity_types=None,
                 activity_type=mb.DEFAULT_ACTIVITY_TYPE, ids=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("In Matrix42 buchen")
        self.setMinimumWidth(560)
        self.reader = reader
        self.ids = ids or dict(mb.DEFAULT_IDS)
        self.day = plan["start"].date()
        self.result_entry = ""
        self.ticket_info = None
        layout = QVBoxLayout(self)
        intro = QLabel("Zeitzeuge legt eine Zeiterfassung mit Status „Neu“ am Ticket an. "
                       "Freigeben kannst du sie danach wie gewohnt in Matrix42.")
        intro.setWordWrap(True)
        prose(intro)
        intro.setObjectName("hint")
        layout.addWidget(intro)

        form = QFormLayout()
        self.ticket_edit = QLineEdit(plan.get("ticket", ""))
        self.ticket_edit.setPlaceholderText("Ticketnummer, z. B. TCK0000049374")
        form.addRow("T&icket:", self.ticket_edit)
        self.ticket_hint = QLabel(plan.get("customer", ""))
        self.ticket_hint.setObjectName("hint")
        self.ticket_hint.setWordWrap(True)
        form.addRow("Kunde:", self.ticket_hint)

        # Ticket suchen: Kunde, Benutzer (Melder, Bearbeiter), Ticketnummer oder Titel
        search = QHBoxLayout()
        self.search_edit = QLineEdit(plan.get("customer", "") if not plan.get("ticket") else "")
        self.search_edit.setPlaceholderText("Kunde, Benutzer, Ticketnummer oder Titel")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.returnPressed.connect(self.search)
        self.search_button = QPushButton("Suchen")
        self.search_button.setAutoDefault(False)
        self.search_button.setAccessibleName("Tickets in Matrix42 suchen")
        self.search_button.clicked.connect(self.search)
        search.addWidget(self.search_edit, 1)
        search.addWidget(self.search_button)
        search_label = QLabel("Ticket &suchen:")
        search_label.setBuddy(self.search_edit)
        form.addRow(search_label, search)
        self.results = QListWidget()
        self.results.setAccessibleName("Gefundene Tickets")
        self.results.setMaximumHeight(130)
        self.results.itemActivated.connect(self.take_ticket)
        self.results.itemClicked.connect(self.take_ticket)
        self.results.hide()
        form.addRow("", self.results)
        form.addRow("Datum:", QLabel(f"{plan['start']:%d.%m.%Y}"))

        times = QHBoxLayout()
        self.start_edit = QTimeEdit(QTime(plan["start"].hour, plan["start"].minute))
        self.end_edit = QTimeEdit(QTime(plan["end"].hour, plan["end"].minute))
        for edit, name in ((self.start_edit, "Von"), (self.end_edit, "Bis")):
            edit.setDisplayFormat("HH:mm")
            edit.setAccessibleName(name)
            edit.timeChanged.connect(self.validate)
        bis = QLabel("&bis")
        bis.setBuddy(self.end_edit)
        self.duration = QLabel()
        self.duration.setObjectName("hint")
        times.addWidget(self.start_edit)
        times.addWidget(bis)
        times.addWidget(self.end_edit)
        times.addWidget(self.duration, 1)
        von = QLabel("&Von:")
        von.setBuddy(self.start_edit)
        form.addRow(von, times)

        self.type_edit = QComboBox()
        self.type_edit.setAccessibleName("Tätigkeitsart")
        self.set_activity_types(activity_types or mb.ACTIVITY_TYPES, activity_type)
        form.addRow("Tätigkeits&art:", self.type_edit)

        # Kulanz und Reise wie im Matrix42-Dialog, vorbelegt aus der Tätigkeit
        flags = QHBoxLayout()
        self.goodwill_box = QCheckBox("K&ulanz")
        self.goodwill_box.setChecked(bool(plan.get("goodwill")))
        self.goodwill_box.setToolTip("Die Zeit wird als Kulanz gebucht (nicht berechnet).")
        self.travel_box = QCheckBox("&Reise")
        self.travel_box.setChecked(bool(plan.get("travel")))
        self.travel_box.setToolTip("Die Zeit wird als Reise (Anfahrt) gebucht.")
        self.surcharge_box = QCheckBox("&Zuschlag ignorieren")
        self.surcharge_box.setChecked(bool(plan.get("no_surcharge")))
        self.surcharge_box.setToolTip("Zuschläge (z. B. außerhalb der Servicezeit) nicht berechnen.")
        flags.addWidget(self.goodwill_box)
        flags.addWidget(self.travel_box)
        flags.addWidget(self.surcharge_box)
        flags.addStretch(1)
        form.addRow("", flags)
        self.goodwill_reason = QLineEdit("Kulanz" if plan.get("goodwill") else "")
        self.goodwill_reason.setPlaceholderText("Grund für die Kulanz")
        self.goodwill_reason.setAccessibleName("Kulanzgrund")
        self.goodwill_label = QLabel("Kulanz&grund:")
        self.goodwill_label.setBuddy(self.goodwill_reason)
        form.addRow(self.goodwill_label, self.goodwill_reason)
        self.goodwill_box.toggled.connect(self._goodwill_toggled)
        self._goodwill_toggled(self.goodwill_box.isChecked())
        self.surcharge_reason = QLineEdit(mb.SURCHARGE_REASON if plan.get("no_surcharge") else "")
        self.surcharge_reason.setPlaceholderText("Grund, warum kein Zuschlag berechnet wird")
        self.surcharge_reason.setAccessibleName("Grund für Zuschlag ignorieren")
        self.surcharge_label = QLabel("Zuschlagsgrun&d:")
        self.surcharge_label.setBuddy(self.surcharge_reason)
        form.addRow(self.surcharge_label, self.surcharge_reason)
        self.surcharge_box.toggled.connect(self._surcharge_toggled)
        self._surcharge_toggled(self.surcharge_box.isChecked())

        self.text_edit = QPlainTextEdit(plan.get("text", ""))
        self.text_edit.setTabChangesFocus(True)
        self.text_edit.setFixedHeight(90)
        form.addRow("&Beschreibung:", self.text_edit)
        layout.addLayout(form)

        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setObjectName("hint")
        layout.addWidget(self.warning)
        self.set_overlaps(overlaps)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("hint")
        layout.addWidget(self.status)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.book_button = self.buttons.button(QDialogButtonBox.Ok)
        self.book_button.setText("In Matrix42 &buchen")
        fit_bold(self.book_button)
        self.buttons.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        self.buttons.accepted.connect(self.book)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.ticket_edit.textChanged.connect(self.validate)
        if reader is not None:
            reader.booking_done.connect(self.on_booked, Qt.QueuedConnection)
            reader.tickets_found.connect(self.on_tickets, Qt.QueuedConnection)
            # Methoden (keine Lambdas): Qt trennt sie, sobald das Fenster gelöscht ist
            reader.activity_types_loaded.connect(self.on_activity_types, Qt.QueuedConnection)
        self.validate()
        self.text_edit.setFocus()
        if reader is not None and self.search_edit.text().strip():
            self.search()  # ohne Ticket: gleich nach dem Kunden suchen

    # ---- Anzeige

    def set_activity_types(self, types, current=None):
        self.type_edit.clear()
        for value, name in types:
            self.type_edit.addItem(name, value)
        index = self.type_edit.findData(current)
        self.type_edit.setCurrentIndex(max(index, 0))

    def _goodwill_toggled(self, on):
        self.goodwill_reason.setVisible(on)
        self.goodwill_label.setVisible(on)
        if on and not self.goodwill_reason.text().strip():
            self.goodwill_reason.setText("Kulanz")

    def _surcharge_toggled(self, on):
        self.surcharge_reason.setVisible(on)
        self.surcharge_label.setVisible(on)
        if on and not self.surcharge_reason.text().strip():
            self.surcharge_reason.setText(mb.SURCHARGE_REASON)

    def on_activity_types(self, types):
        self.set_activity_types(types, self.type_edit.currentData())

    def set_overlaps(self, bookings):
        if not bookings:
            self.warning.setText("")
            self.warning.setVisible(False)
            return
        lines = [f"{b['start'][11:16]}–{b['end'][11:16]} {b.get('ticket', '')} {b.get('subject', '')}".strip()
                 for b in bookings[:3]]
        self.warning.setText("⚠ In Matrix42 ist zu dieser Zeit schon gebucht:\n" + "\n".join(lines))
        self.warning.setVisible(True)

    def times(self):
        start = datetime.combine(self.day, self.start_edit.time().toPython().replace(second=0))
        end = datetime.combine(self.day, self.end_edit.time().toPython().replace(second=0))
        return start, end

    def validate(self, *_):
        start, end = self.times()
        ticket = mb.normalize_ticket(self.ticket_edit.text())
        minutes = int((end - start).total_seconds() // 60)
        self.duration.setText(_hm(minutes) if minutes > 0 else "")
        problem = ("⚠ Fehler: „Bis“ muss nach „Von“ liegen." if minutes <= 0 else
                   "⚠ Bitte eine Ticketnummer (TCK…) angeben." if not ticket else "")
        if not (self.reader is not None and self.reader.booking):
            self.status.setText(problem)
        self.book_button.setEnabled(not problem and not (self.reader is not None and self.reader.booking))
        return not problem

    # ---- Ticket suchen

    def _search_list(self):
        return self.ids.get("ticket_list")

    def on_tickets(self, result):
        if result.get("text") != self.search_edit.text().strip():
            return  # ältere Suche
        self.search_button.setEnabled(True)
        self.show_tickets(result.get("rows") or [], result.get("error", ""))

    def show_tickets(self, rows, error=""):
        self._fill_results(rows)
        self.results.setVisible(bool(rows))
        if rows:
            self.status.setText(f"{len(rows)} Ticket{'s' if len(rows) != 1 else ''} gefunden. "
                                "Klick übernimmt das Ticket.")
        else:
            self.status.setText(f"⚠ Kein Ticket gefunden{': ' + error if error else '.'}")

    def take_ticket(self, item):
        row = item.data(Qt.UserRole) or {}
        self.ticket_edit.setText(row.get("ticket", ""))
        self.ticket_hint.setText(" · ".join(t for t in (row.get("customer"), row.get("subject")) if t))
        self.validate()

    # ---- Buchen

    def request(self):
        start, end = self.times()
        return {"ticket": mb.normalize_ticket(self.ticket_edit.text()), "start": start, "end": end,
                "minutes": int((end - start).total_seconds() // 60),
                "text": self.text_edit.toPlainText().strip(),
                "activity_type": self.type_edit.currentData(), "ids": self.ids,
                "goodwill": self.goodwill_box.isChecked(), "travel": self.travel_box.isChecked(),
                "goodwill_reason": self.goodwill_reason.text().strip(),
                "no_surcharge": self.surcharge_box.isChecked(),
                "surcharge_reason": self.surcharge_reason.text().strip()}

    def book(self):
        if not self.validate():
            return
        if self.reader is None:
            self.status.setText("⚠ Matrix42 ist nicht eingeschaltet (Einstellungen → Datenquellen).")
            return
        if not self.reader.book(self.request()):
            self.status.setText("⚠ Zeitzeuge bucht gerade schon. Bitte kurz warten.")
            return
        self.book_button.setEnabled(False)
        self.status.setText("Bucht in Matrix42 …")

    def on_booked(self, result):
        if result.get("ok"):
            self.result_entry = result.get("entry", "")
            self.ticket_info = result.get("ticket")
            self.accept()
            return
        self.validate()  # vor dem Fehlertext: validate() leert sonst die Statuszeile
        if result.get("unclear"):  # nicht ein zweites Mal buchen, erst in Matrix42 nachsehen
            self.book_button.setEnabled(False)
            self.status.setText(f"⚠ Vielleicht gebucht: {result.get('error')}")
            return
        self.status.setText(f"⚠ Nicht gebucht: {result.get('error') or 'unbekannter Fehler'}")


class TicketSearchDialog(_TicketSearch, QDialog):
    """Ticket in Matrix42 suchen, bevor die Tätigkeit dokumentiert oder gebucht wird.
    Nach Auswahl: self.row = {"ticket", "customer", "subject", …}."""

    def __init__(self, reader, text="", ticket_list=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ticket suchen")
        self.setMinimumSize(960, 480)
        self.reader = reader
        self.ticket_list = ticket_list
        self.row = None
        layout = QVBoxLayout(self)
        search = QHBoxLayout()
        self.search_edit = QLineEdit(text)
        self.search_edit.setPlaceholderText("Kunde, Benutzer, Ticketnummer oder Titel")
        self.search_edit.setAccessibleName("Suchtext")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.returnPressed.connect(self.search)
        self.search_button = QPushButton("&Suchen")
        self.search_button.setAutoDefault(False)
        self.search_button.setAccessibleName("Tickets in Matrix42 suchen")
        self.search_button.clicked.connect(self.search)
        search.addWidget(self.search_edit, 1)
        search.addWidget(self.search_button)
        layout.addLayout(search)
        from ticket_table import TicketTable
        self.results = TicketTable("Gefundene Tickets")
        self.results.setAccessibleDescription("Enter oder Doppelklick übernimmt das Ticket.")
        self.results.setMinimumHeight(220)
        self.results.activated.connect(self._take_row)
        layout.addWidget(self.results, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("hint")
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.take_button = buttons.button(QDialogButtonBox.Ok)
        self.take_button.setText("&Übernehmen")
        self.take_button.setEnabled(False)
        buttons.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        buttons.accepted.connect(lambda: self._take_row(self.results.current_row()))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.results.itemSelectionChanged.connect(
            lambda: self.take_button.setEnabled(self.results.current_row() is not None))
        # Rahmen wie „Tätigkeit nachtragen“: Kopf, Inhalt, Fuß mit „Übernehmen“ als Hauptaktion
        from card_dialog import modernize
        modernize(self, "Ticket suchen", "In Matrix42 nach Kunde, Melder, Ticketnummer oder Titel", "search",
                  intro=False, primary=self.take_button)
        if reader is not None:
            reader.tickets_found.connect(self.on_tickets, Qt.QueuedConnection)
        self.search_edit.setFocus()
        # Beim Tippen: Treffer sofort auf den neuen Text eingrenzen, nach einer kurzen Pause
        # in Matrix42 neu suchen (Enter oder „Suchen“ sucht gleich)
        self._rows = []
        self._auto = QTimer(self, singleShot=True, interval=700)
        self._auto.timeout.connect(self._auto_search)
        self.search_edit.textChanged.connect(self._typed)
        self.search_edit.returnPressed.connect(self._auto.stop)
        self.search_button.clicked.connect(self._auto.stop)
        self.search_edit.installEventFilter(self)  # Pfeil runter: in die Treffer
        if reader is not None and len(text.strip()) >= 3:
            self.search()

    def eventFilter(self, obj, event):
        if obj is self.search_edit and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Down \
                and self.results.visible_rows():
            self.results.setFocus()
            if self.results.current_row() is None:
                self.results.select_first()
            return True
        return super().eventFilter(obj, event)

    def _search_list(self):
        return self.ticket_list

    def _typed(self, text):
        rows = mb.merge_tickets_rows(self._rows, text.strip())
        if rows:
            self._show(rows, "")
        else:  # nichts mehr in den alten Treffern: auf die neue Suche warten
            self.results.set_rows([])
            self.status.setText("Enter sucht in Matrix42." if len(text.strip()) >= 3
                                else "Bitte mindestens 3 Zeichen eingeben.")
        if self.reader is not None and len(text.strip()) >= 3:
            self._auto.start()

    def _auto_search(self):
        if self.search_edit.text().strip() != getattr(self, "_searched", None):
            self.search()

    def search(self):
        self._searched = self.search_edit.text().strip()
        super().search()

    def on_tickets(self, result):
        if result.get("text") != self.search_edit.text().strip():
            return  # ältere Suche
        self.search_button.setEnabled(True)
        self._rows = result.get("rows") or []
        self._show(self._rows, result.get("error", ""))

    def _show(self, rows, error):
        self.results.set_rows(rows)
        if rows:
            self.results.select_first()
            open_n = sum(not mb.is_closed(r) for r in rows)
            self.status.setText(f"{len(rows)} Ticket{'s' if len(rows) != 1 else ''} gefunden, "
                                f"{open_n} offen (stehen oben, Klick auf eine Spalte sortiert). "
                                "Doppelklick oder „Übernehmen“ übernimmt das Ticket.")
        else:
            self.status.setText(f"⚠ Kein Ticket gefunden{': ' + error if error else '.'}")

    def _take_row(self, row):
        if not row:
            return
        self.row = row
        self.accept()


class TicketLookup(QObject):
    """Ticketsuche beim Tippen (Feld „Ticket“ im Eintragen-Fenster): immer nur eine Suche
    zugleich; was währenddessen getippt wird, wird danach gesucht. Ergebnis über found."""

    found = Signal(str, list, str)  # Suchtext, Tickets, Fehler

    def __init__(self, reader, ticket_list=None, parent=None):
        super().__init__(parent)
        self.reader = reader
        self.ticket_list = ticket_list
        self._running = None  # Suchtext der laufenden Suche
        self._pending = None
        reader.tickets_found.connect(self._on_result, Qt.QueuedConnection)

    def lookup(self, text):
        text = (text or "").strip()
        if self._running is not None:
            self._pending = text
            return
        self._running = text
        self.reader.search_tickets(text, self.ticket_list)

    def _on_result(self, result):
        if self._running is None or result.get("text") != self._running:
            return  # Suche aus einem anderen Fenster
        self._running = None
        self.found.emit(result["text"], result.get("rows") or [], result.get("error", ""))
        pending, self._pending = self._pending, None
        if pending is not None and pending != result["text"]:
            self.lookup(pending)


def search_ticket(reader, text="", ticket_list=None, parent=None):
    """Suchfenster zeigen. Gewähltes Ticket (dict) oder None."""
    dialog = TicketSearchDialog(reader, text, ticket_list, parent)
    owner = parent.window() if parent is not None else None
    if owner is not None and owner.windowFlags() & Qt.WindowStaysOnTopHint:
        # Aus dem Nachfrage-Fenster (immer im Vordergrund): sonst kann die Suche dahinter
        # landen, und Zeitzeuge wirkt aufgehängt, weil das gesperrte Fenster auf sie wartet
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    # Nur das aufrufende Fenster sperren: Hauptfenster und Infobereich bleiben bedienbar
    dialog.setWindowModality(Qt.WindowModal if owner is not None else Qt.ApplicationModal)
    QTimer.singleShot(0, dialog, lambda: (dialog.raise_(), dialog.activateWindow()))
    row = dialog.row if dialog.exec() == QDialog.Accepted else None
    dialog.deleteLater()  # sonst bliebe es mit tickets_found verbunden
    return row
