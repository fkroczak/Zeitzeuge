"""Fenster „Meine Tickets“: offene Tickets in Matrix42, bei denen du Bearbeiter bist.

Die Liste liest M42Reader alle 10 Minuten (my_tickets_loaded), „Aktualisieren“ liest sofort.
Nur lesen: Anlegen und Schließen kommen nach dem Mitschnitt „Ticket anlegen und schließen“.
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
        buttons.button(QDialogButtonBox.Close).setText("Schließen")
        self.copy_button = QPushButton("Nummer &kopieren", self)
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(lambda: self.copy_number(self.results.currentItem()))
        self.refresh_button = QPushButton("&Aktualisieren", self)
        self.refresh_button.clicked.connect(self.refresh)
        buttons.addButton(self.copy_button, QDialogButtonBox.ActionRole)
        buttons.addButton(self.refresh_button, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.results.currentItemChanged.connect(lambda item, _old: self.copy_button.setEnabled(item is not None))
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
        self.status.setText(text)

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
