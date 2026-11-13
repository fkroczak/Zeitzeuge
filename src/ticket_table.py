"""Tickettabelle für „Tickets“ und „Ticket suchen“: Spalten Ticket, Betreff, Kunde, Melder,
Art (Störung/Serviceanfrage), Status, Bearbeiter, Angelegt; nach jeder Spalte sortierbar, filterbar (jedes Wort muss vorkommen, wie bei
der Ticketsuche), erledigte Tickets grau. Enter oder Doppelklick: Signal activated(row).
Spaltenbreiten lassen sich im Kopf ziehen; gezogene Breiten bleiben (je Tabelle gespeichert),
Rechtsklick auf den Kopf setzt sie zurück. Der Betreff bekommt immer den Rest.
"""
from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QPainter, QPalette
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTableWidget, QTableWidgetItem

import m42_booking as mb
import skeleton

# Spalte -> Feld der Ticketzeile (m42_booking.ticket_row)
COLUMNS = [("Ticket", "ticket"), ("Betreff", "subject"), ("Kunde", "customer"), ("Melder", "initiator"),
           ("Art", "type"), ("Status", "state"), ("Bearbeiter", "recipient"), ("Angelegt", "created")]
SUBJECT_COL = 1
PEOPLE_KEYS = ("customer", "initiator", "recipient")
# Kunde, Melder, Bearbeiter: Anteil an der Tabellenbreite, in Grenzen. Fest 150 px ließen dem
# Betreff bei 1280 px Fensterbreite nur 160 px („Meldung ploppt …“)
PEOPLE_SHARE, PEOPLE_MIN, PEOPLE_MAX = 0.09, 70, 130
# Art, Status, Angelegt: nach Inhalt, aber nur so breit, dass dem Betreff gut ein Drittel bleibt
# (unter Windows sind sie fast doppelt so breit wie unter Linux); nie schmaler als SMALL_MIN
SUBJECT_SHARE, SMALL_MIN = 0.35, 50


def settings():
    """Ablage der gezogenen Spaltenbreiten (Tests ersetzen sie)."""
    return QSettings("ZeitZeuge", "ZeitZeuge")


class _Item(QTableWidgetItem):
    """Zelle, die nach einem eigenen Schlüssel sortiert (Datum nach ISO statt „12.11.26“)."""

    def __init__(self, text, key):
        super().__init__(text)
        self.key = key

    def __lt__(self, other):
        return self.key < getattr(other, "key", other.text().casefold())


class TicketTable(QTableWidget):
    activated = Signal(object)  # Ticketzeile (dict), Enter oder Doppelklick

    def __init__(self, name, parent=None):
        super().__init__(0, len(COLUMNS), parent)
        self.setHorizontalHeaderLabels([n for n, _key in COLUMNS])
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(28)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)
        self.setAccessibleName(name)
        # Betreff bekommt den Platz; Kunde, Melder und Bearbeiter wachsen nur mäßig mit
        # (lange Firmennamen mit …, ganz im Hinweis), siehe resizeEvent
        header = self.horizontalHeader()
        for col, (_name, key) in enumerate(COLUMNS):
            if col == SUBJECT_COL:
                header.setSectionResizeMode(col, QHeaderView.Stretch)
            else:  # Breiten setzt _fit_columns (bei Größe und Inhalt), ziehen geht trotzdem
                header.setSectionResizeMode(col, QHeaderView.Interactive)
        # Sortieren erst auf Klick: bis dahin bleibt die Reihenfolge der Daten (Suche: offene zuerst)
        self._sort = None
        self._filter = ""
        self.page_size = 0  # Tickets je Seite, 0 = alle auf einer Seite
        self.page = 0
        self._loading = False
        # Vom Benutzer gezogene Breiten {Feld: px}; _fit_columns lässt sie stehen
        self._fitting = False
        self._settings_key = "ticket_table/%s/widths" % name
        self._user_widths = self._load_widths()
        header.sectionResized.connect(self._section_resized)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_menu)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(-1, Qt.AscendingOrder)
        header.sortIndicatorChanged.connect(self.sort_by)
        self.cellDoubleClicked.connect(lambda _r, _c: self._activate())
        enter = QAction(self)
        enter.setShortcuts([QKeySequence(Qt.Key_Return), QKeySequence(Qt.Key_Enter)])
        enter.setShortcutContext(Qt.WidgetShortcut)
        enter.triggered.connect(self._activate)
        self.addAction(enter)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_columns()

    def _load_widths(self):
        try:
            raw = settings().value(self._settings_key, {}) or {}
            keys = {key for _n, key in COLUMNS} - {COLUMNS[SUBJECT_COL][1]}
            return {k: int(v) for k, v in dict(raw).items() if k in keys and int(v) > 0}
        except (TypeError, ValueError):
            return {}

    def _save_widths(self):
        store = settings()
        if self._user_widths:
            store.setValue(self._settings_key, dict(self._user_widths))
        else:
            store.remove(self._settings_key)

    def _section_resized(self, col, _old, new):
        """Spalte im Kopf gezogen (oder Doppelklick auf den Rand): Breite merken."""
        if self._fitting or col == SUBJECT_COL or new <= 0:
            return
        self._user_widths[COLUMNS[col][1]] = new
        self._save_widths()

    def reset_widths(self):
        """Gezogene Breiten vergessen, wieder automatisch."""
        self._user_widths = {}
        self._save_widths()
        self._fit_columns()

    def _header_menu(self, pos):
        menu = QMenu(self)
        reset = menu.addAction("Spaltenbreiten zurücksetzen")
        reset.setEnabled(bool(self._user_widths))
        reset.triggered.connect(self.reset_widths)
        menu.exec(self.horizontalHeader().mapToGlobal(pos))

    def _fit_columns(self):
        self._fitting = True
        try:
            self._fit_auto()
        finally:
            self._fitting = False

    def _fit_auto(self):
        """Spaltenbreiten so, dass der Betreff (gestreckt) den meisten Platz bekommt:
        Ticketnummer ganz, Kunde/Melder/Bearbeiter mit Anteil an der Breite, Art/Status/Angelegt
        nach Inhalt, bei Platzmangel gekürzt (…, ganz im Hinweis). Gezogene Breiten bleiben."""
        header = self.horizontalHeader()
        width = self.viewport().width()
        people = max(PEOPLE_MIN, min(PEOPLE_MAX, int(width * PEOPLE_SHARE)))

        def content(col):
            return max(self.sizeHintForColumn(col), header.sectionSizeHint(col))
        small = {}
        fixed = 0  # schon vergebene Breite (ohne Betreff und Art/Status/Angelegt)
        for col, (_name, key) in enumerate(COLUMNS):
            if key in self._user_widths:
                want = self._user_widths[key]
                header.resizeSection(col, want)
                fixed += want
            elif key == "ticket":
                want = content(col)
                header.resizeSection(col, want)
                fixed += want
            elif key in PEOPLE_KEYS:
                header.resizeSection(col, people)
                fixed += people
            elif col != SUBJECT_COL:
                small[col] = content(col)
        budget = width * (1 - SUBJECT_SHARE) - fixed
        scale = min(1.0, max(budget, 0) / max(sum(small.values()), 1))
        for col, want in small.items():
            header.resizeSection(col, max(SMALL_MIN, min(want, int(want * scale))))

    def set_loading(self, on):
        """Wird gelesen: solange keine Zeile da ist, pulsierende Umrisse von Zeilen zeigen."""
        on = bool(on)
        if on == self._loading:
            return
        self._loading = on
        (skeleton.pulse().watch if on else skeleton.pulse().unwatch)(self.viewport())
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._loading and not any(not self.isRowHidden(r) for r in range(self.rowCount())):
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.Antialiasing)
            skeleton.table_rows(painter, self, row_height=self.verticalHeader().defaultSectionSize())
            painter.end()

    def _activate(self):
        row = self.current_row()
        if row:
            self.activated.emit(row)

    def sort_by(self, col, order=Qt.AscendingOrder):
        """Nach Spalte sortieren (auch bei späteren set_rows); col -1: Reihenfolge der Daten."""
        self._sort = (col, order) if col >= 0 else None
        header = self.horizontalHeader()
        if (header.sortIndicatorSection(), header.sortIndicatorOrder()) != (col, order):
            header.setSortIndicator(col, order)  # meldet sich über sortIndicatorChanged wieder
            return
        if self._sort:
            self.sortItems(col, order)
            self._show_page()

    def set_rows(self, rows):
        """Tickets zeigen: in der Reihenfolge der Daten, oder sortiert, wenn eine Spalte gewählt ist."""
        selected = (self.current_row() or {}).get("id")
        grey = self.palette().color(QPalette.PlaceholderText)  # muted (Design), wie Hinweise
        self.clearSelection()
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            closed = mb.is_closed(row)
            for c, (_name, key) in enumerate(COLUMNS):
                if key == "created":
                    text, sort_key = mb.ticket_date(row), row.get("created") or ""
                elif key == "type":
                    text = mb.ticket_kind(row)
                    sort_key = text.casefold()
                else:
                    text = row.get(key) or ""
                    if key in ("initiator", "recipient"):
                        text = text.split(" - ")[0]  # „Müller, Jan“ ohne Firma/Abteilung (steht im Hinweis)
                    sort_key = text.casefold()
                item = _Item(text, sort_key)
                item.setToolTip(mb.ticket_tooltip(row))
                if closed:
                    item.setForeground(grey)
                if c == 0:
                    item.setData(Qt.UserRole, row)
                self.setItem(r, c, item)
        if self._sort:
            self.sortItems(*self._sort)
        self._show_page()
        for r in range(self.rowCount()):
            if selected and self.row_at(r).get("id") == selected:
                self.selectRow(r)
                break

    def row_at(self, r):
        item = self.item(r, 0)
        return (item.data(Qt.UserRole) if item is not None else None) or {}

    def current_row(self):
        rows = self.selectionModel().selectedRows()
        return self.row_at(rows[0].row()) if rows else None

    def select_first(self):
        for r in range(self.rowCount()):
            if not self.isRowHidden(r):
                self.selectRow(r)
                return

    def visible_rows(self):
        """Angezeigte Tickets in der Reihenfolge der Tabelle (nach Filter und Sortierung)."""
        return [self.row_at(r) for r in range(self.rowCount()) if not self.isRowHidden(r)]

    def apply_filter(self, text):
        """Nur Tickets zeigen, in denen jedes Wort vorkommt; zurück auf die erste Seite."""
        self._filter = (text or "").strip()
        self.page = 0
        self._show_page()

    def _matching(self):
        """Zeilennummern, die zum Filter passen, in der Reihenfolge der Tabelle."""
        return [r for r in range(self.rowCount()) if not self._filter or mb.matches(self.row_at(r), self._filter)]

    def matching_rows(self):
        """Alle zum Filter passenden Tickets (über alle Seiten)."""
        return [self.row_at(r) for r in self._matching()]

    def pages(self):
        n = len(self._matching())
        return max(1, -(-n // self.page_size)) if self.page_size else 1

    def set_page(self, page, size=None):
        """Seite (ab 0) zeigen; size: Tickets je Seite (0 = alle)."""
        if size is not None:
            self.page_size = size
        self.page = page
        self._show_page()

    def _show_page(self):
        """Filter und Seite anwenden: nur die passenden Zeilen der aktuellen Seite zeigen."""
        match = self._matching()
        self.page = max(0, min(self.page, self.pages() - 1))
        shown = set(match[self.page * self.page_size:(self.page + 1) * self.page_size]
                    if self.page_size else match)
        for r in range(self.rowCount()):
            hide = r not in shown
            self.setRowHidden(r, hide)
            if hide and self.selectionModel().isRowSelected(r):
                self.clearSelection()
        self._fit_columns()  # Inhalt geändert: Breiten nach den gezeigten Zeilen
