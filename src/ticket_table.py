"""Tickettabelle für „Tickets“ und „Ticket suchen“: Spalten Ticket, Betreff, Kunde, Verwalter (des Kunden,
aus Matrix42 nachgeladen, siehe use_reader), Melder,
Art (Störung/Serviceanfrage), Status, Bearbeiter, Angelegt; nach jeder Spalte sortierbar, filterbar (jedes Wort muss vorkommen, wie bei
der Ticketsuche), erledigte Tickets grau. Enter oder Doppelklick: Signal activated(row).
Spaltenbreiten lassen sich im Kopf ziehen; gezogene Breiten bleiben (je Tabelle gespeichert).
Rechtsklick auf den Kopf: Spalten ein- und ausblenden (Ticket und Betreff bleiben immer, Verwalter ist
anfangs aus) und Breiten zurücksetzen; beides je Tabelle gespeichert. Der Betreff bekommt immer den Rest.
Rote/gelbe SLA-Ampel und neue Nachricht (blau): Zeile getönt, Balken am linken Rand. Neue Nachricht lässt
sich per Rechtsklick als gelesen markieren (mark_read, nur in Zeitzeuge gemerkt). Mit „ticket_state_colors“ auch die
übrigen Zeilen in der Farbe ihres Status (Einstellungen → Darstellung → Tickets).
"""
from PySide6.QtCore import QSettings, Qt, Signal

import m42_tickets as mt
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QPalette
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QMenu, QStyle, QStyledItemDelegate, QTableWidget,
                               QTableWidgetItem)

import m42_booking as mb
import skeleton

# Spalte -> Feld der Ticketzeile (m42_booking.ticket_row)
COLUMNS = [("Ticket", "ticket"), ("Betreff", "subject"), ("Kunde", "customer"), ("Verwalter", "managers"),
           ("Melder", "initiator"),
           ("Art", "type"), ("Status", "state"), ("Bearbeiter", "recipient"), ("Angelegt", "created")]
SUBJECT_COL = 1
ALWAYS_SHOWN = ("ticket", "subject")  # lassen sich nicht ausblenden
DEFAULT_HIDDEN = frozenset({"managers"})  # Verwalter erst auf Wunsch (Rechtsklick auf den Kopf)
PEOPLE_KEYS = ("customer", "managers", "initiator", "recipient")
# Kunde, Melder, Bearbeiter: Anteil an der Tabellenbreite, in Grenzen. Fest 150 px ließen dem
# Betreff bei 1280 px Fensterbreite nur 160 px („Meldung ploppt …“)
PEOPLE_SHARE, PEOPLE_MIN, PEOPLE_MAX = 0.09, 70, 130
# Art, Status, Angelegt: nach Inhalt, aber nur so breit, dass dem Betreff gut ein Drittel bleibt
# (unter Windows sind sie fast doppelt so breit wie unter Linux); nie schmaler als SMALL_MIN
SUBJECT_SHARE, SMALL_MIN = 0.35, 50

# Farben: SLA-Ampel und neue Nachricht (immer) und Status (nur mit config["ticket_state_colors"]); Zeile getönt
# (Deckkraft 0–255), Balken BAR_WIDTH px am linken Rand der Ticketnummer
SLA_COLORS = {"red": "#DC2626", "yellow": "#EAB308"}
MESSAGE_COLOR = "#2563EB"  # neue Nachricht im Ticket; „Neu“ darum türkis statt blau
STATE_COLORS = {"neu": "#0891B2", "zugewiesen": "#7C3AED", "in bearbeitung": "#16A34A",
                "angehalten": "#D97706"}
CLOSED_COLOR = "#9CA3AF"
SLA_TINT, STATE_TINT, BAR_WIDTH = 36, 20, 6
MARK_ROLE = Qt.UserRole + 1


def row_color(row, all_states=False):
    """Farbe einer Ticketzeile -> (Farbe, Deckkraft der Tönung) oder None."""
    if row.get("sla") in SLA_COLORS and not mb.is_closed(row):
        return SLA_COLORS[row["sla"]], SLA_TINT
    if row.get("new_message") and not mb.is_closed(row):
        return MESSAGE_COLOR, SLA_TINT
    if not all_states:
        return None
    if mb.is_closed(row):
        return CLOSED_COLOR, STATE_TINT
    color = STATE_COLORS.get((row.get("state") or "").strip().casefold())
    return (color, STATE_TINT) if color else None


READ_KEY = "ticket_table/read"  # Tickets, deren neue Nachricht als gelesen markiert ist (Ids)


def read_marks():
    """Ids der Tickets, deren neue Nachricht du als gelesen markiert hast (nur in Zeitzeuge: Matrix42
    bleibt „Neue Information erhalten“ gesetzt). Kommt das Kennzeichen weg und später wieder, ist das
    Ticket wieder blau."""
    raw = settings().value(READ_KEY, []) or []
    return {str(x) for x in ([raw] if isinstance(raw, str) else raw) if x}


def save_read_marks(ids):
    store = settings()
    if ids:
        store.setValue(READ_KEY, sorted(ids))
    else:
        store.remove(READ_KEY)


def is_unread(row, marks):
    """Neue Nachricht, die noch nicht als gelesen markiert ist."""
    return bool(row.get("new_message")) and row.get("id") not in marks


def _config_of(widget):
    """Einstellungen des Hauptfensters: erstes Fenster in der Eltern-Kette mit config."""
    while widget is not None:
        if isinstance(getattr(widget, "config", None), dict):
            return widget.config
        widget = widget.parent()
    return {}


class _MarkDelegate(QStyledItemDelegate):
    """Zeile in der Farbe des Tickets tönen (das Stylesheet übergeht setBackground) und vor der
    Ticketnummer einen Balken ohne Abstand an den linken Rand setzen."""

    def paint(self, painter, option, index):
        mark = index.siblingAtColumn(0).data(MARK_ROLE)
        if mark and not option.state & QStyle.State_Selected:
            tint = QColor(mark[0])
            tint.setAlpha(mark[1])
            painter.fillRect(option.rect, tint)
        super().paint(painter, option, index)
        if mark and index.column() == 0:
            r = option.rect
            painter.fillRect(r.left(), r.top(), BAR_WIDTH, r.height(), QColor(mark[0]))


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
        self.setItemDelegate(_MarkDelegate(self))
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
        self._reader = None  # liefert Verwalter je Kunde (use_reader)
        self._managers = {}  # OU-Id -> Verwalter des Kunden (m42_tickets.manager_summary)
        # Vom Benutzer gezogene Breiten {Feld: px}; _fit_columns lässt sie stehen
        self._fitting = False
        self._settings_key = "ticket_table/%s/widths" % name
        self._user_widths = self._load_widths()
        self._hidden_key = "ticket_table/%s/hidden" % name
        self._hidden = self._load_hidden()  # ausgeblendete Spalten (Felder)
        self._apply_hidden()
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

    def use_reader(self, reader):
        """Verwalter der Kunden aus Matrix42 nachladen (M42Reader.load_managers), sobald Tickets da sind."""
        self._reader = reader
        self._apply_hidden()
        if hasattr(reader, "managers_loaded"):
            reader.managers_loaded.connect(self.set_managers, Qt.QueuedConnection)

    # ------------------------------------------------------------ Spalten ein-/ausblenden

    def _load_hidden(self):
        store = settings()
        if not store.contains(self._hidden_key):
            return set(DEFAULT_HIDDEN)
        raw = store.value(self._hidden_key, "") or ""
        keys = {key for _n, key in COLUMNS} - set(ALWAYS_SHOWN)
        return {k for k in (raw if isinstance(raw, list) else str(raw).split(",")) if k in keys}

    def _offered(self, key):
        """Spalte im Kopfmenü wählbar? Verwalter nur, wenn sie aus Matrix42 kommen können."""
        return key not in ALWAYS_SHOWN and (key != "managers" or self._reader is not None)

    def _apply_hidden(self):
        for col, (_name, key) in enumerate(COLUMNS):
            self.setColumnHidden(col, key in self._hidden or (key == "managers" and self._reader is None))

    def column_visible(self, key):
        return not self.isColumnHidden([k for _n, k in COLUMNS].index(key))

    def set_column_visible(self, key, on):
        """Spalte ein- oder ausblenden und merken; Verwalter beim Einblenden gleich nachladen."""
        if key in ALWAYS_SHOWN:
            return
        self._hidden.discard(key) if on else self._hidden.add(key)
        settings().setValue(self._hidden_key, ",".join(sorted(self._hidden)))
        self._apply_hidden()
        if on and key == "managers":
            self._load_managers([self.row_at(r) for r in range(self.rowCount())])
        self._fit_columns()

    def reset_columns(self):
        """Spaltenauswahl wie am Anfang (alle außer Verwalter)."""
        settings().remove(self._hidden_key)
        self._hidden = set(DEFAULT_HIDDEN)
        self._apply_hidden()
        self._fit_columns()

    def _load_managers(self, rows):
        """Verwalter der offenen Tickets beim Leser anfragen (nur bei sichtbarer Spalte)."""
        if self._reader is None or not hasattr(self._reader, "load_managers") or not self.column_visible("managers"):
            return
        known = self._reader.load_managers([row.get("ou") for row in rows if not mb.is_closed(row)])
        if known:
            self._managers.update(known)
            for r in range(self.rowCount()):
                self._fill_managers(r, self.row_at(r))

    MANAGERS_COL = [key for _n, key in COLUMNS].index("managers")

    def set_managers(self, found):
        """Verwalter je Kunde (OU-Id -> Info) eintragen, in allen Zeilen dieses Kunden."""
        self._managers.update(found or {})
        for r in range(self.rowCount()):
            ou = self.row_at(r).get("ou")
            if ou in (found or {}):
                self._fill_managers(r, self.row_at(r))
        self._fit_columns()

    def _fill_managers(self, r, row):
        text, tip = mt.manager_summary(self._managers.get(row.get("ou")))
        item = self.item(r, self.MANAGERS_COL)
        if item is None:
            return
        item.setText(text)
        item.key = text.casefold() if text != "–" else "~"  # „nicht hinterlegt“ ans Ende
        item.setToolTip(f"{row.get('customer') or 'Kunde'}\n{tip}" if tip else mb.ticket_tooltip(row))

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
        menu.addSection("Spalten zeigen")
        for _name, key in COLUMNS:
            if not self._offered(key):
                continue
            action = menu.addAction(_name)
            action.setCheckable(True)
            action.setChecked(self.column_visible(key))
            action.toggled.connect(lambda on, k=key: self.set_column_visible(k, on))
        menu.addSeparator()
        columns = menu.addAction("Spaltenauswahl zurücksetzen")
        columns.setEnabled(settings().contains(self._hidden_key))
        columns.triggered.connect(self.reset_columns)
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
            if self.isColumnHidden(col):
                continue
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
        all_states = bool(_config_of(self).get("ticket_state_colors", False))
        self.clearSelection()
        self.setRowCount(len(rows))
        marks = read_marks()
        # Kennzeichen in Matrix42 weg: Markierung vergessen, damit die nächste Nachricht wieder blau ist
        stale = {row.get("id") for row in rows if not row.get("new_message")} & marks
        if stale:
            marks -= stale
            save_read_marks(marks)
        for r, row in enumerate(rows):
            closed = mb.is_closed(row)
            mark = row_color(dict(row, new_message=is_unread(row, marks)), all_states)
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
                    item.setData(MARK_ROLE, mark)
                self.setItem(r, c, item)
            self._fill_managers(r, row)
        self._load_managers(rows)
        if self._sort:
            self.sortItems(*self._sort)
        self._show_page()
        for r in range(self.rowCount()):
            if selected and self.row_at(r).get("id") == selected:
                self.selectRow(r)
                break

    def is_unread(self, row):
        return is_unread(row, read_marks())

    def mark_read(self, row, read=True):
        """Neue Nachricht als gelesen (blau weg) bzw. wieder als ungelesen markieren."""
        marks = read_marks()
        marks = marks | {row["id"]} if read else marks - {row["id"]}
        save_read_marks(marks)
        all_states = bool(_config_of(self).get("ticket_state_colors", False))
        for r in range(self.rowCount()):
            if self.row_at(r).get("id") == row["id"]:
                self.item(r, 0).setData(MARK_ROLE, row_color(dict(row, new_message=is_unread(row, marks)),
                                                             all_states))
        self.viewport().update()

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
