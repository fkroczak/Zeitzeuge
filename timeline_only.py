# timeline_only.py
import threading
from datetime import datetime
from html import escape

from PyQt5.QtCore import QDate, QDateTime, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                             QGraphicsRectItem, QGraphicsScene, QGraphicsView,
                             QLabel, QLineEdit, QTextEdit, QVBoxLayout)

from activity_tracker import app_label, merge_segments
from call_import import load_call_suggestions
from grouping import format_tv_id, group_entries
from log_parsers import ConnectionIndex, RdmParser, TeamViewerParser

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


def type_label(activity):
    """Typ-Text für Liste und Details, bei Telefonaten mit Richtung."""
    direction = activity.get("direction")
    if direction and direction != "Anruf":
        return f"{activity.get('type', '')} {direction.lower()}"
    return activity.get("type", "")


def format_duration(seconds):
    minutes = int(round(seconds / 60))
    if minutes < 1:
        return "< 1 min"
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60}:{minutes % 60:02d} h"


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
    day_loaded = pyqtSignal(list, list)
    # Hintergrund-Thread hat TeamViewer- und RDM-Logs gelesen
    logs_loaded = pyqtSignal(object, object)

    APP_COLORS = ["#5B8DEF", "#E67E22", "#27AE60", "#9B59B6", "#E84393",
                  "#16A085", "#C0392B", "#F1C40F", "#2C3E50", "#7F8C8D"]

    LEFT = 20          # Rand links in Pixeln
    AXIS_H = 26        # Höhe der Stundenleiste oben
    PC_BAND_H = 14     # Band für die PC-Aktivität
    LANE_H = 26        # Höhe eines Eintrags
    LANE_GAP = 6
    MIN_LANES = 4
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
        self.personal_day = None  # date_str -> Personalzeiten aus ITM, vom Hauptfenster gesetzt

        self._remote_cache = {}  # date_str -> list[conn]
        self._tv_parser = TeamViewerParser(self.config)
        self._rdm_parser = RdmParser(self.config)
        self._tv_index = None   # None = Logs noch nicht gelesen
        self._rdm_index = None
        self.loading = False    # Logs werden gerade im Hintergrund gelesen
        self._reload = False    # während des Lesens erneut angefordert
        self.logs_loaded.connect(self._on_logs_loaded)

        self.zoom_level = 1.0
        self.fit_day = True        # ganzen Tag ins Fenster einpassen
        self._drag_start = None    # Mausposition beim Drücken (Bereich ziehen)
        self._drag_item = None     # markierter Bereich während des Ziehens
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
        threading.Thread(target=self._load_logs, daemon=True).start()

    def _start_first_load(self):
        self.loading = False
        self.refresh()

    def _load_logs(self):
        indexes = []
        for name, parser in (("TeamViewer", self._tv_parser), ("RDM", self._rdm_parser)):
            try:
                indexes.append(ConnectionIndex(parser.parse_logs()))
            except Exception as e:
                print(f"Fehler beim Lesen der {name}-Logs: {e}")
                indexes.append(ConnectionIndex([]))
        self.logs_loaded.emit(*indexes)  # Qt stellt das im GUI-Thread zu

    def _on_logs_loaded(self, tv_index, rdm_index):
        self._tv_index, self._rdm_index = tv_index, rdm_index
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

        day = self._tv_index.get_for_date(date_str) + self._rdm_index.get_for_date(date_str)
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
        if not self.tracker:
            return []
        segments = self.tracker.segments_for(date.toString("yyyy-MM-dd"))
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
        day = self.personal_day(date.toString("yyyy-MM-dd")) if self.personal_day else None
        if day and day.get("zeiten"):
            spans = []
            for t in day["zeiten"]:
                start = parse_time(t["start"])
                end = parse_time(t["end"]) if t["end"] else datetime.now()  # noch eingestempelt
                end_min = end.hour * 60 + end.minute if end.date() == start.date() else 24 * 60
                spans.append((start.hour * 60 + start.minute, end_min))
            return spans
        hours = work_hours(self.config, date.dayOfWeek() - 1)
        return [hours] if hours else []

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
        self.activity_rects.clear()
        self.tooltip.hide()
        self.scene.setBackgroundBrush(self.background_color)

        activities = self.view_entries(date)

        # Spuren verteilen: überlappende Einträge kommen in die nächste Zeile
        lanes_end = []
        placed = []
        for a in activities:
            start, end = parse_time(a["start"]), parse_time(a["end"])
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
            placed.append((a, start, end, idx))

        pc_band = self.pc_entries_for(date, min_seconds=5, max_gap=15)
        n_lanes = max(self.MIN_LANES, len(lanes_end))
        band_y = self.AXIS_H + 6
        top = band_y + (self.PC_BAND_H + 10 if self.tracker else 2)
        content_h = top + n_lanes * (self.LANE_H + self.LANE_GAP) + 8
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

        # Einträge
        label_font = QFont("Segoe UI", 8)
        metrics = QFontMetrics(label_font)
        for a, start, end, lane in placed:
            x1 = self._x(start.hour * 60 + start.minute + start.second / 60)
            x2 = self._x(end.hour * 60 + end.minute + end.second / 60)
            if end.date() > start.date():  # über Mitternacht
                x2 = self._x(24 * 60)
            w = max(4.0, x2 - x1)
            y = top + lane * (self.LANE_H + self.LANE_GAP)

            base = entry_color(a, self.config)
            fill = QColor(base)
            if a["is_suggestion"]:
                fill.setAlpha(110 if self.dark_mode else 70)
                pen = QPen(base, 1.5, Qt.DashLine)
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

        # PC-Aktivität als schmales Band
        if self.tracker:
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
            label.setPos(self._x(0) - 18, band_y - 3)

        # Jetzt-Linie
        if date == QDate.currentDate():
            now = QDateTime.currentDateTime().time()
            x = self._x(now.hour() * 60 + now.minute())
            self.scene.addLine(x, 0, x, height, QPen(QColor("#E74C3C"), 1.5))

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
            self.set_zoom(self.zoom_level * factor, event.pos().x())
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
        # Klicken und ziehen: Bereich markieren
        if self._drag_start is not None and abs(event.pos().x() - self._drag_start.x()) > 5:
            self.tooltip.hide()
            x1 = self.mapToScene(self._drag_start).x()
            x2 = self.mapToScene(event.pos()).x()
            rect = self.sceneRect()
            if self._drag_item is None:
                color = QColor("#0078D7")
                color.setAlpha(50)
                self._drag_item = self.scene.addRect(0, 0, 0, 0, QPen(QColor("#0078D7"), 1), QBrush(color))
                self._drag_item.setZValue(100)
            self._drag_item.setRect(min(x1, x2), 0, abs(x2 - x1), rect.height())
            a, b = sorted((self._minute_at(self._drag_start.x()), self._minute_at(event.pos().x())))
            a, b = max(0, int(a)), min(24 * 60, int(b))
            self.tooltip.setText(f"{a // 60:02d}:{a % 60:02d} – {b // 60:02d}:{b % 60:02d}")
            self.tooltip.adjustSize()
            gp = self.mapToGlobal(event.pos())
            self.tooltip.move(gp.x() + 15, gp.y() + 15)
            self.tooltip.show()
            return

        a = self._activity_at(event.pos())
        if a:
            start, end = parse_time(a["start"]), parse_time(a["end"])
            lines = [f"<b>{escape(a.get('customer_name') or a.get('type'))}</b>",
                     escape(type_label(a)),
                     f"{start:%H:%M} – {end:%H:%M}  ({format_duration((end - start).total_seconds())})"]
            if a.get("details"):
                lines.append(escape(a["details"]))
            if a.get("is_suggestion"):
                lines.append("<i>Vorschlag aus Log</i>")
            self.tooltip.setText("<br>".join(lines))
            self.tooltip.adjustSize()
            global_pos = self.mapToGlobal(event.pos())
            self.tooltip.move(global_pos.x() + 15, global_pos.y() + 15)
            self.tooltip.show()
        else:
            self.tooltip.hide()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.tooltip.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_start is not None:
            start, self._drag_start = self._drag_start, None
            if self._drag_item is not None:  # Bereich gezogen -> diesen Bereich zeigen
                self.scene.removeItem(self._drag_item)
                self._drag_item = None
                self.tooltip.hide()
                self.show_range(self._minute_at(start.x()), self._minute_at(event.pos().x()))
                return
            a = self._activity_at(event.pos())  # einfacher Klick -> Details
            if a:
                self.tooltip.hide()
                ActivityViewDialog(a, self).exec_()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and not self._activity_at(event.pos()):
            self.show_whole_day()
            return
        super().mouseDoubleClickEvent(event)
