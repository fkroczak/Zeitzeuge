"""Update mit Rückmeldung (app_update.py, update_dialog.py).

Prüft: Klick auf „Jetzt aktualisieren“ zeigt sofort das Update-Fenster mit drehendem Ring,
Fortschritt beim Laden („… 97 % (43 von 44 MB)“), danach „Zeitzeuge wird beendet …“ ohne
Abbrechen, Setup gestartet und erst dann beendet; Merker für den Neustart, Bestätigung
„Aktualisiert auf …“ mit Changelog nach dem Neustart, Meldung, wenn die Version gleich blieb;
Abbrechen während des Ladens schließt das Fenster ohne Fehlermeldung; zum Schluss das echte
Beenden mit offenem Update-Fenster (Qt 6 bricht das Beenden ab, wenn ein Fenster das Schließen
ablehnt – so hing das Update auf 4.1.65).

Ohne Netz und ohne Setup: Laden und Starten sind Attrappen. Läuft als eigener Prozess (Skript).
"""
import faulthandler
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()
os.environ["ZEITZEUGE_UPDATE_TOKEN"] = "test"

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

import main_timeline as mt  # noqa: E402
import updater  # noqa: E402
import version  # noqa: E402


def spin(until, seconds=3.0):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        if until():
            return True
        time.sleep(0.01)
    return until()


def check(ok, text):
    if not ok:
        print(f"::error title=update_gui_test::{text}")
        os._exit(1)
    print("ok:", text)


version._INFO = {"channel": "main", "version": "4.1.62"}
w = mt.TimelineApp()
check(w.updates_possible(), "Updates in einer main-Version mit Token möglich")

# --- Knopf „Jetzt updaten“ links neben „Ansicht“: nur, wenn ein Update da ist ---
check(not w.update_now_action.isVisible(), "Ohne Update kein Knopf „Jetzt updaten“")
w._update_checked({"version": "4.1.63", "changes": []}, None, False)
check(w.update_now_action.isVisible(), "Update gefunden: Knopf „Jetzt updaten“ sichtbar")
check("4.1.63" in w.update_now_action.toolTip(), "Hinweis am Knopf nennt die neue Version")
w._update_checked({"version": "4.1.62"}, None, False)
check(not w.update_now_action.isVisible(), "Wieder aktuell: Knopf verschwindet")

# --- Laden mit Fortschritt, dann Prüfen, Setup starten, beenden ---
gate = {"go": False}


def fake_download(info, token, folder, progress=None, cancelled=None):
    for i in range(1, 6):
        progress(i * 9_000_000, 46_000_000)
        time.sleep(0.02)
    while not gate["go"]:
        time.sleep(0.01)
    return os.path.join(folder, "Zeitzeuge-Setup-4.1.63.exe")


started, quits = [], []
updater.download = fake_download
updater.signature_ok = lambda path: True
updater.start_setup = lambda path, minimized=False: started.append((path, minimized))
w.quit_app = lambda: quits.append(1)

w.update_info = {"version": "4.1.63", "url": "u", "size": 46_000_000, "sha256": "a" * 64,
                 "changes": ["Update-Fenster mit Fortschritt", "Bestätigung nach dem Neustart"]}
w.install_update()
win = w._update_window
check(win is not None and win.isVisible(), "Update-Fenster erscheint sofort beim Klick")
check(win.spinner._timer.isActive(), "Ring dreht sich")
check(spin(lambda: "97 %" in win.step.text()), f"Fortschritt beim Laden: {win.step.text()!r}")
check("43 von 44 MB" in win.step.text(), "Größe in MB")
check(win.cancel_button.isVisible(), "Abbrechen während des Ladens")
check(not started and not quits, "noch nichts gestartet oder beendet")

gate["go"] = True
check(spin(lambda: started), "Setup gestartet")
spin(lambda: "beendet" in win.step.text())  # Setup startet im Hintergrund, dann der Schritt
check("beendet" in win.step.text() and not win.cancel_button.isVisible(),
      f"Schritt „Zeitzeuge wird beendet“ ohne Abbrechen: {win.step.text()!r}")
check(win.isVisible() and not quits, "Fenster bleibt, bis Zeitzeuge beendet")
check(spin(lambda: quits, 2), "danach beendet")
pending = w.config.get("update_pending")
check(pending and pending["from"] == "4.1.62" and pending["to"] == "4.1.63"
      and pending["notes"][0] == "Update-Fenster mit Fortschritt", "Merker für den Neustart gespeichert")

# --- Neustart: Bestätigung mit Changelog ---
version._INFO = {"channel": "main", "version": "4.1.63"}
notes = []
w.notify = lambda title, text, **k: notes.append((title, text, k))
w._finished_update = w.config.pop("update_pending")
w._report_finished_update()
check(notes and notes[0][0] == "Aktualisiert auf 4.1.63" and notes[0][2]["items"][0].startswith("Update-Fenster")
      and notes[0][2]["kind"] == "info", "Bestätigung nach dem Neustart mit Changelog")
check(w._finished_update is None, "Bestätigung nur einmal")

# --- Neustart, aber Version gleich geblieben ---
version._INFO = {"channel": "main", "version": "4.1.62"}
notes.clear()
w._finished_update = {"from": "4.1.62", "to": "4.1.63", "notes": []}
w._report_finished_update()
check(notes and notes[0][0] == "Update nicht installiert" and notes[0][2]["kind"] == "warn",
      "Meldung, wenn das Update nicht installiert wurde")

# --- Abbrechen während des Ladens ---
w._update_busy = False
started.clear()


def slow_download(info, token, folder, progress=None, cancelled=None):
    while not cancelled():
        time.sleep(0.01)
    raise updater.UpdateError("Abgebrochen.")


updater.download = slow_download
w.install_update()
spin(lambda: False, 0.1)
w._update_window._cancel()
check(spin(lambda: w._update_window is None), "Abbrechen schließt das Fenster")
check(not started and "abgebrochen" in w.statusBar().currentMessage(), "kein Setup, Hinweis in der Statuszeile")

# --- Echtes Beenden mit offenem Update-Fenster: darf nicht hängen ---
from PySide6.QtCore import QTimer  # noqa: E402

real_quit = type(w).quit_app
del w.quit_app  # wieder die echte Methode (TrayMixin.quit_app)
check(w.quit_app.__func__ is real_quit, "echtes quit_app")
updater.download = fake_download
gate["go"] = True
w._update_busy = False
w.install_update()
check(spin(lambda: started), "Setup gestartet (echtes Beenden)")
QTimer.singleShot(5000, lambda: app.exit(3))  # hängt das Beenden, endet exec mit 3
code = app.exec()
check(code == 0, f"Zeitzeuge beendet sich mit offenem Update-Fenster (Code {code}, 3 = hängt)")

print("update_gui_test: alles ok")
sys.stdout.flush()
os._exit(0)
