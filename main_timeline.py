import json
import os
import re
import sys
import warnings

from datetime import datetime

from PyQt5.QtCore import (QDate, QLocale, QObject, QProcess, QSize, Qt, QTimer,
                          QUrl, pyqtSignal)
from PyQt5.QtGui import (QColor, QDesktopServices, QIcon, QKeySequence, QPalette,
                         QPixmap)
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication, QProxyStyle,
                             QStyle, QStyleFactory,
                             QCheckBox, QComboBox, QDateEdit, QInputDialog, QDialog, QDialogButtonBox,
                             QFileDialog, QFormLayout, QHeaderView, QLabel, QLineEdit,
                             QMainWindow, QMenu, QMessageBox, QPushButton,
                             QSpinBox, QSplitter, QSystemTrayIcon, QTableWidget,
                             QTableWidgetItem, QToolBar, QToolButton,
                             QVBoxLayout, QWidget)

from activity_tracker import ActivityTracker
from browser_setup import BrowserSetupDialog, build_userscript
from call_import import start_call_server
from itm_reader import ItmReader
from pbx_reader import PbxReader, find_browser
import storage
from log_parsers import VpnParser
from settings_dialogs import (ActivityTypeSettingsDialog,
                              ConnectionSettingsDialog, WorkHoursDialog)
from grouping import format_tv_id, work_blocks
from timeline_only import (ActivityViewDialog, TimelineView, entry_color,
                           format_duration, parse_time, type_label)

warnings.filterwarnings("ignore", category=DeprecationWarning)

# Oberfläche mit der Windows-Anzeigegröße (125 %, 150 %, 200 %) mitskalieren.
# Muss vor dem Start der QApplication gesetzt werden.
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)


def resource_path(relative_path: str) -> str:
    """Pfad für Ressourcen, funktioniert im Script und in der PyInstaller-EXE."""
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS  # Temp-Ordner der EXE
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# Ordner der EXE (bzw. des Skripts). Früher lagen die Daten hier.
if hasattr(sys, "_MEIPASS"):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Daten: standardmäßig Dokumente\Zeitzeuge (im Menü änderbar)
DATA_DIR = storage.data_dir()
CONFIG_FILE = os.path.join(DATA_DIR, "zeitzeuge_config.json")
CALLS_FILE = os.path.join(DATA_DIR, "anrufe.json")
ACTIVITY_DIR = os.path.join(DATA_DIR, "aktivitaet")
# 3CX-Anmeldung immer lokal (nicht in OneDrive-synchronisierten Dokumenten)
PBX_PROFILE_DIR = os.path.join(storage.local_dir(), "3cx_profil")
ITM_FILE = os.path.join(DATA_DIR, "personalzeiten.json")
ITM_PROFILE_DIR = os.path.join(storage.local_dir(), "itm_profil")


class AppStyle(QProxyStyle):
    """Fusion mit gut sichtbarem Knopf für ausgeblendete Werkzeugleisten-Befehle.

    Ist das Fenster schmal (z. B. Laptop mit 200 % Anzeige), rutschen Knöpfe wie
    "Einstellungen" in diesen Knopf. Standard sind nur 12 px ohne erkennbares Symbol.
    """

    def __init__(self):
        super().__init__(QStyleFactory.create("Fusion"))

    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PM_ToolBarExtensionExtent:
            return 26
        return super().pixelMetric(metric, option, widget)


class CallSignal(QObject):
    # Signal aus dem Server-Thread sicher in den GUI-Thread bringen
    updated = pyqtSignal()



def clean_path(path):
    """Doppelte Backslashes in Pfaden entfernen (Netzwerkpfade \\\\server bleiben)."""
    if path.startswith("\\\\"):
        return "\\\\" + re.sub(r"\\{2,}", r"\\", path[2:])
    return re.sub(r"\\{2,}", r"\\", path)


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
            os.path.expandvars(r"%APPDATA%\TeamViewer\Connections.txt")
        ],
        "rdm_paths": [
            os.path.expandvars(
                r"%LOCALAPPDATA%\Devolutions\RemoteDesktopManager\Connections.log"
            )
        ],
        # VPN-Verbindungen (Logs von VPN-Clients und VPN-Einträge aus RDM)
        "vpn_enabled": True,
        "vpn_paths": VpnParser().default_paths,  # OpenVPN GUI, OpenVPN Connect, Sophos SSL VPN
        "vpn_timezone_correction": 0,  # VPN-Clients schreiben Ortszeit
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
        "calls_days_back": 14,  # 3CX: so viele Tage zurück lesen
        "calls_3cx_url": "https://voice.visaas.de:5001",

        # Aktivitätsprotokoll (aktives Fenster)
        "tracking_enabled": True,
        "tracking_idle_minutes": 5,
        "tracking_ignore": ["KeePass", "Bitwarden", "1Password", "Online-Banking"],
        "show_pc_in_list": False,

        "pbx_reader_enabled": False,  # 3CX direkt über Edge im Hintergrund lesen
        "itm_url": "https://app.itm-gruppe.com",
        "itm_reader_enabled": False,  # Personalzeiten aus der ITM-Zeiterfassung lesen
        "close_to_tray": True,

        # Tagesliste: "grouped" (zusammengefasst), "single" (einzeln), "blocks" (Arbeitsblöcke)
        "list_view": "grouped",
        "merge_gap_minutes": 5,    # Verbindungen mit kürzerer Pause werden eine Zeile
        "block_gap_minutes": 10,   # Einträge mit kürzerer Pause werden ein Arbeitsblock
        "teamviewer_names": {},    # TeamViewer-ID -> Name, z. B. {"1076789144": "Müller GmbH"}
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
    # Arbeitszeiten pro Wochentag (aus work_start/work_end übernommen)
    if "work_days" not in cfg:
        span = f"{cfg['work_start']}-{cfg['work_end']}"
        cfg["work_days"] = {d: (span if i < 5 else "")
                            for i, d in enumerate(["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"])}
    cfg["type_colors"].setdefault("Telefonat", "#27AE60")
    for kind, color in [("VPN-Verbindung", "#00B894"), ("SSH-Verbindung", "#E67E22"),
                        ("FTP-Verbindung", "#7F8C8D"), ("TeamViewer-Verbindung", "#3460DB"),
                        ("Zugangsdaten", "#9B59B6"), ("Arbeitsblock", "#5B8DEF")]:
        cfg["type_colors"].setdefault(kind, color)
    # Alte Standardpfade enthielten doppelte Backslashes (C:\Users\x\\TeamViewer)
    for key in ("teamviewer_paths", "rdm_paths", "vpn_paths"):
        cfg[key] = [clean_path(p) for p in cfg.get(key, [])]
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
        "accent": "#0067C0", "hover": "#E8EBEF", "pressed": "#DADEE3",
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
QToolButton:focus, QPushButton:focus { border: 2px solid $accent; }
QToolButton:focus { padding: 3px 7px; }
QPushButton:focus { padding: 5px 11px; }
QDateEdit:focus, QTimeEdit:focus, QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QListWidget:focus, QTableWidget:focus, QGraphicsView:focus {
    border: 1px solid $accent; }
QToolButton#qt_toolbar_ext_button { border: 1px solid $border; background-color: $hover; }
QLabel#hint { color: $muted; }
QPushButton:disabled, QToolButton:disabled, QLineEdit:disabled, QDateEdit:disabled,
QTimeEdit:disabled, QSpinBox:disabled, QCheckBox:disabled { color: $muted; }
QPushButton:disabled { background-color: $surface; }
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

        # Daten, die noch neben der EXE liegen, in den Datenordner umziehen
        moved = storage.move_data(APP_DIR, DATA_DIR)
        if moved:
            print(f"Nach {DATA_DIR} verschoben: {', '.join(moved)}")
        os.makedirs(DATA_DIR, exist_ok=True)
        self.config = load_config_with_defaults()
        self.dark_mode = self.config.get("dark_mode", False)
        self.current_date = QDate.currentDate()
        self.activities = []
        self.day_activities = []
        self.pc_activities = []
        self.list_entries = []
        self._quitting = False

        self._build_toolbar()

        # Timeline oben, Tagesliste unten
        self.timeline = TimelineView(self.activities, self.config, parent=self)
        self.timeline.day_loaded.connect(self.update_day_list)

        # Aktivitätsprotokoll: alle 5 Sekunden aktives Fenster abfragen
        self.tracker = None
        self.track_timer = QTimer(self)
        self.track_timer.timeout.connect(self.track_sample)
        self.set_tracking(self.config.get("tracking_enabled", True))

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
        self.table.setAccessibleName("Tagesliste")
        self.table.cellDoubleClicked.connect(lambda row, _col: self.open_details(row))
        details_action = QAction("Details öffnen", self.table)
        details_action.setShortcuts([QKeySequence(Qt.Key_Return), QKeySequence(Qt.Key_Enter)])
        details_action.setShortcutContext(Qt.WidgetShortcut)
        details_action.triggered.connect(lambda: self.open_details(self.table.currentRow()))
        self.table.addAction(details_action)
        copy_action = QAction("Kopieren", self.table)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.setShortcutContext(Qt.WidgetShortcut)
        copy_action.triggered.connect(self.copy_selection)
        self.table.addAction(copy_action)
        name_action = QAction("TeamViewer-ID benennen …", self.table)
        name_action.triggered.connect(self.name_teamviewer_id)
        self.table.addAction(name_action)
        self.table.setContextMenuPolicy(Qt.ActionsContextMenu)

        self.timeline.setAccessibleName("Timeline des Tages")
        self.timeline.setAccessibleDescription(
            "Grafische Tagesübersicht. Dieselben Einträge stehen in der Tagesliste darunter.")

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
                CALLS_FILE, port=port, on_update=self.call_signal.updated.emit,
                script_provider=self.userscript_text,
            )
            self.calls_label.setText(
                f"Anrufempfang aktiv (Port {port})" if self.call_server
                else f"Anrufempfang: Port {port} belegt"
            )

        # Logs regelmäßig neu prüfen (nur geänderte Dateien werden gelesen)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.auto_refresh)
        self.refresh_timer.start(2 * 60 * 1000)

        self._build_tray()

        # 3CX direkt auslesen (Edge im Hintergrund)
        self.pbx_reader = None
        if self.config.get("pbx_reader_enabled", False):
            self.start_pbx_reader()

        # Personalzeiten aus der ITM-Zeiterfassung (Edge im Hintergrund)
        self.itm_reader = None
        if self.config.get("itm_reader_enabled", False):
            self.start_itm_reader()

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
        self.date_edit.setAccessibleName("Datum")
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
        tb.addAction(self._action("Ganzer Tag", self.timeline_whole_day, "Ctrl+0",
                                  "Ganzen Tag zeigen (oder Doppelklick in die Timeline)"))
        tb.addAction(self._action("Arbeitszeit", self.timeline_work_time, "Ctrl+9",
                                  "Arbeitszeit des Tages zeigen"))

        spacer = QWidget(self)
        spacer.setSizePolicy(spacer.sizePolicy().Expanding, spacer.sizePolicy().Preferred)
        spacer.setStyleSheet("background: transparent;")
        tb.addWidget(spacer)

        self.view_combo = QComboBox(self)
        self.view_combo.setAccessibleName("Ansicht der Tagesliste")
        self.view_combo.setToolTip(
            "Zusammengefasst: Verbindungen und Passwort-/OTP-Anzeigen werden je Eintrag eine Zeile\n"
            "Einzeln: jede Zeile aus den Logs\n"
            "Arbeitsblöcke: alles mit kurzer Pause dazwischen als ein Block, z. B. fürs Ticket")
        for key, text in self.VIEWS:
            self.view_combo.addItem(text, key)
        self.view_combo.setCurrentIndex(
            max(0, self.view_combo.findData(self.config.get("list_view", "grouped"))))
        self.view_combo.currentIndexChanged.connect(self.change_view)
        tb.addWidget(self.view_combo)

        self.pc_list_action = QAction("PC-Verlauf in Liste", self)
        self.pc_list_action.setCheckable(True)
        self.pc_list_action.setChecked(self.config.get("show_pc_in_list", False))
        self.pc_list_action.setToolTip("Aktive Fenster in der Tagesliste anzeigen")
        self.pc_list_action.toggled.connect(self.toggle_pc_list)
        tb.addAction(self.pc_list_action)

        self.dark_action = QAction("Dunkel", self)
        self.dark_action.setCheckable(True)
        self.dark_action.setChecked(self.dark_mode)
        self.dark_action.setToolTip("Dunkles Design")
        self.dark_action.toggled.connect(self.toggle_dark_mode)
        tb.addAction(self.dark_action)

        # Gruppen: Anzeige | Datenquellen | Aufzeichnung | Speicher | Info
        menu = QMenu(self)
        menu.addAction("&Arbeitszeiten …", self.edit_work_hours)
        menu.addAction("Aktivitäts&typen und Farben …", self.edit_activity_types)
        menu.addSeparator()
        menu.addAction("Team&Viewer-Logs …", self.edit_teamviewer_settings)
        menu.addAction("&RDM-Logs …", self.edit_rdm_settings)
        menu.addAction("&VPN-Verbindungen …", self.edit_vpn_settings)
        menu.addSeparator()
        menu.addAction("3CX &direkt auslesen …", self.open_pbx_settings)
        menu.addAction("3CX über &Chrome/Tampermonkey einrichten …", self.open_browser_setup)
        menu.addAction("&ITM-Personalzeiten …", self.open_itm_settings)
        menu.addSeparator()
        self.tracking_action = menu.addAction("Aktive &Fenster aufzeichnen")
        self.tracking_action.setCheckable(True)
        self.tracking_action.setChecked(self.config.get("tracking_enabled", True))
        self.tracking_action.toggled.connect(self.toggle_tracking)
        menu.addSeparator()
        menu.addAction("&Speicherort ändern …", self.change_data_dir)
        menu.addAction("Daten&ordner öffnen",
                       lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(DATA_DIR)))
        menu.addSeparator()
        menu.addAction("Ü&ber Zeitzeuge", self.show_about)
        settings_btn = QToolButton(self)
        settings_btn.setText("&Einstellungen ▾")
        settings_btn.setAccessibleName("Einstellungen")
        settings_btn.setMenu(menu)
        settings_btn.setPopupMode(QToolButton.InstantPopup)
        tb.addWidget(settings_btn)

        # Screenreader lesen sonst nur "◀", "+" usw. vor
        for action in tb.actions():
            button = tb.widgetForAction(action)
            if isinstance(button, QToolButton) and not button.accessibleName():
                button.setAccessibleName(action.toolTip().split(" (")[0] or action.text())
        # Überlauf-Knopf, wenn das Fenster schmal ist (z. B. bei 200 % Anzeige)
        ext = tb.findChild(QToolButton, "qt_toolbar_ext_button")
        if ext:
            ext.setAccessibleName("Weitere Befehle")
            ext.setToolTip("Weitere Befehle")
            ext.setText("»")
            ext.setToolButtonStyle(Qt.ToolButtonTextOnly)

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

    def update_day_list(self, activities, pc_activities=None):
        self.day_activities = activities
        self.pc_activities = pc_activities or []
        entries = list(activities)
        if self.config.get("list_view") == "blocks":
            entries = work_blocks(entries, self.config.get("block_gap_minutes", 10))
        elif self.config.get("show_pc_in_list", False):
            entries += self.pc_activities
        entries.sort(key=lambda a: a["start"])
        self.list_entries = entries

        self.table.setRowCount(len(entries))
        for row, a in enumerate(entries):
            start, end = parse_time(a["start"]), parse_time(a["end"])
            pix = QPixmap(10, 10)
            if "app" in a:
                pix.fill(self.timeline.app_color(a["app"]))
            else:
                pix.fill(entry_color(a, self.config))
            type_item = QTableWidgetItem(QIcon(pix), type_label(a))
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

    VIEWS = [("grouped", "Zusammengefasst"), ("single", "Einzeln"), ("blocks", "Arbeitsblöcke")]

    def change_view(self, _index):
        self.config["list_view"] = self.view_combo.currentData()
        save_config(self.config)
        self.timeline.draw_timeline(self.current_date)

    def name_teamviewer_id(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.list_entries):
            return
        tv_id = self.list_entries[row].get("tv_id")
        if not tv_id:
            self.statusBar().showMessage("Die markierte Zeile ist keine TeamViewer-Verbindung", 4000)
            return
        names = self.config.setdefault("teamviewer_names", {})
        name, ok = QInputDialog.getText(
            self, "TeamViewer-ID benennen",
            f"Name für TeamViewer-ID {format_tv_id(tv_id)} (leer = Name entfernen):",
            text=names.get(tv_id, ""))
        if not ok:
            return
        if name.strip():
            names[tv_id] = name.strip()
        else:
            names.pop(tv_id, None)
        save_config(self.config)
        self.timeline.draw_timeline(self.current_date)

    def open_details(self, row):
        if 0 <= row < len(self.list_entries):
            ActivityViewDialog(self.list_entries[row], self).exec_()

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
        parts = [day]
        n = len(self.day_activities)
        if n:
            parts.append(f"{n} Einträge")
            parts.append(f"belegt {format_duration(merged_seconds(self.day_activities))}")
        else:
            parts.append("keine Einträge")
            missing = self.timeline.missing_sources()
            if missing:
                parts.append(f"keine Logdatei gefunden: {', '.join(missing)} "
                             "(Pfade unter Einstellungen ▾)")
        if self.pc_activities:
            parts.append(f"am PC aktiv {format_duration(merged_seconds(self.pc_activities))}")
        itm_day = self.itm_reader.day(self.current_date.toString("yyyy-MM-dd")) if self.itm_reader else None
        if itm_day and itm_day.get("gewertet") is not None:
            text = f"Personalzeit {format_duration(itm_day['gewertet'] * 60)}"
            if itm_day.get("soll"):
                text += f" (Soll {format_duration(itm_day['soll'] * 60)})"
            parts.append(text)
        self.info_label.setText("   ·   ".join(parts))

    # ---------------------- Datum / Navigation --------------------------------

    def date_changed(self, date: QDate):
        self.current_date = date
        self.timeline.draw_timeline(self.current_date)
        # Fehlende Daten für diesen Tag im Hintergrund nachlesen
        for reader in (self.pbx_reader, self.itm_reader):
            if reader:
                reader.want(date.toString("yyyy-MM-dd"))

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

    # ---------------------- Aktivitätsprotokoll -------------------------------

    def set_tracking(self, enabled):
        if enabled and not self.tracker:
            self.tracker = ActivityTracker(
                ACTIVITY_DIR,
                idle_limit=self.config.get("tracking_idle_minutes", 5) * 60,
                ignore=self.config.get("tracking_ignore", []),
            )
            self.track_timer.start(5000)
        elif not enabled and self.tracker:
            self.track_timer.stop()
            self.tracker.stop()
            self.tracker = None
        self.timeline.tracker = self.tracker

    def track_sample(self):
        if self.tracker and self.tracker.sample():
            # Ansicht höchstens alle 30 s neu zeichnen, und nur, wenn heute angezeigt wird
            now = datetime.now()
            last = getattr(self, "_last_track_draw", None)
            if (self.current_date == QDate.currentDate() and self.isVisible()
                    and (last is None or (now - last).total_seconds() > 30)):
                self._last_track_draw = now
                self.timeline.draw_timeline(self.current_date)

    def toggle_tracking(self, enabled):
        self.config["tracking_enabled"] = enabled
        save_config(self.config)
        self.set_tracking(enabled)
        self.timeline.draw_timeline(self.current_date)

    def toggle_pc_list(self, enabled):
        self.config["show_pc_in_list"] = enabled
        save_config(self.config)
        self.update_day_list(self.day_activities, self.pc_activities)

    # ---------------------- Browser-Anbindung ---------------------------------

    def userscript_text(self):
        with open(resource_path("zeitzeuge_anrufe.user.js"), "r", encoding="utf-8") as f:
            template = f.read()
        return build_userscript(template, self.config.get("calls_3cx_url", ""),
                                self.config.get("calls_port", 8765))

    def open_browser_setup(self):
        if not self.call_server:
            QMessageBox.warning(self, "Browser-Anbindung",
                                "Der Anrufempfang läuft nicht (Port belegt oder ausgeschaltet).")
            return
        BrowserSetupDialog(self.config, self.config.get("calls_port", 8765),
                           save_config, self).exec_()

    # ---------------------- 3CX direkt auslesen -------------------------------

    def start_pbx_reader(self):
        if self.pbx_reader or PbxReader is None:
            return
        self.pbx_reader = PbxReader(
            self.config.get("calls_3cx_url", ""), CALLS_FILE, PBX_PROFILE_DIR,
            open(resource_path("zeitzeuge_anrufe.user.js"), encoding="utf-8").read(), self,
            days_back=self.config.get("calls_days_back", 14),
        )
        self.pbx_reader.status_changed.connect(self.calls_label.setText)
        self.pbx_reader.calls_added.connect(
            lambda _n: self.timeline.draw_timeline(self.current_date)
        )
        self.pbx_reader.login_required.connect(self.on_pbx_login_required)
        self.pbx_reader.recording_done.connect(self.on_recording_done)
        self.pbx_reader.start()
        self.calls_label.setText("3CX: wird geladen …")

    def stop_pbx_reader(self):
        if self.pbx_reader:
            self.pbx_reader.stop()
            self.pbx_reader.deleteLater()
            self.pbx_reader = None

    def on_pbx_login_required(self):
        if self.tray:
            self.tray.showMessage(
                "3CX-Anmeldung nötig",
                "Zeitzeuge kann die Anrufliste nicht lesen. Klick hier, um dich anzumelden.",
                QSystemTrayIcon.Warning, 8000,
            )

    def show_pbx_login(self):
        if not self.pbx_reader:
            self.start_pbx_reader()
        if self.pbx_reader:
            self.pbx_reader.show_login(self)

    # Texte und Schlüssel der beiden Hintergrund-Leser (für den gemeinsamen Dialog)
    READER_DIALOGS = {
        "pbx": dict(
            title="3CX direkt auslesen",
            text="Zeitzeuge öffnet den 3CX-Webclient unsichtbar mit Microsoft Edge (eigenes Profil) "
                 "und liest jede Minute die Anrufliste. Es hält die eingestellten Tage vollständig, "
                 "ältere Tage beim Blättern. Tampermonkey wird dafür nicht gebraucht.\n\n"
                 "Zum Anmelden öffnet sich ein Edge-Fenster: anmelden und das Fenster schließen. "
                 "Die Anmeldung bleibt gespeichert. Ton, Mikrofon und Benachrichtigungen sind gesperrt.",
            url_label="3CX-Adresse:", url_key="calls_3cx_url", enabled_key="pbx_reader_enabled",
            enabled_text="Anrufliste automatisch im Hintergrund lesen",
            login_text="Bei 3CX anmelden …", attr="pbx_reader",
            record_text="Ein Edge-Fenster mit dem 3CX-Webclient öffnet sich.\n\n"
                        "1. Falls nötig anmelden.\n"
                        "2. Die Anrufliste öffnen und ein Stück nach unten scrollen, "
                        "damit ältere Anrufe nachladen.\n"
                        "3. Das Fenster schließen.\n\n"
                        "Zeitzeuge speichert dann die Mitschnitt-Datei im Datenordner.",
        ),
        "itm": dict(
            title="ITM-Personalzeiten",
            text="Zeitzeuge öffnet die ITM-Zeiterfassung unsichtbar mit Microsoft Edge (eigenes Profil) "
                 "und liest deine Personalzeiten: heute alle 5 Minuten, andere Tage beim Blättern. "
                 "Die Timeline hebt dann deine gestempelte Arbeitszeit hervor, Pausen sind abgedunkelt."
                 "\n\nZum Anmelden öffnet sich ein Edge-Fenster: anmelden und das Fenster schließen.",
            url_label="ITM-Adresse:", url_key="itm_url", enabled_key="itm_reader_enabled",
            enabled_text="Personalzeiten automatisch im Hintergrund lesen",
            login_text="Bei ITM anmelden …", attr="itm_reader",
            record_text="Ein Edge-Fenster mit der ITM-Zeiterfassung öffnet sich.\n\n"
                        "1. Falls nötig anmelden.\n"
                        "2. Zwei oder drei andere Tage in der Tagesübersicht aufrufen.\n"
                        "3. Das Fenster schließen.\n\n"
                        "Zeitzeuge speichert dann die Mitschnitt-Datei im Datenordner.",
        ),
    }

    def open_pbx_settings(self):
        self._open_reader_settings("pbx")

    def open_itm_settings(self):
        self._open_reader_settings("itm")

    def build_pbx_dialog(self):
        return self.build_reader_dialog("pbx")

    def build_itm_dialog(self):
        return self.build_reader_dialog("itm")

    def _open_reader_settings(self, kind):
        if not find_browser():
            QMessageBox.warning(self, self.READER_DIALOGS[kind]["title"],
                                "Microsoft Edge oder Google Chrome wurde nicht gefunden.")
            return
        self.build_reader_dialog(kind).exec_()

    def build_reader_dialog(self, kind):
        """Einstellungen für einen Hintergrund-Leser (3CX oder ITM)."""
        spec = self.READER_DIALOGS[kind]
        attr, url_key, enabled_key = spec["attr"], spec["url_key"], spec["enabled_key"]
        start = self.start_pbx_reader if kind == "pbx" else self.start_itm_reader
        stop = self.stop_pbx_reader if kind == "pbx" else self.stop_itm_reader

        dialog = QDialog(self)
        dialog.setWindowTitle(spec["title"])
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)
        info = QLabel(spec["text"])
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        url_edit = QLineEdit(self.config.get(url_key, ""))
        form.addRow(spec["url_label"], url_edit)
        enabled = QCheckBox(spec["enabled_text"])
        enabled.setChecked(self.config.get(enabled_key, False))
        form.addRow("", enabled)
        days = None
        if kind == "pbx":
            days = QSpinBox()
            days.setRange(1, 365)
            days.setSuffix(" Tage")
            days.setValue(self.config.get("calls_days_back", 14))
            days.setToolTip("Ältere Tage liest Zeitzeuge nach, sobald du sie anzeigst.")
            form.addRow("Anrufe zurück lesen:", days)
        layout.addLayout(form)

        status = QLabel("Aus")
        status.setObjectName("hint")
        layout.addWidget(status)

        def apply():
            url = url_edit.text().strip().rstrip("/")
            changed = url != self.config.get(url_key)
            if days and days.value() != self.config.get("calls_days_back", 14):
                self.config["calls_days_back"] = days.value()
                changed = True  # Leser mit der neuen Zahl neu starten
            self.config[url_key] = url
            self.config[enabled_key] = enabled.isChecked()
            save_config(self.config)
            if changed or not enabled.isChecked():
                stop()
            if enabled.isChecked():
                start()
            return getattr(self, attr)

        def follow_status():
            # Status im Dialog live mitlaufen lassen
            reader = getattr(self, attr)
            if reader:
                status.setText(reader.status)
                reader.status_changed.connect(status.setText)

        def login():
            enabled.setChecked(True)
            reader = apply()
            if reader:
                follow_status()
                reader.show_login(self)

        def record():
            enabled.setChecked(True)
            reader = apply()
            if not reader:
                return
            follow_status()
            path = os.path.join(DATA_DIR, f"mitschnitt_{kind}_{datetime.now():%Y-%m-%d_%H%M}.json")
            if reader.record(path):
                QMessageBox.information(dialog, "Abfragen mitschneiden", spec["record_text"])

        follow_status()

        login_btn = QPushButton(spec["login_text"])
        login_btn.clicked.connect(login)
        record_btn = QPushButton("Abfragen &mitschneiden …")
        record_btn.setToolTip("Aufzeichnen, welche Abfragen die Seite an ihren Server schickt "
                              "(Passwörter und Token werden geschwärzt).")
        record_btn.clicked.connect(record)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.addButton(login_btn, QDialogButtonBox.ActionRole)
        buttons.addButton(record_btn, QDialogButtonBox.ActionRole)
        buttons.accepted.connect(lambda: (apply(), dialog.accept()))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog

    def on_recording_done(self, path):
        if not path:
            QMessageBox.warning(self, "Abfragen mitschneiden",
                                "Der Mitschnitt hat nicht geklappt. Details stehen in der Statuszeile.")
            return
        box = QMessageBox(QMessageBox.Information, "Mitschnitt gespeichert",
                          f"Gespeichert unter:\n{path}\n\n"
                          "Passwörter, Token und Cookie-Werte sind geschwärzt, Antworten gekürzt. "
                          "Die Datei kann trotzdem Namen und Nummern aus der Anrufliste enthalten. "
                          "Schau sie vor dem Weitergeben kurz durch.", parent=self)
        open_btn = box.addButton("Ordner öffnen", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec_()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    # ---------------------- ITM-Personalzeiten --------------------------------

    def start_itm_reader(self):
        if self.itm_reader:
            return
        self.itm_reader = ItmReader(self.config.get("itm_url", ""), ITM_FILE, ITM_PROFILE_DIR, self)
        self.itm_reader.status_changed.connect(
            lambda text: self.statusBar().showMessage(text, 5000)
        )
        self.itm_reader.day_read.connect(
            lambda d: self.timeline.draw_timeline(self.current_date)
            if d == self.current_date.toString("yyyy-MM-dd") else None
        )
        self.itm_reader.login_required.connect(
            lambda: self.tray and self.tray.showMessage(
                "ITM-Anmeldung nötig",
                "Zeitzeuge kann die Personalzeiten nicht lesen. Klick hier, um dich anzumelden.",
                QSystemTrayIcon.Warning, 8000,
            )
        )
        self.itm_reader.recording_done.connect(self.on_recording_done)
        self.timeline.personal_day = self.itm_reader.day
        self.itm_reader.start()
        self.itm_reader.want(self.current_date.toString("yyyy-MM-dd"))

    def stop_itm_reader(self):
        if self.itm_reader:
            self.itm_reader.stop()
            self.itm_reader.deleteLater()
            self.itm_reader = None
            self.timeline.personal_day = None

    # ---------------------- Speicherort ----------------------------------------

    def change_data_dir(self):
        new_dir = QFileDialog.getExistingDirectory(
            self, f"Speicherort wählen (bisher: {DATA_DIR})", DATA_DIR
        )
        if not new_dir or os.path.abspath(new_dir) == os.path.abspath(DATA_DIR):
            return
        answer = QMessageBox.question(
            self, "Speicherort ändern",
            f"Config, Anrufe und Aktivitätsprotokoll werden nach\n{new_dir}\n"
            "verschoben. Zeitzeuge startet danach neu.",
        )
        if answer != QMessageBox.Yes:
            return
        # Erst alles anhalten, was in die Dateien schreibt
        if self.tracker:
            self.tracker.stop()
        for reader in (self.pbx_reader, self.itm_reader):
            if reader:
                reader.stop()
        save_config(self.config)
        try:
            storage.move_data(DATA_DIR, new_dir)
            storage.set_data_dir(new_dir)
        except OSError as e:
            QMessageBox.warning(self, "Speicherort ändern", f"Verschieben fehlgeschlagen:\n{e}")
            return
        self.restart()

    def restart(self):
        if hasattr(sys, "_MEIPASS"):
            QProcess.startDetached(sys.executable, [])
        else:
            QProcess.startDetached(sys.executable, [os.path.abspath(__file__)])
        self.quit_app()

    # ---------------------- Infobereich (Tray) --------------------------------

    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("Zeitzeuge")
        menu = QMenu(self)
        menu.addAction("Ö&ffnen", self.show_from_tray)
        menu.addSeparator()
        menu.addAction("&Beenden", self.quit_app)
        self.tray.setContextMenu(menu)
        # Klick auf die Meldung "3CX-Anmeldung nötig" öffnet die Anmeldung
        self.tray.messageClicked.connect(self.on_tray_message_clicked)
        self.tray.activated.connect(
            lambda reason: self.show_from_tray()
            if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None
        )
        self.tray.show()

    def on_tray_message_clicked(self):
        """Klick auf "Anmeldung nötig" öffnet die passende Anmeldung."""
        if self.pbx_reader and self.pbx_reader.needs_login:
            self.show_pbx_login()
        elif self.itm_reader and self.itm_reader.needs_login:
            self.itm_reader.show_login(self)

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.timeline.draw_timeline(self.current_date)

    def quit_app(self):
        self._quitting = True
        if self.tracker:
            self.tracker.stop()
        for reader in (self.pbx_reader, self.itm_reader):
            if reader:
                reader.stop()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if self.tray and self.config.get("close_to_tray", True) and not self._quitting:
            event.ignore()
            self.hide()
            if not getattr(self, "_tray_hint_shown", False):
                self._tray_hint_shown = True
                self.tray.showMessage(
                    "Zeitzeuge läuft weiter",
                    "Zeitzeuge zeichnet im Hintergrund weiter auf. "
                    "Beenden über das Symbol im Infobereich.",
                    QSystemTrayIcon.Information, 4000,
                )
            return
        self.quit_app()
        super().closeEvent(event)

    # ---------------------- Zoom / Dark-Mode ----------------------------------

    def zoom_in(self):
        self.timeline.set_zoom(self.timeline.zoom_level * 1.25)

    def zoom_out(self):
        self.timeline.set_zoom(self.timeline.zoom_level / 1.25)

    def timeline_whole_day(self):
        self.timeline.show_whole_day()

    def timeline_work_time(self):
        self.timeline.show_work_time()

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

    def _edit_log_settings(self, key, default_path, title, **options):
        defaults = default_path if isinstance(default_path, list) else [default_path]
        dialog = ConnectionSettingsDialog(
            self.config, key, [os.path.expandvars(p) for p in defaults], title, self, **options
        )
        if dialog.exec_() == dialog.Accepted:
            self.config[f"{key}_paths"] = dialog.get_paths()
            if dialog.enabled_box:
                self.config[f"{key}_enabled"] = dialog.enabled_box.isChecked()
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

    def edit_vpn_settings(self):
        self._edit_log_settings(
            "vpn", VpnParser().default_paths, "VPN-Verbindungen",
            enabled_text="VPN-Verbindungen auslesen und anzeigen (auch die VPN-Einträge aus RDM)",
            folders=True,
            hint="Logdateien oder Ordner deiner VPN-Clients, z. B. OpenVPN GUI "
                 "(%USERPROFILE%\\OpenVPN\\log), OpenVPN Connect oder Sophos SSL VPN. "
                 "Bei einem Ordner zählen alle .log- und .txt-Dateien darin, "
                 "der Dateiname wird zum Verbindungsnamen.",
        )

    def edit_work_hours(self):
        dialog = WorkHoursDialog(self.config, self)
        if dialog.exec_() == dialog.Accepted:
            self.config["work_days"] = dialog.get_work_days()
            save_config(self.config)
            self.timeline._first_draw = True  # auf die neue Arbeitszeit springen
            self.timeline.draw_timeline(self.current_date)

    def edit_activity_types(self):
        dialog = ActivityTypeSettingsDialog(self.config, self)
        if dialog.exec_() == dialog.Accepted:
            self.config["activity_types"] = dialog.get_types()
            save_config(self.config)
            self.timeline.draw_timeline(self.current_date)


if __name__ == "__main__":
    QLocale.setDefault(GERMAN)
    app = QApplication(sys.argv)
    app.setStyle(AppStyle())
    app.setQuitOnLastWindowClosed(False)
    window = TimelineApp()
    from hang_watch import HangWatch
    hang_watch = HangWatch(os.path.join(DATA_DIR, "haenger.log"), app)
    if "--minimized" in sys.argv or window.config.get("start_minimized", False):
        if not window.tray:
            window.showMinimized()
    else:
        window.show()
    sys.exit(app.exec_())
