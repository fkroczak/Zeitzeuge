"""Infobereich (Tray): Schnellzugriffe und Fensteraufzeichnung ein/aus.

Läuft ohne Bildschirm. Dort gibt es keinen Infobereich, deshalb wird er für
den Test als vorhanden gemeldet; das Menü und die Zustände sind dieselben.
"""
import json
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

import main_timeline  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
app = QApplication(sys.argv)
window = main_timeline.TimelineApp()
assert window.tray, "Infobereich fehlt"

menu = window.tray.contextMenu()
texts = [a.text().replace("&", "") for a in menu.actions() if not a.isSeparator()]
print("Tray-Menü:", texts)
assert menu.defaultAction().text().replace("&", "") == "Zeitzeuge öffnen"
for needed in ["Aufzeichnung pausieren", "Aktualisieren", "Offene Nachfragen", "Benachrichtigungen …",
               "Einstellungen …", "Beenden"]:
    assert needed in texts, needed
# Ein Eintrag für die Aufzeichnung (kein zweiter, nur anzeigender), Datenquellen nur im Hauptfenster
assert "Aufzeichnung aktiv" not in texts and "Datenquellen" not in texts, texts
assert not window.tray_prompts_action.isEnabled()  # noch nichts offen
row = window.tray_record


def state():
    return (window.tracker is not None, row.recording, row.state.text(),
            window.tracking_button.text(), window.tracking_action.isChecked(),
            window.config["tracking_enabled"], "aktiv" in window.tray.toolTip())


assert state() == (True, True, "läuft", "Aufzeichnung aktiv", True, True, True), state()
assert row.dot.isVisibleTo(row.row) and not row.pause.isVisibleTo(row.row)  # roter Punkt

# Bisher Aufgezeichnetes von heute
today = datetime.now().strftime("%Y-%m-%d")
window.data_store.append("aktivitaet", today, {"start": f"{today} 00:00:01", "end": f"{today} 00:10:00",
                                              "app": "outlook.exe", "title": "Posteingang"})

# Pausieren über das Tray-Menü
row._activate()
assert state() == (False, False, "pausiert", "Aufzeichnung pausiert", False, False, False), state()
assert row.text() == "Aufzeichnung fortsetzen" and not row.dot.isVisibleTo(row.row)
assert window.timeline.pc_entries_for(window.current_date), "pausiert: bisherige PC-Daten fehlen"
with open(main_timeline.CONFIG_FILE, encoding="utf-8") as f:
    assert json.load(f)["tracking_enabled"] is False  # Zustand bleibt nach Neustart

# Fortsetzen über den Knopf in der Statuszeile
window.tracking_button.click()
assert state() == (True, True, "läuft", "Aufzeichnung aktiv", True, True, True), state()
assert row.text() == "Aufzeichnung pausieren"

# Beenden, während die Logs noch gelesen werden: Thread wird abgewartet und meldet nichts mehr
import time  # noqa: E402
timeline = window.timeline
# Erstes Einlesen beim Start (startet per Timer) ganz abschließen lassen, auch die Meldung
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    app.processEvents()
    if timeline._threads and not timeline.loading and not any(t.is_alive() for t in timeline._threads):
        break
    time.sleep(0.05)
app.processEvents()
emitted = []
timeline.logs_loaded.connect(lambda *_: emitted.append(1))
slow = timeline._tv_parser.parse_logs
timeline._tv_parser.parse_logs = lambda: (time.sleep(0.5), slow())[1]
timeline.loading = False
timeline.refresh()
window.quit_app()
app.processEvents()
assert not any(t.is_alive() for t in timeline._threads), "Log-Thread läuft nach dem Beenden weiter"
assert not emitted, "Log-Thread hat nach dem Beenden noch gemeldet"
print("Tray ok")

# Direkt beenden: die Qt-Bindung räumt beim Interpreter-Ende sporadisch in falscher Reihenfolge auf
# (Zugriffsfehler unter Windows, auch mit altem Code). Alle Prüfungen sind hier gelaufen.
sys.stdout.flush()
import safe_io  # Ende ohne Qt-Aufräumen (Absturz unter Windows)
safe_io.hard_exit(0)
