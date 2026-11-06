"""Fenster „Tagesabschluss“: Vorschläge des Tages prüfen, dokumentieren und in Matrix42 buchen.

Die Vorschläge kommen aus day_close.py. Du prüfst die Liste, änderst bei Bedarf Kunde, Ticket
oder Text direkt in der Tabelle und bestätigst einmal für alle angehakten Zeilen:
- **Nur dokumentieren**: Entwürfe werden eigene Tätigkeiten (Zeile „Doku“, Ansicht
  Dokumentation, Kopieren fürs Ticket).
- **Dokumentieren und buchen**: zusätzlich legt Zeitzeuge je Zeile mit Ticket eine
  Zeiterfassung (Status „Neu“) in Matrix42 an, nacheinander über M42Reader.book. Freigeben
  bleibt in Matrix42. Zeilen ohne Ticket werden nur dokumentiert.
- **Einzeln buchen …** öffnet für die markierte Zeile das bekannte Fenster „In Matrix42
  buchen“ mit Ticketsuche.
Zeitzeuge bucht nie von selbst: erst der Klick auf einen der Knöpfe speichert oder bucht.
"""
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
                               QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QToolButton, QVBoxLayout)

import day_close as dc
import m42_booking as mb
import prompt_topics
from theme import GERMAN, fit_bold, prose

DAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
COL_CHECK, COL_TIME, COL_DURATION, COL_CUSTOMER, COL_TICKET, COL_TEXT, COL_NOTE = range(7)
COLUMNS = ["", "Zeit", "Dauer", "Kunde", "Ticket", "Tickettext", "Hinweis"]
EDITABLE = {COL_CUSTOMER: "customer", COL_TICKET: "ticket", COL_TEXT: "text"}
KIND_NAMES = {dc.KIND_DOC: "deine Tätigkeit", dc.KIND_DRAFT: "Vorschlag", dc.KIND_GAP: "nicht zugeordnet"}
RETRY_MS = 1500   # Matrix42 bucht gerade (z. B. ein anderes Fenster): so lange warten …
RETRIES = 20      # … und so oft versuchen


def _minutes(row):
    return int((dc._t(row["end"]) - dc._t(row["start"])).total_seconds() // 60)


class DayCloseDialog(QDialog):
    """Vorschläge eines Tages. window: Hauptfenster (day_close_plan, journal, m42_reader …)."""

    def __init__(self, window, date_str, parent=None):
        super().__init__(parent)
        self.window = window
        self.date_str = date_str
        self.rows = []
        self.plan = {}
        self.queue = []      # [(Zeile, Tätigkeit, Anfrage)] noch zu buchen
        self.current = None  # (Zeile, Tätigkeit, Anfrage) wird gerade gebucht
        self.retries = 0
        self.results = {"booked": 0, "documented": 0, "failed": 0, "no_ticket": 0, "skipped": 0}
        self._filling = False
        self.setWindowTitle("Tagesabschluss")
        self.setMinimumSize(900, 480)
        layout = QVBoxLayout(self)

        head = QHBoxLayout()
        self.prev_button = QToolButton(self)
        self.prev_button.setText("◀")
        self.prev_button.setAccessibleName("Tag zurück")
        self.prev_button.setToolTip("Tag zurück (Bild auf)")
        self.prev_button.clicked.connect(lambda: self.move_day(-1))
        self.next_button = QToolButton(self)
        self.next_button.setText("▶")
        self.next_button.setAccessibleName("Tag vor")
        self.next_button.setToolTip("Tag vor (Bild ab)")
        self.next_button.clicked.connect(lambda: self.move_day(1))
        self.title = QLabel(self)
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        head.addWidget(self.prev_button)
        head.addWidget(self.title, 1)
        head.addWidget(self.next_button)
        layout.addLayout(head)
        QShortcut(QKeySequence(Qt.Key_PageUp), self, activated=lambda: self.move_day(-1))
        QShortcut(QKeySequence(Qt.Key_PageDown), self, activated=lambda: self.move_day(1))

        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        intro = QLabel("Zeitzeuge hat den Tag aus Verbindungen, Telefonaten, KI-Vorschlägen, Regeln und "
                       "PC-Aktivität zu Blöcken je Kunde zusammengestellt. Prüfe die angehakten Zeilen, "
                       "ändere Kunde, Ticket oder Text per Doppelklick und bestätige unten einmal für alle. "
                       "Gebucht wird mit Status „Neu“, freigeben kannst du danach in Matrix42.", self)
        intro.setWordWrap(True)
        intro.setObjectName("hint")
        prose(intro)
        layout.addWidget(intro)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setAccessibleName("Vorschläge des Tages")
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                   | QAbstractItemView.AnyKeyPressed)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for col in (COL_CHECK, COL_TIME, COL_DURATION, COL_TICKET):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_CUSTOMER, QHeaderView.Interactive)
        header.setSectionResizeMode(COL_TEXT, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_NOTE, QHeaderView.Interactive)
        self.table.setColumnWidth(COL_CUSTOMER, 160)
        self.table.setColumnWidth(COL_NOTE, 220)
        self.table.itemChanged.connect(self.on_item_changed)
        self.table.currentCellChanged.connect(lambda *_: self.update_buttons())
        layout.addWidget(self.table, 1)

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.status.setObjectName("hint")
        layout.addWidget(self.status)

        tools = QHBoxLayout()
        self.all_button = QPushButton("&Alle mit Kunde anhaken", self)
        self.all_button.setAutoDefault(False)
        self.all_button.clicked.connect(self.check_all)
        self.single_button = QPushButton("&Einzeln buchen …", self)
        self.single_button.setAutoDefault(False)
        self.single_button.setToolTip("Markierte Zeile im Fenster „In Matrix42 buchen“ prüfen, "
                                      "mit Ticketsuche")
        self.single_button.clicked.connect(self.book_single)
        self.measure_button = QPushButton("Erkennung &messen …", self)
        self.measure_button.setAutoDefault(False)
        self.measure_button.setToolTip("Wie gut hätte der Tagesabschluss die letzten 20 Tage erkannt? "
                                       "Vergleich mit deinen echten Matrix42-Buchungen")
        self.measure_button.clicked.connect(self.measure)
        tools.addWidget(self.all_button)
        tools.addWidget(self.single_button)
        tools.addStretch(1)
        tools.addWidget(self.measure_button)
        layout.addLayout(tools)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        self.buttons.button(QDialogButtonBox.Close).setText("Schließen")
        self.doc_button = QPushButton("Nur &dokumentieren", self)
        self.doc_button.setAutoDefault(False)
        self.doc_button.setToolTip("Angehakte Vorschläge als Tätigkeiten speichern, nichts buchen")
        self.doc_button.clicked.connect(lambda: self.run(book=False))
        self.book_button = QPushButton("Dokumentieren und &buchen", self)
        self.book_button.setDefault(True)
        self.book_button.setToolTip("Angehakte Zeilen speichern und alle mit Ticket in Matrix42 buchen")
        self.book_button.clicked.connect(lambda: self.run(book=True))
        fit_bold(self.book_button)
        self.buttons.addButton(self.doc_button, QDialogButtonBox.ActionRole)
        self.buttons.addButton(self.book_button, QDialogButtonBox.ActionRole)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.lookups = set()  # Tickets, deren Kunde gerade in Matrix42 nachgeschlagen wird
        reader = self.reader()
        if reader is not None:
            # Methoden (keine Lambdas): Qt trennt sie, sobald das Fenster gelöscht ist
            reader.booking_done.connect(self.on_booked, Qt.QueuedConnection)
            if hasattr(reader, "tickets_found"):
                reader.tickets_found.connect(self.on_ticket_customer, Qt.QueuedConnection)
        self.fill()

    # ---- Daten

    def reader(self):
        return getattr(self.window, "m42_reader", None)

    def move_day(self, step):
        if self.busy():
            return
        day = datetime.strptime(self.date_str, "%Y-%m-%d") + timedelta(days=step)
        if day.date() > datetime.now().date():
            return
        self.date_str = day.strftime("%Y-%m-%d")
        self.status.setText("")
        self.fill()

    def fill(self):
        day = datetime.strptime(self.date_str, "%Y-%m-%d")
        self.title.setText(f"Tagesabschluss · {DAY_NAMES[day.weekday()]}, {day:%d.%m.%Y}")
        self.next_button.setEnabled(day.date() < datetime.now().date())
        try:
            self.plan = self.window.day_close_plan(self.date_str)
        except Exception as e:  # Anzeige darf nie das Hauptfenster mitreißen
            import safe_io
            safe_io.report(f"Tagesabschluss: Vorschläge gingen nicht ({type(e).__name__})")
            self.plan = {"rows": [], "work": 0, "booked": 0, "percent_now": None, "percent_after": None}
            self.status.setText("⚠ Fehler: Die Vorschläge konnten nicht erstellt werden (Details in fehler.log).")
        self.rows = self.plan["rows"]
        self._filling = True
        self.table.setRowCount(len(self.rows))
        for i, row in enumerate(self.rows):
            self._set_row(i, row)
        self._filling = False
        self.lookup_customers()
        if not self.rows and not self.status.text():
            self.status.setText("Für diesen Tag gibt es nichts mehr zu dokumentieren oder zu buchen.")
        self.update_summary()
        self.update_buttons()

    def _set_row(self, i, row):
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        check.setCheckState(Qt.Checked if row.get("checked") else Qt.Unchecked)
        check.setData(Qt.AccessibleTextRole, "angehakt" if row.get("checked") else "nicht angehakt")
        self.table.setItem(i, COL_CHECK, check)
        fixed = {COL_TIME: f"{row['start'][11:16]}–{row['end'][11:16]}",
                 COL_DURATION: dc.hm(_minutes(row)), COL_NOTE: self.note(row)}
        for col, text in fixed.items():
            item = QTableWidgetItem(text)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setToolTip(text if col != COL_NOTE else self.tooltip(row))
            self.table.setItem(i, col, item)
        for col, key in EDITABLE.items():
            item = QTableWidgetItem(row.get(key, ""))
            item.setToolTip(row.get(key, "") or "Doppelklick zum Eintragen")
            if row.get("result_ok"):
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # gebucht: nicht mehr ändern
            self.table.setItem(i, col, item)

    @staticmethod
    def note(row):
        if row.get("result"):
            return row["result"]
        # Was zu tun ist zuerst, dann woher es kommt
        parts = [row.get("note", ""), KIND_NAMES.get(row["kind"], "")]
        if row["kind"] == dc.KIND_DRAFT:
            parts.append(f"Sicherheit {row['confidence']}")
        return " · ".join(p for p in parts if p)

    @staticmethod
    def tooltip(row):
        lines = [DayCloseDialog.note(row)]
        if row.get("sources"):
            lines.append("Aus: " + ", ".join(row["sources"]))
        if row.get("customer_source"):
            lines.append(f"Kunde {row['customer_source']}")
        if row.get("ticket_source"):
            lines.append(f"Ticket aus: {row['ticket_source']}")
        if row.get("category"):
            lines.append(f"Kategorie: {row['category']}")
        return "\n".join(lines)

    def update_summary(self):
        plan = dc.summarize(self.date_str, self._work_spans(), self.rows, self._bookings(), self._docs())
        self.plan.update({k: v for k, v in plan.items() if k != "rows"})
        if not plan["work"]:
            self.summary.setText("Keine Personalzeit an diesem Tag – Vorschläge nur aus den Spuren.")
            return
        now_text = f"{dc.hm(plan['booked'])} ({plan['percent_now']} %)"
        self.summary.setText(
            f"Personalzeit {dc.hm(plan['work'])} · in Matrix42 gebucht {now_text} · "
            f"mit den angehakten Zeilen <b>{dc.hm(plan['proposed'])} ({plan['percent_after']} %)</b>")

    def _work_spans(self):
        import week_dialogs
        return week_dialogs.day_inputs(self.window, self.date_str, datetime.now())["spans"]

    def _bookings(self):
        getter = getattr(self.window, "_m42_bookings", None)
        return (getter(self.date_str) if getter else None) or []

    def _docs(self):
        return [i for i in self.window.journal.items(self.date_str) if not i.get("von_pc")]

    def busy(self):
        return bool(self.queue or self.current)

    def update_buttons(self):
        busy = self.busy()
        checked = any(r.get("checked") for r in self.rows)
        self.doc_button.setEnabled(checked and not busy)
        self.book_button.setEnabled(checked and not busy and self.reader() is not None)
        self.book_button.setToolTip(
            "Angehakte Zeilen speichern und alle mit Ticket in Matrix42 buchen" if self.reader() is not None
            else "Matrix42 ist nicht eingeschaltet (Einstellungen → Datenquellen)")
        self.single_button.setEnabled(not busy and 0 <= self.table.currentRow() < len(self.rows))
        self.all_button.setEnabled(not busy)
        self.prev_button.setEnabled(not busy)

    # ---- Kunde zu einem neuen Ticket: Matrix42 weiß, wem es gehört

    def lookup_customers(self):
        reader = self.reader()
        if reader is None or not hasattr(reader, "search_tickets"):
            return
        for row in self.rows:
            ticket = mb.normalize_ticket(row.get("ticket", ""))
            if row["kind"] == dc.KIND_DRAFT and ticket and not row.get("customer") and ticket not in self.lookups:
                self.lookups.add(ticket)
                reader.search_tickets(ticket, mb.ids(self.window.config).get("ticket_list"))

    def on_ticket_customer(self, result):
        ticket = (result.get("text") or "").upper()
        if ticket not in self.lookups:
            return  # Suche aus einem anderen Fenster
        self.lookups.discard(ticket)
        hit = next((r for r in result.get("rows") or [] if r.get("ticket") == ticket and r.get("customer")), None)
        if not hit:
            return
        changed = False
        for row in self.rows:
            if mb.normalize_ticket(row.get("ticket", "")) == ticket and not row.get("customer") \
                    and not row.get("result_ok"):
                row.update(customer=hit["customer"], customer_source="aus Matrix42 (Ticket)", checked=True,
                           note="" if row.get("note") == "Kunde fehlt" else row.get("note", ""))
                if row.get("confidence") == "niedrig":
                    row["confidence"] = "mittel"
                changed = True
        if changed:
            self.refresh_rows()
            self.update_buttons()

    # ---- Erkennung messen (day_close_eval.py)

    def measure(self):
        import day_close_eval as ev
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication
        if not hasattr(self.window, "day_close_quality"):
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        try:
            quality = self.window.day_close_quality(20)
        finally:
            QApplication.restoreOverrideCursor()
        total = quality["total"]
        _level, text = ev.verdict(total)
        lines = [text, "", ev.summary_text(total), ""]
        for date_str, r in quality["days"][:10]:
            lines.append(f"{date_str[8:10]}.{date_str[5:7]}.: Erkennungsgrad "
                         f"{'–' if r['recognized'] is None else str(r['recognized']) + ' %'}, "
                         f"gebucht {dc.hm(r['truth_minutes'])}")
        lines += ["", "So gemessen: Für jeden der letzten 20 Tage mit Matrix42-Buchungen rechnet Zeitzeuge die "
                  "Vorschläge, als wäre nichts eingetragen und nichts gebucht, und vergleicht Minute für Minute "
                  "mit deinen echten Buchungen."]
        self.quality_text = "\n".join(lines)
        QMessageBox.information(self, "Erkennung des Tagesabschlusses", self.quality_text)

    # ---- Bearbeiten in der Tabelle

    def on_item_changed(self, item):
        if self._filling or not 0 <= item.row() < len(self.rows):
            return
        row = self.rows[item.row()]
        if item.column() == COL_CHECK:
            row["checked"] = item.checkState() == Qt.Checked
            item.setData(Qt.AccessibleTextRole, "angehakt" if row["checked"] else "nicht angehakt")
        elif item.column() in EDITABLE:
            key = EDITABLE[item.column()]
            value = item.text().strip()
            if key == "ticket" and value:
                value = mb.normalize_ticket(value) or value
            row[key] = value
            row["edited"] = True
            if key == "ticket":  # von Hand eingetragen oder geändert: gilt als bestätigt
                row["ticket_guessed"] = False
                row["ticket_source"] = "von Hand" if value else ""
                if row.get("note", "").startswith("Ticket"):
                    row["note"] = "" if value else "Ticket fehlt – wird nur dokumentiert"
            if key in ("customer", "ticket", "text") and value and row["kind"] != dc.KIND_DOC:
                row["checked"] = bool(row.get("customer"))
            self._filling = True
            if key == "ticket" and value != item.text():
                item.setText(value)
            self.table.item(item.row(), COL_CHECK).setCheckState(Qt.Checked if row["checked"] else Qt.Unchecked)
            self._filling = False
        self.update_summary()
        self.update_buttons()

    def check_all(self):
        self._filling = True
        for i, row in enumerate(self.rows):
            if row.get("result_ok"):
                continue
            row["checked"] = bool(row.get("customer"))
            self.table.item(i, COL_CHECK).setCheckState(Qt.Checked if row["checked"] else Qt.Unchecked)
        self._filling = False
        self.update_summary()
        self.update_buttons()

    # ---- Speichern und Buchen

    def _document(self, row):
        """Zeile als Tätigkeit sichern (Entwurf: neu, eigene Tätigkeit: Änderungen übernehmen).
        -> Tätigkeit oder None bei Fehler."""
        journal = self.window.journal
        try:
            if row["kind"] == dc.KIND_DOC:
                old = row["doc_item"]
                changes = {k: row.get(k, "") for k in ("customer", "ticket", "text")
                           if row.get(k, "") != old.get(k, "")}
                if not changes:
                    return old
                row["doc_item"] = journal.update(old, changes)
                return row["doc_item"]
            item = dc.to_item(row)
            # Antwort auf die erkannten Spuren: nicht mehr nachfragen (wie beim Eintragen)
            index = self.window.customer_index() if hasattr(self.window, "customer_index") else None
            item["answered"] = prompt_topics.answer_span(
                {"start": row["start"], "end": row["end"], "customer_name": row.get("customer", "")}, index)
            saved = journal.add(item)
        except (OSError, ValueError) as e:
            row["result"] = f"⚠ nicht gespeichert: {e}"
            self.results["failed"] += 1
            return None
        row.update(kind=dc.KIND_DOC, doc_item=saved)
        self.results["documented"] += 1
        return saved

    def run(self, book):
        if self.busy():
            return
        todo = [r for r in self.rows if r.get("checked") and not r.get("result_ok")]
        if not todo:
            return
        missing = [r for r in todo if not r.get("customer") and not r.get("text")]
        if missing:
            QMessageBox.information(self, "Tagesabschluss", f"{len(missing)} angehakte Zeile(n) ohne Kunde und "
                                    "Text. Bitte ergänzen oder den Haken entfernen.")
            return
        include_guessed = False
        guessed = [r for r in todo if book and r.get("ticket_guessed") and r.get("ticket")]
        if guessed and self.reader() is not None:
            box = QMessageBox(QMessageBox.Question, "Tagesabschluss",
                              f"{len(guessed)} Zeile(n) haben nur ein vermutetes Ticket (zuletzt für den Kunden "
                              "benutzt). Das kann ein altes Ticket sein.\n\nSichere Zeilen werden gebucht. "
                              "Die vermuteten auch?", parent=self)
            safe = box.addButton("Nur &sichere buchen", QMessageBox.AcceptRole)
            also = box.addButton("&Vermutete mitbuchen", QMessageBox.YesRole)
            box.addButton("Abbrechen", QMessageBox.RejectRole)
            box.setDefaultButton(safe)
            box.exec()
            if box.clickedButton() not in (safe, also):
                return
            include_guessed = box.clickedButton() is also
        self.results = {"booked": 0, "documented": 0, "failed": 0, "no_ticket": 0, "skipped": 0}
        saved = [(r, self._document(r)) for r in todo]
        saved = [(r, item) for r, item in saved if item is not None]
        if not book:
            self.finish()
            return
        reader = self.reader()
        if reader is None:
            self.finish()
            return
        bookings = self._bookings()
        plans = []
        for row, item in saved:
            if item.get("m42_entry"):
                continue
            if not mb.normalize_ticket(item.get("ticket", "")):
                row["result"] = "nur dokumentiert – Ticket fehlt (Einzeln buchen …)"
                self.results["no_ticket"] += 1
                continue
            if row.get("ticket_guessed") and not include_guessed:
                row["result"] = "nur dokumentiert – Ticket vermutet, bitte prüfen (Einzeln buchen …)"
                self.results["no_ticket"] += 1
                continue
            plan = mb.plan(item, self.window.billing(), self.window.config.get("ticket_format", ""))
            plans.append((row, item, plan))
        dc.sequence_plans([p for _r, _i, p in plans])
        config = self.window.config
        for row, item, plan in plans:
            if mb.overlaps(bookings, plan["start"], plan["end"]):
                row["result"] = "nicht gebucht – Matrix42 hat zu der Zeit schon etwas (Einzeln buchen …)"
                self.results["skipped"] += 1
                continue
            request = dict(plan, text=plan["text"] or item.get("text", "") or item.get("category", ""),
                           activity_type=config.get("m42_activity_type", mb.DEFAULT_ACTIVITY_TYPE),
                           ids=mb.ids(config), goodwill_reason="Kulanz" if plan.get("goodwill") else "")
            self.queue.append((row, item, request))
        self.refresh_rows()
        self.update_buttons()
        self.next_booking()

    def next_booking(self):
        if self.current or not self.queue:
            if not self.current and not self.queue:
                self.finish()
            return
        row, item, request = self.queue[0]
        reader = self.reader()
        if reader is None:
            self.queue.clear()
            self.finish()
            return
        if not reader.book(request):
            self.retries += 1
            if self.retries > RETRIES:
                for r, _i, _q in self.queue:
                    r["result"] = "⚠ nicht gebucht: Matrix42 ist beschäftigt, bitte später noch einmal"
                    self.results["failed"] += 1
                self.queue.clear()
                self.finish()
                return
            QTimer.singleShot(RETRY_MS, self.next_booking)
            return
        self.retries = 0
        self.queue.pop(0)
        self.current = (row, item, request)
        done = self.results["booked"] + self.results["failed"]
        self.status.setText(f"Bucht in Matrix42 … {done + 1} von {done + 1 + len(self.queue)}: "
                            f"{request['ticket']} {request['start']:%H:%M}–{request['end']:%H:%M}")

    def on_booked(self, result):
        if not self.current or result.get("request") is not self.current[2]:
            return  # Buchung aus einem anderen Fenster
        row, item, request = self.current
        self.current = None
        if result.get("ok"):
            entry = result.get("entry", "")
            booked = dict(item, m42_entry=entry, m42_booked=datetime.now().strftime(dc.TIME_FMT))
            try:
                row["doc_item"] = self.window.journal.update(item, booked)
            except (OSError, ValueError) as e:
                row["result"] = f"gebucht als {entry}, aber nicht vermerkt: {e}"
            else:
                shifted = " (verschoben, damit sich nichts überschneidet)" if request.get("shifted") else ""
                row["result"] = f"✓ gebucht {entry} · {request['start']:%H:%M}–{request['end']:%H:%M}{shifted}"
            row["result_ok"] = True
            row["checked"] = False
            self.results["booked"] += 1
        else:
            error = result.get("error") or "unbekannter Fehler"
            row["result"] = f"⚠ nicht gebucht: {error}"
            if result.get("unclear"):  # abgeschickt, Antwort fehlt: nicht noch einmal mitbuchen
                row["result"] = f"⚠ {error}"
                row["checked"] = False
            self.results["failed"] += 1
            if "anmelden" in error:  # ohne Anmeldung scheitern auch alle weiteren
                for r, _i, _q in self.queue:
                    r["result"] = "⚠ nicht gebucht: bitte zuerst bei Matrix42 anmelden"
                    self.results["failed"] += 1
                self.queue.clear()
        self.refresh_rows()
        self.next_booking()

    def refresh_rows(self):
        self._filling = True
        for i, row in enumerate(self.rows):
            self._set_row(i, row)
        self._filling = False
        self.update_summary()

    def finish(self):
        r = self.results
        parts = []
        if r["documented"]:
            parts.append(f"{r['documented']} dokumentiert")
        if r["booked"]:
            parts.append(f"{r['booked']} in Matrix42 gebucht")
        if r["no_ticket"]:
            parts.append(f"{r['no_ticket']} ohne sicheres Ticket (nur dokumentiert)")
        if r["skipped"]:
            parts.append(f"{r['skipped']} übersprungen (Überschneidung)")
        if r["failed"]:
            parts.append(f"{r['failed']} mit Fehler")
        text = "Fertig: " + ", ".join(parts) + "." if parts else "Nichts geändert."
        self.refresh_rows()
        self.status.setText(text)
        self.update_buttons()
        if getattr(self, "_close_when_done", False):
            QTimer.singleShot(0, super().reject)
        timeline = getattr(self.window, "timeline", None)
        if timeline is not None and hasattr(self.window, "current_date"):
            timeline.draw_timeline(self.window.current_date)
        if hasattr(self.window, "statusBar"):
            self.window.statusBar().showMessage(f"Tagesabschluss {GERMAN.toString(self._qdate(), 'dd.MM.')}: "
                                                f"{text}", 8000)

    def _qdate(self):
        from PySide6.QtCore import QDate
        return QDate.fromString(self.date_str, "yyyy-MM-dd")

    def book_single(self):
        i = self.table.currentRow()
        if self.busy() or not 0 <= i < len(self.rows) or not hasattr(self.window, "book_in_m42"):
            return
        row = self.rows[i]
        if row.get("result_ok"):
            return
        if not row.get("customer") and not row.get("text"):
            self.status.setText("⚠ Bitte zuerst Kunde oder Text eintragen.")
            return
        self.results = {"booked": 0, "documented": 0, "failed": 0, "no_ticket": 0, "skipped": 0}
        item = self._document(row)
        if item is None:
            self.refresh_rows()
            return
        if self.window.book_in_m42(item, parent=self):
            fresh = next((x for x in self.window.journal.items(self.date_str) if x.get("id") == item.get("id")), item)
            row.update(doc_item=fresh, result_ok=True, checked=False,
                       result=f"✓ gebucht {fresh.get('m42_entry', '')}", ticket=fresh.get("ticket", row.get("ticket", "")))
        self.refresh_rows()
        self.update_buttons()

    def reject(self):
        if self.busy():
            if QMessageBox.question(
                    self, "Tagesabschluss", "Zeitzeuge bucht gerade. Abbrechen? Die laufende Buchung "
                    "wird noch fertig und vermerkt, die übrigen nicht mehr.") != QMessageBox.Yes:
                return
            for r, _i, _q in self.queue:
                r["result"] = "abgebrochen – nicht gebucht"
            self.queue.clear()
            if self.current:  # erst schließen, wenn die laufende Buchung an der Tätigkeit steht
                self._close_when_done = True
                self.status.setText("Bucht noch die laufende Zeile zu Ende, dann schließt das Fenster …")
                return
        super().reject()

    def keyPressEvent(self, event):
        # Enter in der Tabelle bearbeitet, statt das Fenster zu schließen
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.table.hasFocus():
            index = self.table.currentIndex()
            if index.isValid() and index.column() in EDITABLE:
                self.table.edit(index)
                return
        super().keyPressEvent(event)
