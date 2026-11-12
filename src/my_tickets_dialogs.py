"""Fenster „Meine Tickets“: offene Tickets in Matrix42, bei denen du Bearbeiter bist.

Tabelle (Ticket, Betreff, Kunde, Melder, Status, Angelegt), nach jeder Spalte sortierbar, mit
Filterfeld darüber (jedes Wort muss irgendwo vorkommen, wie bei der Ticketsuche).
Die Liste liest M42Reader alle 10 Minuten (my_tickets_loaded), „Aktualisieren“ liest sofort.
„Neues Ticket …“, „Bearbeiten …“ und „Schließen …“ öffnen die Fenster aus ticket_dialogs.py.
"""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QLineEdit, QPushButton, QVBoxLayout

from ticket_table import COLUMNS, TicketTable


class MyTicketsDialog(QDialog):
    def __init__(self, reader, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Meine Tickets")
        self.setMinimumSize(960, 480)
        self.reader = reader
        self._note = ""  # letzte Meldung (angelegt/geschlossen/kopiert), bleibt beim Neuladen stehen
        self._error = ""
        self._rows = []
        self._at = ""
        layout = QVBoxLayout(self)
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("Filtern nach Ticket, Betreff, Kunde, Melder oder Status")
        self.filter_edit.setAccessibleName("Tickets filtern")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self.apply_filter)
        self.filter_edit.installEventFilter(self)
        layout.addWidget(self.filter_edit)

        self.table = TicketTable("Meine offenen Tickets", self)
        self.table.setAccessibleDescription("Enter oder Doppelklick kopiert die Ticketnummer.")
        self.table.sort_by(len(COLUMNS) - 1, Qt.DescendingOrder)  # neueste zuerst
        self.table.activated.connect(lambda _row: self.copy_number())
        self.table.itemSelectionChanged.connect(self._selected)
        layout.addWidget(self.table, 1)

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.status.setObjectName("hint")
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.button(QDialogButtonBox.Close).setText("Fertig")
        self.copy_button = QPushButton("Nummer &kopieren", self)
        self.copy_button.clicked.connect(self.copy_number)
        self.refresh_button = QPushButton("&Aktualisieren", self)
        self.refresh_button.clicked.connect(self.refresh)
        self.new_button = QPushButton("&Neues Ticket …", self)
        self.new_button.clicked.connect(self.new_ticket)
        self.edit_button = QPushButton("&Bearbeiten …", self)
        self.edit_button.setToolTip("Betreff des markierten Tickets ändern oder die Beschreibung ergänzen")
        self.edit_button.clicked.connect(self.edit_ticket)
        self.close_button = QPushButton("&Schließen …", self)
        self.close_button.setToolTip("Markiertes Ticket mit Lösungstext schließen")
        self.close_button.clicked.connect(self.close_ticket)
        for button in (self.new_button, self.edit_button, self.close_button, self.copy_button,
                       self.refresh_button):
            button.setAutoDefault(False)
            buttons.addButton(button, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        # Rahmen wie „Tätigkeit nachtragen“: Kopf, Inhalt, Fuß mit „Neues Ticket …“ als Hauptaktion
        from card_dialog import modernize
        modernize(self, "Meine Tickets", "Offene Tickets in Matrix42, bei denen du Bearbeiter bist", "list",
                  intro=False, primary=self.new_button)
        self._selected()
        reader.my_tickets_loaded.connect(self.show_result, Qt.QueuedConnection)
        if reader.my_tickets is None:
            self.refresh()
        else:
            self.show_result(reader.my_tickets)
        self.filter_edit.setFocus()

    def eventFilter(self, obj, event):
        # Pfeil runter im Filterfeld: in die Tabelle
        if obj is self.filter_edit and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Down:
            self.table.setFocus()
            if self.current_row() is None:
                self.table.select_first()
            return True
        return super().eventFilter(obj, event)

    # ---- Daten

    def refresh(self):
        self.refresh_button.setEnabled(False)
        self.status.setText("Lese meine Tickets aus Matrix42 …")
        self.reader.load_my_tickets()

    def show_result(self, result):
        self.refresh_button.setEnabled(True)
        self._at = result.get("at", "")
        self._error = result.get("error", "")
        if result.get("rows") is not None:
            self._fill(result["rows"])
        else:
            self._update_status()

    def _fill(self, rows):
        self._rows = list(rows)
        self.table.set_rows(self._rows)
        self.apply_filter()

    def current_row(self):
        return self.table.current_row()

    def visible_rows(self):
        return self.table.visible_rows()

    def apply_filter(self, *_):
        self.table.apply_filter(self.filter_edit.text())
        self._update_status()

    def _update_status(self):
        n, shown = len(self._rows), len(self.visible_rows())
        text = ""
        if self._at or n:
            text = (f"{n} offene{'s' if n == 1 else ''} Ticket{'s' if n != 1 else ''}, bei denen du Bearbeiter "
                    f"bist (Stand {self._at}).")
            if shown != n:
                text += f" {shown} passen zum Filter."
            text += " Enter kopiert die Nummer."
        if self._error:
            text = (text + "\n" if text else "") + f"⚠ {self._error}"
        self.status.setText("\n".join(t for t in (self._note, text) if t))

    def _selected(self):
        on = self.current_row() is not None
        self.copy_button.setEnabled(on)
        self.edit_button.setEnabled(on)
        self.close_button.setEnabled(on)

    # ---- Aktionen

    def new_ticket(self):
        from ticket_dialogs import NewTicketDialog
        dialog = NewTicketDialog(self.reader, self)
        if dialog.exec() == QDialog.Accepted and dialog.created:
            c = dialog.created
            text = f"{c['ticket']} angelegt" + (" und übernommen" if c.get("taken_over") else "") + \
                ", Nummer kopiert."
            self._note = text + (f"\n⚠ {c['warning']}" if c.get("warning") else "")
            self._update_status()
        dialog.deleteLater()

    def edit_ticket(self):
        from ticket_dialogs import EditTicketDialog
        row = self.current_row()
        if not row:
            return
        dialog = EditTicketDialog(self.reader, row, self)
        if dialog.exec() == QDialog.Accepted and dialog.saved:
            self._note = f"{row['ticket']} gespeichert."
            subject = dialog.saved.get("subject") or row.get("subject", "")
            self._fill([dict(r, subject=subject) if r.get("id") == row.get("id") else r for r in self._rows])
        dialog.deleteLater()

    def close_ticket(self):
        from ticket_dialogs import CloseTicketDialog
        row = self.current_row()
        if not row:
            return
        dialog = CloseTicketDialog(self.reader, row, self)
        if dialog.exec() == QDialog.Accepted and dialog.closed:
            self._note = f"{row['ticket']} geschlossen."
            self._fill([r for r in self._rows if r.get("id") != row.get("id")])
        dialog.deleteLater()

    def copy_number(self):
        row = self.current_row()
        if not row:
            return
        QApplication.clipboard().setText(row["ticket"])
        self._note = f"{row['ticket']} kopiert."
        self._update_status()

    def done(self, result):
        try:
            self.reader.my_tickets_loaded.disconnect(self.show_result)
        except (RuntimeError, TypeError):
            pass
        super().done(result)
