"""Statuszeile: Anzeige je Datenquelle (Haken, gelbes Dreieck, Uhr) und Klick zur Lösung."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

import main_timeline  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


class FakeReader:
    """Steht für den 3CX- bzw. ITM-Leser, ohne Edge."""
    def __init__(self, state, why, needs_login=False):
        self.state, self.why, self.needs_login = state, why, needs_login
        self.status = f"Test: {why}"
        self.logins = 0

    def health(self):
        return self.state, self.why

    def show_login(self, _parent=None):
        self.logins += 1

    def day(self, _date):
        return None


app = QApplication(sys.argv)
app.setStyle(main_timeline.AppStyle())
window = main_timeline.TimelineApp()
window.show()
buttons = window.source_buttons

# Ohne Leser: keine Anzeige für 3CX und ITM
window.update_source_indicators()
assert buttons["pbx"].isHidden() and buttons["itm"].isHidden()

# 3CX braucht eine Anmeldung, ITM läuft
window.pbx_reader = FakeReader("warn", "Anmeldung nötig", needs_login=True)
window.itm_reader = FakeReader("ok", "17:53")
window.update_source_indicators()
pbx, itm = buttons["pbx"], buttons["itm"]
assert not pbx.isHidden() and pbx.text() == "3CX: Anmeldung nötig", pbx.text()
assert not itm.isHidden() and itm.text() == "ITM 17:53", itm.text()
assert not pbx.icon().isNull() and not itm.icon().isNull()
assert "Problem" in pbx.accessibleName() and "läuft" in itm.accessibleName()
assert "anzumelden" in pbx.toolTip()

# Nebeneinander in der Statuszeile, vor "Aufzeichnung aktiv"
assert pbx.y() == itm.y() == window.tracking_button.y()
assert pbx.x() < itm.x() < window.tracking_button.x()

# Klick führt zur Anmeldung
calls = []
window.show_pbx_login = lambda: calls.append("login")
pbx.click()
assert calls == ["login"], calls

# Offline: gelbes Dreieck mit Grund
window.pbx_reader = FakeReader("warn", "offline")
window.update_source_indicators()
assert pbx.text() == "3CX: offline"

# Fehlende Logs (TeamViewer) werden angezeigt, Klick öffnet die Pfade
window.timeline.missing_sources = lambda: ["TeamViewer"]
window.timeline.loading = False
window.update_source_indicators()
assert not buttons["logs"].isHidden() and "TeamViewer" in buttons["logs"].text()
opened = []
window.edit_teamviewer_settings = lambda: opened.append("tv")
buttons["logs"].click()
assert opened == ["tv"]

window.pbx_reader = window.itm_reader = None  # Fake-Leser nicht beim Beenden stoppen
window.quit_app()
print("Statuszeile ok")
sys.stdout.flush()
os._exit(0)
