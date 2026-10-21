# timeline_only.py
from datetime import datetime
from html import escape

from PyQt5.QtCore import QDate, QDateTime, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                             QGraphicsRectItem, QGraphicsScene, QGraphicsView,
                             QLabel, QLineEdit, QTextEdit, QVBoxLayout)

from call_import import load_call_suggestions
from log_parsers import ConnectionIndex, RdmParser, TeamViewerParser

DEBUG = False  # bei Bedarf auf True setzen
TIME_FMT = "%Y-%m-%d %H:%M:%S"


def parse_time(text):
    return datetime.strptime(text, TIME_FMT)


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

        form.addRow("Typ:", ro_field(activity.get("type", "")))
        form.addRow("Kunde:", ro_field(activity.get("customer_name", "")))
        form.addRow("Zeit:", ro_field(zeit))
        form.addRow("Dauer:", ro_field(dauer))
        layout.addLayout(form)

        if activity.get("details"):
            details = QTextEdit(activity["details"])
            details.setReadOnly(True)
            details.setMaximumHeight(90)
            layout.addWidget(QLabel("Details:"))
            layout.addWidget(details)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class TimelineView(QGraphicsView):
    # Liefert nach jedem Zeichnen alle Einträge des Tages (für die Tagesliste)
    day_loaded = pyqtSignal(list)

    LEFT = 20          # Rand links in Pixeln
    AXIS_H = 26        # Höhe der Stundenleiste oben
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

        self._remote_cache = {}  # date_str -> list[conn]
        self._tv_parser = TeamViewerParser(debug=DEBUG)
        self._rdm_parser = RdmParser(debug=DEBUG)
        self._tv_index = None
        self._rdm_index = None

        self.zoom_level = 1.0
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
        """Logdateien neu einlesen (nur geänderte Dateien werden wirklich gelesen)."""
        self._tv_index = None
        self._rdm_index = None
        self._remote_cache.clear()
        self.draw_timeline(self.current_date)

    # Alter Name, falls noch irgendwo verwendet
    update_realtime_connections = refresh

    def load_remote_connections(self, date: QDate):
        date_str = date.toString("yyyy-MM-dd")
        if date_str in self._remote_cache:
            self.remote_suggestions = self._remote_cache[date_str]
            return

        if self._tv_index is None:
            try:
                self._tv_index = ConnectionIndex(self._tv_parser.parse_logs())
            except Exception as e:
                print(f"Fehler im TeamViewerParser: {e}")
                self._tv_index = ConnectionIndex([])

        if self._rdm_index is None:
            try:
                self._rdm_index = ConnectionIndex(self._rdm_parser.parse_logs())
            except Exception as e:
                print(f"Fehler im RdmParser: {e}")
                self._rdm_index = ConnectionIndex([])

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
            result += [
                c for c in load_call_suggestions(
                    self.calls_file,
                    ignore_missed=self.config.get("calls_ignore_missed", True),
                    min_seconds=self.config.get("calls_min_duration", 0),
                )
                if c["start"].startswith(date_str)
            ]

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
        return valid

    # ----------------------------- Zeichnen ----------------------------------

    def _x(self, minutes):
        return self.LEFT + minutes * self._ppm

    def _work_minutes(self):
        def to_min(text, default):
            try:
                h, m = text.split(":")
                return int(h) * 60 + int(m)
            except (AttributeError, ValueError):
                return default
        return (to_min(self.config.get("work_start"), 8 * 60),
                to_min(self.config.get("work_end"), 17 * 60))

    def draw_timeline(self, date: QDate):
        # Mittelpunkt merken, damit Zoom/Neuzeichnen die Ansicht nicht verschiebt
        center_min = None
        if not self._first_draw and self._ppm:
            center_x = self.mapToScene(self.viewport().rect().center()).x()
            center_min = (center_x - self.LEFT) / self._ppm

        self.current_date = date
        self._ppm = self.BASE_PX_PER_MIN * self.zoom_level
        self.scene.clear()
        self.activity_rects.clear()
        self.tooltip.hide()
        self.scene.setBackgroundBrush(self.background_color)

        activities = self.activities_for(date)
        type_colors = self.config.get("type_colors", {})

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

        n_lanes = max(self.MIN_LANES, len(lanes_end))
        top = self.AXIS_H + 8
        content_h = top + n_lanes * (self.LANE_H + self.LANE_GAP) + 8
        # Platz für die horizontale Scrollleiste lassen, sonst erscheint eine senkrechte
        free_h = self.maximumViewportSize().height() - self.horizontalScrollBar().sizeHint().height()
        height = max(content_h, free_h)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if content_h > free_h else Qt.ScrollBarAlwaysOff
        )
        width = self._x(24 * 60) + self.LEFT

        # Außerhalb der Arbeitszeit abdunkeln
        work_start, work_end = self._work_minutes()
        no_pen = QPen(Qt.NoPen)
        self.scene.addRect(self._x(0), 0, self._x(work_start) - self._x(0), height,
                           no_pen, QBrush(self.non_work_color))
        self.scene.addRect(self._x(work_end), 0, self._x(24 * 60) - self._x(work_end), height,
                           no_pen, QBrush(self.non_work_color))

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
                    self.text_color if work_start <= hour * 60 < work_end else self.muted_text
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

            base = QColor(type_colors.get(a["type"], "#4682B4"))
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

        # Jetzt-Linie
        if date == QDate.currentDate():
            now = QDateTime.currentDateTime().time()
            x = self._x(now.hour() * 60 + now.minute())
            self.scene.addLine(x, 0, x, height, QPen(QColor("#E74C3C"), 1.5))

        self.setSceneRect(0, 0, width, height)

        if self._first_draw:
            self.centerOn(self._x((work_start + work_end) / 2), 0)
            self._first_draw = False
        elif center_min is not None:
            self.centerOn(self._x(center_min), self.mapToScene(0, 0).y())

        self.day_loaded.emit(activities)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Höhe der Fläche an das Fenster anpassen
        if self._ppm and abs(self.sceneRect().height() - self.viewport().height()) > 30:
            self.draw_timeline(self.current_date)

    # ----------------------------- Maus / Zoom / Tooltip ----------------------

    def set_zoom(self, level, anchor_viewport_x=None):
        level = max(0.5, min(level, 12.0))
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

    def mouseMoveEvent(self, event):
        a = self._activity_at(event.pos())
        if a:
            start, end = parse_time(a["start"]), parse_time(a["end"])
            lines = [f"<b>{escape(a.get('customer_name') or a.get('type'))}</b>",
                     escape(a.get("type", "")),
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
            a = self._activity_at(event.pos())
            if a:
                self.tooltip.hide()
                ActivityViewDialog(a, self).exec_()
                return
        super().mousePressEvent(event)
