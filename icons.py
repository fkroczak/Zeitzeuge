"""Einheitliche Linien-Icons für Werkzeugleiste, Menüs und Infobereich.

Die Formen stammen aus Lucide (https://lucide.dev, ISC-Lizenz). Sie werden in der
Textfarbe des aktuellen Designs gezeichnet, deshalb passen sie zu Hell und Dunkel.
"""
from PyQt5.QtCore import QByteArray, QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer  # explizit importiert, damit PyInstaller QtSvg einpackt

PATHS = {
    "prev": '<path d="m15 18-6-6 6-6"/>',
    "next": '<path d="m9 18 6-6-6-6"/>',
    "today": '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>'
             '<path d="m9 16 2 2 4-4"/>',
    "refresh": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>'
               '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "zoom_in": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35M11 8v6M8 11h6"/>',
    "zoom_out": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35M8 11h6"/>',
    "whole_day": '<path d="m18 8 4 4-4 4M6 8l-4 4 4 4M2 12h20"/>',
    "work_time": '<path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>'
                 '<rect width="20" height="14" x="2" y="6" rx="2"/>',
    "monitor": '<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8M12 17v4"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "palette": '<circle cx="13.5" cy="6.5" r="1"/><circle cx="17.5" cy="10.5" r="1"/>'
               '<circle cx="8.5" cy="7.5" r="1"/><circle cx="6.5" cy="12.5" r="1"/>'
               '<path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.93 0 1.65-.75 1.65-1.69 0-.44-.18-.84-.44-1.13'
               '-.29-.29-.44-.65-.44-1.13a1.64 1.64 0 0 1 1.67-1.67h2c3.05 0 5.55-2.5 5.55-5.55'
               'C21.97 6.01 17.46 2 12 2z"/>',
    "plug": '<path d="M12 22v-5M9 8V2M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z"/>',
    "folder": '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4'
              'a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "power": '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>',
    "window": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 8h20M6 4v4M10 4v4"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "pause": '<rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/>',
    "record": '<path d="M2.06 12.35a1 1 0 0 1 0-.7 10.75 10.75 0 0 1 19.88 0 1 1 0 0 1 0 .7 10.75 10.75 0 0 1-19.88 0"/>'
              '<circle cx="12" cy="12" r="3"/>',
    "copy": '<rect width="14" height="14" x="8" y="8" rx="2"/>'
            '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "details": '<path d="M3 12h.01M3 18h.01M3 6h.01M8 12h13M8 18h13M8 6h13"/>',
    "tag": '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.42l8.7 8.7a2.43 2.43 0 0 0 3.42 0'
           'l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="1"/>',
}


def icon(name, color):
    """Icon in der Farbe color (z. B. Textfarbe des Designs), scharf auch bei 200 % Anzeige."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{QColor(color).name()}" stroke-width="2" stroke-linecap="round" '
           f'stroke-linejoin="round">{PATHS[name]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    result = QIcon()
    for size in (16, 20, 24, 32, 48):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        result.addPixmap(pix)
    return result


def _draw_state(painter, x, y, r, active):
    """Grüner Punkt = Aufzeichnung läuft, grauer Punkt mit Pause-Zeichen = pausiert.

    Das Pause-Zeichen sorgt dafür, dass der Zustand nicht nur an der Farbe hängt.
    """
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#1F9D55" if active else "#6B7280"))
    painter.drawEllipse(QRectF(x, y, r, r))
    if not active:
        painter.setBrush(QColor("#FFFFFF"))
        w, h = r * 0.14, r * 0.46
        painter.drawRect(QRectF(x + r * 0.30, y + (r - h) / 2, w, h))
        painter.drawRect(QRectF(x + r * 0.56, y + (r - h) / 2, w, h))


def with_badge(base_icon, active, size=64):
    """App-Symbol mit Zustandspunkt unten rechts (für den Infobereich)."""
    pix = base_icon.pixmap(size, size)
    painter = QPainter(pix)
    r = size * 0.42
    x = y = size - r - 1
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawEllipse(QRectF(x - 2, y - 2, r + 4, r + 4))
    _draw_state(painter, x, y, r, active)
    painter.end()
    return QIcon(pix)


def state_dot(active, size=32):
    """Nur der Zustandspunkt (für die Statuszeile)."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    _draw_state(painter, size * 0.1, size * 0.1, size * 0.8, active)
    painter.end()
    result = QIcon(pix)
    result.addPixmap(pix, QIcon.Disabled)  # auch in der (deaktivierten) Statuszeile des Menüs farbig
    return result
