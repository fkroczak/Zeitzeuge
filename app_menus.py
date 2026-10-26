"""Hauptfenster: Werkzeugleiste, Menü Einstellungen, Design, Einstellungsdialoge, Speicherort.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
"""
import os
import sys

from PySide6.QtCore import QProcess, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (QAction, QActionGroup, QColor, QDesktopServices, QIcon, QKeySequence,
                           QPalette)
from PySide6.QtWidgets import (QApplication, QDateEdit, QDialog, QFileDialog, QMenu, QMessageBox,
                               QToolBar, QToolButton, QHBoxLayout, QSizePolicy, QWidget)

import datastore
import icons
import storage
from log_parsers import VpnParser
from vpn_reader import vpn_sources
from settings_dialogs import ActivityTypeSettingsDialog, ConnectionSettingsDialog, WorkHoursDialog
from theme import GERMAN, STYLESHEET, THEMES
from timeline_only import TIMELINE_ROWS
from version import VERSION
import main_timeline as mt  # Pfade und save_config zur Laufzeit von dort (Tests ersetzen sie dort)


class MenusMixin:
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
        header.setObjectName("band_row")
        # Nur die Zeile selbst durchsichtig, sonst erben auch Datum und Knöpfe "transparent"
        header.setStyleSheet("#band_row { background: transparent; }")
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
            "Zuordnung ohne KI: Tätigkeiten, die Zeitzeuge über feste Regeln erkannt hat\n"
            "  (z. B. Outlook → E-Mail, TeamViewer → Fernwartung)\n"
            "KI-Vorschläge: Tätigkeiten, die Claude aus dem Tag erkannt hat\n"
            "Matrix42-Abgleich: Buchungen, Personalzeit ohne Buchung, Verbindungen ohne Buchung")
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
            (menu.addAction("&Zuordnung ohne KI (Regeln) …", self.edit_rules), "rules"),
        ]
        menu.addSeparator()
        self._icon_actions += [
            (menu.addAction("&Arbeitszeiten …", self.edit_work_hours), "clock"),
            (menu.addAction("Aktivitäts&typen und Farben …", self.edit_activity_types), "palette"),
            (menu.addAction("&KI-Vorschläge …", self.edit_ai_settings), "spark"),
            (menu.addAction("Abre&chnung …", self.edit_billing), "tag"),
        ]
        menu.addSeparator()
        self._icon_actions.append(
            (menu.addAction("&Nachfragen und Erinnerungen …", self.edit_prompt_settings), "bell"))
        self._icon_actions.append((menu.addAction("Text&bausteine …", self.edit_snippets), "edit"))
        rows_menu = menu.addMenu("&Zeilen der Timeline")
        self.row_actions = {}
        for key, text in TIMELINE_ROWS:
            if key in ("doc", "call"):  # Gruppen: Zeit | Auswertung | Verbindungen
                rows_menu.addSeparator()
            action = rows_menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(self.config.get("timeline_rows", {}).get(key, True))
            action.toggled.connect(lambda on, k=key: self.toggle_row(k, on))
            self.row_actions[key] = action
        rows_menu.addSeparator()
        rows_menu.addAction("&Alle einblenden", self.show_all_rows)
        self._icon_actions.append((rows_menu.menuAction(), "rows"))
        menu.addSeparator()
        self.sources_menu = self._build_sources_menu(menu)
        storage_menu = menu.addMenu("Daten&speicher")
        self.open_folder_action = storage_menu.addAction(
            "&Datenordner öffnen", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(mt.DATA_DIR)))
        storage_menu.addAction("&Speicherort ändern …", self.change_data_dir)
        self._icon_actions.append((storage_menu.addAction("Sc&hutz …", self.show_protection), "lock"))
        storage_menu.addAction("PC-&Verlauf automatisch löschen …", lambda: self.retention.edit())
        storage_menu.addSeparator()  # zwei PCs, z. B. Arbeits-PC und PAW
        storage_menu.addAction("Daten &exportieren (für einen anderen PC) …", self.export_data)
        storage_menu.addAction("Daten &übernehmen (von einem anderen PC) …", self.import_data)
        self.paw_action = storage_menu.addAction("Dieser PC ist eine &PAW (nur RDM sammeln)")
        self.paw_action.setCheckable(True)
        self.paw_action.setChecked(self.config.get("pc_role") == "paw")
        self.paw_action.toggled.connect(self.toggle_paw)
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
        [("pbx_reader_enabled", "&3CX-Anrufe"), ("itm_reader_enabled", "&ITM-Personalzeiten"),
         ("m42_reader_enabled", "&Matrix42-Buchungen (Firmennetz)")],
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
                                                                          "itm_reader_enabled",
                                                                          "m42_reader_enabled"))))
                action.toggled.connect(lambda on, k=key: self.toggle_source(k, on))
                self.source_actions[key] = action
        menu.addSeparator()
        setup = menu.addMenu("&Einrichten")
        setup.addAction("Team&Viewer-Logs …", self.edit_teamviewer_settings)
        setup.addAction("&RDM-Logs …", self.edit_rdm_settings)
        setup.addAction("&VPN-Logs …", self.edit_vpn_settings)
        setup.addSeparator()  # Webseiten im Hintergrund
        setup.addAction("&3CX …", self.open_pbx_settings)
        setup.addAction("&ITM-Personalzeiten …", self.open_itm_settings)
        setup.addAction("&Matrix42 …", self.open_m42_settings)
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
        mt.save_config(self.config)
        if key == "pbx_reader_enabled":
            self.start_pbx_reader() if on else self.stop_pbx_reader()
        elif key == "itm_reader_enabled":
            self.start_itm_reader() if on else self.stop_itm_reader()
        elif key == "m42_reader_enabled":
            if on and not self.config.get("m42_url"):  # erst die Adresse einrichten
                self.open_m42_settings()
                if not self.m42_reader:  # abgebrochen: bleibt aus
                    self.config[key] = False
                    mt.save_config(self.config)
                self.sync_source_actions()
            elif on:
                self.start_m42_reader()
            else:
                self.stop_m42_reader()
        elif key in ("sophos_enabled", "forti_enabled"):
            self.timeline.vpn_reader.sources = vpn_sources(self.config)
            self.apply_vpn_monitor()
        self.timeline.refresh()  # neu einlesen und zeichnen

    def show_about(self):
        icon_path = mt.resource_path("zeitzeuge.png")
        msg = QMessageBox(self)
        msg.setWindowTitle("Über Zeitzeuge")
        msg.setTextFormat(Qt.RichText)
        msg.setText(
            f"<b>Zeitzeuge</b><br>Version {VERSION}<br><br>"
            "<a href='https://github.com/fkroczak/Zeitzeuge'>github.com/fkroczak/Zeitzeuge</a>"
        )
        msg.setStandardButtons(QMessageBox.Ok)
        if os.path.exists(icon_path):
            msg.setIconPixmap(QIcon(icon_path).pixmap(64, 64))
        msg.exec()

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
        mt.save_config(self.config)
        self.apply_style()

    def apply_style(self):
        theme = THEMES["dark" if self.dark_mode else "light"]
        sheet = STYLESHEET
        for key in sorted(theme, key=len, reverse=True):  # $bandtext vor $band ersetzen
            sheet = sheet.replace(f"${key}", theme[key])
        # Palette passend setzen, sonst nutzen Tabellen/Scrollbars die Systemfarben
        pal = QPalette()
        for role, key in [(QPalette.Window, "bg"), (QPalette.WindowText, "text"),
                          (QPalette.Base, "surface"), (QPalette.AlternateBase, "alt"),
                          (QPalette.Text, "text"), (QPalette.Button, "bar"),
                          (QPalette.ButtonText, "text"), (QPalette.Highlight, "sel"),
                          (QPalette.HighlightedText, "seltext"),
                          (QPalette.ToolTipBase, "surface"), (QPalette.ToolTipText, "text"),
                          (QPalette.PlaceholderText, "muted"),
                          (QPalette.Accent, "accent")]:  # Qt 6 nutzt Accent statt Highlight
            pal.setColor(role, QColor(theme[key]))
        self.setStyleSheet("")  # alte Farben vollständig entfernen
        QApplication.instance().setPalette(pal)
        self.setStyleSheet(sheet)
        # Symbole im farbigen Band oben in dessen Schriftfarbe, in Menüs in der normalen
        for action, name in self._icon_actions:
            in_menu = any(isinstance(o, QMenu) for o in action.associatedObjects())
            action.setIcon(icons.icon(name, theme["text" if in_menu else "bandtext"]))
        self.menu_button.setIcon(icons.icon("menu", theme["bandtext"]))
        self.view_button.setIcon(icons.icon("eye", theme["bandtext"]))
        self.busy_bar.set_color(theme["accent"])
        self.update_tracking_state()
        self.timeline.set_dark_mode(self.dark_mode)

    # ---------------------- Einstellungen / Dialoge ---------------------------

    def _edit_log_settings(self, key, default_path, title, **options):
        defaults = default_path if isinstance(default_path, list) else [default_path]
        dialog = ConnectionSettingsDialog(
            self.config, key, [os.path.expandvars(p) for p in defaults], title, self, **options
        )
        if dialog.exec() == QDialog.Accepted:
            self.config[f"{key}_paths"] = dialog.get_paths()
            if dialog.enabled_box:
                self.config[f"{key}_enabled"] = dialog.enabled_box.isChecked()
            self.config[f"{key}_timezone_correction"] = dialog.get_timezone_correction()
            mt.save_config(self.config)
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
        if dialog.exec() == QDialog.Accepted:
            self.config["work_days"] = dialog.get_work_days()
            mt.save_config(self.config)
            self.timeline._first_draw = True  # auf die neue Arbeitszeit springen
            self.timeline.draw_timeline(self.current_date)

    def edit_billing(self):
        from billing_dialogs import BillingDialog
        dialog = BillingDialog(self.config, self.known_customers(), self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply()
            mt.save_config(self.config)
            self.timeline.draw_timeline(self.current_date)

    def edit_activity_types(self):
        dialog = ActivityTypeSettingsDialog(self.config, self)
        if dialog.exec() == QDialog.Accepted:
            self.config["activity_types"] = dialog.get_types()
            mt.save_config(self.config)
            self.timeline.draw_timeline(self.current_date)

    # ---------------------- Speicherort ----------------------------------------

    def change_data_dir(self):
        new_dir = QFileDialog.getExistingDirectory(
            self, f"Speicherort wählen (bisher: {mt.DATA_DIR})", mt.DATA_DIR
        )
        if not new_dir or os.path.abspath(new_dir) == os.path.abspath(mt.DATA_DIR):
            return
        answer = QMessageBox.question(
            self, "Speicherort ändern",
            f"Einstellungen und die Sicherung der Datenbank werden nach\n{new_dir}\n"
            "verschoben. Zeitzeuge startet danach neu.",
        )
        if answer != QMessageBox.Yes:
            return
        # Erst alles anhalten, was in die Dateien schreibt
        if self.tracker:
            self.tracker.stop()
        for reader in self.all_readers():
            if reader:
                reader.stop()
        mt.save_config(self.config)
        mt.backup_store(force=True)  # Sicherung auf den neuesten Stand, sie zieht mit um
        if not mt.BACKUP_FILE:  # Datenbank liegt im Datenordner: vor dem Verschieben schließen
            datastore.unregister(mt.DATA_DIR)
        try:
            storage.move_data(mt.DATA_DIR, new_dir)
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
            QProcess.startDetached(sys.executable, [os.path.abspath(mt.__file__), "--neustart"])
        self.quit_app()
