import json
import os
import sys
import warnings

from PyQt5.QtCore import QDate, QObject, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPalette
from PyQt5.QtWidgets import (QAction, QApplication, QDateEdit, QLabel,
                             QMainWindow, QMenu, QMessageBox, QToolBar,
                             QVBoxLayout, QWidget)

from call_import import start_call_server
from settings_dialogs import (ActivityTypeSettingsDialog,
                              ConnectionSettingsDialog)
from timeline_only import TimelineView

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


class TimelineApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Zeitzeuge")
        self.setWindowIcon(QIcon(resource_path("zeitzeuge.ico")))
        self.resize(1100, 550)

        self.config = load_config_with_defaults()
        self.dark_mode = self.config.get("dark_mode", False)
        self.current_date = QDate.currentDate()
        self.activities = []

        central = QWidget()
        layout = QVBoxLayout(central)

        # Toolbar
        self.toolbar = QToolBar("Navigation", self)
        self.toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        prev_action = QAction("◀", self)
        next_action = QAction("▶", self)
        today_action = QAction("Heute", self)

        prev_action.triggered.connect(self.show_previous_day)
        next_action.triggered.connect(self.show_next_day)
        today_action.triggered.connect(self.show_today)

        self.date_edit = QDateEdit(self.current_date, self)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.dateChanged.connect(self.date_changed)

        zoom_in = QAction("Zoom +", self)
        zoom_out = QAction("Zoom -", self)
        zoom_reset = QAction("Reset", self)

        self.dark_action = QAction("Dark", self)
        self.dark_action.setCheckable(True)
        self.dark_action.setChecked(self.dark_mode)
        self.dark_action.toggled.connect(self.toggle_dark_mode)

        zoom_in.triggered.connect(self.zoom_in)
        zoom_out.triggered.connect(self.zoom_out)
        zoom_reset.triggered.connect(self.reset_zoom)

        self.toolbar.addAction(prev_action)
        self.toolbar.addAction(next_action)
        self.toolbar.addWidget(self.date_edit)
        self.toolbar.addAction(today_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(zoom_in)
        self.toolbar.addAction(zoom_out)
        self.toolbar.addAction(zoom_reset)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.dark_action)

        # Einstellungen direkt in der Toolbar
        settings_tv = QAction("TeamViewer", self)
        settings_rdm = QAction("RDM", self)
        settings_types = QAction("Aktivitätstypen", self)

        settings_tv.triggered.connect(self.edit_teamviewer_settings)
        settings_rdm.triggered.connect(self.edit_rdm_settings)
        settings_types.triggered.connect(self.edit_activity_types)

        self.toolbar.addSeparator()
        self.toolbar.addAction(settings_tv)
        self.toolbar.addAction(settings_rdm)
        self.toolbar.addAction(settings_types)
        
        about_action = QAction("?", self)
        about_action.triggered.connect(self.show_about)

        self.toolbar.addSeparator()
        self.toolbar.addAction(about_action)



        # Statuszeile
        self.info_label = QLabel("", self)
        self.statusBar().addPermanentWidget(self.info_label)

        # Timeline
        self.timeline = TimelineView(self.activities, self.config, parent=self)
        layout.addWidget(self.timeline)
        self.setCentralWidget(central)

        # Anruf-Empfang für das Tampermonkey-Skript starten
        self.timeline.calls_file = CALLS_FILE
        if self.config.get("calls_enabled", True):
            self.call_signal = CallSignal()
            self.call_signal.updated.connect(
                lambda: self.timeline.draw_timeline(self.current_date)
            )
            self.call_server = start_call_server(
                CALLS_FILE,
                port=self.config.get("calls_port", 8765),
                on_update=self.call_signal.updated.emit,
            )

        #Menü "Datei -> Einstellungen"
        #menubar = self.menuBar()
        #file_menu = menubar.addMenu("Datei")

       # settings_menu = QMenu("Einstellungen", self)
        #file_menu.addMenu(settings_menu)

       # teamviewer_action = QAction("TeamViewer", self)
       # rdm_action = QAction("RDM", self)
       # types_action = QAction("Aktivitätstypen", self)

        #teamviewer_action.triggered.connect(self.edit_teamviewer_settings)
       # rdm_action.triggered.connect(self.edit_rdm_settings)
       # types_action.triggered.connect(self.edit_activity_types)

       # settings_menu.addAction(teamviewer_action)
       # settings_menu.addAction(rdm_action)
       # settings_menu.addSeparator()
        #settings_menu.addAction(types_action)

        self.apply_style()
        self.timeline.draw_timeline(self.current_date)
        self.update_status_text()

    def show_about(self):
        icon_path = resource_path("zeitzeuge.png")
        text = (
            "<b>Zeitzeuge</b><br>"
            "Version 3.3<br>"
            "27.11.2025<br><br>"
        )
        msg = QMessageBox(self)
        msg.setWindowTitle("Über Zeitzeuge")
        msg.setText(text)
        msg.setTextFormat(Qt.RichText)
        msg.setStandardButtons(QMessageBox.Ok)
        if os.path.exists(icon_path):
            msg.setWindowIcon(QIcon(icon_path))
            msg.setIconPixmap(QIcon(icon_path).pixmap(64, 64))
        msg.exec_()



    # ---------------------- Datum / Navigation --------------------------------

    def update_status_text(self):
        self.info_label.setText(self.current_date.toString("ddd, dd.MM.yyyy"))

    def date_changed(self, date: QDate):
        self.current_date = date
        self.timeline.draw_timeline(self.current_date)
        self.update_status_text()

    def show_previous_day(self):
        self.date_edit.setDate(self.current_date.addDays(-1))

    def show_next_day(self):
        self.date_edit.setDate(self.current_date.addDays(1))

    def show_today(self):
        self.date_edit.setDate(QDate.currentDate())

    # ---------------------- Zoom / Dark-Mode ----------------------------------

    def zoom_in(self):
        self.timeline.zoom_level *= 1.1
        self.timeline.draw_timeline(self.current_date)

    def zoom_out(self):
        self.timeline.zoom_level /= 1.1
        self.timeline.draw_timeline(self.current_date)

    def reset_zoom(self):
        # Zoom zurücksetzen
        self.timeline.zoom_level = 1.0
        # aktuellen Tag neu zeichnen
        self.timeline._first_draw = True  # wieder auf Arbeitszeit zentrieren
        self.timeline.draw_timeline(self.current_date)


    def toggle_dark_mode(self, enabled: bool):
        self.dark_mode = enabled
        self.config["dark_mode"] = enabled
        save_config(self.config)
        self.apply_style()

    # ---------------------- Einstellungen / Dialoge ---------------------------

    def edit_teamviewer_settings(self):
        default_paths = [os.path.expandvars(r"%APPDATA%\TeamViewer\Connections.txt")]
        dialog = ConnectionSettingsDialog(
            self.config,
            "teamviewer",
            default_paths,
            "TeamViewer-Logeinstellungen",
            self,
        )
        if dialog.exec_() == dialog.Accepted:
            self.config["teamviewer_paths"] = dialog.get_paths()
            self.config["teamviewer_timezone_correction"] = (
                dialog.get_timezone_correction()
            )
            save_config(self.config)
            self.timeline.draw_timeline(self.current_date)

    def edit_rdm_settings(self):
        default_paths = [
            os.path.expandvars(
                r"%LOCALAPPDATA%\Devolutions\RemoteDesktopManager\Connections.log"
            )
        ]
        dialog = ConnectionSettingsDialog(
            self.config,
            "rdm",
            default_paths,
            "RDM-Logeinstellungen",
            self,
        )
        if dialog.exec_() == dialog.Accepted:
            self.config["rdm_paths"] = dialog.get_paths()
            self.config["rdm_timezone_correction"] = dialog.get_timezone_correction()
            save_config(self.config)
            self.timeline.draw_timeline(self.current_date)

    def edit_activity_types(self):
        dialog = ActivityTypeSettingsDialog(self.config, self)
        if dialog.exec_() == dialog.Accepted:
            self.config["activity_types"] = dialog.get_types()
            save_config(self.config)
            self.timeline.draw_timeline(self.current_date)

    # ---------------------- Styles (Dark / Light) -----------------------------

    def apply_style(self):
        if self.dark_mode:
            self.set_dark_style()
        else:
            self.set_light_style()
        self.timeline.set_dark_mode(self.dark_mode)

    def set_dark_style(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(30, 30, 30))
        dark_palette.setColor(QPalette.WindowText, QColor(243, 243, 243))
        dark_palette.setColor(QPalette.Base, QColor(37, 37, 38))
        dark_palette.setColor(QPalette.AlternateBase, QColor(45, 45, 48))
        dark_palette.setColor(QPalette.ToolTipBase, QColor(60, 60, 60))
        dark_palette.setColor(QPalette.ToolTipText, Qt.white)
        dark_palette.setColor(QPalette.Text, QColor(243, 243, 243))
        dark_palette.setColor(QPalette.Button, QColor(58, 61, 65))
        dark_palette.setColor(QPalette.ButtonText, QColor(243, 243, 243))
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Highlight, QColor(0, 122, 204))
        dark_palette.setColor(QPalette.HighlightedText, Qt.white)

        self.setPalette(dark_palette)
        self.setStyleSheet(
            """
        QWidget {
            background-color: #1E1E1E;
            color: #F3F3F3;
            font-size: 12px;
            font-family: "Segoe UI", Arial, sans-serif;
        }
        QGroupBox {
            border: 1px solid #3C3C3C;
            border-radius: 6px;
            margin-top: 1em;
            padding-top: 12px;
            background-color: #252526;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
        }
        QTextEdit, QLineEdit, QComboBox {
            background-color: #252526;
            color: #F3F3F3;
            border: 1px solid #3C3C3C;
            border-radius: 4px;
            padding: 4px;
            selection-background-color: #007ACC;
            selection-color: #FFFFFF;
        }
        QPushButton {
            background-color: #3A3D41;
            color: #F3F3F3;
            border: 1px solid #3C3C3C;
            border-radius: 4px;
            padding: 6px 12px;
            min-width: 80px;
        }
        QPushButton:hover {
            background-color: #45494E;
        }
        QPushButton:pressed {
            background-color: #33373B;
        }
        QDateEdit {
            background-color: #252526;
            color: #F3F3F3;
            border-radius: 4px;
            border: 1px solid #3C3C3C;
            padding: 4px;
            min-width: 110px;
        }
        QToolBar {
            background-color: #2D2D30;
            border-bottom: 1px solid #3C3C3C;
        }
        QStatusBar {
            background-color: #2D2D30;
            color: #C8C8C8;
        }
        QMenuBar {
            background-color: #2D2D30;
            color: #F3F3F3;
        }
        QMenuBar::item:selected {
            background-color: #007ACC;
            color: #FFFFFF;
        }
        QMenu {
            background-color: #252526;
            color: #F3F3F3;
            border: 1px solid #3C3C3C;
            border-radius: 4px;
            padding: 4px;
        }
        QMenu::item:selected {
            background-color: #007ACC;
            color: #FFFFFF;
        }
        QGraphicsView {
            border: 1px solid #3C3C3C;
            border-radius: 4px;
            background: #1E1E1E;
        }
        QDateEdit {
            background-color: #252526;
            color: #F3F3F3;
            border-radius: 4px;
            border: 1px solid #3C3C3C;
            padding: 4px;
            min-width: 110px;
        }

        /* Kalender-Popup im Dark-Mode */
        QCalendarWidget {
            background-color: #252526;
            color: #F3F3F3;
            border: 1px solid #3C3C3C;
        }

        /* Navigation (Monat/Jahr + Pfeile) */
        QCalendarWidget QToolButton {
            background-color: #2D2D30;
            color: #F3F3F3;
            border: none;
            font-weight: bold;
        }

        /* Bereich für Wochentagszeile (Mo–So) */
        QCalendarWidget QWidget#qt_calendar_navigationbar {
            background-color: #2D2D30;
        }

        /* Tabellenbereich: Wochentage + Tage */
        QCalendarWidget QTableView {
            background-color: #1E1E1E;
            color: #F3F3F3;                  /* Mo–Fr + alle Tage */
            selection-background-color: #007ACC;
            selection-color: #FFFFFF;
            gridline-color: #3C3C3C;
        }

        /* Wochentagskürzel (Mo–So) explizit heller und fett */
        QCalendarWidget QTableView QHeaderView::section {
            background-color: #252526;
            color: #FFFFFF;
            font-weight: bold;
        }

        /* ausgegraute Tage aus Vormonat/Nachmonat */
        QCalendarWidget QAbstractItemView:disabled {
            color: #555555;
        }
        """
        )

    def set_light_style(self):
        light_palette = QPalette()
        light_palette.setColor(QPalette.Window, QColor(240, 242, 245))
        light_palette.setColor(QPalette.WindowText, QColor(34, 34, 34))
        light_palette.setColor(QPalette.Base, Qt.white)
        light_palette.setColor(QPalette.AlternateBase, QColor(248, 248, 248))
        light_palette.setColor(QPalette.ToolTipBase, Qt.white)
        light_palette.setColor(QPalette.ToolTipText, QColor(34, 34, 34))
        light_palette.setColor(QPalette.Text, QColor(34, 34, 34))
        light_palette.setColor(QPalette.Button, QColor(225, 228, 232))
        light_palette.setColor(QPalette.ButtonText, QColor(34, 34, 34))
        light_palette.setColor(QPalette.BrightText, Qt.red)
        light_palette.setColor(QPalette.Highlight, QColor(0, 120, 215))
        light_palette.setColor(QPalette.HighlightedText, Qt.white)

        self.setPalette(light_palette)
        self.setStyleSheet(
            """
        QWidget {
            background-color: #F0F2F5;
            color: #222222;
            font-size: 12px;
            font-family: "Segoe UI", Arial, sans-serif;
        }
        QGroupBox {
            border: 1px solid #CCCCCC;
            border-radius: 6px;
            margin-top: 1em;
            padding-top: 12px;
            background-color: #FFFFFF;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
        }
        QTextEdit, QLineEdit, QComboBox {
            background-color: #FFFFFF;
            color: #222222;
            border: 1px solid #BBBBBB;
            border-radius: 4px;
            padding: 4px;
            selection-background-color: #0078D7;
            selection-color: #FFFFFF;
        }
        QPushButton {
            background-color: #E1E4E8;
            color: #222222;
            border: 1px solid #C0C4C8;
            border-radius: 4px;
            padding: 6px 12px;
            min-width: 80px;
        }
        QPushButton:hover {
            background-color: #D1D5D9;
        }
        QPushButton:pressed {
            background-color: #C0C4C8;
        }
        QDateEdit {
            background-color: #FFFFFF;
            color: #222222;
            border-radius: 4px;
            border: 1px solid #BBBBBB;
            padding: 4px;
            min-width: 110px;
        }
        QToolBar {
            background-color: #FFFFFF;
            border-bottom: 1px solid #CCCCCC;
        }
        QStatusBar {
            background-color: #FFFFFF;
            color: #555555;
        }
        QMenuBar {
            background-color: #FFFFFF;
            color: #222222;
        }
        QMenuBar::item:selected {
            background-color: #0078D7;
            color: #FFFFFF;
        }
        QMenu {
            background-color: #FFFFFF;
            color: #222222;
            border: 1px solid #CCCCCC;
            border-radius: 4px;
            padding: 4px;
        }
        QMenu::item:selected {
            background-color: #0078D7;
            color: #FFFFFF;
        }
        QGraphicsView {
            border: 1px solid #CCCCCC;
            border-radius: 4px;
            background: #FFFFFF;
        }
        """
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TimelineApp()
    window.show()
    sys.exit(app.exec_())
