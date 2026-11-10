"""Einheitliche Linien-Icons für Werkzeugleiste, Menüs und Infobereich.

Die Formen stammen aus Lucide (https://lucide.dev, ISC-Lizenz). Sie werden in der
Textfarbe des aktuellen Designs gezeichnet, deshalb passen sie zu Hell und Dunkel.
"""
import re
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer  # explizit importiert, damit PyInstaller QtSvg einpackt

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
    "spark": '<path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5'
             'l1.58-6.14a.5.5 0 0 1 .96 0L14.06 8.5A2 2 0 0 0 15.5 9.94l6.14 1.58a.5.5 0 0 1 0 .96'
             'L15.5 14.06a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0Z"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "power": '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>',
    "pin": '<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12'
           'a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8'
           'a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>',
    "close": '<path d="M18 6 6 18M6 6l12 12"/>',
    "check_mark": '<path d="M20 6 9 17l-5-5"/>',
    "calendar": '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "window": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 8h20M6 4v4M10 4v4"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "pause": '<rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/>',
    "eye": '<path d="M2.06 12.35a1 1 0 0 1 0-.7 10.75 10.75 0 0 1 19.88 0 1 1 0 0 1 0 .7 10.75 10.75 0 0 1-19.88 0"/>'
           '<circle cx="12" cy="12" r="3"/>',
    "record": '<path d="M2.06 12.35a1 1 0 0 1 0-.7 10.75 10.75 0 0 1 19.88 0 1 1 0 0 1 0 .7 10.75 10.75 0 0 1-19.88 0"/>'
              '<circle cx="12" cy="12" r="3"/>',
    "copy": '<rect width="14" height="14" x="8" y="8" rx="2"/>'
            '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "details": '<path d="M3 12h.01M3 18h.01M3 6h.01M8 12h13M8 18h13M8 6h13"/>',
    "tag": '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.42l8.7 8.7a2.43 2.43 0 0 0 3.42 0'
           'l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="1"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "edit": '<path d="M12 20h9"/><path d="M16.38 3.62a1 1 0 0 1 3 3L7.37 18.64a2 2 0 0 1-.85.51'
            'l-2.87.84a.5.5 0 0 1-.62-.62l.84-2.87a2 2 0 0 1 .51-.85z"/>',
    "bell": '<path d="M10.27 21a2 2 0 0 0 3.46 0"/><path d="M3.26 15.33A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.67'
            'C19.41 13.96 18 12.5 18 8A6 6 0 0 0 6 8c0 4.5-1.41 5.96-2.74 7.33"/>',
    "rows": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M21 9H3M21 15H3"/>',
    "filter": '<path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/>',
    "lock": '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "rules": '<path d="m3 17 2 2 4-4M3 7l2 2 4-4M13 6h8M13 12h8M13 18h8"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',  # Wochenabschluss
    "check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',  # Tagesabschluss
    "settings": '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08'
                'a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74'
                'l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73'
                'V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08'
                'a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74'
                'l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25'
                'a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    "help": '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01"/>',
    # Ansichten der Tagesliste
    "layers": '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0'
              'l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65'
              'M22 12.65l-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    "list": '<path d="M3 12h.01M3 18h.01M3 6h.01M8 12h13M8 18h13M8 6h13"/>',
    "blocks": '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/>'
              '<rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
    "doc": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
           '<path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m9 15 2 2 4-4"/>',
    "alert": '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
    "map_pin": '<path d="M20 10c0 4.99-5.54 10.19-7.4 11.8a1 1 0 0 1-1.2 0C9.54 20.19 4 14.99 4 10a8 8 0 0 1 16 0"/>'
               '<circle cx="12" cy="10" r="3"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "sliders": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M2 14h4M10 8h4M18 16h4"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/>'
                '<path d="M3 12a9 3 0 0 0 18 0"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1'
              'c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66'
           'l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
    "trash": '<path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "server": '<rect width="20" height="8" x="2" y="2" rx="2"/><rect width="20" height="8" x="2" y="14" rx="2"/>'
              '<path d="M6 6h.01M6 18h.01"/>',
    "phone": '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6'
             ' 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81'
             ' 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0'
             ' 2.81.7A2 2 0 0 1 22 16.92z"/>',
    # Kundenerkennung (customers_dialogs.py)
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/>'
             '<path d="M2 12h20"/>',
    "type": '<path d="M4 7V4h16v3M9 20h6M12 4v16"/>',
    "network": '<rect x="16" y="16" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/>'
               '<rect x="9" y="2" width="6" height="6" rx="1"/><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"/>'
               '<path d="M12 12V8"/>',
    "wifi": '<path d="M12 20h.01M2 8.82a15 15 0 0 1 20 0M5 12.86a10 10 0 0 1 14 0M8.5 16.43a5 5 0 0 1 7 0"/>',
    "screen_share": '<path d="M13 3H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-3"/>'
                    '<path d="M8 21h8M12 17v4M17 8l5-5M17 3h5v5"/>',
}


def icon(name, color):
    """Icon in der Farbe color (z. B. Textfarbe des Designs), scharf auch bei 200 % Anzeige."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{QColor(color).name()}" stroke-width="2" stroke-linecap="round" '
           f'stroke-linejoin="round">{PATHS[name]}</svg>')
    return _render(svg, (16, 20, 24, 32, 48))


# Farben aus dem Logo: roter "Jetzt"-Punkt = Aufzeichnung läuft, grau = pausiert
ACTIVE_COLOR = "#E5484D"
PAUSED_COLOR = "#7D8590"  # Kontrast >= 3:1 auf heller und dunkler Taskleiste
# Pause-Zeichen im Koordinatensystem des Logos (256 x 256), ersetzt dort den Punkt
PAUSE_BARS = ('<rect x="96" y="86" width="26" height="84" rx="7" fill="{c}"/>'
              '<rect x="134" y="86" width="26" height="84" rx="7" fill="{c}"/>')


def _render(svg, sizes):
    """Gerendertes Icon; gleiches SVG nur einmal rendern (Start, Designwechsel, Einstellungen
    brauchen dieselben Symbole immer wieder, je Icon 5 Pixmaps ≈ 1,5 ms)."""
    return QIcon(_render_cached(svg, sizes))  # Kopie: QIcon ist implizit geteilt, kostet nichts


@lru_cache(maxsize=512)
def _render_cached(svg, sizes):
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    result = QIcon()
    for size in sizes:
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        result.addPixmap(pix)
        result.addPixmap(pix, QIcon.Disabled)  # auch in deaktivierten Menüzeilen farbig
    return result


def tray_icon(logo_svg, active):
    """Logo für den Infobereich. Pausiert: Ring grau, Pause-Zeichen statt rotem Punkt.

    Der Zustand hängt so nicht nur an der Farbe, sondern auch an der Form.
    """
    if not active:
        logo_svg = re.sub(r'stroke="#[0-9A-Fa-f]{6}"', f'stroke="{PAUSED_COLOR}"', logo_svg)
        logo_svg = re.sub(r"<circle[^>]*/>", PAUSE_BARS.format(c=PAUSED_COLOR), logo_svg)
    return _render(logo_svg, (16, 20, 24, 32, 48, 64))


def state_dot(active):
    """Kleiner Zustandspunkt für Statuszeile und Menü, in den Farben des Logos."""
    if active:
        svg = f'<circle cx="128" cy="128" r="80" fill="{ACTIVE_COLOR}"/>'
    else:
        svg = (f'<circle cx="128" cy="128" r="110" fill="{PAUSED_COLOR}"/>'
               + PAUSE_BARS.format(c="#FFFFFF"))
    return _render(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">{svg}</svg>',
                   (16, 20, 24, 32))


# Zustand einer Datenquelle in der Statuszeile. Form UND Farbe: Haken, Dreieck, Uhr.
WARN_FILL, WARN_LINE = "#F5B800", "#6B4E00"   # gelbes Warndreieck mit dunklem Rand
OK_COLOR = "#2E9E5B"
BUSY_COLOR = "#7D8590"


def source_icon(state):
    """state: "ok" (grüner Haken), "warn" (gelbes Dreieck mit !), "busy" (graue Uhr)."""
    if state == "warn":
        svg = (f'<path d="M12 2.5 22.5 21h-21z" fill="{WARN_FILL}" stroke="{WARN_LINE}" '
               'stroke-width="1.6" stroke-linejoin="round"/>'
               f'<path d="M12 9v5.5" stroke="{WARN_LINE}" stroke-width="2.4" stroke-linecap="round"/>'
               f'<circle cx="12" cy="17.7" r="1.4" fill="{WARN_LINE}"/>')
    elif state == "ok":
        svg = (f'<circle cx="12" cy="12" r="10" fill="{OK_COLOR}"/>'
               '<path d="m7.5 12.5 3 3 6-6.5" stroke="#FFFFFF" stroke-width="2.4" fill="none" '
               'stroke-linecap="round" stroke-linejoin="round"/>')
    else:
        svg = (f'<circle cx="12" cy="12" r="9" fill="none" stroke="{BUSY_COLOR}" stroke-width="2"/>'
               f'<path d="M12 7v5l3 2" stroke="{BUSY_COLOR}" stroke-width="2" fill="none" '
               'stroke-linecap="round"/>')
    return _render(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{svg}</svg>',
                   (16, 20, 24, 32))


def dot(color, size=10):
    """Gefüllter Farbpunkt, z. B. für die Zeilen der Timeline im Menü Ansicht."""
    r = size / 2
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
           f'<rect x="{12 - r}" y="{12 - r}" width="{size}" height="{size}" rx="2" '
           f'fill="{QColor(color).name()}"/></svg>')
    return _render(svg, (16, 20, 24, 32))


# Datenquellen: Zeichen in der Hausfarbe des Herstellers (vereinfacht nachgezeichnet, keine
# Original-Logodateien). Schlüssel wie in den Einstellungen.
_BRAND_TEXT = ('<text x="12" y="{y}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" '
               'font-weight="700" font-size="{size}" fill="#FFFFFF">{text}</text>')
BRANDS = {
    # TeamViewer: blauer Kreis mit Doppelpfeil
    "teamviewer": ('#0E8EE9', 'circle',
                   '<path d="M5 12h14M8.5 8.5 5 12l3.5 3.5M15.5 8.5 19 12l-3.5 3.5" stroke="#FFFFFF" '
                   'stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'),
    "rdm": ('#E8412C', 'square', _BRAND_TEXT.format(y=15.5, size=8, text="RDM")),  # Devolutions RDM
    "rdmbetter": ('#B2331F', 'square', _BRAND_TEXT.format(y=15.5, size=8, text="RDM+")),  # RDM Better
    # Remotedesktop (mstsc): Bildschirm mit Pfeil
    "mstsc": ('#0067B8', 'square',
              '<rect x="5" y="6" width="14" height="9.5" rx="1.2" fill="none" stroke="#FFFFFF" '
              'stroke-width="1.8"/><path d="M9.5 19h5M12 15.5V19M9.5 11h5M12.5 9l2 2-2 2" stroke="#FFFFFF" '
              'stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'),
    # SSH / PowerShell: Eingabeaufforderung
    "shell": ('#2B2F36', 'square',
              '<path d="M6 8l4 4-4 4M12 16.5h6" stroke="#FFFFFF" stroke-width="2" fill="none" '
              'stroke-linecap="round" stroke-linejoin="round"/>'),
    # PC gesperrt: Schloss
    "pcstate": ('#4B5563', 'square',
                '<rect x="7" y="11" width="10" height="7.5" rx="1.2" fill="#FFFFFF"/>'
                '<path d="M9 11V9a3 3 0 0 1 6 0v2" stroke="#FFFFFF" stroke-width="1.8" fill="none"/>'),
    # WLAN: Bögen
    "wlan": ('#0EA5A4', 'square',
             '<path d="M5 10.5a10 10 0 0 1 14 0M7.5 13a6.5 6.5 0 0 1 9 0M10 15.5a3 3 0 0 1 4 0" '
             'stroke="#FFFFFF" stroke-width="1.8" fill="none" stroke-linecap="round"/>'
             '<circle cx="12" cy="18" r="1.3" fill="#FFFFFF"/>'),
    # Dateien: Blatt mit Ecke
    "files": ('#D97706', 'square',
              '<path d="M8 5h6l3 3v11H8z" fill="none" stroke="#FFFFFF" stroke-width="1.8" '
              'stroke-linejoin="round"/><path d="M14 5v3h3" fill="none" stroke="#FFFFFF" stroke-width="1.6"/>'),
    # Browser: Globus
    "browser": ('#2563EB', 'circle',
                '<circle cx="12" cy="12" r="6.5" fill="none" stroke="#FFFFFF" stroke-width="1.6"/>'
                '<path d="M5.5 12h13M12 5.5c-2.2 2.2-2.2 10.8 0 13M12 5.5c2.2 2.2 2.2 10.8 0 13" '
                'fill="none" stroke="#FFFFFF" stroke-width="1.4"/>'),
    # Teams-Chat: Sprechblase
    "teamschat": ('#6264A7', 'square',
                  '<path d="M5.5 6.5h13v8.5h-7l-3.5 3v-3h-2.5z" fill="none" stroke="#FFFFFF" '
                  'stroke-width="1.8" stroke-linejoin="round"/>'),
    # Fahrten: Auto
    "travel": ('#B45309', 'square',
               '<path d="M5 15.5v-3l2-4.5h10l2 4.5v3zM5 12.5h14" fill="none" stroke="#FFFFFF" '
               'stroke-width="1.7" stroke-linejoin="round"/><circle cx="8.5" cy="16.5" r="1.5" '
               'fill="#FFFFFF"/><circle cx="15.5" cy="16.5" r="1.5" fill="#FFFFFF"/>'),
    "sophos": ('#005BC8', 'square', _BRAND_TEXT.format(y=17, size=14, text="S")),
    # Fortinet: rotes Feld mit weißem Raster
    "forti": ('#DA291C', 'square',
              ''.join(f'<rect x="{x}" y="{y}" width="4" height="3" fill="#FFFFFF"/>'
                      for x, y in ((5, 6), (10, 6), (15, 6), (5, 10.5), (15, 10.5), (5, 15), (10, 15), (15, 15)))),
    "vpn": ('#0F9D8A', 'square',
            '<path d="M12 5.5 17.5 7.5v4c0 3.4-2.4 5.3-5.5 6.5-3.1-1.2-5.5-3.1-5.5-6.5v-4z" fill="none" '
            'stroke="#FFFFFF" stroke-width="1.8" stroke-linejoin="round"/>'),
    "pbx": ('#00A3E0', 'square', _BRAND_TEXT.format(y=15.5, size=8.5, text="3CX")),
    "itm": ('#1B1F24', 'square', _BRAND_TEXT.format(y=15.5, size=8, text="ITM")),
    "m42": ('#0B2D6B', 'square', _BRAND_TEXT.format(y=16.5, size=11, text="42")),
    "outlook": ('#0F6CBD', 'square', _BRAND_TEXT.format(y=17, size=13, text="O")),
    "teams": ('#5B5FC7', 'square', _BRAND_TEXT.format(y=17, size=13, text="T")),
    "tracking": ('#2F7BFF', 'square',
                 '<rect x="5" y="6" width="14" height="9.5" rx="1.2" fill="none" stroke="#FFFFFF" '
                 'stroke-width="1.8"/><path d="M9.5 19h5M12 15.5V19" stroke="#FFFFFF" stroke-width="1.8" '
                 'stroke-linecap="round"/>'),
}


def brand_icon(key):
    """Zeichen einer Datenquelle (BRANDS), z. B. für Einstellungen und Menü Datenquellen."""
    color, shape, glyph = BRANDS[key]
    ground = (f'<circle cx="12" cy="12" r="11" fill="{color}"/>' if shape == "circle"
              else f'<rect x="1" y="1" width="22" height="22" rx="4.5" fill="{color}"/>')
    return _render(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{ground}{glyph}</svg>',
                   (16, 20, 24, 32, 48))


def check_box(color, on):
    """Kästchen in Farbe color: an = gefüllt mit weißem Haken, aus = nur Rahmen.
    Für Menüs, in denen ein Symbol sonst den Haken verdecken würde."""
    c = QColor(color).name()
    if on:
        body = (f'<rect x="3" y="3" width="18" height="18" rx="3" fill="{c}"/>'
                '<path d="m7.5 12.5 3 3 6-6.5" stroke="#FFFFFF" stroke-width="2.6" fill="none" '
                'stroke-linecap="round" stroke-linejoin="round"/>')
    else:
        body = f'<rect x="4" y="4" width="16" height="16" rx="3" fill="none" stroke="{c}" stroke-width="2"/>'
    return _render(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>',
                   (16, 20, 24, 32))


def check_mark_file(color):
    """Haken als PNG-Datei für das Stylesheet (QCheckBox::indicator braucht eine Datei).

    Liegt im Temp-Ordner, je Farbe eine Datei; gibt den Pfad mit / zurück."""
    import os
    import tempfile
    c = QColor(color).name()
    path = os.path.join(tempfile.gettempdir(), f"zeitzeuge_check_{c[1:]}.png")
    if not os.path.exists(path):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
               f'<path d="m5 12.5 4.5 4.5 9.5-10" stroke="{c}" stroke-width="3" fill="none" '
               'stroke-linecap="round" stroke-linejoin="round"/></svg>')
        _render(svg, (48,)).pixmap(48, 48).save(path, "PNG")
    return path.replace(os.sep, "/")


def app_icon(resource_path):
    """Programmsymbol für Fenster und Taskleiste.

    Aus der .ico und zusätzlich aus PNG/SVG: Fehlt in der EXE das Qt-Plugin für .ico,
    bliebe das Symbol sonst leer und die Taskleiste zeigte kein Logo.
    """
    result = QIcon()
    for name in ("zeitzeuge.ico", "zeitzeuge.png"):
        pix = QPixmap(resource_path(name))
        if not pix.isNull():
            result.addPixmap(pix)
    try:
        with open(resource_path("zeitzeuge.svg"), encoding="utf-8") as f:
            svg = f.read()
        logo = _render(svg, (16, 24, 32, 48, 64, 256))
        for size in logo.availableSizes():
            result.addPixmap(logo.pixmap(size))
    except OSError:
        pass
    return result


def set_windows_app_id():
    """Eigene Kennung für die Windows-Taskleiste: Sonst ordnet Windows das Fenster beim Start
    aus dem Quelltext python.exe zu und zeigt dessen (oder gar kein) Symbol."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Zeitzeuge.Zeitzeuge")
    except (AttributeError, OSError):
        pass
