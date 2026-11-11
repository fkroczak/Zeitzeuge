# timeline_only.py
import sys
import threading
import time
from datetime import datetime
from functools import lru_cache
from html import escape

from PySide6.QtCore import QDate, QDateTime, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QContextMenuEvent, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QFrame, QGraphicsRectItem,
                               QGraphicsScene, QGraphicsView, QLabel, QLineEdit, QMenu,
                               QPlainTextEdit, QScrollArea, QVBoxLayout)

from activity_tracker import app_label, merge_segments, read_segments
import call_import
from call_import import load_call_suggestions
import focus
import travel
import customers
from grouping import format_tv_id, group_entries
from log_parsers import ConnectionIndex, RdmParser, TeamViewerParser, VpnParser
from rdp_reader import RdpReader
from local_sources import BROWSER_TYPE, FILE_TYPE, NET_TYPE, PC_STATE_TYPES, WLAN_TYPE, LocalReader
from theme import contrast, readable_on, theme_for, ui_font
import skeleton
from vpn_reader import VpnReader, drop_unnamed_twins, vpn_sources

TIME_FMT = "%Y-%m-%d %H:%M:%S"


def _parse_time(text):
    if len(text) != 19 or text[10] != " ":
        raise ValueError(f"Ungültige Zeit: {text!r}")
    return datetime.fromisoformat(text)


_parse_time_cached = lru_cache(maxsize=65536)(_parse_time)


def parse_time(text):
    """'JJJJ-MM-TT hh:mm:ss' -> datetime. Streng wie strptime, aber viel schneller.
    Texte werden gemerkt: Beim Zeichnen, im Hinweis und in der Tagesliste kommen dieselben
    Zeiten oft (anderes als Text wie bisher ungemerkt, z. B. aus kaputten Daten)."""
    return _parse_time_cached(text) if type(text) is str else _parse_time(text)


class _RoundRect(QGraphicsRectItem):
    """Balken mit runden Ecken (Design „Companion“). Bleibt ein QGraphicsRectItem,
    damit Treffer, Hinweis und Auswahl wie bisher über rect() laufen."""

    RADIUS = 4.0

    def paint(self, painter, option, widget=None):
        r = self.rect()
        radius = min(self.RADIUS, r.width() / 2, r.height() / 2)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRoundedRect(r, radius, radius)


def _first_line(text):
    """Erste nicht-leere Zeile: Balken-Beschriftungen sind einzeilig, sonst laufen
    mehrzeilige Beschreibungen über die Zeilen darunter."""
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _to_min(text):
    h, m = text.strip().split(":")
    return int(h) * 60 + int(m)


def work_hours(config, weekday):
    """Arbeitszeit (Start, Ende) in Minuten für einen Wochentag (0 = Montag), None = frei."""
    days = config.get("work_days")
    try:
        if days is None:  # alte Config: work_start/work_end für Mo–Fr
            if weekday >= 5:
                return None
            return _to_min(config.get("work_start", "08:00")), _to_min(config.get("work_end", "17:00"))
        text = days.get(WEEKDAYS[weekday], "")
        if not text:
            return None
        start, end = text.split("-")
        return _to_min(start), _to_min(end)
    except (AttributeError, ValueError):
        return None


def work_break(config, weekday):
    """Pause (Start, Ende) in Minuten für einen Wochentag, None = keine."""
    try:
        text = (config.get("work_breaks") or {}).get(WEEKDAYS[weekday], "")
        if not text:
            return None
        start, end = text.split("-")
        start, end = _to_min(start), _to_min(end)
        return (start, end) if end > start else None
    except (AttributeError, ValueError):
        return None


def work_spans(config, weekday):
    """Arbeitszeit eines Wochentags als [(Start, Ende)] in Minuten, ohne die Pause."""
    hours = work_hours(config, weekday)
    if not hours:
        return []
    pause = work_break(config, weekday)
    if not pause or pause[1] <= hours[0] or pause[0] >= hours[1]:
        return [hours]
    return [(a, b) for a, b in ((hours[0], pause[0]), (pause[1], hours[1])) if b > a]


# Farben für Telefonate wie im 3CX-Client (in der Config unter "call_colors" änderbar)
# Eingehend blau, ausgehend orange: unterscheiden sich auch in der Helligkeit, nicht nur im Farbton.
# Dazu ein Pfeil im Balken (CALL_MARKS), damit es nicht nur an der Farbe hängt.
DEFAULT_CALL_COLORS = {"Eingehend": "#1F5FD6", "Ausgehend": "#F08A24", "Verpasst": "#E5484D"}
CALL_MARKS = {"Eingehend": "↙", "Ausgehend": "↗", "Verpasst": "✕"}


def _blend(fill, background):
    """Farbe, die eine halb durchsichtige Füllung auf dem Hintergrund ergibt."""
    a = fill.alpha() / 255
    return QColor(*(round(getattr(fill, c)() * a + getattr(background, c)() * (1 - a))
                    for c in ("red", "green", "blue")))


def entry_color(activity, config):
    """Farbe eines Eintrags: eigene Farbe der Zeile (config["row_colors"]), sonst
    Telefonate nach Richtung und alles andere nach Aktivitätstyp."""
    own = (config.get("row_colors") or {}).get(row_of(activity))
    if own:
        return QColor(own)
    direction = activity.get("direction")
    if direction:
        colors = {**DEFAULT_CALL_COLORS, **config.get("call_colors", {})}
        if direction in colors:
            return QColor(colors[direction])
    return QColor(config.get("type_colors", {}).get(activity.get("type"), "#4682B4"))


# Eigene Zeile je Quelle (Kennung, Beschriftung links); nur RDM und der Rest teilen sich mehrere Spuren
# Outlook (Termine, Mails) nur, wenn die Datenquelle an ist (sonst bliebe die Zeile leer)
FIXED_ROWS = [("call", "Tel"), ("outlook", "Outlook"), ("vpn", "VPN"), ("tv", "TV"),
              ("pcstate", "PC-Zustand"), ("wlan", "Netz"), ("files", "Dateien")]
OUTLOOK_TYPES = ("Termin", "Teams-Besprechung", "Mail gesendet", "Mail beantwortet", "Teams-Chat")
# Legende links: Name der Zeile und Schlüssel in config["type_colors"] für das Farbfeld
LEGEND_FIXED = {"call": ("Telefon", "Telefonat"), "outlook": ("Outlook", "Termin"),
                "vpn": ("VPN", "VPN-Verbindung"),
                "tv": ("TeamViewer", "TeamViewer"),
                "pcstate": ("PC-Zustand", "PC gesperrt"), "wlan": ("Netzwerk", "Netzwerk"),
                "files": ("Dateien & Web", "Datei geöffnet")}
LEGEND_BANDS = {"work": ("Personalzeit", "Personalzeit"), "doc": ("Dokumentation", "Dokumentiert"), "m42": ("Matrix42", "Matrix42-Buchung"),
                "rule": ("Zuordnung o. KI", "Klassifizierung"), "ai": ("KI-Vorschläge", "KI-Vorschlag")}

# Alle Zeilen der Timeline in der Reihenfolge von oben nach unten: Schlüssel in
# config["timeline_rows"], Text im Menü. Jede lässt sich einzeln aus- und einblenden.
TIMELINE_ROWS = [
    ("pc", "&PC-Aktivität (aktive Fenster)"),
    ("work", "P&ersonalzeit (aus der Zeiterfassung)"),
    ("doc", "&Dokumentation (eigene Tätigkeiten)"),
    ("m42", "&Matrix42 (gebucht / nicht gebucht)"),
    ("rule", "&Zuordnung ohne KI (feste Regeln)"),
    ("ai", "&KI-Vorschläge"),
    ("call", "&Telefon (3CX, Teams)"),
    ("outlook", "&Outlook (Termine, Mails)"),
    ("vpn", "&VPN"),
    ("tv", "T&eamViewer"),
    ("pcstate", "PC-&Zustand (gesperrt, Ruhezustand)"),
    ("wlan", "&Netzwerk (WLAN, Kabel)"),
    ("files", "Dateien und &Browser"),
    ("other", "&Remote / Weitere (RDM, SSH, RDP …)"),
]
ROW_NAMES = {"pc": "PC-Aktivität", "work": "Personalzeit", "doc": "Dokumentation", "m42": "Matrix42", "rule": "Zuordnung ohne KI",
             "ai": "KI-Vorschläge", "call": "Telefon", "outlook": "Outlook", "vpn": "VPN", "tv": "TeamViewer",
             "pcstate": "PC-Zustand", "wlan": "Netzwerk", "files": "Dateien & Web", "other": "Remote / Weitere"}


# Zeilen, die sich in der Legende verschieben lassen (PC-Aktivität bleibt oben, Remote / Weitere unten)
MOVABLE_ROWS = ["work", "doc", "m42", "rule", "ai"] + [k for k, _l in FIXED_ROWS]


def row_order(config):
    """Reihenfolge der verschiebbaren Zeilen: gespeicherte zuerst, neue Zeilen an ihrem Standardplatz."""
    saved = [k for k in config.get("timeline_row_order") or [] if k in MOVABLE_ROWS]
    order = list(dict.fromkeys(saved))
    for i, key in enumerate(MOVABLE_ROWS):
        if key not in order:  # hinter ihren Vorgänger aus der Standardreihenfolge
            after = next((k for k in reversed(MOVABLE_ROWS[:i]) if k in order), None)
            order.insert(order.index(after) + 1 if after else 0, key)
    return order


def moved(order, key, target, below):
    """Reihenfolge, nachdem key vor (below=False) oder hinter target gezogen wurde."""
    order = [k for k in order if k != key]
    if target not in order:
        return order + [key]
    i = order.index(target) + (1 if below else 0)
    return order[:i] + [key] + order[i:]


def row_kind(activity):
    """Feste Zeile eines Eintrags ("call", "outlook", "vpn", "tv") oder None für die freien Spuren."""
    kind = activity.get("type", "")
    if activity.get("direction") or kind == "Telefonat":
        return "call"
    if kind in OUTLOOK_TYPES or kind == travel.TYPE:  # Fahrten stehen neben ihrem Termin
        return "outlook"
    if kind.startswith("VPN"):
        return "vpn"
    if kind.startswith("TeamViewer"):
        return "tv"
    if kind in PC_STATE_TYPES:
        return "pcstate"
    if kind in (WLAN_TYPE, NET_TYPE):
        return "wlan"
    if kind in (FILE_TYPE, BROWSER_TYPE):
        return "files"
    return None


def row_of(activity):
    """Zeile der Timeline, in der ein Eintrag steht (Kennung aus TIMELINE_ROWS)."""
    if activity.get("work"):
        return "work"
    if activity.get("doc") or activity.get("open") or activity.get("cluster"):
        return "doc"
    if activity.get("m42") or activity.get("m42_gap"):
        return "m42"
    if activity.get("rule"):
        return "rule"
    if activity.get("ai"):
        return "ai"
    if activity.get("app") or activity.get("pc_block"):
        return "pc"
    return row_kind(activity) or "other"


# Zeilen mit einstellbarer Farbe (PC-Aktivität färbt nach Tätigkeit bzw. Programm)
COLOR_ROWS = [k for k, _t in TIMELINE_ROWS if k != "pc"]


def now_pill_color(color):
    """Füllung der Pille an der Jetzt-Linie: Farbe der Linie, falls die weiße Uhrzeit darauf
    lesbar ist, sonst derselbe Farbton kräftiger und dunkler (helles Rot im dunklen Design)."""
    fill = QColor(color)
    if contrast("#FFFFFF", fill.name()) >= 4.5:
        return fill
    hue = max(0, fill.hslHue())
    for light in range(150, 40, -10):  # Sättigung hoch statt grau-braun, Helligkeit schrittweise runter
        fill = QColor.fromHsl(hue, 230, light)
        if contrast("#FFFFFF", fill.name()) >= 4.5:
            break
    return fill


def type_label(activity):
    """Typ-Text für Liste und Details, bei Telefonaten mit Richtung."""
    if activity.get("doc"):
        return f"Doku: {activity['category']}" if activity.get("category") else "Doku"
    if activity.get("open"):
        return "Undokumentiert"
    if activity.get("m42"):
        return f"Matrix42: {activity['category']}" if activity.get("category") else "Matrix42"
    if activity.get("m42_gap"):
        return "Nicht gebucht"
    if activity.get("rule"):
        return f"Zuordnung: {activity.get('category', '')}"
    if activity.get("ai"):
        text = f"KI: {activity.get('category', '')}"
        return text + " (übernommen)" if activity.get("status") == "übernommen" else text
    direction = activity.get("direction")
    text = activity.get("type", "")
    if direction and direction != "Anruf":
        text = f"{text} {direction.lower()}"
    return f"Nicht gebucht: {text}" if activity.get("m42_unbooked") else text


def hhmm(minutes):
    minutes = int(minutes)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def format_duration(seconds):
    minutes = int(round(seconds / 60))
    if minutes < 1:
        return "< 1 min"
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60}:{minutes % 60:02d} h"


def ai_copy_text(entry):
    """KI-Vorschlag als Zeile fürs Ticket: Zeit, Kunde, Beschreibung."""
    start, end = parse_time(entry["start"]), parse_time(entry["end"])
    who = f"{entry['customer_name']}: " if entry.get("customer_name") else ""
    return (f"{start:%H:%M}–{end:%H:%M} ({format_duration((end - start).total_seconds())})  "
            f"{who}{entry.get('description', '')}")


def cluster_open(band, gap_seconds=120):
    """Zeile Dokumentation: offene Einträge, die sich überschneiden oder dicht folgen, als ein Block.

    Statt mehrerer übereinanderliegender „? Ka…“-Kästchen steht dort „? 3 offen“. Der Block
    verweist auf den ersten offenen Eintrag (Klick trägt ihn ein), der Hinweis zeigt alle.
    """
    result, group = [], []

    def flush():
        if len(group) == 1:
            result.append(group[0])
        elif group:
            first = group[0]
            result.append({**first, "end": max(e["end"] for e in group), "cluster": list(group),
                           "customer_name": f"{len(group)} offen",
                           "details": f"{len(group)} Tätigkeiten noch nicht dokumentiert"})
        group.clear()

    for e in sorted(band, key=lambda e: e["start"]):
        if not e.get("open"):
            flush()
            result.append(e)
            continue
        if group and (parse_time(e["start"]) - parse_time(max(g["end"] for g in group))
                      ).total_seconds() > gap_seconds:
            flush()
        group.append(e)
    flush()
    return result


def stack_lanes(spans, max_lanes=10):
    """Überlappende Zeiträume auf Unterzeilen verteilen (wie im Kalender).

    spans: [(start, end)]. -> ([Unterzeile je Zeitraum, ab 0], Anzahl Unterzeilen).
    Jeder Zeitraum kommt in die oberste Unterzeile, in der er nichts überdeckt. Was nur
    aneinanderstößt (Ende = Anfang), bleibt in einer Zeile. Mehr als max_lanes: die letzte
    Unterzeile nimmt den Rest auf.
    """
    lanes, ends = [0] * len(spans), []
    for i in sorted(range(len(spans)), key=lambda i: spans[i]):
        start, end = spans[i]
        for idx, lane_end in enumerate(ends):
            if start >= lane_end:
                break
        else:
            if len(ends) < max_lanes:
                ends.append(start)
            idx = len(ends) - 1
        ends[idx] = max(ends[idx], end)
        lanes[i] = idx
    return lanes, len(ends)


def entry_menu_items(entry, customer_known=False):
    """Befehle für einen Eintrag: [(Text, Befehl)], None = Trennlinie.

    Timeline und Tagesliste zeigen dasselbe Menü mit denselben Texten, und nur Befehle,
    die zu diesem Eintrag passen.
    """
    if entry.get("work"):  # Personalzeit: nur kopieren
        return [("&Kopieren", "copy")]
    if entry.get("m42"):  # Buchung aus Matrix42: nur ansehen und kopieren
        return [("&Details öffnen", "details"), None, ("&Kopieren", "copy")]
    if entry.get("m42_gap"):  # Zeit ohne Buchung
        return [(f"&Tätigkeit ab {hhmm(entry['minute'])} eintragen …", "add_at"), None,
                ("&Kopieren", "copy")]
    if "minute" in entry:  # freie Stelle in der Timeline
        return [(f"&Tätigkeit ab {hhmm(entry['minute'] // 5 * 5)} eintragen …", "add_at")]
    if entry.get("open"):
        return [("Jetzt &eintragen …", "add"), ("&Nicht dokumentieren", "ignore")]
    if entry.get("doc") and entry.get("doc_item", {}).get("von_pc"):  # von anderem PC übernommen
        return [("Als Ticketzeile &kopieren", "copy")]
    if entry.get("doc"):
        # Dritter Wert False = deaktiviert (reine Anzeige, darum ohne Alt-Buchstaben)
        booked = entry.get("doc_item", {}).get("m42_entry")
        book = ((f"In Matrix42 gebucht ({booked})", "m42_book", False) if booked
                else ("In &Matrix42 buchen …", "m42_book"))
        return [("Tätigkeit &bearbeiten …", "edit"), ("Tätigkeit &löschen", "delete"), None,
                ("Als Ticketzeile &kopieren", "copy"), book]
    items = [("&Details öffnen", "details"), None]
    if entry.get("ai") or entry.get("rule"):
        items.append(("Als &Tätigkeit eintragen …", "add"))
    else:
        items.append(("&Tätigkeit dazu eintragen …", "add"))
    if entry.get("tv_id"):
        items.append(("TeamViewer-ID &benennen …", "name_tv"))
    elif not customer_known and customers.primary_trace(entry):  # RDM, VPN, Telefon, E-Mail
        items.append(("Kunde &zuordnen …", "assign_customer"))
    if entry.get("ai"):
        if not entry.get("von_pc"):  # übernommene Vorschläge verwirft man auf dem anderen PC
            items += [None, ("Vorschlag &verwerfen", "reject")]
    items += [None, ("&Kopieren", "copy")]
    return items


def exec_entry_menu(parent, entry, global_pos):
    """Menü zu entry zeigen, gewählten Befehl zurückgeben (oder None)."""
    menu = QMenu(parent)
    keys = {}
    known = False
    config = getattr(parent, "config", None)
    if isinstance(config, dict) and not entry.get("tv_id"):
        imported = getattr(parent, "imported", None)
        known = bool(customers.index(config, imported.customers() if imported else None)
                     .customer_for(entry))
    for item in entry_menu_items(entry, known):
        if item is None:
            menu.addSeparator()
        else:
            action = menu.addAction(item[0])
            if len(item) > 2 and not item[2]:
                action.setEnabled(False)
                if item[1] == "m42_book":
                    action.setToolTip("Diese Tätigkeit ist schon in Matrix42 gebucht")
            keys[action] = item[1]
    menu.setToolTipsVisible(True)
    return keys.get(menu.exec(global_pos))


def _config_of(widget):
    """Einstellungen des Hauptfensters: erstes Fenster in der Eltern-Kette mit config."""
    while widget is not None:
        config = getattr(widget, "config", None)
        if isinstance(config, dict):
            return config
        widget = widget.parent()
    return {}


class ActivityViewDialog(QDialog):
    """Nur-Anzeigen-Dialog zum Kopieren von Aktivitätsdaten."""

    def __init__(self, activity, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aktivitätsdetails")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft)

        # Einstellungen → Ansicht → „Aktivitätsdetails als Textfelder“: Werte in schreibgeschützten
        # Feldern, dort reicht Klick + Strg+A + Strg+C zum Kopieren
        fields = bool(_config_of(parent).get("detail_text_fields", False))

        def row(key, text):
            """Nur anzeigen: Name grau, Wert als markierbarer Text oder als schreibgeschütztes Feld."""
            label = QLabel(key)
            label.setObjectName("detail_key")
            if fields:
                value = QLineEdit(text or "")
                value.setReadOnly(True)
                value.setCursorPosition(0)
            else:
                value = QLabel(text or "–")
                value.setObjectName("detail_value")
                value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(label, value)

        try:
            start = parse_time(activity["start"])
            end = parse_time(activity["end"])
            zeit = f"{start:%d.%m.%Y}, {start:%H:%M} – {end:%H:%M}"
            dauer = format_duration((end - start).total_seconds())
        except (KeyError, ValueError):
            zeit = dauer = ""

        row("Typ", type_label(activity))
        row("Kunde", activity.get("customer_name", ""))
        row("Zeit", zeit)
        row("Dauer", dauer)
        layout.addLayout(form)

        text = activity.get("details", "")
        parts = [p for p in activity.get("parts") or [] if isinstance(p, dict)]  # ohne (Programm, Sek.)-Paare
        if parts:
            lines = [f"{p['start'][11:16]}–{p['end'][11:16]}  {type_label(p)}  "
                     f"{p.get('customer_name', '')}" for p in parts]
            text = (text + "\n\n" if text else "") + \
                f"Enthält {len(lines)} Einträge:\n" + "\n".join(lines)
        if activity.get("ai"):
            text = activity.get("description", "")
            row("Sicherheit", f"{round(activity.get('confidence', 0) * 100)} %")
        if text and fields:
            details = QPlainTextEdit(text)
            details.setReadOnly(True)
            details.setMaximumHeight(240 if parts else 110)
            label = QLabel("Details")
            label.setObjectName("detail_key")
            layout.addSpacing(8)
            layout.addWidget(label)
            layout.addWidget(details)
        elif text:
            box = QFrame()
            box.setObjectName("notice")
            inner = QVBoxLayout(box)
            inner.setContentsMargins(12, 10, 12, 10)
            details = QLabel(text)
            details.setWordWrap(True)
            details.setTextInteractionFlags(Qt.TextSelectableByMouse)
            details.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            scroll = QScrollArea()  # lange Listen (Arbeitsblöcke) scrollen statt das Fenster zu sprengen
            scroll.setWidget(details)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setMaximumHeight(240 if parts else 90)
            inner.addWidget(scroll)
            label = QLabel("Details")
            label.setObjectName("detail_key")
            layout.addSpacing(8)
            layout.addWidget(label)
            layout.addWidget(box)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class TimelineView(QGraphicsView):
    # Nach jedem Zeichnen: Einträge des Tages und PC-Aktivität (für die Tagesliste)
    day_loaded = Signal(list, list)
    # Rechtsklick auf einen KI-Vorschlag: (Eintrag, "übernehmen" | "verwerfen")
    ai_action = Signal(dict, str)
    # Tätigkeit eintragen/ändern: (Aktion, Eintrag oder {"minute": …})
    # Aktionen: "add" (zu einem Eintrag), "add_at" (freie Stelle), "edit", "delete", "ignore",
    # "add_range" (mit links gezogener Bereich: {"start_min": …, "end_min": …})
    doc_request = Signal(str, dict)
    # Rechtsklick-Menü: (Befehl aus entry_menu_items, Eintrag oder {"minute": …})
    entry_action = Signal(str, dict)
    # Rechtsklick auf die Legende links: Menü „Zeilen der Timeline“ an dieser Stelle (global)
    # und die Zeile unter der Maus ("" = keine), für „Farbe ändern“
    rows_menu_requested = Signal(QPoint, str)
    # Zeilen in der Legende verschoben: neue Reihenfolge (Liste der Kennungen)
    row_order_changed = Signal(list)
    # Mindest- oder Höchsthöhe geändert (andere Zahl Zeilen): Hauptfenster passt die Aufteilung an
    height_limits_changed = Signal()
    # Hintergrund-Thread hat TeamViewer- und RDM-Logs gelesen
    logs_loaded = Signal(object, object, object)
    # Logs werden gelesen (True) oder sind fertig (False) – für die Ladeanzeige
    loading_changed = Signal(bool)
    # Hintergrund-Thread hat für reload_source vorgelesen (z. B. Ereignisprotokoll): Quelle
    _source_ready = Signal(str)
    # Fahrzeit zu einer Termin-Adresse berechnet (Schlüssel, Minuten oder None bei Fehler)
    _route_done = Signal(str, object)
    # Config geändert (z. B. neue Fahrzeit gemerkt): Hauptfenster speichert sie
    config_changed = Signal()

    # Kräftige, gut unterscheidbare Farben je Programm (Band "PC")
    APP_COLORS = ["#2F7BFF", "#FF7A00", "#18B34B", "#9B3DF2", "#FF2E8A",
                  "#00A8B5", "#E5242B", "#F5B700", "#4C6EF5", "#8BC34A"]

    LEFT = 136         # Rand links in Pixeln: Platz für die schwebende Beschriftung (Legende)
    RIGHT = 34         # Rand rechts
    AXIS_H = 26        # Höhe der Stundenleiste oben
    PC_BAND_H = 22     # Zeile PC-Aktivität (Arbeitsblöcke mit Beschriftung)
    PC_RAW_H = 14      # schmales Band, wenn jedes Fenster einzeln gezeigt wird (pc_blocks aus)
    # Arbeitsblöcke am PC: ruhige, gedeckte Farben (in beiden Designs mind. 3 : 1 zum Grund),
    # bekannte Tätigkeiten mit fester Farbe, alle anderen über den Namen verteilt
    BLOCK_COLORS = ["#356CA9", "#25766B", "#267841", "#85642A", "#BB3B50", "#7C51C8", "#2A7285",
                    "#9C5831"]
    CATEGORY_COLORS = {"E-Mail / Kommunikation": "#356CA9", "Beratung / Abstimmung": "#7C51C8",
                       "Fernwartung": "#85642A", "Cloud-/M365-Administration": "#2A7285",
                       "Dokumentation / Ticket": "#267841", "Telefonsupport": "#25766B",
                       "Zugangsdaten / Sicherheit": "#BB3B50"}
    LANE_H = 26        # Höhe eines Eintrags (wird kleiner, wenn sonst nicht alles ins Fenster passt)
    LANE_GAP = 6
    MIN_LANE_H = 16
    MIN_LANES = 0      # freie Spuren unter den festen Zeilen (RDM …), nur so viele wie nötig
    MAX_LANES = 10
    BASE_PX_PER_MIN = 1.2

    def __init__(self, activities, config, parent=None):
        super().__init__(parent)
        self.activities = activities
        self.config = config or {}
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self._first_draw = True
        self._ppm = None  # Pixel pro Minute beim letzten Zeichnen
        self.activity_rects = {}
        self.remote_suggestions = []
        self.current_date = QDate.currentDate()
        self.calls_file = None  # wird vom Hauptfenster gesetzt (anrufe.json)
        self.tracker = None     # Aktivitätsprotokoll, vom Hauptfenster gesetzt
        self.activity_dir = None  # Ordner des Protokolls (auch lesbar, wenn pausiert)
        self.personal_day = None  # date_str -> Personalzeiten aus ITM, vom Hauptfenster gesetzt
        self.ai_entries = None    # date_str -> KI-Vorschläge, vom Hauptfenster gesetzt
        self.rule_entries = None  # date_str -> Blöcke aus den Regeln (ohne KI)
        self.doc_entries = None   # date_str -> eigene Tätigkeiten und noch offene
        self.m42_entries = None   # date_str -> Buchungen aus Matrix42 und Lücken ohne Buchung
        self.imported = None      # übernommene Daten anderer PCs (transfer.ImportStore)
        self.outlook_entries = None  # date_str -> Termine, Mails, Teams-Anrufe (app_outlook.py)
        # Beim Start: erstes Zeichnen (bevorzugter Zeitraum), sobald die Logs gelesen sind;
        # vom Hauptfenster gesetzt (start_first_load). So wird der Tag nur einmal gezeichnet.
        self.first_show = None

        # Fahrzeiten zu Termin-Adressen über OpenStreetMap nur im Hauptfenster (nicht in der
        # Vorschau der Einstellungen); laufende und in dieser Sitzung gescheiterte Abfragen
        self.route_lookups = False
        self._route_asked = set()
        self._route_done.connect(self._on_route_done)

        self._remote_cache = {}  # date_str -> list[conn]
        self._tv_parser = TeamViewerParser(self.config)
        self._rdm_parser = RdmParser(self.config)
        self._vpn_parser = VpnParser(self.config)
        self.rdp_reader = RdpReader(self.config)  # RDM Better und mstsc
        self._rdp_index = None
        self.local_reader = LocalReader(self.config)  # Spuren vom PC (local_sources.py)
        self._local_index = None
        self._tv_index = None   # None = Logs noch nicht gelesen
        self._rdm_index = None
        self.vpn_reader = VpnReader()  # Sophos Connect/FortiClient; Archivdatei setzt das Hauptfenster
        self._sophos_index = None
        self._vpn_index = None
        self.loading = False    # Logs werden gerade im Hintergrund gelesen
        self._reload = False    # während des Lesens erneut angefordert
        self._skip_draw = False  # refresh(draw=False): nach dem Lesen nicht zeichnen
        self._reload_draw = False  # erneutes Lesen soll danach zeichnen
        self.draw_stale = False  # Daten neuer als die gezeichnete Timeline (Fenster war versteckt)
        self._thread = None
        self._threads = []      # alle gestarteten Einlese-Threads (zum Abwarten beim Beenden)
        self._closing = False   # beim Beenden: Thread darf nichts mehr melden
        self._day_data = None   # Daten vom letzten draw_timeline (Zoom zeichnet nur neu)
        # Nur während draw_timeline: Ergebnisse, die Timeline, Tagesliste und Statuszeile
        # mehrmals brauchen (Einträge des Tages, offene Tätigkeiten …). Danach wieder None,
        # damit nichts veraltet.
        self._draw_memo = None
        self._pc_cache = {}  # (Tag, Mindestdauer, Lücke) -> (Fensterstücke, Einträge), siehe _pc_entries_for
        self._block_cache = {}  # siehe pc_blocks_for
        # Beide Zwischenspeicher füllt auch der Thread, der den Vortag vorbereitet (_prefetch)
        self._cache_lock = threading.Lock()
        self._prefetch_date = None
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.setInterval(self.PREFETCH_MS)
        self._prefetch_timer.timeout.connect(self._start_prefetch)
        self.logs_loaded.connect(self._on_logs_loaded)

        self.zoom_level = 1.0
        self._wheel_zoom = None    # (Zoomstufe, Mausposition), noch nicht gezeichnet
        self._wheel_timer = QTimer(self)
        self._wheel_timer.setSingleShot(True)
        self._wheel_timer.setInterval(30)
        self._wheel_timer.timeout.connect(self._apply_wheel_zoom)
        # Fenster/Leiste in der Größe ändern: erst zeichnen, wenn die Größe kurz stillsteht
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(40)
        self._resize_timer.timeout.connect(self._apply_resize)
        # Aufzeichnungen (mstsc, VPN, Spuren vom PC) melden sich alle 30 Sekunden kurz
        # nacheinander: ein Neuzeichnen für alle (reload_source)
        self._source_timer = QTimer(self)
        self._source_timer.setSingleShot(True)
        self._source_timer.setInterval(150)
        self._source_timer.timeout.connect(self._redraw_sources)
        self._source_ready.connect(self._apply_source)
        self._rendered_h = None    # Höhe der Fläche beim letzten Zeichnen
        # Jetzt-Linie mit Uhrzeit-Pille: jede Minute verschieben, auch ohne neues Zeichnen
        # (z. B. Aufzeichnung pausiert). Nur die zwei Teile, nicht die ganze Szene.
        self._now_items = None     # (Linie, Pille, Text, Szenenbreite, Höhe)
        self._now_timer = QTimer(self)
        self._now_timer.setSingleShot(True)
        self._now_timer.timeout.connect(self._tick_now)
        self._schedule_now_tick()
        self.fit_day = True        # ganzen Tag ins Fenster einpassen
        self._drag_start = None    # Mausposition beim Drücken (Bereich ziehen)
        self._drag_button = None   # links: Tätigkeit eintragen, rechts: Zoom
        self._drag_item = None     # markierter Bereich während des Ziehens
        self._hover_line = None    # senkrechte Linie unter der Maus
        self._hover_label = None   # Uhrzeit oben an der Linie
        self._day_entries = []     # gezeichnete Einträge (für die Linie)
        self._pc_band = []
        self._ai_band = []
        self._bands = []           # obere Zeilen: [(Kennung, Text, Einträge)]
        self.dark_mode = self.config.get("dark_mode", False)

        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(200)
        # Keine senkrechte Scrollleiste: die Zeilen werden niedriger, bis alles passt
        # (reicht das nicht, blättert UMSCHALT + Mausrad nach oben und unten)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._legend = []          # [(y, Höhe, Name, Farbe oder None)] für die Legende links
        self._legend_keys = []     # Kennung je Legendenzeile (gleiche Reihenfolge)
        self._row_drag = None      # Zeile, die gerade in der Legende verschoben wird: [Kennung, y]
        self._legend_cursor = False  # Hand über der Legende gesetzt
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setMouseTracking(True)

        self.init_timeline_colors()
        self.tooltip = self._create_tooltip()
        # Bis zum ersten Zeichnen: Umrisse von Zeilen und Balken (skeleton.py)
        self._skeleton = True
        skeleton.pulse().watch(self.viewport())

    # ----------------------------- Farben / Dark-Mode -------------------------

    def init_timeline_colors(self):
        """Grundfarben aus dem Design (theme.THEMES), Balken in den Typfarben."""
        t = theme_for({**(self.config or {}), "dark_mode": self.dark_mode})
        self.background_color = QColor(t["canvas"])
        self.text_color = QColor(t["text"])
        self.muted_text = QColor(t["muted"])
        self.accent = QColor(t["accent"])
        self.now_color = QColor(t["now"])
        if self.dark_mode:
            self.hour_line = QColor(255, 255, 255, 22)
            self.half_line = QColor(255, 255, 255, 9)
            self.non_work_color = QColor(0, 0, 0, 80)
        else:
            self.hour_line = QColor(27, 31, 36, 26)
            self.half_line = QColor(27, 31, 36, 10)
            self.non_work_color = QColor(27, 31, 36, 14)
        self.axis_bg = QColor(t["canvas"])

    def _add_block(self, x, y, w, h, pen, brush):
        """Balken mit runden Ecken in die Szene legen (wie scene.addRect)."""
        item = _RoundRect(x, y, w, h)
        item.setPen(pen)
        item.setBrush(brush)
        self.scene.addItem(item)
        return item

    def set_dark_mode(self, enabled: bool):
        self.dark_mode = enabled
        self.init_timeline_colors()
        if self._ppm:  # erst neu zeichnen, wenn schon einmal gezeichnet wurde
            self.relayout()

    # ----------------------------- Tooltip -----------------------------------

    def _create_tooltip(self):
        tooltip = QLabel(self.parent(), Qt.ToolTip)
        tooltip.setObjectName("timeline_tip")  # Aussehen wie QToolTip, siehe theme.py
        tooltip.hide()
        return tooltip

    # ----------------------------- Daten laden --------------------------------

    def refresh(self, draw=True):
        """Logdateien im Hintergrund neu einlesen (nur geänderte Dateien werden wirklich gelesen).

        Große Logs oder Netzwerkpfade blockieren so weder den Start noch die Bedienung.
        Danach wird die Timeline neu gezeichnet; mit draw=False nur gelesen (Fenster versteckt:
        Nachfragen brauchen die Daten, das Zeichnen holt draw_stale beim Öffnen nach).
        """
        if self.loading:
            self._reload = True
            self._reload_draw = self._reload_draw or draw
            return
        self._skip_draw = not draw
        self.loading = True
        self.loading_changed.emit(True)
        self._thread = threading.Thread(target=self._load_logs, daemon=True)
        self._threads = [t for t in self._threads if t.is_alive()] + [self._thread]
        self._thread.start()

    def shutdown(self, timeout=3):
        """Beim Beenden: laufendes Einlesen abwarten, danach meldet der Thread nichts mehr.

        Sonst kann er nach dem Aufräumen ein Signal an die gelöschte Timeline senden
        (Absturz beim Beenden unter Windows).
        """
        self._closing = True
        end = time.monotonic() + timeout
        # Auch ein älteres, noch laufendes Einlesen abwarten (nicht nur das letzte)
        for thread in list(self._threads):
            thread.join(max(0, end - time.monotonic()))

    SOURCE_INDEX = {"rdp": "_rdp_index", "vpn": "_sophos_index", "local": "_local_index"}

    def reload_source(self, name, draw=True):
        """Nur eine selbst aufgezeichnete Quelle neu aufbereiten ("rdp", "vpn", "local").

        Statt refresh(): die Logs von TeamViewer, RDM und VPN bleiben, wie sie sind. Für
        mstsc wird das Windows-Ereignisprotokoll (wevtutil, bis zu Sekunden) vorher im
        Hintergrund gelesen, damit die Oberfläche nie darauf wartet."""
        if self.loading:  # gleich kommen ohnehin alle Quellen neu
            return
        if name == "rdp" and (self.config.get("mstsc_enabled", True)
                              or self.config.get("rdmbetter_enabled", True)):
            def prefetch():
                try:
                    self.rdp_reader.event_sessions()
                except Exception as e:  # Timeline darf daran nie scheitern
                    print(f"RDP-Ereignisprotokoll nicht vorab gelesen: {e}")
                if not self._closing:
                    self._source_ready.emit("rdp" if draw else "rdp-nodraw")
            thread = threading.Thread(target=prefetch, daemon=True, name="RDP-Ereignisse")
            self._threads = [t for t in self._threads if t.is_alive()] + [thread]
            thread.start()
            return
        self._apply_source(name if draw else f"{name}-nodraw")

    def _apply_source(self, name):
        if self._closing:
            return
        name, _sep, flag = name.partition("-")
        setattr(self, self.SOURCE_INDEX[name], None)
        self._remote_cache.clear()
        if flag != "nodraw":
            self._source_timer.start()

    def _redraw_sources(self):
        if not self.loading and not self._closing:  # beim Lesen zeichnet _on_logs_loaded
            self.draw_timeline(self.current_date)

    def _start_first_load(self):
        self.loading = False
        self.refresh()

    def start_first_load(self, first_show, fallback_ms=1500):
        """Beim Start: Logs sofort im Hintergrund lesen (während das Fenster aufgebaut und mit
        Umrissen gezeigt wird) und den Tag erst danach einmal zeichnen (first_show).
        Dauert das Lesen länger als fallback_ms (z. B. Logs auf einem Netzlaufwerk), zeichnet
        first_show schon ohne die Logs; sie kommen dann wie bisher nach."""
        self.first_show = first_show
        # Der Lese-Thread rechnet in Python; Qt braucht für jeden Aufruf in Python-Code (Zeichnen,
        # Größen) kurz den GIL. Mit dem Standard (5 ms je Wechsel) wartet das Fenster dann
        # spürbar. Bis zum ersten Zeichnen öfter abwechseln, danach wieder wie gewohnt.
        self._switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(min(self._switch_interval, 0.0005))
        # Erst die Umrisse malen lassen, dann lesen: Beides gleichzeitig kostet das erste Bild
        # deutlich mehr Zeit, als das Lesen gewinnt. Ist das Fenster nicht zu sehen (Start im
        # Infobereich), gleich lesen; sonst spätestens nach 250 ms.
        self._load_after_paint = True
        QTimer.singleShot(250 if self._will_show() else 0, self._start_load_after_paint)
        QTimer.singleShot(fallback_ms, self._first_show_now)

    def _will_show(self):
        """Wird das Fenster gleich gezeigt? (Start im Infobereich: nein; setzt das Hauptfenster)"""
        return getattr(self.window(), "start_visible", True)

    def _start_load_after_paint(self):
        if self._load_after_paint and not self._closing:
            self._load_after_paint = False
            self.refresh()

    def _first_show_now(self):
        first, self.first_show = self.first_show, None
        if getattr(self, "_switch_interval", None):
            sys.setswitchinterval(self._switch_interval)
            self._switch_interval = None
        if first and not self._closing:
            first()

    def _colleagues(self):
        return call_import.colleagues_for(
            self.calls_file, self.config.get("colleague_numbers") or (),
            self.config.get("colleagues_auto", True))

    def _warm_up(self):
        """Im Lese-Thread vorab rechnen, was das Zeichnen sonst im Fenster rechnen müsste
        (nur Teile ohne Qt, die selbst threadsicher sind: Anrufliste/Kollegen, Spuren vom PC)."""
        try:
            if self.calls_file:
                self._colleagues()
            if any(self.config.get(k, True) for k in ("pcstate_enabled", "shell_enabled", "wlan_enabled",
                                                      "recent_files_enabled", "browser_enabled")):
                self.local_reader.entries()
            if self.activity_dir and self.config.get("pc_blocks", True):
                # Aktive Fenster des Tages lesen und den Fenstern ihre Tätigkeit zuordnen
                # (Regeln, Kundenliste). Beides wird gemerkt; das Zeichnen trifft es dann.
                segments = read_segments(self.activity_dir, self.current_date.toString("yyyy-MM-dd"))
                pieces = [{"start": s["start"], "end": s["end"], "app": s["app"], "title": s["title"]}
                          for s in merge_segments(segments, min_seconds=5, max_gap=15)]
                focus.focus_blocks(pieces, self.config.get("rules") or [],
                                   jump_seconds=self.config.get("pc_jump_seconds", focus.JUMP_SECONDS),
                                   keywords=customers.index(self.config))
        except Exception as e:  # nur Vorarbeit: Fehler zeigen sich beim Zeichnen ohnehin
            print(f"Vorab rechnen fehlgeschlagen: {e}")

    def _load_logs(self):
        indexes = []
        # Jede Quelle lässt sich im Menü "Datenquellen" einzeln abschalten
        for name, parser, key in (("TeamViewer", self._tv_parser, "teamviewer_enabled"),
                                  ("RDM", self._rdm_parser, "rdm_enabled"),
                                  ("VPN", self._vpn_parser, "vpn_enabled")):
            try:
                skip = not self.config.get(key, True)
                indexes.append(ConnectionIndex([] if skip else parser.parse_logs()))
            except Exception as e:
                print(f"Fehler beim Lesen der {name}-Logs: {e}")
                indexes.append(ConnectionIndex([]))
        # Windows-Ereignisprotokoll (wevtutil, bis zu Sekunden) hier im Hintergrund lesen:
        # nach logs_loaded baut der GUI-Thread den RDP-Index neu und trifft dann den frischen Cache
        if self.config.get("mstsc_enabled", True) or self.config.get("rdmbetter_enabled", True):
            try:
                self.rdp_reader.event_sessions()
            except Exception as e:  # Timeline darf daran nie scheitern
                print(f"RDP-Ereignisprotokoll nicht vorab gelesen: {e}")
        if not self._closing and self._day_data is None:  # nur vor dem ersten Zeichnen
            self._warm_up()
        if not self._closing:
            self.logs_loaded.emit(*indexes)  # Qt stellt das im GUI-Thread zu

    def _on_logs_loaded(self, tv_index, rdm_index, vpn_index):
        if self._closing:
            return  # beim Beenden nichts mehr zeichnen
        self._tv_index, self._rdm_index, self._vpn_index = tv_index, rdm_index, vpn_index
        self._sophos_index = None  # Archiv der VPN-Aufzeichnung beim nächsten Zeichnen neu lesen
        self._rdp_index = None     # ebenso RDM Better und mstsc
        self._local_index = None   # und die Spuren vom PC
        self._remote_cache.clear()
        self.loading = False
        self.loading_changed.emit(False)
        if self._reload:
            self._reload = False
            draw, self._reload_draw = self._reload_draw, False
            self.refresh(draw=draw)
        if self.first_show is not None:
            self._skip_draw = False
            self._first_show_now()  # erstes Zeichnen, gleich mit den Logs
            return
        if self._skip_draw:
            self._skip_draw = False
            self.draw_stale = True
            return
        self.draw_timeline(self.current_date)

    def load_remote_connections(self, date: QDate):
        date_str = date.toString("yyyy-MM-dd")
        if date_str in self._remote_cache:
            self.remote_suggestions = self._remote_cache[date_str]
            return
        if self._tv_index is None:  # erster Start: ohne Logs zeichnen, sie kommen gleich nach
            self.remote_suggestions = []
            if not self.loading:
                self.loading = True
                self.loading_changed.emit(True)
                # Erst lesen, wenn dieses Zeichnen fertig ist (sonst bremst der Thread es aus)
                QTimer.singleShot(0, self._start_first_load)
            return

        if self._sophos_index is None:
            try:
                self.vpn_reader.sources = vpn_sources(self.config)
                self._sophos_index = ConnectionIndex(
                    self.vpn_reader.connections() if self.vpn_reader.sources else [])
            except Exception as e:
                print(f"Fehler beim Lesen der VPN-Logs: {e}")
                self._sophos_index = ConnectionIndex([])

        if self._rdp_index is None:
            try:
                wanted = self.config.get("mstsc_enabled", True) or self.config.get("rdmbetter_enabled", True)
                self._rdp_index = ConnectionIndex(self.rdp_reader.connections() if wanted else [])
            except Exception as e:
                print(f"Fehler beim Lesen der Remotedesktop-Sitzungen: {e}")
                self._rdp_index = ConnectionIndex([])

        day = self._tv_index.get_for_date(date_str) + self._rdm_index.get_for_date(date_str)
        day += self._rdp_index.get_for_date(date_str)
        if self._local_index is None:
            try:
                self._local_index = ConnectionIndex(self.local_reader.entries())
            except Exception as e:
                print(f"Fehler beim Lesen der Spuren vom PC: {e}")
                self._local_index = ConnectionIndex([])
        day += self._local_index.get_for_date(date_str)
        day += self._vpn_index.get_for_date(date_str) + self._sophos_index.get_for_date(date_str)
        for conn in day:
            conn["is_suggestion"] = True
        self.remote_suggestions = day
        self._remote_cache[date_str] = day

    def memo(self, key, func):
        """func() einmal je Zeichnen berechnen (außerhalb von draw_timeline: jedes Mal)."""
        memo = self._draw_memo
        if memo is None:
            return func()
        if key not in memo:
            memo[key] = func()
        return memo[key]

    def activities_for(self, date: QDate):
        """Alle Einträge des Tages aus allen Quellen (ohne PC-Fenster), nach Beginn sortiert."""
        return list(self.memo(("activities", date.toString("yyyy-MM-dd")), lambda: self._activities_for(date)))

    def _activities_for(self, date: QDate):
        date_str = date.toString("yyyy-MM-dd")
        self.load_remote_connections(date)
        result = [a for a in self.activities if a.get("start", "").startswith(date_str)]
        result += [s for s in self.remote_suggestions if s.get("start", "").startswith(date_str)]
        if self.calls_file:
            result += load_call_suggestions(
                self.calls_file, date_str,
                ignore_missed=self.config.get("calls_ignore_missed", True),
                min_seconds=self.config.get("calls_min_duration", 0),
                colleague=self._colleagues(),
            )
        if self.outlook_entries:
            try:
                result += self.outlook_entries(date_str)
            except Exception as e:  # Outlook darf die Timeline nicht leeren
                print(f"Fehler beim Lesen von Outlook/Teams: {e}")
        if self.imported:  # von einem anderen PC übernommen (z. B. auf der PAW)
            own = {(a.get("type"), a.get("start"), a.get("end")) for a in result}
            for a in self.imported.connections(date_str):
                if (a.get("type"), a.get("start"), a.get("end")) not in own:
                    a["details"] = " · ".join(t for t in (a.get("details"), f"von {a['source_pc']}") if t)
                    result.append(a)

        valid = []
        for a in result:
            a.setdefault("type", "Aktivität")
            a.setdefault("customer_name", "")
            a.setdefault("details", "")
            a.setdefault("is_suggestion", False)
            try:
                parse_time(a["start"]), parse_time(a["end"])
            except (KeyError, ValueError):
                continue
            valid.append(a)
        # Derselbe VPN-Tunnel aus zwei Quellen (Logs, Archiv, anderer PC): der mit Namen gewinnt
        vpn = [a for a in valid if a.get("vpn_source")]
        if len(vpn) > 1:
            kept = {id(a) for a in drop_unnamed_twins(vpn)}
            valid = [a for a in valid if not a.get("vpn_source") or id(a) in kept]
        valid.sort(key=lambda a: a["start"])

        # TeamViewer: eigener Name statt nur der ID
        names = {**(self.imported.teamviewer_names() if self.imported else {}),
                 **self.config.get("teamviewer_names", {})}
        for a in valid:
            tv_id = a.get("tv_id")
            if tv_id:
                a["customer_name"] = names.get(tv_id) or f"TeamViewer {format_tv_id(tv_id)}"
                a["details"] = f"TeamViewer-ID {format_tv_id(tv_id)}"
        if self.config.get("travel_enabled", True):
            valid = self._with_trips(date, valid)
        return valid

    def _with_trips(self, date, entries):
        """Vermutete Fahrten zu Terminen mit Ort und zu Kundennetzen dazu (travel.py)."""
        places = any(e.get("type") == "Termin" and "Ort: " in (e.get("details") or "") for e in entries)
        nets = any(e.get("type") in (NET_TYPE, WLAN_TYPE) for e in entries)
        if not places and not nets:
            return entries  # nichts, woraus sich eine Fahrt ergibt: aktive Fenster nicht lesen
        try:
            index = customers.index(self.config)
            own = customers.customer_list(self.config)
            minutes = {c["name"]: c["travel_minutes"] for c in own if "travel_minutes" in c}

            def customer_minutes(appointment):  # Kunde des Termins, z. B. über die Mail-Domains
                return minutes.get(index.customer_for(appointment)) if minutes else None

            trips = travel.suggest(entries, self.pc_entries_for(date),
                                   customer_net=lambda name: index.lookup("net", name),
                                   places=travel.places_from_config(self.config, own),
                                   customer_minutes=customer_minutes,
                                   address_minutes=self._address_minutes,
                                   max_minutes=int(self.config.get("travel_max_minutes", travel.MAX_MINUTES)))
        except Exception as e:  # Vorschläge dürfen die Timeline nie leeren
            print(f"Fehler bei den vermuteten Fahrten: {e}")
            return entries
        return sorted(entries + trips, key=lambda a: a["start"])

    def _address_minutes(self, appointment):
        """Fahrzeit vom Büro zur Adresse im Ort des Termins oder None.

        Gemerkt in der Config (travel_address_minutes). Noch unbekannt: im Hintergrund über
        OpenStreetMap berechnen (nur die beiden Adressen gehen nach außen), danach neu zeichnen.
        Ändert sich die Adresse im Termin, ist das ein neuer Schlüssel und wird neu berechnet."""
        import route
        home = " ".join(str(self.config.get("travel_home_address") or "").split())
        if not home or not self.config.get("travel_route_appointments", True):
            return None
        place = " ".join(travel._location(appointment).split())
        if not route.looks_like_address(place):
            return None
        key = f"{home} → {place}".casefold()
        known = self.config.get("travel_address_minutes")
        if isinstance(known, dict) and key in known:
            return known[key]
        if self.route_lookups and key not in self._route_asked:
            self._route_asked.add(key)

            def work():
                try:
                    minutes = route.drive_minutes(home, place)
                except Exception as e:  # Adresse unbekannt, offline …: Schätzung über Lücken
                    print(f"Fahrzeit zu „{place}“ nicht berechnet: {e}")
                    minutes = None
                if not self._closing:
                    self._route_done.emit(key, minutes)

            thread = threading.Thread(target=work, daemon=True, name="Fahrzeit Termin")
            self._threads = [t for t in self._threads if t.is_alive()] + [thread]
            thread.start()
        return None

    def _on_route_done(self, key, minutes):
        if minutes is None or self._closing:
            return
        known = self.config.get("travel_address_minutes")
        if not isinstance(known, dict):
            known = self.config["travel_address_minutes"] = {}
        known[key] = int(minutes)
        if len(known) > 300:  # nur die neuesten Adressen behalten
            for old in list(known)[:-300]:
                known.pop(old, None)
        self.config_changed.emit()
        self._source_timer.start()  # neu zeichnen, die Fahrt hat jetzt die echte Länge

    def view_entries(self, date: QDate):
        """Einträge so, wie Timeline und Liste sie zeigen (einzeln oder zusammengefasst)."""
        entries = self.activities_for(date)
        if self.config.get("list_view", "grouped") == "single":
            return entries
        return group_entries(entries, self.config.get("merge_gap_minutes", 5))

    def pc_entries_for(self, date: QDate, min_seconds=30, max_gap=60):
        """Aktive Fenster des Tages als Einträge (für Band und Tagesliste)."""
        key = ("pc", date.toString("yyyy-MM-dd"), min_seconds, max_gap)
        return [dict(e) for e in self.memo(key, lambda: self._pc_entries_for(date, min_seconds, max_gap))]

    def _pc_entries_for(self, date: QDate, min_seconds, max_gap):
        date_str = date.toString("yyyy-MM-dd")
        if self.tracker:
            segments = self.tracker.segments_for(date_str)
        elif self.activity_dir:  # pausiert: bisher Aufgezeichnetes trotzdem zeigen
            segments = read_segments(self.activity_dir, date_str)
        else:
            segments = []
        if self.imported:  # aktive Fenster des anderen PCs
            segments = segments + self.imported.segments(date_str)
        if not segments:
            return []
        # Timeline, Tagesliste, Dokumentation und Statuszeile fragen beim Zeichnen mehrmals
        # nach demselben Tag: Ergebnis merken, solange die Fensterstücke gleich sind
        key = (date_str, min_seconds, max_gap)
        sig = tuple((s["start"], s["end"], s["app"], s["title"]) for s in segments)
        cache = self._pc_cache
        with self._cache_lock:
            hit = cache.pop(key, None)
        if hit is None or hit[0] != sig:
            result = []
            for seg in merge_segments(segments, min_seconds=min_seconds, max_gap=max_gap):
                result.append({
                    "start": seg["start"], "end": seg["end"],
                    "type": f"PC: {app_label(seg['app'])}",
                    "customer_name": seg["title"] or app_label(seg["app"]),
                    "details": seg["app"], "app": seg["app"],
                    "is_suggestion": True,
                })
            hit = (sig, result)
        with self._cache_lock:
            cache[key] = hit  # zuletzt benutzt ans Ende
            while len(cache) > 3 * self.BLOCK_CACHE_DAYS:  # nur die zuletzt gezeigten Tage (je bis zu 3 Varianten)
                del cache[next(iter(cache))]
        return hit[1]  # pc_entries_for gibt Kopien heraus

    def missing_sources(self):
        """Quellen, für die keine einzige Logdatei gelesen werden konnte."""
        return [name for name, parser in [("TeamViewer", self._tv_parser), ("RDM", self._rdm_parser)]
                if parser.files_read == 0]

    def rdmbetter_missing(self):
        """launcher.log von RDM Better nicht gefunden (nur für die Kachel in den Einstellungen)."""
        return self.config.get("rdmbetter_enabled", True) and self.rdp_reader.launcher.files_read == 0

    def app_color(self, app):
        return QColor(self.APP_COLORS[sum(map(ord, app.lower())) % len(self.APP_COLORS)])

    def block_color(self, block):
        """Farbe eines Arbeitsblocks am PC (nach Tätigkeit), sonst des Programms."""
        if not block.get("pc_block"):
            return self.app_color(block.get("app", ""))
        category = block.get("category", "")
        color = self.CATEGORY_COLORS.get(category) or \
            self.BLOCK_COLORS[sum(map(ord, category.lower())) % len(self.BLOCK_COLORS)]
        return QColor(color)

    BLOCK_CACHE_DAYS = 8

    def pc_blocks_for(self, date: QDate):
        """PC-Aktivität für die Timeline: Arbeitsblöcke (focus.py) oder, abgeschaltet, jedes Fenster."""
        raw = self.pc_entries_for(date, min_seconds=5, max_gap=15)
        if not raw or not self.config.get("pc_blocks", True):
            return raw
        return self._blocks_for(date, raw)

    def _blocks_for(self, date: QDate, raw):
        """Arbeitsblöcke aus den Fensterstücken raw (pc_entries_for mit 5 s / 15 s); ändert raw nicht."""
        rule_list = self.config.get("rules") or []
        index = customers.index(self.config)  # Stichwörter der Kundenliste (gleicher Index = gleiche Liste)
        # Gemerkt für die zuletzt gezeigten Tage (Hin- und Herspringen zwischen heute und
        # gestern rechnet sonst jedes Mal alles neu). Regeln über ihren Inhalt; der Index wird
        # mit gemerkt, damit seine id nicht an einen neuen Index vergeben werden kann.
        key = (date.toString("yyyy-MM-dd"), len(raw), raw[-1]["end"], repr(rule_list),
               self.config.get("pc_jump_seconds", focus.JUMP_SECONDS), id(index))
        with self._cache_lock:
            cache = self._block_cache
            if not isinstance(cache, dict):  # None: verworfen (z. B. Vorschau in den Einstellungen)
                cache = self._block_cache = {}
            hit = cache.pop(key, None)
        if hit is None or hit[1] is not index:
            segments = [{"start": e["start"], "end": e["end"], "app": e["app"], "title": e["customer_name"]}
                        for e in raw]
            hit = (focus.focus_blocks(segments, rule_list,
                                      jump_seconds=self.config.get("pc_jump_seconds", focus.JUMP_SECONDS),
                                      keywords=index), index)
        with self._cache_lock:
            cache[key] = hit  # zuletzt benutzt ans Ende
            while len(cache) > self.BLOCK_CACHE_DAYS:
                del cache[next(iter(cache))]
        return hit[0]

    # ------------------------- Vortag vorbereiten -----------------------------

    PREFETCH_MS = 400  # so lange nach dem Zeichnen warten (Bedienung geht vor)

    def _schedule_prefetch(self, date: QDate):
        """Nach dem Zeichnen den Vortag im Hintergrund vorbereiten: Beim Nachtragen geht es
        meist Tag für Tag zurück, dann trifft das Zeichnen die Zwischenspeicher."""
        if (self._closing or self.loading or self.imported
                or not (self.tracker or self.activity_dir) or not self.config.get("pc_blocks", True)):
            return
        self._prefetch_date = date.addDays(-1)
        self._prefetch_timer.start()

    def _start_prefetch(self):
        date, self._prefetch_date = self._prefetch_date, None
        if date is None or self._closing or self.loading:
            return
        running = getattr(self, "_prefetch_thread", None)
        if running is not None and running.is_alive():
            return
        thread = threading.Thread(target=self._prefetch, args=(date,), daemon=True, name="Vortag vorbereiten")
        self._prefetch_thread, self._prefetch_day = thread, date.toString("yyyy-MM-dd")
        self._threads = [t for t in self._threads if t.is_alive()] + [thread]
        thread.start()

    def _wait_for_prefetch(self, date: QDate):
        """Bereitet der Thread gerade genau diesen Tag vor: kurz auf ihn warten, statt
        dasselbe gleichzeitig noch einmal zu rechnen."""
        thread = getattr(self, "_prefetch_thread", None)
        if (thread is not None and thread.is_alive()
                and getattr(self, "_prefetch_day", None) == date.toString("yyyy-MM-dd")):
            thread.join(1.0)

    def _prefetch(self, date: QDate):
        """Im Thread: Fensterstücke (beide Varianten) und Arbeitsblöcke des Tages in die
        Zwischenspeicher. Nur Teile ohne Qt, die selbst threadsicher sind (wie _warm_up)."""
        try:
            raw = self._pc_entries_for(date, 5, 15)
            if raw and not self._closing:
                self._blocks_for(date, raw)
            if not self._closing:
                self._pc_entries_for(date, 30, 60)
        except Exception as e:  # nur Vorarbeit: das Zeichnen rechnet es sonst selbst
            print(f"Vortag nicht vorbereitet: {e}")

    # ----------------------------- Zeichnen ----------------------------------

    def _x(self, minutes):
        return self.LEFT + minutes * self._ppm

    def _work_spans(self, date: QDate):
        """Arbeitszeit als [(Start, Ende)] in Minuten: Personalzeiten aus ITM, sonst Einstellungen."""
        return self._work_info(date)[0]

    def _work_info(self, date: QDate):
        """([(Start, Ende)] in Minuten, aus ITM?, Index der offenen Buchung oder None).

        Offen heute: noch eingestempelt, läuft bis jetzt. Offen an einem früheren Tag: Gehen
        vergessen. Das Ende ist unbekannt, der Block reicht bis zum geplanten Feierabend
        (sonst eine Stunde) und gilt nicht als Personalzeit (siehe missing_end_idx)."""
        day = self.personal_day(date.toString("yyyy-MM-dd")) if self.personal_day else None
        if day and day.get("zeiten"):
            spans, open_idx = [], None
            now = datetime.now()
            for t in day["zeiten"]:
                start = parse_time(t["start"])
                a = start.hour * 60 + start.minute
                if t["end"]:
                    end = parse_time(t["end"])
                    b = end.hour * 60 + end.minute if end.date() == start.date() else 24 * 60
                else:
                    open_idx = len(spans)
                    if start.date() >= now.date():  # noch eingestempelt
                        b = now.hour * 60 + now.minute if now.date() == start.date() else 24 * 60
                    else:  # Gehen fehlt
                        hours = work_hours(self.config, date.dayOfWeek() - 1)
                        b = hours[1] if hours and hours[1] > a else min(a + 60, 24 * 60)
                spans.append((a, b))
            return spans, True, open_idx
        return work_spans(self.config, date.dayOfWeek() - 1), False, None

    def missing_end_idx(self, date: QDate):
        """Index der Personalzeit, bei der an einem früheren Tag das Gehen fehlt, sonst None."""
        _spans, from_itm, open_idx = self._work_info(date)
        if from_itm and open_idx is not None and date < QDate.currentDate():
            return open_idx
        return None

    def work_entries(self, date_str):
        """Zeile "Personalzeit": je gestempeltem Abschnitt ein Block mit Beginn und Ende
        (ohne ITM die Arbeitszeit aus den Einstellungen)."""
        date = QDate.fromString(date_str, "yyyy-MM-dd")
        spans, from_itm, open_idx = self._work_info(date)
        missing = self.missing_end_idx(date)
        name = "Personalzeit" if from_itm else "Arbeitszeit"
        result = []
        for i, (a, b) in enumerate(spans):
            if b <= a:
                continue
            running = i == open_idx and missing is None
            if i == missing:
                label = f"{hhmm(a)} – Gehen fehlt"
            else:
                label = f"{hhmm(a)} – {'jetzt' if running else hhmm(b)}"
            end = f"{date_str} 23:59:59" if b >= 24 * 60 else f"{date_str} {hhmm(b)}:00"
            details = f"{name} {label}" + (" (eingestempelt)" if running else "")
            if i == missing:
                details += " (in ITM nachtragen; Ende hier nur geschätzt)"
            result.append({
                "start": f"{date_str} {hhmm(a)}:00", "end": end, "type": name,
                "customer_name": label, "work": True, "from_itm": from_itm, "running": running,
                "missing_end": i == missing, "details": details,
                "is_suggestion": False,
            })
        return result

    def _work_text(self, minute):
        """Was zu dieser Minute laut Personalzeit/Arbeitszeit gilt (eine Zeile)."""
        spans, from_itm, open_idx = self._work_info(self.current_date)
        missing = self.missing_end_idx(self.current_date)
        name = "Personalzeit" if from_itm else "Arbeitszeit"
        if not spans:
            return f"<i>Keine {name}</i>"
        for i, (a, b) in enumerate(spans):
            if a <= minute < b:
                if i == missing:
                    return f"<b>{name}</b> seit {hhmm(a)} (Gehen fehlt in ITM)"
                if i == open_idx:
                    return f"<b>{name}</b> seit {hhmm(a)} (eingestempelt)"
                return f"<b>{name}</b> {hhmm(a)} – {hhmm(b)}"
        before = [b for _a, b in spans if b <= minute]
        after = [a for a, _b in spans if a > minute]
        if before and after:
            return f"<b>Pause</b> {hhmm(max(before))} – {hhmm(min(after))}"
        return f"<i>Außerhalb der {name}</i>"

    def _work_minutes(self, date: QDate):
        """Beginn und Ende der Arbeitszeit; an freien Tagen ist der ganze Tag abgedunkelt."""
        spans = self._work_spans(date)
        if not spans:
            return 12 * 60, 12 * 60
        return spans[0][0], max(end for _start, end in spans)

    def draw_timeline(self, date: QDate):
        """Daten des Tages neu lesen und zeichnen (nach Änderungen an den Daten)."""
        self.draw_stale = False
        self._wait_for_prefetch(date)
        outer, self._draw_memo = self._draw_memo, {}  # je Zeichnen frisch, auch verschachtelt
        try:
            self._day_data = self._collect(date)
            self._render()
            self.day_loaded.emit(self._day_data["activities"], self.pc_entries_for(date))
        finally:
            self._draw_memo = outer
        self._schedule_prefetch(date)

    def relayout(self):
        """Nur neu anordnen (Zoom, Fenstergröße, Design): Daten vom letzten Zeichnen,
        ohne Logs, Outlook, Anrufe … erneut zu lesen und ohne die Tagesliste neu aufzubauen."""
        if self._day_data is None or self._day_data["date"] != self.current_date:
            self.draw_timeline(self.current_date)
        else:
            self._render()

    def _collect(self, date: QDate):
        """Alles, was das Zeichnen braucht und nicht vom Zoom abhängt."""
        activities = self.view_entries(date)


        # Telefonate, Outlook, VPN und TeamViewer je in eine feste Zeile; der Rest (v. a. RDM)
        # in die freien Spuren. Überlappende Einträge kommen in jeder Zeile in eine weitere
        # Zeile darunter (stack_lanes). Ausgeblendete Zeilen (Menü "Zeilen der Timeline") fallen ganz weg.
        shown = self.config.get("timeline_rows", {})
        # Feste Zeilen nur, wenn es an diesem Tag etwas darin gibt (leere Zeilen lenken ab)
        present = {row_kind(a) for a in activities}
        fixed_rows = [(kind, label) for kind, label in FIXED_ROWS if shown.get(kind, True)
                      and kind in present]
        show_other = shown.get("other", True)
        fixed_items = {kind: [] for kind, _label in fixed_rows}
        free_items = []
        for a in activities:
            kind = row_kind(a)
            if kind is None:
                if show_other:
                    free_items.append(a)
            elif kind in fixed_items:
                fixed_items[kind].append(a)
        fixed_layout = [(kind, *self._stacked(fixed_items[kind])) for kind, _label in fixed_rows]
        free_placed, n_free = self._stacked(free_items)
        show_pc = shown.get("pc", True)
        pc_band = self.pc_blocks_for(date) if show_pc else []
        blocks_on = any(p.get("pc_block") for p in pc_band)
        pc_h = self.PC_BAND_H if blocks_on else self.PC_RAW_H
        bands = self.band_rows(date)
        ai_band = next((e for k, _t, e in bands if k == "ai"), [])
        # Doku: offene Einträge erst zusammenfassen, dann auf Unterzeilen verteilen
        band_layout = [(kind, *self._stacked(cluster_open(band) if kind == "doc" else band))
                       for kind, _text, band in bands]
        return {"date": date, "activities": activities, "fixed_layout": fixed_layout,
                "free_placed": free_placed, "n_free": n_free, "show_other": show_other,
                "show_pc": show_pc, "pc_band": pc_band, "pc_h": pc_h, "bands": bands,
                "ai_band": ai_band, "band_layout": band_layout}

    def _render(self):
        """Szene aus den gesammelten Daten aufbauen (schnell, für Zoom und Größe)."""
        self._end_skeleton()
        d = self._day_data
        date = d["date"]
        # Mittelpunkt merken, damit Zoom/Neuzeichnen die Ansicht nicht verschiebt
        center_min = None
        if not self._first_draw and self._ppm:
            center_x = self.mapToScene(self.viewport().rect().center()).x()
            center_min = (center_x - self.LEFT) / self._ppm

        self.current_date = date
        if self.fit_day:
            self.zoom_level = self._fit_ppm() / self.BASE_PX_PER_MIN
            center_min = None
        self._ppm = self.BASE_PX_PER_MIN * self.zoom_level
        self._drag_item = None
        self.scene.clear()
        self._hover_line = self._hover_label = None  # mit der Szene gelöscht
        self._now_items = None
        self.activity_rects.clear()
        self.tooltip.hide()
        self.scene.setBackgroundBrush(self.background_color)
        fixed_layout, free_placed, n_free = d["fixed_layout"], d["free_placed"], d["n_free"]
        show_other, show_pc, pc_band, pc_h = d["show_other"], d["show_pc"], d["pc_band"], d["pc_h"]
        bands, ai_band, band_layout = d["bands"], d["ai_band"], d["band_layout"]
        n_lanes = max(self.MIN_LANES, n_free) if show_other else 0
        show_other = show_other and n_lanes > 0
        band_y = self.AXIS_H + 6
        show_band = show_pc and bool(self.tracker or pc_band)
        top = band_y + (pc_h + 10 if show_band else 2)
        # Zeilenhöhe so wählen, dass alle Zeilen ohne senkrechte Scrollleiste ins Fenster passen;
        # Platz für die horizontale Scrollleiste lassen
        n_rows = (sum(max(1, n) for _k, _p, n in band_layout)
                  + sum(max(1, n) for _k, _p, n in fixed_layout) + n_lanes)
        # Erst die Grenzen setzen: Im Hauptfenster stellt der Splitter die Höhe dann sofort ein,
        # und es wird gleich mit der neuen Höhe gezeichnet (sonst ein zweites Mal über
        # _apply_resize). Ändert sich die Größe erst später, zeichnet _apply_resize wie bisher.
        self._fit_height_to_rows(top + (4 if bands else 0) + 6 + 8, n_rows)
        self._rendered_h = self.maximumViewportSize().height()
        free_h = self._rendered_h - self.horizontalScrollBar().sizeHint().height()
        fit = (free_h - top - (4 if bands else 0) - 6 - 8) / max(1, n_rows)
        lane_h, gap = type(self).LANE_H, type(self).LANE_GAP
        if fit < lane_h + gap:
            gap = 4
            lane_h = max(self.MIN_LANE_H, int(fit - gap))
        self.LANE_H, self.LANE_GAP = lane_h, gap
        row_h = self.LANE_H + self.LANE_GAP
        # Zeilen in der Reihenfolge aus den Einstellungen (in der Legende verschiebbar)
        heights = {k: max(1, n) for k, _p, n in band_layout + fixed_layout}
        tops = {}
        y = top
        for key in row_order(self.config):
            if key in heights:
                tops[key] = y
                y += heights[key] * row_h
        if bands:
            y += 4
        band_tops = [tops[k] for k, _p, _n in band_layout]
        fixed_tops = [tops[k] for k, _p, _n in fixed_layout]
        free_top = y + 6  # kleiner Abstand vor den freien Spuren
        content_h = free_top + n_lanes * row_h + 8
        height = max(content_h, free_h)
        width = self._x(24 * 60) + self.RIGHT

        # Außerhalb der Arbeitszeit abdunkeln (mit ITM-Personalzeiten auch die Pausen)
        spans = self._work_spans(date)
        work_start, work_end = self._work_minutes(date)
        no_pen = QPen(Qt.NoPen)
        prev = 0
        for span_start, span_end in spans + [(24 * 60, 24 * 60)]:
            if span_start > prev:
                self.scene.addRect(self._x(prev), 0, self._x(span_start) - self._x(prev), height,
                                   no_pen, QBrush(self.non_work_color))
            prev = max(prev, span_end)

        # Arbeitszeit: zarte Fläche im Akzent (statt eigener Zeile, die gibt es nur mit Zeiterfassung)
        work_tint = QColor(self.accent)
        work_tint.setAlpha(14 if self.dark_mode else 10)
        for span_start, span_end in spans:
            self.scene.addRect(self._x(span_start), self.AXIS_H, self._x(span_end) - self._x(span_start),
                               height, no_pen, QBrush(work_tint))

        # Stundenleiste, darunter die Arbeitszeit als feine Linie im Akzent
        self.scene.addRect(0, 0, width, self.AXIS_H, no_pen, QBrush(self.axis_bg))
        for span_start, span_end in spans:
            self.scene.addRect(self._x(span_start), self.AXIS_H - 3, self._x(span_end) - self._x(span_start),
                               3, no_pen, QBrush(self.accent))
        hour_font = ui_font(8)
        step = 1 if self._ppm * 60 >= 45 else 2
        for hour in range(25):
            x = self._x(hour * 60)
            self.scene.addLine(x, self.AXIS_H, x, height, QPen(self.hour_line, 1))
            if hour < 24 and self._ppm * 60 >= 60:
                xh = self._x(hour * 60 + 30)
                self.scene.addLine(xh, self.AXIS_H, xh, height, QPen(self.half_line, 1))
            if hour % step == 0 and hour < 24:
                label = self.scene.addSimpleText(f"{hour:02d}:00", hour_font)
                label.setBrush(
                    self.text_color if any(a <= hour * 60 < b for a, b in spans) else self.muted_text
                )
                label.setPos(x + 6, 7)

        # Zeilen unterscheidbar: feine Linien oder (Einstellung) jede zweite Zeile hinterlegt
        stripe = QColor(255, 255, 255, 10) if self.dark_mode else QColor(0, 0, 0, 10)
        # (eine feste Zeile mit Unterzeilen bleibt eine Fläche)
        row_tops = [(y, max(1, n)) for y, (_k, _p, n) in zip(fixed_tops, fixed_layout)]
        row_tops += [(free_top + i * row_h, 1) for i in range(n_lanes)]
        if self.config.get("timeline_stripes"):  # wie früher: jede zweite Zeile hinterlegt
            for i, (y, n) in enumerate(row_tops):
                if i % 2 == 0:
                    self.scene.addRect(0, y - self.LANE_GAP / 2, width, n * row_h, no_pen, QBrush(stripe))
        else:  # Standard: feine Linie zwischen den Zeilen
            line_pen = QPen(self.hour_line, 1)
            for y, _n in row_tops[1:]:
                self.scene.addLine(0, y - self.LANE_GAP / 2, width, y - self.LANE_GAP / 2, line_pen)

        # Legende links (schwebt über den Zeilen, siehe drawForeground) und Trennlinie
        colors = self.config.get("type_colors", {})
        own = self.config.get("row_colors") or {}
        legend, legend_keys = [], []
        if show_band:
            legend.append((band_y, pc_h, "PC-Aktivität", None))
            legend_keys.append("pc")
        # Name mittig über alle Unterzeilen einer Zeile
        for (kind, _text, band), y, (_k, _p, n) in zip(bands, band_tops, band_layout):
            name, key = LEGEND_BANDS[kind]
            legend.append((y, max(1, n) * row_h - self.LANE_GAP, name, own.get(kind) or colors.get(key)))
            legend_keys.append(kind)
        for (kind, _placed, n), y in zip(fixed_layout, fixed_tops):
            name, key = LEGEND_FIXED[kind]
            legend.append((y, max(1, n) * row_h - self.LANE_GAP, name, own.get(kind) or colors.get(key)))
            legend_keys.append(kind)
        if show_other:
            legend.append((free_top, self.LANE_H, "Remote / Weitere",
                           own.get("other") or colors.get("RDP-Verbindung")))
            legend_keys.append("other")
            sep_y = free_top - (6 + self.LANE_GAP) / 2
            if fixed_layout:
                self.scene.addLine(0, sep_y, width, sep_y, QPen(self.hour_line, 1))
        # Farbfeld = Farben, die in der Zeile wirklich vorkommen (Telefon z. B. blau und orange)
        used = {}
        for kind, items, _n in fixed_layout + band_layout:
            for a, _lane in items:
                c = entry_color(a, self.config).name().upper()
                if c not in used.setdefault(kind, []):
                    used[kind].append(c)
        legend = [(ly, lh, ln, (used[k][0] if len(used[k]) == 1 else tuple(used[k][:3])) if used.get(k) else lc)
                  for (ly, lh, ln, lc), k in zip(legend, legend_keys)]
        # Von oben nach unten sortiert (die Reihenfolge ist einstellbar)
        ordered = sorted(zip(legend, legend_keys), key=lambda pair: pair[0][0])
        self._legend = [entry for entry, _k in ordered]
        self._legend_keys = [k for _e, k in ordered]

        # Einträge
        label_font = ui_font(8)
        metrics = QFontMetrics(label_font)
        placed = [(a, y + lane * row_h) for (_k, items, _n), y in zip(fixed_layout, fixed_tops)
                  for a, lane in items]
        placed += [(a, free_top + lane * row_h) for a, lane in free_placed]
        for a, y in placed:
            start, end = parse_time(a["start"]), parse_time(a["end"])
            x1 = self._x(start.hour * 60 + start.minute + start.second / 60)
            x2 = self._x(end.hour * 60 + end.minute + end.second / 60)
            if end.date() > start.date():  # über Mitternacht
                x2 = self._x(24 * 60)
            w = max(4.0, x2 - x1)

            # Metro: volle Kachel ohne Rand, Schrift hell oder dunkel je nach Farbe
            base = entry_color(a, self.config)
            fill = QColor(base)
            pen = QPen(Qt.NoPen)
            label_color = readable_on(base)

            rect = self._add_block(x1, y, w, self.LANE_H, pen, QBrush(fill))
            rect.setData(0, a)
            rect.setCursor(Qt.PointingHandCursor)
            self.activity_rects[rect] = a

            label_text = a["customer_name"] or a["type"]
            if a.get("direction") in CALL_MARKS:  # Richtung auch als Form, nicht nur als Farbe
                label_text = f"{CALL_MARKS[a['direction']]} {label_text}"
            self._add_label(label_text, x1, y, w, self.LANE_H, label_font, metrics, label_color)

        # Obere Zeilen: Doku (eigene Tätigkeiten, offene gestrichelt), Regeln, KI
        for (_kind, items, _n), y in zip(band_layout, band_tops):
            for a, lane in items:
                self._draw_band_entry(a, y + lane * row_h, label_font, metrics)

        # PC-Aktivität: Arbeitsblöcke mit Beschriftung (oder schmales Band je Fenster)
        if show_band:
            for p in pc_band:
                start, end = parse_time(p["start"]), parse_time(p["end"])
                x1 = self._x(start.hour * 60 + start.minute + start.second / 60)
                x2 = self._x(end.hour * 60 + end.minute + end.second / 60)
                color = self.block_color(p)
                # 1 px Abstand zwischen Blöcken, damit sie als einzelne Kacheln lesbar bleiben
                w = max(1.5, x2 - x1 - (1 if p.get("pc_block") else 0))
                rect = self._add_block(x1, band_y, w, pc_h, QPen(Qt.NoPen), QBrush(color))
                rect.setCursor(Qt.PointingHandCursor)
                self.activity_rects[rect] = p
                if p.get("pc_block"):
                    self._add_label(p["label"], x1, band_y, w, pc_h, label_font, metrics,
                                    readable_on(color), p.get("short_labels", ()))

        # Leerer Tag: freundlicher Hinweis mitten im sichtbaren Ausschnitt
        if not placed and not pc_band and not any(band for _k, _t, band in bands) and not self.loading:
            title = self.scene.addSimpleText("Keine Spuren an diesem Tag", ui_font(11, bold=True))
            title.setBrush(self.text_color)
            sub = self.scene.addSimpleText("Kein PC-Verlauf, keine Verbindungen, keine Anrufe. "
                                           "Mit dem Stift trägst du trotzdem eine Tätigkeit nach.", ui_font(9))
            sub.setBrush(self.muted_text)
            if self.fit_day or self._first_draw:
                mid_x = (self._x(work_start) + self._x(work_end)) / 2 if work_end > work_start \
                    else self._x(12 * 60)
            else:
                mid_x = self.mapToScene(self.viewport().rect().center()).x()
            mid_y = (self.AXIS_H + height) / 2
            title.setPos(mid_x - title.boundingRect().width() / 2, mid_y - 24)
            sub.setPos(mid_x - sub.boundingRect().width() / 2, mid_y + 2)
            for item in (title, sub):
                item.setAcceptedMouseButtons(Qt.NoButton)

        # Jetzt-Linie
        if date == QDate.currentDate():
            now = QDateTime.currentDateTime().time()
            x = self._x(now.hour() * 60 + now.minute())
            line = self.scene.addLine(x, 0, x, height, QPen(self.now_color, 2))
            pill, label = self._add_now_pill(x, now.toString("HH:mm"), width)
            self._now_items = (line, pill, label, width, height)

        # Senkrechte Linie unter der Maus (erst bei Mausbewegung sichtbar)
        self._hover_line = self.scene.addLine(0, 0, 0, height, QPen(self.text_color, 1, Qt.DashLine))
        self._hover_line.setZValue(90)
        self._hover_line.hide()
        self._hover_label = self.scene.addText("", ui_font(8, bold=True))
        self._hover_label.setDefaultTextColor(self.text_color)
        self._hover_label.setZValue(91)
        self._hover_label.hide()
        self._day_entries = [a for a, _y in placed]  # nur die gezeichneten
        self._pc_band = pc_band
        self._ai_band = ai_band
        self._bands = bands

        self.setSceneRect(0, 0, width, height)

        if self.fit_day:
            self.horizontalScrollBar().setValue(0)
            self._first_draw = False
        elif self._first_draw:
            center = (work_start + work_end) / 2 if work_end > work_start else 12.5 * 60
            self.centerOn(self._x(center), 0)
            self._first_draw = False
        elif center_min is not None:
            self.centerOn(self._x(center_min), self.mapToScene(0, 0).y())

    def _stacked(self, items):
        """Einträge einer Zeile -> ([(Eintrag, Unterzeile)], Anzahl Unterzeilen)."""
        spans = [(parse_time(a["start"]), parse_time(a["end"])) for a in items]
        lanes, count = stack_lanes(spans, self.MAX_LANES)
        return list(zip(items, lanes)), count

    # Obere Zeilen: Kennung, Beschriftung links, Schlüssel in config["timeline_rows"]
    BAND_ROWS = [("work", "Personalzeit"), ("doc", "Doku"), ("m42", "Matrix42"), ("rule", "Zuordnung"), ("ai", "KI")]

    def band_rows(self, date: QDate):
        """Sichtbare obere Zeilen mit ihren Einträgen: [(Kennung, Text, Einträge)].

        Doku steht immer da (auch leer), damit offene Tätigkeiten sofort auffallen.
        Matrix42, Zuordnung (Regeln) und KI nur, wenn es Einträge gibt. Jede Zeile lässt sich abschalten.
        """
        date_str = date.toString("yyyy-MM-dd")
        shown = self.config.get("timeline_rows", {})
        sources = {"work": self.work_entries, "doc": self.doc_entries, "m42": self.m42_entries,
                   "rule": self.rule_entries,
                   "ai": self.ai_entries}
        result = []
        for kind, text in self.BAND_ROWS:
            func = sources[kind]
            if not func or not shown.get(kind, True):
                continue
            try:
                entries = func(date_str) or []
            except Exception as e:  # eine fehlerhafte Zeile darf die Timeline nicht leeren
                print(f"Fehler in der Zeile {text}: {e}")
                entries = []
            if kind == "work" and not any(e.get("from_itm") for e in entries):
                entries = []  # Arbeitszeit aus den Einstellungen: nur Fläche und Linie unter den Uhrzeiten
            if entries or kind == "doc":
                result.append((kind, text, entries))
        return result

    MIN_LABEL_CHARS = 6  # weniger lesbare Zeichen: lieber keine Beschriftung als „Chro…“

    def _add_label(self, text, x, y, w, h, font, metrics, color, alternatives=()):
        """Beschriftung in einem Balken; zu wenig Platz: kürzere Alternative, sonst keine
        (der Name steht im Hinweis beim Darüberfahren)."""
        text = _first_line(text)
        alternatives = tuple(_first_line(t) for t in alternatives if t)
        if w < 28 or not text:
            return None
        room = int(w - 8)
        fitting = [t for t in (text, *alternatives) if t and metrics.horizontalAdvance(t) <= room]
        if fitting:
            shown = fitting[0]
        else:
            shown = metrics.elidedText(text, Qt.ElideRight, room)
            visible = shown.rstrip("…").strip(" ?✓·↙↗")
            if len(visible) < min(self.MIN_LABEL_CHARS, len(text.strip(" ?✓·↙↗"))):
                return None
        item = self.scene.addSimpleText(shown, font)
        item.setBrush(color)
        item.setPos(x + 6, y + (h - metrics.height()) / 2)
        item.setAcceptedMouseButtons(Qt.NoButton)
        return item

    def _draw_band_entry(self, a, y, font, metrics):
        start, end = parse_time(a["start"]), parse_time(a["end"])
        x1 = self._x(start.hour * 60 + start.minute)
        x2 = self._x(24 * 60) if end.date() > start.date() else self._x(end.hour * 60 + end.minute)
        w = max(4.0, x2 - x1)
        base = entry_color(a, self.config)
        fill = QColor(base)
        # Deckkraft der halb durchsichtigen Kacheln (Regeln, KI, offene, Lücken): kräftig statt pastell
        light = 175 if self.dark_mode else 150
        label_color = self.text_color
        if a.get("work") and (not a.get("from_itm") or a.get("missing_end")):
            # Arbeitszeit aus den Einstellungen oder Ende unbekannt (Gehen fehlt): nur Rahmen
            fill.setAlpha(light // 2)
            pen = QPen(base, 1.2, Qt.DashLine)
        elif a.get("m42_gap"):  # Personalzeit ohne Buchung: fällt auf
            fill.setAlpha(light // 2)
            pen = QPen(base, 1.5, Qt.DashLine)
        elif a.get("doc") or a.get("m42") or a.get("work") or a.get("status") == "übernommen":  # volle Kachel
            pen = QPen(Qt.NoPen)
            label_color = readable_on(base)
        elif a.get("open"):  # noch nicht dokumentiert: fällt auf, lädt zum Klicken ein
            fill.setAlpha(light // 2)
            pen = QPen(base, 1.5, Qt.DashLine)
        elif a.get("rule"):
            fill.setAlpha(light)
            pen = QPen(base, 1.2, Qt.DashDotLine)
        else:  # KI-Vorschlag
            fill.setAlpha(light)
            pen = QPen(base, 1.5, Qt.DotLine)
        if fill.alpha() < 255:  # Schrift passend zur gemischten Fläche (kräftige Farben)
            label_color = readable_on(_blend(fill, self.background_color))
        rect = self._add_block(x1, y, w, self.LANE_H, pen, QBrush(fill))
        rect.setCursor(Qt.PointingHandCursor)
        self.activity_rects[rect] = a
        if w > 28:
            if a.get("work"):
                label_text = a["customer_name"]
            elif a.get("m42_gap"):
                label_text = "nicht gebucht"
            elif a.get("m42"):
                label_text = " · ".join(t for t in (a.get("customer_name"), a.get("description")) if t) \
                    or a.get("category") or "Buchung"
            elif a.get("cluster"):
                label_text = f"? {len(a['cluster'])} offen"
            elif a.get("open"):
                label_text = f"? {a.get('customer_name') or 'eintragen'}"
            elif a.get("doc"):  # Form statt nur Farbe: ✓ dokumentiert, ? offen
                label_text = "✓ " + (" · ".join(t for t in (a.get("customer_name"), a.get("description"))
                                                if t) or a.get("category") or "Tätigkeit")
            else:
                label_text = " · ".join(t for t in (a.get("customer_name"), a.get("category"),
                                                    a.get("description") if a.get("doc") else "")
                                        if t) or a.get("type", "")
            self._add_label(label_text, x1, y, w, self.LANE_H, font, metrics, label_color)

    def _fit_height_to_rows(self, fixed_h, n_rows):
        """Höhe der Timeline an die Zeilen binden: kleinste Höhe = alle Zeilen in der
        Mindesthöhe (nichts wird abgeschnitten), größte = alle Zeilen in voller Höhe."""
        chrome = (self.height() - self.maximumViewportSize().height()
                  + self.horizontalScrollBar().sizeHint().height())
        rows = max(1, n_rows)
        low = int(chrome + fixed_h + rows * (self.MIN_LANE_H + 4))
        high = int(chrome + fixed_h + rows * (type(self).LANE_H + type(self).LANE_GAP))
        if (low, high) != (self.minimumHeight(), self.maximumHeight()):
            self.setMinimumHeight(low)
            self.setMaximumHeight(max(low, high))
            self.height_limits_changed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._ppm:
            self._resize_timer.start()  # beim Ziehen nicht bei jedem Pixel neu zeichnen

    def _apply_resize(self):
        # Ganzer Tag: Breite mitziehen; sonst Zeilenhöhe an die neue Höhe anpassen
        if self._ppm and (
            (self.fit_day and abs(self._ppm - self._fit_ppm()) > 0.01)
            or self.maximumViewportSize().height() != self._rendered_h
        ):
            self.relayout()

    # ----------------------------- Ansicht / Zoom -----------------------------

    def _fit_ppm(self):
        """Pixel pro Minute, damit 0–24 Uhr genau ins Fenster passt."""
        width = self.maximumViewportSize().width() - self.LEFT - self.RIGHT - 4
        return max(0.2, width / (24 * 60))

    def show_whole_day(self):
        self.fit_day = True
        self.relayout()

    def show_range(self, start_min, end_min):
        """Zeitraum (Minuten seit 0 Uhr) genau ins Fenster einpassen."""
        start_min, end_min = max(0, min(start_min, end_min)), min(24 * 60, max(start_min, end_min))
        if end_min - start_min < 5:
            return
        width = self.maximumViewportSize().width() - self.LEFT - self.RIGHT - 4
        self.fit_day = False
        self.zoom_level = max(1.0, width / (end_min - start_min)) / self.BASE_PX_PER_MIN
        self.zoom_level = min(self.zoom_level, 30.0)
        self._first_draw = False
        self.relayout()
        self.horizontalScrollBar().setValue(int(self._x(start_min) - self.LEFT))

    def show_work_time(self):
        start, end = self._work_minutes(self.current_date)
        if end > start:
            self.show_range(start - 30, end + 30)
        else:
            self.show_whole_day()

    def set_zoom(self, level, anchor_viewport_x=None):
        fit_level = self._fit_ppm() / self.BASE_PX_PER_MIN
        if level <= fit_level * 1.01:  # weiter raus als "ganzer Tag" geht nicht
            self.show_whole_day()
            return
        level = min(level, 30.0)
        self.fit_day = False
        if anchor_viewport_x is None:
            self.zoom_level = level
            self.relayout()
            return
        # Zeitpunkt unter der Maus bleibt an derselben Stelle
        scene_x = self.mapToScene(int(anchor_viewport_x), 0).x()
        minute = (scene_x - self.LEFT) / self._ppm
        self.zoom_level = level
        self._first_draw = False
        self.relayout()
        target = self._x(minute) - anchor_viewport_x
        self.horizontalScrollBar().setValue(int(target))

    def _apply_wheel_zoom(self):
        if self._wheel_zoom:
            level, x = self._wheel_zoom
            self._wheel_zoom = None
            self.set_zoom(level, x)

    # Platzhalter vor dem ersten Zeichnen: (Beginn, Länge) als Anteil der Tagesbreite je Zeile
    SKELETON_ROWS = (((0.02, 0.14), (0.17, 0.22), (0.41, 0.09), (0.52, 0.27), (0.81, 0.15)),
                     ((0.06, 0.20), (0.48, 0.16), (0.70, 0.12)),
                     ((0.10, 0.05), (0.24, 0.07), (0.39, 0.04), (0.58, 0.06), (0.77, 0.05)),
                     ((0.03, 0.31), (0.57, 0.33)),
                     ((0.15, 0.12), (0.36, 0.18), (0.66, 0.08)),
                     ((0.08, 0.10), (0.45, 0.14)))

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        if self._skeleton:
            self._paint_skeleton(painter)
            if getattr(self, "_load_after_paint", False):  # Umrisse stehen: jetzt lesen
                QTimer.singleShot(0, self._start_load_after_paint)

    def _paint_skeleton(self, painter):
        """Umrisse von Stundenleiste, Legende und Zeilen, bis die Daten gezeichnet sind."""
        painter.save()
        painter.resetTransform()
        vp = self.viewport().rect()
        painter.fillRect(vp, self.background_color)
        painter.setRenderHint(QPainter.Antialiasing, True)
        fill = skeleton.color(self.text_color)
        left, right = self.LEFT, max(self.LEFT + 100, vp.width() - self.RIGHT)
        span = right - left
        painter.setPen(QPen(self.hour_line, 1))
        painter.drawLine(0, self.AXIS_H, vp.width(), self.AXIS_H)
        for i in range(12):  # Uhrzeiten oben
            x = left + span * i / 12
            skeleton.bar(painter, QRectF(x + 6, 9, 30, 8), fill, 4)
        y = self.AXIS_H + 6
        row_h = self.LANE_H + self.LANE_GAP
        for i, row in enumerate(self.SKELETON_ROWS):
            h = self.PC_BAND_H if i == 0 else self.LANE_H
            if y + h > vp.height():
                break
            skeleton.bar(painter, QRectF(10, y + h / 2 - 5, 64 + (i * 13) % 30, 10), fill, 5)  # Legende
            for start, length in row:
                skeleton.bar(painter, QRectF(left + span * start, y, span * length, h), fill, 5)
            y += (h + 10) if i == 0 else row_h
        painter.restore()

    def _end_skeleton(self):
        if self._skeleton:
            self._skeleton = False
            skeleton.pulse().unwatch(self.viewport())

    def drawForeground(self, painter, rect):
        """Legende links: Name und Farbe jeder Zeile, bleibt beim Blättern stehen."""
        super().drawForeground(painter, rect)
        if not self._legend:
            return
        painter.save()
        painter.resetTransform()  # ab hier Koordinaten des Fensters, nicht der Szene
        font = ui_font(8)  # normal statt fett: die Balken stehen im Vordergrund
        painter.setFont(font)
        fm = QFontMetrics(font)
        width = self.LEFT - 6
        top = self.mapFromScene(0, self.AXIS_H).y()
        last_y, last_h = self._legend[-1][0], self._legend[-1][1]
        bottom = min(self.viewport().height(), self.mapFromScene(0, last_y + last_h).y() + 6)
        panel = QColor(self.background_color)
        panel.setAlpha(232)
        painter.fillRect(0, top, width, max(0, bottom - top), panel)
        painter.fillRect(0, 0, width, top, QColor(self.background_color))  # Zeitachse unter der Legende
        painter.setPen(QPen(self.hour_line, 1))
        painter.drawLine(width, top, width, bottom)
        for y, h, name, color in self._legend:
            center = self.mapFromScene(0, y + h / 2).y()
            if center < top or center > bottom:
                continue
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)
            if isinstance(color, tuple):  # mehrere Farben: kleine Punkte nebeneinander
                for i, c in enumerate(color):
                    painter.setBrush(QColor(c))
                    painter.drawEllipse(QPointF(12 + i * 4, center), 3.5, 3.5)
            elif color:
                painter.setBrush(QColor(color))
                painter.drawEllipse(QPointF(12, center), 4, 4)
            else:  # PC: mehrere Programme, kleine Streifen
                for i, c in enumerate(self.APP_COLORS[:3]):
                    painter.fillRect(8 + i * 3, center - 4, 2, 8, QColor(c))
            painter.setPen(self.text_color)
            painter.drawText(26 if isinstance(color, tuple) and len(color) > 2 else 22, center + (fm.ascent() - fm.descent()) // 2,
                             fm.elidedText(name, Qt.ElideRight, width - 26))
        if self._row_drag is not None:  # Zeile wird verschoben: Linie, wo sie landet
            target, below = self._row_drop(self._row_drag[1])
            entry = next(((y, h) for (y, h, _n, _c), k in zip(self._legend, self._legend_keys)
                          if k == target), None)
            if entry:
                line_y = self.mapFromScene(0, entry[0] + (entry[1] + self.LANE_GAP / 2 if below
                                                          else -self.LANE_GAP / 2)).y()
                accent = QColor(theme_for(self.config)["accent"])
                painter.setPen(QPen(accent, 3))
                painter.drawLine(4, line_y, self.viewport().width(), line_y)
        painter.restore()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        # Nur den Legendenstreifen neu zeichnen, sonst wandert sie beim Blättern mit.
        # Nicht die ganze Fläche: Qt verschiebt den Rest als Bild, das hält Blättern flüssig.
        # + |dx|: die mitgeschobene alte Legende rechts daneben ebenfalls übermalen
        self.viewport().update(0, 0, self.LEFT + abs(dx) + 2, self.viewport().height())

    def wheelEvent(self, event):
        """STRG + Mausrad: Zoom, UMSCHALT + Mausrad: Zeilen, Mausrad: horizontal blättern."""
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.ControlModifier:
            if delta:
                factor = 1.15 if delta > 0 else 1 / 1.15
                level = (self._wheel_zoom[0] if self._wheel_zoom else self.zoom_level) * factor
                self._wheel_zoom = (level, event.position().x())
                self._wheel_timer.start()  # schnelles Drehen: nur einmal zeichnen
        elif delta and event.modifiers() & Qt.ShiftModifier:  # ohne Scrollleiste: Zeilen blättern
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - delta)
        elif delta:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - delta)
        else:
            super().wheelEvent(event)

    def _activity_at(self, pos):
        for item in self.scene.items(self.mapToScene(pos)):
            if isinstance(item, QGraphicsRectItem) and item in self.activity_rects:
                return self.activity_rects[item]
        return None

    def _minute_at(self, viewport_x):
        return (self.mapToScene(int(viewport_x), 0).x() - self.LEFT) / self._ppm

    def _legend_key_at(self, viewport_y):
        """Kennung der Legendenzeile unter der Maus (oder None)."""
        y = self.mapToScene(0, int(viewport_y)).y()
        for (top, h, _name, _color), key in zip(self._legend, self._legend_keys):
            if top - self.LANE_GAP <= y <= top + h + self.LANE_GAP:
                return key
        return None

    def _row_drop(self, viewport_y):
        """(Ziel, darunter?) für die gezogene Zeile an dieser Höhe."""
        y = self.mapToScene(0, int(viewport_y)).y()
        rows = [(top, h, key) for (top, h, _n, _c), key in zip(self._legend, self._legend_keys)
                if key in MOVABLE_ROWS]
        if not rows:
            return None, False
        for top, h, key in rows:
            if y < top + h / 2:
                return key, False
        return rows[-1][2], True

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._row_drag is not None:
            self._row_drag[1] = pos.y()
            self.viewport().update()  # Linie reicht über die ganze Breite
            return
        in_legend = bool(self._legend) and pos.x() < self.LEFT - 6 and self._drag_start is None
        if in_legend:  # Hand über verschiebbaren Zeilen, sonst Pfeil (auch über Balken darunter)
            if self._legend_key_at(pos.y()) in MOVABLE_ROWS:
                self.viewport().setCursor(Qt.OpenHandCursor)
            else:
                self.viewport().setCursor(Qt.ArrowCursor)
            self._legend_cursor = True
        elif self._legend_cursor:
            # Hand nur über der Legende; sonst merkt sich QGraphicsView sie als Grundzeiger
            # und zeigt sie überall statt des Pfeils
            self.viewport().unsetCursor()
            self._legend_cursor = False
        # Klicken und ziehen: Bereich markieren (links: Tätigkeit, rechts: Zoom)
        if self._drag_start is not None and abs(pos.x() - self._drag_start.x()) > 5:
            self._hide_hover()
            x1 = self.mapToScene(self._drag_start).x()
            x2 = self.mapToScene(pos).x()
            rect = self.sceneRect()
            zoom = self._drag_button == Qt.RightButton
            if self._drag_item is None:
                color = QColor("#0078D7" if zoom else "#18B34B")
                fill = QColor(color)
                fill.setAlpha(50)
                self._drag_item = self.scene.addRect(0, 0, 0, 0, QPen(color, 1), QBrush(fill))
                self._drag_item.setZValue(100)
            self._drag_item.setRect(min(x1, x2), 0, abs(x2 - x1), rect.height())
            a, b = self._drag_minutes(self._drag_start.x(), pos.x())
            hint = "Loslassen: diesen Zeitraum zeigen" if zoom else "Loslassen: Tätigkeit eintragen"
            self.tooltip.setText(f"<b>{hhmm(a)} – {hhmm(b)}</b> ({format_duration((b - a) * 60)})"
                                 f"<br><i>{hint}</i>")
            self.tooltip.adjustSize()
            self._move_tooltip(pos)
            self.tooltip.show()
            return

        minute = self._minute_at(pos.x()) if self._ppm else -1
        if 0 <= minute < 24 * 60:
            self._show_hover_line(minute)
            self.tooltip.setText(self._hover_text(minute, self._activity_at(pos)))
            self.tooltip.adjustSize()
            self._move_tooltip(pos)
            self.tooltip.show()
        else:
            self._hide_hover()
        if not in_legend:  # Balken unter der Legende sollen dort keinen Zeiger setzen
            super().mouseMoveEvent(event)

    def _add_now_pill(self, x, text, width):
        """Rote Pille mit weißer Uhrzeit oben in der Stundenleiste, wandert mit der Linie."""
        font = ui_font(8, bold=True)
        metrics = QFontMetrics(font)
        w, h = metrics.horizontalAdvance(text) + 12, self.AXIS_H - 8
        left = max(0, min(x - w / 2, width - w))
        path = QPainterPath()
        path.addRoundedRect(left, 4, w, h, h / 2, h / 2)
        pill = self.scene.addPath(path, QPen(Qt.NoPen), QBrush(now_pill_color(self.now_color)))
        pill.setZValue(80)
        label = self.scene.addSimpleText(text, font)
        label.setBrush(QColor("#FFFFFF"))
        label.setPos(left + 6, 4 + (h - metrics.height()) / 2)
        label.setZValue(81)
        return pill, label

    def _schedule_now_tick(self):
        """Kurz nach dem nächsten Minutenwechsel _tick_now aufrufen."""
        sec = QDateTime.currentDateTime().time().second()
        self._now_timer.start((60 - sec) * 1000 + 200)

    def _tick_now(self):
        """Jetzt-Linie und Pille auf die aktuelle Minute setzen."""
        self._schedule_now_tick()
        if not self._now_items or self.current_date != QDate.currentDate():
            return
        line, pill, label, width, height = self._now_items
        now = QDateTime.currentDateTime().time()
        x = self._x(now.hour() * 60 + now.minute())
        line.setLine(x, 0, x, height)
        self.scene.removeItem(pill)
        self.scene.removeItem(label)
        pill, label = self._add_now_pill(x, now.toString("HH:mm"), width)
        self._now_items = (line, pill, label, width, height)

    def _show_hover_line(self, minute):
        if not self._hover_line:
            return
        x = self._x(minute)
        rect = self.sceneRect()
        self._hover_line.setLine(x, self.AXIS_H, x, rect.height())
        self._hover_line.show()
        # Uhrzeit oben in der Stundenleiste, mit Hintergrund damit sie lesbar bleibt
        self._hover_label.setHtml(
            f'<span style="background-color:{self.axis_bg.name()}">&nbsp;{hhmm(minute)}&nbsp;</span>')
        w = self._hover_label.boundingRect().width()
        self._hover_label.setPos(max(0, min(x - w / 2, rect.width() - w)), 1)
        self._hover_label.show()

    def _hide_hover(self):
        self.tooltip.hide()
        if self._hover_line:
            self._hover_line.hide()
            self._hover_label.hide()

    def _move_tooltip(self, pos):
        """Hinweis neben die Maus, am rechten/unteren Bildschirmrand auf die andere Seite."""
        gp = self.mapToGlobal(pos)
        x, y = gp.x() + 15, gp.y() + 15
        screen = self.screen().availableGeometry() if hasattr(self, "screen") else None
        if screen is not None:
            if x + self.tooltip.width() > screen.right():
                x = gp.x() - 15 - self.tooltip.width()
            if y + self.tooltip.height() > screen.bottom():
                y = gp.y() - 15 - self.tooltip.height()
        self.tooltip.move(x, y)

    def _customer_line(self, entry):
        """Kunde aus der Kundenliste, wenn er nicht schon im Namen steht (sonst nichts)."""
        if entry.get("tv_id"):
            return []
        try:
            index = customers.index(self.config, self.imported.customers() if self.imported else None)
        except Exception:  # Anzeige darf nie am Hinweis scheitern
            return []
        text = customers.with_customer(entry, index)
        if text == (entry.get("customer_name") or ""):
            return []
        return [f"Kunde: {escape(index.customer_for(entry))}"]

    def _swatch(self, entry):
        """Farbquadrat wie der Balken in der Timeline (Text daneben bleibt, Farbe nur zusätzlich)."""
        try:
            pc = entry.get("pc_block") or ("app" in entry and any(p is entry for p in self._pc_band))
            color = self.block_color(entry) if pc else entry_color(entry, self.config)
        except Exception:  # Anzeige darf nie am Hinweis scheitern
            return ""
        return f'<span style="color:{color.name()}">■</span>&nbsp;'

    def _hover_text(self, minute, hovered=None):
        """Hinweis zur Linie: Uhrzeit, Personalzeit und alles, was zu dieser Minute lief."""
        date_str = self.current_date.toString("yyyy-MM-dd")
        moment = parse_time(f"{date_str} {hhmm(minute)}:00")
        lines = [f"<b>{hhmm(minute)} Uhr</b>"]
        if not any(k == "work" for k, _t, _e in self._bands):  # Zeile aus: Personalzeit im Hinweis
            lines.append(self._work_text(minute))

        if hovered:  # Eintrag direkt unter der Maus: ausführlich
            start, end = parse_time(hovered["start"]), parse_time(hovered["end"])
            lines += ["", f"{self._swatch(hovered)}<b>{escape(hovered.get('customer_name') or hovered.get('type'))}</b>",
                      escape(type_label(hovered)),
                      *self._customer_line(hovered),
                      f"{start:%H:%M} – {end:%H:%M}  ({format_duration((end - start).total_seconds())})"]
            if hovered.get("work"):
                if hovered.get("missing_end"):
                    lines.append("<i>Gehen fehlt in ITM, Ende geschätzt</i>")
                else:
                    lines.append("<i>Eingestempelt (ITM)</i>" if hovered.get("from_itm")
                                 else "<i>Arbeitszeit aus den Einstellungen</i>")
            elif hovered.get("m42"):
                lines.append(escape(hovered.get("details", "")))
                lines.append("<i>In Matrix42 gebucht</i>")
            elif hovered.get("m42_gap"):
                lines.append(escape(hovered.get("details", "")))
                lines.append("<i>Nicht gebucht · Rechtsklick: Tätigkeit eintragen</i>")
            elif hovered.get("cluster"):
                for e in hovered["cluster"][:8]:
                    lines.append(f"{self._swatch(e.get('source_entry', e))}"
                                 f"{parse_time(e['start']):%H:%M}–{parse_time(e['end']):%H:%M}  "
                                 f"{escape(e.get('customer_name') or type_label(e.get('source_entry', e)))}")
                if len(hovered["cluster"]) > 8:
                    lines.append(f"<i>… und {len(hovered['cluster']) - 8} weitere</i>")
                lines.append("<i>Noch nicht dokumentiert · Klick: das erste eintragen</i>")
            elif hovered.get("open"):
                lines.append("<i>Noch nicht dokumentiert · Klick: jetzt eintragen</i>")
            elif hovered.get("doc"):
                if hovered.get("description"):
                    lines.append(escape(hovered["description"]))
                lines.append("<i>Deine Tätigkeit · Klick: bearbeiten</i>")
            elif hovered.get("rule"):
                lines.append(escape(hovered.get("description") or hovered.get("details", "")))
                lines.append("<i>Automatisch zugeordnet (feste Regel, ohne KI)"
                             " · Rechtsklick: als Tätigkeit eintragen</i>")
            elif hovered.get("ai"):
                lines.append(escape(hovered.get("description", "")))
                lines.append(f"<i>KI-Vorschlag, Sicherheit {round(hovered.get('confidence', 0) * 100)} %"
                             " · Rechtsklick: übernehmen oder verwerfen</i>")
            elif hovered.get("pc_block"):
                total = sum(sec for _n, sec in hovered["parts"]) or 1
                for name, sec in hovered["parts"][:5]:
                    lines.append(f"{escape(name)}  {format_duration(sec)}  ({round(sec * 100 / total)} %)")
                if len(hovered["parts"]) > 5:
                    lines.append(f"<i>… und {len(hovered['parts']) - 5} weitere Programme</i>")
                lines.append(f"<i>Arbeitsblock am PC · {hovered['switches']} Fensterwechsel · "
                             f"Fokus {round(hovered['focus'] * 100)} %</i>")
            elif hovered.get("details"):
                lines.append(escape(hovered["details"]))
            if hovered.get("pc_block"):
                pass  # kein „Vorschlag aus Log“
            elif hovered.get("is_suggestion") and not any(hovered.get(k) for k in ("ai", "rule", "open", "work",
                                                                                 "m42", "m42_gap")):
                lines.append("<i>Vorschlag aus Log</i>")

        # Weitere Einträge, die zu dieser Minute liefen (Minute zählt, nicht die Sekunde)
        band_entries = [a for _k, _t, band in self._bands for a in band]
        others = [a for a in band_entries + self._day_entries if a is not hovered
                  and parse_time(a["start"]).replace(second=0) <= moment < parse_time(a["end"])]
        if not any(p is hovered for p in self._pc_band):
            others += [p for p in self._pc_band
                       if parse_time(p["start"]).replace(second=0) <= moment < parse_time(p["end"])][:1]
        if others:
            lines.append("")
            for a in others[:8]:
                lines.append(f"{self._swatch(a)}{parse_time(a['start']):%H:%M}–{parse_time(a['end']):%H:%M}  "
                             f"{escape(type_label(a))}: {escape(a.get('customer_name') or '')}")
            if len(others) > 8:
                lines.append(f"<i>… und {len(others) - 8} weitere</i>")
        elif not hovered:
            lines.append("<i>Keine Einträge</i>")
        return "<br>".join(lines)

    def leaveEvent(self, event):
        self._hide_hover()
        if self._legend_cursor and self._row_drag is None:
            self.viewport().unsetCursor()
            self._legend_cursor = False
        super().leaveEvent(event)

    def _drag_minutes(self, x1, x2):
        """Gezogener Bereich in ganzen Minuten seit 0 Uhr (innerhalb des Tages)."""
        a, b = sorted((self._minute_at(x1), self._minute_at(x2)))
        return max(0, round(a)), min(24 * 60, round(b))

    def _cancel_drag(self):
        self._drag_start = self._drag_button = None
        if self._drag_item is not None:
            self.scene.removeItem(self._drag_item)
            self._drag_item = None
        self.tooltip.hide()

    def mousePressEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.RightButton) and self._ppm:
            if self._drag_start is not None:  # zweite Taste während des Ziehens: abbrechen
                self._cancel_drag()
                return
            pos = event.position().toPoint()
            if event.button() == Qt.RightButton and self._legend and pos.x() < self.LEFT - 6:
                return  # Legende: Menü beim Loslassen, kein Bereich
            if event.button() == Qt.LeftButton and self._legend and pos.x() < self.LEFT - 6:
                key = self._legend_key_at(pos.y())  # Legende: Zeile verschieben
                if key in MOVABLE_ROWS:
                    self._row_drag = [key, pos.y()]
                    self.viewport().setCursor(Qt.ClosedHandCursor)
                    self._legend_cursor = True
                return
            self._drag_start, self._drag_button = pos, event.button()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        button = event.button()
        pos = event.position().toPoint()
        if self._row_drag is not None and button == Qt.LeftButton:
            key = self._row_drag[0]
            self._row_drag = None
            self.viewport().unsetCursor()
            self._legend_cursor = False  # nächste Mausbewegung setzt die Hand wieder, falls nötig
            target, below = self._row_drop(pos.y())
            if target and target != key:
                self.row_order_changed.emit(moved(row_order(self.config), key, target, below))
            self.viewport().update()
            return
        if button == Qt.RightButton and self._drag_start is None:  # Legende oder abgebrochen
            if self._legend and pos.x() < self.LEFT - 6:
                self._show_menu(pos, event.globalPosition().toPoint())
            return
        if button != self._drag_button or self._drag_start is None:
            super().mouseReleaseEvent(event)
            return
        start = self._drag_start
        dragged = self._drag_item is not None
        self._cancel_drag()
        if dragged:
            a, b = self._drag_minutes(start.x(), pos.x())
            if button == Qt.RightButton:  # rechts gezogen -> diesen Bereich zeigen
                self.show_range(a, b)
            elif b > a:  # links gezogen -> Tätigkeit für diesen Zeitraum eintragen
                self.doc_request.emit("add_range", {"start_min": a, "end_min": b})
            return
        if button == Qt.RightButton:  # einfacher Rechtsklick -> Menü
            self._show_menu(pos, event.globalPosition().toPoint())
            return
        a = self._activity_at(pos)  # einfacher Klick -> Details
        if a:
            if a.get("open"):  # offene Tätigkeit: gleich eintragen
                self.doc_request.emit("add", a["source_entry"])
            elif a.get("m42_gap"):  # nicht gebucht: Tätigkeit ab hier eintragen
                self.doc_request.emit("add_at", a)
            elif a.get("doc"):
                self.doc_request.emit("edit", a)
            else:
                ActivityViewDialog(a, self).exec()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self._row_drag is not None:
            self._row_drag = None
            self.viewport().update()
            return
        if event.key() == Qt.Key_Escape and self._drag_start is not None:
            self._cancel_drag()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        """Menütaste der Tastatur; mit der Maus kommt das Menü beim Loslassen (Rechtsziehen = Zoom)."""
        if event.reason() == QContextMenuEvent.Mouse:
            event.accept()
            return
        self._show_menu(event.pos(), event.globalPos())

    def _show_menu(self, pos, global_pos):
        """Rechtsklick: dasselbe Menü wie in der Tagesliste (entry_menu_items)."""
        if self._legend and pos.x() < self.LEFT - 6:  # Legende: Zeilen ein-/ausblenden
            self._hide_hover()
            self.rows_menu_requested.emit(global_pos, self._legend_key_at(pos.y()) or "")
            return
        a = self._activity_at(pos)
        self._hide_hover()
        if a is None:
            minute = self._minute_at(pos.x()) if self._ppm else -1
            if not 0 <= minute < 24 * 60:
                return
            a = {"minute": minute}
        key = exec_entry_menu(self, a, global_pos)
        if key:
            self.entry_action.emit(key, a)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and not self._activity_at(event.position().toPoint()):
            self.show_whole_day()
            return
        super().mouseDoubleClickEvent(event)
