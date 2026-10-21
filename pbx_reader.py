"""
3CX-Anrufliste direkt aus Zeitzeuge lesen (ohne Chrome/Tampermonkey).

Zeitzeuge öffnet den 3CX-Webclient in einem eingebauten, unsichtbaren Browser.
Beim ersten Mal meldest du dich in einem Zeitzeuge-Fenster an; die Anmeldung
wird wie in einem normalen Browser gespeichert (Ordner 3cx_profil).
Jede Minute wird die Anrufliste gelesen. Ton, Mikrofon, Kamera und
Benachrichtigungen sind gesperrt, damit dort nichts klingelt.
"""

import json
import os
from datetime import datetime

from PyQt5.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtWidgets import QDialog, QLabel, QVBoxLayout
from PyQt5.QtWebEngineWidgets import (QWebEnginePage, QWebEngineProfile,
                                      QWebEngineView)

from call_import import merge_calls

PARSER_START = "// ---- ANRUFLISTE LESEN: START ----"
PARSER_END = "// ---- ANRUFLISTE LESEN: ENDE ----"


def build_reader_js(userscript_text):
    """Den Lese-Teil aus dem Tampermonkey-Skript nehmen und als Abfrage verpacken."""
    start = userscript_text.index(PARSER_START)
    end = userscript_text.index(PARSER_END)
    parser = userscript_text[start:end]
    return (
        "(function(){" + parser +
        "const login = !!document.querySelector('input[type=password]');"
        "return JSON.stringify({login: login, url: location.href, calls: login ? [] : sammeln()});"
        "})()"
    )


class _QuietPage(QWebEnginePage):
    """Seite ohne Ton und ohne Zugriff auf Mikrofon/Kamera/Benachrichtigungen."""

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.setAudioMuted(True)
        self.featurePermissionRequested.connect(
            lambda origin, feature: self.setFeaturePermission(
                origin, feature, QWebEnginePage.PermissionDeniedByUser
            )
        )

    def javaScriptConsoleMessage(self, level, message, line, source):
        pass  # Konsole der 3CX-Seite nicht ausgeben


class PbxReader(QObject):
    # Nach jedem Lesen: Status-Text, Anzahl neuer Anrufe
    status_changed = pyqtSignal(str)
    calls_added = pyqtSignal(int)
    login_required = pyqtSignal()

    def __init__(self, base_url, calls_file, profile_dir, userscript_text, parent=None):
        super().__init__(parent)
        self.base_url = base_url.strip().rstrip("/")
        self.calls_file = calls_file
        self.js = build_reader_js(userscript_text)
        self.needs_login = False
        self.last_read = None
        self.last_count = 0
        self.status = "Startet …"
        self._unanswered = 0  # Abfragen ohne Antwort vom Browser

        self.profile = QWebEngineProfile("zeitzeuge-3cx", self)
        self.profile.setPersistentStoragePath(profile_dir)
        self.profile.setCachePath(os.path.join(profile_dir, "cache"))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)

        self.view = QWebEngineView()
        self.view.setAttribute(Qt.WA_DontShowOnScreen)  # "sichtbar", aber nicht auf dem Bildschirm
        self.page = _QuietPage(self.profile, self.view)
        self.view.setPage(self.page)
        # Absturz der Seite: nach kurzer Pause neu laden
        self.page.renderProcessTerminated.connect(
            lambda *_: (self._set_status("3CX: Browser abgestürzt, lade neu"),
                        QTimer.singleShot(3000, self.open_call_list))
        )
        self.view.resize(1100, 2400)  # hoch, damit viele Einträge geladen werden
        self.view.show()

        self.read_timer = QTimer(self)
        self.read_timer.timeout.connect(self.read)
        self.reload_timer = QTimer(self)
        self.reload_timer.timeout.connect(self.open_call_list)
        self._login_dialog = None

    def call_list_url(self):
        return f"{self.base_url}/#/call_history/all"

    def start(self):
        self.open_call_list()
        self.read_timer.start(60 * 1000)          # jede Minute lesen
        self.reload_timer.start(15 * 60 * 1000)   # alle 15 Minuten neu laden
        QTimer.singleShot(15 * 1000, self.read)   # erstes Lesen nach dem Laden

    def stop(self):
        self.read_timer.stop()
        self.reload_timer.stop()
        self.page.setUrl(QUrl("about:blank"))

    def open_call_list(self):
        if self._login_dialog:  # während der Anmeldung nicht neu laden
            return
        self.page.setUrl(QUrl(self.call_list_url()))

    def read(self):
        # Antwortet der Browser mehrmals nicht, Seite neu laden
        if self._unanswered >= 3:
            self._unanswered = 0
            self._set_status("3CX: Browser reagiert nicht, lade neu")
            self.page.triggerAction(QWebEnginePage.Stop)
            self.open_call_list()
            return
        self._unanswered += 1
        self.page.runJavaScript(self.js, self._on_result)

    def _set_status(self, text):
        self.status = text
        self.status_changed.emit(text)

    def _on_result(self, raw):
        self._unanswered = 0
        try:
            data = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            data = None
        if not data:
            self._set_status("3CX: Seite lädt noch")
            return

        if data["login"]:
            if not self.needs_login:
                self.needs_login = True
                self.login_required.emit()
            self._set_status("3CX: Anmeldung nötig")
            return
        self.needs_login = False

        calls = data["calls"]
        if not calls:
            if "call_history" not in data["url"]:
                self.open_call_list()
            self._set_status("3CX: keine Anrufe gefunden")
            return

        added = merge_calls(self.calls_file, calls)
        self.last_read = datetime.now()
        self.last_count = len(calls)
        self._set_status(f"3CX gelesen {self.last_read:%H:%M} ({len(calls)} Anrufe)")
        if added:
            self.calls_added.emit(added)

    def show_login(self, parent=None):
        """3CX im Fenster zeigen (zum Anmelden oder Nachsehen)."""
        dialog = QDialog(parent)
        dialog.setWindowTitle("3CX – Anmeldung für Zeitzeuge")
        dialog.resize(1000, 760)
        layout = QVBoxLayout(dialog)
        hint = QLabel("Melde dich hier bei 3CX an. Danach kannst du das Fenster schließen – "
                      "Zeitzeuge liest die Anrufliste im Hintergrund weiter.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.view.hide()
        self.view.setAttribute(Qt.WA_DontShowOnScreen, False)
        self.view.setMinimumSize(0, 0)
        layout.addWidget(self.view, 1)
        self.view.show()
        if self.page.url().isEmpty() or self.page.url().toString() == "about:blank":
            self.open_call_list()

        self._login_dialog = dialog
        dialog.exec_()
        self._login_dialog = None

        # Browser wieder unsichtbar im Hintergrund weiterlaufen lassen
        layout.removeWidget(self.view)
        self.view.setParent(None)
        self.view.setAttribute(Qt.WA_DontShowOnScreen)
        self.view.resize(1100, 2400)
        self.view.show()
        self.open_call_list()
        QTimer.singleShot(10 * 1000, self.read)
