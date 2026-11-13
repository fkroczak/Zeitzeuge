"""Fenster „Tickets“: aktuelle Tickets in Matrix42, nach Kategorie.

Kategorien schalten um (immer genau eine): „Meine Tickets“ (vorausgewählt), „TK-Tickets“, „Alle“
und die gespeicherten Filter der Ticketliste in Matrix42. „Geschlossene“ wirkt bei jeder
Kategorie: an zeigt sie auch gelöste/geschlossene Tickets, aus nur offene und angehaltene.

Wie die Kategorien angeboten werden, wählt Einstellungen → Darstellung → Tickets (Kacheln mit
Skelett-Bild), gespeichert in der Einstellung ticket_layout:
  1 Zwei beschriftete Zeilen „Ansicht“ und „Pools“, Schalter „Geschlossene zeigen“ (Standard)
  2 Kompakt: Hauptkategorien als Pillen, TK/Pools/Weitere als Menü-Pillen
  3 Seitenleiste mit Überschriften wie in Matrix42
  4 Zwei Ebenen: oben der Bereich, darunter seine Kategorien
  5 Favoriten: angeheftete Pillen (ticket_favorites), der Rest über „+ Filter“

Das Filterfeld sucht nur in dem, was Kategorie und Status zeigen; jedes Wort muss irgendwo
vorkommen, wie bei der Ticketsuche. Tabelle (Ticket, Betreff, Kunde, Melder, Art, Status,
Bearbeiter, Angelegt), nach jeder Spalte sortierbar, in Seiten zu 50 oder 100 Tickets.

Meine Tickets liest M42Reader alle 10 Minuten (my_tickets_loaded), die übrigen Kategorien beim
ersten Anzeigen und wenn sie älter als 10 Minuten sind (tickets_loaded); „Aktualisieren“ liest
sofort. „Neues Ticket …“, „Ansehen …“ (auch Enter/Doppelklick), „Bearbeiten …“ und „Schließen …“
öffnen die Fenster aus ticket_dialogs.py.
"""
import time

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

import m42_booking as mb
from flow_layout import FlowLayout
from ticket_table import COLUMNS, TicketTable

MINE = "mine"
STALE_AFTER = 10 * 60  # Kategorien, die älter sind, beim Anzeigen neu lesen
# Feste Kategorien: (Schlüssel, Pille, gespeicherter Filter in Matrix42; "" = alle Tickets)
FIXED = [(MINE, "Meine Tickets", None), ("tk", "TK-Tickets", mb.TK_FILTER), ("all", "Alle", "")]
# Reihenfolge der Pillen: Gruppen (mit Abstand dazwischen), darin diese Reihenfolge.
# Titel klein und ohne Leer-/Satzzeichen; Filter, die nirgends passen, kommen ans Ende.
PILL_GROUPS = [
    ["meinetickets"],                                                         # ich
    ["alle", "neuetickets", "ohneverantwortung"],                             # alle / unverteilt
    ["tktickets", "neuetktickets", "ticketpooltk"],                           # TK
    ["ticketpoola", "ticketpoolb", "ticketpoolinfrastruktur", "ticketpoolpvs"],  # Pools
    ["offenvertrieb"],                                                        # Vertrieb
]


def pill_rank(title):
    """Titel -> (Gruppe, Platz) für die Reihenfolge der Pillen. Unbekannte nach Ähnlichkeit:
    „TK“ zur TK-Gruppe, „Pool“ zu den Pools, sonst ans Ende (Reihenfolge wie in Matrix42)."""
    key = mb._title_key(title)
    for g, keys in enumerate(PILL_GROUPS):
        if key in keys:
            return g, keys.index(key)
    words = set(mb.filter_title(title).casefold().split())
    if "tk" in words:
        return 2, 99
    if "pool" in words or key.startswith("ticketpool"):
        return 3, 99
    return len(PILL_GROUPS), 99


GROUP_NAMES = ["Meine", "Allgemein", "TK", "Pools", "Weitere"]  # zu PILL_GROUPS, „Weitere“ = Rest

# Anordnungen (Einstellung ticket_layout), Nummer -> Name
LAYOUTS = {1: "Zwei beschriftete Zeilen", 2: "Kompakt mit Menüs", 3: "Seitenleiste wie in Matrix42",
           4: "Bereich und Unterfilter", 5: "Favoriten"}
DEFAULT_LAYOUT = 1
DEFAULT_FAVORITES = [MINE, "tk", "all"]

PAGE_SIZES = (50, 100)  # Tickets je Seite; die Wahl gilt bis zum Beenden für jedes neue Fenster


def _chip(text, parent, name="chip"):
    b = QToolButton(parent)
    b.setObjectName(name)
    b.setText(text)
    b.setCheckable(name == "chip")
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.StrongFocus)
    return b


class _Row(FlowLayout):
    """Fließende Pillen-Zeile ohne „Höhe aus Breite“ nach außen: die Höhe setzt _fit_rows. Sonst
    verteilt der Kartenrahmen freien Platz als Lücken zwischen Auswahl, Suche und Tabelle."""

    def hasHeightForWidth(self):
        return False


def _gap(parent, width):
    gap = QWidget(parent)
    gap.setAttribute(Qt.WA_TransparentForMouseEvents)
    gap.setStyleSheet("background: transparent;")
    gap.setFixedSize(width, 1)
    return gap


class TicketsDialog(QDialog):
    page_size = PAGE_SIZES[0]
    favorites_changed = Signal(list)  # Favoriten (Anordnung 5) geändert (zum Speichern)

    def __init__(self, reader, parent=None, layout=DEFAULT_LAYOUT, favorites=None):
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

        self.layout_no = layout if layout in LAYOUTS else DEFAULT_LAYOUT
        self.favorites = list(favorites) if favorites else list(DEFAULT_FAVORITES)
        self.category_buttons = {}  # Kategorie -> Pille, soweit in der Anordnung als Pille sichtbar
        for key, title, fid in FIXED:
            self.categories[key] = (title, fid)

        # „Geschlossene“: als Pille (Anordnungen 3, 5) oder als Schalter (1, 2, 4), beide gleich
        self.closed_chip = _chip("Geschlossene", self)
        self.closed_switch = QCheckBox("Geschlossene zeigen", self)
        self.closed_switch.setObjectName("switch")
        for w in (self.closed_chip, self.closed_switch):
            w.setToolTip("Auch gelöste und geschlossene Tickets der Kategorie zeigen")
            w.setAccessibleName("Geschlossene Tickets zeigen")
            w.toggled.connect(self._closed_toggled)

        # Oben: Auswahl der Kategorie (je nach Anordnung neu gebaut), darunter Suche
        self.selector = QWidget(self)
        self.selector.setObjectName("chips")
        self.selector_layout = QVBoxLayout(self.selector)
        self.selector_layout.setContentsMargins(0, 0, 0, 0)
        self.selector_layout.setSpacing(6)
        self.selector.setStyleSheet("QWidget#chips, QWidget#chip_row { background: transparent; }")
        self.selector.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)  # Platz bekommt die Tabelle
        layout.addWidget(self.selector)

        self.filter_edit = QLineEdit(self)
        self.filter_edit.setAccessibleName("Tickets filtern")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self.apply_filter)
        self.filter_edit.installEventFilter(self)
        self.search_row = QWidget(self)
        search = self._search_layout = QHBoxLayout(self.search_row)
        search.setContentsMargins(0, 0, 0, 0)
        search.addWidget(self.filter_edit, 1)
        search.addWidget(self.closed_switch)
        search.addWidget(self.closed_chip)
        layout.addWidget(self.search_row)

        self.table = TicketTable("Tickets", self)
        self.table.setAccessibleDescription("Enter oder Doppelklick öffnet das Ticket.")
        self.table.sort_by(len(COLUMNS) - 1, Qt.DescendingOrder)  # neueste zuerst
        self.table.activated.connect(lambda _row: self.view_ticket())
        self.table.itemSelectionChanged.connect(self._selected)
        self.table.set_page(0, self.page_size)
        # Mitte: Seitenleiste (Anordnung 3) und Tabelle
        self.sidebar = QListWidget(self)
        self.sidebar.setAccessibleName("Kategorien")
        self.sidebar.setFixedWidth(220)
        self.sidebar.itemClicked.connect(self._sidebar_clicked)
        self.sidebar.currentItemChanged.connect(lambda item, _old: self._sidebar_clicked(item))
        self.middle = QWidget(self)
        self.middle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # der Platz geht an die Tabelle
        mid = QHBoxLayout(self.middle)
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(12)
        mid.addWidget(self.sidebar)
        mid.addWidget(self.table, 1)
        layout.addWidget(self.middle, 1)

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
        self.view_button = QPushButton("Ans&ehen …", self)
        self.view_button.setToolTip("Markiertes Ticket mit Beschreibung und Kontakt des Melders zeigen (Enter)")
        self.view_button.clicked.connect(self.view_ticket)
        self.edit_button = QPushButton("&Bearbeiten …", self)
        self.edit_button.setToolTip("Betreff, Kategorie oder Beschreibung des markierten Tickets ändern")
        self.edit_button.clicked.connect(self.edit_ticket)
        self.close_button = QPushButton("&Schließen …", self)
        self.close_button.setToolTip("Markiertes Ticket mit Lösungstext schließen")
        self.close_button.clicked.connect(self.close_ticket)
        for button in (self.new_button, self.view_button, self.edit_button, self.close_button, self.copy_button,
                       self.refresh_button):
            button.setAutoDefault(False)
            buttons.addButton(button, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        # Rahmen wie „Tätigkeit nachtragen“: Kopf, Inhalt, Fuß mit „Neues Ticket …“ als Hauptaktion
        from card_dialog import modernize
        modernize(self, "Tickets", "Aktuelle Tickets in Matrix42, nach Kategorie", "list",
                  intro=False, primary=self.new_button)
        self._build_selector()
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

    # ---- Auswahl der Kategorie (Anordnungen 1–5)

    @property
    def closed_button(self):
        """Der sichtbare Knopf für „Geschlossene“ (Pille oder Schalter)."""
        return self.closed_chip if self.layout_no in (3, 5) else self.closed_switch

    def closed(self):
        return self.closed_switch.isChecked()

    def _closed_toggled(self, on):
        for w in (self.closed_chip, self.closed_switch):
            if w.isChecked() != on:
                w.blockSignals(True)
                w.setChecked(on)
                w.blockSignals(False)
        self.show_category()

    def groups(self):
        """[(Gruppe, [Kategorien])] in Anzeigereihenfolge, leere Gruppen weggelassen."""
        order = sorted(self.categories, key=lambda k: pill_rank(self.categories[k][0]))  # stabil
        out = {}
        for key in order:
            out.setdefault(pill_rank(self.categories[key][0])[0], []).append(key)
        return [(g, out[g]) for g in sorted(out)]

    def group_of(self, key):
        return pill_rank(self.categories[key][0])[0]

    def show_filters(self, filters):
        """Gespeicherte Filter aus Matrix42 als weitere Kategorien."""
        for f in filters or []:
            key = f"f:{f['id']}"
            if key not in self.categories:
                self.categories[key] = (f["title"], f["id"])
        self._build_selector()

    def choose_layout(self, no):
        """Anordnung wechseln (Einstellungen → Darstellung → Tickets)."""
        if no not in LAYOUTS:
            return
        self.layout_no = no
        self._build_selector()

    def _pill(self, key, parent, text=None):
        title = self.categories[key][0]
        b = _chip(text or title, parent)
        b.setAccessibleName(f"Kategorie {title}")
        b.setChecked(key == self.category)
        b.clicked.connect(lambda _c=False, k=key: self.choose(k))
        self.category_buttons[key] = b
        return b

    def _flow(self, parent=None):
        w = QWidget(parent or self.selector)
        w.setObjectName("chip_row")  # ohne eigenen Hintergrund (Stil am Auswahlbereich)
        return w, _Row(w, spacing=6)

    def _row_label(self, text, parent):
        label = QLabel(text, parent)
        label.setObjectName("section_title")
        label.setFixedWidth(64)
        return label

    def _build_selector(self):
        """Auswahl der Kategorie für die gewählte Anordnung neu bauen; die Kategorie mit dem
        Fokus behält ihn."""
        focused = next((k for k, b in self.category_buttons.items() if b.hasFocus()), None)
        if self.closed_chip.parentWidget() is not self.search_row:  # aus Anordnung 5 zurückholen
            self._search_layout.insertWidget(2, self.closed_chip)
        while self.selector_layout.count():
            w = self.selector_layout.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self.category_buttons = {}
        no = self.layout_no
        self.sidebar.setVisible(no == 3)
        self.closed_switch.setVisible(no in (1, 2, 4))
        self.closed_chip.setVisible(no == 3)
        getattr(self, f"_build_{no}")()
        for b in self.selector.findChildren(QToolButton):
            b.ensurePolished()  # Größe mit Stil (Polster), sonst schneidet die Zeile Knöpfe ab
        self.selector.setVisible(self.selector_layout.count() > 0)
        # Höhe neu rechnen: sonst behält der Bereich die Höhe der vorigen Anordnung
        self._fit_rows()
        if focused in self.category_buttons:
            self.category_buttons[focused].setFocus()

    def _fit_rows(self):
        """Pillen-Zeilen so hoch wie für die echte Breite nötig. Ohne bekannte Breite schätzt
        Qt eine fließende Zeile, als stünde jede Pille allein (viel zu hoch)."""
        width = self.search_row.width()
        if width <= 0:
            return
        for i in range(self.selector_layout.count()):
            row = self.selector_layout.itemAt(i).widget()
            if row is not None and row.layout() is not None:
                row.setFixedHeight(row.layout().heightForWidth(width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_rows()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_rows()

    def _build_1(self):
        """Zwei beschriftete Zeilen: „Ansicht“ (Meine, Allgemein, Weitere) und „Pools“ (TK, Pools)."""
        for title, wanted in (("Ansicht", (0, 1, 4)), ("Pools", (2, 3))):
            row, flow = self._flow()
            flow.addWidget(self._row_label(title, row))
            first = True
            for g, keys in self.groups():
                if g not in wanted:
                    continue
                if not first:
                    flow.addWidget(_gap(row, 10))
                first = False
                for key in keys:
                    flow.addWidget(self._pill(key, row))
            if not first:
                self.selector_layout.addWidget(row)
            else:
                row.deleteLater()

    def _build_2(self):
        """Kompakt: Meine und Allgemein als Pillen, TK/Pools/Weitere als Menü-Pillen."""
        row, flow = self._flow()
        for g, keys in self.groups():
            if g in (0, 1):
                for key in keys:
                    flow.addWidget(self._pill(key, row))
                continue
            name = GROUP_NAMES[g]
            current = self.category if self.category in keys else None
            b = _chip((f"{name}: {self.categories[current][0]}" if current else name) + "  ▾", row)
            b.setChecked(current is not None)
            b.setAccessibleName(f"Kategorien {name}")
            b.setPopupMode(QToolButton.InstantPopup)
            menu = QMenu(b)
            for key in keys:
                action = menu.addAction(self.categories[key][0])
                action.setCheckable(True)
                action.setChecked(key == self.category)
                action.triggered.connect(lambda _c=False, k=key: self.choose(k))
            b.setMenu(menu)
            b.group_keys = keys
            flow.addWidget(_gap(row, 4))
            flow.addWidget(b)
        self.selector_layout.addWidget(row)

    def _build_3(self):
        """Seitenleiste mit Überschriften je Gruppe (wie in Matrix42)."""
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        heads = ["Persönlich", "Allgemein", "TK", "Pools", "Weitere"]
        for g, keys in self.groups():
            head = QListWidgetItem(heads[g].upper())
            head.setFlags(Qt.NoItemFlags)
            font = QFont(self.sidebar.font())
            font.setBold(True)
            font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
            head.setFont(font)
            self.sidebar.addItem(head)
            for key in keys:
                item = QListWidgetItem("   " + self.categories[key][0])
                item.setData(Qt.UserRole, key)
                self.sidebar.addItem(item)
                if key == self.category:
                    self.sidebar.setCurrentItem(item)
        self.sidebar.blockSignals(False)

    def _sidebar_clicked(self, item):
        key = item.data(Qt.UserRole) if item is not None else None
        if key and key != self.category:
            self.choose(key)

    def _build_4(self):
        """Zwei Ebenen: oben die Bereiche, darunter die Kategorien des gewählten Bereichs."""
        groups = self.groups()
        current = self.group_of(self.category)
        top, flow = self._flow()
        for g, keys in groups:
            b = _chip(GROUP_NAMES[g], top)
            b.setStyleSheet("QToolButton#chip { padding: 4px 16px; font-weight: bold; }")
            b.setChecked(g == current)
            b.setAccessibleName(f"Bereich {GROUP_NAMES[g]}")
            b.clicked.connect(lambda _c=False, k=keys: self.choose(self._last_in(k)))
            flow.addWidget(b)
        self.selector_layout.addWidget(top)
        keys = dict(groups).get(current, [])
        if len(keys) > 1:
            sub, flow = self._flow()
            label = QLabel(f"{GROUP_NAMES[current]}:", sub)
            label.setObjectName("hint")
            flow.addWidget(label)
            for key in keys:
                flow.addWidget(self._pill(key, sub))
            self.selector_layout.addWidget(sub)

    def _last_in(self, keys):
        """Zuletzt gewählte Kategorie eines Bereichs (sonst die erste)."""
        last = getattr(self, "_last_by_group", {})
        return last.get(self.group_of(keys[0]), keys[0])

    def _build_5(self):
        """Favoriten als Pillen, die übrigen über „+ Filter“ (dort auch anheften/lösen)."""
        row, flow = self._flow()
        shown = [k for k in self.favorites if k in self.categories]
        if self.category not in shown:
            shown.append(self.category)  # gewählt, aber nicht angeheftet: vorübergehend zeigen
        for key in shown:
            flow.addWidget(self._pill(key, row))
        more = _chip("+ Filter", row, name="chip_add")
        more.setAccessibleName("Weitere Kategorien und Favoriten")
        more.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(more)
        for g, keys in self.groups():
            menu.addSection(GROUP_NAMES[g])
            for key in keys:
                action = menu.addAction(self.categories[key][0])
                action.triggered.connect(lambda _c=False, k=key: self.choose(k))
        menu.addSeparator()
        pin = menu.addMenu("Als Pille &anheften")
        for g, keys in self.groups():
            for key in keys:
                action = pin.addAction(self.categories[key][0])
                action.setCheckable(True)
                action.setChecked(key in self.favorites)
                action.toggled.connect(lambda on, k=key: self.pin(k, on))
        more.setMenu(menu)
        flow.addWidget(more)
        flow.addWidget(_gap(row, 18))
        self.closed_chip.setParent(row)
        flow.addWidget(self.closed_chip)
        self.closed_chip.show()
        self.selector_layout.addWidget(row)

    def pin(self, key, on):
        """Kategorie als Favoriten-Pille anheften oder lösen (Anordnung 5)."""
        if on and key not in self.favorites:
            self.favorites.append(key)
        elif not on and key in self.favorites:
            self.favorites.remove(key)
        else:
            return
        self.favorites_changed.emit(list(self.favorites))
        self._build_selector()

    def choose(self, key):
        """Kategorie umschalten, bei Bedarf neu lesen."""
        if key not in self.categories:
            return
        if not hasattr(self, "_last_by_group"):
            self._last_by_group = {}
        self._last_by_group[self.group_of(key)] = key
        changed = key != self.category
        self.category = key
        if changed:
            self.table.clearSelection()
            view = self._view()
            if key != MINE and key not in self._loading and \
                    (view is None or time.time() - view.get("time", 0) > STALE_AFTER):
                self.refresh()
            self.show_category()
        if self.layout_no == 3:
            self._sync_sidebar()  # nicht neu bauen: kann aus dem Signal der Liste kommen
        else:
            self._build_selector()

    def _sync_sidebar(self):
        for i in range(self.sidebar.count()):
            item = self.sidebar.item(i)
            if item.data(Qt.UserRole) == self.category and self.sidebar.currentItem() is not item:
                self.sidebar.blockSignals(True)
                self.sidebar.setCurrentItem(item)
                self.sidebar.blockSignals(False)

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
        if self.category == MINE and self.closed():
            rows = view.get("all", rows)
        rows = [dict(r, **self._changed.get(r.get("id"), {})) for r in rows or []]
        if not self.closed():
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
        closed = self.closed()
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
            text += " Enter öffnet das Ticket."
        if view.get("error"):
            text = (text + "\n" if text else "") + f"⚠ {view['error']}"
        self._set_status("\n".join(t for t in (self._note, text) if t))

    def _set_status(self, text):
        self.status.setText(text)
        self.status.setToolTip(text)

    def _selected(self):
        row = self.current_row()
        self.copy_button.setEnabled(row is not None)
        self.view_button.setEnabled(row is not None)
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

    def view_ticket(self):
        from ticket_dialogs import ViewTicketDialog
        row = self.current_row()
        if not row:
            return
        dialog = ViewTicketDialog(self.reader, row, self)
        action = dialog.action if dialog.exec() == QDialog.Accepted else None
        self._note_taken_over(row, dialog)
        dialog.deleteLater()
        if action == "edit":
            self.edit_ticket(row)
        elif action == "close":
            self.close_ticket(row)

    def edit_ticket(self, row=None):
        from ticket_dialogs import EditTicketDialog
        row = row or self.current_row()
        if not row:
            return
        dialog = EditTicketDialog(self.reader, row, self)
        accepted = dialog.exec() == QDialog.Accepted
        self._note_taken_over(row, dialog)
        if accepted and dialog.saved:
            self._note = f"{row['ticket']} gespeichert."
            subject = dialog.saved.get("subject") or row.get("subject", "")
            self._changed.setdefault(row["id"], {})["subject"] = subject
            self.show_category()
        dialog.deleteLater()

    def _note_taken_over(self, row, dialog):
        """Im Fenster übernommen: bis zum Neulesen dich als Bearbeiter zeigen."""
        if getattr(dialog, "taken_over", None) is None:
            return
        self._note = f"{row['ticket']} übernommen."
        changed = self._changed.setdefault(row["id"], {})
        changed["recipient"] = dialog.taken_over or getattr(self.reader, "user_name", "") or row.get("recipient", "")
        if getattr(self.reader, "user_id", ""):
            changed["recipient_id"] = self.reader.user_id
        self.show_category()

    def close_ticket(self, row=None):
        from ticket_dialogs import CloseTicketDialog
        row = row or self.current_row()
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
