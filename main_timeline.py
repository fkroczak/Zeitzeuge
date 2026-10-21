import json
import os
import sys
import warnings

from datetime import datetime

from PyQt5.QtCore import QDate, QLocale, QObject, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QKeySequence, QPalette, QPixmap
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication,
                             QDateEdit, QHeaderView, QLabel, QMainWindow,
                             QMenu, QMessageBox, QShortcut, QSplitter,
                             QTableWidget, QTableWidgetItem, QToolBar,
                             QToolButton, QWidget)

from call_import import start_call_server
from settings_dialogs import (ActivityTypeSettingsDialog,
                              ConnectionSettingsDialog)
from timeline_only import (ActivityViewDialog, TimelineView, format_duration,
                           parse_time)

warnings.filterwarnings("ignore", category=DeprecationWarning)


def resource_path(relative_path: str) -> str:
    """Pfad für Ressourcen, funktioniert im Script und in der PyInstaller-EXE."""
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS  # Temp-Ordner der EXE
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# Basisverzeichnis: Ordner der EXE oder des Skripts
if hasattr(sys, "_MEIPASS"):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "zeitzeuge_config.json")
CALLS_FILE = os.path.join(BASE_DIR, "anrufe.json")


class CallSignal(QObject):
    # Signal aus dem Server-Thread sicher in den GUI-Thread bringen
    updated = pyqtSignal()



def load_config_with_defaults():
    defaults = {
        "activity_types": [
            # Remote / ZugÃ¤nge
            "VPN-Sitzung",
            "RDP-Sitzung",
            "SSH-Sitzung",
            "TeamViewer",
            "RDP-Verbindung",
            "SSH",
            "VPN",
            "Website-Verbindung",

            # Admin-OberflÃ¤chen / Dienste
            "Nextcloud-Admin",
            "NAS-Admin",
            "Website-Verbindung",
            "Hosting-Admin",
            "M365-Admin",
            "Mail-Administration",

            # Sicherheits-/Zugangsthemen
            "Passwortaktion",
            "OTP / 2FA",
            "Benutzername angezeigt",
            "Passwort angezeigt",

        ],
        "type_colors": {
            # Remote / ZugÃ¤nge
            "VPN-Sitzung":           "#00B894",  # TÃ¼rkis
            "RDP-Sitzung":           "#F1C40F",  # Gelb
            "SSH-Sitzung":           "#E67E22",  # Orange

            # Admin-OberflÃ¤chen / Dienste
            "Nextcloud-Admin":       "#3498DB",  # Blau
            "NAS-Admin":             "#16A085",  # Petrol
            "Website-Admin":         "#1ABC9C",  # TÃ¼rkisgrÃ¼n
            "Hosting-Admin":         "#9B59B6",  # Lila (z.B. Netcup/goneo)
            "M365-Admin":            "#2980B9",  # Dunkelblau
            "Mail-Administration":   "#C0392B",  # Rot

            # Sicherheits-/Zugangsthemen
            "Passwortaktion":        "#9B59B6",  # Lila
            "OTP-Anzeige":             "#E84393",  # Pink
            "Benutzername angezeigt": "#9B59B6",  # Grau
            "Passwort angezeigt": "#9B59B6",  # Grau

            # Parser-Typen aus TeamViewer/RDM
            "TeamViewer":            "#3460DB",
            "RDP-Verbindung":        "#F1C40F",
            "SSH":                   "#E67E22",
            "VPN":                   "#00B894",
            "Website-Verbindung":    "#1ABC9C",
        },

        "suggestion_colors": {
            "light": {"background": "#B4B4B4", "text": "#000000"},
            "dark": {"background": "#4A4A4A", "text": "#FFFFFF"},
        },

        "auto_start": True,
        "work_start": "08:00",
        "work_end": "17:00",

        "teamviewer_paths": [
            os.path.expandvars(r"%APPDATA%\\TeamViewer\\Connections.txt")
        ],
        "rdm_paths": [
            os.path.expandvars(
                r"%LOCALAPPDATA%\\Devolutions\\RemoteDesktopManager\\Connections.log"
            )
        ],
        # deine gewÃ¼nschten Zeitzonen
        "timezone_correction": 0,
        "teamviewer_timezone_correction": 1,
        "rdm_timezone_correction": 0,

        "dark_mode": False,
        "start_minimized": False,

        # Anrufe aus dem 3CX-Webclient (Tampermonkey-Skript)
        "calls_enabled": True,
        "calls_port": 8765,
        "calls_ignore_missed": True,
        "calls_min_duration": 0,
    }
    if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}
    else:
        cfg = {}

    # Defaults mergen
    for k, v in defaults.items():
        cfg.setdefault(k, v)
    cfg["type_colors"].setdefault("Telefonat", "#27AE60")
    if "Telefonat" not in cfg["activity_types"]:
        cfg["activity_types"].append("Telefonat")

    # gleich zurückschreiben (damit neue Keys persistieren)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Konfiguration konnte nicht gespeichert werden: {e}")

    return cfg


def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


GERMAN = QLocale(QLocale.German, QLocale.Germany)

THEMES = {
    "dark": {
        "bg": "#1E1E1E", "surface": "#252526", "bar": "#2D2D30",
        "border": "#3C3C3C", "text": "#F3F3F3", "muted": "#A0A0A0",
        "accent": "#007ACC", "hover": "#3A3D41", "pressed": "#33373B",
        "alt": "#2A2A2B", "handle": "#5A5A5A",
    },
    "light": {
        "bg": "#F3F4F6", "surface": "#FFFFFF", "bar": "#FFFFFF",
        "border": "#D5D9DE", "text": "#222222", "muted": "#666666",
        "accent": "#0078D7", "hover": "#E8EBEF", "pressed": "#DADEE3",
        "alt": "#F8F9FA", "handle": "#C2C7CD",
    },
}

STYLESHEET = """
QWidget { background-color: $bg; color: $text; font-size: 12px;
          font-family: "Segoe UI", Arial, sans-serif; }
QToolBar { background-color: $bar; border: none; border-bottom: 1px solid $border;
           padding: 4px; spacing: 4px; }
QToolBar::separator { background: $border; width: 1px; margin: 4px 6px; }
QToolButton { background: transparent; border: 1px solid transparent;
              border-radius: 4px; padding: 4px 8px; }
QToolButton:hover { background-color: $hover; border-color: $border; }
QToolButton:pressed, QToolButton:checked { background-color: $pressed; border-color: $border; }
QToolButton::menu-indicator { image: none; }
QStatusBar { background-color: $bar; color: $muted; border-top: 1px solid $border; }
QStatusBar QLabel { background: transparent; color: $muted; padding: 0 8px; }
QStatusBar::item { border: none; }
QDateEdit, QLineEdit, QTextEdit, QComboBox, QSpinBox, QListWidget {
    background-color: $surface; color: $text; border: 1px solid $border;
    border-radius: 4px; padding: 4px; selection-background-color: $accent;
    selection-color: #FFFFFF; }
QDateEdit { min-width: 105px; }
QPushButton { background-color: $hover; color: $text; border: 1px solid $border;
              border-radius: 4px; padding: 6px 12px; min-width: 80px; }
QPushButton:hover { background-color: $pressed; }
QGroupBox { border: 1px solid $border; border-radius: 6px; margin-top: 1em;
            padding-top: 12px; background-color: $surface; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QMenu { background-color: $surface; border: 1px solid $border; padding: 4px; }
QMenu::item { padding: 5px 20px; border-radius: 3px; }
QMenu::item:selected { background-color: $accent; color: #FFFFFF; }
QGraphicsView { border: 1px solid $border; border-radius: 4px; }
QTableWidget { background-color: $surface; alternate-background-color: $alt;
               border: 1px solid $border; border-radius: 4px; gridline-color: transparent;
               selection-background-color: $accent; selection-color: #FFFFFF; }
QTableWidget::item { padding: 2px 6px; border: none; }
QHeaderView::section { background-color: $bar; color: $muted; border: none;
                       border-bottom: 1px solid $border; padding: 4px 6px; font-weight: 600; }
QTableCornerButton::section { background-color: $bar; border: none; }
QSplitter::handle { background: transparent; }
QScrollBar:horizontal { height: 10px; background: transparent; margin: 0; }
QScrollBar:vertical { width: 10px; background: transparent; margin: 0; }
QScrollBar::handle { background: $handle; border-radius: 4px; min-width: 30px; min-height: 30px; }
QScrollBar::handle:horizontal { margin: 2px 0; }
QScrollBar::handle:vertical { margin: 0 2px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QCalendarWidget QToolButton { color: $text; font-weight: bold; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background-color: $bar; }
QCalendarWidget QAbstractItemView { background-color: $surface; color: $text;
    selection-background-color: $accent; selection-color: #FFFFFF; }
QCalendarWidget QAbstractItemView:disabled { color: $muted; }
QToolTip { background-color: #2b2b2b; color: #f0f0f0; border: 1px solid #555; }
"""


def merged_seconds(activities):
    """Gesamtzeit ohne doppelt gezählte Überschneidungen."""
    total, cur_start, cur_end = 0, None, None
    for a in sorted(activities, key=lambda a: a["start"]):
        s, e = parse_time(a["start"]), parse_time(a["end"])
        if cur_end is None or s > cur_end:
            if cur_end is not None:
                total += (cur_end - cur_start).total_seconds()
            cur_start, cur_end = s, e
        else:
            cur_end = max(cur_end, e)
    if cur_end is not None:
        total += (cur_end - cur_start).total_seconds()
    return total


class TimelineApp(QMainWindow):
    COLUMNS = ["Von", "Bis", "Dauer", "Typ", "Kunde / Verbindung", "Details"]

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Zeitzeuge")
        self.setWindowIcon(QIcon(resource_path("zeitzeuge.ico")))
        self.resize(1200, 720)

        self.config = load_config_with_defaults()
        self.dark_mode = self.config.get("dark_mode", False)
        self.current_date = QDate.currentDate()
        self.activities = []
        self.day_activities = []

        self._build_toolbar()

        # Timeline oben, Tagesliste unten
        self.timeline = TimelineView(self.activities, self.config, parent=self)
        self.timeline.day_loaded.connect(self.update_day_list)

        self.table = QTableWidget(0, len(self.COLUMNS), self)
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(26)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for col in range(4):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Interactive)
        header.resizeSection(4, 300)
        header.setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(
            lambda row, _col: ActivityViewDialog(self.day_activities[row], self).exec_()
        )
        copy_action = QAction("Kopieren", self.table)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.setShortcutContext(Qt.WidgetShortcut)
        copy_action.triggered.connect(self.copy_selection)
        self.table.addAction(copy_action)
        self.table.setContextMenuPolicy(Qt.ActionsContextMenu)

        splitter = QSplitter(Qt.Vertical, self)
        splitter.addWidget(self.timeline)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([260, 400])
        splitter.setContentsMargins(8, 8, 8, 8)
        self.setCentralWidget(splitter)

        # Statuszeile
        self.info_label = QLabel(self)
        self.calls_label = QLabel(self)
        self.statusBar().addWidget(self.info_label, 1)
        self.statusBar().addPermanentWidget(self.calls_label)
        self.statusBar().setSizeGripEnabled(False)

        # Anruf-Empfang für das Tampermonkey-Skript starten
        self.timeline.calls_file = CALLS_FILE
        self.call_server = None
        if self.config.get("calls_enabled", True):
            self.call_signal = CallSignal()
            self.call_signal.updated.connect(
                lambda: self.timeline.draw_timeline(self.current_date)
            )
            port = self.config.get("calls_port", 8765)
            self.call_server = start_call_server(
                CALLS_FILE, port=port, on_update=self.call_signal.updated.emit
            )
            self.calls_label.setText(
                f"Anrufempfang aktiv (Port {port})" if self.call_server
                else f"Anrufempfang: Port {port} belegt"
            )

        # Logs regelmäßig neu prüfen (nur geänderte Dateien werden gelesen)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.auto_refresh)
        self.refresh_timer.start(2 * 60 * 1000)

        self.apply_style()  # zeichnet die Timeline
        self.timeline.setFocus()

    # ---------------------- Werkzeugleiste ------------------------------------

    def _action(self, text, slot, shortcut=None, tip=None):
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcuts(shortcut if isinstance(shortcut, list) else [shortcut])
        label = tip or text
        if shortcut:
            first = shortcut[0] if isinstance(shortcut, list) else shortcut
            label += f" ({QKeySequence(first).toString(QKeySequence.NativeText)})"
        action.setToolTip(label)
        self.addAction(action)  # Tastenkürzel im ganzen Fenster
        return action

    def _build_toolbar(self):
        tb = QToolBar("Navigation", self)
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(Qt.TopToolBarArea, tb)

        tb.addAction(self._action("◀", self.show_previous_day, "Ctrl+Left", "Vorheriger Tag"))
        self.date_edit = QDateEdit(self.current_date, self)
        self.date_edit.setLocale(GERMAN)
        self.date_edit.setDisplayFormat("ddd dd.MM.yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.dateChanged.connect(self.date_changed)
        tb.addWidget(self.date_edit)
        tb.addAction(self._action("▶", self.show_next_day, "Ctrl+Right", "Nächster Tag"))
        tb.addAction(self._action("Heute", self.show_today, "Ctrl+T"))
        tb.addSeparator()
        tb.addAction(self._action("⟳ Aktualisieren", self.refresh, "F5", "Logs neu einlesen"))
        tb.addSeparator()
        tb.addAction(self._action("−", self.zoom_out, "Ctrl+-", "Verkleinern"))
        tb.addAction(self._action("+", self.zoom_in, ["Ctrl++", "Ctrl+="], "Vergrößern"))
        tb.addAction(self._action("Arbeitszeit", self.reset_zoom, "Ctrl+0",
                                  "Zoom zurücksetzen und auf Arbeitszeit springen"))

        spacer = QWidget(self)
        spacer.setSizePolicy(spacer.sizePolicy().Expanding, spacer.sizePolicy().Preferred)
        spacer.setStyleSheet("background: transparent;")
        tb.addWidget(spacer)

        self.dark_action = QAction("Dunkel", self)
        self.dark_action.setCheckable(True)
        self.dark_action.setChecked(self.dark_mode)
        self.dark_action.setToolTip("Dunkles Design")
        self.dark_action.toggled.connect(self.toggle_dark_mode)
        tb.addAction(self.dark_action)

        menu = QMenu(self)
        menu.addAction("TeamViewer-Logs …", self.edit_teamviewer_settings)
        menu.addAction("RDM-Logs …", self.edit_rdm_settings)
        menu.addAction("Aktivitätstypen und Farben …", self.edit_activity_types)
        menu.addSeparator()
        menu.addAction("Über Zeitzeuge", self.show_about)
        settings_btn = QToolButton(self)
        settings_btn.setText("Einstellungen ▾")
        settings_btn.setMenu(menu)
        settings_btn.setPopupMode(QToolButton.InstantPopup)
        tb.addWidget(settings_btn)

    def show_about(self):
        icon_path = resource_path("zeitzeuge.png")
        msg = QMessageBox(self)
        msg.setWindowTitle("Über Zeitzeuge")
        msg.setTextFormat(Qt.RichText)
        msg.setText(
            "<b>Zeitzeuge</b><br>Version 3.3<br><br>"
            "<a href='https://github.com/fkroczak/Zeitzeuge'>github.com/fkroczak/Zeitzeuge</a>"
        )
        msg.setStandardButtons(QMessageBox.Ok)
        if os.path.exists(icon_path):
            msg.setIconPixmap(QIcon(icon_path).pixmap(64, 64))
        msg.exec_()

    # ---------------------- Tagesliste ----------------------------------------

    def update_day_list(self, activities):
        self.day_activities = activities
        colors = self.config.get("type_colors", {})
        self.table.setRowCount(len(activities))
        for row, a in enumerate(activities):
            start, end = parse_time(a["start"]), parse_time(a["end"])
            pix = QPixmap(10, 10)
            pix.fill(QColor(colors.get(a["type"], "#4682B4")))
            type_item = QTableWidgetItem(QIcon(pix), a["type"])
            values = [
                QTableWidgetItem(f"{start:%H:%M}"),
                QTableWidgetItem(f"{end:%H:%M}"),
                QTableWidgetItem(format_duration((end - start).total_seconds())),
                type_item,
                QTableWidgetItem(a.get("customer_name", "")),
                QTableWidgetItem(a.get("details", "")),
            ]
            for col, item in enumerate(values):
                item.setToolTip(item.text())
                self.table.setItem(row, col, item)
        self.update_status_text()

    def copy_selection(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            rows = range(self.table.rowCount())
        lines = []
        for row in rows:
            cells = [self.table.item(row, c).text() for c in range(self.table.columnCount())]
            lines.append(f"{cells[0]}–{cells[1]}\t" + "\t".join(cells[2:]).rstrip())
        QApplication.clipboard().setText("\n".join(lines))
        self.statusBar().showMessage(f"{len(lines)} Zeile(n) kopiert", 3000)

    def update_status_text(self):
        day = GERMAN.toString(self.current_date, "dddd, dd.MM.yyyy")
        n = len(self.day_activities)
        if n:
            total = format_duration(merged_seconds(self.day_activities))
            self.info_label.setText(f"{day}   ·   {n} Einträge   ·   belegt {total}")
        else:
            self.info_label.setText(f"{day}   ·   keine Einträge")

    # ---------------------- Datum / Navigation --------------------------------

    def date_changed(self, date: QDate):
        self.current_date = date
        self.timeline.draw_timeline(self.current_date)

    def show_previous_day(self):
        self.date_edit.setDate(self.current_date.addDays(-1))

    def show_next_day(self):
        self.date_edit.setDate(self.current_date.addDays(1))

    def show_today(self):
        self.date_edit.setDate(QDate.currentDate())

    def refresh(self):
        self.timeline.refresh()
        self.statusBar().showMessage("Logs neu eingelesen", 2000)

    def auto_refresh(self):
        if self.current_date == QDate.currentDate():
            self.timeline.refresh()

    # ---------------------- Zoom / Dark-Mode ----------------------------------

    def zoom_in(self):
        self.timeline.set_zoom(self.timeline.zoom_level * 1.25)

    def zoom_out(self):
        self.timeline.set_zoom(self.timeline.zoom_level / 1.25)

    def reset_zoom(self):
        self.timeline.zoom_level = 1.0
        self.timeline._first_draw = True  # wieder auf Arbeitszeit zentrieren
        self.timeline.draw_timeline(self.current_date)

    def toggle_dark_mode(self, enabled: bool):
        self.dark_mode = enabled
        self.config["dark_mode"] = enabled
        save_config(self.config)
        self.apply_style()

    def apply_style(self):
        theme = THEMES["dark" if self.dark_mode else "light"]
        sheet = STYLESHEET
        for key, value in theme.items():
            sheet = sheet.replace(f"${key}", value)
        # Palette passend setzen, sonst nutzen Tabellen/Scrollbars die Systemfarben
        pal = QPalette()
        for role, key in [(QPalette.Window, "bg"), (QPalette.WindowText, "text"),
                          (QPalette.Base, "surface"), (QPalette.AlternateBase, "alt"),
                          (QPalette.Text, "text"), (QPalette.Button, "bar"),
                          (QPalette.ButtonText, "text"), (QPalette.Highlight, "accent"),
                          (QPalette.ToolTipBase, "surface"), (QPalette.ToolTipText, "text"),
                          (QPalette.PlaceholderText, "muted")]:
            pal.setColor(role, QColor(theme[key]))
        pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
        self.setStyleSheet("")  # alte Farben vollständig entfernen
        QApplication.instance().setPalette(pal)
        self.setStyleSheet(sheet)
        self.timeline.set_dark_mode(self.dark_mode)

    # ---------------------- Einstellungen / Dialoge ---------------------------

    def _edit_log_settings(self, key, default_path, title):
        dialog = ConnectionSettingsDialog(
            self.config, key, [os.path.expandvars(default_path)], title, self
        )
        if dialog.exec_() == dialog.Accepted:
            self.config[f"{key}_paths"] = dialog.get_paths()
            self.config[f"{key}_timezone_correction"] = dialog.get_timezone_correction()
            save_config(self.config)
            self.timeline.refresh()

    def edit_teamviewer_settings(self):
        self._edit_log_settings(
            "teamviewer", r"%APPDATA%\TeamViewer\Connections.txt",
            "TeamViewer-Logeinstellungen",
        )

    def edit_rdm_settings(self):
        self._edit_log_settings(
            "rdm", r"%LOCALAPPDATA%\Devolutions\RemoteDesktopManager\Connections.log",
            "RDM-Logeinstellungen",
        )

    def edit_activity_types(self):
        dialog = ActivityTypeSettingsDialog(self.config, self)
        if dialog.exec_() == dialog.Accepted:
            self.config["activity_types"] = dialog.get_types()
            save_config(self.config)
            self.timeline.draw_timeline(self.current_date)


if __name__ == "__main__":
    QLocale.setDefault(GERMAN)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = TimelineApp()
    window.show()
    sys.exit(app.exec_())
