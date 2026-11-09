"""Schematisches Zeitzeuge-Fenster im Dialog „Eigene Farben“.

Zeigt Kopfleiste, Timeline und Tagesliste in den gewählten Farben (theme.custom_theme).
Ein Klick auf einen Bereich wählt die passende Grundfarbe (theme.CUSTOM_KEYS) zum Ändern.
Die Farben der Balken sind fest (Beispiel), sie hängen nicht vom Design ab.
"""
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from theme import CUSTOM_KEYS, custom_theme, ui_font

# Zeichenfläche in festen Einheiten, wird aufs Widget skaliert
W, H = 640, 330
NAMES = dict(CUSTOM_KEYS)

# Beispielbalken der Timeline: (Zeile, Start, Ende in Einheiten ab Zeitachse, Farbe)
BARS = [(0, 0, 70, "#2F6FDE"), (0, 74, 150, "#2E9E5B"), (0, 154, 230, "#2F6FDE"), (0, 300, 400, "#7C4DCC"),
        (1, 10, 60, "#2E9E5B"), (1, 250, 330, "#2E9E5B"),
        (2, 40, 46, "#1E63D0"), (2, 200, 214, "#E67E22"),
        (3, 70, 150, "#C08A10"), (3, 300, 360, "#C08A10")]
ROWS = ["PC-Aktivität", "Dokumentation", "Telefon", "Remote"]


class ThemeMockup(QWidget):
    """Klickbare Skizze des Hauptfensters. Signal picked(Schlüssel) beim Klick auf einen Bereich."""

    picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.colors = {}
        self._hover = None
        self._areas = []  # (Rechteck in Einheiten, Schlüssel), spezifischste zuerst
        self.setMouseTracking(True)
        self.setMinimumSize(580, 300)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("Vorschau des Designs. Klick auf einen Bereich ändert seine Farbe.")

    def set_colors(self, colors):
        self.colors = dict(colors)
        self.update()

    def sizeHint(self):
        return QSize(W, H)

    # ---- Abbildung Widget ↔ Einheiten

    def _scale(self):
        s = min(self.width() / W, self.height() / H)
        return s, (self.width() - W * s) / 2, (self.height() - H * s) / 2

    def key_at(self, pos):
        s, dx, dy = self._scale()
        p = QPointF((pos.x() - dx) / s, (pos.y() - dy) / s)
        for rect, key in self._areas:
            if rect.contains(p):
                return key
        return None

    # ---- Maus

    def mouseMoveEvent(self, event):
        key = self.key_at(event.position())
        if key != self._hover:
            self._hover = key
            self.update()
        if key:
            QToolTip.showText(event.globalPosition().toPoint(), f"{NAMES[key]} – klicken zum Ändern", self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        key = self.key_at(event.position())
        if key and event.button() == Qt.LeftButton:
            self.picked.emit(key)

    # ---- Zeichnen

    def paintEvent(self, _event):
        t = custom_theme(self.colors)
        c = {k: QColor(v) for k, v in t.items()}
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s, dx, dy = self._scale()
        p.translate(dx, dy)
        p.scale(s, s)
        areas = []

        def box(rect, fill, radius=0, border=None):
            p.setPen(QPen(border, 1) if border is not None else Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(rect, radius, radius)

        def text(x, y, value, color, size=8, bold=False, key=None):
            font = ui_font(size, bold)
            p.setFont(font)
            p.setPen(color)
            width = p.fontMetrics().horizontalAdvance(value)
            rect = QRectF(x, y, width, p.fontMetrics().height())
            p.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, value)
            if key:
                areas.append((rect.adjusted(-3, -2, 3, 2), key))

        # Fenster mit Hintergrund
        window = QRectF(0.5, 0.5, W - 1, H - 1)
        box(window, c["bg"], 8, c["border"])
        # Kopfleiste
        band = QRectF(1, 1, W - 2, 34)
        box(band, c["band"], 7)
        box(QRectF(1, 20, W - 2, 15), c["band"])
        text(14, 9, "Zeitzeuge", c["bandtext"], 9, True)
        for i, label in enumerate(("Heute", "Ansicht", "Einstellungen")):
            text(110 + i * 72, 10, label, c["bandtext"])
        box(QRectF(W - 160, 9, 146, 17), c["bg"], 8.5, c["border"])
        text(W - 150, 10, "Suchen …", c["muted"], 7)
        areas.append((band, "band"))

        # Zeile mit Datum und Schalter
        text(16, 46, "Mittwoch, 21. Oktober", c["text"], 9, True, "text")
        text(160, 48, "6:45 h erfasst · 2 offen", c["muted"], 7)
        sw = QRectF(W - 120, 46, 28, 15)
        box(sw, c["accent"], 7.5)
        box(QRectF(sw.right() - 13, sw.top() + 2, 11, 11), c["onaccent"], 5.5)
        areas.append((sw.adjusted(-2, -2, 2, 2), "accent"))
        text(W - 86, 47, "Aufzeichnung", c["text"], 7, key="text")

        # Timeline-Karte
        tl = QRectF(14, 70, W - 28, 128)
        box(tl, c["surface"], 6, c["border"])
        left = tl.left() + 92
        for i in range(6):
            x = left + 20 + i * 80
            p.setPen(QPen(c["border"], 1))
            p.drawLine(QPointF(x, tl.top() + 22), QPointF(x, tl.bottom() - 6))
            text(x - 13, tl.top() + 5, f"{8 + i * 2:02d}:00", c["muted"], 7)
        for row, name in enumerate(ROWS):
            y = tl.top() + 28 + row * 24
            text(tl.left() + 10, y + 2, name, c["text"], 7, True, "text")
        for row, a, b, color in BARS:
            y = tl.top() + 28 + row * 24
            box(QRectF(left + a, y, b - a, 16), QColor(color), 3)
        now = left + 360
        p.setPen(QPen(c["now"], 1.5))
        p.drawLine(QPointF(now, tl.top() + 20), QPointF(now, tl.bottom() - 4))

        # Tagesliste
        ls = QRectF(14, 208, W - 28, 108)
        box(ls, c["surface"], 6, c["border"])
        cols = (12, 62, 112, 232, 420)
        for x, label in zip(cols, ("Von", "Bis", "Typ", "Kunde", "Details")):
            text(ls.left() + x, ls.top() + 6, label, c["muted"], 7, True)
        p.setPen(QPen(c["border"], 1))
        p.drawLine(QPointF(ls.left() + 1, ls.top() + 24), QPointF(ls.right() - 1, ls.top() + 24))
        rows = [("08:05", "08:09", "Telefonat", "Kanzlei Schmidt", "Eingehend"),
                ("08:12", "08:58", "TeamViewer", "Müller GmbH", "2 Verbindungen"),
                ("09:02", "09:58", "RDP", "Kanzlei Schmidt", "DC01")]
        for i, values in enumerate(rows):
            y = ls.top() + 28 + i * 25
            selected = i == 1
            if selected:
                sel = QRectF(ls.left() + 4, y - 2, ls.width() - 8, 22)
                box(sel, c["sel"], 4)
                box(QRectF(sel.left(), sel.top() + 4, 3, 14), c["accent"], 1.5)
                areas.append((QRectF(sel.left() - 2, sel.top(), 8, sel.height()), "accent"))
            color = c["seltext"] if selected else c["text"]
            for x, value in zip(cols, values):
                text(ls.left() + x, y + 1, value, color, 7, key="text")
            if selected:
                areas.append((sel, "accent"))

        # Reihenfolge: spezifisch vor allgemein
        areas += [(tl, "surface"), (ls, "surface"), (window, "bg")]
        self._areas = areas

        # Markierung unter der Maus
        if self._hover:
            p.setBrush(Qt.NoBrush)
            pen = QPen(c["accent"] if self._hover != "accent" else c["text"], 2, Qt.DashLine)
            p.setPen(pen)
            for rect, key in areas:
                if key == self._hover:
                    p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 5, 5)
        p.end()
