# timeline_only.py
from datetime import datetime

from PyQt5.QtCore import QDate, Qt, QTime, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (QDialog, QFormLayout, QGraphicsRectItem,
                             QGraphicsScene, QGraphicsView, QLabel, QLineEdit,
                             QPushButton, QTextEdit, QVBoxLayout)

from call_import import load_call_suggestions
from log_parsers import (ConnectionIndex, RdmParser,  # neu: ConnectionIndex
                         TeamViewerParser)

DEBUG = False  # bei Bedarf auf True setzen


class ActivityViewDialog(QDialog):
    """Nur-Anzeigen-Dialog zum Kopieren von Aktivitätsdaten."""

    def __init__(self, activity, parent=None):
        super().__init__(parent)
        self.activity = activity
        self.setWindowTitle("Aktivitätsdetails")
        self.setMinimumWidth(420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        def ro_field(text):
            w = QLineEdit(text)
            w.setReadOnly(True)
            return w

        form.addRow("Typ:", ro_field(self.activity.get("type", "")))
        form.addRow("Kunde:", ro_field(self.activity.get("customer_name", "")))
        form.addRow("Start:", ro_field(self.activity.get("start", "")))
        form.addRow("Ende:", ro_field(self.activity.get("end", "")))

        try:
            start = datetime.strptime(self.activity["start"], "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(self.activity["end"], "%Y-%m-%d %H:%M:%S")
            dur = end - start
            dur_str = f"{dur.seconds // 60} min"
        except Exception:
            dur_str = ""
        form.addRow("Dauer:", ro_field(dur_str))

        layout.addLayout(form)

        details = QTextEdit(self.activity.get("details", ""))
        details.setReadOnly(True)
        layout.addWidget(QLabel("Details:"))
        layout.addWidget(details)

        close_btn = QPushButton("Schließen")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class TimelineView(QGraphicsView):
    time_selected = pyqtSignal(QTime, QTime)

    def __init__(self, activities, config, parent=None):
        super().__init__(parent)
        self._remote_cache = {}  # date_str -> list[conn]
        self.activities = activities
        self.config = config or {}
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self._first_draw = True
        self.selection_start = None
        self.selection_rect = None
        self.activity_rects = {}
        self.remote_suggestions = []
        self.current_date = QDate.currentDate()

        # Parser-Instanzen + Indexe zwischenspeichern
        self._tv_parser = TeamViewerParser(debug=DEBUG)
        self._rdm_parser = RdmParser(debug=DEBUG)
        self._tv_index = None
        self._rdm_index = None
        self.calls_file = None  # wird vom Hauptfenster gesetzt (anrufe.json)

        self.TIME_AXIS_Y = 30
        self.zoom_level = 1.0
        self.dark_mode = self.config.get("dark_mode", False)

        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(320)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        self.init_timeline_colors()
        self.tooltip = self._create_tooltip()

        #self.update_timer = QTimer(self)
        #self.update_timer.timeout.connect(self.update_realtime_connections)
        #self.update_timer.start(120000)

    # ----------------------------- Farben / Dark-Mode -------------------------

    def init_timeline_colors(self):
        if self.dark_mode:
            self.background_color = QColor(46, 46, 46)
            self.text_color = Qt.white
            self.axis_color = QColor(200, 200, 200)
            self.non_work_color = QColor(70, 70, 70)
            self.work_area_color = QColor(90, 120, 160, 180)
        else:
            self.background_color = Qt.white
            self.text_color = Qt.black
            self.axis_color = QColor(80, 80, 80)
            self.non_work_color = QColor(240, 240, 240)
            self.work_area_color = QColor(173, 216, 230, 160)

    def set_dark_mode(self, enabled: bool):
        self.dark_mode = enabled
        self.init_timeline_colors()
        self.draw_timeline(self.current_date)

    # ----------------------------- Tooltip -----------------------------------

    def _create_tooltip(self):
        tooltip = QLabel(self.parent(), Qt.ToolTip)
        tooltip.setStyleSheet(
            """
        QLabel {
            background-color: #2b2b2b;
            color: #f0f0f0;
            border: 1px solid #555;
            padding: 4px 6px;
            border-radius: 3px;
        }
        """
        )
        tooltip.hide()
        return tooltip

    # ----------------------------- Parser / Logs ------------------------------

    def update_realtime_connections(self):
        if self.isVisible():
            # Indexe neu aufbauen, falls sich Logs geändert haben könnten
            self._tv_index = None
            self._rdm_index = None
            self.draw_timeline(self.current_date)

    def load_remote_connections(self, date: QDate):
        date_str = date.toString("yyyy-MM-dd")

        # Cache-Hit?
        if date_str in self._remote_cache:
            self.remote_suggestions = self._remote_cache[date_str]
            if DEBUG:
                print(f"Remote-Suggestions Cache-Hit für {date_str}: "
                    f"{len(self.remote_suggestions)} Einträge")
            return

        self.remote_suggestions = []

        # TeamViewer nur einmal einlesen und indizieren
        if self._tv_index is None:
            try:
                tv_conns = self._tv_parser.parse_logs()
                if DEBUG:
                    print(f"TeamViewerParser: {len(tv_conns)} Verbindungen gesamt")
                self._tv_index = ConnectionIndex(tv_conns)
            except Exception as e:
                print(f"Fehler im TeamViewerParser: {e}")
                self._tv_index = ConnectionIndex([])

        # RDM nur einmal einlesen und indizieren
        if self._rdm_index is None:
            try:
                rdm_conns = self._rdm_parser.parse_logs()
                if DEBUG:
                    print(f"RdmParser: {len(rdm_conns)} Verbindungen gesamt")
                self._rdm_index = ConnectionIndex(rdm_conns)
            except Exception as e:
                print(f"Fehler im RdmParser: {e}")
                self._rdm_index = ConnectionIndex([])

        day_tv = self._tv_index.get_for_date(date_str)
        day_rdm = self._rdm_index.get_for_date(date_str)


        for conn in day_tv + day_rdm:
            conn["is_suggestion"] = True

        self.remote_suggestions = day_tv + day_rdm
        self._remote_cache[date_str] = self.remote_suggestions

        if DEBUG:
            print(
                f"Remote-Suggestions für {date_str}: "
                f"{len(self.remote_suggestions)}"
            )

    # ----------------------------- Zeichnen der Timeline ----------------------

    def draw_timeline(self, date: QDate):
        self.current_date = date
        # Remote-Suggestions für diesen Draw zurücksetzen
        self.remote_suggestions = []
        self.scene.clear()
        self.activity_rects.clear()
        self.scene.setBackgroundBrush(self.background_color)

        # Transform für Button-Zoom (nicht für STRG+Scroll) zurücksetzen
        self.resetTransform()
        self.scale(self.zoom_level, self.zoom_level)

        if DEBUG:
            print(f"\n=== Debug für {date.toString('dd.MM.yyyy')} ===")
            print(f"Aktivitäten in Memory: {len(self.activities)}")

        self.load_remote_connections(date)

        date_str = date.toString("yyyy-MM-dd")
        day_activities = [
            a for a in self.activities if a.get("start", "").startswith(date_str)
        ]
        day_suggestions = [
            s for s in self.remote_suggestions if s.get("start", "").startswith(date_str)
        ]
        if self.calls_file:
            day_suggestions += [
                c for c in load_call_suggestions(
                    self.calls_file,
                    ignore_missed=self.config.get("calls_ignore_missed", True),
                    min_seconds=self.config.get("calls_min_duration", 0),
                )
                if c["start"].startswith(date_str)
            ]
        all_activities = day_activities + day_suggestions

        if DEBUG:
            print(f"Lokale Aktivitäten: {len(day_activities)}")
            print(f"Remote-Vorschläge: {len(day_suggestions)}")
            print(f"Gesamtaktivitäten: {len(all_activities)}")
            for i, act in enumerate(all_activities[:3], 1):
                print(f"Aktivität {i}: {act['type']} {act['start']} - {act['end']}")

        TIMELINE_HEIGHT = 220
        TIME_AXIS_Y = 30
        TIME_AXIS_HEIGHT = 200
        ACTIVITY_HEIGHT = 20
        ACTIVITY_Y_OFFSET = 50
        MAX_LANES = 10

        main_window = self.window()
        type_colors = getattr(main_window, "config", {}).get("type_colors", {})

        title = self.scene.addText(f"Aktivitäten am {date.toString('dd.MM.yyyy')}")
        title.setDefaultTextColor(self.text_color)
        title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        title.setPos(10, 8)

        for hour in range(25):
            x = 50 + hour * 60
            self.scene.addLine(
                x,
                TIME_AXIS_Y,
                x,
                TIME_AXIS_Y + TIME_AXIS_HEIGHT,
                QPen(self.axis_color, 1),
            )
            time_text = self.scene.addText(f"{hour:02d}:00")
            time_text.setDefaultTextColor(self.text_color)
            time_text.setFont(QFont("Segoe UI", 8))
            time_text.setPos(x - 18, TIME_AXIS_Y + TIME_AXIS_HEIGHT + 5)

            if hour < 24:
                for minute in [15, 30, 45]:
                    xm = x + minute
                    self.scene.addLine(
                        xm,
                        TIME_AXIS_Y,
                        xm,
                        TIME_AXIS_Y + TIME_AXIS_HEIGHT / 2,
                        QPen(QColor(190, 190, 190), 1),
                    )

        self.scene.addRect(
            50,
            TIME_AXIS_Y,
            7 * 60,
            TIME_AXIS_HEIGHT,
            QPen(Qt.NoPen),
            QBrush(self.non_work_color),
        )
        self.scene.addRect(
            50 + 18 * 60,
            TIME_AXIS_Y,
            6 * 60,
            TIME_AXIS_HEIGHT,
            QPen(Qt.NoPen),
            QBrush(self.non_work_color),
        )

        work_start = 8 * 60
        work_end = 17 * 60
        self.scene.addRect(
            50 + work_start,
            TIME_AXIS_Y + 2,
            work_end - work_start,
            10,
            QPen(QColor(70, 130, 180)),
            QBrush(self.work_area_color),
        )

        for activity in all_activities:
            activity.setdefault("type", "Aktivität")
            activity.setdefault("customer_name", "")
            activity.setdefault("details", "")
            activity.setdefault("is_suggestion", False)

        all_activities.sort(key=lambda x: x["start"])
        lanes = [[] for _ in range(MAX_LANES)]

        for activity in all_activities:
            try:
                start = datetime.strptime(activity["start"], "%Y-%m-%d %H:%M:%S")
                end = datetime.strptime(activity["end"], "%Y-%m-%d %H:%M:%S")
            except Exception as e:
                if DEBUG:
                    print(f"Fehler beim Parsen der Zeit in Activity: {activity} -> {e}")
                continue

            x_start = 50 + (start.hour * 60 + start.minute)
            x_end = 50 + (end.hour * 60 + end.minute)
            width = max(5, x_end - x_start)

            for lane_idx in range(MAX_LANES):
                overlap = False
                for other in lanes[lane_idx]:
                    o_start = datetime.strptime(other["start"], "%Y-%m-%d %H:%M:%S")
                    o_end = datetime.strptime(other["end"], "%Y-%m-%d %H:%M:%S")
                    if not (end <= o_start or start >= o_end):
                        overlap = True
                        break
                if overlap:
                    continue

                y = ACTIVITY_Y_OFFSET + lane_idx * ACTIVITY_HEIGHT

                atype = activity.get("type", "Aktivität")
                color_hex = type_colors.get(atype, "#4682B4")
                base_color = QColor(color_hex)

                if activity.get("is_suggestion", False):
                    if self.dark_mode:
                        color = base_color.lighter(130)
                        pen = QPen(color, 1, Qt.DashLine)
                        brush = QBrush(color.darker(150))
                    else:
                        color = base_color.lighter(150)
                        pen = QPen(color, 1, Qt.DashLine)
                        brush = QBrush(color.lighter(170))
                else:
                    color = base_color
                    pen = QPen(color.darker(120))
                    brush = QBrush(color.lighter(130))

                rect = self.scene.addRect(x_start, y, width, ACTIVITY_HEIGHT, pen, brush)
                rect.setData(0, activity)
                self.activity_rects[rect] = activity

                if width > 30:
                    label = f"{activity['customer_name']} ({activity['type']})"
                    short_label = label[: int(width / 10)]
                    text = self.scene.addText(short_label)
                    text.setFont(QFont("Segoe UI", 8))
                    text.setDefaultTextColor(
                        Qt.white if self.dark_mode else Qt.black
                    )
                    text.setPos(x_start + 3, y)

                lanes[lane_idx].append(activity)
                break

        self.setSceneRect(0, 0, 50 + 24 * 60 + 100, TIMELINE_HEIGHT + 80)
        if self._first_draw:
            view_x = 50 + 8 * 60
            view_width = (17 - 8) * 60
            self.centerOn(view_x + view_width / 2, TIMELINE_HEIGHT / 2)
            self._first_draw = False

    # ----------------------------- Maus / Zoom / Tooltip ----------------------

    def wheelEvent(self, event):
        """STRG + Mausrad: Zoom, sonst normales Scrollen."""
        if event.modifiers() & Qt.ControlModifier:
            zoom_factor = 1.15
            if event.angleDelta().y() < 0:
                zoom_factor = 1.0 / zoom_factor

            self.zoom_level *= zoom_factor
            self.scale(zoom_factor, zoom_factor)
        else:
            super().wheelEvent(event)

    def mouseMoveEvent(self, event):
        pos = self.mapToScene(event.pos())
        items = self.scene.items(pos)

        found_activity = None
        for item in items:
            if isinstance(item, QGraphicsRectItem) and item in self.activity_rects:
                found_activity = self.activity_rects[item]
                break

        if found_activity:
            try:
                start = datetime.strptime(found_activity["start"], "%Y-%m-%d %H:%M:%S")
                end = datetime.strptime(found_activity["end"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                start = end = None

            lines = [f"Typ: {found_activity.get('type', '')}"]
            if found_activity.get("customer_name"):
                lines.append(f"Kunde: {found_activity.get('customer_name')}")
            if start and end:
                duration_h = (end - start).total_seconds() / 3600.0
                lines.append(
                    f"Zeit: {start.strftime('%H:%M')} - {end.strftime('%H:%M')} "
                    f"({duration_h:.2f} h)"
                )
            if found_activity.get("details"):
                lines.append(f"Details: {found_activity.get('details')}")

            tooltip_text = "\n".join(lines)
            self.tooltip.setText(tooltip_text)
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
            pos = self.mapToScene(event.pos())
            items = self.scene.items(pos)
            for item in items:
                if isinstance(item, QGraphicsRectItem) and item in self.activity_rects:
                    activity = self.activity_rects[item]
                    dlg = ActivityViewDialog(activity, self)
                    dlg.exec_()
                    break
        super().mousePressEvent(event)
