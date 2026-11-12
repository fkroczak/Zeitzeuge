"""Kleine Skelett-Bilder für die Kacheln auf der Seite „Darstellung“ (settings_window.py).

Nur Umrisse und Balken, keine Texte: Design (Hell, Dunkel, Wie Windows, Eigene Farben),
Timeline beim Start, PC-Aktivität, Hervorhebung unter der Maus, PC-Verlauf in der Liste und die Ansichten der Tagesliste.
Farben kommen aus den Tokens des Designs (theme.py); die Design-Kacheln zeigen jeweils ihr
eigenes Design. preview(key, value, tokens) gibt ein QPixmap in 96 × 60 (doppelt aufgelöst).
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient

import theme

W, H = 96, 60


def _color(value, alpha=None):
    color = QColor(value)
    if alpha is not None:
        color.setAlpha(alpha)
    return color


class _Sketch:
    def __init__(self, tokens):
        self.t = tokens
        self.pixmap = QPixmap(W * 2, H * 2)
        self.pixmap.setDevicePixelRatio(2)
        self.pixmap.fill(Qt.transparent)
        self.p = QPainter(self.pixmap)
        self.p.setRenderHint(QPainter.Antialiasing)

    def frame(self, tokens=None):
        t = tokens or self.t
        self.p.setPen(QPen(_color(t["border"]), 1))
        self.p.setBrush(_color(t["bg"]))
        self.p.drawRoundedRect(QRectF(0.5, 0.5, W - 1, H - 1), 6, 6)

    def bar(self, x, y, w, h, color, radius=1.5):
        self.p.setPen(Qt.NoPen)
        self.p.setBrush(color)
        self.p.drawRoundedRect(QRectF(x, y, w, h), radius, radius)

    def outline(self, x, y, w, h, color, radius=2, dashed=False):
        pen = QPen(color, 1)
        if dashed:
            pen.setDashPattern([2, 1.5])
        self.p.setPen(pen)
        self.p.setBrush(Qt.NoBrush)
        self.p.drawRoundedRect(QRectF(x, y, w, h), radius, radius)

    def dot(self, x, y, r, color):
        self.p.setPen(Qt.NoPen)
        self.p.setBrush(color)
        self.p.drawEllipse(QPointF(x, y), r, r)

    def muted(self, alpha=150):
        return _color(self.t["muted"], alpha)

    def done(self):
        self.p.end()
        return self.pixmap


def _window(s, t):
    """Kleines Hauptfenster in den Farben eines Designs: Kopfleiste, Timeline, Liste."""
    s.frame(t)
    s.bar(1, 1, W - 2, 9, _color(t["band"]), 5)
    s.bar(6, 4, 14, 3, _color(t["bandtext"], 150))
    for y, h in ((14, 18), (36, 19)):
        s.p.setPen(QPen(_color(t["border"]), 1))
        s.p.setBrush(_color(t["surface"]))
        s.p.drawRoundedRect(QRectF(6, y, W - 12, h), 3, 3)
    s.bar(10, 18, 22, 4, _color(t["accent"]))
    s.bar(36, 18, 14, 4, _color(t["good"]))
    s.bar(54, 24, 26, 4, _color(t["rate_value_mid"]))
    for i in range(3):
        s.bar(10, 40 + i * 5, 50 - i * 8, 2.5, _color(t["muted"], 140))


def _theme(value, tokens, custom_colors=None):
    s = _Sketch(tokens)
    if value == "system":  # Wie Windows: links hell, rechts dunkel
        for name, path in (("light", [(0, 0), (62, 0), (34, H), (0, H)]),
                           ("dark", [(62, 0), (W, 0), (W, H), (34, H)])):
            clip = QPainterPath()
            clip.moveTo(*path[0])
            for point in path[1:]:
                clip.lineTo(*point)
            clip.closeSubpath()
            s.p.save()
            s.p.setClipPath(clip)
            _window(s, theme.THEMES[name])
            s.p.restore()
    elif value == "custom":
        _window(s, theme.custom_theme(custom_colors) if custom_colors else theme.THEMES["light"])
    else:
        _window(s, theme.THEMES[value])
    return s.done()


def _grid(s):
    for i in range(9):
        s.bar(8 + i * 10, 8, 0.8, 44, _color(s.t["border"]), 0)


def _timeline_range(value, tokens):
    s = _Sketch(tokens)
    s.frame()
    t = s.t
    accent, good, mid = _color(t["accent"]), _color(t["good"]), _color(t["rate_value_mid"])
    if value == "day":  # ganzer Tag: Nacht links und rechts grau, Arbeit schmal in der Mitte
        s.bar(1, 1, 26, H - 2, _color(t["border"], 130), 0)
        s.bar(W - 27, 1, 26, H - 2, _color(t["border"], 130), 0)
        _grid(s)
        rows = [(30, 14, 10, accent), (42, 14, 8, good), (52, 14, 9, mid), (32, 26, 15, s.muted()),
                (50, 26, 10, s.muted()), (34, 38, 8, _color(t["accent"], 170)), (46, 38, 12, _color(t["good"], 170))]
    else:  # Arbeitszeit: Balken über die ganze Breite
        _grid(s)
        rows = [(8, 14, 30, accent), (42, 14, 22, good), (66, 14, 22, mid), (14, 26, 40, s.muted()),
                (58, 26, 26, s.muted()), (20, 38, 18, _color(t["accent"], 170)), (50, 38, 30, _color(t["good"], 170))]
    for x, y, w, color in rows:
        s.bar(x, y, w, 7, color)
    return s.done()


def _pc_blocks(value, tokens):
    s = _Sketch(tokens)
    s.frame()
    t = s.t
    if value == "on":  # Arbeitsblöcke: wenige breite Blöcke
        for x, w, key in ((8, 30, "accent"), (40, 18, "good"), (60, 28, "rate_value_mid")):
            s.bar(x, 12, w, 12, _color(t[key]), 3)
    else:  # jedes Fenster: viele schmale Streifen
        colors = [t["accent"], t["good"], t["rate_value_mid"], t["muted"], t["now"]]
        x, i = 8, 0
        while x < 86:
            w = (3, 5, 2, 7, 4, 2, 6)[i % 7]
            s.bar(x, 12, w, 12, _color(colors[i % 5]), 0.6)
            x, i = x + w + 1, i + 1
    s.bar(8, 32, 50, 3, s.muted(130))
    s.bar(8, 40, 36, 3, s.muted(130))
    return s.done()


def _pc_list(value, tokens):
    s = _Sketch(tokens)
    s.frame()
    for i in range(5):
        pc = value == "on" and i % 2 == 1  # PC-Verlauf: zusätzliche, blassere Zeilen
        s.bar(8, 9 + i * 9, 8, 4, _color(s.t["muted"] if pc else s.t["accent"]))
        s.bar(20, 9 + i * 9, 50 - (i % 2) * 12, 4, s.muted(80 if pc else 150))
    return s.done()


def _list_view(value, tokens):
    s = _Sketch(tokens)
    s.frame()
    t = s.t
    text = s.muted()
    if value == "single":
        for i in range(9):
            s.bar(8, 7 + i * 5.2, 66 - (i % 4) * 9, 2.4, text)
    elif value == "blocks":
        for y, key in ((8, "accent"), (32, "good")):
            s.bar(8, y, 80, 6, _color(t[key], 90), 2)
            s.bar(14, y + 10, 50, 3, text)
            s.bar(14, y + 16, 40, 3, text)
    elif value == "calls":
        for i in range(5):
            s.dot(11, 11 + i * 9, 2.6, _color(t["now"] if i == 2 else t["good"]))
            s.bar(18, 9 + i * 9, 46 - (i % 2) * 10, 4, text)
    elif value == "doc":
        for i in range(3):
            s.bar(8, 8 + i * 16, 2.5, 12, _color(t["accent"]), 1)
            s.bar(14, 8 + i * 16, 56, 3.5, _color(t["text"], 200))
            s.bar(14, 14 + i * 16, 40, 3, s.muted(130))
    elif value == "rules":
        for i in range(5):
            s.bar(8, 9 + i * 9, 44 - (i % 2) * 10, 4, text)
            s.bar(60, 8 + i * 9, 26, 6, _color(t["sel"]), 3)
    elif value == "ai":
        for i in range(4):
            s.outline(8, 8 + i * 11, 80, 8, _color(t["accent"]), dashed=True)
            s.bar(12, 11 + i * 11, 40 - (i % 2) * 10, 2.5, text)
    elif value == "m42":
        s.bar(48, 6, 0.8, 48, _color(t["border"]), 0)
        for i in range(5):
            s.bar(8, 9 + i * 9, 32, 4, text)
            if i == 3:
                s.dot(85, 11 + i * 9, 2.6, _color(t["now"]))
                continue
            s.bar(54, 9 + i * 9, 24, 4, text)
            s.p.setPen(QPen(_color(t["good"]), 1.6))
            s.p.drawPolyline([QPointF(82, 11 + i * 9), QPointF(84, 13 + i * 9), QPointF(88, 9 + i * 9)])
    else:  # zusammengefasst: Zeilen mit Zahl
        for i in range(5):
            s.bar(8, 9 + i * 9, 54 - (i % 3) * 8, 4, text)
            s.bar(76, 8 + i * 9, 12, 6, _color(t["chip"]), 3)
    return s.done()


def _hover(value, tokens):
    """Drei Zeilen Balken, der mittlere unter der Maus: so stark Nebel, Lichtkegel und Leuchten."""
    from timeline_only import HOVER_STYLES, HOVER_DEFAULT
    s = _Sketch(tokens)
    s.frame()
    t = s.t
    colors = [t["accent"], t["good"], t["rate_value_mid"]]
    bars = [(8, 12, 22, 0), (34, 12, 14, 1), (52, 12, 30, 2), (10, 26, 18, 1), (40, 26, 22, 0),
            (66, 26, 18, 2), (14, 40, 26, 2), (46, 40, 16, 0), (66, 40, 20, 1)]
    for x, y, w, c in bars:
        s.bar(x, y, w, 8, _color(colors[c]), 2)
    style = HOVER_STYLES.get(value if value != "custom" else HOVER_DEFAULT)
    focus = QRectF(40, 26, 22, 8)
    if style:
        alpha = round(style["fog"] * 2.55)
        if alpha:
            if style["cone"]:
                radius = 11 + style["cone"] / 8
                grad = QRadialGradient(focus.center(), radius)
                grad.setColorAt(0, _color(t["bg"], 0))
                grad.setColorAt(11 / radius, _color(t["bg"], round(alpha * 0.22)))
                grad.setColorAt(1, _color(t["bg"], alpha))
                s.p.setBrush(grad)
            else:
                s.p.setBrush(_color(t["bg"], alpha))
            s.p.setPen(Qt.NoPen)
            s.p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 5, 5)
        for i in range(style["glow"] // 6, 0, -1):  # Leuchten als weiche Ringe
            s.bar(focus.x() - i, focus.y() - i, focus.width() + 2 * i, focus.height() + 2 * i,
                  _color(colors[0], 45), 2 + i)
        s.bar(focus.x(), focus.y(), focus.width(), focus.height(), _color(colors[0]), 2)
        if style["outline"]:
            s.outline(focus.x(), focus.y(), focus.width(), focus.height(), _color(t["text"], 110))
    if value == "custom":  # Regler andeuten
        for i, at in enumerate((0.35, 0.7, 0.5)):
            x0 = 8 + i * 28
            s.bar(x0, 53, 24, 1.5, s.muted(160), 0.75)
            s.dot(x0 + 24 * at, 53.75, 2.4, _color(t["accent"]))
    return s.done()


PAINTERS = {"hover_focus": _hover, "theme": _theme, "timeline_range": _timeline_range, "pc_blocks_action": _pc_blocks,
            "pc_list_action": _pc_list, "list_view": _list_view}


def preview(key, value, tokens, custom_colors=None):
    """Bild für die Kachel value der Einstellung key."""
    if key == "theme":
        return _theme(value, tokens, custom_colors)
    return PAINTERS[key](value, tokens)
