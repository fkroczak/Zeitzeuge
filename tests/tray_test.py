"""Infobereich (Tray): Schnellzugriffe und Fensteraufzeichnung ein/aus.

Läuft ohne Bildschirm. Dort gibt es keinen Infobereich, deshalb wird er für
den Test als vorhanden gemeldet; das Menü und die Zustände sind dieselben.
"""
import json
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

import main_timeline  # noqa: E402
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
app = QApplication(sys.argv)
window = main_timeline.TimelineApp()
assert window.tray, "Infobereich fehlt"

menu = window.tray.contextMenu()
texts = [a.text().replace("&", "") for a in menu.actions() if not a.isSeparator()]
print("Tray-Menü:", texts)
assert menu.defaultAction().text().replace("&", "") == "Zeitzeuge öffnen"
for needed in ["Aufzeichnung aktiv", "Aufzeichnung pausieren", "Logs neu einlesen",
               "Datenquellen", "Datenordner öffnen", "Beenden"]:
    assert needed in texts, needed
assert not window.tray_state_action.isEnabled()  # reine Anzeige


def state():
    return (window.tracker is not None, window.tray_state_action.text(),
            window.tracking_button.text(), window.tracking_action.isChecked(),
            window.config["tracking_enabled"], "aktiv" in window.tray.toolTip())


assert state() == (True, "Aufzeichnung aktiv", "Aufzeichnung aktiv", True, True, True), state()

# Bisher Aufgezeichnetes von heute
today = datetime.now().strftime("%Y-%m-%d")
os.makedirs(main_timeline.ACTIVITY_DIR, exist_ok=True)
with open(os.path.join(main_timeline.ACTIVITY_DIR, f"{today}.jsonl"), "w", encoding="utf-8") as f:
    f.write(json.dumps({"start": f"{today} 00:00:01", "end": f"{today} 00:10:00",
                        "app": "outlook.exe", "title": "Posteingang"}) + "\n")

# Pausieren über das Tray-Menü
window.tray_toggle_action.trigger()
assert state() == (False, "Aufzeichnung pausiert", "Aufzeichnung pausiert", False, False, False), state()
assert window.tray_toggle_action.text().replace("&", "") == "Aufzeichnung fortsetzen"
assert window.timeline.pc_entries_for(window.current_date), "pausiert: bisherige PC-Daten fehlen"
with open(main_timeline.CONFIG_FILE, encoding="utf-8") as f:
    assert json.load(f)["tracking_enabled"] is False  # Zustand bleibt nach Neustart

# Fortsetzen über den Knopf in der Statuszeile
window.tracking_button.click()
assert state() == (True, "Aufzeichnung aktiv", "Aufzeichnung aktiv", True, True, True), state()
assert window.tray_toggle_action.text().replace("&", "") == "Aufzeichnung pausieren"

# Beenden, während die Logs noch gelesen werden: Thread wird abgewartet und meldet nichts mehr
import time  # noqa: E402
timeline = window.timeline
app.processEvents()
emitted = []
timeline.logs_loaded.connect(lambda *_: emitted.append(1))
slow = timeline._tv_parser.parse_logs
timeline._tv_parser.parse_logs = lambda: (time.sleep(0.5), slow())[1]
timeline.loading = False
timeline.refresh()
window.quit_app()
app.processEvents()
assert not timeline._thread.is_alive(), "Log-Thread läuft nach dem Beenden weiter"
assert not emitted, "Log-Thread hat nach dem Beenden noch gemeldet"
print("Tray ok")
