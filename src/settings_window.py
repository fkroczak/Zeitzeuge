"""Fenster „Einstellungen“: Bereiche links, Suche oben, Datenquellen als Kacheln mit Zustand.

Alles wirkt sofort: Schalter sind dieselben Aktionen wie im Hauptfenster (Menü, Infobereich),
Zahlen werden gleich gespeichert, „Ändern …“ öffnet die bisherigen Dialoge. Die Bereiche
stehen in PAGES und ROWS; die Suche geht über Titel, Beschreibung und Bereich jeder Zeile.

Teil von TimelineApp (main_timeline.py): SettingsWindow(main) bekommt das Hauptfenster.
"""
import os

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QIcon, QPainter
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
                               QSpinBox, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

import icons
from flow_layout import FlowLayout
from theme import theme_for, fit_bold, fit_text, prose, SPACE_2XL, SPACE_L, SPACE_M, SPACE_S, SPACE_XL, SPACE_XS
import main_timeline as mt  # Pfade und save_config zur Laufzeit von dort (Tests ersetzen sie dort)

# Bereiche: Schlüssel, Name, Symbol, Satz darunter. Reihenfolge wie der Arbeitstag:
# aufzeichnen, nachfragen, zuordnen, buchen; danach Darstellung, Datenschutz, Info.
PAGES = [
    ("home", "Übersicht", "today", "Was gerade los ist und was du oft brauchst."),
    ("sources", "Aufzeichnung", "plug", "Was Zeitzeuge mitschreibt und woher."),
    ("prompts", "Nachfragen", "bell", "Wann und wie Zeitzeuge nach deinen Tätigkeiten fragt."),
    ("mapping", "Zuordnung", "users", "Wie Zeitzeuge Kunde und Kategorie erkennt, und Textbausteine."),
    ("booking", "Buchung", "gauge", "Matrix42, Arbeitszeiten, Abrechnung und Buchungsquote."),
    ("view", "Darstellung", "eye", "Aussehen von Timeline und Tagesliste."),
    ("data", "Datenschutz", "shield", "Wo die Daten liegen, wie lange, und wer sie lesen kann."),
    ("about", "Info", "info", "Version, Hilfe bei Problemen und Beenden."),
]
# Frühere Namen der Bereiche (Menüs, Tests, gespeicherte Seite) zeigen auf den neuen
PAGE_ALIASES = {"general": "home", "customers": "mapping", "rules": "mapping", "debug": "about"}


def row_page(spec):
    """Bereich einer Zeile: „view/Timeline“ -> „view“."""
    return spec[0].partition("/")[0]


def row_section(spec):
    """Abschnitt einer Zeile im Bereich: „view/Timeline“ -> „Timeline“ ("" = ohne Überschrift)."""
    return spec[0].partition("/")[2]


def _prompt_summary(main):
    c = main.config
    from prompt_card import POSITIONS, STYLES, prompt_position, prompt_style, prompt_timeout
    style = prompt_style(c)
    if style == "off":
        return "aus"
    seconds = prompt_timeout(c)
    shown = "dauerhaft" if not seconds else f"{seconds} s" if seconds < 60 else f"{seconds // 60} min"
    where = "" if style == "strip" else f" · {dict(POSITIONS)[prompt_position(c)].lower()}"
    return f"{dict(STYLES)[style]}{where} · {shown} · später nach {c.get('prompt_snooze_minutes', 15)} min"


def _billing_summary(main):
    c = main.config
    if c.get("billing_mode", "up") == "off":
        return "echte Dauer"
    return f"{c.get('billing_step_minutes', 15)}-Minuten-Takt"


def _open_data_dir(main):
    QDesktopServices.openUrl(QUrl.fromLocalFile(mt.DATA_DIR))


# Zeilen: (Bereich/Abschnitt, Art, Symbol, Titel, Beschreibung, Ziel, Zusatz)
#   toggle: Ziel = Name einer QAction am Hauptfenster
#   button: Ziel = Methode am Hauptfenster (oder Funktion main -> None), Zusatz = Wert-Funktion
#   spin:   Ziel = Config-Schlüssel, Zusatz = (min, max, Einheit, Text bei 0, Nachlauf)
#   check:  Ziel = Config-Schlüssel, Zusatz = Standardwert
#   choice: Ziel = Config-Schlüssel, Zusatz = ([(Wert, Text)] oder Funktion main -> Liste, Nachlauf)
#   theme:  Auswahl des Designs als Liste (Wie Windows, Hell, Dunkel, Eigene Farben)
#   tiles:  Auswahl als Kacheln mit Skelett-Bild (settings_skeletons.py), Zusatz = [(Wert, Text)]
#           oder Funktion main -> Liste. Ziel: "theme", ein Config-Schlüssel oder eine QAction
#           (Werte "on"/"off")
# Jede Einstellung steht genau einmal; nur „Übersicht → Häufig“ wiederholt die häufigsten.
ROWS = [
    ("home/Häufig", "theme", "palette", "Design", "Hell, Dunkel, wie Windows oder eigene Farben.", None, None),
    ("home/Häufig", "toggle", "monitor", "Aktive Fenster aufzeichnen",
     "Band „PC“: welches Programm wann vorn war. Auch im Infobereich pausierbar.", "tracking_action", None),
    ("home/Häufig", "toggle", "power", "Mit Windows starten",
     "Startet beim Anmelden an Windows im Infobereich, damit nichts unaufgezeichnet bleibt.",
     "autostart_action", None),
    ("home/Häufig", "button", "users", "Kundenliste", "Kunden mit ihren Spuren.", "edit_customers", None),
    ("home/Häufig", "button", "edit", "Textbausteine", "Bausteine und Ticket-Format beim Eintragen.",
     "edit_snippets", None),

    ("sources/Grundlagen", "toggle", "power", "Mit Windows starten",
     "Startet beim Anmelden an Windows im Infobereich, damit nichts unaufgezeichnet bleibt.",
     "autostart_action", None),
    ("sources/Grundlagen", "button", "spark", "Einrichtungsassistent", "Alle Quellen Schritt für Schritt neu einrichten.",
     "show_setup_wizard", None),
    ("sources/Grundlagen", "spin", "pause", "Leerlauf nach",
     "Ohne Maus und Tastatur zeichnet Zeitzeuge keine aktiven Fenster auf.",
     "tracking_idle_minutes", (1, 60, "min", "", "idle_limit")),
    ("sources/Grundlagen", "toggle", "server", "Dieser PC ist eine PAW", "Nur RDM sammeln, alles andere aus.",
     "paw_action", None),

    ("mapping", "button", "users", "Kundenliste", "Kunden mit ihren Spuren (TeamViewer-ID, RDM, VPN, Telefon, Domain).",
     "edit_customers", None),
    ("mapping", "button", "map_pin", "Orte und Fahrzeiten",
     "Startadresse, Orte und Kunden mit Fahrzeit für vermutete Fahrten.", "edit_travel_settings", None),
    ("mapping", "button", "rules", "Regeln ohne KI", "Feste Regeln: Programm oder Verbindung → Kategorie und Kunde.",
     "edit_rules", None),
    ("mapping", "button", "spark", "KI-Vorschläge", "Modell, Schlüssel und Kategorien für Claude.",
     "edit_ai_settings", None),
    ("mapping", "button", "edit", "Textbausteine", "Bausteine und Ticket-Format beim Eintragen.",
     "edit_snippets", None),

    ("booking", "button", "gauge", "Matrix42 einrichten", "Adresse der Kalenderseite und Anmeldung (nur im Firmennetz).",
     "open_m42_settings", None),
    ("booking", "button", "clock", "Arbeitszeiten", "Arbeitstage und Zeiten, wenn keine ITM-Personalzeit da ist.",
     "edit_work_hours", None),
    ("booking", "button", "tag", "Abrechnung", "Abrechnungstakt, auch je Kunde.", "edit_billing", _billing_summary),
    ("booking", "spin", "gauge", "Ziel Buchungsquote", "So viel der Personalzeit soll in Matrix42 gebucht sein.",
     "booking_target_percent", (10, 150, "%", "", "redraw")),
    ("booking", "check", "details", "Quote in der Statuszeile", "„Quote heute 72 % · 7 Tage 81 %“ unten anzeigen.",
     "booking_rate_status", True),
    ("booking", "check", "alert", "Bei Feierabend prüfen",
     "Pausen, Stempelung, Buchungen außerhalb der Personalzeit, Quote unter Ziel.", "day_checks_enabled", True),

    # Darstellung: alles, was nur die Anzeige ändert; Auswahl über Kacheln mit Skelett-Bild
    ("view/Aussehen", "tiles", "palette", "Design", "Hell, Dunkel, wie Windows oder eigene Farben. Gilt sofort.",
     "theme", [("system", "Wie &Windows"), ("light", "&Hell"), ("dark", "&Dunkel"), ("custom", "&Eigene Farben")]),
    ("view/Aussehen", "button", "palette", "Aktivitätstypen und Farben", "Farbe je Art in der Timeline.",
     "edit_activity_types", None),
    ("view/Timeline", "tiles", "clock", "Timeline beim Start",
     "Zeitraum beim Start und beim Blättern zum nächsten Tag.",
     "timeline_range", [("work", "Arbeitszeit"), ("day", "Ganzer Tag")]),
    ("view/Timeline", "button", "rows", "Zeilen der Timeline",
     "Jede Zeile ein- oder ausblenden. Leere Zeilen blendet Zeitzeuge von selbst aus.",
     lambda main: main.rows_menu.exec(QCursor.pos()), None),
    ("view/Timeline", "tiles", "blocks", "PC-Aktivität",
     "Fenster zu Blöcken je Tätigkeit zusammenfassen oder jedes Fenster einzeln zeigen.",
     "pc_blocks_action", [("on", "Arbeitsblöcke"), ("off", "Jedes Fenster")]),
    ("view/Timeline", "spin", "layers", "Kurze Sprünge bis",
     "Kürzere Wechsel zählen zur Haupttätigkeit, wenn es danach dort weitergeht oder der Kunde passt.",
     "pc_jump_seconds", (0, 600, "s", "aus", "redraw")),
    ("view/Timeline", "spin", "blocks", "Arbeitsblock bis Pause",
     "Ansicht „Arbeitsblöcke“: alles mit kürzerer Pause wird ein Block.",
     "block_gap_minutes", (1, 240, "min", "", "redraw")),
    ("view/Timeline", "spin", "monitor", "Gesendete Mail als Block",
     "So breit steht eine gesendete Mail in der Timeline (Outlook).",
     "outlook_mail_minutes", (1, 60, "min", "", "redraw")),
    ("view/Tagesliste", "tiles", "layers", "Ansicht der Tagesliste",
     "Wie die Liste unter der Timeline die Einträge zeigt (F1 erklärt alle).",
     "list_view", lambda main: list(main.VIEWS)),
    ("view/Tagesliste", "tiles", "monitor", "PC-Verlauf in der Liste", "Arbeitsblöcke am PC auch in der Tagesliste zeigen.",
     "pc_list_action", [("off", "Nur Einträge"), ("on", "Mit PC-Verlauf")]),
    ("view/Tagesliste", "spin", "layers", "Zusammenfassen bis Pause",
     "Ansicht „Zusammengefasst“: gleiche Verbindungen mit kürzerer Pause werden eine Zeile.",
     "merge_gap_minutes", (0, 120, "min", "nie", "redraw")),
    ("view/Tagesliste", "check", "details", "Aktivitätsdetails als Textfelder",
     "Werte im Fenster „Aktivitätsdetails“ in Textfeldern zeigen: hineinklicken, Strg+A, Strg+C.",
     "detail_text_fields", False),

    ("data/Speicherort", "button", "folder", "Datenordner", "Einstellungen, Datenbank und Sicherung. Auch die Mitschnitte der Fehlersuche.",
     _open_data_dir, lambda _m: os.path.normpath(mt.DATA_DIR)),
    ("data/Speicherort", "button", "folder", "Speicherort ändern", "Daten in einen anderen Ordner verschieben (startet neu).",
     "change_data_dir", None),
    ("data/Schutz", "button", "lock", "PIN und Wiederherstellungsschlüssel",
     "Daten sind verschlüsselt. PIN beim Start, Schlüssel für den Notfall.", "show_protection", None),
    ("data/Aufbewahren", "button", "trash", "PC-Verlauf automatisch löschen", "Aufgezeichnete Fenster nach einigen Tagen löschen.",
     lambda main: main.retention.edit(),
     lambda m: f"nach {m.config.get('pc_history_days', 90)} Tagen" if m.config.get("pc_history_purge") else "aus"),
    ("data/Aufbewahren", "spin", "trash", "Spuren-Verlauf aufbewahren",
     "Spuren vom PC, Remotedesktop und VPN: Älteres wird einmal am Tag gelöscht. Tätigkeiten bleiben.",
     "trace_history_days", (30, 3650, "Tage", "", None)),
    ("data/Anderer PC", "button", "upload", "Daten exportieren", "Für einen anderen PC, z. B. die PAW.", "export_data", None),
    ("data/Anderer PC", "button", "download", "Daten übernehmen", "Von einem anderen PC einlesen.", "import_data", None),

    ("about", "check", "download", "Updates automatisch suchen",
     "Alle 6 Stunden nach einer neuen Version sehen und sie mit einem Klick installieren.", "update_check", True),
    ("about", "button", "refresh", "Nach Updates suchen",
     "Neue Version laden und installieren. Zeitzeuge startet danach neu, die Daten bleiben.",
     "check_update_now", lambda m: m.update_state_text()),
    ("about", "button", "power", "Zeitzeuge beenden", "Aufzeichnung und Datenquellen stoppen.",
     lambda main: _confirm_quit(main), None),
    ("about/Fehlersuche", "button", "record", "3CX: Abfragen mitschneiden",
     "Edge-Fenster mit dem 3CX-Webclient öffnen und aufzeichnen, was die Seite abfragt.",
     lambda main: main.record_source("pbx"), None),
    ("about/Fehlersuche", "button", "phone", "3CX: Direkt-Abfrage prüfen",
     "Anrufe ohne Webseite direkt vom 3CX-Server holen und mit der gespeicherten Anrufliste vergleichen.",
     "check_pbx_direct", None),
    ("about/Fehlersuche", "button", "record", "Matrix42: Abfragen mitschneiden",
     "Edge-Fenster mit dem Matrix42-Kalender öffnen und aufzeichnen, was die Seite abfragt.",
     lambda main: main.record_source("m42"), None),
    ("about/Fehlersuche", "button", "record", "Matrix42: Buchung mitschneiden",
     "Aufzeichnen, wie Matrix42 eine Zeiterfassung speichert. Du legst dabei selbst eine Buchung an.",
     lambda main: main.record_source("m42", booking=True), None),
    ("about/Fehlersuche", "button", "record", "Matrix42: Ticket anlegen und schließen mitschneiden",
     "Aufzeichnen, wie Matrix42 Incidents und Service Requests anlegt und mit Lösungstext schließt. "
     "Du legst dabei selbst zwei Test-Tickets an und schließt sie.",
     lambda main: main.record_source("m42", ticket=True), None),
    ("about/Fehlersuche", "button", "record", "ITM: Abfragen mitschneiden",
     "Edge-Fenster mit der ITM-Zeiterfassung öffnen und aufzeichnen, was die Seite abfragt.",
     lambda main: main.record_source("itm"), None),
]
# Eingeklappte Abschnitte (im Alltag nicht nötig): Bereich/Abschnitt -> Satz darunter
COLLAPSED = {"about/Fehlersuche": "Für tiefergehende Analysen, z. B. wenn nach einem Update etwas nicht mehr "
             "gelesen wird. Passwörter und Token werden geschwärzt, die Mitschnitte landen im Datenordner."}

# Suchbegriffe für die Seite „Nachfragen“ (dort keine Zeilen, sondern eigene Bedienelemente)
PROMPT_TOPICS = [
    ("Darstellung der Nachfrage", "Karte Kompakt Leiste Aus Fenster Infobereich"),
    ("Ausblenden nach und Position", "Sekunden Minuten dauerhaft Anzeigedauer tippen Maus Punkte ✕ Leiste "
     "Position Ecke oben unten links rechts"),
    ("Fragen bei", "Verbindungen Telefonate Arbeitsblöcke PC Besprechungen Mails Zugangsdaten Regeln "
     "Grenzwerte Minuten ab Abwesenheit"),
    ("„Später“ fragt wieder nach", "Minuten später zurückgestellt"),
    ("Erinnern", "Feierabend Beenden Offenes Benachrichtigungen Hinweis läuft weiter Windows Sprechblase"),
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
    "Nach Updates suchen": "Jetzt suchen",
}


def _confirm_quit(main):
    """Beenden aus den Einstellungen erst nach Rückfrage (ein Klick daneben soll nichts stoppen)."""
    box = QMessageBox(QMessageBox.Question, "Zeitzeuge beenden",
                      "Zeitzeuge beenden? Aufzeichnung und Datenquellen stoppen dann.",
                      parent=main._settings_window if getattr(main, "_settings_window", None) else main)
    quit_button = box.addButton("&Beenden", QMessageBox.AcceptRole)
    box.addButton("Abbre&chen", QMessageBox.RejectRole)
    fit_bold(quit_button)
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
    ("sessionmgmt_enabled", "sessionmgmt", "SessionMGMT", "Sitzungen mit Kunde aus sessions.log",
     "edit_sessionmgmt_settings", ("log", "SessionMGMT")),
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
    ("travel_enabled", "travel", "Fahrten (vermutet)", "Orte, Kundenadressen, Fahrzeiten", "edit_travel_settings", None),
    ("tracking", "tracking", "Aktive Fenster", "Band „PC“, alle 5 s · Fenster-Filter", "edit_tracking_filters",
     None),
]

# Kacheln der Aufzeichnung in Abschnitten nach Art
TILE_GROUPS = [
    ("Fernwartung", ["teamviewer_enabled", "rdm_enabled", "rdmbetter_enabled", "sessionmgmt_enabled",
                     "mstsc_enabled", "shell_enabled"]),
    ("VPN", ["sophos_enabled", "forti_enabled", "vpn_enabled"]),
    ("Kommunikation", ["pbx_reader_enabled", "teams_calls_enabled", "teams_chats_enabled", "outlook_enabled",
                       "travel_enabled"]),
    ("Am PC", ["tracking", "pcstate_enabled", "wlan_enabled", "recent_files_enabled", "browser_enabled"]),
    ("Firmensysteme", ["itm_reader_enabled", "m42_reader_enabled"]),
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
        if kind[1] == "SessionMGMT":
            try:
                missing = ["SessionMGMT"] if main.timeline.sessionmgmt_missing() else []
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
    box.setLayoutDirection(Qt.RightToLeft)  # Text links, Schalter bündig rechts wie die Knöpfe
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


class _ElidedLabel(QLabel):
    """Wert rechts in einer Zeile (z. B. Pfad): so breit wie nötig, höchstens maximumWidth,
    in schmalen Fenstern in der Mitte mit „…“ gekürzt (voller Text als Tooltip).
    Ein normales QLabel ist nie schmaler als sein Text und schiebt die Seite sonst nach rechts
    aus dem Fenster (horizontale Scrollleiste)."""

    def __init__(self):
        super().__init__()
        self._full = ""

    def set_full_text(self, text):
        self._full = text
        self.setText(text)
        self._update_tip()

    def minimumSizeHint(self):
        return QSize(60, super().minimumSizeHint().height())

    def _update_tip(self):
        self.setToolTip(self._full if self.fontMetrics().horizontalAdvance(self._full) > self.width() else "")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_tip()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        rect = self.contentsRect()
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter,
                         self.fontMetrics().elidedText(self._full, Qt.ElideMiddle, rect.width()))


CONTROL_WIDTH = 150
TILE_WIDTH = 132  # Kachel mit Skelett-Bild (96 px) und Beschriftung darunter


class _Row(QFrame):
    """Eine Einstellung: Symbol, Titel, Beschreibung, rechts Schalter, Zahl oder „Ändern …“."""

    def __init__(self, window, spec, show_page=False):
        super().__init__()
        self.setObjectName("setting_row")  # Karte mit 1 px Rand (theme.py)
        self.window, self.spec = window, spec
        main = window.main
        _where, kind, icon_name, title, desc, target, extra = spec
        page = row_page(spec)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_M + 2, SPACE_M, SPACE_M + 2, SPACE_M)
        layout.setSpacing(SPACE_M)
        pic = QLabel()
        pic.setObjectName("row_icon")
        pic.setFixedSize(32, 32)
        pic.setContentsMargins(7, 7, 7, 7)  # 18-px-Symbol mittig in der 32-px-Kachel
        pic.setPixmap(icons.icon(icon_name, window.icon_color).pixmap(18, 18))
        layout.addWidget(pic, 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(SPACE_XS)
        head = QLabel(title)
        head.setObjectName("row_title")
        head.setWordWrap(True)  # lange Titel umbrechen statt die Seite zu verbreitern
        head.setMinimumWidth(80)  # sonst verlangt Qt je nach Schrift (Windows) mehr Breite
        text.addWidget(head)
        if show_page:
            where = QLabel(" · ".join(t for t in (dict((k, n) for k, n, _i, _s in PAGES)[page], row_section(spec)) if t))
            where.setObjectName("row_page")
            text.insertWidget(0, where)
        body = QLabel(desc)
        body.setObjectName("hint")
        body.setWordWrap(True)
        body.setMinimumWidth(80)
        prose(body)
        text.addWidget(body)
        layout.addLayout(text, 1)
        self.pic, self.icon_name = pic, icon_name
        self.value = None
        self.control = None
        self.tiles = {}
        self.custom_panel = None

        if kind == "tiles":  # Auswahl als Kacheln unter dem Text, ohne Steuerelement rechts
            self._build_tiles(text)
            self.refresh()
            return
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
        elif kind == "theme":
            self.control = QComboBox()
            self.control.setAccessibleName(title)
            for value, text in main.THEME_CHOICES:
                self.control.addItem(text.replace("&", ""), value)
            self.control.activated.connect(lambda i: self._choose_theme(self.control.itemData(i)))
        elif kind == "choice":
            options, _after = extra
            self.control = QComboBox()
            self.control.setAccessibleName(title)
            for value, text in (options(main) if callable(options) else options):
                self.control.addItem(text, value)
            self.control.activated.connect(
                lambda i: self._set_config(target, self.control.itemData(i), extra[1]))
        else:  # button
            if extra:
                self.value = _ElidedLabel()
                self.value.setObjectName("row_value")
                self.value.setMaximumWidth(320)  # lange Pfade quetschen sonst die Beschreibung
                layout.addWidget(self.value)
            self.control = QPushButton(BUTTON_TEXT.get(title, "Öffnen …") if kind == "button" else "")
            self.control.setAccessibleName(f"{title}: {self.control.text().rstrip(' …')}")
            self.control.setAutoDefault(False)
            fit_text(self.control)  # nie schmaler als der Text, die Beschreibung bricht stattdessen um
            self.control.clicked.connect(self._run)
        self.control.setMinimumWidth(CONTROL_WIDTH)  # Schalter, Zahlen und Knöpfe in einer Spalte
        layout.addWidget(self.control)
        self.refresh()

    # ---- Kacheln mit Skelett-Bild (Seite „Darstellung“)

    def _options(self):
        extra = self.spec[6]
        return extra(self.window.main) if callable(extra) else extra

    def _build_tiles(self, text):
        target = self.spec[5]
        options = self._options()
        host = QWidget()
        host.setObjectName("chips")
        flow = FlowLayout(host, spacing=SPACE_S)  # bricht in schmalen Fenstern um
        group = QButtonGroup(self)
        for value, label in options:
            tile = QToolButton()
            tile.setObjectName("style_tile")
            tile.setCheckable(True)
            tile.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            tile.setIconSize(QSize(96, 60))
            tile.setFixedWidth(TILE_WIDTH)
            tile.setText(label if "&" in label else label.replace("&", "&&"))
            tile.setAccessibleName(f"{self.spec[3]}: {label.replace('&', '')}")
            tile.clicked.connect(lambda _c=False, v=value: self._pick(v))
            group.addButton(tile)
            flow.addWidget(tile)
            self.tiles[value] = tile
        text.addSpacing(SPACE_XS)
        text.addWidget(host)
        if target == "theme":
            from theme_dialog import CustomColorsPanel
            self.custom_panel = CustomColorsPanel(self.window.main)
            text.addWidget(self.custom_panel)
        main = self.window.main
        if target.endswith("_action"):
            getattr(main, target).toggled.connect(self._on_action_toggled)
        self.paint_tiles()

    def paint_tiles(self):
        import settings_skeletons
        main = self.window.main
        tokens = theme_for(main.config)
        for value, tile in self.tiles.items():
            tile.setIcon(QIcon(settings_skeletons.preview(self.spec[5], value, tokens,
                                                          main.config.get("custom_colors"))))

    def _tile_value(self):
        target = self.spec[5]
        main = self.window.main
        if target == "theme":
            return main.current_theme_key()
        if target.endswith("_action"):
            return "on" if getattr(main, target).isChecked() else "off"
        return main.config.get(target, next(iter(self.tiles)))

    def _pick(self, value):
        target = self.spec[5]
        main = self.window.main
        if target == "theme":
            main.choose_theme(value)
        elif target.endswith("_action"):
            getattr(main, target).setChecked(value == "on")
        else:
            self._set_config(target, value, {"timeline_range": "range", "list_view": "view"}.get(target))
        self.refresh()

    def retheme(self):
        """Neues Design: Symbol und Kachelbilder in den neuen Farben (ohne Neuaufbau)."""
        self.pic.setPixmap(icons.icon(self.icon_name, self.window.icon_color).pixmap(18, 18))
        if self.tiles:
            self.paint_tiles()

    def _choose_theme(self, key):
        main = self.window.main
        if key != main.current_theme_key():
            QTimer.singleShot(0, lambda: main.choose_theme(key))  # baut das Fenster neu auf

    def _sync_toggle(self, on):
        if self.control.isChecked() != on:
            _set_quiet(self.control, on)

    def _on_action_toggled(self, on):
        if self.tiles:
            self.refresh()
        else:
            self._sync_toggle(on)

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
        if key in ("booking_rate_status", "booking_target_percent"):
            import week_dialogs
            week_dialogs.update_rate_button(main)

    def refresh(self):
        kind, target, extra = self.spec[1], self.spec[5], self.spec[6]
        main = self.window.main
        if kind == "tiles":
            current = self._tile_value()
            for value, tile in self.tiles.items():
                tile.setChecked(value == current)
            if self.custom_panel is not None:
                self.custom_panel.setVisible(current == "custom")
            return
        if self.value is not None and extra:
            self.value.set_full_text(str(extra(main)))
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
        elif kind == "theme":
            self.control.blockSignals(True)
            self.control.setCurrentIndex(max(0, self.control.findData(main.current_theme_key())))
            self.control.blockSignals(False)


class _Tile(QFrame):
    """Datenquelle: Zeichen, Name, Schalter, Zustand und „Einrichten …“."""

    def __init__(self, window, spec):
        super().__init__()
        self.setObjectName("tile")
        self.window, self.spec = window, spec
        key, brand, name, desc, setup, _kind = spec
        main = window.main
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_L, SPACE_M, SPACE_L, SPACE_M)
        layout.setSpacing(SPACE_S)
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

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Zeitzeuge – Einstellungen")
        self.setObjectName("settings_window")
        # Maximieren erlauben: lange Seiten (Aufzeichnung, Darstellung) brauchen dann nicht zu blättern
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint, True)
        self.setMinimumSize(720, 480)
        # Mindestens 3 Kacheln nebeneinander ohne Scrollleiste, auf großen Bildschirmen mehr Platz
        screen = main.screen() if main is not None else None
        if screen is not None:
            free = screen.availableGeometry()
            self.resize(max(720, min(1280, int(free.width() * 0.85))),
                        max(480, min(900, int(free.height() * 0.85))))
        else:
            self.resize(1040, 660)
        theme = theme_for(main.config)
        self.icon_color = theme["text"]
        self.rows, self.tiles, self.tile_grids = [], [], []
        self.status, self.collapsed, self.status_pics = {}, {}, []
        self.prompt_settings = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(SPACE_L, SPACE_M, SPACE_L, SPACE_M)
        heading = QLabel("Einstellungen")
        heading.setObjectName("page_title")
        top.addWidget(heading)
        top.addSpacing(SPACE_XL)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Einstellung suchen, z. B. Minuten, VPN, PIN")
        self.search.setAccessibleName("Einstellungen durchsuchen")
        self.search.setClearButtonEnabled(True)
        self.search_action = self.search.addAction(icons.icon("search", theme["muted"]),
                                                   QLineEdit.ActionPosition.LeadingPosition)
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
        self.nav.setCurrentRow(0)

    # ---- Aufbau

    # Höchstbreite einer Seite (mit Rand): In breiten Fenstern stehen Text und Knopf/Zahlenfeld sonst
    # weit auseinander. Die Seite bleibt links an der Navigation, rechts davon ist frei.
    PAGE_MAX_WIDTH = 960

    def _scroll(self, widget):
        widget.setMaximumWidth(self.PAGE_MAX_WIDTH)
        holder = QWidget()
        holder.setObjectName("settings_page_holder")
        line = QHBoxLayout(holder)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(0)
        line.addWidget(widget, 1)
        line.addStretch(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(holder)
        return scroll

    def _section(self, layout, text, key=None):
        """Überschrift eines Abschnitts. Eingeklappte Abschnitte (COLLAPSED): Knopf mit Pfeil,
        die Zeilen darunter erst nach Klick. Gibt das Layout für die Zeilen zurück."""
        layout.addSpacing(SPACE_M)
        if key not in COLLAPSED:
            title = QLabel(text)
            title.setObjectName("section_title")
            layout.addWidget(title)
            return layout
        toggle = QToolButton()
        toggle.setObjectName("section_toggle")
        toggle.setText(text)
        toggle.setCheckable(True)
        toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.RightArrow)
        toggle.setAccessibleName(f"{text} aufklappen")
        layout.addWidget(toggle)
        box = QWidget()
        box.setObjectName("settings_page")
        inner = QVBoxLayout(box)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(SPACE_S)
        hint = QLabel(COLLAPSED[key])
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        inner.addWidget(hint)
        box.hide()
        layout.addWidget(box)

        def flip(on):
            box.setVisible(on)
            toggle.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        toggle.toggled.connect(flip)
        self.collapsed[key] = toggle
        return inner

    def _rows(self, layout, key):
        """Zeilen eines Bereichs, nach Abschnitten (Reihenfolge wie in ROWS)."""
        sections = []
        for spec in ROWS:
            if row_page(spec) == key and row_section(spec) not in sections:
                sections.append(row_section(spec))
        for section in sections:
            target = self._section(layout, section, f"{key}/{section}") if section else layout
            for spec in ROWS:
                if row_page(spec) == key and row_section(spec) == section:
                    row = _Row(self, spec)
                    self.rows.append(row)
                    target.addWidget(row)

    def _page(self, key, name, subtitle):
        page = QWidget()
        page.setObjectName("settings_page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(SPACE_2XL, SPACE_XL, SPACE_2XL, SPACE_XL)
        layout.setSpacing(SPACE_S)
        head = layout
        title = QLabel(name)
        title.setObjectName("page_title")
        head.addWidget(title)
        sub = QLabel(subtitle)
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        head.addWidget(sub)
        head.addSpacing(SPACE_S)
        if key == "home":
            self._status_rows(layout)
        if key == "about":
            layout.addWidget(self._about_card())
        if key == "prompts":
            from journal_dialogs import PromptSettings
            self.prompt_settings = PromptSettings(self.main.config)
            self.prompt_settings.changed.connect(self._prompts_changed)
            layout.addWidget(self.prompt_settings)
        self._rows(layout, key)
        if key == "sources":  # nach den Grundlagen die Quellen als Kacheln, nach Art
            for group, keys in TILE_GROUPS:
                self._section(layout, group)
                grid = QGridLayout()
                grid.setSpacing(SPACE_M)
                tiles = [_Tile(self, spec) for k in keys for spec in SOURCE_TILES if spec[0] == k]
                self.tiles += tiles
                self.tile_grids.append((grid, tiles))
                layout.addLayout(grid)
            self._tile_columns = 0
            self._place_tiles(3)
        layout.addStretch(1)
        return self._scroll(page)

    def _about_card(self):
        """Logo, Version, Build und Links oben auf der Info-Seite (früher eigenes Fenster
        „Über Zeitzeuge“; das Menü öffnet jetzt diese Seite)."""
        from version import build_details, full_version
        card = QFrame()
        card.setObjectName("setting_row")
        card.setAccessibleName("Über Zeitzeuge")
        line = QHBoxLayout(card)
        # Ränder, Logo-Platz und Textspalte wie bei den Zeilen darunter (_Row): Titel und Texte
        # aller Karten beginnen an derselben Kante
        line.setContentsMargins(SPACE_M + 2, SPACE_M, SPACE_M + 2, SPACE_M)
        line.setSpacing(SPACE_M)
        logo = QLabel()
        logo.setFixedSize(32, 32)
        logo.setPixmap(icons.app_icon(mt.resource_path).pixmap(32, 32))
        line.addWidget(logo, 0, Qt.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(SPACE_XS)
        name = QLabel("Zeitzeuge")
        name.setObjectName("row_title")
        texts.addWidget(name)
        # Version und Build in einer Zeile, in der Farbe der Beschreibungen der anderen Zeilen
        self.about_version = QLabel(" · ".join([f"Version {full_version()}", *build_details()]))
        self.about_version.setObjectName("hint")
        self.about_version.setTextInteractionFlags(Qt.TextSelectableByMouse)  # zum Kopieren für Fehlermeldungen
        self.about_version.setWordWrap(True)
        texts.addWidget(self.about_version)
        links = QLabel("<a href='https://github.com/fkroczak/Zeitzeuge/blob/main/CHANGELOG.md'>Was ist neu?</a>"
                       " &nbsp;·&nbsp; <a href='https://github.com/fkroczak/Zeitzeuge'>Projektseite</a>")
        links.setTextFormat(Qt.RichText)
        links.setOpenExternalLinks(True)
        links.setTextInteractionFlags(Qt.TextBrowserInteraction)
        texts.addWidget(links)
        line.addLayout(texts, 1)
        return card

    # ---- Übersicht: Zustand je Bereich

    STATUS = [("sources", "plug", "Aufzeichnung"), ("prompts", "bell", "Nachfragen"),
              ("booking", "gauge", "Buchung"), ("data", "shield", "Datenschutz")]

    def _status_rows(self, layout):
        title = QLabel("Zustand")
        title.setObjectName("section_title")
        layout.addWidget(title)
        for key, icon_name, name in self.STATUS:
            row = QFrame()
            row.setObjectName("setting_row")
            line = QHBoxLayout(row)
            line.setContentsMargins(SPACE_M + 2, SPACE_M, SPACE_M + 2, SPACE_M)
            line.setSpacing(SPACE_M)
            pic = QLabel()
            pic.setObjectName("row_icon")
            pic.setFixedSize(32, 32)
            pic.setContentsMargins(7, 7, 7, 7)  # 18-px-Symbol mittig in der 32-px-Kachel
            pic.setPixmap(icons.icon(icon_name, self.icon_color).pixmap(18, 18))
            self.status_pics.append((pic, icon_name))
            line.addWidget(pic, 0, Qt.AlignTop)
            texts = QVBoxLayout()
            texts.setSpacing(SPACE_XS)
            head = QLabel(name)
            head.setObjectName("row_title")
            texts.addWidget(head)
            state = QHBoxLayout()
            state.setSpacing(SPACE_S)
            mark = QLabel()
            mark.setFixedSize(16, 16)
            # eine Zeile, bei Platzmangel mit „…“ (voller Text als Hinweis): Breite unabhängig von
            # Schrift und Umbruch (unter Windows war die Übersicht sonst bei 960 × 540 zu breit)
            from prompt_card import _ElidedLabel as _OneLine
            text = _OneLine()
            text.setObjectName("hint")
            state.addWidget(mark)
            state.addWidget(text, 1)
            texts.addLayout(state)
            # Knopf unter dem Zustand statt daneben: Titel und Knopf teilen sich die Breite nicht,
            # so passt die Übersicht auch unter Windows (breitere Schrift) in 960 × 540
            button = QPushButton(f"{name} …")
            button.setAutoDefault(False)
            button.setAccessibleName(f"{name} öffnen")
            button.clicked.connect(lambda _c=False, k=key: self.show_page(k))
            texts.addWidget(button, 0, Qt.AlignLeft)
            line.addLayout(texts, 1)
            layout.addWidget(row)
            self.status[key] = (mark, text)

    def _status_text(self, key):
        """(Zustand ok/warn/off, Text, Begründung) für die Übersicht. Die Begründung steht als
        Tooltip auf Zeichen und Text: Warum ist es gelb, und was ist zu tun?"""
        main = self.main
        if key == "sources":
            states = [(spec[2], *tile_state(main, spec[0], spec[5])) for spec in SOURCE_TILES]
            on = len([s for _n, s, _w in states if s != "off"])
            problems = [f"{name}: {why}" for name, state, why in states if state == "warn"]
            text = f"{on} von {len(states)} Quellen an"
            if not problems:
                return "ok", text, "Alle eingeschalteten Quellen liefern Daten."
            return ("warn", f"{text} · {len(problems)} mit Problem",
                    "Mit Problem:\n" + "\n".join(problems) + "\n\nDetails und Abhilfe: Aufzeichnung …")
        if key == "prompts":
            count = main.open_prompt_count() if hasattr(main, "open_prompt_count") else 0
            summary = _prompt_summary(main)
            if summary == "aus":
                return "off", "Nachfragen aus", ""
            if count:
                return ("warn", f"{summary} · {count} offen",
                        f"{count} Nachfrage(n) noch nicht beantwortet. Du findest sie im Infobereich "
                        "unter „Offene Nachfragen“.")
            return "ok", summary, "Keine offenen Nachfragen."
        if key == "booking":
            import week_dialogs
            if not week_dialogs.has_m42(main):
                return "off", "Matrix42 nicht eingerichtet", ""
            try:
                info = week_dialogs.rate_info(main)
                text = info["text"].rsplit("  ", 1)[0]  # ohne Zeichen (✓, !) am Ende: das zeigt das Symbol
            except (KeyError, TypeError, ValueError, AttributeError):
                return "warn", "Quote gerade nicht lesbar", "Matrix42 hat noch keine Buchungen geliefert, " \
                    "aus denen sich die Quote rechnen lässt."
            tip = info["tip"].replace("\nKlick: Wochenabschluss", "")
            return ("ok" if info["level"] in ("ok", "over") else "warn"), text, tip
        if key == "data":
            try:
                _win, pin, recovery, _transfer, _where = main.protection_state()
            except Exception:  # Zustand darf die Einstellungen nie blockieren
                return "warn", "Zustand unbekannt", "Der Schutz der Daten ließ sich gerade nicht prüfen."
            ok = recovery != "fehlt noch"
            text = f"Verschlüsselt · PIN {pin} · Wiederherstellungsschlüssel {recovery}"
            why = ("Daten verschlüsselt, Wiederherstellungsschlüssel vorhanden." if ok else
                   "Es gibt noch keinen Wiederherstellungsschlüssel. Ohne ihn sind die Daten verloren, "
                   "wenn Windows-Konto oder PIN nicht mehr gehen. Anlegen unter Datenschutz …")
            return ("ok" if ok else "warn"), text, why
        return "off", "", ""

    def retheme(self):
        """Design gewechselt (auch eigene Farben): Symbole und Kachelbilder neu malen. Das Fenster
        bleibt stehen, mit Seite, Scrollstand und aufgeklapptem „Eigene Farben“."""
        tokens = theme_for(self.main.config)
        self.icon_color = tokens["text"]
        icon_of = {k: i for k, _n, i, _s in PAGES}
        for i in range(self.nav.count()):
            item = self.nav.item(i)
            item.setIcon(icons.icon(icon_of[item.data(Qt.UserRole)], self.icon_color))
        self.search_action.setIcon(icons.icon("search", tokens["muted"]))
        for pic, name in self.status_pics:
            pic.setPixmap(icons.icon(name, self.icon_color).pixmap(18, 18))
        for row in self.rows:
            row.retheme()
        if self.prompt_settings is not None:
            self.prompt_settings.retheme(tokens)
        self.refresh()

    def refresh_status(self):
        for key, (mark, text) in self.status.items():
            state, words, why = self._status_text(key)
            if state == "off":
                mark.clear()
            else:
                mark.setPixmap(icons.source_icon(state).pixmap(16, 16))
            text.set_full_text(words)
            tip = f"{words}\n\n{why}" if why else ""  # Begründung: warum gelb, was tun
            mark.setToolTip(tip)
            text.set_tip(tip)
            mark.setAccessibleDescription(why)

    def _prompts_changed(self):
        main = self.main
        mt.save_config(main.config)
        if getattr(main, "idle_watch", None):
            main.idle_watch.minutes = main.config.get("idle_prompt_minutes", 15)

    def _place_tiles(self, columns):
        """Kacheln in so vielen Spalten wie nebeneinander passen (1–3), sonst ragen sie rechts
        aus schmalen Fenstern (kleines Fenster, 150/200 % Anzeige)."""
        if columns == self._tile_columns:
            return
        self._tile_columns = columns
        for grid, tiles in self.tile_grids:
            for tile in tiles:
                grid.removeWidget(tile)
            for i, tile in enumerate(tiles):
                grid.addWidget(tile, i // columns, i % columns)
            for col in range(3):
                grid.setColumnStretch(col, 1 if col < columns else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_tiles()

    def _fit_tiles(self):
        # Erst wenn die Seite zu sehen ist, hat das Stylesheet die Kacheln fertig vermessen
        if self.tiles and self.tiles[0].isVisible():
            spacing = self.tile_grids[0][0].spacing()
            need = max(t.minimumSizeHint().width() for t in self.tiles) + spacing
            # Platz rechts der Navigation abzüglich Seitenrand (2 × 28) und Scrollbalken
            free = min(self.width() - self.nav.width() - 12, self.PAGE_MAX_WIDTH) - 56 + spacing
            self._place_tiles(max(1, min(3, free // need)))

    def _results_page(self):
        page = QWidget()
        page.setObjectName("settings_page")
        self.results_layout = QVBoxLayout(page)
        self.results_layout.setContentsMargins(SPACE_2XL, SPACE_XL, SPACE_2XL, SPACE_XL)
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
        self._fit_tiles()
        self.refresh()

    def show_page(self, key):
        """Bereich zeigen, z. B. show_page("sources"). Frühere Namen gelten weiter (PAGE_ALIASES)."""
        key = PAGE_ALIASES.get(key, key)
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == key:
                self.nav.setCurrentRow(i)
                self._show_row(i)
                return

    def show_custom_colors(self):
        """Seite „Darstellung“ mit aufgeklapptem „Eigene Farben“ zeigen."""
        row = next((r for r in self.rows if r.custom_panel is not None), None)
        if row is None:
            return
        self.show_page("view")
        row.refresh()
        QTimer.singleShot(0, lambda: row.parentWidget() and self._scroll_to(row))

    def _scroll_to(self, widget):
        area = widget.parentWidget()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        if area is not None:
            area.ensureWidgetVisible(widget)

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
        # Übersicht wiederholt nur Zeilen anderer Bereiche: nicht doppelt finden
        found = [spec for spec in ROWS if row_page(spec) != "home"
                 and matches(text, spec[3], spec[4], names[row_page(spec)], row_section(spec), _unit_words(spec))]
        tiles = [spec for spec in SOURCE_TILES if matches(text, spec[2], spec[3], "Aufzeichnung Datenquellen")]
        topics = [t for t in PROMPT_TOPICS if matches(text, t[0], t[1], "Nachfragen")]
        links = [(icons.brand_icon(spec[1]), f"  {spec[2]} – Aufzeichnung", "sources") for spec in tiles]
        links += [(icons.icon("bell", self.icon_color), f"  {title} – Nachfragen", "prompts")
                  for title, _words in topics]
        for icon, label, page in links:
            row = QPushButton(icon, label)
            row.setObjectName("result_link")
            row.setAutoDefault(False)
            row.clicked.connect(lambda _c=False, p=page: self.show_page(p))
            self.results_box.addWidget(row)
        for spec in found:
            self.results_box.addWidget(_Row(self, spec, show_page=True))
        count = len(found) + len(links)
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
        if self.isVisible():
            self.refresh_status()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()  # Fenster bleibt nach dem Schließen erhalten: nicht alle 3 s aufwachen

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start(3000)
        self._fit_tiles()
        self.refresh()
