# timeline_only.py
import threading
import time
from datetime import datetime
from html import escape

from PySide6.QtCore import QDate, QDateTime, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QContextMenuEvent, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QGraphicsRectItem,
                               QGraphicsScene, QGraphicsView, QLabel, QLineEdit, QMenu,
                               QTextEdit, QVBoxLayout)

from activity_tracker import app_label, merge_segments, read_segments
from call_import import load_call_suggestions
import focus
import customers
from grouping import format_tv_id, group_entries
from log_parsers import ConnectionIndex, RdmParser, TeamViewerParser, VpnParser
from theme import THEMES, readable_on, ui_font
from vpn_reader import VpnReader, vpn_sources

TIME_FMT = "%Y-%m-%d %H:%M:%S"


def parse_time(text):
    """'JJJJ-MM-TT hh:mm:ss' -> datetime. Streng wie strptime, aber viel schneller."""
    if len(text) != 19 or text[10] != " ":
        raise ValueError(f"Ungültige Zeit: {text!r}")
    return datetime.fromisoformat(text)


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
    """Farbe eines Eintrags: Telefonate nach Richtung, sonst nach Aktivitätstyp."""
    direction = activity.get("direction")
    if direction:
        colors = {**DEFAULT_CALL_COLORS, **config.get("call_colors", {})}
        if direction in colors:
            return QColor(colors[direction])
    return QColor(config.get("type_colors", {}).get(activity.get("type"), "#4682B4"))


# Eigene Zeile je Quelle (Kennung, Beschriftung links); nur RDM und der Rest teilen sich mehrere Spuren
# Outlook (Termine, Mails) nur, wenn die Datenquelle an ist (sonst bliebe die Zeile leer)
FIXED_ROWS = [("call", "Tel"), ("outlook", "Outlook"), ("vpn", "VPN"), ("tv", "TV")]
OUTLOOK_TYPES = ("Termin", "Teams-Besprechung", "Mail gesendet")
# Legende links: Name der Zeile und Schlüssel in config["type_colors"] für das Farbfeld
LEGEND_FIXED = {"call": ("Telefon", "Telefonat"), "outlook": ("Outlook", "Termin"),
                "vpn": ("VPN", "VPN-Verbindung"),
                "tv": ("TeamViewer", "TeamViewer")}
LEGEND_BANDS = {"work": ("Personalzeit", "Personalzeit"), "doc": ("Dokumentation", "Dokumentiert"), "m42": ("Matrix42", "Matrix42-Buchung"),
                "rule": ("Zuordnung o. KI", "Klassifizierung"), "ai": ("KI-Vorschläge", "KI-Vorschlag")}

# Alle Zeilen der Timeline in der Reihenfolge von oben nach unten: Schlüssel in
# config["timeline_rows"], Text im Menü. Jede lässt sich einzeln aus- und einblenden.
TIMELINE_ROWS = [
    ("pc", "&PC-Aktivität (aktive Fenster)"),
    ("work", "P&ersonalzeit (ITM, sonst Arbeitszeit)"),
    ("doc", "&Dokumentation (eigene Tätigkeiten)"),
    ("m42", "&Matrix42 (gebucht / nicht gebucht)"),
    ("rule", "&Zuordnung ohne KI (feste Regeln)"),
    ("ai", "&KI-Vorschläge"),
    ("call", "&Telefon (3CX, Teams)"),
    ("outlook", "&Outlook (Termine, Mails)"),
    ("vpn", "&VPN"),
    ("tv", "T&eamViewer"),
    ("other", "&Remote / Weitere (RDM, SSH, RDP …)"),
]
ROW_NAMES = {"pc": "PC-Aktivität", "work": "Personalzeit", "doc": "Dokumentation", "m42": "Matrix42", "rule": "Zuordnung ohne KI",
             "ai": "KI-Vorschläge", "call": "Telefon", "outlook": "Outlook", "vpn": "VPN", "tv": "TeamViewer",
             "other": "Remote / Weitere"}


def row_kind(activity):
    """Feste Zeile eines Eintrags ("call", "outlook", "vpn", "tv") oder None für die freien Spuren."""
    kind = activity.get("type", "")
    if activity.get("direction") or kind == "Telefonat":
        return "call"
    if kind in OUTLOOK_TYPES:
        return "outlook"
    if kind.startswith("VPN"):
        return "vpn"
    if kind.startswith("TeamViewer"):
        return "tv"
    return None


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


class ActivityViewDialog(QDialog):
    """Nur-Anzeigen-Dialog zum Kopieren von Aktivitätsdaten."""

    def __init__(self, activity, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aktivitätsdetails")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        def ro_field(text):
            w = QLineEdit(text)
            w.setReadOnly(True)
            return w

        try:
            start = parse_time(activity["start"])
            end = parse_time(activity["end"])
            zeit = f"{start:%d.%m.%Y}, {start:%H:%M} – {end:%H:%M}"
            dauer = format_duration((end - start).total_seconds())
        except (KeyError, ValueError):
            zeit = dauer = ""

        form.addRow("Typ:", ro_field(type_label(activity)))
        form.addRow("Kunde:", ro_field(activity.get("customer_name", "")))
        form.addRow("Zeit:", ro_field(zeit))
        form.addRow("Dauer:", ro_field(dauer))
        layout.addLayout(form)

        text = activity.get("details", "")
        if activity.get("parts"):
            lines = [f"{p['start'][11:16]}–{p['end'][11:16]}  {type_label(p)}  "
                     f"{p.get('customer_name', '')}" for p in activity["parts"]]
            text = (text + "\n\n" if text else "") + \
                f"Enthält {len(lines)} Einträge:\n" + "\n".join(lines)
        if activity.get("ai"):
            text = activity.get("description", "")
            form.addRow("Sicherheit:", ro_field(f"{round(activity.get('confidence', 0) * 100)} %"))
        if text:
            details = QTextEdit(text)
            details.setReadOnly(True)
            details.setMaximumHeight(240 if activity.get("parts") else 90)
            label = QLabel("Details:")
            label.setBuddy(details)
            layout.addWidget(label)
            layout.addWidget(details)

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
    rows_menu_requested = Signal(QPoint)
    # Hintergrund-Thread hat TeamViewer- und RDM-Logs gelesen
    logs_loaded = Signal(object, object, object)
    # Logs werden gelesen (True) oder sind fertig (False) – für die Ladeanzeige
    loading_changed = Signal(bool)

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

        self._remote_cache = {}  # date_str -> list[conn]
        self._tv_parser = TeamViewerParser(self.config)
        self._rdm_parser = RdmParser(self.config)
        self._vpn_parser = VpnParser(self.config)
        self._tv_index = None   # None = Logs noch nicht gelesen
        self._rdm_index = None
        self.vpn_reader = VpnReader()  # Sophos Connect/FortiClient; Archivdatei setzt das Hauptfenster
        self._sophos_index = None
        self._vpn_index = None
        self.loading = False    # Logs werden gerade im Hintergrund gelesen
        self._reload = False    # während des Lesens erneut angefordert
        self._thread = None
        self._threads = []      # alle gestarteten Einlese-Threads (zum Abwarten beim Beenden)
        self._closing = False   # beim Beenden: Thread darf nichts mehr melden
        self.logs_loaded.connect(self._on_logs_loaded)

        self.zoom_level = 1.0
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
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setMouseTracking(True)

        self.init_timeline_colors()
        self.tooltip = self._create_tooltip()

    # ----------------------------- Farben / Dark-Mode -------------------------

    def init_timeline_colors(self):
        """Grundfarben aus dem Design (theme.THEMES), Balken in den Typfarben."""
        t = THEMES["dark" if self.dark_mode else "light"]
        self.background_color = QColor(t["surface"])
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
        self.axis_bg = QColor(t["surface"])

    def set_dark_mode(self, enabled: bool):
        self.dark_mode = enabled
        self.init_timeline_colors()
        if self._ppm:  # erst neu zeichnen, wenn schon einmal gezeichnet wurde
            self.draw_timeline(self.current_date)

    # ----------------------------- Tooltip -----------------------------------

    def _create_tooltip(self):
        tooltip = QLabel(self.parent(), Qt.ToolTip)
        tooltip.setStyleSheet(
            "QLabel { background-color: #1B1F24; color: #F2F4F7; "
            "border: 1px solid #3A424C; padding: 5px 8px; border-radius: 0; }"
        )
        tooltip.hide()
        return tooltip

    # ----------------------------- Daten laden --------------------------------

    def refresh(self):
        """Logdateien im Hintergrund neu einlesen (nur geänderte Dateien werden wirklich gelesen).

        Große Logs oder Netzwerkpfade blockieren so weder den Start noch die Bedienung.
        Danach wird die Timeline neu gezeichnet.
        """
        if self.loading:
            self._reload = True
            return
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

    def _start_first_load(self):
        self.loading = False
        self.refresh()

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
        if not self._closing:
            self.logs_loaded.emit(*indexes)  # Qt stellt das im GUI-Thread zu

    def _on_logs_loaded(self, tv_index, rdm_index, vpn_index):
        if self._closing:
            return  # beim Beenden nichts mehr zeichnen
        self._tv_index, self._rdm_index, self._vpn_index = tv_index, rdm_index, vpn_index
        self._sophos_index = None  # Archiv der VPN-Aufzeichnung beim nächsten Zeichnen neu lesen
        self._remote_cache.clear()
        self.loading = False
        self.loading_changed.emit(False)
        if self._reload:
            self._reload = False
            self.refresh()
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

        day = self._tv_index.get_for_date(date_str) + self._rdm_index.get_for_date(date_str)
        day += self._vpn_index.get_for_date(date_str) + self._sophos_index.get_for_date(date_str)
        for conn in day:
            conn["is_suggestion"] = True
        self.remote_suggestions = day
        self._remote_cache[date_str] = day

    def activities_for(self, date: QDate):
        date_str = date.toString("yyyy-MM-dd")
        self.load_remote_connections(date)
        result = [a for a in self.activities if a.get("start", "").startswith(date_str)]
        result += [s for s in self.remote_suggestions if s.get("start", "").startswith(date_str)]
        if self.calls_file:
            result += load_call_suggestions(
                self.calls_file, date_str,
                ignore_missed=self.config.get("calls_ignore_missed", True),
                min_seconds=self.config.get("calls_min_duration", 0),
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
        valid.sort(key=lambda a: a["start"])

        # TeamViewer: eigener Name statt nur der ID
        names = {**(self.imported.teamviewer_names() if self.imported else {}),
                 **self.config.get("teamviewer_names", {})}
        for a in valid:
            tv_id = a.get("tv_id")
            if tv_id:
                a["customer_name"] = names.get(tv_id) or f"TeamViewer {format_tv_id(tv_id)}"
                a["details"] = f"TeamViewer-ID {format_tv_id(tv_id)}"
        return valid

    def view_entries(self, date: QDate):
        """Einträge so, wie Timeline und Liste sie zeigen (einzeln oder zusammengefasst)."""
        entries = self.activities_for(date)
        if self.config.get("list_view", "grouped") == "single":
            return entries
        return group_entries(entries, self.config.get("merge_gap_minutes", 5))

    def pc_entries_for(self, date: QDate, min_seconds=30, max_gap=60):
        """Aktive Fenster des Tages als Einträge (für Band und Tagesliste)."""
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
        result = []
        for seg in merge_segments(segments, min_seconds=min_seconds, max_gap=max_gap):
            result.append({
                "start": seg["start"], "end": seg["end"],
                "type": f"PC: {app_label(seg['app'])}",
                "customer_name": seg["title"] or app_label(seg["app"]),
                "details": seg["app"], "app": seg["app"],
                "is_suggestion": True,
            })
        return result

    def missing_sources(self):
        """Quellen, für die keine einzige Logdatei gelesen werden konnte."""
        return [name for name, parser in [("TeamViewer", self._tv_parser), ("RDM", self._rdm_parser)]
                if parser.files_read == 0]

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

    def pc_blocks_for(self, date: QDate):
        """PC-Aktivität für die Timeline: Arbeitsblöcke (focus.py) oder, abgeschaltet, jedes Fenster."""
        raw = self.pc_entries_for(date, min_seconds=5, max_gap=15)
        if not raw or not self.config.get("pc_blocks", True):
            return raw
        rule_list = self.config.get("rules") or []
        key = (date.toString("yyyy-MM-dd"), len(raw), raw[-1]["end"], id(rule_list), len(rule_list),
               self.config.get("pc_jump_seconds", focus.JUMP_SECONDS))
        cached = getattr(self, "_block_cache", None)
        if cached and cached[0] == key:
            return cached[1]
        segments = [{"start": e["start"], "end": e["end"], "app": e["app"], "title": e["customer_name"]}
                    for e in raw]
        blocks = focus.focus_blocks(segments, rule_list,
                                    jump_seconds=self.config.get("pc_jump_seconds", focus.JUMP_SECONDS))
        self._block_cache = (key, blocks)
        return blocks

    # ----------------------------- Zeichnen ----------------------------------

    def _x(self, minutes):
        return self.LEFT + minutes * self._ppm

    def _work_spans(self, date: QDate):
        """Arbeitszeit als [(Start, Ende)] in Minuten: Personalzeiten aus ITM, sonst Einstellungen."""
        return self._work_info(date)[0]

    def _work_info(self, date: QDate):
        """([(Start, Ende)] in Minuten, aus ITM?, Index der noch offenen Buchung oder None)."""
        day = self.personal_day(date.toString("yyyy-MM-dd")) if self.personal_day else None
        if day and day.get("zeiten"):
            spans, open_idx = [], None
            for t in day["zeiten"]:
                start = parse_time(t["start"])
                if not t["end"]:
                    open_idx = len(spans)
                end = parse_time(t["end"]) if t["end"] else datetime.now()  # noch eingestempelt
                end_min = end.hour * 60 + end.minute if end.date() == start.date() else 24 * 60
                spans.append((start.hour * 60 + start.minute, end_min))
            return spans, True, open_idx
        hours = work_hours(self.config, date.dayOfWeek() - 1)
        return ([hours] if hours else []), False, None

    def work_entries(self, date_str):
        """Zeile "Personalzeit": je gestempeltem Abschnitt ein Block mit Beginn und Ende
        (ohne ITM die Arbeitszeit aus den Einstellungen)."""
        date = QDate.fromString(date_str, "yyyy-MM-dd")
        spans, from_itm, open_idx = self._work_info(date)
        name = "Personalzeit" if from_itm else "Arbeitszeit"
        result = []
        for i, (a, b) in enumerate(spans):
            if b <= a:
                continue
            running = i == open_idx
            label = f"{hhmm(a)} – {'jetzt' if running else hhmm(b)}"
            end = f"{date_str} 23:59:59" if b >= 24 * 60 else f"{date_str} {hhmm(b)}:00"
            result.append({
                "start": f"{date_str} {hhmm(a)}:00", "end": end, "type": name,
                "customer_name": label, "work": True, "from_itm": from_itm, "running": running,
                "details": f"{name} {label}" + (" (eingestempelt)" if running else ""),
                "is_suggestion": False,
            })
        return result

    def _work_text(self, minute):
        """Was zu dieser Minute laut Personalzeit/Arbeitszeit gilt (eine Zeile)."""
        spans, from_itm, open_idx = self._work_info(self.current_date)
        name = "Personalzeit" if from_itm else "Arbeitszeit"
        if not spans:
            return f"<i>Keine {name}</i>"
        for i, (a, b) in enumerate(spans):
            if a <= minute < b:
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
        self.activity_rects.clear()
        self.tooltip.hide()
        self.scene.setBackgroundBrush(self.background_color)

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
        n_lanes = max(self.MIN_LANES, n_free) if show_other else 0
        show_other = show_other and n_lanes > 0
        band_y = self.AXIS_H + 6
        show_band = show_pc and bool(self.tracker or pc_band)
        top = band_y + (pc_h + 10 if show_band else 2)
        # Zeilenhöhe so wählen, dass alle Zeilen ohne senkrechte Scrollleiste ins Fenster passen;
        # Platz für die horizontale Scrollleiste lassen
        free_h = self.maximumViewportSize().height() - self.horizontalScrollBar().sizeHint().height()
        n_rows = (sum(max(1, n) for _k, _p, n in band_layout)
                  + sum(max(1, n) for _k, _p, n in fixed_layout) + n_lanes)
        fit = (free_h - top - (4 if bands else 0) - 6 - 8) / max(1, n_rows)
        lane_h, gap = type(self).LANE_H, type(self).LANE_GAP
        if fit < lane_h + gap:
            gap = 4
            lane_h = max(self.MIN_LANE_H, int(fit - gap))
        self.LANE_H, self.LANE_GAP = lane_h, gap
        row_h = self.LANE_H + self.LANE_GAP
        band_tops = []
        for _kind, _placed, n in band_layout:  # eigene Zeilen für Doku, Regeln und KI über den Einträgen
            band_tops.append(top)
            top += max(1, n) * row_h
        if bands:
            top += 4
        fixed_tops = []
        y = top
        for _kind, _placed, n in fixed_layout:
            fixed_tops.append(y)
            y += max(1, n) * row_h
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

        # Stundenleiste
        self.scene.addRect(0, 0, width, self.AXIS_H, no_pen, QBrush(self.axis_bg))
        hour_font = ui_font(8)
        step = 1 if self._ppm * 60 >= 45 else 2
        for hour in range(25):
            x = self._x(hour * 60)
            self.scene.addLine(x, self.AXIS_H, x, height, QPen(self.hour_line, 1))
            if hour < 24 and self._ppm * 60 >= 60:
                xh = self._x(hour * 60 + 30)
                self.scene.addLine(xh, self.AXIS_H, xh, height, QPen(self.half_line, 1))
            if hour % step == 0 and hour < 24:
                label = self.scene.addText(f"{hour:02d}:00", hour_font)
                label.setDefaultTextColor(
                    self.text_color if any(a <= hour * 60 < b for a, b in spans) else self.muted_text
                )
                label.setPos(x + 2, 3)

        # Jede zweite Zeile leicht hinterlegt, damit die Zeilen unterscheidbar sind
        stripe = QColor(255, 255, 255, 10) if self.dark_mode else QColor(0, 0, 0, 10)
        # (eine feste Zeile mit Unterzeilen bleibt eine Fläche)
        row_tops = [(y, max(1, n)) for y, (_k, _p, n) in zip(fixed_tops, fixed_layout)]
        row_tops += [(free_top + i * row_h, 1) for i in range(n_lanes)]
        for i, (y, n) in enumerate(row_tops):
            if i % 2 == 0:
                self.scene.addRect(0, y - self.LANE_GAP / 2, width, n * row_h, no_pen, QBrush(stripe))

        # Legende links (schwebt über den Zeilen, siehe drawForeground) und Trennlinie
        colors = self.config.get("type_colors", {})
        legend = []
        if show_band:
            legend.append((band_y, pc_h, "PC-Aktivität", None))
        # Name mittig über alle Unterzeilen einer Zeile
        for (kind, _text, band), y, (_k, _p, n) in zip(bands, band_tops, band_layout):
            name, key = LEGEND_BANDS[kind]
            if kind == "work" and band and not band[0].get("from_itm"):
                name = "Arbeitszeit"  # ohne ITM: Arbeitszeit aus den Einstellungen
            legend.append((y, max(1, n) * row_h - self.LANE_GAP, name, colors.get(key)))
        for (kind, _placed, n), y in zip(fixed_layout, fixed_tops):
            name, key = LEGEND_FIXED[kind]
            legend.append((y, max(1, n) * row_h - self.LANE_GAP, name, colors.get(key)))
        if show_other:
            legend.append((free_top, self.LANE_H, "Remote / Weitere", colors.get("RDP-Verbindung")))
            sep_y = free_top - (6 + self.LANE_GAP) / 2
            if fixed_layout:
                self.scene.addLine(0, sep_y, width, sep_y, QPen(self.hour_line, 1))
        self._legend = legend

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

            rect = self.scene.addRect(x1, y, w, self.LANE_H, pen, QBrush(fill))
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
                rect = self.scene.addRect(x1, band_y, w, pc_h, QPen(Qt.NoPen), QBrush(color))
                rect.setCursor(Qt.PointingHandCursor)
                self.activity_rects[rect] = p
                if p.get("pc_block"):
                    self._add_label(p["label"], x1, band_y, w, pc_h, label_font, metrics,
                                    readable_on(color), p.get("short_labels", ()))

        # Jetzt-Linie
        if date == QDate.currentDate():
            now = QDateTime.currentDateTime().time()
            x = self._x(now.hour() * 60 + now.minute())
            self.scene.addLine(x, 0, x, height, QPen(self.now_color, 2))

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

        self.day_loaded.emit(activities, self.pc_entries_for(date))

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
            if entries or kind == "doc":
                result.append((kind, text, entries))
        return result

    MIN_LABEL_CHARS = 6  # weniger lesbare Zeichen: lieber keine Beschriftung als „Chro…“

    def _add_label(self, text, x, y, w, h, font, metrics, color, alternatives=()):
        """Beschriftung in einem Balken; zu wenig Platz: kürzere Alternative, sonst keine
        (der Name steht im Hinweis beim Darüberfahren)."""
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
        item = self.scene.addText(shown, font)
        item.setDefaultTextColor(color)
        item.setPos(x + 2, y + (h - item.boundingRect().height()) / 2)
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
        if a.get("work") and not a.get("from_itm"):  # Arbeitszeit aus den Einstellungen: nur Rahmen
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
        rect = self.scene.addRect(x1, y, w, self.LANE_H, pen, QBrush(fill))
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Ganzer Tag: Breite mitziehen; sonst Höhe der Fläche an das Fenster anpassen
        if self._ppm and (
            (self.fit_day and abs(self._ppm - self._fit_ppm()) > 0.01)
            or abs(self.sceneRect().height() - self.viewport().height()) > 30
        ):
            self.draw_timeline(self.current_date)

    # ----------------------------- Ansicht / Zoom -----------------------------

    def _fit_ppm(self):
        """Pixel pro Minute, damit 0–24 Uhr genau ins Fenster passt."""
        width = self.maximumViewportSize().width() - self.LEFT - self.RIGHT - 4
        return max(0.2, width / (24 * 60))

    def show_whole_day(self):
        self.fit_day = True
        self.draw_timeline(self.current_date)

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
        self.draw_timeline(self.current_date)
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
            self.draw_timeline(self.current_date)
            return
        # Zeitpunkt unter der Maus bleibt an derselben Stelle
        scene_x = self.mapToScene(int(anchor_viewport_x), 0).x()
        minute = (scene_x - self.LEFT) / self._ppm
        self.zoom_level = level
        self._first_draw = False
        self.draw_timeline(self.current_date)
        target = self._x(minute) - anchor_viewport_x
        self.horizontalScrollBar().setValue(int(target))

    def drawForeground(self, painter, rect):
        """Legende links: Name und Farbe jeder Zeile, bleibt beim Blättern stehen."""
        super().drawForeground(painter, rect)
        if not self._legend:
            return
        painter.save()
        painter.resetTransform()  # ab hier Koordinaten des Fensters, nicht der Szene
        font = ui_font(8, bold=True)
        painter.setFont(font)
        fm = QFontMetrics(font)
        width = self.LEFT - 6
        top = self.mapFromScene(0, self.AXIS_H).y()
        last_y, last_h = self._legend[-1][0], self._legend[-1][1]
        bottom = min(self.viewport().height(), self.mapFromScene(0, last_y + last_h).y() + 6)
        panel = QColor(self.background_color)
        panel.setAlpha(232)
        painter.fillRect(0, top, width, max(0, bottom - top), panel)
        painter.setPen(QPen(self.hour_line, 1))
        painter.drawLine(width, top, width, bottom)
        for y, h, name, color in self._legend:
            center = self.mapFromScene(0, y + h / 2).y()
            if center < top or center > bottom:
                continue
            if color:
                painter.fillRect(8, center - 4, 8, 8, QColor(color))
            else:  # PC: mehrere Programme, kleine Streifen
                for i, c in enumerate(self.APP_COLORS[:3]):
                    painter.fillRect(8 + i * 3, center - 4, 2, 8, QColor(c))
            painter.setPen(self.text_color)
            painter.drawText(22, center + (fm.ascent() - fm.descent()) // 2,
                             fm.elidedText(name, Qt.ElideRight, width - 26))
        painter.restore()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self.viewport().update()  # Legende neu zeichnen, sonst wandert sie beim Blättern mit

    def wheelEvent(self, event):
        """STRG + Mausrad: Zoom, UMSCHALT + Mausrad: Zeilen, Mausrad: horizontal blättern."""
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.set_zoom(self.zoom_level * factor, event.position().x())
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

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
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
        super().mouseMoveEvent(event)

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

    def _hover_text(self, minute, hovered=None):
        """Hinweis zur Linie: Uhrzeit, Personalzeit und alles, was zu dieser Minute lief."""
        date_str = self.current_date.toString("yyyy-MM-dd")
        moment = parse_time(f"{date_str} {hhmm(minute)}:00")
        lines = [f"<b>{hhmm(minute)} Uhr</b>"]
        if not any(k == "work" for k, _t, _e in self._bands):  # Zeile aus: Personalzeit im Hinweis
            lines.append(self._work_text(minute))

        if hovered:  # Eintrag direkt unter der Maus: ausführlich
            start, end = parse_time(hovered["start"]), parse_time(hovered["end"])
            lines += ["", f"<b>{escape(hovered.get('customer_name') or hovered.get('type'))}</b>",
                      escape(type_label(hovered)),
                      *self._customer_line(hovered),
                      f"{start:%H:%M} – {end:%H:%M}  ({format_duration((end - start).total_seconds())})"]
            if hovered.get("work"):
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
                    lines.append(f"{parse_time(e['start']):%H:%M}–{parse_time(e['end']):%H:%M}  "
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
                lines.append(f"{parse_time(a['start']):%H:%M}–{parse_time(a['end']):%H:%M}  "
                             f"{escape(type_label(a))}: {escape(a.get('customer_name') or '')}")
            if len(others) > 8:
                lines.append(f"<i>… und {len(others) - 8} weitere</i>")
        elif not hovered:
            lines.append("<i>Keine Einträge</i>")
        return "<br>".join(lines)

    def leaveEvent(self, event):
        self._hide_hover()
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
            self._drag_start, self._drag_button = pos, event.button()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        button = event.button()
        pos = event.position().toPoint()
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
            self.rows_menu_requested.emit(global_pos)
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
