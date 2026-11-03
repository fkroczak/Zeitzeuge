"""Einrichtungsassistent: beim ersten Start alle Datenquellen nacheinander durchgehen.

Seite 1 fragt ab, was du nutzen willst. Danach kommt für jede gewählte Quelle eine Seite
mit Erklärung, was Zeitzeuge auf diesem PC gefunden hat, und dem Knopf zur Einrichtung
(dieselben Dialoge wie unter Einstellungen → Datenquellen → Einrichten). Zum Schluss eine
Übersicht. Wieder aufrufen: Einstellungen → Datenquellen → Einrichtungsassistent …

Der Assistent schaltet über die Funktionen des Hauptfensters (toggle_source usw.), also
genau wie das Menü. Nur über main_timeline laden.
"""
import glob
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from theme import prose
import main_timeline as mt  # save_config zur Laufzeit von dort (Tests ersetzen sie dort)


def _exists(paths):
    """Erste vorhandene Datei oder Ordner aus der Liste (Umgebungsvariablen aufgelöst)."""
    for p in paths or []:
        if isinstance(p, str):
            p = os.path.expandvars(p)
            if os.path.exists(p) or glob.glob(p):
                return p
    return ""


def _browser():
    try:
        from pbx_reader import find_browser
        return find_browser() or ""
    except Exception:  # Suche darf den Assistenten nie aufhalten
        return ""


def _sophos_log(cfg, name):
    for d in cfg.get("sophos_connect_dirs") or []:
        path = os.path.join(os.path.expandvars(d), name)
        if os.path.exists(path):
            return path
    return ""


def _found(path, what="Gefunden"):
    return f"{what}: {path}" if path else ""


# Gruppen und Quellen. key: Schalter in der Config (None: nur Einrichtung, z. B. Arbeitszeiten).
# detect(cfg) -> Text, was auf dem PC gefunden wurde ("" = nichts gefunden).
# setup: Name der Methode im Hauptfenster, die den Einrichtungsdialog öffnet.
GROUPS = [
    ("Fernwartung", [
        dict(id="teamviewer", key="teamviewer_enabled", title="TeamViewer",
             text="Liest die TeamViewer-Verbindungen (Connections.txt) mit ID, Beginn und Ende. "
                  "Den Kunden zu einer ID lernt Zeitzeuge, wenn du die Verbindung dokumentierst.",
             detect=lambda c: _found(_exists(c.get("teamviewer_paths"))),
             missing="Connections.txt nicht gefunden. Liegt sie woanders, trag den Pfad unter "
                     "„Einrichten …“ ein.",
             setup="edit_teamviewer_settings", button="Pfad einrichten …", file=True),
        dict(id="rdm", key="rdm_enabled", title="Remote Desktop Manager (RDM)",
             text="Liest RDP-, SSH-, VPN- und Website-Verbindungen aus Connections.log, dazu "
                  "angezeigte Passwörter, Benutzernamen und OTP.",
             detect=lambda c: _found(_exists(c.get("rdm_paths"))),
             missing="Connections.log nicht gefunden. Liegt sie woanders, trag den Pfad unter "
                     "„Einrichten …“ ein.",
             setup="edit_rdm_settings", button="Pfad einrichten …", file=True),
        dict(id="rdmbetter", key="rdmbetter_enabled", title="RDM Better",
             text="Liest aus launcher.log, wann du eine Remotedesktop-Verbindung gestartet hast. "
                  "Das Ende kommt aus der Aufzeichnung „Remotedesktop (mstsc)“.",
             detect=lambda c: _found(_exists(c.get("rdmbetter_paths"))),
             missing="launcher.log nicht gefunden. Liegt sie woanders, trag den Pfad unter "
                     "„Einrichten …“ ein.",
             setup="edit_rdmbetter_settings", button="Pfad einrichten …", file=True),
        dict(id="mstsc", key="mstsc_enabled", title="Remotedesktop (mstsc)",
             text="Zeitzeuge prüft alle 30 Sekunden, welche Remotedesktopverbindungen offen sind, "
                  "und zeigt sie mit Ziel, Beginn und Ende wie die Verbindungen aus RDM.",
             detect=lambda c: "Läuft auf jedem Windows-PC.", missing="",
             setup="edit_mstsc_settings", button="Einrichten …"),
        dict(id="shell", key="shell_enabled", title="SSH und PowerShell",
             text="Offene SSH-Sitzungen (ssh, PuTTY, KiTTY, plink, WinSCP) und PowerShell-"
                  "Fernsitzungen, alle 30 Sekunden, mit Ziel, Beginn und Ende.",
             detect=lambda c: "", missing="",
             setup="edit_shell_settings", button="Einrichten …"),
    ]),
    ("VPN", [
        dict(id="sophos", key="sophos_enabled", title="Sophos Connect",
             text="Liest die VPN-Verbindungen aus den Sophos-Logs mit dem Namen, den du der "
                  "Verbindung gegeben hast. Zusätzlich prüft Zeitzeuge alle 30 Sekunden selbst, "
                  "ob ein VPN-Adapter verbunden ist.",
             detect=lambda c: _found(_sophos_log(c, "scvpn.log") or _exists(c.get("sophos_connect_dirs"))),
             missing="Sophos Connect ist auf diesem PC nicht installiert.",
             setup="edit_sophos_settings", button="Ordner einrichten …", file=True),
        dict(id="forti", key="forti_enabled", title="FortiClient",
             text="Liest jede Verbindung mit ihrem Namen, Beginn und Ende aus FortiVPN_1.log "
                  "von FortiClient. Fehlt die Datei, nimmt Zeitzeuge die "
                  "Adapter-Meldungen aus Sophos' charon.log und prüft alle 30 Sekunden selbst, "
                  "ob der Fortinet-Adapter verbunden ist.",
             detect=lambda c: _found(_exists(c.get("forti_paths")) or _sophos_log(c, "charon.log")),
             missing="Keine Logs von FortiClient gefunden. Eigene Pfade trägst du unter "
                     "„Einrichten …“ ein.",
             setup="edit_forti_settings", button="Pfade einrichten …", file=True),
        dict(id="vpn", key="vpn_enabled", title="Weitere VPN-Logs (OpenVPN …)",
             text="Logdateien oder Ordner weiterer VPN-Clients, z. B. OpenVPN GUI, OpenVPN Connect "
                  "oder Sophos SSL VPN.",
             detect=lambda c: _found(_exists(c.get("vpn_paths"))),
             missing="Keine bekannten Logs gefunden. Eigene Pfade trägst du unter „Einrichten …“ ein.",
             setup="edit_vpn_settings", button="Pfade einrichten …", file=True),
    ]),
    ("Firmen-Webseiten (im Hintergrund mit Edge)", [
        dict(id="pbx", key="pbx_reader_enabled", title="3CX-Anrufe",
             text="Zeitzeuge liest die Anrufliste aus dem 3CX-Webclient, ohne dass du die Seite "
                  "offen hast. Unter „Einrichten …“ prüfst du die Adresse und meldest dich einmal "
                  "an; die Anmeldung bleibt gespeichert.",
             detect=lambda c: _found(_browser(), "Browser"),
             missing="Microsoft Edge oder Google Chrome nicht gefunden. Ohne Browser geht 3CX nicht.",
             setup="open_pbx_settings", button="3CX einrichten und anmelden …"),
        dict(id="itm", key="itm_reader_enabled", title="ITM-Zeiterfassung (Personalzeiten)",
             text="Liest deine gestempelten Zeiten. Die Timeline hebt dann deine Arbeitszeit "
                  "hervor, Pausen sind abgedunkelt. Unter „Einrichten …“ trägst du Benutzername "
                  "und Mandant ein (Passwort wird nie gespeichert) oder meldest dich in Edge an.",
             detect=lambda c: _found(c.get("itm_url", ""), "Adresse"),
             missing="", setup="open_itm_settings", button="ITM einrichten und anmelden …"),
        dict(id="m42", key="m42_reader_enabled", title="Matrix42-Buchungen (nur Firmennetz)",
             text="Liest deine Buchungen aus dem Matrix42-Kalender und zeigt Personalzeit ohne "
                  "Buchung. Unter „Einrichten …“ fügst du die Adresse der Kalenderseite ein "
                  "(Service Desk → Kalender, aus der Adresszeile kopieren).",
             detect=lambda c: _found(_browser(), "Browser"),
             missing="Microsoft Edge oder Google Chrome nicht gefunden. Ohne Browser geht Matrix42 nicht.",
             setup="open_m42_settings", button="Matrix42 einrichten …"),
    ]),
    ("Microsoft 365", [
        dict(id="outlook", key="outlook_enabled", title="Outlook (Termine, gesendete Mails)",
             text="Liest Termine, Teams-Besprechungen und gesendete Mails aus dem klassischen "
                  "Outlook. Gespeichert werden nur Betreff, Zeit, Ort und die Domains der "
                  "Teilnehmer, keine Adressen und keine Mailtexte.",
             detect=lambda c: "", missing="",
             setup="open_outlook_settings", button="Outlook einrichten …"),
        dict(id="teams", key="teams_calls_enabled", title="Teams-Anrufe",
             text="Erkennt Teams-Anrufe an der Mikrofon-Nutzung von Teams und an den Teams-Logs. "
                  "Sie stehen in der Zeile „Tel“ wie 3CX-Anrufe.",
             detect=lambda c: "", missing="",
             setup="open_teams_settings", button="Teams einrichten …"),
    ]),
    ("Dieser PC", [
        dict(id="tracking", key="tracking_enabled", title="Aktive Fenster aufzeichnen",
             text="Alle 5 Sekunden merkt sich Zeitzeuge das aktive Fenster (z. B. RDP-Sitzung, "
                  "Browser-Tab, Outlook). Ohne Maus und Tastatur oder bei gesperrtem PC wird nichts "
                  "aufgezeichnet. Mit dem Fenster-Filter lässt du private Programme weg.",
             detect=lambda c: "", missing="",
             setup="edit_tracking_filters", button="Fenster-Filter …"),
        dict(id="pcstate", key="pcstate_enabled", title="PC gesperrt / Ruhezustand",
             text="Wann der PC gesperrt, im Ruhezustand, aus oder abgemeldet war. Sperren prüft "
                  "Zeitzeuge selbst, den Rest liest es aus dem Windows-Ereignisprotokoll.",
             detect=lambda c: "", missing="",
             setup="edit_pcstate_settings", button="Einrichten …"),
        dict(id="wlan", key="wlan_enabled", title="WLAN",
             text="Mit welchem WLAN der PC verbunden war, z. B. beim Kunden vor Ort.",
             detect=lambda c: "", missing="",
             setup="edit_wlan_settings", button="Einrichten …"),
        dict(id="files", key="recent_files_enabled", title="Zuletzt geöffnete Dateien",
             text="Dateiname und Uhrzeit aus der Liste „Zuletzt verwendet“ von Windows. "
                  "Inhalte liest Zeitzeuge nicht.",
             detect=lambda c: _found(_exists(c.get("recent_files_dirs"))), missing="",
             setup="edit_recent_files_settings", button="Ordner einrichten …", file=True),
        dict(id="browser", key="browser_enabled", title="Browser-Verlauf",
             text="Aus dem Verlauf von Edge und Chrome nur Domains und Ticketnummern, "
                  "keine Adressen und keine Seitentitel.",
             detect=lambda c: _found(_exists(c.get("browser_paths"))),
             missing="Kein Verlauf von Edge oder Chrome gefunden.",
             setup="edit_browser_settings", button="Pfade einrichten …", file=True),
        dict(id="work", key=None, title="Arbeitszeiten",
             text="Arbeitszeit je Wochentag. Sie gilt, solange keine Personalzeiten aus der "
                  "ITM-Zeiterfassung kommen.",
             detect=lambda c: "", missing="",
             setup="edit_work_hours", button="Arbeitszeiten einstellen …"),
        dict(id="ai", key=None, title="KI-Vorschläge (Claude)",
             text="Auf Knopfdruck (F6) ordnet Claude die Spuren des Tages zu Tätigkeiten. Dafür "
                  "brauchst du einen API-Schlüssel von Anthropic. Ohne KI ordnen feste Regeln zu.",
             detect=lambda c: "", missing="",
             setup="edit_ai_settings", button="KI einrichten …"),
        dict(id="recovery", key=None, title="Wiederherstellungsschlüssel",
             text="Deine Daten liegen verschlüsselt in der Datenbank. Auf diesem PC öffnet sie "
                  "deine Windows-Anmeldung. Für einen neuen PC oder ein anderes Windows-Konto "
                  "brauchst du den Wiederherstellungsschlüssel. Leg ihn in RDM ab.",
             detect=lambda c: "", missing="",
             setup="new_recovery_code", button="Schlüssel erzeugen …"),
    ]),
]

SOURCES = {s["id"]: s for _g, items in GROUPS for s in items}


class SetupWizard(QDialog):
    """Assistent über dem Hauptfenster (main), Schritt für Schritt."""

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Zeitzeuge einrichten")
        self.setMinimumSize(620, 480)
        cfg = main.config
        self.found = {sid: s["detect"](cfg) for sid, s in SOURCES.items()}
        self.has_recovery = bool(getattr(main, "data_store", None) and main.data_store.has_recovery())

        layout = QVBoxLayout(self)
        self.step_label = QLabel()
        self.step_label.setObjectName("hint")
        layout.addWidget(self.step_label)
        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack, 1)
        buttons = QHBoxLayout()
        self.cancel_button = QPushButton("&Abbrechen")
        self.cancel_button.clicked.connect(self.reject)
        self.back_button = QPushButton("< &Zurück")
        self.back_button.clicked.connect(self.back)
        self.next_button = QPushButton("&Weiter >")
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self.next)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.next_button)
        layout.addLayout(buttons)

        self.choices = {}  # Quelle -> Häkchen auf der Auswahlseite
        self.stack.addWidget(self._choice_page())
        self.steps = []    # gewählte Quellen in Reihenfolge
        self.step_pages = {}
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        self.index = 0
        self._show()

    # ---------------------- Seiten -----------------------------------------------

    def _default(self, sid):
        """Vorauswahl: Dateiquellen, wenn auf dem PC gefunden; sonst wie eingestellt."""
        s = SOURCES[sid]
        if sid == "recovery":
            return not self.has_recovery
        if sid == "work":
            return not self.main.config.get("itm_reader_enabled")
        if sid == "ai":
            return False
        if s.get("file"):
            return bool(self.found[sid])
        return bool(self.main.config.get(s["key"], False))

    def _choice_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        intro = QLabel("<b>Was willst du nutzen?</b><br>Zeitzeuge geht danach jede gewählte Quelle "
                       "mit dir durch. Vorausgewählt ist, was auf diesem PC gefunden wurde. "
                       "Alles lässt sich später unter Einstellungen → Datenquellen ändern.")
        intro.setWordWrap(True)
        prose(intro)
        intro.setTextFormat(Qt.RichText)
        outer.addWidget(intro)
        scroll = QScrollArea(page)
        scroll.setWidgetResizable(True)
        inner = QWidget()
        col = QVBoxLayout(inner)
        for group, items in GROUPS:
            box = QGroupBox(group)
            rows = QVBoxLayout(box)
            for s in items:
                if s["id"] == "recovery" and self.has_recovery:
                    continue
                text = s["title"]
                if s.get("file") or s["id"] in ("pbx", "m42"):
                    text += "  (gefunden)" if self.found[s["id"]] else "  (nicht gefunden)"
                check = QCheckBox(text)
                check.setChecked(self._default(s["id"]))
                check.setToolTip(s["text"])
                rows.addWidget(check)
                self.choices[s["id"]] = check
            col.addWidget(box)
        col.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        return page

    def _step_page(self, sid):
        s = SOURCES[sid]
        page = QWidget()
        col = QVBoxLayout(page)
        title = QLabel(f"<h3>{s['title']}</h3>")
        title.setTextFormat(Qt.RichText)
        col.addWidget(title)
        text = QLabel(s["text"])
        text.setWordWrap(True)
        prose(text)
        col.addWidget(text)
        found = self.found[sid] or s.get("missing", "")
        if found:
            hint = QLabel(("✓ " if self.found[sid] else "! ") + found)
            hint.setWordWrap(True)
            hint.setObjectName("hint")
            hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
            col.addWidget(hint)
        page.use = None
        if s["key"]:
            page.use = QCheckBox(f"{s['title']} verwenden")
            page.use.setChecked(True)
            col.addWidget(page.use)
        page.state = QLabel()
        page.state.setObjectName("hint")
        page.state.setWordWrap(True)
        col.addWidget(page.state)
        if s.get("setup"):
            button = QPushButton(s.get("button", "Einrichten …"))
            button.clicked.connect(lambda _c=False, i=sid: self.run_setup(i))
            row = QHBoxLayout()
            row.addWidget(button)
            row.addStretch(1)
            col.addLayout(row)
            page.setup_button = button
        col.addStretch(1)
        return page

    def _summary_page(self):
        page = QWidget()
        col = QVBoxLayout(page)
        title = QLabel("<h3>Fertig</h3>")
        title.setTextFormat(Qt.RichText)
        col.addWidget(title)
        col.addWidget(self.summary)
        col.addStretch(1)
        return page

    # ---------------------- Ablauf -----------------------------------------------

    def _pages(self):
        return [self.stack.widget(i) for i in range(self.stack.count())]

    def _show(self):
        self.stack.setCurrentIndex(self.index)
        total = len(self.steps)
        if self.index == 0:
            self.step_label.setText("Schritt 1: Auswahl")
        elif self.index <= total:
            sid = self.steps[self.index - 1]
            self.step_label.setText(f"Schritt {self.index + 1} von {total + 2}: {SOURCES[sid]['title']}")
            self._update_state(sid)
        else:
            self.step_label.setText(f"Schritt {total + 2} von {total + 2}: Übersicht")
            self.summary.setText(self.summary_html())
        self.back_button.setEnabled(self.index > 0)
        last = self.index == self.stack.count() - 1 and self.index > 0
        self.next_button.setText("&Fertig" if last else "&Weiter >")
        self.cancel_button.setVisible(not last)

    def next(self):
        if self.index == 0:
            self._build_steps()
        elif self.index <= len(self.steps):
            self._apply_step(self.steps[self.index - 1])
        if self.index >= self.stack.count() - 1:
            self.accept()
            return
        self.index += 1
        self._show()

    def back(self):
        if self.index > 0:
            self.index -= 1
            self._show()

    def _build_steps(self):
        """Nach der Auswahl: abgewählte Quellen ausschalten, Seiten für die gewählten anlegen."""
        chosen = [sid for sid, check in self.choices.items() if check.isChecked()]
        for sid, check in self.choices.items():
            if not check.isChecked() and SOURCES[sid]["key"]:
                self.set_source(sid, False)
        for page in self._pages()[1:]:  # Zurück auf die Auswahl und neu gewählt
            self.stack.removeWidget(page)
            page.deleteLater()
        self.steps = chosen
        self.step_pages = {}
        for sid in chosen:
            page = self._step_page(sid)
            self.step_pages[sid] = page
            self.stack.addWidget(page)
        self.stack.addWidget(self._summary_page())

    def _apply_step(self, sid):
        page = self.step_pages[sid]
        if page.use is not None:
            self.set_source(sid, page.use.isChecked())

    def is_on(self, sid):
        key = SOURCES[sid]["key"]
        if sid == "tracking":
            return self.main.tracker is not None or bool(self.main.config.get(key))
        return bool(self.main.config.get(key))

    def set_source(self, sid, on):
        """Wie im Menü schalten (startet oder stoppt die Leser)."""
        key = SOURCES[sid]["key"]
        if not key or self.is_on(sid) == on:
            return
        if sid == "tracking":
            self.main.tracking_action.setChecked(on)
        else:
            self.main.toggle_source(key, on)
        self.main.sync_source_actions()

    def run_setup(self, sid):
        """Einrichtungsdialog der Quelle öffnen. Dabei die Quelle einschalten, damit die
        Anmeldung gleich klappt (Häkchen „verwenden“ bleibt maßgeblich beim Weiter)."""
        s = SOURCES[sid]
        page = self.step_pages.get(sid)
        if page is not None and page.use is not None and page.use.isChecked() and s["key"]:
            if sid in ("pbx", "itm", "m42"):  # Dialog zeigt das Häkchen schon gesetzt
                self.main.config[s["key"]] = True
        method = getattr(self.main, s["setup"])
        if sid == "recovery":
            method(self)
        else:
            method()
        if sid in ("pbx", "itm", "m42"):  # abgebrochen: Leser läuft nicht, dann auch nicht an
            attr = {"pbx": "pbx_reader", "itm": "itm_reader", "m42": "m42_reader"}[sid]
            running = getattr(self.main, attr, None) is not None
            if bool(self.main.config.get(s["key"])) != running:
                self.main.config[s["key"]] = running
                mt.save_config(self.main.config)
            self.main.sync_source_actions()
        if page is not None and page.use is not None and s["key"]:
            page.use.setChecked(self.is_on(sid) or page.use.isChecked())
        self._update_state(sid)

    def _update_state(self, sid):
        page = self.step_pages.get(sid)
        if page is None:
            return
        text = ""
        if sid in ("pbx", "itm", "m42"):
            attr = {"pbx": "pbx_reader", "itm": "itm_reader", "m42": "m42_reader"}[sid]
            reader = getattr(self.main, attr, None)
            text = f"Stand: {reader.status}" if reader and getattr(reader, "status", "") else (
                "Stand: noch nicht eingerichtet. Mit „Weiter“ schaltet Zeitzeuge es ein, die "
                "Anmeldung kommt dann über den Infobereich.")
        elif sid == "recovery":
            done = self.main.data_store.has_recovery()
            text = "Stand: angelegt ✓" if done else "Stand: fehlt noch"
        page.state.setText(text)

    def state_text(self, sid):
        s = SOURCES[sid]
        if sid == "recovery":
            return "angelegt" if self.main.data_store.has_recovery() else "fehlt noch"
        if not s["key"]:
            return "eingestellt" if sid in self.steps else "übersprungen"
        return "an" if self.is_on(sid) else "aus"

    def summary_html(self):
        rows = []
        for _group, items in GROUPS:
            for s in items:
                if s["id"] == "recovery" and self.has_recovery:
                    continue
                state = self.state_text(s["id"])
                mark = "✓" if state in ("an", "angelegt", "eingestellt") else "–"
                rows.append(f"<tr><td>{mark}</td><td>{s['title']}</td><td>{state}</td></tr>")
        return ("Zeitzeuge ist eingerichtet. So steht es jetzt:"
                "<table cellspacing='4'>" + "".join(rows) + "</table><br>"
                "Den Assistenten findest du wieder unter <b>Einstellungen → Datenquellen → "
                "Einrichtungsassistent …</b>")
