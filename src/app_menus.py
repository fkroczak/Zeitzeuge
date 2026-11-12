"""Hauptfenster: Werkzeugleiste, Menüs Ansicht und Einstellungen, Design, Einstellungsdialoge, Speicherort.

Teil von TimelineApp (main_timeline.py), nur über main_timeline laden.
"""
import html
import os
import sys

from PySide6.QtCore import QPoint, QProcess, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (QAction, QActionGroup, QColor, QDesktopServices, QIcon, QKeySequence,
                           QPalette)
from PySide6.QtWidgets import (QApplication, QColorDialog, QDateEdit, QDialog, QFileDialog, QLabel, QMenu, QMessageBox,
                               QToolBar, QToolButton, QHBoxLayout, QSizePolicy, QWidget, QWidgetAction)

import datastore
import icons
import storage
import titlebar
from log_parsers import VpnParser
from local_sources import DEFAULT_BROWSER_HISTORY, DEFAULT_RECENT_DIR
from rdp_reader import DEFAULT_LAUNCHER_LOG
from sessionmgmt_reader import DEFAULT_LOG as DEFAULT_SM_LOG
from vpn_reader import DEFAULT_DIRS as VPN_DEFAULT_DIRS, FORTI_TRACE_PATHS, vpn_sources
from settings_dialogs import ActivityTypeSettingsDialog, ConnectionSettingsDialog, WorkHoursDialog
from theme import GERMAN, STYLESHEET, SPACE_XS, default_custom_colors, theme_for
from timeline_only import (COLOR_ROWS, DEFAULT_CALL_COLORS, LEGEND_BANDS, LEGEND_FIXED, ROW_NAMES,
                           TIMELINE_ROWS, entry_color)
from view_help import VIEW_HELP, ViewHelpDialog, help_text
import main_timeline as mt  # Pfade und save_config zur Laufzeit von dort (Tests ersetzen sie dort)


class MenusMixin:
    # ---------------------- Werkzeugleiste ------------------------------------

    def _action(self, text, slot, shortcut=None, tip=None, icon_name=None):
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcuts(shortcut if isinstance(shortcut, list) else [shortcut])
        # Hinweis: Name fett (die Knöpfe zeigen nur ein Symbol), Kürzel, darunter die Erklärung
        label = f"<b>{html.escape(text)}</b>"
        if shortcut:
            first = shortcut[0] if isinstance(shortcut, list) else shortcut
            label += f" ({QKeySequence(first).toString(QKeySequence.NativeText)})"
        if tip and tip != text:
            tip = tip.removeprefix(f"{text}: ")
            label += f"<br>{html.escape(tip[0].upper() + tip[1:])}"
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
        # Nur die Zeile selbst durchsichtig (QWidget#band_row in theme.py), nicht Datum und Knöpfe
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACE_XS)
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
                    button.setAccessibleName(action.text().replace("&", ""))
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
        if hasattr(self, "splitter"):
            QTimer.singleShot(0, self._fit_splitter)  # Timeline wieder so hoch wie ihre Zeilen

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
        theme = theme_for(self.config)
        for k, action in self.view_actions.items():  # Hilfe mit den aktuellen Pausen
            action.setToolTip(help_text(k, self.config))
            action.setStatusTip(help_text(k, self.config))
            # Symbol statt Haken: die aktuelle Ansicht in Akzentfarbe und fett
            action.setIcon(icons.icon(VIEW_HELP[k][0], theme["accent" if k == key else "text"]))
            font = action.font()
            font.setBold(k == key)
            action.setFont(font)
        chips = getattr(self, "view_chips", None)
        if chips is not None:
            chips.set_tips({k: help_text(k, self.config) for k in self.view_actions})

    def show_view_help(self):
        """Erklärung der Ansichten der Tagesliste mit Beispielen."""
        theme = theme_for(self.config)
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
                      "calls": "Tele&fonate",
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
        accent = theme_for(self.config)["accent"]
        # Die Ansichten selbst wählt man über die Chips über der Tagesliste (day_summary.ViewChips);
        # view_actions bleiben als Aktionen ohne Menüeintrag (Einstellungsfenster, Hinweise).
        self._menu_header(menu, "Tagesliste")
        group = QActionGroup(self)
        self.view_actions = {}
        for key, text in self.VIEWS:
            action = QAction(self.VIEW_MNEMONICS.get(key, text), self)
            action.setCheckable(True)
            action.setActionGroup(group)
            action.triggered.connect(lambda _c=False, k=key: self.change_view(k))
            self.view_actions[key] = action
        self._add_check(menu, self.pc_list_action, accent, "PC-&Verlauf in der Liste")
        help_action = menu.addAction("&Was zeigen die Ansichten? …", self.show_view_help)
        help_action.setShortcut(QKeySequence("F1"))
        help_action.setToolTip("Zusammengefasst, Einzeln, Arbeitsblöcke … mit Beispielen erklärt")
        self.addAction(help_action)
        self._icon_actions.append((help_action, "help"))

        # Zeilen der Timeline: eigenes Menü, auch per Rechtsklick auf die Legende links.
        # „PC-Aktivität als Arbeitsblöcke“ steht nur dort (vorher doppelt in diesem Menü).
        self.rows_menu = self._build_rows_menu()
        self._menu_header(menu, "Timeline")
        self._icon_actions.append((menu.addMenu(self.rows_menu), "rows"))

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
        # Tages-/Wochenbericht als PDF (report_pdf.py): eigener Beleg, auch ohne Matrix42-Buchung
        self.report_action = QAction("&Bericht als PDF …", self)
        self.report_action.setToolTip("Tagesbericht des angezeigten Tags als PDF: Tätigkeiten, Zeit ohne "
                                      "Matrix42-Buchung und Spuren als eigener Beleg zum Ausdrucken. "
                                      "Wochenbericht: im Wochenabschluss")
        self.report_action.triggered.connect(lambda: self.save_report())
        menu.addAction(self.report_action)
        self._icon_actions.append((self.report_action, "doc"))
        # Zeitraum (Ganzer Tag, Arbeitszeit) steht in der Werkzeugleiste
        menu.addSeparator()
        # Design: Hell, Dunkel oder eigene Farben. „Dunkles Design“ im Menü
        # Einstellungen und im Einstellungsfenster schaltet zwischen Hell und Dunkel.
        self._ensure_dark_action()
        self._view_dark_proxy = None
        self._menu_header(menu, "Design")
        self.theme_actions = {}
        for key, text in self.THEME_CHOICES:
            if key == "custom":  # wählt eigene Farben und zeigt sie gleich zum Festlegen
                action = menu.addAction(text + " …", self.edit_custom_colors)
            else:
                action = menu.addAction(text)
                action.triggered.connect(lambda _c=False, k=key: self.choose_theme(k))
            self.theme_actions[key] = action
        menu.addSeparator()
        self._icon_actions.append((menu.addAction("Darstellung an&passen …",
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
        accent = theme_for(self.config)["accent"]
        blocks = menu.addAction(self.pc_blocks_action.text())
        blocks.setToolTip(self.pc_blocks_action.toolTip())
        blocks.triggered.connect(self.pc_blocks_action.toggle)
        blocks.setData(accent)
        self.pc_blocks_action.toggled.connect(lambda on, p=blocks: p.setIcon(icons.check_box(p.data(), on)))
        blocks.setIcon(icons.check_box(accent, self.pc_blocks_action.isChecked()))
        self._rows_blocks_proxy = blocks
        # Zeilen abwechselnd grau hinterlegen (früherer Standard) statt feiner Linien
        self.stripes_action = QAction("Zeilen abwechselnd &hinterlegen", self)
        self.stripes_action.setCheckable(True)
        self.stripes_action.setChecked(self.config.get("timeline_stripes", False))
        self.stripes_action.toggled.connect(self.toggle_stripes)
        self._add_check(menu, self.stripes_action, accent)
        menu.addSeparator()
        self.row_actions = {}
        for key, text in TIMELINE_ROWS:
            if key in ("doc", "call", "pcstate"):  # Gruppen: Zeit | Auswertung | Verbindungen | PC
                menu.addSeparator()
            action = QAction(text, self)
            action.setCheckable(True)
            action.setChecked(self.config.get("timeline_rows", {}).get(key, True))
            action.toggled.connect(lambda on, k=key: self.toggle_row(k, on))
            self.row_actions[key] = action
            self._add_check(menu, action, "#4682B4")
        menu.addSeparator()
        self._icon_actions.append((menu.addAction("A&lle Zeilen einblenden", self.show_all_rows), "rows"))
        menu.addAction("&Reihenfolge zurücksetzen", lambda: self.set_row_order(None))
        colors = menu.addMenu("&Farben der Zeilen")
        for key in COLOR_ROWS:
            if key in ("doc", "call", "pcstate"):  # Gruppen wie oben im Menü
                colors.addSeparator()
            if key == "call":  # Telefon: Farbe je Richtung, nicht eine für alle Anrufe
                for direction, text in self.CALL_COLOR_TEXTS:
                    colors.addAction(f"{ROW_NAMES[key]} {text} …",
                                     lambda d=direction: self.choose_call_color(d))
                continue
            colors.addAction(f"{ROW_NAMES[key]} …", lambda k=key: self.choose_row_color(k))
        colors.addSeparator()
        colors.addAction("Alle &Standardfarben", lambda: self.set_row_color(None, None))
        menu.menuAction().setToolTip("Leere Zeilen blendet Zeitzeuge von selbst aus. "
                                     "Verschieben: Zeilenname links anfassen und ziehen.")
        self.update_row_icons()
        return menu

    def set_row_order(self, order):
        """Zeilen der Timeline in dieser Reihenfolge (aus der Legende gezogen); None = Standard."""
        if order:
            self.config["timeline_row_order"] = list(order)
        else:
            self.config.pop("timeline_row_order", None)
        mt.save_config(self.config)
        self.timeline.draw_timeline(self.current_date)

    def toggle_stripes(self, on):
        self.config["timeline_stripes"] = on
        mt.save_config(self.config)
        self.timeline.draw_timeline(self.current_date)

    def show_rows_menu(self, pos, key=""):
        """Rechtsklick auf die Legende der Timeline: Farbe der Zeile darunter, dann alle Zeilen."""
        menu = self.rows_menu
        extra = []
        if key in COLOR_ROWS:  # nur für diesen Aufruf oben einfügen
            name = ROW_NAMES[key]
            if key == "call":
                picks = []
                for direction, text in self.CALL_COLOR_TEXTS:
                    pick = QAction(f"Farbe für Anrufe {text} ändern …", menu)
                    pick.triggered.connect(lambda _c=False, d=direction: self.choose_call_color(d))
                    picks.append(pick)
                own = bool(self.config.get("call_colors"))
            else:
                pick = QAction(f"&Farbe für „{name}“ ändern …", menu)
                pick.triggered.connect(lambda: self.choose_row_color(key))
                picks, own = [pick], False
            default = QAction(f"Standardfarbe für „{name}“", menu)
            default.triggered.connect(lambda: self.set_row_color(key, None))
            default.setEnabled(own or key in (self.config.get("row_colors") or {}))
            sep = QAction(menu)
            sep.setSeparator(True)
            extra = picks + [default, sep]
            first = menu.actions()[0] if menu.actions() else None
            menu.insertActions(first, extra)
        try:
            menu.exec(pos)
        finally:
            for action in extra:
                menu.removeAction(action)

    def row_color(self, key):
        """Farbe, in der die Zeile gerade gezeichnet wird (eigene oder die des Typs)."""
        own = (self.config.get("row_colors") or {}).get(key)
        if own:
            return own
        colors = self.config.get("type_colors", {})
        if key == "call":
            return {**DEFAULT_CALL_COLORS, **self.config.get("call_colors", {})}["Eingehend"]
        if key == "other":
            return colors.get("RDP-Sitzung", "#BB8400")
        legend = LEGEND_BANDS.get(key) or LEGEND_FIXED.get(key)
        return colors.get(legend[1], "#4682B4") if legend else "#4682B4"

    CALL_COLOR_TEXTS = [("Eingehend", "eingehend"), ("Ausgehend", "ausgehend")]

    def call_color(self, direction):
        """Farbe der Anrufe einer Richtung, wie die Timeline sie zeichnet."""
        return entry_color({"type": "Telefonat", "direction": direction}, self.config).name()

    def choose_call_color(self, direction):
        text = dict(self.CALL_COLOR_TEXTS)[direction]
        color = QColorDialog.getColor(QColor(self.call_color(direction)), self, f"Farbe für Anrufe {text}")
        if color.isValid():
            self.set_call_color(direction, color.name())

    def set_call_color(self, direction, color):
        """Eigene Farbe für ein- oder ausgehende Anrufe (config["call_colors"]).

        Eine ältere Farbe der ganzen Zeile Telefon galt für alle Anrufe: sie bleibt für die
        andere Richtung erhalten, damit sich dort nichts ändert."""
        rows = dict(self.config.get("row_colors") or {})
        calls = dict(self.config.get("call_colors") or {})
        old = rows.pop("call", None)
        if old:
            for d, _t in self.CALL_COLOR_TEXTS:
                calls.setdefault(d, old)
        calls[direction] = color
        self.config["call_colors"] = calls
        if rows:
            self.config["row_colors"] = rows
        else:
            self.config.pop("row_colors", None)
        mt.save_config(self.config)
        self.update_row_icons()
        self.timeline.draw_timeline(self.current_date)

    def choose_row_color(self, key):
        color = QColorDialog.getColor(QColor(self.row_color(key)), self, f"Farbe für „{ROW_NAMES[key]}“")
        if color.isValid():
            self.set_row_color(key, color.name())

    def set_row_color(self, key, color):
        """Eigene Farbe einer Zeile (None = Standard); key None = alle zurücksetzen."""
        own = dict(self.config.get("row_colors") or {})
        if key in (None, "call") and not color:
            self.config.pop("call_colors", None)  # Standard: auch die Farben je Richtung
        if key is None:
            own = {}
        elif color:
            own[key] = color
        else:
            own.pop(key, None)
        if own:
            self.config["row_colors"] = own
        else:
            self.config.pop("row_colors", None)
        mt.save_config(self.config)
        self.update_row_icons()
        self.timeline.draw_timeline(self.current_date)  # auch die Tagesliste zeigt die Farben

    def update_row_icons(self):
        """Kästchen je Zeile der Timeline, in der Farbe ihrer Einträge."""
        for key, action in self.row_actions.items():
            color = "#2F7BFF" if key == "pc" else self.row_color(key)
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
        # Mit Windows starten (autostart.py): Schalter im Einstellungsfenster, Stand aus der Registry
        import autostart
        self.autostart_action = QAction("Mit &Windows starten", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(autostart.is_enabled())
        self.autostart_action.setEnabled(autostart.supported())
        self.autostart_action.toggled.connect(self.toggle_autostart)
        self._ensure_dark_action()  # Design wählt man im Menü Ansicht (Hell, Dunkel, Wie Windows)
        # Datenquellen: im Einstellungsfenster (Kacheln mit Zustand); das Untermenü nutzt der Infobereich
        self.sources_menu = self._build_sources_menu()
        self._icon_actions += [
            (menu.addAction("Auf&zeichnung …", lambda: self.show_settings("sources")), "plug"),
            (menu.addAction("&Nachfragen …", self.edit_prompt_settings), "bell"),
        ]
        self._menu_header(menu, "Zuordnung")
        self._icon_actions += [
            (menu.addAction("Kunden&liste …", self.edit_customers), "users"),
            (menu.addAction("&Orte und Fahrzeiten …", self.edit_travel_settings), "map_pin"),
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
        [("teamviewer_enabled", "&TeamViewer"), ("rdm_enabled", "&RDM (Remote Desktop Manager)"),
         ("rdmbetter_enabled", "RDM &Better"), ("sessionmgmt_enabled", "SessionM&GMT")],
        [("mstsc_enabled", "Remote&desktop (mstsc)"),
         ("shell_enabled", "SS&H und PowerShell")],
        [("sophos_enabled", "&Sophos Connect"), ("forti_enabled", "&FortiClient"),
         ("vpn_enabled", "&Weitere VPN-Logs (OpenVPN …)")],
        [("pbx_reader_enabled", "&3CX-Anrufe"), ("itm_reader_enabled", "&ITM-Personalzeiten"),
         ("m42_reader_enabled", "&Matrix42-Buchungen (Firmennetz)")],
        [("outlook_enabled", "&Outlook (Termine, Mails)"), ("teams_calls_enabled", "Tea&ms-Anrufe"),
         ("teams_chats_enabled", "Teams-&Chats")],
        [("pcstate_enabled", "&PC gesperrt / Ruhezustand"), ("wlan_enabled", "&Netzwerk (WLAN, Kabel)"),
         ("recent_files_enabled", "&Zuletzt geöffnete Dateien"), ("browser_enabled", "Bro&wser-Verlauf"),
         ("travel_enabled", "&Fahrten (vermutet)")],
    ]

    SOURCE_BRANDS = {"teamviewer_enabled": "teamviewer", "rdm_enabled": "rdm",
                     "rdmbetter_enabled": "rdmbetter", "sessionmgmt_enabled": "sessionmgmt", "mstsc_enabled": "mstsc", "shell_enabled": "shell",
                     "pcstate_enabled": "pcstate", "wlan_enabled": "wlan", "recent_files_enabled": "files",
                     "browser_enabled": "browser", "sophos_enabled": "sophos",
                     "forti_enabled": "forti", "vpn_enabled": "vpn", "pbx_reader_enabled": "pbx",
                     "itm_reader_enabled": "itm", "m42_reader_enabled": "m42", "outlook_enabled": "outlook",
                     "teams_calls_enabled": "teams", "teams_chats_enabled": "teamschat",
                     "travel_enabled": "travel"}

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
                                                                          "teams_calls_enabled",
                                                                          "teams_chats_enabled"))))
                action.toggled.connect(lambda on, k=key: self.toggle_source(k, on))
                action.setIcon(icons.brand_icon(self.SOURCE_BRANDS[key]))
                self.source_actions[key] = action
        menu.addSeparator()
        setup = menu.addMenu("&Einrichten")
        for entry in (("Team&Viewer-Logs …", self.edit_teamviewer_settings, "teamviewer"),
                      ("&RDM-Logs …", self.edit_rdm_settings, "rdm"),
                      ("RDM &Better …", self.edit_rdmbetter_settings, "rdmbetter"),
                      ("SessionM&GMT …", self.edit_sessionmgmt_settings, "sessionmgmt"), None,
                      ("Remote&desktop (mstsc) …", self.edit_mstsc_settings, "mstsc"),
                      ("SS&H und PowerShell …", self.edit_shell_settings, "shell"), None,
                      ("&Sophos Connect …", self.edit_sophos_settings, "sophos"),
                      ("&FortiClient …", self.edit_forti_settings, "forti"),
                      ("Weitere &VPN-Logs …", self.edit_vpn_settings, "vpn"), None,
                      ("&3CX …", self.open_pbx_settings, "pbx"),
                      ("&ITM-Personalzeiten …", self.open_itm_settings, "itm"),
                      ("&Matrix42 …", self.open_m42_settings, "m42"), None,
                      ("&Outlook …", self.open_outlook_settings, "outlook"),
                      ("Tea&ms-Anrufe …", self.open_teams_settings, "teams"),
                      ("Teams-&Chats …", self.edit_teams_chats_settings, "teamschat"), None,
                      ("&PC gesperrt / Ruhezustand …", self.edit_pcstate_settings, "pcstate"),
                      ("&Netzwerk …", self.edit_wlan_settings, "wlan"),
                      ("&Zuletzt geöffnete Dateien …", self.edit_recent_files_settings, "files"),
                      ("Bro&wser-Verlauf …", self.edit_browser_settings, "browser"),
                      ("&Fahrten: Orte und Fahrzeiten …", self.edit_travel_settings, "travel")):
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
        elif key in ("outlook_enabled", "teams_calls_enabled", "teams_chats_enabled"):
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
        elif key in ("mstsc_enabled", "rdmbetter_enabled"):
            self.apply_mstsc_monitor()
        elif key in self.LOCAL_KEYS:
            self.apply_local_monitor()
        self.timeline.refresh()  # neu einlesen und zeichnen

    def show_about(self):
        """Über Zeitzeuge: Version, Build und Links stehen oben auf der Info-Seite der Einstellungen."""
        return self.show_settings("about")

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

    def toggle_autostart(self, on):
        import autostart
        if autostart.is_enabled() == on:
            return
        if not autostart.set_enabled(on):
            QMessageBox.warning(self, "Mit Windows starten",
                                "Der Autostart ließ sich nicht ändern (Richtlinie oder fehlende Rechte).")
            self.autostart_action.blockSignals(True)
            self.autostart_action.setChecked(autostart.is_enabled())
            self.autostart_action.blockSignals(False)
            return
        self.config["auto_start"] = on
        mt.save_config(self.config)
        self.statusBar().showMessage("Zeitzeuge startet " + ("ab jetzt mit Windows im Infobereich" if on
                                                             else "nicht mehr mit Windows"), 4000)

    def _ensure_dark_action(self):
        """Schalter „Dunkles Design“ (Menüs Ansicht und Einstellungen, Einstellungsfenster)."""
        if getattr(self, "dark_action", None) is None:
            self.dark_action = QAction("&Dunkles Design", self)
            self.dark_action.setCheckable(True)
            self.dark_action.setChecked(self.dark_mode)
            self.dark_action.toggled.connect(self.toggle_dark_mode)
        return self.dark_action

    THEME_CHOICES = [("system", "Wie &Windows"), ("light", "&Hell"), ("dark", "&Dunkel"),
                     ("custom", "&Eigene Farben")]

    @staticmethod
    def windows_dark():
        """Dunkler App-Modus in Windows (Einstellungen → Personalisierung → Farben)."""
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
                return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
        except OSError:
            return False

    def current_theme_key(self):
        if self.config.get("theme_follow_system"):
            return "system"
        colors = self.config.get("custom_colors") or {}
        if self.config.get("custom_theme") and (colors.get("base") == "dark") == bool(self.dark_mode):
            return "custom"
        return "dark" if self.dark_mode else "light"

    def toggle_dark_mode(self, enabled: bool):
        self.set_theme("dark" if enabled else "light")

    def choose_theme(self, key):
        """Design wählen (Menü Ansicht → Design, Einstellungen). Eigene Farben ohne gespeicherte
        Werte: mit den Farben des aktuellen Designs beginnen und gleich zum Festlegen zeigen."""
        if key == "custom" and not self.config.get("custom_colors"):
            self.edit_custom_colors()
        else:
            self.set_theme(key)

    def edit_custom_colors(self):
        """Eigene Farben festlegen: Einstellungen → Darstellung, unter der Kachel „Eigene Farben“."""
        if self.current_theme_key() != "custom":
            if not self.config.get("custom_colors"):
                self.config["custom_colors"] = default_custom_colors("dark" if self.dark_mode else "light")
            self.set_theme("custom")
        window = self.show_settings("view")
        window.show_custom_colors()
        return window

    def set_theme(self, key, save=True):
        """Design wechseln: "light", "dark" oder "custom" (config["custom_colors"])."""
        self.config["theme_follow_system"] = key == "system"
        if key == "system":
            dark = self.windows_dark()
            self.config["custom_theme"] = False
        elif key == "custom":
            colors = self.config.get("custom_colors") or {}
            dark = colors.get("base") == "dark"
            self.config["custom_theme"] = True
        else:
            dark = key == "dark"
            self.config["custom_theme"] = False
        self.dark_mode = dark
        self.config["dark_mode"] = dark
        action = getattr(self, "dark_action", None)
        if action is not None and action.isChecked() != dark:
            action.blockSignals(True)  # nur den Haken nachziehen, nicht erneut umschalten
            action.setChecked(dark)
            action.blockSignals(False)
            proxy = self._check_proxies.get(action)
            if proxy is not None:
                proxy.setIcon(icons.check_box(proxy.data(), dark))
        if save:
            mt.save_config(self.config)
        self.apply_style()

    def update_title_bars(self):
        """Windows: Titelleisten aller offenen Fenster passend zum Design (titlebar.py).
        Neue Fenster (Dialoge) bekommen sie, sobald sie aktiv werden."""
        app = QApplication.instance()
        if not getattr(self, "_title_bar_hooked", False):
            self._title_bar_hooked = True
            app.focusWindowChanged.connect(self._window_activated)
        for widget in app.topLevelWidgets():
            # nur schon erzeugte Fenster (internalWinId), Menüs und Hinweise haben keine Titelleiste
            if widget.internalWinId() and widget.windowType() in (Qt.Window, Qt.Dialog):
                titlebar.apply(widget.internalWinId(), self.dark_mode)

    def _window_activated(self, window):
        if window is None:
            return
        # „Wie Windows“: hat jemand Windows zwischendurch umgestellt, beim nächsten Aktivieren folgen
        if self.config.get("theme_follow_system") and self.windows_dark() != bool(self.dark_mode):
            self.set_theme("system")
        titlebar.apply(window.winId(), self.dark_mode)

    def apply_style(self):
        theme = theme_for(self.config)
        sheet = STYLESHEET
        tokens = {**theme, "checkmark": icons.check_mark_file(theme["onaccent"]), **icons.switch_tokens(theme)}
        for key in sorted(tokens, key=len, reverse=True):  # $bandtext vor $band ersetzen
            sheet = sheet.replace(f"${key}", tokens[key])
        # Palette passend setzen, sonst nutzen Tabellen/Scrollbars die Systemfarben
        pal = QPalette()
        for role, key in [(QPalette.Window, "bg"), (QPalette.WindowText, "text"),
                          (QPalette.Base, "surface"), (QPalette.AlternateBase, "alt"),
                          (QPalette.Text, "text"), (QPalette.Button, "bar"),
                          (QPalette.ButtonText, "text"), (QPalette.Highlight, "sel"),
                          (QPalette.HighlightedText, "seltext"),
                          (QPalette.ToolTipBase, "surface"), (QPalette.ToolTipText, "text"),
                          (QPalette.PlaceholderText, "muted"),
                          (QPalette.Link, "accent"), (QPalette.LinkVisited, "accent"),
                          (QPalette.Accent, "accent")]:  # Qt 6 nutzt Accent statt Highlight
            pal.setColor(role, QColor(theme[key]))
        self.setStyleSheet("")  # alte Farben vollständig entfernen
        QApplication.instance().setPalette(pal)
        self.setStyleSheet(sheet)
        self.update_title_bars()
        # Symbole im farbigen Band oben in dessen Schriftfarbe, in Menüs in der normalen
        for action, name in self._icon_actions:
            in_menu = any(isinstance(o, QMenu) for o in action.associatedObjects())
            action.setIcon(icons.icon(name, theme["text" if in_menu else "bandtext"]))
        if getattr(self, "tray_record", None):  # Eintrag Aufzeichnung im Infobereich
            self.tray_record.set_state(self.tracker is not None, theme)
        self.update_view_button()
        current = self.current_theme_key()
        for key, action in getattr(self, "theme_actions", {}).items():
            # Punkt in Akzentfarbe und fett am aktuellen Design (wie die Ansichten der Tagesliste)
            action.setIcon(icons.dot(theme["accent"]) if key == current else QIcon())
            font = action.font()
            font.setBold(key == current)
            action.setFont(font)
        for action in (self.pc_list_action, self.dark_action, self.pc_blocks_action):
            for proxy in (self._check_proxies.get(action),
                          self._rows_blocks_proxy if action is self.pc_blocks_action else None,
                          self._view_dark_proxy if action is self.dark_action else None):
                if proxy is not None:
                    proxy.setData(theme["accent"])
                    proxy.setIcon(icons.check_box(theme["accent"], action.isChecked()))
        self.menu_button.setIcon(icons.icon("settings", theme["bandtext"]))
        self.view_button.setIcon(icons.icon("eye", theme["bandtext"]))
        settings = getattr(self, "_settings_window", None)
        if settings is not None:  # Symbole in neuer Farbe; das Fenster bleibt, wie es ist
            settings.retheme()
        self.busy_bar.set_color(theme["muted"])  # Ladebalken dunkelgrau, nicht in Akzentfarbe
        self.update_tracking_state()
        self.timeline.set_dark_mode(self.dark_mode)

    # ---------------------- Einstellungen / Dialoge ---------------------------

    def _edit_log_settings(self, key, default_path, title, after=None, **options):
        """Einrichtungsfenster einer Datenquelle: eigener Schalter, Pfade, Zeitzone."""
        defaults = default_path if isinstance(default_path, list) else [default_path]
        options.setdefault("enabled_text", "Diese Datenquelle auslesen und anzeigen")
        dialog = ConnectionSettingsDialog(
            self.config, key, [os.path.expandvars(p) for p in defaults], title, self, **options
        )
        if dialog.exec() == QDialog.Accepted:
            self.config.update(dialog.values())
            mt.save_config(self.config)
            self.sync_source_actions()
            if after:
                after()
            self.timeline.refresh()

    def edit_teamviewer_settings(self):
        self._edit_log_settings(
            "teamviewer", r"%APPDATA%\TeamViewer\Connections.txt",
            "TeamViewer-Logeinstellungen",
            enabled_text="TeamViewer-Verbindungen auslesen und anzeigen",
            utc_auto_key="teamviewer_utc_auto",
        )

    def edit_rdm_settings(self):
        self._edit_log_settings(
            "rdm", r"%LOCALAPPDATA%\Devolutions\RemoteDesktopManager\Connections.log",
            "RDM-Logeinstellungen",
            enabled_text="RDM-Sitzungen auslesen und anzeigen",
        )

    def edit_rdmbetter_settings(self):
        self._edit_log_settings(
            "rdmbetter", DEFAULT_LAUNCHER_LOG, "RDM Better",
            enabled_text="Starts aus RDM Better auslesen und anzeigen",
            timezone=False,
            hint="RDM Better schreibt in launcher.log nur, wann du eine Verbindung startest "
                 "(Zeit in UTC, Zeitzeuge rechnet sie in Ortszeit um). Das Ende erkennt Zeitzeuge "
                 "am Fenster der Remotedesktopverbindung (mstsc), das es dafür alle 30 Sekunden "
                 "prüft. Findet es keins, steht ein Start 1 Minute in der Timeline.",
            after=self.apply_mstsc_monitor,
        )

    def edit_sessionmgmt_settings(self):
        self._edit_log_settings(
            "sessionmgmt", DEFAULT_SM_LOG, "SessionMGMT",
            enabled_text="Sitzungen aus SessionMGMT auslesen und anzeigen",
            timezone=False,
            hint="SessionMGMT schreibt jede Sitzung in sessions.log im Datenordner: RDP, SSH, VPN "
                 "und Web mit Kunde (Tresor), Eintrag, Ziel, Benutzer, Beginn und Ende (Zeit in UTC, "
                 "Zeitzeuge rechnet sie in Ortszeit um). Einen anderen Datenordner aus dem Installer "
                 "(SessionMGMT.json) findet Zeitzeuge selbst.\n\n"
                 "Zeigen mstsc, PuTTY oder das VPN-Log dieselbe Sitzung, steht sie nur einmal da: "
                 "RDP und SSH mit dem Kunden aus SessionMGMT, VPN mit den Zeiten aus dem VPN-Log. "
                 "Web-Einträge haben kein Ende und stehen 1 Minute in der Timeline.",
        )

    def edit_mstsc_settings(self):
        self._edit_log_settings(
            "mstsc", [], "Remotedesktop (mstsc)",
            enabled_text="Remotedesktop-Verbindungen (mstsc) aufzeichnen",
            checks=[("mstsc_events_enabled", "Auch aus dem Windows-Ereignisprotokoll lesen", True)],
            paths=False, timezone=False,
            hint="Zeitzeuge prüft alle 30 Sekunden, welche Remotedesktopverbindungen (mstsc.exe) "
                 "offen sind, und speichert Beginn, Ende und Ziel (z. B. DC01 oder 10.10.80.35). "
                 "Sie stehen in der Timeline wie die Verbindungen aus RDM. Auch Starts aus "
                 "RDM Better bekommen so ihr Ende.\n\n"
                 "Das Ereignisprotokoll des RDP-Clients (TerminalServices-RDPClient/Operational) "
                 "kennt Aufbau und Trennung jeder Verbindung sekundengenau, auch aus Zeiten, in "
                 "denen Zeitzeuge nicht lief. Windows hält es nur einige Wochen.",
            after=self.apply_mstsc_monitor,
        )

    def edit_shell_settings(self):
        self._edit_log_settings(
            "shell", [], "SSH und PowerShell",
            enabled_text="SSH- und PowerShell-Fernsitzungen aufzeichnen",
            paths=False, timezone=False,
            hint="Zeitzeuge prüft alle 30 Sekunden, welche Sitzungen offen sind: ssh.exe, PuTTY, "
                 "KiTTY, plink, WinSCP und PowerShell mit Enter-PSSession oder -ComputerName in "
                 "der Befehlszeile. Gespeichert werden Ziel, Beginn und Ende. Sie stehen in der "
                 "Timeline bei den Verbindungen wie RDM.",
            after=self.apply_local_monitor,
        )

    def edit_pcstate_settings(self):
        self._edit_log_settings(
            "pcstate", [], "PC gesperrt / Ruhezustand",
            enabled_text="Sperren, Ruhezustand, Ausschalten und Abmelden anzeigen",
            paths=False, timezone=False,
            hint="Gesperrt: Zeitzeuge prüft alle 30 Sekunden selbst, ob der Bildschirm gesperrt ist. "
                 "Ruhezustand, ausgeschaltet und abgemeldet liest es aus dem Windows-"
                 "Ereignisprotokoll „System“, auch für Zeiten, in denen Zeitzeuge nicht lief "
                 "(14 Tage zurück). Alles steht in der Zeile „PC-Zustand“.",
            after=self.apply_local_monitor,
        )

    def edit_wlan_settings(self):
        self._edit_log_settings(
            "wlan", [], "Netzwerk",
            enabled_text="Verbundene Netzwerke aufzeichnen (WLAN und Kabel)",
            paths=False, timezone=False,
            hint="Zeitzeuge merkt sich alle 2 Minuten, mit welchem Netzwerk der PC verbunden ist: den "
                 "Namen, den Windows dem Netz gibt (beim WLAN der WLAN-Name, im Firmennetz meist die "
                 "Domäne), auch über Kabel und Dockingstation. VPN-Adapter zählen nicht. So siehst du "
                 "in der Zeile „Netzwerk“, ob du im Büro, im Homeoffice oder beim Kunden warst. "
                 "Rechtsklick auf ein Netz → „Kunde merken“ ordnet es einem Kunden zu.",
            after=self.apply_local_monitor,
        )

    def edit_recent_files_settings(self):
        self._edit_log_settings(
            "recent_files", [DEFAULT_RECENT_DIR], "Zuletzt geöffnete Dateien",
            enabled_text="Zuletzt geöffnete Dateien anzeigen",
            paths_key="recent_files_dirs", path_title="Ordner mit Verknüpfungen",
            files=False, folders=True, timezone=False,
            hint="Windows legt für jede geöffnete Datei eine Verknüpfung im Ordner „Recent“ an. "
                 "Zeitzeuge liest daraus Dateiname und Uhrzeit (alle 2 Minuten) und hebt sie auf, "
                 "auch wenn Windows die Liste kürzt. Inhalte liest es nicht.",
            after=self.apply_local_monitor,
        )

    def edit_browser_settings(self):
        self._edit_log_settings(
            "browser", list(DEFAULT_BROWSER_HISTORY), "Browser-Verlauf",
            enabled_text="Browser-Verlauf auswerten (nur Domains und Ticketnummern)",
            path_title="Verlauf-Dateien (Edge, Chrome)", timezone=False,
            hint="Zeitzeuge liest alle 2 Minuten den Verlauf von Edge und Chrome (14 Tage zurück) und "
                 "behält davon nur die Domain (z. B. „kunde.de“) und Ticketnummern aus Adresse oder "
                 "Titel. Adressen und Seitentitel speichert es nicht. Aufrufe derselben Domain mit "
                 "weniger als 5 Minuten Pause sind ein Block. Suchmaschinen und Anmeldeseiten "
                 "fallen weg (browser_ignore_domains in der zeitzeuge_config.json).",
            after=self.apply_local_monitor,
        )

    def edit_teams_chats_settings(self):
        if self.is_paw():
            self.statusBar().showMessage("Teams-Chats: auf der PAW aus.", 8000)
            return
        self._edit_log_settings(
            "teams_chats", [], "Teams-Chats",
            enabled_text="Teams-Chats aus dem Postfach lesen (über Outlook)",
            paths=False, timezone=False,
            hint="Exchange legt jede Teams-Nachricht auch in deinem Postfach ab. Zeitzeuge liest sie "
                 "über das klassische Outlook (wie Termine und Mails, Outlook muss dafür nicht als "
                 "Datenquelle an sein) und behält nur Uhrzeit, ob die Nachricht von dir war, und die "
                 "Domains der Gesprächspartner (z. B. „kunde.de“). Keine Texte, keine Namen. "
                 "Nachrichten mit derselben Firma und weniger als 10 Minuten Pause sind ein Block "
                 "„Chat mit kunde.de“ in der Zeile Outlook. Standardmäßig nur Chats mit anderen Firmen "
                 "(teams_chats_external_only).",
            after=self.apply_outlook_reader,
        )

    def edit_travel_settings(self):
        from travel_dialogs import TravelSettingsDialog
        dialog = TravelSettingsDialog(self.config, self.known_customers(), self)
        if dialog.exec() == QDialog.Accepted:
            self.config.update(dialog.values())
            mt.save_config(self.config)
            self.sync_source_actions()
            self.timeline.refresh()

    def edit_sophos_settings(self):
        self._edit_log_settings(
            "sophos", list(VPN_DEFAULT_DIRS), "Sophos Connect",
            enabled_text="Sophos-Connect-Verbindungen auslesen und anzeigen",
            paths_key="sophos_connect_dirs", path_title="Ordner von Sophos Connect",
            files=False, folders=True, timezone=False,
            hint="Zeitzeuge liest scvpn.log und scgui.log aus dem Programmordner von Sophos "
                 "Connect, mit dem Namen, den du der Verbindung gegeben hast. Zusätzlich prüft "
                 "es alle 30 Sekunden, ob der Sophos-Adapter verbunden ist.",
            after=self.apply_vpn_settings,
        )

    def edit_forti_settings(self):
        self._edit_log_settings(
            "forti", list(FORTI_TRACE_PATHS), "FortiClient",
            enabled_text="FortiClient-Verbindungen auslesen und anzeigen",
            path_title="Logdateien von FortiClient", timezone=False,
            hint="Zeitzeuge liest FortiVPN_1.log aus logs\\trace von FortiClient: jede Verbindung "
                 "mit ihrem Namen aus FortiClient (z. B. „Tenbrink“), Beginn und Ende. Ruhezustand "
                 "beendet eine Verbindung. Fehlt die Datei, nimmt es die Adapter-Meldungen aus "
                 "charon.log von Sophos Connect. Zusätzlich prüft es alle 30 Sekunden, ob der "
                 "Fortinet-Adapter verbunden ist. * im Pfad steht für beliebige Zeichen.",
            after=self.apply_vpn_settings,
        )

    def edit_vpn_settings(self):
        self._edit_log_settings(
            "vpn", VpnParser().default_paths, "Weitere VPN-Logs (OpenVPN …)",
            enabled_text="Diese VPN-Logs auslesen und anzeigen",
            folders=True,
            hint="Logdateien oder Ordner deiner VPN-Clients, z. B. OpenVPN GUI "
                 "(%USERPROFILE%\\OpenVPN\\log), OpenVPN Connect oder Sophos SSL VPN. "
                 "Bei einem Ordner zählen alle .log- und .txt-Dateien darin, "
                 "der Dateiname wird zum Verbindungsnamen. Sophos Connect und FortiClient "
                 "haben eigene Fenster.",
        )

    def apply_vpn_settings(self):
        """Sophos-/FortiClient-Einstellungen an den VPN-Leser geben."""
        vpn = self.timeline.vpn_reader
        vpn.dirs = self.config.get("sophos_connect_dirs") or VPN_DEFAULT_DIRS
        vpn.forti_paths = self.config.get("forti_paths") or FORTI_TRACE_PATHS
        vpn.sources = vpn_sources(self.config)
        vpn._sig = None  # neu lesen
        self.apply_vpn_monitor()

    def edit_work_hours(self):
        dialog = WorkHoursDialog(self.config, self)
        if dialog.exec() == QDialog.Accepted:
            self.config["work_days"] = dialog.get_work_days()
            self.config["work_breaks"] = dialog.get_work_breaks()
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
        new_dir = os.path.normpath(new_dir) if new_dir else new_dir  # Qt liefert / statt Backslash
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
