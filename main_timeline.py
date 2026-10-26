"""Zeitzeuge: Startpunkt (python main_timeline.py, PyInstaller) und Hauptfenster TimelineApp.

TimelineApp setzt sich aus Mixins zusammen:
  app_menus    Werkzeugleiste, Menü Einstellungen, Design, Einstellungsdialoge
  app_daylist  Tagesliste, Statuszeile, Blättern zwischen den Tagen
  app_docs     KI-Vorschläge, eigene Tätigkeiten, Nachfragen
  app_readers  3CX/ITM im Hintergrund, Wächter, Fehleranzeige
  app_tray     Fensteraufzeichnung, Infobereich, Beenden
  app_transfer Export/Import für einen anderen PC (PAW)
  app_protect  Schutz der Daten: Schlüssel, Sicherung der Datenbank
Aussehen in theme.py, Standardwerte der Config in config_defaults.py.
"""
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
import traceback
import warnings

# Als Skript gestartet heißt dieses Modul "__main__". Die Mixins holen Pfade und
# save_config über "import main_timeline": ohne den Eintrag würde es ein zweites Mal geladen.
if __name__ == "__main__":
    sys.modules.setdefault("main_timeline", sys.modules[__name__])

from datetime import datetime

from PySide6.QtCore import QDate, QLocale, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHeaderView, QLabel,
                               QMainWindow, QMessageBox, QSplitter, QTableWidget, QToolButton,
                               QVBoxLayout, QWidget)

from ai_classifier import AI_TYPE, AiClassifier, AiStore
from busy_bar import BusyBar
from transfer import ImportStore
from retention_dialogs import RetentionRunner
import datastore
import safe_io
import storage
from vpn_reader import vpn_sources
from journal import Journal
from settings_dialogs import ActivityTypeSettingsDialog, ConnectionSettingsDialog, WorkHoursDialog
from timeline_only import ActivityViewDialog, TimelineView, parse_time
from config_defaults import default_config
from theme import GERMAN, STYLESHEET, THEMES, AppStyle, install_translator
from app_menus import MenusMixin
from app_daylist import DayListMixin
from app_docs import DocsMixin
from app_readers import ReadersMixin
from app_tray import TrayMixin
from app_transfer import TransferMixin
from app_protect import ProtectMixin

# Weiter über main_timeline erreichbar (Tests, Hilfsskripte)
__all__ = [
    "TimelineApp", "AppStyle", "install_translator", "GERMAN", "THEMES", "STYLESHEET",
    "resource_path", "APP_DIR", "DATA_DIR", "CONFIG_FILE", "CALLS_FILE", "VPN_FILE",
    "ACTIVITY_DIR", "PBX_PROFILE_DIR", "ITM_FILE", "ITM_PROFILE_DIR", "ITM_AUTH_FILE",
    "M42_FILE", "M42_PROFILE_DIR", "IMPORT_FILE", "AI_DIR", "JOURNAL_DIR", "DB_FILE", "BACKUP_FILE",
    "open_store", "backup_store",
    "CONFIG_LOCKED", "clean_path", "load_config_with_defaults", "save_config", "merged_seconds",
    "report_exception", "install_error_hooks", "acquire_single_instance",
    "ActivityViewDialog", "ActivityTypeSettingsDialog", "ConnectionSettingsDialog", "WorkHoursDialog",
]


warnings.filterwarnings("ignore", category=DeprecationWarning)

# Oberfläche mit der Windows-Anzeigegröße (125 %, 150 %, 200 %) mitskalieren.
# Qt 6 skaliert immer; nur die Rundung muss vor dem Start der QApplication gesetzt werden.
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
# Alle Nutzdaten liegen verschlüsselt in einer Datenbank (datastore.py). Die *_FILE/*_DIR
# unten sind die alten Pfade: Über sie finden die Module ihre Ablage in der Datenbank.
DB_FILE = storage.db_file(DATA_DIR)
BACKUP_FILE = storage.backup_file(DATA_DIR)  # None, wenn die Datenbank im Datenordner liegt
CONFIG_FILE = os.path.join(DATA_DIR, "zeitzeuge_config.json")
CALLS_FILE = os.path.join(DATA_DIR, "anrufe.json")
VPN_FILE = os.path.join(DATA_DIR, "vpn_verbindungen.json")
ACTIVITY_DIR = os.path.join(DATA_DIR, "aktivitaet")
# 3CX-Anmeldung immer lokal (nicht in OneDrive-synchronisierten Dokumenten)
PBX_PROFILE_DIR = os.path.join(storage.local_dir(), "3cx_profil")
ITM_FILE = os.path.join(DATA_DIR, "personalzeiten.json")
ITM_PROFILE_DIR = os.path.join(storage.local_dir(), "itm_profil")
# ITM-Anmeldung (refreshToken, unter Windows verschlüsselt), ebenfalls nur lokal
ITM_AUTH_FILE = os.path.join(storage.local_dir(), "itm_anmeldung.json")
M42_FILE = os.path.join(DATA_DIR, "m42_buchungen.json")
# Von einem anderen PC übernommene Daten (z. B. auf der PAW), alles in einer Datei
IMPORT_FILE = os.path.join(DATA_DIR, "uebernommen.json")
M42_PROFILE_DIR = os.path.join(storage.local_dir(), "m42_profil")
AI_DIR = os.path.join(DATA_DIR, "ki_vorschlaege")
JOURNAL_DIR = os.path.join(DATA_DIR, "taetigkeiten")
# Fehler und beiseitegelegte Dateien stehen in fehler.log (siehe safe_io)
safe_io.set_log_path(os.path.join(DATA_DIR, "fehler.log"))
CONFIG_LOCKED = False  # Config war beim Start gesperrt: dann nichts darüber speichern


def clean_path(path):
    """Doppelte Backslashes in Pfaden entfernen (Netzwerkpfade \\\\server bleiben)."""
    if path.startswith("\\\\"):
        return "\\\\" + re.sub(r"\\{2,}", r"\\", path[2:])
    return re.sub(r"\\{2,}", r"\\", path)


# Frühere Standard-Typfarben -> Farben aus "Metro Klar" (nur genau diese Werte werden ersetzt)
OLD_TYPE_COLORS = {
    "#00B894": "#0F9D8A",  # VPN
    "#F1C40F": "#D99A00",  # RDP
    "#E67E22": "#E06D10",  # SSH, Undokumentiert
    "#1ABC9C": "#139FB3",  # Website
    "#27AE60": "#2E9E5B",  # Telefonat
    "#2980B9": "#2272AD",  # M365-Admin (Schrift auf vollem Balken sonst zu blass)
}


class StoreLocked(Exception):
    """Daten gesperrt und nicht entsperrt (Abbruch im Dialog)."""


def open_store(ask=None):
    """Datenbank öffnen, entsperren, alte Dateien übernehmen. Einmal je Lauf.

    ask(store) wird aufgerufen, wenn kein Schlüsselfach zu diesem Windows-Benutzer passt
    (Dialog für den Wiederherstellungsschlüssel). Gibt True zurück, wenn entsperrt.
    StoreLocked, wenn die Daten gesperrt bleiben; datastore.Busy, wenn die Datei nicht aufgeht."""
    store = datastore.registered(DATA_DIR)
    if store and store.unlocked:
        return store
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DB_FILE) and BACKUP_FILE and os.path.exists(BACKUP_FILE):
        # Neuer PC oder lokale Daten gelöscht: aus der Sicherung im Datenordner weitermachen
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        shutil.copy2(BACKUP_FILE, DB_FILE)
        safe_io.log("Datenbank aus der Sicherung im Datenordner wiederhergestellt")
    store = datastore.Store(DB_FILE, DATA_DIR).open()
    try:
        store.unlock()
    except datastore.Locked:
        if not ask or not ask(store):
            store.close()
            raise StoreLocked()
    datastore.register(store)
    datastore.migrate_all(store)
    return store


def backup_store(force=False):
    """Sicherung in den Datenordner schreiben, wenn sich seit der letzten etwas geändert hat."""
    store = datastore.registered(DATA_DIR)
    if not BACKUP_FILE or not store or not store.unlocked:
        return False
    if not force and store.changes == store.backed_up:
        return False
    return store.backup(BACKUP_FILE)


def _names_store():
    return datastore.registered(DATA_DIR) or datastore.store_for_dir(DATA_DIR)


def load_config_with_defaults():
    defaults = default_config()
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
    cfg["type_colors"].setdefault("Telefonat", "#2E9E5B")
    for kind, color in [("VPN-Verbindung", "#0F9D8A"), ("SSH-Verbindung", "#E06D10"),
                        ("FTP-Verbindung", "#7F8C8D"), ("TeamViewer-Verbindung", "#3460DB"),
                        ("Zugangsdaten", "#9B59B6"), ("Arbeitsblock", "#5B8DEF"),
                        (AI_TYPE, "#A55EEA"), ("Dokumentiert", "#2E9E5B"),
                        ("Undokumentiert", "#E06D10"), ("Klassifizierung", "#8395A7"),
                        ("Matrix42-Buchung", "#6E7781"), ("Personalzeit", "#3D8BFD"),
                        ("Arbeitszeit", "#3D8BFD"), ("Nicht gebucht", "#E5484D")]:
        cfg["type_colors"].setdefault(kind, color)
    # Design "Metro Klar": alte Standardfarben einmalig umstellen, selbst gewählte Farben bleiben.
    # Nur einmal, damit eine später bewusst gewählte alte Farbe nicht wieder ersetzt wird.
    if cfg.get("type_colors_version", 1) < 2:
        for kind, color in list(cfg["type_colors"].items()):
            if isinstance(color, str) and color.upper() in OLD_TYPE_COLORS:
                cfg["type_colors"][kind] = OLD_TYPE_COLORS[color.upper()]
        cfg["type_colors_version"] = 2
    # Alte Standardpfade enthielten doppelte Backslashes (C:\Users\x\\TeamViewer)
    for key in ("teamviewer_paths", "rdm_paths", "vpn_paths"):
        cfg[key] = [clean_path(p) for p in cfg.get(key, []) if isinstance(p, str)]
    if "Telefonat" not in cfg["activity_types"]:
        cfg["activity_types"].append("Telefonat")
    cfg["activity_types"] = list(dict.fromkeys(cfg["activity_types"]))  # alte Doppelte entfernen

    # Kundennamen (TeamViewer-ID -> Name) sind Nutzdaten: in der Datenbank, nicht in der Config.
    # Stehen noch welche in der Datei, einmal übernehmen.
    old_names = cfg.pop("teamviewer_names", None) or {}
    try:
        store = _names_store()
        names = store.get("teamviewer_names", "", {})
        names = names if isinstance(names, dict) else {}
        if isinstance(old_names, dict) and old_names and any(names.get(k) != v for k, v in old_names.items()):
            names = {**old_names, **names}
            store.put("teamviewer_names", "", names)
    except (datastore.Busy, datastore.Locked) as e:
        safe_io.report(f"Kundennamen gerade nicht lesbar: {e}")
        names = old_names if isinstance(old_names, dict) else {}
    # gleich zurückschreiben (damit neue Keys persistieren), atomar, ohne Kundennamen
    if not CONFIG_LOCKED:
        safe_io.write_json(CONFIG_FILE, cfg, indent=2)
    cfg["teamviewer_names"] = names
    return cfg


def save_config(config: dict):
    if CONFIG_LOCKED:  # sonst stünden statt deiner Einstellungen nur Standardwerte in der Datei
        safe_io.log("zeitzeuge_config.json war beim Start gesperrt, Einstellungen nicht gespeichert")
        return
    names = config.get("teamviewer_names")
    if isinstance(names, dict):
        try:
            store = _names_store()
            if store.get("teamviewer_names", "", {}) != names:
                store.put("teamviewer_names", "", names)
        except (datastore.Busy, datastore.Locked) as e:
            safe_io.report(f"Kundennamen konnten nicht gespeichert werden: {e}")
    safe_io.write_json(CONFIG_FILE, {k: v for k, v in config.items() if k != "teamviewer_names"},
                       indent=4)


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


class TimelineApp(MenusMixin, DayListMixin, DocsMixin, ReadersMixin, TrayMixin, TransferMixin,
                  ProtectMixin, QMainWindow):
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
        self.data_store = open_store()  # im Start (unten) schon mit Dialog geöffnet, in Tests hier
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
        self.timeline.ai_entries = self.ai_day_entries
        self.timeline.ai_action.connect(self.on_ai_action)

        # Eigene Tätigkeiten (nachgetragen oder auf Nachfrage) und Regeln ohne KI
        self.journal = Journal(JOURNAL_DIR)
        # Übernommene Daten eines anderen PCs (Export/Import, z. B. Arbeits-PC -> PAW)
        self.imported = ImportStore(IMPORT_FILE)
        self.timeline.imported = self.imported
        self.journal.extra = self.imported.journal
        self.timeline.personal_day = self.personal_day_for
        self.timeline.doc_entries = self.doc_band
        self.timeline.rule_entries = self.rule_band
        self.timeline.m42_entries = self.m42_band
        self.timeline.doc_request.connect(self.on_doc_request)
        self.timeline.entry_action.connect(self.on_entry_action)
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
        # Metro: Spaltenköpfe in Großbuchstaben mit etwas Sperrung
        self.table.setHorizontalHeaderLabels([c.upper() for c in self.COLUMNS])
        header_font = self.table.horizontalHeader().font()
        header_font.setLetterSpacing(QFont.PercentageSpacing, 106)
        self.table.horizontalHeader().setFont(header_font)
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
        # Rechtsklick: dasselbe Menü wie in der Timeline, nur mit passenden Befehlen
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.table_menu)

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
        # Ladeanzeige über der Timeline: was gerade lädt (Logs, 3CX, ITM, KI)
        self.busy_bar = BusyBar(self)
        self._ai_busy = set()  # Tage, für die Claude gerade Vorschläge erstellt
        self.timeline.loading_changed.connect(lambda _on: self.update_busy_bar())
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.busy_bar)
        central_layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

        # Statuszeile
        self.info_label = QLabel(self)
        self.calls_label = QLabel(self)  # letzter Text des 3CX-Lesers (steht im Hinweis der Anzeige)
        self.calls_label.hide()  # nur Textspeicher, sonst läge es links oben über dem Datumsfeld
        self.statusBar().addWidget(self.info_label, 1)
        # Datenquellen nebeneinander: grüner Haken = läuft, gelbes Dreieck = keine Daten,
        # graue Uhr = liest gerade. Ein Klick führt zur Lösung (Anmeldung, Einstellungen).
        self.source_buttons = {}
        for kind in ("logs", "pbx", "itm", "m42"):
            button = QToolButton(self)
            button.setObjectName("source")
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            button.clicked.connect(lambda _c=False, k=kind: self.on_source_clicked(k))
            button.hide()
            self.statusBar().addPermanentWidget(button)
            self.source_buttons[kind] = button
        # Wichtigste Aufgabe sichtbar machen: offene Tätigkeiten, ein Klick trägt die erste ein
        self.open_docs_button = QToolButton(self)
        self.open_docs_button.setObjectName("cta")
        self.open_docs_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.open_docs_button.clicked.connect(self.document_next_open)
        self.open_docs_button.hide()
        self.statusBar().addPermanentWidget(self.open_docs_button)
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

        # Erst beide anlegen: Beim Start eines Lesers fragt die Statuszeile schon beide ab
        self.pbx_reader = None
        self.itm_reader = None
        self.m42_reader = None
        # 3CX direkt auslesen (Edge im Hintergrund)
        if self.config.get("pbx_reader_enabled", False):
            self.start_pbx_reader()

        # Personalzeiten aus der ITM-Zeiterfassung (Edge im Hintergrund)
        if self.config.get("itm_reader_enabled", False):
            self.start_itm_reader()

        # Gebuchte Zeiten aus Matrix42 (nur im Firmennetz erreichbar)
        if self.config.get("m42_reader_enabled", False):
            self.start_m42_reader()

        self.apply_style()  # setzt auch Icons und Aufzeichnungs-Zustand
        self.timeline.setFocus()
        # Erst zeichnen, wenn das Fenster seine echte Größe hat (spart ein Zeichnen beim Start).
        # Die Logs liest die Timeline dabei im Hintergrund.
        QTimer.singleShot(0, lambda: self.timeline.draw_timeline(self.current_date))
        self._init_protection()
        self._init_robustness()
        # PC-Verlauf nach N Tagen löschen (Standard aus), beim Start verzögert und täglich
        self.retention = RetentionRunner(self, ACTIVITY_DIR, save_config)


_last_error_report = [0.0]


def report_exception(exc_type, exc, tb, where=""):
    """Unbehandelte Ausnahme: Stacktrace in fehler.log, höchstens einmal pro Minute melden.
    Zeitzeuge läuft weiter."""
    try:
        # Der Text einer Ausnahme kann Nutzdaten enthalten (KeyError: 'Müller GmbH').
        # Ins Log nur Art und Stelle, den Text nur bei Datei-/Datenbankfehlern (Pfade).
        detail = str(exc)[:200] if isinstance(exc, (OSError, sqlite3.Error)) else "(Text weggelassen)"
        stack = "Traceback (most recent call last):\n" + "".join(traceback.format_tb(tb))
        safe_io.log(f"Unbehandelter Fehler{where}: {exc_type.__name__}: {detail}\n{stack.rstrip()}")
        if time.time() - _last_error_report[0] > 60:
            _last_error_report[0] = time.time()
            safe_io.report(f"Interner Fehler ({exc_type.__name__}). "
                           "Zeitzeuge läuft weiter, Details in fehler.log.")
    except Exception:
        pass  # Melden darf selbst nie abstürzen


def install_error_hooks():
    """Unbehandelte Ausnahmen abfangen. Ohne das landen Fehler in Slots nur auf der
    Konsole (in der EXE unsichtbar), und Fehler in Threads gingen ungesehen verloren."""
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
    from PySide6.QtCore import QLockFile
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
    # Qt 6 folgt sonst dem Windows-Farbschema (dunkel) bei allem, was das Design nicht selbst
    # färbt (Rahmen, Schatten, Meldungen vor dem Start). Wie unter Qt 5: Systemfarben hell.
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    install_translator(app)
    app.setQuitOnLastWindowClosed(False)
    if not acquire_single_instance(wait_ms=20000 if "--neustart" in sys.argv else 500):
        if "--minimized" not in sys.argv:
            QMessageBox.information(None, "Zeitzeuge",
                                    "Zeitzeuge läuft schon. Du findest es im Infobereich neben der Uhr.")
        sys.exit(0)
    from protect_dialogs import ask_unlock
    try:
        open_store(ask=ask_unlock)
    except StoreLocked:
        sys.exit(0)  # gesperrt gelassen: nichts anlegen, nichts überschreiben
    except datastore.Busy as e:
        QMessageBox.critical(None, "Zeitzeuge", f"Die Datenbank lässt sich nicht öffnen.\n\n{e}\n\n"
                             "Zeitzeuge beendet sich, ohne etwas zu ändern. Details in fehler.log.")
        safe_io.log(f"Datenbank nicht geöffnet: {e}")
        sys.exit(1)
    window = TimelineApp()
    from hang_watch import HangWatch
    hang_watch = HangWatch(os.path.join(DATA_DIR, "haenger.log"), app)
    if "--minimized" in sys.argv or window.config.get("start_minimized", False):
        if not window.tray:
            window.showMinimized()
    else:
        window.show()
    code = app.exec()
    if not window._quitting:  # z. B. Windows-Abmeldung: laufenden Abschnitt trotzdem speichern
        window.quit_app()
    # Direkt beenden: die Qt-Bindung räumt beim Interpreter-Ende sporadisch in falscher Reihenfolge auf
    # (Zugriffsfehler unter Windows). quit_app hat da schon alles gespeichert und gestoppt.
    sys.stdout and sys.stdout.flush()
    os._exit(code)
