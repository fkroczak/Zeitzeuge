# timeline_only.py
import threading
import time
from datetime import datetime
from html import escape

from PySide6.QtCore import QDate, QDateTime, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QGraphicsRectItem,
                               QGraphicsScene, QGraphicsView, QLabel, QLineEdit, QMenu,
                               QTextEdit, QVBoxLayout)

from activity_tracker import app_label, merge_segments, read_segments
from call_import import load_call_suggestions
from grouping import format_tv_id, group_entries
from log_parsers import ConnectionIndex, RdmParser, TeamViewerParser, VpnParser
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
DEFAULT_CALL_COLORS = {"Eingehend": "#3D8BFD", "Ausgehend": "#27AE60", "Verpasst": "#E74C3C"}


def entry_color(activity, config):
    """Farbe eines Eintrags: Telefonate nach Richtung, sonst nach Aktivitätstyp."""
    direction = activity.get("direction")
    if direction:
        colors = {**DEFAULT_CALL_COLORS, **config.get("call_colors", {})}
        if direction in colors:
            return QColor(colors[direction])
    return QColor(config.get("type_colors", {}).get(activity.get("type"), "#4682B4"))


# Eigene Zeile je Quelle (Kennung, Beschriftung links); nur RDM und der Rest teilen sich mehrere Spuren
FIXED_ROWS = [("call", "Tel"), ("vpn", "VPN"), ("tv", "TV")]


def row_kind(activity):
    """Feste Zeile eines Eintrags ("call", "vpn", "tv") oder None für die freien Spuren."""
    kind = activity.get("type", "")
    if activity.get("direction") or kind == "Telefonat":
        return "call"
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
    if activity.get("rule"):
        return f"Regel: {activity.get('category', '')}"
    if activity.get("ai"):
        text = f"KI: {activity.get('category', '')}"
        return text + " (übernommen)" if activity.get("status") == "übernommen" else text
    direction = activity.get("direction")
    if direction and direction != "Anruf":
        return f"{activity.get('type', '')} {direction.lower()}"
    return activity.get("type", "")


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


def entry_menu_items(entry):
    """Befehle für einen Eintrag: [(Text, Befehl)], None = Trennlinie.

    Timeline und Tagesliste zeigen dasselbe Menü mit denselben Texten, und nur Befehle,
    die zu diesem Eintrag passen.
    """
    if "minute" in entry:  # freie Stelle in der Timeline
        return [(f"&Tätigkeit ab {hhmm(entry['minute'] // 5 * 5)} eintragen …", "add_at")]
    if entry.get("open"):
        return [("Jetzt &eintragen …", "add"), ("&Nicht dokumentieren", "ignore")]
    if entry.get("doc"):
        return [("Tätigkeit &bearbeiten …", "edit"), ("Tätigkeit &löschen", "delete"), None,
                ("Als Ticketzeile &kopieren", "copy")]
    items = [("&Details öffnen", "details"), None]
    if entry.get("ai") or entry.get("rule"):
        items.append(("Als &Tätigkeit eintragen …", "add"))
    else:
        items.append(("&Tätigkeit dazu eintragen …", "add"))
    if entry.get("tv_id"):
        items.append(("TeamViewer-ID &benennen …", "name_tv"))
    if entry.get("ai"):
        items += [None, ("Vorschlag &verwerfen", "reject")]
    items += [None, ("&Kopieren", "copy")]
    return items


def exec_entry_menu(parent, entry, global_pos):
    """Menü zu entry zeigen, gewählten Befehl zurückgeben (oder None)."""
    menu = QMenu(parent)
    keys = {}
    for item in entry_menu_items(entry):
        if item is None:
            menu.addSeparator()
        else:
            keys[menu.addAction(item[0])] = item[1]
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
    # Aktionen: "add" (zu einem Eintrag), "add_at" (freie Stelle), "edit", "delete", "ignore"
    doc_request = Signal(str, dict)
    # Rechtsklick-Menü: (Befehl aus entry_menu_items, Eintrag oder {"minute": …})
    entry_action = Signal(str, dict)
    # Hintergrund-Thread hat TeamViewer- und RDM-Logs gelesen
    logs_loaded = Signal(object, object, object)

    APP_COLORS = ["#5B8DEF", "#E67E22", "#27AE60", "#9B59B6", "#E84393",
                  "#16A085", "#C0392B", "#F1C40F", "#2C3E50", "#7F8C8D"]

    LEFT = 30          # Rand links in Pixeln (Platz für die Zeilenbeschriftung)
    AXIS_H = 26        # Höhe der Stundenleiste oben
    PC_BAND_H = 14     # Band für die PC-Aktivität
    LANE_H = 26        # Höhe eines Eintrags
    LANE_GAP = 6
    MIN_LANES = 2      # freie Spuren unter den festen Zeilen (RDM, eigene Einträge)
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
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setMouseTracking(True)

        self.init_timeline_colors()
        self.tooltip = self._create_tooltip()

    # ----------------------------- Farben / Dark-Mode -------------------------

    def init_timeline_colors(self):
        if self.dark_mode:
            self.background_color = QColor("#1E1E1E")
            self.text_color = QColor("#E8E8E8")
            self.muted_text = QColor("#9A9A9A")
            self.hour_line = QColor(255, 255, 255, 28)
            self.half_line = QColor(255, 255, 255, 12)
            self.non_work_color = QColor(0, 0, 0, 70)
            self.axis_bg = QColor("#252526")
        else:
            self.background_color = QColor("#FFFFFF")
            self.text_color = QColor("#222222")
            self.muted_text = QColor("#707070")
            self.hour_line = QColor(0, 0, 0, 30)
            self.half_line = QColor(0, 0, 0, 12)
            self.non_work_color = QColor(0, 0, 0, 12)
            self.axis_bg = QColor("#F5F6F8")

    def set_dark_mode(self, enabled: bool):
        self.dark_mode = enabled
        self.init_timeline_colors()
        if self._ppm:  # erst neu zeichnen, wenn schon einmal gezeichnet wurde
            self.draw_timeline(self.current_date)

    # ----------------------------- Tooltip -----------------------------------

    def _create_tooltip(self):
        tooltip = QLabel(self.parent(), Qt.ToolTip)
        tooltip.setStyleSheet(
            "QLabel { background-color: #2b2b2b; color: #f0f0f0; "
            "border: 1px solid #555; padding: 5px 8px; border-radius: 4px; }"
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
        names = self.config.get("teamviewer_names", {})
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

        # Telefonate, VPN und TeamViewer je in eine feste Zeile; der Rest (v. a. RDM)
        # wird auf Spuren verteilt: überlappende Einträge kommen in die nächste Spur
        fixed_index = {kind: i for i, (kind, _label) in enumerate(FIXED_ROWS)}
        n_fixed = len(FIXED_ROWS)
        lanes_end = []
        placed = []
        for a in activities:
            start, end = parse_time(a["start"]), parse_time(a["end"])
            kind = row_kind(a)
            if kind is not None:
                placed.append((a, start, end, fixed_index[kind]))
                continue
            for idx, lane_end in enumerate(lanes_end):
                if start >= lane_end:
                    lanes_end[idx] = end
                    break
            else:
                if len(lanes_end) >= self.MAX_LANES:
                    idx = self.MAX_LANES - 1
                    lanes_end[idx] = max(lanes_end[idx], end)
                else:
                    lanes_end.append(end)
                    idx = len(lanes_end) - 1
            placed.append((a, start, end, n_fixed + idx))

        pc_band = self.pc_entries_for(date, min_seconds=5, max_gap=15)
        bands = self.band_rows(date)
        ai_band = next((e for k, _t, e in bands if k == "ai"), [])
        n_lanes = max(self.MIN_LANES, len(lanes_end))
        band_y = self.AXIS_H + 6
        show_band = bool(self.tracker or pc_band)
        top = band_y + (self.PC_BAND_H + 10 if show_band else 2)
        band_tops = []
        for _band in bands:  # eigene Zeilen für Doku, Regeln und KI über den Einträgen
            band_tops.append(top)
            top += self.LANE_H + self.LANE_GAP
        if bands:
            top += 4
        row_h = self.LANE_H + self.LANE_GAP
        free_top = top + n_fixed * row_h + 6  # kleiner Abstand vor den freien Spuren
        content_h = free_top + n_lanes * row_h + 8
        # Platz für die horizontale Scrollleiste lassen, sonst erscheint eine senkrechte
        free_h = self.maximumViewportSize().height() - self.horizontalScrollBar().sizeHint().height()
        height = max(content_h, free_h)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if content_h > free_h else Qt.ScrollBarAlwaysOff
        )
        width = self._x(24 * 60) + self.LEFT

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
        hour_font = QFont("Segoe UI", 8)
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

        # Personalzeit/Arbeitszeit als schmaler Streifen unter der Stundenleiste
        work_color = QColor("#27AE60")
        work_color.setAlpha(200)
        for span_start, span_end in spans:
            if span_end <= span_start:
                continue
            self.scene.addRect(self._x(span_start), self.AXIS_H - 3, self._x(span_end) - self._x(span_start),
                               3, no_pen, QBrush(work_color))

        # Jede zweite Zeile leicht hinterlegt, damit die Zeilen unterscheidbar sind
        stripe = QColor(255, 255, 255, 10) if self.dark_mode else QColor(0, 0, 0, 10)
        row_tops = [top + i * row_h for i in range(n_fixed)]
        row_tops += [free_top + i * row_h for i in range(n_lanes)]
        for i, y in enumerate(row_tops):
            if i % 2 == 0:
                self.scene.addRect(0, y - self.LANE_GAP / 2, width, row_h, no_pen, QBrush(stripe))

        # Beschriftung der festen Zeilen und Trennlinie zu den freien Spuren
        row_font = QFont("Segoe UI", 7)
        for i, (_kind, text) in enumerate(FIXED_ROWS):
            label = self.scene.addText(text, row_font)
            label.setDefaultTextColor(self.muted_text)
            label.setPos(0, top + i * row_h + (self.LANE_H - label.boundingRect().height()) / 2)
        sep_y = free_top - (6 + self.LANE_GAP) / 2
        self.scene.addLine(0, sep_y, width, sep_y, QPen(self.hour_line, 1))

        # Einträge
        label_font = QFont("Segoe UI", 8)
        metrics = QFontMetrics(label_font)
        for a, start, end, lane in placed:
            x1 = self._x(start.hour * 60 + start.minute + start.second / 60)
            x2 = self._x(end.hour * 60 + end.minute + end.second / 60)
            if end.date() > start.date():  # über Mitternacht
                x2 = self._x(24 * 60)
            w = max(4.0, x2 - x1)
            y = top + lane * row_h + (6 if lane >= n_fixed else 0)

            base = entry_color(a, self.config)
            fill = QColor(base)
            if a["is_suggestion"]:
                fill.setAlpha(110 if self.dark_mode else 70)
                pen = QPen(base, 1.2)
            else:
                fill.setAlpha(220)
                pen = QPen(base.darker(130), 1.5)

            rect = self.scene.addRect(x1, y, w, self.LANE_H, pen, QBrush(fill))
            rect.setData(0, a)
            rect.setCursor(Qt.PointingHandCursor)
            self.activity_rects[rect] = a

            label_text = a["customer_name"] or a["type"]
            if w > 28:
                text = metrics.elidedText(label_text, Qt.ElideRight, int(w - 8))
                item = self.scene.addText(text, label_font)
                item.setDefaultTextColor(self.text_color)
                item.setPos(x1 + 2, y + (self.LANE_H - item.boundingRect().height()) / 2)
                item.setAcceptedMouseButtons(Qt.NoButton)

        # Obere Zeilen: Doku (eigene Tätigkeiten, offene gestrichelt), Regeln, KI
        for (kind, text, band), y in zip(bands, band_tops):
            for a in band:
                self._draw_band_entry(a, y, label_font, metrics)
            label = self.scene.addText(text, row_font)
            label.setDefaultTextColor(self.muted_text)
            label.setPos(0, y + (self.LANE_H - label.boundingRect().height()) / 2)

        # PC-Aktivität als schmales Band
        if show_band:
            for p in pc_band:
                start, end = parse_time(p["start"]), parse_time(p["end"])
                x1 = self._x(start.hour * 60 + start.minute + start.second / 60)
                x2 = self._x(end.hour * 60 + end.minute + end.second / 60)
                color = self.app_color(p["app"])
                fill = QColor(color)
                fill.setAlpha(200)
                rect = self.scene.addRect(x1, band_y, max(1.5, x2 - x1), self.PC_BAND_H,
                                          QPen(Qt.NoPen), QBrush(fill))
                self.activity_rects[rect] = p
            label = self.scene.addText("PC", QFont("Segoe UI", 7))
            label.setDefaultTextColor(self.muted_text)
            label.setPos(0, band_y - 3)

        # Jetzt-Linie
        if date == QDate.currentDate():
            now = QDateTime.currentDateTime().time()
            x = self._x(now.hour() * 60 + now.minute())
            self.scene.addLine(x, 0, x, height, QPen(QColor("#E74C3C"), 1.5))

        # Senkrechte Linie unter der Maus (erst bei Mausbewegung sichtbar)
        self._hover_line = self.scene.addLine(0, 0, 0, height, QPen(self.text_color, 1, Qt.DashLine))
        self._hover_line.setZValue(90)
        self._hover_line.hide()
        self._hover_label = self.scene.addText("", QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._hover_label.setDefaultTextColor(self.text_color)
        self._hover_label.setZValue(91)
        self._hover_label.hide()
        self._day_entries = activities
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

    # Obere Zeilen: Kennung, Beschriftung links, Schlüssel in config["timeline_rows"]
    BAND_ROWS = [("doc", "Doku"), ("rule", "Regel"), ("ai", "KI")]

    def band_rows(self, date: QDate):
        """Sichtbare obere Zeilen mit ihren Einträgen: [(Kennung, Text, Einträge)].

        Doku steht immer da (auch leer), damit offene Tätigkeiten sofort auffallen.
        Regeln und KI nur, wenn es Einträge gibt. Jede Zeile lässt sich abschalten.
        """
        date_str = date.toString("yyyy-MM-dd")
        shown = self.config.get("timeline_rows", {})
        sources = {"doc": self.doc_entries, "rule": self.rule_entries, "ai": self.ai_entries}
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

    def _draw_band_entry(self, a, y, font, metrics):
        start, end = parse_time(a["start"]), parse_time(a["end"])
        x1 = self._x(start.hour * 60 + start.minute)
        x2 = self._x(24 * 60) if end.date() > start.date() else self._x(end.hour * 60 + end.minute)
        w = max(4.0, x2 - x1)
        base = entry_color(a, self.config)
        fill = QColor(base)
        light = 110 if self.dark_mode else 70
        if a.get("doc") or a.get("status") == "übernommen":
            fill.setAlpha(light)
            pen = QPen(base.darker(130) if not self.dark_mode else base.lighter(130), 2)
        elif a.get("open"):  # noch nicht dokumentiert: fällt auf, lädt zum Klicken ein
            fill.setAlpha(light // 2)
            pen = QPen(base, 1.5, Qt.DashLine)
        elif a.get("rule"):
            fill.setAlpha(light)
            pen = QPen(base, 1.2, Qt.DashDotLine)
        else:  # KI-Vorschlag
            fill.setAlpha(light)
            pen = QPen(base, 1.5, Qt.DotLine)
        rect = self.scene.addRect(x1, y, w, self.LANE_H, pen, QBrush(fill))
        rect.setCursor(Qt.PointingHandCursor)
        self.activity_rects[rect] = a
        if w > 28:
            if a.get("open"):
                label_text = f"? {a.get('customer_name') or 'eintragen'}"
            elif a.get("doc"):  # Form statt nur Farbe: ✓ dokumentiert, ? offen
                label_text = "✓ " + (" · ".join(t for t in (a.get("customer_name"), a.get("description"))
                                                if t) or a.get("category") or "Tätigkeit")
            else:
                label_text = " · ".join(t for t in (a.get("customer_name"), a.get("category"),
                                                    a.get("description") if a.get("doc") else "")
                                        if t) or a.get("type", "")
            item = self.scene.addText(metrics.elidedText(label_text, Qt.ElideRight, int(w - 8)), font)
            item.setDefaultTextColor(self.text_color)
            item.setPos(x1 + 2, y + (self.LANE_H - item.boundingRect().height()) / 2)
            item.setAcceptedMouseButtons(Qt.NoButton)

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
        width = self.maximumViewportSize().width() - 2 * self.LEFT - 4
        return max(0.2, width / (24 * 60))

    def show_whole_day(self):
        self.fit_day = True
        self.draw_timeline(self.current_date)

    def show_range(self, start_min, end_min):
        """Zeitraum (Minuten seit 0 Uhr) genau ins Fenster einpassen."""
        start_min, end_min = max(0, min(start_min, end_min)), min(24 * 60, max(start_min, end_min))
        if end_min - start_min < 5:
            return
        width = self.maximumViewportSize().width() - 2 * self.LEFT - 4
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

    def wheelEvent(self, event):
        """STRG + Mausrad: Zoom, Mausrad: horizontal blättern."""
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.set_zoom(self.zoom_level * factor, event.position().x())
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
        # Klicken und ziehen: Bereich markieren
        if self._drag_start is not None and abs(pos.x() - self._drag_start.x()) > 5:
            self._hide_hover()
            x1 = self.mapToScene(self._drag_start).x()
            x2 = self.mapToScene(pos).x()
            rect = self.sceneRect()
            if self._drag_item is None:
                color = QColor("#0078D7")
                color.setAlpha(50)
                self._drag_item = self.scene.addRect(0, 0, 0, 0, QPen(QColor("#0078D7"), 1), QBrush(color))
                self._drag_item.setZValue(100)
            self._drag_item.setRect(min(x1, x2), 0, abs(x2 - x1), rect.height())
            a, b = sorted((self._minute_at(self._drag_start.x()), self._minute_at(pos.x())))
            a, b = max(0, int(a)), min(24 * 60, int(b))
            self.tooltip.setText(f"{a // 60:02d}:{a % 60:02d} – {b // 60:02d}:{b % 60:02d}")
            self.tooltip.adjustSize()
            gp = self.mapToGlobal(pos)
            self.tooltip.move(gp.x() + 15, gp.y() + 15)
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

    def _hover_text(self, minute, hovered=None):
        """Hinweis zur Linie: Uhrzeit, Personalzeit und alles, was zu dieser Minute lief."""
        date_str = self.current_date.toString("yyyy-MM-dd")
        moment = parse_time(f"{date_str} {hhmm(minute)}:00")
        lines = [f"<b>{hhmm(minute)} Uhr</b>", self._work_text(minute)]

        if hovered:  # Eintrag direkt unter der Maus: ausführlich
            start, end = parse_time(hovered["start"]), parse_time(hovered["end"])
            lines += ["", f"<b>{escape(hovered.get('customer_name') or hovered.get('type'))}</b>",
                      escape(type_label(hovered)),
                      f"{start:%H:%M} – {end:%H:%M}  ({format_duration((end - start).total_seconds())})"]
            if hovered.get("open"):
                lines.append("<i>Noch nicht dokumentiert · Klick: jetzt eintragen</i>")
            elif hovered.get("doc"):
                if hovered.get("description"):
                    lines.append(escape(hovered["description"]))
                lines.append("<i>Deine Tätigkeit · Klick: bearbeiten</i>")
            elif hovered.get("rule"):
                lines.append(escape(hovered.get("description") or hovered.get("details", "")))
                lines.append("<i>Aus Regeln erkannt · Rechtsklick: als Tätigkeit eintragen</i>")
            elif hovered.get("ai"):
                lines.append(escape(hovered.get("description", "")))
                lines.append(f"<i>KI-Vorschlag, Sicherheit {round(hovered.get('confidence', 0) * 100)} %"
                             " · Rechtsklick: übernehmen oder verwerfen</i>")
            elif hovered.get("details"):
                lines.append(escape(hovered["details"]))
            if hovered.get("is_suggestion") and not any(hovered.get(k) for k in ("ai", "rule", "open")):
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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.position().toPoint()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_start is not None:
            start, self._drag_start = self._drag_start, None
            if self._drag_item is not None:  # Bereich gezogen -> diesen Bereich zeigen
                self.scene.removeItem(self._drag_item)
                self._drag_item = None
                self.tooltip.hide()
                self.show_range(self._minute_at(start.x()), self._minute_at(event.position().x()))
                return
            a = self._activity_at(event.position().toPoint())  # einfacher Klick -> Details
            if a:
                self.tooltip.hide()
                if a.get("open"):  # offene Tätigkeit: gleich eintragen
                    self.doc_request.emit("add", a["source_entry"])
                elif a.get("doc"):
                    self.doc_request.emit("edit", a)
                else:
                    ActivityViewDialog(a, self).exec()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Rechtsklick: dasselbe Menü wie in der Tagesliste (entry_menu_items)."""
        a = self._activity_at(event.pos())
        self._hide_hover()
        if a is None:
            minute = self._minute_at(event.pos().x()) if self._ppm else -1
            if not 0 <= minute < 24 * 60:
                return
            a = {"minute": minute}
        key = exec_entry_menu(self, a, event.globalPos())
        if key:
            self.entry_action.emit(key, a)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and not self._activity_at(event.position().toPoint()):
            self.show_whole_day()
            return
        super().mouseDoubleClickEvent(event)
