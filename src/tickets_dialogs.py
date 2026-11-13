"""Fenster „Tickets“: aktuelle Tickets in Matrix42, nach Kategorie.

Über dem Filterfeld eine Reihe Pillen. Kategorien schalten um (immer genau eine):
„Meine Tickets“ (Bearbeiter = ich, vorausgewählt), „TK-Tickets“, „Alle“ und die gespeicherten
Filter der Ticketliste in Matrix42. Dahinter die Pille „Geschlossene“: an zeigt sie in jeder
Kategorie auch gelöste/geschlossene Tickets, aus nur offene und angehaltene.

Das Filterfeld sucht nur in dem, was die Pillen zeigen (Kategorie und Status); jedes Wort
muss irgendwo vorkommen, wie bei der Ticketsuche. Tabelle (Ticket, Betreff, Kunde, Melder,
Art, Status, Bearbeiter, Angelegt), nach jeder Spalte sortierbar, in Seiten zu 50 oder 100 Tickets.

Meine Tickets liest M42Reader alle 10 Minuten (my_tickets_loaded), die übrigen Kategorien beim
ersten Anzeigen und wenn sie älter als 10 Minuten sind (tickets_loaded); „Aktualisieren“ liest
sofort. „Neues Ticket …“, „Bearbeiten …“ und „Schließen …“ öffnen die Fenster aus ticket_dialogs.py.
"""
import time

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QToolButton, QVBoxLayout, QWidget)

import m42_booking as mb
from flow_layout import FlowLayout
from ticket_table import COLUMNS, TicketTable

MINE = "mine"
STALE_AFTER = 10 * 60  # Kategorien, die älter sind, beim Anzeigen neu lesen
# Feste Kategorien: (Schlüssel, Pille, gespeicherter Filter in Matrix42; "" = alle Tickets)
FIXED = [(MINE, "Meine Tickets", None), ("tk", "TK-Tickets", mb.TK_FILTER), ("all", "Alle", "")]
PAGE_SIZES = (50, 100)  # Tickets je Seite; die Wahl gilt bis zum Beenden für jedes neue Fenster


def _chip(text, parent):
    b = QToolButton(parent)
    b.setObjectName("chip")
    b.setText(text)
    b.setCheckable(True)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.StrongFocus)
    return b


class TicketsDialog(QDialog):
    page_size = PAGE_SIZES[0]

    def __init__(self, reader, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tickets")
        self.setMinimumSize(1040, 520)
        self.reader = reader
        self._note = ""  # letzte Meldung (angelegt/geschlossen/kopiert), bleibt beim Neuladen stehen
        self._changed = {}  # Ticket-ID -> geänderte Felder (bis die Liste neu gelesen ist)
        self._loading = set()  # Kategorien, die gerade gelesen werden
        self._rows = []
        self.category = MINE
        self.categories = {}  # Schlüssel -> (Titel, Filter)
        layout = QVBoxLayout(self)

        # ---- Pillen: Kategorien (umschalten) | Geschlossene (wirkt bei jeder Kategorie)
        self.pills = QWidget(self)
        self.pills.setObjectName("chips")
        self._flow = FlowLayout(self.pills, spacing=6)
        self.category_group = QButtonGroup(self)
        self.category_group.setExclusive(True)
        self.category_buttons = {}
        for key, title, fid in FIXED:
            self._add_category(key, title, fid)
        self._gap = QWidget(self.pills)
        self._gap.setFixedWidth(14)
        self._flow.addWidget(self._gap)
        self.closed_button = _chip("Geschlossene", self.pills)
        self.closed_button.setToolTip("Auch gelöste und geschlossene Tickets der Kategorie zeigen")
        self.closed_button.setAccessibleName("Geschlossene Tickets zeigen")
        self.closed_button.toggled.connect(self._closed_toggled)
        self._flow.addWidget(self.closed_button)
        self.category_buttons[MINE].blockSignals(True)  # Tabelle gibt es noch nicht
        self.category_buttons[MINE].setChecked(True)
        self.category_buttons[MINE].blockSignals(False)
        layout.addWidget(self.pills)

        self.filter_edit = QLineEdit(self)
        self.filter_edit.setAccessibleName("Tickets filtern")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self.apply_filter)
        self.filter_edit.installEventFilter(self)
        layout.addWidget(self.filter_edit)

        self.table = TicketTable("Tickets", self)
        self.table.setAccessibleDescription("Enter oder Doppelklick kopiert die Ticketnummer.")
        self.table.sort_by(len(COLUMNS) - 1, Qt.DescendingOrder)  # neueste zuerst
        self.table.activated.connect(lambda _row: self.copy_number())
        self.table.itemSelectionChanged.connect(self._selected)
        self.table.set_page(0, self.page_size)
        layout.addWidget(self.table, 1)

        self.status = QLabel(self)
        # Ohne Umbruch: jede Meldung ist eine Zeile. Ein umbrechendes Label bekommt im Kartenrahmen
        # bei mehr Zeilen nicht mehr Platz (zweite Zeile unter der Fußleiste); lange Texte im Tooltip.
        self.status.setObjectName("hint")
        self.status.setTextFormat(Qt.PlainText)
        # Seiten: ‹ Seite 1 von 3 ›  [50 pro Seite]
        self.prev_button = QToolButton(self)
        self.prev_button.setText("‹")
        self.prev_button.setToolTip("Vorherige Seite")
        self.prev_button.setAccessibleName("Vorherige Seite")
        self.prev_button.clicked.connect(lambda: self.go_page(self.table.page - 1))
        self.page_label = QLabel(self)
        self.page_label.setObjectName("hint")
        self.next_button = QToolButton(self)
        self.next_button.setText("›")
        self.next_button.setToolTip("Nächste Seite")
        self.next_button.setAccessibleName("Nächste Seite")
        self.next_button.clicked.connect(lambda: self.go_page(self.table.page + 1))
        self.size_combo = QComboBox(self)
        self.size_combo.setAccessibleName("Tickets pro Seite")
        for size in PAGE_SIZES:
            self.size_combo.addItem(f"{size} pro Seite", size)
        self.size_combo.setCurrentIndex(PAGE_SIZES.index(self.page_size))
        self.size_combo.currentIndexChanged.connect(self._size_chosen)
        foot = QHBoxLayout()
        foot.addWidget(self.status, 1)
        for w in (self.prev_button, self.page_label, self.next_button, self.size_combo):
            foot.addWidget(w)
        layout.addLayout(foot)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.button(QDialogButtonBox.Close).setText("Fertig")
        self.copy_button = QPushButton("Nummer &kopieren", self)
        self.copy_button.clicked.connect(self.copy_number)
        self.refresh_button = QPushButton("&Aktualisieren", self)
        self.refresh_button.clicked.connect(self.refresh)
        self.new_button = QPushButton("&Neues Ticket …", self)
        self.new_button.clicked.connect(self.new_ticket)
        self.edit_button = QPushButton("&Bearbeiten …", self)
        self.edit_button.setToolTip("Betreff, Kategorie oder Beschreibung des markierten Tickets ändern")
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
        modernize(self, "Tickets", "Aktuelle Tickets in Matrix42, nach Kategorie", "list",
                  intro=False, primary=self.new_button)
        self._selected()
        reader.my_tickets_loaded.connect(self._mine_loaded, Qt.QueuedConnection)
        if hasattr(reader, "tickets_loaded"):
            reader.tickets_loaded.connect(self._category_loaded, Qt.QueuedConnection)
        if hasattr(reader, "ticket_filters_loaded"):
            reader.ticket_filters_loaded.connect(self.show_filters, Qt.QueuedConnection)
            if getattr(reader, "ticket_filters", None) is None:
                reader.load_ticket_filters()
            else:
                self.show_filters(reader.ticket_filters)
        if reader.my_tickets is None:
            self.refresh()
        else:
            self.show_category()
        self.filter_edit.setFocus()

    def eventFilter(self, obj, event):
        # Pfeil runter im Filterfeld: in die Tabelle
        if obj is self.filter_edit and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Down:
            self.table.setFocus()
            if self.current_row() is None:
                self.table.select_first()
            return True
        return super().eventFilter(obj, event)

    # ---- Pillen

    def _add_category(self, key, title, fid):
        b = _chip(title, self.pills)
        b.setAccessibleName(f"Kategorie {title}")
        b.toggled.connect(lambda on, k=key: on and self.choose(k))
        self.category_group.addButton(b)
        self.category_buttons[key] = b
        self.categories[key] = (title, fid)
        self._flow.addWidget(b)
        gap = getattr(self, "_gap", None)
        if gap is not None:  # später dazu (Filter aus Matrix42): vor der Lücke zu „Geschlossene“
            self._flow._items.insert(self._flow.indexOf(gap), self._flow._items.pop())
            self._flow.invalidate()
        return b

    def show_filters(self, filters):
        """Gespeicherte Filter aus Matrix42 als weitere Kategorie-Pillen (nach den festen)."""
        for f in filters or []:
            key = f"f:{f['id']}"
            if key not in self.categories:
                self._add_category(key, f["title"], f["id"])
        self.pills.updateGeometry()

    def choose(self, key):
        """Kategorie umschalten (Pille), bei Bedarf neu lesen."""
        if key not in self.categories:
            return
        if not self.category_buttons[key].isChecked():
            self.category_buttons[key].setChecked(True)  # meldet sich über toggled wieder
            return
        self.category = key
        self.table.clearSelection()
        view = self._view()
        if key != MINE and key not in self._loading and \
                (view is None or time.time() - view.get("time", 0) > STALE_AFTER):
            self.refresh()
        self.show_category()

    def _closed_toggled(self, _on):
        self.show_category()

    def go_page(self, page):
        self.table.set_page(page)
        self._update_status()
        self._selected()

    def _size_chosen(self, _index):
        TicketsDialog.page_size = self.size_combo.currentData()
        self.table.set_page(0, self.page_size)
        self._update_status()
        self._selected()

    def title(self):
        return self.categories[self.category][0]

    # ---- Daten

    def _view(self):
        """Letzte Antwort zur gewählten Kategorie: {rows, all?, error, at, limited} oder None."""
        if self.category == MINE:
            return self.reader.my_tickets
        return getattr(self.reader, "ticket_views", {}).get(self.category)

    def refresh(self):
        self.refresh_button.setEnabled(False)
        self._loading.add(self.category)
        self._set_status(f"Lese {self.title()} aus Matrix42 …")
        if self.category == MINE:
            self.reader.load_my_tickets()
        else:
            self.reader.load_tickets(self.category, self.categories[self.category][1])

    def _mine_loaded(self, _result):
        self._changed.clear()  # frisch gelesen: lokale Änderungen stecken drin
        self._loaded(MINE)

    def _category_loaded(self, result):
        self._loaded(result.get("key"))

    def _loaded(self, key):
        self._loading.discard(key)
        if key == self.category:
            self.show_category()

    def show_category(self):
        """Tabelle aus der gewählten Kategorie und dem Status (Geschlossene an/aus) füllen."""
        self.refresh_button.setEnabled(self.category not in self._loading)
        view = self._view() or {}
        rows = view.get("rows")
        if self.category == MINE and self.closed_button.isChecked():
            rows = view.get("all", rows)
        rows = [dict(r, **self._changed.get(r.get("id"), {})) for r in rows or []]
        if not self.closed_button.isChecked():
            rows = [r for r in rows if not mb.is_closed(r)]
        self._rows = rows
        self.table.page = 0
        self.table.set_rows(rows)
        self.filter_edit.setPlaceholderText(
            f"In „{self.title()}“ filtern nach Ticket, Betreff, Kunde, Melder, Art, Status oder Bearbeiter")
        self.apply_filter()

    def current_row(self):
        return self.table.current_row()

    def visible_rows(self):
        return self.table.visible_rows()

    def apply_filter(self, *_):
        self.table.apply_filter(self.filter_edit.text())
        self._update_status()
        self._selected()

    def _update_status(self):
        view = self._view() or {}
        n, shown = len(self._rows), len(self.table.matching_rows())
        page, pages = self.table.page, self.table.pages()
        self.page_label.setText(f"Seite {page + 1} von {pages}")
        self.prev_button.setEnabled(page > 0)
        self.next_button.setEnabled(page < pages - 1)
        closed = self.closed_button.isChecked()
        text = ""
        if self.category in self._loading:
            text = f"Lese {self.title()} aus Matrix42 …"
        elif view.get("at") or n:
            what = "Ticket" if n == 1 else "Tickets"
            if closed:
                done = sum(1 for r in self._rows if mb.is_closed(r))
                text = f"{self.title()}: {n} {what}, davon {done} geschlossen"
            else:
                text = f"{self.title()}: {n} offene{'s' if n == 1 else ''} {what}"
            text += f" (Stand {view.get('at', '')})."
            if shown != n:
                text += f" {shown} passen zum Filter."
            if view.get("limited"):
                text += f" Nur die neuesten {mb.MY_TICKETS_PAGES * mb.MY_TICKETS_PAGE_SIZE} gelesen."
            text += " Enter kopiert die Nummer."
        if view.get("error"):
            text = (text + "\n" if text else "") + f"⚠ {view['error']}"
        self._set_status("\n".join(t for t in (self._note, text) if t))

    def _set_status(self, text):
        self.status.setText(text)
        self.status.setToolTip(text)

    def _selected(self):
        row = self.current_row()
        self.copy_button.setEnabled(row is not None)
        self.edit_button.setEnabled(row is not None)
        self.close_button.setEnabled(row is not None and not mb.is_closed(row))

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
            self._changed.setdefault(row["id"], {})["subject"] = subject
            self.show_category()
        dialog.deleteLater()

    def close_ticket(self):
        from ticket_dialogs import CloseTicketDialog
        row = self.current_row()
        if not row or mb.is_closed(row):
            return
        dialog = CloseTicketDialog(self.reader, row, self)
        if dialog.exec() == QDialog.Accepted and dialog.closed:
            self._note = f"{row['ticket']} geschlossen."
            # bis zum Neulesen als geschlossen zeigen (ohne „Geschlossene“ verschwindet es)
            self._changed.setdefault(row["id"], {})["state"] = "Geschlossen"
            self.show_category()
        dialog.deleteLater()

    def copy_number(self):
        row = self.current_row()
        if not row:
            return
        QApplication.clipboard().setText(row["ticket"])
        self._note = f"{row['ticket']} kopiert."
        self._update_status()

    def done(self, result):
        for signal, slot in (("my_tickets_loaded", self._mine_loaded), ("tickets_loaded", self._category_loaded),
                             ("ticket_filters_loaded", self.show_filters)):
            try:
                getattr(self.reader, signal).disconnect(slot)
            except (AttributeError, RuntimeError, TypeError):
                pass
        super().done(result)
