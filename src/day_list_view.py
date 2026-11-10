"""Tagesliste als Modell und Ansicht (statt QTableWidget mit einem Objekt je Zelle).

Die Liste bekommt nur die Einträge und eine Funktion, die aus einem Eintrag die Zellen macht.
Qt fragt Zeilen erst ab, wenn sie sichtbar sind oder für die Spaltenbreite gemessen werden;
erst dann wird die Zeile aufbereitet (und gemerkt). Bei vollem PC-Verlauf (Tausende Fenster)
fällt so fast die ganze Arbeit beim Füllen weg.

Für bestehenden Code und Tests bietet DayListView die gewohnten Teile von QTableWidget:
rowCount(), columnCount(), item(r, c).text()/.toolTip(), currentRow(), cellDoubleClicked.
"""
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import QStyleOptionViewItem, QTableView


def _role(r):
    return r.value if hasattr(r, "value") else int(r)


# Qt fragt jede Zelle nach vielen Rollen (beim Messen der Spaltenbreite Tausende Male).
# Vergleiche mit Qt.DisplayRole … sind in PySide6 teuer: Rolle als Zahl -> Platz in der Zelle.
_SLOT = {_role(Qt.DisplayRole): 0, _role(Qt.ToolTipRole): 1, _role(Qt.DecorationRole): 2,
         _role(Qt.TextAlignmentRole): 3}


class Cell(tuple):
    """Eine Zelle: (Text, Hinweis, Symbol, Ausrichtung), lesbar wie QTableWidgetItem."""
    __slots__ = ()

    def __new__(cls, text, tip=None, icon=None, align=None):
        return super().__new__(cls, (text, text if tip is None else tip, icon, align))

    def text(self):
        return self[0]

    def toolTip(self):
        return self[1]

    def icon(self):
        return self[2]

    def textAlignment(self):
        return self[3]


class DayListModel(QAbstractTableModel):
    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self.headers = list(headers)
        self.header_align = {}  # Spalte -> Ausrichtung im Spaltenkopf
        self.entries = []
        self.make_row = None    # Eintrag -> [Cell, …]
        self._rows = {}         # Zeile -> [Cell, …], erst bei Bedarf aufbereitet

    def set_entries(self, entries, make_row):
        self.beginResetModel()
        self.entries, self.make_row, self._rows = list(entries), make_row, {}
        self.endResetModel()

    def cells(self, row):
        cells = self._rows.get(row)
        if cells is None:
            cells = self._rows[row] = self.make_row(self.entries[row])
        return cells

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=0):
        slot = _SLOT.get(role if role.__class__ is int else _role(role))
        if slot is None:
            return None
        row = index.row()
        cells = self._rows.get(row)
        if cells is None:
            if not 0 <= row < len(self.entries):
                return None
            cells = self._rows[row] = self.make_row(self.entries[row])
        return cells[index.column()][slot]

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal or not 0 <= section < len(self.headers):
            return None
        if role == Qt.DisplayRole:
            return self.headers[section]
        if role == Qt.TextAlignmentRole:
            return self.header_align.get(section)
        return None


class DayListView(QTableView):
    """Tabelle der Tagesliste. Doppelklick meldet (Zeile, Spalte) wie bei QTableWidget."""
    cellDoubleClicked = Signal(int, int)

    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self.setObjectName("day_list")  # Stylesheet wie QTableWidget (theme.py)
        self.list_model = DayListModel(headers, self)
        self.setModel(self.list_model)
        self.doubleClicked.connect(lambda index: self.cellDoubleClicked.emit(index.row(), index.column()))

    # Spalten, deren Breite set_entries an den Inhalt anpasst (Rest: Nutzer oder Stretch)
    fit_columns = ()
    FIT_ROWS = 1000  # wie Qt beim Anpassen an den Inhalt: höchstens so viele Zeilen ansehen

    def set_entries(self, entries, make_row):
        self.list_model.set_entries(entries, make_row)
        self.fit_widths()

    def fit_widths(self):
        """Breite der fit_columns an den Inhalt anpassen.

        Statt Qt alle Zellen messen zu lassen (jede Abfrage ein Sprung nach Python, bei
        200 Zeilen über 100.000): je Spalte die Zeile mit dem breitesten Text suchen und
        nur diese eine Zelle von Qt messen lassen (Symbol, Abstände, Stylesheet inklusive)."""
        model, header = self.list_model, self.horizontalHeader()
        if not self.fit_columns:
            return
        metrics = self.fontMetrics()
        widest = {}
        for row in range(min(len(model.entries), self.FIT_ROWS)):
            cells = model.cells(row)
            for col in self.fit_columns:
                width = metrics.horizontalAdvance(cells[col][0])
                if width > widest.get(col, (-1, 0))[0]:
                    widest[col] = (width, row)
        option = QStyleOptionViewItem()
        self.initViewItemOption(option)
        delegate = self.itemDelegate()
        for col in self.fit_columns:
            width = header.sectionSizeHint(col)
            if col in widest:
                option_col = QStyleOptionViewItem(option)
                width = max(width, delegate.sizeHint(option_col, model.index(widest[col][1], col)).width())
            header.resizeSection(col, width)

    def set_header_alignment(self, column, alignment):
        self.list_model.header_align[column] = alignment

    def rowCount(self):
        return self.list_model.rowCount()

    def columnCount(self):
        return self.list_model.columnCount()

    def item(self, row, column):
        if 0 <= row < self.rowCount() and 0 <= column < self.columnCount():
            return self.list_model.cells(row)[column]
        return None

    def currentRow(self):
        index = self.currentIndex()
        return index.row() if index.isValid() else -1

    def visualItemRect(self, item):
        """Rechteck einer Zelle (für Bildschirmfotos); item aus item(r, c)."""
        for row, cells in self.list_model._rows.items():
            for column, cell in enumerate(cells):
                if cell is item:
                    return self.visualRect(self.list_model.index(row, column))
        return self.visualRect(QModelIndex())
