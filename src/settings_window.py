"""Fenster „Einstellungen“: Bereiche links, Suche oben, Datenquellen als Kacheln mit Zustand.

Alles wirkt sofort: Schalter sind dieselben Aktionen wie im Hauptfenster (Menü, Infobereich),
Zahlen werden gleich gespeichert, „Ändern …“ öffnet die bisherigen Dialoge. Die Bereiche
stehen in PAGES und ROWS; die Suche geht über Titel, Beschreibung und Bereich jeder Zeile.

Teil von TimelineApp (main_timeline.py): SettingsWindow(main) bekommt das Hauptfenster.
"""
import os

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
                               QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

import icons
from theme import THEMES, prose
import main_timeline as mt  # Pfade und save_config zur Laufzeit von dort (Tests ersetzen sie dort)

# Bereiche: Schlüssel, Name, Symbol, Satz darunter
PAGES = [
    ("general", "Allgemein", "settings", "Arbeitszeiten und Pausen."),
    ("view", "Ansicht", "eye", "Timeline, Tagesliste und Aussehen."),
    ("sources", "Datenquellen", "plug", "Woher Zeitzeuge deine Spuren liest. Schalter und Zustand je Quelle."),
    ("prompts", "Nachfragen & Grenzwerte", "bell", "Wann Zeitzeuge nachfragt und ab welchen Minuten."),
    ("rules", "Zuordnung & KI", "rules", "Regeln ohne KI und KI-Vorschläge."),
    ("booking", "Matrix42 & Abrechnung", "gauge", "Buchen, Abrechnungstakt und Buchungsquote."),
    ("customers", "Kunden & Texte", "users", "Kundenliste mit Spuren und Textbausteine."),
    ("data", "Daten & Schutz", "shield", "Speicherort, PIN, Löschen, Übernehmen von einem anderen PC."),
    ("debug", "Fehlersuche & Analyse", "search", "Für tiefergehende Analysen, im Alltag nicht nötig: "
     "aufzeichnen, wie 3CX, Matrix42 und ITM mit ihrem Server reden, z. B. wenn nach einem Update "
     "etwas nicht mehr gelesen wird. Passwörter und Token werden geschwärzt, die Dateien landen im Datenordner."),
    ("about", "Über Zeitzeuge", "info", "Version und Beenden."),
]


def _prompt_summary(main):
    c = main.config
    mode = {"window": "Fenster", "tray": "Infobereich", "off": "aus"}.get(c.get("prompt_mode", "window"))
    return f"{mode} · später nach {c.get('prompt_snooze_minutes', 15)} min"


def _billing_summary(main):
    c = main.config
    if c.get("billing_mode", "up") == "off":
        return "echte Dauer"
    return f"{c.get('billing_step_minutes', 15)}-Minuten-Takt"


# Zeilen: (Bereich, Art, Symbol, Titel, Beschreibung, Ziel, Zusatz)
#   toggle: Ziel = Name einer QAction am Hauptfenster
#   button: Ziel = Methode am Hauptfenster (oder Funktion main -> None), Zusatz = Wert-Funktion
#   spin:   Ziel = Config-Schlüssel, Zusatz = (min, max, Einheit, Text bei 0, Nachlauf)
#   check:  Ziel = Config-Schlüssel, Zusatz = Standardwert
#   choice: Ziel = Config-Schlüssel, Zusatz = ([(Wert, Text)] oder Funktion main -> Liste, Nachlauf)
ROWS = [
    ("general", "button", "clock", "Arbeitszeiten", "Arbeitstage und Zeiten, wenn keine ITM-Personalzeit da ist.",
     "edit_work_hours", None),
    # Ein/Aus und Fenster-Filter stehen auf der Kachel „Aktive Fenster“ (SOURCE_TILES), hier nur der Rest
    ("sources", "spin", "pause", "Leerlauf nach", "Ohne Maus und Tastatur zeichnet Zeitzeuge nichts auf.",
     "tracking_idle_minutes", (1, 60, "min", "", "idle_limit")),

    # Ansicht: alles, was nur die Darstellung ändert (mit Vorschau, settings_preview.py)
    ("view", "toggle", "moon", "Dunkles Design", "Helles oder dunkles Aussehen, gilt sofort.",
     "dark_action", None),
    ("view", "choice", "layers", "Tagesliste", "Wie die Liste unter der Timeline die Einträge zeigt (F1 erklärt alle).",
     "list_view", (lambda main: [(k, t) for k, t in main.VIEWS], "view")),
    ("view", "toggle", "monitor", "PC-Verlauf in der Liste", "Arbeitsblöcke am PC auch in der Tagesliste zeigen.",
     "pc_list_action", None),
    ("view", "toggle", "blocks", "PC-Aktivität als Arbeitsblöcke",
     "Fenster zu Blöcken je Tätigkeit zusammenfassen statt jedes Fenster einzeln zu zeigen. "
     "Auch im Menü Ansicht und per Rechtsklick auf die Legende der Timeline.",
     "pc_blocks_action", None),
    ("view", "spin", "layers", "Kurze Sprünge bis",
     "Kürzere Wechsel zählen zur Haupttätigkeit, wenn es danach dort weitergeht oder der Kunde passt.",
     "pc_jump_seconds", (0, 600, "s", "aus", "redraw")),
    ("view", "choice", "clock", "Timeline beim Start",
     "Zeitraum beim Start und beim Blättern zum nächsten Tag.",
     "timeline_range", ([("work", "Arbeitszeit"), ("day", "Ganzer Tag")], "range")),
    ("view", "button", "rows", "Zeilen der Timeline",
     "Jede Zeile ein- oder ausblenden. Leere Zeilen blendet Zeitzeuge von selbst aus.",
     lambda main: main.rows_menu.exec(QCursor.pos()), None),

    ("sources", "button", "spark", "Einrichtungsassistent", "Alle Quellen Schritt für Schritt neu einrichten.",
     "show_setup_wizard", None),

    ("prompts", "button", "bell", "Nachfragen und Erinnerungen",
     "Fenster oder Infobereich, wonach gefragt wird, Erinnerung bei Feierabend und Beenden.",
     "edit_prompt_settings", _prompt_summary),
    ("prompts", "spin", "clock", "Abwesenheit am PC: fragen ab",
     "Nach so vielen Minuten ohne Eingabe fragt Zeitzeuge bei der Rückkehr, was war.",
     "idle_prompt_minutes", (0, 240, "min", "aus", "idle_watch")),
    ("prompts", "spin", "pause", "„Später fragen“ nach", "So lange wartet eine zurückgestellte Nachfrage.",
     "prompt_snooze_minutes", (1, 480, "min", "", None)),
    ("view", "spin", "layers", "Zusammenfassen bis Pause",
     "Ansicht „Zusammengefasst“: gleiche Verbindungen mit kürzerer Pause werden eine Zeile.",
     "merge_gap_minutes", (0, 120, "min", "nie", "redraw")),
    ("view", "spin", "blocks", "Arbeitsblock bis Pause",
     "Ansicht „Arbeitsblöcke“: alles mit kürzerer Pause wird ein Block.",
     "block_gap_minutes", (1, 240, "min", "", "redraw")),
    ("view", "spin", "monitor", "Gesendete Mail als Block",
     "So breit steht eine gesendete Mail in der Timeline (Outlook).",
     "outlook_mail_minutes", (1, 60, "min", "", "redraw")),

    ("rules", "button", "rules", "Zuordnung ohne KI (Regeln)", "Feste Regeln: Programm oder Verbindung → Kategorie und Kunde.",
     "edit_rules", None),
    ("rules", "button", "spark", "KI-Vorschläge", "Modell, Schlüssel und Kategorien für Claude.",
     "edit_ai_settings", None),
    ("view", "button", "palette", "Aktivitätstypen und Farben", "Farbe je Art in der Timeline.",
     "edit_activity_types", None),

    ("booking", "button", "gauge", "Matrix42 einrichten", "Adresse der Kalenderseite und Anmeldung (nur im Firmennetz).",
     "open_m42_settings", None),
    ("booking", "button", "tag", "Abrechnung", "Abrechnungstakt, auch je Kunde.", "edit_billing", _billing_summary),
    ("booking", "spin", "gauge", "Ziel Buchungsquote", "So viel der Personalzeit soll in Matrix42 gebucht sein.",
     "booking_target_percent", (10, 150, "%", "", "redraw")),
    ("booking", "check", "details", "Quote in der Statuszeile", "„Quote heute 72 % · 7 Tage 81 %“ unten anzeigen.",
     "booking_rate_status", True),
    ("booking", "check", "alert", "Bei Feierabend prüfen",
     "Pausen, Stempelung, Buchungen außerhalb der Personalzeit, Quote unter Ziel.", "day_checks_enabled", True),

    ("customers", "button", "users", "Kundenliste", "Kunden mit ihren Spuren (TeamViewer-ID, RDM, VPN, Telefon, Domain).",
     "edit_customers", None),
    ("customers", "button", "edit", "Textbausteine", "Bausteine und Ticket-Format beim Eintragen.",
     "edit_snippets", None),

    ("data", "button", "folder", "Datenordner öffnen", "Ordner mit Einstellungen und Sicherung im Explorer zeigen.",
     lambda main: QDesktopServices.openUrl(QUrl.fromLocalFile(mt.DATA_DIR)),
     lambda _m: os.path.normpath(mt.DATA_DIR)),
    ("data", "button", "folder", "Speicherort ändern", "Daten in einen anderen Ordner verschieben (startet neu).",
     "change_data_dir", None),
    ("data", "button", "lock", "Schutz", "PIN beim Start und Wiederherstellungsschlüssel.", "show_protection", None),
    ("data", "button", "trash", "PC-Verlauf automatisch löschen", "Aufgezeichnete Fenster nach einigen Tagen löschen.",
     lambda main: main.retention.edit(),
     lambda m: f"nach {m.config.get('pc_history_days', 90)} Tagen" if m.config.get("pc_history_purge") else "aus"),
    ("data", "button", "upload", "Daten exportieren", "Für einen anderen PC, z. B. die PAW.", "export_data", None),
    ("data", "button", "download", "Daten übernehmen", "Von einem anderen PC einlesen.", "import_data", None),
    ("data", "toggle", "server", "Dieser PC ist eine PAW", "Nur RDM sammeln, alles andere aus.", "paw_action", None),

    ("debug", "button", "record", "3CX: Abfragen mitschneiden",
     "Edge-Fenster mit dem 3CX-Webclient öffnen und aufzeichnen, was die Seite abfragt.",
     lambda main: main.record_source("pbx"), None),
    ("debug", "button", "phone", "3CX: Direkt-Abfrage prüfen",
     "Anrufe ohne Webseite direkt vom 3CX-Server holen und mit der gespeicherten Anrufliste vergleichen.",
     "check_pbx_direct", None),
    ("debug", "button", "record", "Matrix42: Abfragen mitschneiden",
     "Edge-Fenster mit dem Matrix42-Kalender öffnen und aufzeichnen, was die Seite abfragt.",
     lambda main: main.record_source("m42"), None),
    ("debug", "button", "record", "Matrix42: Buchung mitschneiden",
     "Aufzeichnen, wie Matrix42 eine Zeiterfassung speichert. Du legst dabei selbst eine Buchung an.",
     lambda main: main.record_source("m42", booking=True), None),
    ("debug", "button", "record", "ITM: Abfragen mitschneiden",
     "Edge-Fenster mit der ITM-Zeiterfassung öffnen und aufzeichnen, was die Seite abfragt.",
     lambda main: main.record_source("itm"), None),
    ("debug", "button", "folder", "Datenordner öffnen", "Dort liegen die Mitschnitte (mitschnitt_…json).",
     lambda main: QDesktopServices.openUrl(QUrl.fromLocalFile(mt.DATA_DIR)), None),

    ("about", "button", "info", "Über Zeitzeuge", "Version, Neuigkeiten und Projektseite.", "show_about", None),
    ("about", "button", "power", "Zeitzeuge beenden", "Aufzeichnung und Datenquellen stoppen.",
     lambda main: _confirm_quit(main), None),
]

# Beschriftung des Knopfs je Zeile (sonst „Öffnen …“). „…“ nur, wenn noch ein Fenster kommt.
BUTTON_TEXT = {
    "Datenordner öffnen": "Im Explorer zeigen",
    "Speicherort ändern": "Ändern …",
    "Daten exportieren": "Exportieren …",
    "Daten übernehmen": "Übernehmen …",
    "3CX: Abfragen mitschneiden": "Mitschneiden …",
    "Matrix42: Abfragen mitschneiden": "Mitschneiden …",
    "Matrix42: Buchung mitschneiden": "Mitschneiden …",
    "ITM: Abfragen mitschneiden": "Mitschneiden …",
    "Zeitzeuge beenden": "Beenden …",
}


def _confirm_quit(main):
    """Beenden aus den Einstellungen erst nach Rückfrage (ein Klick daneben soll nichts stoppen)."""
    box = QMessageBox(QMessageBox.Question, "Zeitzeuge beenden",
                      "Zeitzeuge beenden? Aufzeichnung und Datenquellen stoppen dann.",
                      parent=main._settings_window if getattr(main, "_settings_window", None) else main)
    quit_button = box.addButton("&Beenden", QMessageBox.AcceptRole)
    box.addButton("Abbre&chen", QMessageBox.RejectRole)
    box.setDefaultButton(quit_button)
    box.exec()
    if box.clickedButton() is quit_button:
        main.request_quit()

# Datenquellen als Kacheln: (Schalter, Zeichen, Name, Beschreibung, Einrichten, Zustand)
#   Schalter: Schlüssel in main.source_actions, "tracking" = Aufzeichnung der Fenster
#   Zustand: ("log", Name in missing_sources) oder ("reader", Attribut am Hauptfenster) oder None
SOURCE_TILES = [
    ("teamviewer_enabled", "teamviewer", "TeamViewer", "Verbindungen aus Connections.txt",
     "edit_teamviewer_settings", ("log", "TeamViewer")),
    ("rdm_enabled", "rdm", "Remote Desktop Manager", "Sitzungen und Passwort-Anzeigen",
     "edit_rdm_settings", ("log", "RDM")),
    ("rdmbetter_enabled", "rdmbetter", "RDM Better", "Starts aus launcher.log",
     "edit_rdmbetter_settings", ("log", "RDM Better")),
    ("mstsc_enabled", "mstsc", "Remotedesktop (mstsc)", "RDP-Fenster und Ereignisprotokoll",
     "edit_mstsc_settings", None),
    ("shell_enabled", "shell", "SSH und PowerShell", "ssh, PuTTY, WinSCP, PSSession",
     "edit_shell_settings", None),
    ("sophos_enabled", "sophos", "Sophos Connect", "VPN-Verbindungen mit Namen", "edit_sophos_settings", None),
    ("forti_enabled", "forti", "FortiClient", "VPN-Zeiten aus den FortiClient-Logs", "edit_forti_settings", None),
    ("vpn_enabled", "vpn", "Weitere VPN-Logs", "OpenVPN und andere Clients", "edit_vpn_settings", None),
    ("pbx_reader_enabled", "pbx", "3CX-Telefonate", "Anrufliste aus dem Webclient", "open_pbx_settings",
     ("reader", "pbx_reader")),
    ("itm_reader_enabled", "itm", "ITM-Personalzeiten", "Gestempelte Zeiten und Pausen", "open_itm_settings",
     ("reader", "itm_reader")),
    ("m42_reader_enabled", "m42", "Matrix42", "Gebuchte Zeiten (Firmennetz)", "open_m42_settings",
     ("reader", "m42_reader")),
    ("outlook_enabled", "outlook", "Outlook", "Termine und gesendete Mails", "open_outlook_settings", None),
    ("teams_calls_enabled", "teams", "Teams-Anrufe", "Anrufe aus Microsoft Teams", "open_teams_settings", None),
    ("teams_chats_enabled", "teamschat", "Teams-Chats", "Nur Zeit und Firma, über Outlook",
     "edit_teams_chats_settings", None),
    ("pcstate_enabled", "pcstate", "PC gesperrt / Ruhezustand", "Sperren, Schlafen, Aus, Abmelden",
     "edit_pcstate_settings", None),
    ("wlan_enabled", "wlan", "Netzwerk", "WLAN und Kabel, alle 2 Minuten", "edit_wlan_settings", None),
    ("recent_files_enabled", "files", "Zuletzt geöffnete Dateien", "Dateiname und Uhrzeit",
     "edit_recent_files_settings", None),
    ("browser_enabled", "browser", "Browser-Verlauf", "Nur Domains und Tickets", "edit_browser_settings", None),
    ("travel_enabled", "travel", "Fahrten (vermutet)", "Termine mit Ort, Kundennetze", "edit_travel_settings", None),
    ("tracking", "tracking", "Aktive Fenster", "Band „PC“, alle 5 s · Fenster-Filter", "edit_tracking_filters",
     None),
]

STATE_TEXT = {"ok": "läuft", "warn": "Problem", "busy": "liest gerade", "off": "aus"}


def tile_state(main, key, kind):
    """(Zustand, Text) einer Datenquelle: ok, warn, busy oder off."""
    action = main.tracking_action if key == "tracking" else main.source_actions.get(key)
    if action is not None and not action.isChecked():
        return "off", "Aus"
    if kind and kind[0] == "reader":
        reader = getattr(main, kind[1], None)
        if reader is None:
            return "busy", "startet …"
        try:
            state, why = reader.health()
        except Exception:  # ein Leser darf die Einstellungen nie blockieren
            return "warn", "Zustand unbekannt"
        return state, why
    if kind and kind[0] == "log":
        try:
            missing = [] if main.timeline.loading else main.timeline.missing_sources()
        except Exception:
            missing = []
        if kind[1] == "RDM Better":
            try:
                missing = ["RDM Better"] if main.timeline.rdmbetter_missing() else []
            except Exception:
                missing = []
        if kind[1] in missing:
            return "warn", "Logdatei nicht gefunden"
    if key == "tracking":
        return "ok", "zeichnet auf"
    return "ok", "an"


def matches(query, *texts):
    """Passt die Suche? Alle Wörter müssen irgendwo vorkommen (ohne Groß/Klein)."""
    hay = " ".join(t for t in texts if t).lower()
    return all(word in hay for word in query.lower().split())


def _unit_words(spec):
    """Suchwörter zur Einheit einer Zahl: „min“ findet man auch mit „Minuten“."""
    if spec[1] != "spin":
        return ""
    return {"min": "min Minuten Grenzwert", "%": "Prozent Grenzwert"}.get(spec[6][2], spec[6][2])


def _switch(name):
    """Schalter mit Text „An“ / „Aus“ (Aussehen: theme.py, QCheckBox#switch)."""
    box = QCheckBox("Aus")
    box.setObjectName("switch")
    box.setAccessibleName(name)
    box.toggled.connect(lambda on: box.setText("An" if on else "Aus"))
    box.setChecked(False)
    return box


def _set_quiet(box, on):
    """Schalter setzen, ohne die Änderung erneut auszulösen."""
    box.blockSignals(True)
    box.setChecked(bool(on))
    box.blockSignals(False)
    if box.objectName() == "switch":
        box.setText("An" if on else "Aus")


class _Combo(QComboBox):
    """Auswahlliste, die beim Schließen Bescheid gibt (Vorschau zurück auf den Stand)."""

    def __init__(self, on_close):
        super().__init__()
        self._on_close = on_close

    def hidePopup(self):
        super().hidePopup()
        self._on_close()


# Schalter am Hauptfenster -> Config-Schlüssel, damit die Vorschau den umgeschalteten Wert zeigen kann
ACTION_KEYS = {"dark_action": "dark_mode", "pc_blocks_action": "pc_blocks", "pc_list_action": "show_pc_in_list"}


class _Row(QFrame):
    """Eine Einstellung: Symbol, Titel, Beschreibung, rechts Schalter, Zahl oder „Ändern …“."""

    def __init__(self, window, spec, show_page=False):
        super().__init__()
        self.setObjectName("setting_row")
        self.window, self.spec = window, spec
        main = window.main
        page, kind, icon_name, title, desc, target, extra = spec
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 10, 4, 10)
        layout.setSpacing(12)
        pic = QLabel()
        pic.setPixmap(icons.icon(icon_name, window.icon_color).pixmap(20, 20))
        pic.setAlignment(Qt.AlignTop)
        layout.addWidget(pic)
        text = QVBoxLayout()
        text.setSpacing(2)
        head = QLabel(title)
        head.setObjectName("row_title")
        text.addWidget(head)
        if show_page:
            where = QLabel(dict((k, n) for k, n, _i, _s in PAGES)[page])
            where.setObjectName("row_page")
            text.insertWidget(0, where)
        body = QLabel(desc)
        body.setObjectName("hint")
        body.setWordWrap(True)
        prose(body)
        text.addWidget(body)
        layout.addLayout(text, 1)
        self.value = None
        self.control = None

        if kind == "toggle":
            action = getattr(main, target)
            self.control = _switch(title)
            self.control.setChecked(action.isChecked())
            self.control.toggled.connect(lambda on: action.isChecked() != on and action.setChecked(on))
            action.toggled.connect(self._on_action_toggled)
        elif kind == "check":
            self.control = _switch(title)
            self.control.setChecked(bool(main.config.get(target, extra)))
            self.control.toggled.connect(lambda on: self._set_config(target, on, "redraw"))
        elif kind == "spin":
            low, high, unit, zero_text, after = extra
            self.control = QSpinBox()
            self.control.setRange(low, high)
            self.control.setSuffix(f" {unit}")
            if zero_text:
                self.control.setSpecialValueText(zero_text)
            self.control.setAccessibleName(title)
            self.control.setValue(int(main.config.get(target, low) or 0))
            self.control.valueChanged.connect(lambda v: self._set_config(target, v, after))
        elif kind == "choice":
            options, _after = extra
            self.control = _Combo(lambda: window.preview_hover(None))
            self.control.setAccessibleName(title)
            for value, text in (options(main) if callable(options) else options):
                self.control.addItem(text, value)
            self.control.activated.connect(
                lambda i: self._set_config(target, self.control.itemData(i), extra[1]))
            # Vorschau schon beim Durchgehen der Liste, bevor etwas gewählt ist
            self.control.highlighted.connect(
                lambda i: window.preview_hover(self.spec, self.control.itemData(i), self.control.itemText(i)))
        else:  # button
            if extra:
                self.value = QLabel()
                self.value.setObjectName("row_value")
                self.value.setMaximumWidth(320)  # lange Pfade quetschen sonst die Beschreibung
                layout.addWidget(self.value)
            self.control = QPushButton(BUTTON_TEXT.get(title, "Öffnen …") if kind == "button" else "")
            self.control.setAccessibleName(f"{title}: {self.control.text().rstrip(' …')}")
            self.control.setAutoDefault(False)
            self.control.clicked.connect(self._run)
        layout.addWidget(self.control)
        self.refresh()

    def _sync_toggle(self, on):
        if self.control.isChecked() != on:
            _set_quiet(self.control, on)

    def _on_action_toggled(self, on):
        self._sync_toggle(on)
        self.window.refresh_preview_later()

    # Vorschau: beim Darüberfahren zeigen, wie es nach dem Umschalten aussähe
    def enterEvent(self, event):
        self.window.preview_hover(self.spec)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.window.preview_hover(None)
        super().leaveEvent(event)

    def _run(self):
        target = self.spec[5]
        main = self.window.main
        (getattr(main, target) if isinstance(target, str) else (lambda: target(main)))()
        self.window.refresh()

    def _set_config(self, key, value, after):
        main = self.window.main
        if main.config.get(key) == value:
            return
        main.config[key] = value
        mt.save_config(main.config)
        if after == "idle_watch" and getattr(main, "idle_watch", None):
            main.idle_watch.minutes = value
        elif after == "idle_limit" and getattr(main, "tracker", None):
            main.tracker.idle_limit = value * 60
        if after in ("redraw", "idle_watch"):
            main.timeline.draw_timeline(main.current_date)
        elif after == "view":
            main.change_view(value)
        elif after == "range":
            main.show_preferred_range()
        self.window.refresh_preview_later()
        if key in ("booking_rate_status", "booking_target_percent"):
            import week_dialogs
            week_dialogs.update_rate_button(main)

    def refresh(self):
        kind, target, extra = self.spec[1], self.spec[5], self.spec[6]
        main = self.window.main
        if self.value is not None and extra:
            full = str(extra(main))
            shown = self.value.fontMetrics().elidedText(full, Qt.ElideMiddle, self.value.maximumWidth())
            self.value.setText(shown)
            self.value.setToolTip(full if shown != full else "")
        elif kind == "spin":
            self.control.blockSignals(True)
            self.control.setValue(int(main.config.get(target, extra[0]) or 0))
            self.control.blockSignals(False)
        elif kind == "check":
            _set_quiet(self.control, main.config.get(target, extra))
        elif kind == "choice":
            default = self.control.itemData(0)
            index = self.control.findData(main.config.get(target, default))
            self.control.blockSignals(True)
            self.control.setCurrentIndex(max(0, index))
            self.control.blockSignals(False)
        elif kind == "toggle":
            self._sync_toggle(getattr(main, target).isChecked())


class _Tile(QFrame):
    """Datenquelle: Zeichen, Name, Schalter, Zustand und „Einrichten …“."""

    def __init__(self, window, spec):
        super().__init__()
        self.setObjectName("tile")
        self.window, self.spec = window, spec
        key, brand, name, desc, setup, _kind = spec
        main = window.main
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        head = QHBoxLayout()
        pic = QLabel()
        pic.setPixmap(icons.brand_icon(brand).pixmap(28, 28))
        head.addWidget(pic)
        title = QLabel(name)
        title.setObjectName("row_title")
        title.setWordWrap(True)
        head.addWidget(title, 1)
        self.switch = _switch(f"{name} einschalten")
        self.action = main.tracking_action if key == "tracking" else main.source_actions.get(key)
        if self.action is not None:
            self.switch.setChecked(self.action.isChecked())
            self.switch.toggled.connect(self._toggle)
            self.action.toggled.connect(self._on_action)
        head.addWidget(self.switch)
        layout.addLayout(head)
        info = QLabel(desc)
        info.setObjectName("hint")
        info.setWordWrap(True)
        layout.addWidget(info)
        state = QHBoxLayout()
        self.state_icon = QLabel()
        self.state_text = QLabel()
        self.state_text.setWordWrap(True)
        state.addWidget(self.state_icon)
        state.addWidget(self.state_text, 1)
        layout.addLayout(state)
        layout.addStretch(1)
        button = QPushButton("Einrichten …")
        button.setAutoDefault(False)
        button.setAccessibleName(f"{name} einrichten")
        button.clicked.connect(lambda: (getattr(main, setup)(), window.refresh()))
        layout.addWidget(button, 0, Qt.AlignLeft)
        self.refresh()

    def _on_action(self, _on):
        self.refresh()

    def _toggle(self, on):
        if self.action.isChecked() != on:
            self.action.setChecked(on)
        self.window.refresh()

    def refresh(self):
        key, _brand, name, _desc, _setup, kind = self.spec
        state, text = tile_state(self.window.main, key, kind)
        if self.action is not None and self.switch.isChecked() != self.action.isChecked():
            _set_quiet(self.switch, self.action.isChecked())
        if (state, text) == getattr(self, "_shown", None):
            return  # unverändert: Zeichen und Stil nicht alle 3 s neu aufbauen
        self._shown = (state, text)
        if state == "off":
            self.state_icon.clear()
        else:
            self.state_icon.setPixmap(icons.source_icon(state).pixmap(16, 16))
        self.state_text.setText(text)
        self.state_text.setObjectName("hint" if state == "off" else "")
        self.state_text.style().unpolish(self.state_text)
        self.state_text.style().polish(self.state_text)
        self.setToolTip(f"{name}: {STATE_TEXT.get(state, state)} – {text}")
        self.state = state


class SettingsWindow(QDialog):
    """Alle Einstellungen in einem Fenster. Bleibt offen, während du weiterarbeitest."""

    HOVER_DELAY_MS = 120

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Zeitzeuge – Einstellungen")
        self.setObjectName("settings_window")
        self.resize(1000, 660)
        self.setMinimumSize(720, 480)
        theme = THEMES["dark" if main.dark_mode else "light"]
        self.icon_color = theme["text"]
        self.rows, self.tiles = [], []
        self.preview = None  # Vorschau auf der Seite „Ansicht“ (settings_preview.py)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(0)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._preview_stale = False  # Änderung, während die Seite „Ansicht“ nicht zu sehen war
        # Darüberfahren: erst zeichnen, wenn die Maus kurz auf einer Zeile bleibt. Beim Wischen
        # über viele Zeilen sonst eine volle Neuzeichnung je Zeile (Fenster wirkt zäh).
        self._hover_pending = None
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(self.HOVER_DELAY_MS)
        self._hover_timer.timeout.connect(self._apply_hover)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(16, 12, 16, 12)
        heading = QLabel("Einstellungen")
        heading.setObjectName("page_title")
        top.addWidget(heading)
        top.addSpacing(24)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Einstellung suchen, z. B. Minuten, VPN, PIN")
        self.search.setAccessibleName("Einstellungen durchsuchen")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icons.icon("search", theme["muted"]), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self.on_search)
        top.addWidget(self.search, 1)
        outer.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("settings_nav")
        self.nav.setAccessibleName("Bereiche")
        self.nav.setFixedWidth(240)
        self.nav.setIconSize(QSize(18, 18))
        self.stack = QStackedWidget()
        self.pages = {}
        for key, name, icon_name, subtitle in PAGES:
            item = QListWidgetItem(icons.icon(icon_name, self.icon_color), name)
            item.setData(Qt.UserRole, key)
            item.setSizeHint(QSize(0, 40))
            self.nav.addItem(item)
            self.pages[key] = self.stack.addWidget(self._page(key, name, subtitle))
        self.results_index = self.stack.addWidget(self._results_page())
        self.nav.currentRowChanged.connect(self._show_row)
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)

        # Zustände der Quellen nachziehen, solange das Fenster offen ist
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_tiles)
        self._timer.start(3000)
        # Änderungen aus dem Hauptfenster (Menü Ansicht, Zeilen der Timeline) auch in der Vorschau
        for action in list(getattr(main, "row_actions", {}).values()):
            action.toggled.connect(self.refresh_preview_later)
        for action in getattr(main, "view_actions", {}).values():
            action.triggered.connect(self.refresh_preview_later)
        self.nav.setCurrentRow(0)

    # ---- Aufbau

    def _scroll(self, widget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _page(self, key, name, subtitle):
        page = QWidget()
        page.setObjectName("settings_page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(4)
        # Seite „Ansicht“: Titel und Vorschau bleiben stehen, nur die Einstellungen darunter blättern
        head = layout
        if key == "view":
            fixed = QWidget()
            fixed.setObjectName("settings_page")
            head = QVBoxLayout(fixed)
            head.setContentsMargins(28, 20, 28, 8)
            head.setSpacing(4)
            layout.setContentsMargins(28, 4, 28, 20)
        title = QLabel(name)
        title.setObjectName("page_title")
        head.addWidget(title)
        sub = QLabel(subtitle)
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        head.addWidget(sub)
        head.addSpacing(10)
        if key == "view":
            from settings_preview import PreviewPane
            self.preview = PreviewPane(self.main)
            head.addWidget(self.preview)
        if key == "sources":  # Einrichtungsassistent ganz oben, darunter die Kacheln
            for spec in ROWS:
                if spec[0] == key and spec[1] == "button" and spec[5] == "show_setup_wizard":
                    row = _Row(self, spec)
                    self.rows.append(row)
                    layout.addWidget(row)
            layout.addSpacing(8)
            grid = QGridLayout()
            grid.setSpacing(12)
            for i, spec in enumerate(SOURCE_TILES):
                tile = _Tile(self, spec)
                self.tiles.append(tile)
                grid.addWidget(tile, i // 3, i % 3)
            for col in range(3):
                grid.setColumnStretch(col, 1)
            layout.addLayout(grid)
            layout.addSpacing(12)
            pc = QLabel("Aktive Fenster")  # Aufzeichnung am PC: Schalter, Filter, Leerlauf
            pc.setObjectName("row_title")
            layout.addWidget(pc)
        for spec in ROWS:
            if spec[0] == key and not (key == "sources" and spec[5] == "show_setup_wizard"):
                row = _Row(self, spec)
                self.rows.append(row)
                layout.addWidget(row)
        layout.addStretch(1)
        if key == "view":
            wrapper = QWidget()
            box = QVBoxLayout(wrapper)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(0)
            box.addWidget(fixed)
            box.addWidget(self._scroll(page), 1)
            return wrapper
        return self._scroll(page)

    # ---- Vorschau (Seite „Ansicht“)

    def preview_hover(self, spec, value=None, text=None):
        """Variante zeigen: Schalter umgedreht oder Eintrag einer Auswahl; spec None = aktueller Stand."""
        if self.preview is None:
            return
        changes, caption = None, ""
        if spec is not None:
            main = self.main
            kind, title, target, extra = spec[1], spec[3], spec[5], spec[6]
            key = ACTION_KEYS.get(target) if kind == "toggle" else target
            if kind == "toggle" and key:
                on = not getattr(main, target).isChecked()
                changes, caption = {key: on}, f"So sähe es aus mit „{title}“ {'an' if on else 'aus'}"
            elif kind == "check":
                on = not bool(main.config.get(target, extra))
                changes, caption = {key: on}, f"So sähe es aus mit „{title}“ {'an' if on else 'aus'}"
            elif kind == "choice" and value is not None and value != main.config.get(target):
                changes, caption = {key: value}, f"So sähe es aus mit „{title}: {text}“"
        self._hover_pending = (changes, caption)
        self._hover_timer.start()  # neu starten: nur die Zeile zählt, auf der die Maus bleibt

    def _apply_hover(self):
        if self.preview is None or self._hover_pending is None:
            return
        changes, caption = self._hover_pending
        self._hover_pending = None
        current = self.preview.variant
        if (changes or None) == (current[0] if current else None):
            return  # zeigt schon genau das
        if not self.preview.isVisible():
            self._preview_stale = True
            return
        self.preview.show_variant(changes, caption)

    def refresh_preview_later(self):
        """Nach einer Änderung (auch aus dem Hauptfenster) die Vorschau einmal neu zeichnen."""
        if self.preview is not None and not self._preview_timer.isActive():
            self._preview_timer.start()

    def _refresh_preview(self):
        if self.preview is None:
            return
        if not self.preview.isVisible():  # erst zeichnen, wenn die Seite „Ansicht“ gezeigt wird
            self._preview_stale = True
            return
        self._preview_stale = False
        self.preview.show_variant(None)

    def _results_page(self):
        page = QWidget()
        page.setObjectName("settings_page")
        self.results_layout = QVBoxLayout(page)
        self.results_layout.setContentsMargins(28, 20, 28, 20)
        self.results_title = QLabel()
        self.results_title.setObjectName("page_title")
        self.results_layout.addWidget(self.results_title)
        self.results_box = QVBoxLayout()
        self.results_layout.addLayout(self.results_box)
        self.results_layout.addStretch(1)
        return self._scroll(page)

    # ---- Bedienen

    def _show_row(self, row):
        if row < 0:
            return
        if self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        key = self.nav.item(row).data(Qt.UserRole)
        self.stack.setCurrentIndex(self.pages[key])
        self.refresh()
        if key == "view" and self._preview_stale:
            self._refresh_preview()

    def show_page(self, key):
        """Bereich zeigen, z. B. show_page("sources")."""
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == key:
                self.nav.setCurrentRow(i)
                self._show_row(i)
                return

    def current_page(self):
        item = self.nav.currentItem()
        return item.data(Qt.UserRole) if item else None

    def on_search(self, text):
        while self.results_box.count():
            widget = self.results_box.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        text = text.strip()
        if not text:
            self._show_row(self.nav.currentRow())
            return
        names = {k: n for k, n, _i, _s in PAGES}
        found = [spec for spec in ROWS if matches(text, spec[3], spec[4], names[spec[0]], _unit_words(spec))]
        tiles = [spec for spec in SOURCE_TILES if matches(text, spec[2], spec[3], "Datenquellen")]
        for spec in tiles:
            row = QPushButton(icons.brand_icon(spec[1]), f"  {spec[2]} – Datenquellen")
            row.setObjectName("result_link")
            row.setAutoDefault(False)
            row.clicked.connect(lambda: self.show_page("sources"))
            self.results_box.addWidget(row)
        for spec in found:
            self.results_box.addWidget(_Row(self, spec, show_page=True))
        count = len(found) + len(tiles)
        self.results_title.setText(f"{count} Treffer für „{text}“" if count
                                   else f"Nichts gefunden für „{text}“")
        self.results_found = count
        self.stack.setCurrentIndex(self.results_index)

    def refresh_tiles(self):
        if self.isVisible():
            for tile in self.tiles:
                tile.refresh()

    def refresh(self):
        for row in self.rows:
            row.refresh()
        self.refresh_tiles()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        if self._preview_stale and self.current_page() == "view":
            self.refresh_preview_later()
