"""Hauptfenster: Werkzeugleiste, Menüs Ansicht und Einstellungen, Design, Einstellungsdialoge, Speicherort.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
"""
import os
import sys

from PySide6.QtCore import QPoint, QProcess, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (QAction, QActionGroup, QColor, QDesktopServices, QIcon, QKeySequence,
                           QPalette)
from PySide6.QtWidgets import (QApplication, QDateEdit, QDialog, QFileDialog, QLabel, QMenu, QMessageBox,
                               QToolBar, QToolButton, QHBoxLayout, QSizePolicy, QWidget, QWidgetAction)

import datastore
import icons
import storage
from log_parsers import VpnParser
from vpn_reader import vpn_sources
from settings_dialogs import ActivityTypeSettingsDialog, ConnectionSettingsDialog, WorkHoursDialog
from theme import GERMAN, STYLESHEET, THEMES
from timeline_only import DEFAULT_CALL_COLORS, LEGEND_BANDS, LEGEND_FIXED, TIMELINE_ROWS
from view_help import VIEW_HELP, ViewHelpDialog, help_text
from version import build_details, full_version
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
        self._band_row = header

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
        today = self._action("Heute", self.show_today, "Ctrl+T", "Heute zeigen", "today")
        days.addAction(today)
        self._today_button = days.widgetForAction(today)
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
        # Nachtragen (Stift), KI-Vorschläge (Stern)
        self.pc_list_action = QAction("PC-Verlauf", self)
        self.pc_list_action.setCheckable(True)
        self.pc_list_action.setChecked(self.config.get("show_pc_in_list", False))
        self.pc_list_action.toggled.connect(self.toggle_pc_list)
        self._icon_actions.append((self.pc_list_action, "monitor"))
        # PC-Aktivität: Arbeitsblöcke je Tätigkeit oder jedes Fenster einzeln (focus.py)
        self.pc_blocks_action = QAction("PC-Aktivität als &Arbeitsblöcke", self)
        self.pc_blocks_action.setCheckable(True)
        self.pc_blocks_action.setChecked(self.config.get("pc_blocks", True))
        self.pc_blocks_action.setToolTip("An: Fenster je Tätigkeit zu Blöcken zusammengefasst. "
                                         "Aus: jedes Fenster einzeln als schmales Band.")
        self.pc_blocks_action.toggled.connect(self.toggle_pc_blocks)
        # PC-Verlauf: nur im Menü Ansicht
        self.update_pc_list_tip()

        self.ai_button_action = self._action(
            "KI-Vorschläge", lambda: self.classify_day(), "F6",
            "KI-Vorschläge: Tätigkeiten des Tages von Claude einordnen lassen", "spark")
        self.doc_button_action = self._action(
            "Nachtragen", lambda: self.add_doc(), None,
            "Tätigkeit nachtragen (zur markierten Zeile oder zur letzten halben Stunde)", "edit")
        tb.addAction(self.doc_button_action)  # Stift vorn, gleich nach Aktualisieren
        tb.addAction(self.ai_button_action)
        self.week_action = self._action(
            "Wochenabschluss", self.show_week, None,
            "Wochenabschluss: Buchungsquote, Lücken und Offenes der Woche", "gauge")
        # Wochenabschluss: im Menü Ansicht und per Klick auf die Quote in der Statuszeile
        tb.addSeparator()
        # Ausschnitt der Timeline
        self.zoom_out_action = self._action("Verkleinern", self.zoom_out, "Ctrl+-", "Timeline verkleinern",
                                            "zoom_out")
        self.zoom_in_action = self._action("Vergrößern", self.zoom_in, ["Ctrl++", "Ctrl+="],
                                           "Timeline vergrößern", "zoom_in")
        # Verkleinern/Vergrößern nur per Tastatur (Strg+-, Strg++) und Strg+Mausrad, nicht als Knöpfe
        whole_day = self._action("Ganzer Tag", self.timeline_whole_day, "Ctrl+0",
                                 "Ganzen Tag zeigen (oder Doppelklick in die Timeline; "
                                 "zoomen mit Strg+Mausrad oder mit rechts ziehen)", "whole_day")
        work_time = self._action("Arbeitszeit", self.timeline_work_time, "Ctrl+9",
                                 "Arbeitszeit des Tages zeigen (feiner zoomen mit Strg+Mausrad)", "work_time")
        tb.addAction(whole_day)
        tb.addAction(work_time)
        self.whole_day_action, self.work_time_action = whole_day, work_time
        self._adaptive_buttons = []  # Heute, Ganzer Tag, Arbeitszeit: nur Symbol, Text im Hinweis

        # ---- rechts: Einstellungen (immer sichtbar)
        right = QToolBar("Einstellungen", header)
        right.setObjectName("fixed")
        right.setIconSize(QSize(18, 18))
        right.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        right.addWidget(self._build_view_button())
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
        # Heute, Ansicht und Einstellungen mit Text, solange das Fenster breit genug ist
        wide = self.width() >= 980
        for button in (self.view_button, self.menu_button):
            if button is not None:
                button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if wide else Qt.ToolButtonIconOnly)
        self.place_busy_bar()

    def place_busy_bar(self):
        """Ladeanzeige in den freien Platz zwischen Werkzeugen und Menü legen, Streifen oben.

        Sie schwebt über der Leiste, statt im Layout Platz zu belegen: Ein- und
        Ausblenden verschiebt so weder Knöpfe noch die Timeline."""
        bar, tb = getattr(self, "busy_bar", None), getattr(self, "tools_bar", None)
        if bar is None or tb is None:
            return
        header = self._band_row
        tools_right = 0
        for action in tb.actions():
            widget = tb.widgetForAction(action)
            if widget is not None and widget.isVisible():
                tools_right = max(tools_right, widget.geometry().right())
        ext = tb.findChild(QToolButton, "qt_toolbar_ext_button")
        if ext is not None and ext.isVisible():
            tools_right = max(tools_right, ext.geometry().right())
        left = tb.mapTo(header, QPoint(tools_right, 0)).x() + 16
        right = tb.geometry().right() - 4
        height = min(header.height(), 30)
        bar.setGeometry(left, (header.height() - height) // 2, max(right - left, 0), height)
        stripe = bar.stripe
        if stripe.parentWidget() is not bar:
            stripe.setGeometry(0, 0, stripe.parentWidget().width(), stripe.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.fit_toolbar)  # erst wenn die Leiste ihre neue Breite hat

    def update_view_button(self):
        """Haken an der aktuellen Ansicht und Hinweis am Knopf „Ansicht“."""
        key = self.config.get("list_view", "grouped")
        if key not in self.view_actions:
            key = "grouped"
        self.view_actions[key].setChecked(True)
        current = dict(self.VIEWS)[key]
        self.view_button.setToolTip(f"Ansicht: Tagesliste ({current}), Zeilen der Timeline, "
                                    "Zeitraum, Übersichten und Design (Alt+A)")
        self.view_button.setAccessibleDescription(f"Tagesliste aktuell: {current}")
        theme = THEMES["dark" if self.dark_mode else "light"]
        for k, action in self.view_actions.items():  # Hilfe mit den aktuellen Pausen
            action.setToolTip(help_text(k, self.config))
            action.setStatusTip(help_text(k, self.config))
            # Symbol statt Haken: die aktuelle Ansicht in Akzentfarbe und fett
            action.setIcon(icons.icon(VIEW_HELP[k][0], theme["accent" if k == key else "text"]))
            font = action.font()
            font.setBold(k == key)
            action.setFont(font)

    def show_view_help(self):
        """Erklärung der Ansichten der Tagesliste mit Beispielen."""
        theme = THEMES["dark" if self.dark_mode else "light"]
        ViewHelpDialog(self.VIEWS, self.config, theme["text"],
                       self.config.get("list_view", "grouped"), self).exec()

    def _menu_header(self, menu, text):
        """Überschrift eines Abschnitts im Menü (klein, grau, fett, nicht anklickbar)."""
        if menu.actions():
            menu.addSeparator()
        label = QLabel(text)  # keine Großbuchstaben: schwerer zu lesen
        label.setObjectName("menu_header")
        action = QWidgetAction(menu)
        action.setDefaultWidget(label)
        action.setEnabled(False)
        menu.addAction(action)
        return action

    # Ansichten im Menü mit Alt-Buchstaben (VIEWS bleibt ohne, für Hinweise und Hilfe)
    VIEW_MNEMONICS = {"grouped": "Zus&ammengefasst", "single": "E&inzeln", "blocks": "Arbeits&blöcke",
                      "doc": "Dok&umentation", "rules": "Zuordnung o&hne KI", "ai": "K&I-Vorschläge",
                      "m42": "Matri&x42-Abgleich"}

    def _add_check(self, menu, action, color, text=None):
        """Schalter im Menü mit sichtbarem Kästchen: eigener Eintrag, der action umschaltet.
        Das Kästchen hat die Farbe color (z. B. Farbe der Zeile) und folgt action."""
        proxy = menu.addAction(text or action.text())
        proxy.setToolTip(action.toolTip() if action.toolTip() != action.text() else "")
        proxy.triggered.connect(action.toggle)
        proxy.setData(color)
        action.toggled.connect(lambda on, p=proxy: p.setIcon(icons.check_box(p.data(), on)))
        proxy.setIcon(icons.check_box(color, action.isChecked()))
        self._check_proxies[action] = proxy
        return proxy

    def _build_view_button(self):
        """Knopf „Ansicht“: alles, was nur die Anzeige ändert, nichts an den Daten."""
        menu = QMenu(self)
        menu.setObjectName("view_menu")
        menu.setToolTipsVisible(True)  # Hilfe zu den Ansichten beim Darüberfahren
        self._check_proxies = {}
        accent = THEMES["dark" if self.dark_mode else "light"]["accent"]
        self._menu_header(menu, "Tagesliste")
        group = QActionGroup(menu)
        self.view_actions = {}
        for key, text in self.VIEWS:
            if key == "doc":  # Trennlinie: Einträge aus den Logs | eingeordnete Tätigkeiten
                menu.addSeparator()
            action = menu.addAction(self.VIEW_MNEMONICS.get(key, text))
            action.setCheckable(True)
            action.setActionGroup(group)
            action.triggered.connect(lambda _c=False, k=key: self.change_view(k))
            self.view_actions[key] = action
        menu.addSeparator()
        self._add_check(menu, self.pc_list_action, accent, "PC-&Verlauf in der Liste")
        help_action = menu.addAction("&Was zeigen die Ansichten? …", self.show_view_help)
        help_action.setShortcut(QKeySequence("F1"))
        help_action.setToolTip("Zusammengefasst, Einzeln, Arbeitsblöcke … mit Beispielen erklärt")
        self.addAction(help_action)
        self._icon_actions.append((help_action, "help"))

        # Zeilen der Timeline: eigenes Menü, auch per Rechtsklick auf die Legende links
        self.rows_menu = self._build_rows_menu()
        menu.addSeparator()
        self._icon_actions.append((menu.addMenu(self.rows_menu), "rows"))
        self._add_check(menu, self.pc_blocks_action, accent)

        self._menu_header(menu, "Übersichten")
        self._icon_actions.append((menu.addAction("Wochen&abschluss …", self.show_week), "gauge"))
        # Tagesabschluss (app_day_close.py): Vorschläge prüfen, dokumentieren, buchen
        self.day_close_action = QAction("&Tagesabschluss …", self)
        self.day_close_action.setToolTip("Tag aus allen Spuren zu Blöcken je Kunde zusammenstellen, "
                                         "prüfen, dokumentieren und in Matrix42 buchen")
        self.day_close_action.triggered.connect(lambda: self.show_day_close())
        # kein Kürzel: F7 bis F12 bleiben für andere Werkzeuge frei (README, Tastenkürzel)
        menu.addAction(self.day_close_action)
        self._icon_actions.append((self.day_close_action, "check"))
        self._icon_actions.append((menu.addAction("&Offene Tätigkeiten …", self.show_open_docs), "alert"))
        # Zeitraum (Ganzer Tag, Arbeitszeit) steht in der Werkzeugleiste, Design in den Einstellungen
        menu.addSeparator()
        self._icon_actions.append((menu.addAction("An&passen mit Vorschau …",
                                                  lambda: self.show_settings("view")), "eye"))

        self.view_button = QToolButton(self)
        self.view_button.setText("&Ansicht")
        self.view_button.setAccessibleName("Ansicht")
        self.view_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.view_button.setMenu(menu)
        self.view_button.setPopupMode(QToolButton.InstantPopup)
        self.update_view_button()
        return self.view_button

    def _build_rows_menu(self):
        """Menü „Zeilen der Timeline“: jede Zeile ein- und ausblenden."""
        menu = QMenu("&Zeilen der Timeline", self)
        menu.setToolTipsVisible(True)
        # Auch hier umschaltbar (Rechtsklick auf die Legende), ohne das Kästchen im Menü Ansicht zu ersetzen
        accent = THEMES["dark" if self.dark_mode else "light"]["accent"]
        blocks = menu.addAction(self.pc_blocks_action.text())
        blocks.setToolTip(self.pc_blocks_action.toolTip())
        blocks.triggered.connect(self.pc_blocks_action.toggle)
        blocks.setData(accent)
        self.pc_blocks_action.toggled.connect(lambda on, p=blocks: p.setIcon(icons.check_box(p.data(), on)))
        blocks.setIcon(icons.check_box(accent, self.pc_blocks_action.isChecked()))
        self._rows_blocks_proxy = blocks
        menu.addSeparator()
        self.row_actions = {}
        for key, text in TIMELINE_ROWS:
            if key in ("doc", "call"):  # Gruppen: Zeit | Auswertung | Verbindungen
                menu.addSeparator()
            action = QAction(text, self)
            action.setCheckable(True)
            action.setChecked(self.config.get("timeline_rows", {}).get(key, True))
            action.toggled.connect(lambda on, k=key: self.toggle_row(k, on))
            self.row_actions[key] = action
            self._add_check(menu, action, "#4682B4")
        menu.addSeparator()
        self._icon_actions.append((menu.addAction("A&lle Zeilen einblenden", self.show_all_rows), "rows"))
        hint = menu.addAction("Leere Zeilen blendet Zeitzeuge von selbst aus")
        hint.setEnabled(False)
        self.update_row_icons()
        return menu

    def show_rows_menu(self, pos):
        """Rechtsklick auf die Legende der Timeline."""
        self.rows_menu.exec(pos)

    def update_row_icons(self):
        """Kästchen je Zeile der Timeline, in der Farbe ihrer Einträge."""
        colors = self.config.get("type_colors", {})
        call = {**DEFAULT_CALL_COLORS, **self.config.get("call_colors", {})}["Eingehend"]
        fixed = {"pc": "#2F7BFF", "call": call, "other": colors.get("RDP-Sitzung", "#BB8400")}
        for key, action in self.row_actions.items():
            color = fixed.get(key)
            if color is None:
                legend = LEGEND_BANDS.get(key) or LEGEND_FIXED.get(key)
                color = colors.get(legend[1], "#4682B4") if legend else "#4682B4"
            proxy = self._check_proxies.get(action)
            if proxy is not None:
                proxy.setData(color)
                proxy.setIcon(icons.check_box(color, action.isChecked()))

    def toggle_pc_blocks(self, on):
        self.config["pc_blocks"] = on
        mt.save_config(self.config)
        self.timeline.draw_timeline(self.current_date)
        self.statusBar().showMessage("PC-Aktivität: " + ("Arbeitsblöcke je Tätigkeit" if on
                                                         else "jedes Fenster einzeln"), 3000)

    def update_pc_list_tip(self):
        on = self.pc_list_action.isChecked()
        self.pc_list_action.setToolTip(
            "PC-Verlauf: aktive Fenster in der Tagesliste " + ("zeigen (an)" if on else "zeigen (aus)"))

    def _build_settings_button(self):
        """Knopf „Einstellungen“: Klick öffnet das Einstellungsfenster (settings_window.py),
        der Pfeil daneben zeigt Schnellzugriffe. Steht rechts außerhalb des Überlaufs (»)."""
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        self._icon_actions.append(
            (menu.addAction("&Alle Einstellungen …", self.show_settings), "settings"))
        menu.addSeparator()
        self.tracking_action = menu.addAction("Aktive &Fenster aufzeichnen")
        self.tracking_action.setCheckable(True)
        self.tracking_action.setChecked(self.config.get("tracking_enabled", True))
        self.tracking_action.toggled.connect(self.toggle_tracking)
        self._icon_actions.append((self.tracking_action, "monitor"))
        self.dark_action = QAction("&Dunkles Design", self)
        self.dark_action.setCheckable(True)
        self.dark_action.setChecked(self.dark_mode)
        self.dark_action.toggled.connect(self.toggle_dark_mode)
        self._add_check(menu, self.dark_action, THEMES["dark" if self.dark_mode else "light"]["accent"])
        # Datenquellen: im Einstellungsfenster (Kacheln mit Zustand); das Untermenü nutzt der Infobereich
        self.sources_menu = self._build_sources_menu()
        self._icon_actions.append(
            (menu.addAction("Daten&quellen …", lambda: self.show_settings("sources")), "plug"))
        menu.addSeparator()
        self._icon_actions += [
            (menu.addAction("&Nachfragen und Erinnerungen …", self.edit_prompt_settings), "bell"),
            (menu.addAction("Kunden&liste …", self.edit_customers), "users"),
            (menu.addAction("Text&bausteine …", self.edit_snippets), "edit"),
        ]
        # Datenspeicher: im Einstellungsfenster unter „Daten & Schutz“. Die Aktionen gibt es
        # trotzdem, der Infobereich nutzt „Datenordner öffnen“ und den PAW-Schalter.
        self.open_folder_action = QAction("&Datenordner öffnen", self)
        self.open_folder_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(mt.DATA_DIR)))
        self.paw_action = QAction("Dieser PC ist eine &PAW (nur RDM sammeln)", self)
        self.paw_action.setCheckable(True)
        self.paw_action.setChecked(self.config.get("pc_role") == "paw")
        self.paw_action.toggled.connect(self.toggle_paw)
        self._icon_actions += [(self.sources_menu.menuAction(), "plug"),
                               (self.open_folder_action, "folder")]
        menu.addSeparator()
        self._icon_actions += [
            (menu.addAction("Ü&ber Zeitzeuge", self.show_about), "info"),
            (menu.addAction("Zeitzeuge be&enden", self.request_quit), "power"),
        ]
        settings_shortcut = QAction(self)
        settings_shortcut.setShortcut(QKeySequence("Ctrl+,"))
        settings_shortcut.triggered.connect(self.show_settings)
        self.addAction(settings_shortcut)
        self.menu_button = QToolButton(self)
        self.menu_button.setText("&Einstellungen")
        self.menu_button.setToolTip("Einstellungen öffnen (Strg+,) · Pfeil: Schnellzugriffe")
        self.menu_button.setAccessibleName("Einstellungen")
        self.menu_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.menu_button.setMenu(menu)
        self.menu_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.menu_button.clicked.connect(lambda: self.show_settings())
        return self.menu_button

    def show_settings(self, page=None):
        """Einstellungsfenster zeigen (bleibt offen), optional auf einem Bereich."""
        from settings_window import SettingsWindow
        window = getattr(self, "_settings_window", None)
        if window is None:
            window = self._settings_window = SettingsWindow(self)
        if page:
            window.show_page(page)
        window.show()
        window.raise_()
        window.activateWindow()
        return window

    # Datenquellen: Schlüssel in der Config, Text im Menü (Gruppen mit Trennlinie)
    SOURCES = [
        [("teamviewer_enabled", "&TeamViewer"), ("rdm_enabled", "&RDM (Remote Desktop Manager)")],
        [("sophos_enabled", "&Sophos Connect"), ("forti_enabled", "&FortiClient"),
         ("vpn_enabled", "&Weitere VPN-Logs (OpenVPN …)")],
        [("pbx_reader_enabled", "&3CX-Anrufe"), ("itm_reader_enabled", "&ITM-Personalzeiten"),
         ("m42_reader_enabled", "&Matrix42-Buchungen (Firmennetz)"),
         ("outlook_enabled", "&Outlook (Termine, Mails)"), ("teams_calls_enabled", "Tea&ms-Anrufe")],
    ]

    SOURCE_BRANDS = {"teamviewer_enabled": "teamviewer", "rdm_enabled": "rdm", "sophos_enabled": "sophos",
                     "forti_enabled": "forti", "vpn_enabled": "vpn", "pbx_reader_enabled": "pbx",
                     "itm_reader_enabled": "itm", "m42_reader_enabled": "m42", "outlook_enabled": "outlook",
                     "teams_calls_enabled": "teams"}

    def _build_sources_menu(self):
        """Jede Datenquelle als Schalter, die Einrichtung (Pfade, Anmeldung) im Untermenü."""
        menu = QMenu("Daten&quellen", self)
        self.source_actions = {}
        for i, group in enumerate(self.SOURCES):
            if i:
                menu.addSeparator()
            for key, text in group:
                action = menu.addAction(text)
                action.setCheckable(True)
                action.setChecked(bool(self.config.get(key, key not in ("pbx_reader_enabled",
                                                                          "itm_reader_enabled",
                                                                          "m42_reader_enabled",
                                                                          "outlook_enabled",
                                                                          "teams_calls_enabled"))))
                action.toggled.connect(lambda on, k=key: self.toggle_source(k, on))
                action.setIcon(icons.brand_icon(self.SOURCE_BRANDS[key]))
                self.source_actions[key] = action
        menu.addSeparator()
        setup = menu.addMenu("&Einrichten")
        for entry in (("Team&Viewer-Logs …", self.edit_teamviewer_settings, "teamviewer"),
                                  ("&RDM-Logs …", self.edit_rdm_settings, "rdm"),
                                  ("&VPN-Logs …", self.edit_vpn_settings, "vpn"), None,
                                  ("&3CX …", self.open_pbx_settings, "pbx"),
                                  ("&ITM-Personalzeiten …", self.open_itm_settings, "itm"),
                                  ("&Matrix42 …", self.open_m42_settings, "m42"),
                                  ("&Outlook und Teams …", self.open_outlook_settings, "outlook")):
            if entry is None:
                setup.addSeparator()  # Webseiten im Hintergrund
                continue
            text, slot, brand = entry
            setup.addAction(icons.brand_icon(brand), text, slot)
        self._icon_actions += [
            (setup.menuAction(), "settings"),
            (menu.addAction("Einrichtungs&assistent …", self.show_setup_wizard), "spark"),
            (menu.addAction("Alle Datenquellen im &Überblick …", lambda: self.show_settings("sources")), "plug"),
        ]
        return menu

    def show_setup_wizard(self):
        """Alle Datenquellen Schritt für Schritt einrichten (setup_wizard.py)."""
        from setup_wizard import SetupWizard
        self._wizard_open = True
        try:
            wizard = SetupWizard(self)
            wizard.exec()
            wizard.deleteLater()
        finally:
            self._wizard_open = False
        if not self.config.get("setup_done"):
            self.config["setup_done"] = True  # auch nach Abbrechen nicht noch einmal von selbst
            mt.save_config(self.config)
        self.timeline.refresh()

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
        elif key in ("outlook_enabled", "teams_calls_enabled"):
            if on and self.is_paw():
                self.statusBar().showMessage("Outlook und Teams: auf der PAW aus. Daten kommen über "
                                             "„Daten übernehmen“.", 8000)
                self.config[key] = False
                mt.save_config(self.config)
                self.sync_source_actions()
                return
            self.apply_outlook_reader()
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
            f"<b>Zeitzeuge</b><br>Version {full_version()}<br>"
            f"{' · '.join(build_details())}<br><br>"
            "<a href='https://github.com/fkroczak/Zeitzeuge/blob/main/CHANGELOG.md'>Was ist neu?</a>"
            "<br><a href='https://github.com/fkroczak/Zeitzeuge'>github.com/fkroczak/Zeitzeuge</a>"
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
        self._remember_range("day")
        self.timeline.show_whole_day()

    def timeline_work_time(self):
        self._remember_range("work")
        self.timeline.show_work_time()

    def _remember_range(self, value):
        """Zuletzt gewählter Zeitraum gilt beim Start und beim Blättern zum nächsten Tag."""
        if self.config.get("timeline_range", "work") != value:
            self.config["timeline_range"] = value
            mt.save_config(self.config)

    def show_preferred_range(self):
        """Timeline im bevorzugten Zeitraum zeichnen: Arbeitszeit (Standard) oder ganzer Tag."""
        if self.config.get("timeline_range", "work") == "work":
            self.timeline.show_work_time()
        else:
            self.timeline.show_whole_day()

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
        self.update_view_button()
        for action in (self.pc_list_action, self.dark_action, self.pc_blocks_action):
            for proxy in (self._check_proxies.get(action),
                          self._rows_blocks_proxy if action is self.pc_blocks_action else None):
                if proxy is not None:
                    proxy.setData(theme["accent"])
                    proxy.setIcon(icons.check_box(theme["accent"], action.isChecked()))
        self.menu_button.setIcon(icons.icon("settings", theme["bandtext"]))
        self.view_button.setIcon(icons.icon("eye", theme["bandtext"]))
        old_window = getattr(self, "_settings_window", None)
        if old_window is not None:  # Symbole in neuer Farbe: Fenster neu aufbauen
            page = old_window.current_page() if old_window.isVisible() else None
            old_window.hide()
            old_window.deleteLater()
            self._settings_window = None
            if page:
                QTimer.singleShot(0, lambda: self.show_settings(page))
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
            self.update_row_icons()  # Farbpunkte im Menü Ansicht
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
