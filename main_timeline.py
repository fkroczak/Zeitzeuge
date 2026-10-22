import json
import os
import re
import sys
import threading
import time
import traceback
import warnings

from datetime import datetime, timedelta

from PyQt5.QtCore import (QDate, QLibraryInfo, QLocale, QProcess, QSize, Qt,
                          QTimer, QTranslator, QUrl)
from PyQt5.QtGui import (QColor, QDesktopServices, QFont, QIcon, QKeySequence, QPalette,
                         QPixmap)
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication, QProxyStyle,
                             QStyle, QStyleFactory,
                             QCheckBox, QComboBox, QDateEdit, QInputDialog, QDialog, QDialogButtonBox,
                             QFileDialog, QFormLayout, QHeaderView, QLabel, QLineEdit,
                             QMainWindow, QMenu, QMessageBox, QPushButton,
                             QSpinBox, QSplitter, QSystemTrayIcon, QTableWidget,
                             QTableWidgetItem, QToolBar, QToolButton,
                             QActionGroup, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget)

from activity_tracker import ActivityTracker, tracking_filters
from ai_classifier import AI_TYPE, AiClassifier, AiStore
import icons
import safe_io
import storage
from log_parsers import VpnParser
from vpn_reader import vpn_sources
from journal import Journal, describe, entry_key as journal_key, open_entry, suggest_category, suggest_customer, ticket_line
from journal_dialogs import DocPromptDialog, EntryDialog, PromptWindow, default_span
from settings_dialogs import (ActivityTypeSettingsDialog, AiSettingsDialog,
                              ConnectionSettingsDialog, WorkHoursDialog)
from settings_dialogs import RulesDialog, TrackingFilterDialog
import rules
from grouping import format_tv_id, group_entries, work_blocks
from timeline_only import (ActivityViewDialog, TimelineView, ai_copy_text, entry_color,
                           format_duration, parse_time, row_kind, type_label)

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
VPN_FILE = os.path.join(DATA_DIR, "vpn_verbindungen.json")
ACTIVITY_DIR = os.path.join(DATA_DIR, "aktivitaet")
# 3CX-Anmeldung immer lokal (nicht in OneDrive-synchronisierten Dokumenten)
PBX_PROFILE_DIR = os.path.join(storage.local_dir(), "3cx_profil")
ITM_FILE = os.path.join(DATA_DIR, "personalzeiten.json")
ITM_PROFILE_DIR = os.path.join(storage.local_dir(), "itm_profil")
AI_DIR = os.path.join(DATA_DIR, "ki_vorschlaege")
JOURNAL_DIR = os.path.join(DATA_DIR, "taetigkeiten")
# Fehler und beiseitegelegte Dateien stehen in fehler.log (siehe safe_io)
safe_io.set_log_path(os.path.join(DATA_DIR, "fehler.log"))
CONFIG_LOCKED = False  # Config war beim Start gesperrt: dann nichts darüber speichern


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

    def styleHint(self, hint, option=None, widget=None, data=None):
        # Dialogknöpfe überall wie unter Windows: OK links von Abbrechen, ohne Symbole
        if hint == QStyle.SH_DialogButtonLayout:
            return QDialogButtonBox.WinLayout
        if hint == QStyle.SH_DialogButtonBox_ButtonsHaveIcons:
            return 0
        return super().styleHint(hint, option, widget, data)


def install_translator(app):
    """Qt-eigene Texte (OK/Abbrechen, Ja/Nein, Kalender) auf Deutsch."""
    translator = QTranslator(app)
    if translator.load(GERMAN, "qtbase", "_", QLibraryInfo.location(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
    return translator



def clean_path(path):
    """Doppelte Backslashes in Pfaden entfernen (Netzwerkpfade \\\\server bleiben)."""
    if path.startswith("\\\\"):
        return "\\\\" + re.sub(r"\\{2,}", r"\\", path[2:])
    return re.sub(r"\\{2,}", r"\\", path)


def load_config_with_defaults():
    defaults = {
        "activity_types": [
            # Remote / Zugänge
            "VPN-Sitzung",
            "RDP-Sitzung",
            "SSH-Sitzung",
            "TeamViewer",
            "RDP-Verbindung",
            "SSH",
            "VPN",
            "Website-Verbindung",

            # Admin-Oberflächen / Dienste
            "Nextcloud-Admin",
            "NAS-Admin",
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
            # Remote / Zugänge
            "VPN-Sitzung":           "#00B894",  # Türkis
            "RDP-Sitzung":           "#F1C40F",  # Gelb
            "SSH-Sitzung":           "#E67E22",  # Orange

            # Admin-Oberflächen / Dienste
            "Nextcloud-Admin":       "#3498DB",  # Blau
            "NAS-Admin":             "#16A085",  # Petrol
            "Website-Admin":         "#1ABC9C",  # Türkisgrün
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
        # Datenquellen, einzeln im Menü "Datenquellen" ein- und ausschaltbar
        "teamviewer_enabled": True,
        "rdm_enabled": True,
        "sophos_enabled": True,
        "forti_enabled": True,
        # Weitere VPN-Clients (OpenVPN usw.) über ihre Logdateien
        "vpn_enabled": True,
        "vpn_paths": VpnParser().default_paths,  # OpenVPN GUI, OpenVPN Connect, Sophos SSL VPN
        "vpn_timezone_correction": 0,  # VPN-Clients schreiben Ortszeit
        # Sophos Connect (scvpn.log, scgui.log, charon.log – charon.log enthält auch FortiClient)
        "sophos_connect_dirs": [
            r"C:\Program Files (x86)\Sophos\Connect",
            r"C:\Program Files\Sophos\Connect",
        ],
        # Eigene VPN-Aufzeichnung: Teil der Adapterbeschreibung -> Quelle
        "vpn_monitor_enabled": True,
        "vpn_adapters": {"Sophos": "Sophos", "Fortinet": "FortiClient"},
        # deine gewünschten Zeitzonen
        "timezone_correction": 0,
        "teamviewer_timezone_correction": 1,
        "rdm_timezone_correction": 0,

        "dark_mode": False,
        "start_minimized": False,

        # Anrufe aus 3CX
        "calls_ignore_missed": True,
        "calls_min_duration": 0,
        "calls_days_back": 14,  # 3CX: so viele Tage zurück lesen
        "calls_3cx_url": "https://voice.visaas.de:5001",

        # Aktivitätsprotokoll (aktives Fenster)
        "tracking_enabled": True,
        "tracking_idle_minutes": 5,
        "tracking_ignore": ["KeePass", "Bitwarden", "1Password", "Online-Banking"],
        # Fenster-Filter: "blacklist" = alles außer Sperrliste, "whitelist" = nur tracking_allow
        "tracking_mode": "blacklist",
        "tracking_skip": [],               # gar nicht aufzeichnen (Lücke)
        "tracking_allow": [],              # Erlaubt-Liste für den Whitelist-Modus
        "tracking_whitelist_other": "mask",  # andere Fenster: "mask" = "(andere)", "skip" = Lücke
        # Klassifizierung ohne KI (rules.py); Reihenfolge = Priorität
        "rules": rules.default_rules(),
        "rules_gap_minutes": 5,
        "rules_min_minutes": 2,
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

        # KI-Vorschläge (Anthropic). Der API-Schlüssel steht nicht hier, sondern lokal.
        "ai_model": "claude-opus-5-5",
        "ai_effort": "low",
        "ai_send_window_titles": True,
        "ai_auto": False,          # vergangene Tage beim Anzeigen automatisch einordnen

        # Eigene Zeilen oben in der Timeline: Doku (eigene Tätigkeiten), Regeln, KI
        "timeline_rows": {"doc": True, "rule": True, "ai": True},
        # Nachfragen nach erkannten Tätigkeiten ("Was hast du gemacht?")
        "prompt_mode": "window",       # "window" (kleines Fenster), "tray" (nur Meldung), "off"
        "prompt_min_minutes": 5,       # kürzere Tätigkeiten nicht nachfragen
        "prompt_sources": ["connections", "calls"],  # auch "rules" (Blöcke aus den Regeln)
        "prompt_snooze_minutes": 15,   # "Später fragen"
        "prompt_on_quit": True,        # beim Beenden an offene Tätigkeiten erinnern
        "prompt_end_of_day": True,     # nach Feierabend an offene Tätigkeiten erinnern
    }
    # Kaputte Datei wird beiseitegelegt (zeitzeuge_config.json.defekt-…), nicht überschrieben
    global CONFIG_LOCKED
    try:
        cfg = safe_io.read_json(CONFIG_FILE, {}, expect=dict, raise_locked=True)
    except safe_io.FileLocked:
        cfg = {}
        CONFIG_LOCKED = True
        safe_io.report("zeitzeuge_config.json ist gesperrt. Zeitzeuge startet mit Standardwerten "
                       "und speichert Einstellungen erst nach einem Neustart.")

    # Früher schaltete "vpn_enabled" auch Sophos Connect und FortiClient ab
    for key in ("sophos_enabled", "forti_enabled"):
        if key not in cfg and "vpn_enabled" in cfg:
            cfg[key] = cfg["vpn_enabled"]
    # Defaults mergen
    for k, v in defaults.items():
        if isinstance(v, (dict, list)) and not isinstance(cfg.get(k, v), type(v)):
            safe_io.report(f"Einstellung „{k}“ war ungültig und steht wieder auf Standard.")
            cfg[k] = v
        cfg.setdefault(k, v)
    # Arbeitszeiten pro Wochentag (aus work_start/work_end übernommen)
    if not isinstance(cfg.get("work_days"), dict):
        span = f"{cfg['work_start']}-{cfg['work_end']}"
        cfg["work_days"] = {d: (span if i < 5 else "")
                            for i, d in enumerate(["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"])}
    cfg["type_colors"].setdefault("Telefonat", "#27AE60")
    for kind, color in [("VPN-Verbindung", "#00B894"), ("SSH-Verbindung", "#E67E22"),
                        ("FTP-Verbindung", "#7F8C8D"), ("TeamViewer-Verbindung", "#3460DB"),
                        ("Zugangsdaten", "#9B59B6"), ("Arbeitsblock", "#5B8DEF"),
                        (AI_TYPE, "#A55EEA"), ("Dokumentiert", "#2E9E5B"),
                        ("Undokumentiert", "#E67E22"), ("Klassifizierung", "#8E7CC3")]:
        cfg["type_colors"].setdefault(kind, color)
    # Alte Standardpfade enthielten doppelte Backslashes (C:\Users\x\\TeamViewer)
    for key in ("teamviewer_paths", "rdm_paths", "vpn_paths"):
        cfg[key] = [clean_path(p) for p in cfg.get(key, []) if isinstance(p, str)]
    if "Telefonat" not in cfg["activity_types"]:
        cfg["activity_types"].append("Telefonat")
    cfg["activity_types"] = list(dict.fromkeys(cfg["activity_types"]))  # alte Doppelte entfernen

    # gleich zurückschreiben (damit neue Keys persistieren), atomar
    if not CONFIG_LOCKED:
        safe_io.write_json(CONFIG_FILE, cfg, indent=2)

    return cfg


def save_config(config: dict):
    if CONFIG_LOCKED:  # sonst stünden statt deiner Einstellungen nur Standardwerte in der Datei
        safe_io.log("zeitzeuge_config.json war beim Start gesperrt, Einstellungen nicht gespeichert")
        return
    safe_io.write_json(CONFIG_FILE, config, indent=4)


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
QWidget { background-color: $bg; color: $text; font-size: 13px;
          font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", Arial, sans-serif; }
QToolBar { background-color: $bar; border: none; border-bottom: 1px solid $border;
           padding: 6px 8px; spacing: 4px; }
QToolBar::separator { background: $border; width: 1px; margin: 6px 6px; }
QToolBar#tools, QToolBar#fixed { border: none; padding: 0; background: transparent; }
QToolButton { background: transparent; border: 1px solid transparent;
              border-radius: 6px; padding: 4px 6px; }
QToolButton:hover { background-color: $hover; }
QToolButton:pressed, QToolButton:checked { background-color: $pressed; border-color: $border; }
QToolButton::menu-indicator { image: none; }
QStatusBar { background-color: $bar; color: $muted; border-top: 1px solid $border; }
QStatusBar QLabel { background: transparent; color: $muted; padding: 3px 8px; }
QStatusBar QToolButton { color: $text; padding: 2px 8px; margin: 2px 4px; }
QStatusBar::item { border: none; }
QDateEdit, QLineEdit, QTextEdit, QComboBox, QSpinBox, QTimeEdit, QListWidget {
    background-color: $surface; color: $text; border: 1px solid $border;
    border-radius: 6px; padding: 4px 6px; selection-background-color: $accent;
    selection-color: #FFFFFF; }
QDateEdit, QComboBox { min-height: 22px; }
QSpinBox, QTimeEdit { padding-right: 6px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { width: 0; border: none; }
QDateEdit { min-width: 120px; }
QComboBox QAbstractItemView { padding: 4px; outline: none; }
QPushButton { background-color: $hover; color: $text; border: 1px solid $border;
              border-radius: 6px; padding: 6px 14px; min-width: 80px; }
QPushButton:hover { background-color: $pressed; }
QPushButton:default { background-color: $accent; color: #FFFFFF; border-color: $accent; }
QToolButton:focus, QPushButton:focus { border: 2px solid $accent; }
QToolButton:focus { padding: 3px 5px; }
QPushButton:focus { padding: 5px 13px; }
QPushButton:default:focus { border-color: $text; }
QDateEdit:focus, QTimeEdit:focus, QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QListWidget:focus, QTableWidget:focus, QGraphicsView:focus {
    border: 1px solid $accent; }
QToolButton#qt_toolbar_ext_button { border: 1px solid $border; background-color: $hover; }
QLabel#hint { color: $muted; }
QPushButton:disabled, QToolButton:disabled, QLineEdit:disabled, QDateEdit:disabled,
QTimeEdit:disabled, QSpinBox:disabled, QCheckBox:disabled { color: $muted; }
QPushButton:disabled { background-color: $surface; }
QGroupBox { border: 1px solid $border; border-radius: 8px; margin-top: 1.2em;
            padding: 12px 8px 8px 8px; background-color: $surface; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
QGroupBox QWidget { font-weight: normal; }
QGroupBox QLabel, QGroupBox QCheckBox { background: transparent; }
QCheckBox { spacing: 8px; }
QMenu { background-color: $surface; border: 1px solid $border; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 6px 28px 6px 10px; border-radius: 4px; }
QMenu::item:selected { background-color: $hover; color: $text; }
QMenu::item:disabled { color: $muted; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QMenu::icon { padding-left: 6px; }
QGraphicsView { border: 1px solid $border; border-radius: 8px; }
QTableWidget { background-color: $surface; alternate-background-color: $alt;
               border: 1px solid $border; border-radius: 8px; gridline-color: transparent;
               selection-background-color: $accent; selection-color: #FFFFFF; }
QTableWidget::item { padding: 2px 8px; border: none; }
QHeaderView::section { background-color: $bar; color: $muted; border: none;
                       border-bottom: 1px solid $border; padding: 6px 8px; font-weight: 600; }
QTableCornerButton::section { background-color: $bar; border: none; }
QSplitter::handle { background: transparent; }
QSplitter::handle:vertical { height: 8px; }
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
QToolTip { background-color: #2b2b2b; color: #f0f0f0; border: 1px solid #555; padding: 4px 6px; }
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
        self._icon_actions = []  # (Aktion, Iconname): werden bei Designwechsel neu eingefärbt

        self._build_toolbar()

        # Timeline oben, Tagesliste unten
        self.timeline = TimelineView(self.activities, self.config, parent=self)
        self.timeline.day_loaded.connect(self.update_day_list)
        self.timeline.activity_dir = ACTIVITY_DIR

        # KI-Vorschläge (Claude): Ablage pro Tag, Aufruf im Hintergrund
        self.ai_store = AiStore(AI_DIR)
        self.ai = AiClassifier(self.ai_store, self.config, self)
        self.ai.finished.connect(self.on_ai_finished)
        self.ai.failed.connect(self.on_ai_failed)
        self.timeline.ai_entries = self.ai_store.entries
        self.timeline.ai_action.connect(self.on_ai_action)

        # Eigene Tätigkeiten (nachgetragen oder auf Nachfrage) und Regeln ohne KI
        self.journal = Journal(JOURNAL_DIR)
        self.timeline.doc_entries = self.doc_band
        self.timeline.rule_entries = self.rule_band
        self.timeline.doc_request.connect(self.on_doc_request)
        self._rule_cache = {}
        self._prompt_window = None
        self._prompt_queue = []
        self._prompt_asked = {}     # Schlüssel -> frühestens wieder fragen (datetime)
        self._started_at = datetime.now()
        self._reminded_day = None   # Feierabend-Erinnerung nur einmal am Tag

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
        details_action = QAction("&Details öffnen", self.table)
        details_action.setShortcuts([QKeySequence(Qt.Key_Return), QKeySequence(Qt.Key_Enter)])
        details_action.setShortcutContext(Qt.WidgetShortcut)
        details_action.triggered.connect(lambda: self.open_details(self.table.currentRow()))
        self.table.addAction(details_action)
        copy_action = QAction("&Kopieren", self.table)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.setShortcutContext(Qt.WidgetShortcut)
        copy_action.triggered.connect(self.copy_selection)
        self.table.addAction(copy_action)
        doc_action = QAction("Tätigkeit &eintragen / bearbeiten …", self.table)
        doc_action.triggered.connect(self.doc_for_row)
        self.table.addAction(doc_action)
        doc_delete = QAction("Tätigkeit &löschen", self.table)
        doc_delete.triggered.connect(self.delete_doc_row)
        self.table.addAction(doc_delete)
        self._icon_actions.append((doc_action, "edit"))
        name_action = QAction("&TeamViewer-ID benennen …", self.table)
        name_action.triggered.connect(self.name_teamviewer_id)
        self.table.addAction(name_action)
        for text, status in [("KI-Vorschlag übernehmen", "übernehmen"),
                             ("KI-Vorschlag verwerfen", "verwerfen")]:
            action = QAction(text, self.table)
            action.triggered.connect(lambda _c=False, s=status: self.ai_action_on_row(s))
            self.table.addAction(action)
        self._icon_actions += [(details_action, "details"), (copy_action, "copy"),
                               (name_action, "tag")]
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
        # Zustand der Fensteraufzeichnung, ein Klick schaltet sie um (wie im Infobereich)
        self.tracking_button = QToolButton(self)
        self.tracking_button.setAccessibleName("Fensteraufzeichnung ein- oder ausschalten")
        self.tracking_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.tracking_button.clicked.connect(self.tracking_action.toggle)
        self.statusBar().addPermanentWidget(self.tracking_button)
        self.statusBar().setSizeGripEnabled(False)

        self.timeline.calls_file = CALLS_FILE
        # VPN: eigene Aufzeichnung alle 30 Sekunden, Logs alle 2 Minuten – unabhängig von der Ansicht
        vpn = self.timeline.vpn_reader
        vpn.archive_file = VPN_FILE
        vpn.dirs = self.config.get("sophos_connect_dirs") or vpn.dirs
        vpn.adapters = self.config.get("vpn_adapters") or vpn.adapters
        vpn.sources = vpn_sources(self.config)
        self.vpn_timer = QTimer(self)
        self.vpn_timer.timeout.connect(self.vpn_sample)
        self.apply_vpn_monitor()

        # Logs regelmäßig neu prüfen (nur geänderte Dateien werden gelesen)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.auto_refresh)
        self.refresh_timer.start(2 * 60 * 1000)

        # Nachfragen nach erkannten Tätigkeiten: jede Minute prüfen
        self.prompt_timer = QTimer(self)
        self.prompt_timer.timeout.connect(self.check_prompts)
        self.prompt_timer.start(60 * 1000)

        self._build_tray()

        # 3CX direkt auslesen (Edge im Hintergrund)
        self.pbx_reader = None
        if self.config.get("pbx_reader_enabled", False):
            self.start_pbx_reader()

        # Personalzeiten aus der ITM-Zeiterfassung (Edge im Hintergrund)
        self.itm_reader = None
        if self.config.get("itm_reader_enabled", False):
            self.start_itm_reader()

        self.apply_style()  # setzt auch Icons und Aufzeichnungs-Zustand
        self.timeline.setFocus()
        # Erst zeichnen, wenn das Fenster seine echte Größe hat (spart ein Zeichnen beim Start).
        # Die Logs liest die Timeline dabei im Hintergrund.
        QTimer.singleShot(0, lambda: self.timeline.draw_timeline(self.current_date))
        self._init_robustness()

    # ---------------------- Werkzeugleiste ------------------------------------

    def _action(self, text, slot, shortcut=None, tip=None, icon_name=None):
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcuts(shortcut if isinstance(shortcut, list) else [shortcut])
        label = tip or text
        if shortcut:
            first = shortcut[0] if isinstance(shortcut, list) else shortcut
            label += f" ({QKeySequence(first).toString(QKeySequence.NativeText)})"
        action.setToolTip(label)
        if icon_name:
            self._icon_actions.append((action, icon_name))
        self.addAction(action)  # Tastenkürzel im ganzen Fenster
        return action

    def _build_toolbar(self):
        """Werkzeugleiste: links Tag wählen, in der Mitte die Werkzeuge, rechts Einstellungen.

        Tag und Einstellungen stehen außerhalb des Überlaufs (»), sie verschwinden also
        nie. Wird das Fenster schmal, zeigen zuerst "Ganzer Tag" und "Arbeitszeit" nur
        noch ihr Symbol, danach rutschen Werkzeuge in den Überlauf. Jeder Knopf hat einen
        Hinweis beim Darüberfahren.
        """
        outer = QToolBar("Navigation", self)
        outer.setObjectName("main_toolbar")
        outer.setMovable(False)
        outer.setFloatable(False)
        self.addToolBar(Qt.TopToolBarArea, outer)
        header = QWidget(outer)
        header.setStyleSheet("background: transparent;")
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        outer.addWidget(header)

        # ---- links: Tag wählen (immer sichtbar)
        days = QToolBar("Tag", header)
        days.setObjectName("fixed")
        days.setIconSize(QSize(18, 18))
        days.setToolButtonStyle(Qt.ToolButtonIconOnly)
        prev_day = self._action("Vorheriger Tag", self.show_previous_day, "Ctrl+Left", icon_name="prev")
        next_day = self._action("Nächster Tag", self.show_next_day, "Ctrl+Right", icon_name="next")
        days.addAction(prev_day)
        self.date_edit = QDateEdit(self.current_date, self)
        self.date_edit.setAccessibleName("Datum")
        self.date_edit.setToolTip("Tag wählen")
        self.date_edit.setLocale(GERMAN)
        self.date_edit.setDisplayFormat("ddd dd.MM.yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.dateChanged.connect(self.date_changed)
        days.addWidget(self.date_edit)
        days.addAction(next_day)
        days.addAction(self._action("Heute", self.show_today, "Ctrl+T", "Heute zeigen", "today"))
        days.addSeparator()
        days.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        row.addWidget(days, 0)

        # ---- Mitte: Werkzeuge (dürfen im schmalen Fenster in den Überlauf)
        tb = QToolBar("Werkzeuge", header)
        tb.setObjectName("tools")
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.tools_bar = tb
        row.addWidget(tb, 1)

        self.refresh_action = self._action("Aktualisieren", self.refresh, "F5", "Logs neu einlesen",
                                           "refresh")
        tb.addAction(self.refresh_action)
        tb.addSeparator()
        # Tagesliste: Ansicht (Auge), PC-Verlauf, KI-Vorschläge (Stern)
        self.view_button = QToolButton(tb)
        self.view_button.setAccessibleName("Ansicht der Tagesliste")
        self.view_button.setPopupMode(QToolButton.InstantPopup)
        view_menu = QMenu(self.view_button)
        group = QActionGroup(view_menu)
        self.view_actions = {}
        for key, text in self.VIEWS:
            if key == "doc":  # Trennlinie: Einträge aus den Logs | eingeordnete Tätigkeiten
                view_menu.addSeparator()
            action = view_menu.addAction(text)
            action.setCheckable(True)
            action.setActionGroup(group)
            action.triggered.connect(lambda _c=False, k=key: self.change_view(k))
            self.view_actions[key] = action
        self.view_button.setMenu(view_menu)
        tb.addWidget(self.view_button)
        self._view_icon = True
        self.update_view_button()

        self.pc_list_action = QAction("PC-Verlauf", self)
        self.pc_list_action.setCheckable(True)
        self.pc_list_action.setChecked(self.config.get("show_pc_in_list", False))
        self.pc_list_action.toggled.connect(self.toggle_pc_list)
        self._icon_actions.append((self.pc_list_action, "monitor"))
        tb.addAction(self.pc_list_action)
        self.update_pc_list_tip()

        self.ai_button_action = self._action(
            "KI-Vorschläge", lambda: self.classify_day(), "F6",
            "KI-Vorschläge: Tätigkeiten des Tages von Claude einordnen lassen", "spark")
        tb.addAction(self.ai_button_action)
        self.doc_button_action = self._action(
            "Nachtragen", lambda: self.add_doc(), "F7",
            "Tätigkeit nachtragen (zur markierten Zeile oder zur letzten halben Stunde)", "edit")
        tb.addAction(self.doc_button_action)
        tb.addSeparator()
        # Ausschnitt der Timeline
        tb.addAction(self._action("Verkleinern", self.zoom_out, "Ctrl+-", "Timeline verkleinern",
                                  "zoom_out"))
        tb.addAction(self._action("Vergrößern", self.zoom_in, ["Ctrl++", "Ctrl+="],
                                  "Timeline vergrößern", "zoom_in"))
        whole_day = self._action("Ganzer Tag", self.timeline_whole_day, "Ctrl+0",
                                 "Ganzen Tag zeigen (oder Doppelklick in die Timeline)", "whole_day")
        work_time = self._action("Arbeitszeit", self.timeline_work_time, "Ctrl+9",
                                 "Arbeitszeit des Tages zeigen", "work_time")
        tb.addAction(whole_day)
        tb.addAction(work_time)
        # Mit Text, solange Platz ist; im schmalen Fenster nur das Symbol
        self._adaptive_buttons = [tb.widgetForAction(whole_day), tb.widgetForAction(work_time)]

        # ---- rechts: Einstellungen (immer sichtbar)
        right = QToolBar("Einstellungen", header)
        right.setObjectName("fixed")
        right.setIconSize(QSize(18, 18))
        right.addWidget(self._build_settings_button())
        right.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        row.addWidget(right, 0)

        for bar in (days, tb, right):
            # Screenreader lesen sonst nur das Symbol vor
            for action in bar.actions():
                button = bar.widgetForAction(action)
                if isinstance(button, QToolButton) and not button.accessibleName():
                    button.setAccessibleName(action.toolTip().split(" (")[0] or action.text())
        # Überlauf-Knopf, wenn das Fenster schmal ist (z. B. bei 200 % Anzeige)
        ext = tb.findChild(QToolButton, "qt_toolbar_ext_button")
        if ext:
            ext.setAccessibleName("Weitere Befehle")
            ext.setToolTip("Weitere Befehle")
            ext.setText("»")
            ext.setToolButtonStyle(Qt.ToolButtonTextOnly)

    def fit_toolbar(self):
        """Text bei "Ganzer Tag"/"Arbeitszeit" nur zeigen, wenn alle Werkzeuge Platz haben."""
        tb = getattr(self, "tools_bar", None)
        if tb is None:
            return
        for button in self._adaptive_buttons:
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        if tb.sizeHint().width() > tb.width():
            for button in self._adaptive_buttons:
                button.setToolButtonStyle(Qt.ToolButtonIconOnly)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.fit_toolbar)  # erst wenn die Leiste ihre neue Breite hat

    def update_view_button(self):
        """Hinweis am Auge: aktuelle Ansicht und was die Ansichten zeigen."""
        key = self.config.get("list_view", "grouped")
        if key not in self.view_actions:
            key = "grouped"
        self.view_actions[key].setChecked(True)
        current = dict(self.VIEWS)[key]
        self.view_button.setToolTip(
            f"Ansicht der Tagesliste: {current}\n\n"
            "Zusammengefasst: Verbindungen und Passwort-/OTP-Anzeigen je Eintrag eine Zeile\n"
            "Einzeln: jede Zeile aus den Logs\n"
            "Arbeitsblöcke: alles mit kurzer Pause dazwischen als ein Block, z. B. fürs Ticket\n"
            "Dokumentation: deine eingetragenen Tätigkeiten und was noch offen ist (F7)\n"
            "Regeln (ohne KI): Tätigkeiten, die Zeitzeuge über deine Regeln erkannt hat\n"
            "KI-Vorschläge: Tätigkeiten, die Claude aus dem Tag erkannt hat")
        self.view_button.setAccessibleDescription(f"Aktuell: {current}")

    def update_pc_list_tip(self):
        on = self.pc_list_action.isChecked()
        self.pc_list_action.setToolTip(
            "PC-Verlauf: aktive Fenster in der Tagesliste " + ("zeigen (an)" if on else "zeigen (aus)"))

    def _build_settings_button(self):
        """Knopf "Einstellungen" mit dem Menü. Steht links in der Werkzeugleiste, damit er
        auch im schmalen Fenster nie im Überlauf (») verschwindet."""
        # Menü nach Aufgaben: Ansicht | Aufzeichnung | Einstellen | Info.
        # Seltenes (Datenquellen, Speicherort) steckt in Untermenüs.
        menu = QMenu(self)
        self.dark_action = menu.addAction("&Dunkles Design")
        self.dark_action.setCheckable(True)
        self.dark_action.setChecked(self.dark_mode)
        self.dark_action.toggled.connect(self.toggle_dark_mode)
        menu.addSeparator()
        self.tracking_action = menu.addAction("Aktive &Fenster aufzeichnen")
        self.tracking_action.setCheckable(True)
        self.tracking_action.setChecked(self.config.get("tracking_enabled", True))
        self.tracking_action.toggled.connect(self.toggle_tracking)
        self._icon_actions += [
            (menu.addAction("Fenster-F&ilter …", self.edit_tracking_filters), "filter"),
            (menu.addAction("&Regeln (ohne KI) …", self.edit_rules), "rules"),
        ]
        menu.addSeparator()
        self._icon_actions += [
            (menu.addAction("&Arbeitszeiten …", self.edit_work_hours), "clock"),
            (menu.addAction("Aktivitäts&typen und Farben …", self.edit_activity_types), "palette"),
            (menu.addAction("&KI-Vorschläge …", self.edit_ai_settings), "spark"),
        ]
        menu.addSeparator()
        self._icon_actions.append(
            (menu.addAction("&Nachfragen und Erinnerungen …", self.edit_prompt_settings), "bell"))
        rows_menu = menu.addMenu("&Zeilen der Timeline")
        self.row_actions = {}
        for key, text in [("doc", "&Doku (eigene Tätigkeiten)"), ("rule", "&Regeln (ohne KI)"),
                          ("ai", "&KI-Vorschläge")]:
            action = rows_menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(self.config.get("timeline_rows", {}).get(key, True))
            action.toggled.connect(lambda on, k=key: self.toggle_row(k, on))
            self.row_actions[key] = action
        self._icon_actions.append((rows_menu.menuAction(), "rows"))
        menu.addSeparator()
        self.sources_menu = self._build_sources_menu(menu)
        storage_menu = menu.addMenu("Daten&speicher")
        self.open_folder_action = storage_menu.addAction(
            "&Datenordner öffnen", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(DATA_DIR)))
        storage_menu.addAction("&Speicherort ändern …", self.change_data_dir)
        self._icon_actions += [(self.sources_menu.menuAction(), "plug"),
                               (storage_menu.menuAction(), "folder"),
                               (self.open_folder_action, "folder")]
        menu.addSeparator()
        self._icon_actions += [
            (menu.addAction("Ü&ber Zeitzeuge", self.show_about), "info"),
            (menu.addAction("Zeitzeuge be&enden", self.request_quit), "power"),
        ]
        self.menu_button = QToolButton(self)
        self.menu_button.setText("&Einstellungen")
        self.menu_button.setToolTip("Einstellungen, Datenquellen und mehr (Alt+E)")
        self.menu_button.setAccessibleName("Einstellungen")
        self.menu_button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.menu_button.setMenu(menu)
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        return self.menu_button

    # Datenquellen: Schlüssel in der Config, Text im Menü (Gruppen mit Trennlinie)
    SOURCES = [
        [("teamviewer_enabled", "&TeamViewer"), ("rdm_enabled", "&RDM (Remote Desktop Manager)")],
        [("sophos_enabled", "&Sophos Connect"), ("forti_enabled", "&FortiClient"),
         ("vpn_enabled", "&Weitere VPN-Logs (OpenVPN …)")],
        [("pbx_reader_enabled", "&3CX-Anrufe"), ("itm_reader_enabled", "&ITM-Personalzeiten")],
    ]

    def _build_sources_menu(self, parent_menu):
        """Jede Datenquelle als Schalter, die Einrichtung (Pfade, Anmeldung) im Untermenü."""
        menu = parent_menu.addMenu("Daten&quellen")
        self.source_actions = {}
        for i, group in enumerate(self.SOURCES):
            if i:
                menu.addSeparator()
            for key, text in group:
                action = menu.addAction(text)
                action.setCheckable(True)
                action.setChecked(bool(self.config.get(key, key not in ("pbx_reader_enabled",
                                                                          "itm_reader_enabled"))))
                action.toggled.connect(lambda on, k=key: self.toggle_source(k, on))
                self.source_actions[key] = action
        menu.addSeparator()
        setup = menu.addMenu("&Einrichten")
        setup.addAction("Team&Viewer-Logs …", self.edit_teamviewer_settings)
        setup.addAction("&RDM-Logs …", self.edit_rdm_settings)
        setup.addAction("&VPN-Logs …", self.edit_vpn_settings)
        setup.addAction("&3CX …", self.open_pbx_settings)
        setup.addAction("&ITM-Personalzeiten …", self.open_itm_settings)
        return menu

    def sync_source_actions(self):
        """Schalter im Menü an die Einstellungen angleichen (z. B. nach einem Dialog)."""
        for key, action in self.source_actions.items():
            action.blockSignals(True)
            action.setChecked(bool(self.config.get(key, True)))
            action.blockSignals(False)

    def toggle_source(self, key, on):
        """Datenquelle ein- oder ausschalten (Menü "Datenquellen")."""
        if bool(self.config.get(key)) == on and key in self.config:
            return
        self.config[key] = on
        save_config(self.config)
        if key == "pbx_reader_enabled":
            self.start_pbx_reader() if on else self.stop_pbx_reader()
        elif key == "itm_reader_enabled":
            self.start_itm_reader() if on else self.stop_itm_reader()
        elif key in ("sophos_enabled", "forti_enabled"):
            self.timeline.vpn_reader.sources = vpn_sources(self.config)
            self.apply_vpn_monitor()
        self.timeline.refresh()  # neu einlesen und zeichnen

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
        date_str = self.current_date.toString("yyyy-MM-dd")
        if self.config.get("list_view") == "ai":
            entries = self.ai_store.entries(date_str)
        elif self.config.get("list_view") == "doc":
            entries = self.doc_band(date_str)
        elif self.config.get("list_view") == "rules":
            entries = self.rule_band(date_str)
        elif self.config.get("list_view") == "blocks":
            entries = work_blocks(entries, self.config.get("block_gap_minutes", 10))
        elif self.config.get("show_pc_in_list", False):
            entries += self.pc_activities
        entries.sort(key=lambda a: a["start"])
        self.list_entries = entries

        # Spaltenbreiten beim Befüllen einfrieren: Mit "an Inhalt anpassen" misst Qt sonst nach
        # jeder Zelle alle Zeilen neu (bei vollem PC-Verlauf über 20 s, Fenster hängt)
        header = self.table.horizontalHeader()
        self.table.setUpdatesEnabled(False)
        for col in range(4):
            header.setSectionResizeMode(col, QHeaderView.Fixed)
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
        for col in range(4):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)  # einmal messen
        self.table.setUpdatesEnabled(True)
        self.update_status_text()

    VIEWS = [("grouped", "Zusammengefasst"), ("single", "Einzeln"), ("blocks", "Arbeitsblöcke"),
             ("doc", "Dokumentation"), ("rules", "Regeln (ohne KI)"), ("ai", "KI-Vorschläge")]

    def change_view(self, key):
        self.config["list_view"] = key
        save_config(self.config)
        self.update_view_button()
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
            entry = self.list_entries[row] if row < len(self.list_entries) else {}
            if entry.get("doc"):
                lines.append(ticket_line(entry["doc_item"]))  # fertige Ticketzeile
                continue
            if entry.get("open"):
                lines.append(f"OFFEN: {describe(entry['source_entry'])}")
                continue
            if entry.get("ai") or entry.get("rule"):
                lines.append(ai_copy_text(entry))
                continue
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
        elif self.timeline.loading:
            parts.append("Logs werden gelesen …")
        else:
            parts.append("keine Einträge")
            missing = self.timeline.missing_sources()
            if missing:
                parts.append(f"keine Logdatei gefunden: {', '.join(missing)} "
                             "(Pfade unter Einstellungen → Datenquellen → Einrichten)")
        if self.pc_activities:
            parts.append(f"am PC aktiv {format_duration(merged_seconds(self.pc_activities))}")
        doc = self.doc_band(self.current_date.toString("yyyy-MM-dd"))
        done = [e for e in doc if e.get("doc")]
        open_count = len(doc) - len(done)
        if done or open_count:
            text = f"dokumentiert {format_duration(merged_seconds(done))}" if done else "nichts dokumentiert"
            if open_count:
                text += f", {open_count} offen (F7)"
            parts.append(text)
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
        # Vergangene Tage auf Wunsch automatisch einordnen (nur ohne vorhandene Vorschläge)
        if (self.config.get("ai_auto") and date < QDate.currentDate()
                and not self.ai_store.load(date.toString("yyyy-MM-dd"))):
            self.classify_day(quiet=True)

    def show_previous_day(self):
        self.date_edit.setDate(self.current_date.addDays(-1))

    def show_next_day(self):
        self.date_edit.setDate(self.current_date.addDays(1))

    def show_today(self):
        self.date_edit.setDate(QDate.currentDate())

    def refresh(self):
        self.timeline.refresh()
        self.statusBar().showMessage("Logs werden neu eingelesen …", 2000)

    def auto_refresh(self):
        try:
            if vpn_sources(self.config):
                self.timeline.vpn_reader.update_from_logs()  # Sophos-Logs sichern, bevor sie überschrieben werden
        except Exception as e:
            print(f"Fehler beim Lesen der VPN-Logs: {e}")
        if self.current_date == QDate.currentDate():
            self.timeline.refresh()

    def apply_vpn_monitor(self):
        """Eigene VPN-Aufzeichnung nur, wenn Sophos Connect oder FortiClient eingeschaltet ist."""
        if vpn_sources(self.config) and self.config.get("vpn_monitor_enabled", True):
            if not self.vpn_timer.isActive():
                self.vpn_timer.start(30 * 1000)
                QTimer.singleShot(0, self.vpn_sample)
        else:
            self.vpn_timer.stop()

    def vpn_sample(self):
        if self.timeline.vpn_reader.sample() and self.current_date == QDate.currentDate() and self.isVisible():
            self.timeline.refresh()

    # ---------------------- KI-Vorschläge -------------------------------------

    def ai_input(self, date):
        """Einträge des Tages für die KI: zusammengefasst, damit es kurz bleibt."""
        entries = group_entries(self.timeline.activities_for(date),
                                self.config.get("merge_gap_minutes", 5))
        return entries, self.timeline.pc_entries_for(date, min_seconds=60)

    def classify_day(self, quiet=False):
        date = self.current_date
        date_str = date.toString("yyyy-MM-dd")
        if date_str in self.ai.running:
            self.statusBar().showMessage("KI-Vorschläge werden schon erstellt …", 3000)
            return
        entries, pc = self.ai_input(date)
        if not quiet and self.ai_store.is_current(date_str, self.ai.input_hash(self.ai.input_text(entries, pc))):
            answer = QMessageBox.question(
                self, "KI-Vorschläge",
                "Für diesen Tag gibt es schon Vorschläge, und die Einträge haben sich nicht geändert.\n"
                "Trotzdem neu erstellen? Das kostet einen weiteren Aufruf.")
            if answer != QMessageBox.Yes:
                return
            started = self.ai.start(date_str, entries, pc, force=True)
        else:
            started = self.ai.start(date_str, entries, pc)
        if started:
            self.ai_button_action.setEnabled(False)
            self.statusBar().showMessage(
                f"Claude ordnet {GERMAN.toString(date, 'dd.MM.')} ein …", 60000)

    def on_ai_finished(self, date_str, count, cost):
        self.ai_button_action.setEnabled(True)
        cost_text = f"{cost:.3f}".replace(".", ",")
        self.statusBar().showMessage(
            f"KI: {count} Vorschläge für {date_str[8:10]}.{date_str[5:7]}., "
            f"Kosten ca. {cost_text} $", 8000)
        if date_str == self.current_date.toString("yyyy-MM-dd"):
            self.timeline.draw_timeline(self.current_date)

    def on_ai_failed(self, date_str, message):
        self.ai_button_action.setEnabled(True)
        self.statusBar().showMessage(f"KI-Vorschläge: {message}", 10000)
        if not self.isVisible() or self.config.get("ai_auto"):
            return
        QMessageBox.warning(self, "KI-Vorschläge", message)

    def on_ai_action(self, entry, action):
        status = "übernommen" if action == "übernehmen" else "verworfen"
        self.ai_store.set_status(entry["start"][:10], entry["ai_id"], status)
        if status == "übernommen":  # übernommen = dokumentiert, steht dann in der Zeile "Doku"
            try:
                self.journal.add({"start": entry["start"], "end": entry["end"],
                                  "customer": entry.get("customer_name", ""),
                                  "category": entry.get("category", ""),
                                  "text": entry.get("description", ""), "source": "KI"})
            except (OSError, ValueError) as e:
                self.statusBar().showMessage(str(e), 8000)
        self.timeline.draw_timeline(self.current_date)

    def ai_action_on_row(self, action):
        row = self.table.currentRow()
        if not 0 <= row < len(self.list_entries) or not self.list_entries[row].get("ai"):
            self.statusBar().showMessage("Die markierte Zeile ist kein KI-Vorschlag "
                                         "(Ansicht „KI-Vorschläge“ wählen)", 4000)
            return
        self.on_ai_action(self.list_entries[row], action)

    def ai_spent(self):
        """Summe der bisherigen Kosten aus allen gespeicherten Tagen."""
        total = 0.0
        try:
            names = os.listdir(AI_DIR)
        except OSError:
            return total
        for name in names:
            if name.endswith(".json"):
                data = self.ai_store.load(name[:-5]) or {}
                total += data.get("cost_usd", 0) + data.get("earlier_cost_usd", 0)
        return total

    def edit_ai_settings(self):
        dialog = AiSettingsDialog(self.config, self.ai_spent(), self)
        if dialog.exec_() == dialog.Accepted:
            dialog.apply()
            save_config(self.config)

    # ---------------------- Dokumentation: eigene Tätigkeiten -----------------

    def categories(self):
        return self.ai.categories()

    def known_customers(self):
        """Kunden zur Auswahl: zuletzt dokumentierte, benannte TeamViewer-IDs."""
        names = self.journal.customers()
        names += sorted(set(self.config.get("teamviewer_names", {}).values()) - set(names))
        return names

    def rule_band(self, date_str):
        """Blöcke aus den Regeln (ohne KI), zwischengespeichert bis sich etwas ändert."""
        date = QDate.fromString(date_str, "yyyy-MM-dd")
        entries = self.timeline.activities_for(date)
        pc = self.timeline.pc_entries_for(date, min_seconds=30)
        rule_list = self.config.get("rules") or []
        key = (len(entries), entries[-1]["end"] if entries else "", len(pc),
               pc[-1]["end"] if pc else "", json.dumps(rule_list, sort_keys=True),
               self.config.get("rules_gap_minutes", 5), self.config.get("rules_min_minutes", 2))
        cached = self._rule_cache.get(date_str)
        if cached and cached[0] == key:
            return cached[1]
        blocks = rules.classify(entries, pc, rule_list,
                                gap_minutes=self.config.get("rules_gap_minutes", 5),
                                min_minutes=self.config.get("rules_min_minutes", 2))
        self._rule_cache[date_str] = (key, blocks)
        return blocks

    def doc_candidates(self, date_str):
        """Erkannte Tätigkeiten des Tages, die noch nicht dokumentiert sind."""
        sources = self.config.get("prompt_sources", ["connections", "calls"])
        date = QDate.fromString(date_str, "yyyy-MM-dd")
        entries = []
        if "connections" in sources or "calls" in sources:
            grouped = group_entries(self.timeline.activities_for(date),
                                    self.config.get("merge_gap_minutes", 5))
            for e in grouped:
                is_call = row_kind(e) == "call"
                if is_call and "calls" in sources:
                    entries.append(e)
                elif not is_call and "connections" in sources and e.get("type") != "Zugangsdaten":
                    entries.append(e)
        if "rules" in sources:
            entries += self.rule_band(date_str)
        return self.journal.open_items(entries, date_str,
                                       min_minutes=self.config.get("prompt_min_minutes", 5))

    def doc_band(self, date_str):
        """Zeile "Doku": eigene Tätigkeiten und (gestrichelt) was noch offen ist."""
        entries = self.journal.entries(date_str)
        entries += [open_entry(e) for e in self.doc_candidates(date_str)]
        return sorted(entries, key=lambda e: e["start"])

    def on_doc_request(self, action, entry):
        """Aus der Timeline: eintragen, bearbeiten, löschen, nicht dokumentieren."""
        if action == "add":
            self.add_doc(entry)
        elif action == "add_at":
            self.add_doc(minute=entry["minute"])
        elif action == "edit":
            self.edit_doc(entry["doc_item"])
        elif action == "delete":
            self.delete_doc(entry["doc_item"])
        elif action == "ignore":
            self.journal.ignore(entry)
            self.timeline.draw_timeline(self.current_date)

    def add_doc(self, entry=None, minute=None):
        """Tätigkeit nachtragen, auf Wunsch vorbelegt aus einem erkannten Eintrag."""
        if entry is None and minute is None and self.table.hasFocus():
            row = self.table.currentRow()
            if 0 <= row < len(self.list_entries):
                return self.doc_for_row()
        categories = self.categories()
        if entry:
            start, end = parse_time(entry["start"]), parse_time(entry["end"])
            info = f"Erkannt: {describe(entry)}"
            customer = suggest_customer(entry, self.config.get("teamviewer_names", {}))
            category = suggest_category(entry, categories)
            text = entry.get("description", "") if entry.get("ai") or entry.get("rule") else ""
        else:
            start, end = default_span(self.current_date.toPyDate(), minute)
            info, customer, category, text = "", "", "", ""
        dialog = EntryDialog(start, end, self.known_customers(), categories, customer, category,
                             text, tv_id=(entry or {}).get("tv_id"), info=info, parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        item = dialog.item()
        if entry:
            item["source"] = entry.get("type", "")
        self._save_doc(item, entry, dialog.remember_tv())

    def _save_doc(self, item, entry=None, remember_tv=False, old=None):
        try:
            if old:
                self.journal.update(old, item)
            else:
                self.journal.add(item)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Tätigkeit", str(e))
            return False
        tv_id = (entry or {}).get("tv_id")
        if tv_id and remember_tv and item.get("customer"):
            self.config.setdefault("teamviewer_names", {})[tv_id] = item["customer"]
            save_config(self.config)
        self.timeline.draw_timeline(self.current_date)
        self.statusBar().showMessage("Tätigkeit gespeichert", 3000)
        return True

    def edit_doc(self, item):
        start, end = parse_time(item["start"]), parse_time(item["end"])
        dialog = EntryDialog(start, end, self.known_customers(), self.categories(),
                             item.get("customer", ""), item.get("category", ""),
                             item.get("text", ""), title="Tätigkeit bearbeiten",
                             can_delete=True, parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        if dialog.deleted:
            self.delete_doc(item, ask=False)
        else:
            self._save_doc(dialog.item(), old=item)

    def delete_doc(self, item, ask=True):
        if ask and QMessageBox.question(
                self, "Tätigkeit löschen",
                f"Diese Tätigkeit löschen?\n\n{ticket_line(item)}") != QMessageBox.Yes:
            return
        try:
            self.journal.delete(item)
        except OSError as e:
            QMessageBox.warning(self, "Tätigkeit löschen", str(e))
            return
        self.timeline.draw_timeline(self.current_date)

    def doc_for_row(self):
        """Tagesliste: Tätigkeit zur markierten Zeile eintragen oder bearbeiten."""
        row = self.table.currentRow()
        if not 0 <= row < len(self.list_entries):
            return None
        entry = self.list_entries[row]
        if entry.get("doc"):
            self.edit_doc(entry["doc_item"])
        else:
            self.add_doc(entry.get("source_entry", entry))

    def delete_doc_row(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.list_entries) and self.list_entries[row].get("doc"):
            self.delete_doc(self.list_entries[row]["doc_item"])
        else:
            self.statusBar().showMessage("Die markierte Zeile ist keine eingetragene Tätigkeit", 4000)

    def show_open_docs(self):
        """Fenster zeigen, heute, Ansicht "Dokumentation"."""
        self.show_from_tray()
        self.show_today()
        self.change_view("doc")

    def toggle_row(self, key, on):
        self.config.setdefault("timeline_rows", {})[key] = on
        save_config(self.config)
        self.timeline.draw_timeline(self.current_date)

    def edit_prompt_settings(self):
        dialog = DocPromptDialog(self.config, self)
        if dialog.exec_() == QDialog.Accepted:
            dialog.apply()
            save_config(self.config)
            self.timeline.draw_timeline(self.current_date)

    # ---- Nachfragen ("Was hast du gemacht?")

    def check_prompts(self):
        """Jede Minute: neu erkannte, noch nicht dokumentierte Tätigkeiten nachfragen."""
        mode = self.config.get("prompt_mode", "window")
        if mode == "off" or self._quitting:
            return
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        open_items = self.doc_candidates(today)
        for e in open_items:
            key = journal_key(e)
            # Nur frisch beendete fragen (seit dem Start von Zeitzeuge oder in der letzten
            # Stunde). Ältere stehen gestrichelt in der Zeile "Doku" und in der Liste.
            ended = parse_time(e["end"])
            if ended < min(self._started_at, now) - timedelta(hours=1):
                continue
            if key in self._prompt_asked and self._prompt_asked[key] > now:
                continue
            if key not in (journal_key(q) for q in self._prompt_queue):
                self._prompt_queue.append(e)
        keys = {journal_key(e) for e in open_items}  # inzwischen dokumentiert: nicht mehr fragen
        self._prompt_queue = [q for q in self._prompt_queue if journal_key(q) in keys]
        if self._prompt_queue:
            self.show_next_prompt()
        self.end_of_day_reminder(open_items, now)

    def show_next_prompt(self, force=False):
        if self._prompt_window or not self._prompt_queue:
            if self._prompt_window:
                self._prompt_window.set_pending(len(self._prompt_queue) - 1)
            return
        entry = self._prompt_queue[0]
        if self.config.get("prompt_mode") == "tray" and not force:
            if self.tray and journal_key(entry) not in self._prompt_asked:
                self._prompt_asked[journal_key(entry)] = datetime.max
                self._tray_doc_hint = True
                self.tray.showMessage("Was hast du gemacht?",
                                      f"{describe(entry)}\nKlick hier, um es einzutragen.",
                                      QSystemTrayIcon.Information, 10000)
            return
        window = PromptWindow(entry, self.known_customers(), self.categories(),
                              self.config.get("teamviewer_names", {}),
                              pending=len(self._prompt_queue) - 1, parent=self)
        window.answered.connect(self.on_prompt_answered)
        self._prompt_window = window
        # unten rechts über dem Infobereich, ohne dir den Fokus wegzunehmen
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            window.adjustSize()
            window.move(area.right() - window.width() - 24, area.bottom() - window.height() - 24)
        window.show()

    def on_prompt_answered(self, action, entry, item):
        window, self._prompt_window = self._prompt_window, None
        key = journal_key(entry)
        self._prompt_queue = [q for q in self._prompt_queue if journal_key(q) != key]
        if action == "save":
            item["source"] = entry.get("type", "")
            if not self._save_doc(item, entry, window.remember_tv() if window else False):
                self._prompt_queue.insert(0, entry)
        elif action == "ignore":
            self.journal.ignore(entry)
            self.timeline.draw_timeline(self.current_date)
        else:  # später
            snooze = self.config.get("prompt_snooze_minutes", 15)
            self._prompt_asked[key] = datetime.now() + timedelta(minutes=snooze)
        if window:
            window.deleteLater()
        QTimer.singleShot(400, self.show_next_prompt)

    def end_of_day_reminder(self, open_items, now):
        """Nach Feierabend einmal am Tag an offene Tätigkeiten erinnern."""
        if not (self.config.get("prompt_end_of_day", True) and open_items and self.tray):
            return
        today = now.strftime("%Y-%m-%d")
        if self._reminded_day == today:
            return
        _start, end = self.timeline._work_minutes(QDate.currentDate())
        if end <= _start or now.hour * 60 + now.minute < end:
            return
        self._reminded_day = today
        self._tray_doc_hint = True
        self.tray.showMessage(
            "Feierabend: noch nicht alles dokumentiert",
            f"Heute sind noch {len(open_items)} Tätigkeiten offen. Klick hier zum Nachtragen.",
            QSystemTrayIcon.Warning, 15000)

    def request_quit(self):
        """Beenden über Menü/Infobereich: vorher an offene Tätigkeiten von heute erinnern."""
        if self.config.get("prompt_on_quit", True) and self.config.get("prompt_mode") != "off":
            open_items = self.doc_candidates(datetime.now().strftime("%Y-%m-%d"))
            if open_items and self.ask_document_first(len(open_items)):
                self.show_open_docs()
                return
        self.quit_app()

    def ask_document_first(self, count):
        """Rückfrage beim Beenden. True = erst nachtragen, nicht beenden."""
        box = QMessageBox(QMessageBox.Question, "Zeitzeuge beenden",
                          f"Heute sind noch {count} Tätigkeiten nicht dokumentiert. "
                          "Jetzt nachtragen?", parent=self)
        later = box.addButton("&Nachtragen", QMessageBox.AcceptRole)
        box.addButton("Trotzdem &beenden", QMessageBox.DestructiveRole)
        box.setDefaultButton(later)
        box.exec_()
        return box.clickedButton() is later

    # ---------------------- Aktivitätsprotokoll -------------------------------

    def set_tracking(self, enabled):
        if enabled and not self.tracker:
            self.tracker = ActivityTracker(
                ACTIVITY_DIR,
                idle_limit=self.config.get("tracking_idle_minutes", 5) * 60,
                **tracking_filters(self.config),
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

    def edit_tracking_filters(self):
        dialog = TrackingFilterDialog(self.config, ACTIVITY_DIR, self)
        if dialog.exec_() == dialog.Accepted:
            dialog.apply()
            save_config(self.config)
            if self.tracker:  # neue Regeln gelten sofort
                self.tracker.set_filters(**tracking_filters(self.config))
            self.timeline.draw_timeline(self.current_date)

    def edit_rules(self):
        dialog = RulesDialog(self.config, self)
        if dialog.exec_() == dialog.Accepted:
            dialog.apply()
            save_config(self.config)
            self.timeline.draw_timeline(self.current_date)

    def toggle_tracking(self, enabled):
        self.config["tracking_enabled"] = enabled
        save_config(self.config)
        self.set_tracking(enabled)
        self.update_tracking_state()
        self.timeline.draw_timeline(self.current_date)

    def update_tracking_state(self):
        """Zustand der Aufzeichnung überall gleich zeigen: Statuszeile, Infobereich, Menüs."""
        on = self.tracker is not None
        text = "Aufzeichnung aktiv" if on else "Aufzeichnung pausiert"
        self.tracking_button.setText(text)
        self.tracking_button.setIcon(icons.state_dot(on))
        self.tracking_button.setToolTip(
            "Aktive Fenster werden aufgezeichnet. Klicken zum Pausieren." if on
            else "Die Aufzeichnung der aktiven Fenster ist pausiert. Klicken zum Fortsetzen.")
        if self.tray:
            self.tray.setIcon(icons.tray_icon(self.logo_svg, on) if self.logo_svg
                              else self.windowIcon())
            self.tray.setToolTip(f"Zeitzeuge – {text}")
            self.tray_state_action.setText(text)
            self.tray_state_action.setIcon(icons.state_dot(on))
            self.tray_toggle_action.setText("Aufzeichnung &pausieren" if on
                                            else "Aufzeichnung &fortsetzen")
            color = THEMES["dark" if self.dark_mode else "light"]["text"]
            self.tray_toggle_action.setIcon(icons.icon("pause" if on else "record", color))

    def toggle_pc_list(self, enabled):
        self.config["show_pc_in_list"] = enabled
        save_config(self.config)
        self.update_pc_list_tip()
        self.update_day_list(self.day_activities, self.pc_activities)

    # ---------------------- 3CX direkt auslesen -------------------------------

    def start_pbx_reader(self):
        if self.pbx_reader:
            return
        from pbx_reader import PbxReader  # Edge-Steuerung nur laden, wenn sie gebraucht wird
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
        self.pbx_reader.check_done.connect(self.on_pbx_check_done)
        self._watch_reader(self.pbx_reader)
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
        from pbx_reader import find_browser
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
            self.sync_source_actions()
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
        if kind == "pbx":
            def check():
                enabled.setChecked(True)
                reader = apply()
                if reader:
                    follow_status()
                    path = os.path.join(DATA_DIR, f"3cx_pruefung_{datetime.now():%Y-%m-%d_%H%M}.json")
                    reader.check_direct(path)
            check_btn = QPushButton("Direkt-Abfrage &prüfen")
            check_btn.setToolTip("Anrufe ohne Webseite direkt vom 3CX-Server holen und mit "
                                 "der gespeicherten Anrufliste vergleichen")
            check_btn.clicked.connect(check)
            buttons.addButton(check_btn, QDialogButtonBox.ActionRole)
        buttons.accepted.connect(lambda: (apply(), dialog.accept()))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog

    def on_pbx_check_done(self, path, text):
        if not path:
            QMessageBox.warning(self, "3CX-Direkt-Abfrage", text)
            return
        box = QMessageBox(QMessageBox.Information, "3CX-Direkt-Abfrage",
                          f"{text}\n\nBericht: {path}\n\nNamen und Nummern sind maskiert.",
                          parent=self)
        open_btn = box.addButton("Ordner öffnen", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec_()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

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
        from itm_reader import ItmReader
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
        self._watch_reader(self.itm_reader)
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
        # --neustart: die neue Instanz wartet, bis diese hier beendet ist (nur eine Instanz)
        if hasattr(sys, "_MEIPASS"):
            QProcess.startDetached(sys.executable, ["--neustart"])
        else:
            QProcess.startDetached(sys.executable, [os.path.abspath(__file__), "--neustart"])
        self.quit_app()

    # ---------------------- Infobereich (Tray) --------------------------------

    def _build_tray(self):
        self.tray = None
        try:
            with open(resource_path("zeitzeuge.svg"), encoding="utf-8") as f:
                self.logo_svg = f.read()
        except OSError:  # ältere Builds ohne SVG: einfach das Logo aus der .ico
            self.logo_svg = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        # Schnellzugriffe; Aufzeichnung, Datenquellen und Datenordner sind dieselben
        # Aktionen wie im Hauptfenster, ihr Zustand ist also überall gleich.
        menu = QMenu(self)
        open_action = menu.addAction("&Zeitzeuge öffnen", self.show_from_tray)
        bold = QFont(open_action.font())
        bold.setBold(True)
        open_action.setFont(bold)
        menu.setDefaultAction(open_action)
        menu.addSeparator()
        # Zustand als eigene Zeile, darunter der passende Befehl (Text wechselt mit dem Zustand)
        self.tray_state_action = menu.addAction("")
        self.tray_state_action.setEnabled(False)
        self.tray_toggle_action = menu.addAction("", self.tracking_action.toggle)
        refresh = menu.addAction("Logs &neu einlesen", self.refresh)
        menu.addSeparator()
        menu.addMenu(self.sources_menu)
        menu.addAction(self.open_folder_action)
        menu.addSeparator()
        quit_action = menu.addAction("&Beenden", self.request_quit)
        self._icon_actions += [(open_action, "window"), (refresh, "refresh"), (quit_action, "power")]
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
        if getattr(self, "_tray_doc_hint", False):  # Meldung zu offenen Tätigkeiten
            self._tray_doc_hint = False
            if self._prompt_queue and self.config.get("prompt_mode") == "tray":
                self.show_next_prompt(force=True)
            else:
                self.show_open_docs()
        elif self.pbx_reader and self.pbx_reader.needs_login:
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
        if self._prompt_window:
            self._prompt_window.blockSignals(True)
            self._prompt_window.close()
        self.timeline.shutdown()
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
        for action, name in self._icon_actions:
            action.setIcon(icons.icon(name, theme["text"]))
        self.menu_button.setIcon(icons.icon("menu", theme["text"]))
        self.view_button.setIcon(icons.icon("eye", theme["text"]))
        self.update_tracking_state()
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
            self.sync_source_actions()
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
            enabled_text="Diese VPN-Logs auslesen und anzeigen",
            folders=True,
            hint="Logdateien oder Ordner deiner VPN-Clients, z. B. OpenVPN GUI "
                 "(%USERPROFILE%\\OpenVPN\\log), OpenVPN Connect oder Sophos SSL VPN. "
                 "Bei einem Ordner zählen alle .log- und .txt-Dateien darin, "
                 "der Dateiname wird zum Verbindungsnamen. Sophos Connect und FortiClient "
                 "erkennt Zeitzeuge von selbst.",
        )
        self.apply_vpn_monitor()

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

    # ---------------------- Absicherung gegen Fehler und Aussetzer -------------

    WATCH_INTERVAL = 60 * 1000     # Wächter für die Hintergrund-Leser
    PROBLEM_INTERVAL = 15 * 1000   # Meldungen aus safe_io anzeigen
    TRAY_PROBLEM_GAP = 10 * 60     # Probleme höchstens so oft im Infobereich melden (Sekunden)

    def _init_robustness(self):
        """Wächter für die Leser, Anzeige von Problemen, Edge-Reste aufräumen."""
        self._last_tray_problem = 0
        self.watch_timer = QTimer(self)
        self.watch_timer.timeout.connect(self._watch_readers)
        self.watch_timer.start(self.WATCH_INTERVAL)
        self.problem_timer = QTimer(self)
        self.problem_timer.timeout.connect(self.show_problems)
        self.problem_timer.start(self.PROBLEM_INTERVAL)
        # Probleme beim Start (z. B. kaputte Config) gleich nach dem Anzeigen einmal sagen
        QTimer.singleShot(1500, lambda: self.show_problems(startup=True))
        threading.Thread(target=self._kill_orphans, daemon=True, name="Edge-Reste").start()

    def _watch_reader(self, reader):
        reader.trouble.connect(self.on_reader_trouble)

    def _watch_readers(self):
        """Tote Lese-Threads neu starten, hängende Durchläufe abbrechen."""
        for reader in (self.pbx_reader, self.itm_reader):
            if not reader or reader.stopped:
                continue
            try:
                reader.check_hung()
                if not reader.alive():
                    safe_io.log(f"{reader.NAME}: Lese-Thread war beendet, Wächter startet ihn neu")
                    reader.start()
            except Exception as e:
                safe_io.log(f"Wächter: {reader.NAME} nicht neu gestartet: {e!r}")

    def _kill_orphans(self):
        """Edge-Reste mit Zeitzeuge-Profilen nach einem Absturz beenden (nie dein normaler Edge).
        Für eingeschaltete Leser macht das der Leser selbst, bevor er Edge startet."""
        try:
            for key, profile in (("pbx_reader_enabled", PBX_PROFILE_DIR),
                                 ("itm_reader_enabled", ITM_PROFILE_DIR)):
                if self.config.get(key) or not os.path.isdir(profile):
                    continue
                from pbx_reader import kill_profile_processes
                count = kill_profile_processes(profile)
                if count:
                    safe_io.log(f"{count} übrig gebliebene Edge-Prozesse ({os.path.basename(profile)}) beendet")
        except Exception as e:
            safe_io.log(f"Edge-Reste nicht beendet: {e!r}")

    def on_reader_trouble(self, text):
        """Ein Leser hat mehrmals hintereinander nichts lesen können (einmal pro Störung)."""
        self.statusBar().showMessage(text, 30000)
        if self.tray:
            self.tray.showMessage("Zeitzeuge", text, QSystemTrayIcon.Warning, 8000)

    def show_problems(self, startup=False):
        """Gemerkte Probleme (kaputte Dateien, Fehler) in Statuszeile und Infobereich zeigen."""
        problems = safe_io.take_problems()
        if not problems:
            return
        text = problems[-1] if len(problems) == 1 else \
            f"{problems[-1]} (und {len(problems) - 1} weitere, siehe fehler.log)"
        self.statusBar().showMessage(text, 30000)
        now = time.time()
        if self.tray and (startup or (not self.isVisible()
                                      and now - self._last_tray_problem > self.TRAY_PROBLEM_GAP)):
            self._last_tray_problem = now
            self.tray.showMessage("Zeitzeuge", "\n".join(problems[-3:]), QSystemTrayIcon.Warning, 10000)


_last_error_report = [0.0]


def report_exception(exc_type, exc, tb, where=""):
    """Unbehandelte Ausnahme: Stacktrace in fehler.log, höchstens einmal pro Minute melden.
    Zeitzeuge läuft weiter."""
    try:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        safe_io.log(f"Unbehandelter Fehler{where}:\n{text.rstrip()}")
        if time.time() - _last_error_report[0] > 60:
            _last_error_report[0] = time.time()
            safe_io.report(f"Interner Fehler ({exc_type.__name__}: {str(exc)[:100]}). "
                           "Zeitzeuge läuft weiter, Details in fehler.log.")
    except Exception:
        pass  # Melden darf selbst nie abstürzen


def install_error_hooks():
    """Unbehandelte Ausnahmen abfangen. Ohne das beendet PyQt5 das Programm bei einem
    Fehler in einem Slot sofort, und Fehler in Threads gingen ungesehen verloren."""
    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return sys.__excepthook__(exc_type, exc, tb)
        report_exception(exc_type, exc, tb)

    def thread_hook(args):
        if issubclass(args.exc_type, SystemExit):
            return
        name = args.thread.name if args.thread else "?"
        report_exception(args.exc_type, args.exc_value, args.exc_traceback, f" im Thread {name}")

    sys.excepthook = hook
    threading.excepthook = thread_hook


_instance_lock = None


def acquire_single_instance(path=None, wait_ms=500):
    """Nur eine Instanz: zwei würden sich gegenseitig die Dateien überschreiben.
    Die Sperre liegt lokal (nicht im oft mit OneDrive synchronisierten Datenordner).
    False, wenn Zeitzeuge schon läuft."""
    global _instance_lock
    from PyQt5.QtCore import QLockFile
    path = path or os.path.join(storage.local_dir(), "zeitzeuge.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock = QLockFile(path)
    lock.setStaleLockTime(0)  # nur als verwaist werten, wenn der Prozess nicht mehr läuft
    if not lock.tryLock(wait_ms):
        return False
    _instance_lock = lock
    return True


if __name__ == "__main__":
    QLocale.setDefault(GERMAN)
    install_error_hooks()
    app = QApplication(sys.argv)
    app.setStyle(AppStyle())
    install_translator(app)
    app.setQuitOnLastWindowClosed(False)
    if not acquire_single_instance(wait_ms=20000 if "--neustart" in sys.argv else 500):
        if "--minimized" not in sys.argv:
            QMessageBox.information(None, "Zeitzeuge",
                                    "Zeitzeuge läuft schon. Du findest es im Infobereich neben der Uhr.")
        sys.exit(0)
    window = TimelineApp()
    from hang_watch import HangWatch
    hang_watch = HangWatch(os.path.join(DATA_DIR, "haenger.log"), app)
    if "--minimized" in sys.argv or window.config.get("start_minimized", False):
        if not window.tray:
            window.showMinimized()
    else:
        window.show()
    code = app.exec_()
    if not window._quitting:  # z. B. Windows-Abmeldung: laufenden Abschnitt trotzdem speichern
        window.quit_app()
    # Direkt beenden: PyQt räumt beim Interpreter-Ende sporadisch in falscher Reihenfolge auf
    # (Zugriffsfehler unter Windows). quit_app hat da schon alles gespeichert und gestoppt.
    sys.stdout and sys.stdout.flush()
    os._exit(code)
