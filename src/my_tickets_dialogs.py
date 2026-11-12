"""Fenster „Meine Tickets“: offene Tickets in Matrix42, bei denen du Bearbeiter bist.

Die Liste liest M42Reader alle 10 Minuten (my_tickets_loaded), „Aktualisieren“ liest sofort.
„Neues Ticket …“ und „Schließen …“ öffnen die Fenster aus ticket_dialogs.py.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

import m42_booking as mb


class MyTicketsDialog(QDialog):
    def __init__(self, reader, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Meine Tickets")
        self.setMinimumSize(560, 360)
        self.reader = reader
        self._note = ""  # letzte Meldung (angelegt/geschlossen), bleibt beim Neuladen stehen
        layout = QVBoxLayout(self)
        self.results = QListWidget(self)
        self.results.setAccessibleName("Meine offenen Tickets")
        self.results.setTextElideMode(Qt.ElideRight)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.itemActivated.connect(self.copy_number)
        layout.addWidget(self.results, 1)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.status.setObjectName("hint")
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.button(QDialogButtonBox.Close).setText("Fertig")
        self.copy_button = QPushButton("Nummer &kopieren", self)
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(lambda: self.copy_number(self.results.currentItem()))
        self.refresh_button = QPushButton("&Aktualisieren", self)
        self.refresh_button.clicked.connect(self.refresh)
        self.new_button = QPushButton("&Neues Ticket …", self)
        self.new_button.clicked.connect(self.new_ticket)
        self.close_button = QPushButton("&Schließen …", self)
        self.close_button.setToolTip("Markiertes Ticket mit Lösungstext schließen")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(lambda: self.close_ticket(self.results.currentItem()))
        for button in (self.new_button, self.close_button, self.copy_button, self.refresh_button):
            button.setAutoDefault(False)
            buttons.addButton(button, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.results.currentItemChanged.connect(self._selected)
        reader.my_tickets_loaded.connect(self.show_result, Qt.QueuedConnection)
        if reader.my_tickets is None:
            self.refresh()
        else:
            self.show_result(reader.my_tickets)

    def refresh(self):
        self.refresh_button.setEnabled(False)
        self.status.setText("Lese meine Tickets aus Matrix42 …")
        self.reader.load_my_tickets()

    def show_result(self, result):
        self.refresh_button.setEnabled(True)
        rows = result.get("rows")
        self.results.clear()
        for row in rows or []:
            item = QListWidgetItem(mb.ticket_list_label(row))
            item.setToolTip(mb.ticket_tooltip(row))
            item.setData(Qt.UserRole, row)
            self.results.addItem(item)
        if rows:
            self.results.setCurrentRow(0)
        text = (f"{len(rows)} offene{'s' if len(rows) == 1 else ''} Ticket{'s' if len(rows) != 1 else ''}, "
                f"bei denen du Bearbeiter bist (Stand {result.get('at', '')}). Enter kopiert die Nummer."
                if rows is not None else "")
        if result.get("error"):
            text = (text + "\n" if text else "") + f"⚠ {result['error']}"
        self.status.setText("\n".join(t for t in (self._note, text) if t))

    def _selected(self, item, _old=None):
        self.copy_button.setEnabled(item is not None)
        self.close_button.setEnabled(item is not None)

    def new_ticket(self):
        from ticket_dialogs import NewTicketDialog
        dialog = NewTicketDialog(self.reader, self)
        if dialog.exec() == QDialog.Accepted and dialog.created:
            c = dialog.created
            text = f"{c['ticket']} angelegt" + (" und übernommen" if c.get("taken_over") else "") + \
                ", Nummer kopiert."
            self._note = text + (f"\n⚠ {c['warning']}" if c.get("warning") else "")
            self.status.setText(self._note)
        dialog.deleteLater()

    def close_ticket(self, item):
        from ticket_dialogs import CloseTicketDialog
        row = item.data(Qt.UserRole) if item is not None else None
        if not row:
            return
        dialog = CloseTicketDialog(self.reader, row, self)
        if dialog.exec() == QDialog.Accepted and dialog.closed:
            self.results.takeItem(self.results.row(item))
            self._note = f"{row['ticket']} geschlossen."
            self.status.setText(self._note)
        dialog.deleteLater()

    def copy_number(self, item):
        if item is None:
            return
        number = (item.data(Qt.UserRole) or {}).get("ticket", "")
        QApplication.clipboard().setText(number)
        self.status.setText(f"{number} kopiert.")

    def done(self, result):
        try:
            self.reader.my_tickets_loaded.disconnect(self.show_result)
        except (RuntimeError, TypeError):
            pass
        super().done(result)
