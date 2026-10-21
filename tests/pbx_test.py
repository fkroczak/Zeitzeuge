"""3CX-Direktauslesen gegen eine nachgebaute 3CX-Seite testen (Anmeldung + Liste)."""
import functools
import http.server
import json
import os
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401  (vor QApplication)
from PyQt5.QtCore import QCoreApplication, Qt, QTimer
from PyQt5.QtWidgets import QApplication

from pbx_reader import PbxReader

# Nachgebaute 3CX-Seite bereitstellen
handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                            directory=os.path.join(ROOT, "tests", "mock_3cx"))
server = http.server.ThreadingHTTPServer(("127.0.0.1", 8812), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
app = QApplication(sys.argv)
tmp = tempfile.mkdtemp()
calls_file = os.path.join(tmp, "anrufe.json")
script = open(os.path.join(ROOT, "zeitzeuge_anrufe.user.js"), encoding="utf-8").read()
reader = PbxReader("http://127.0.0.1:8812", calls_file, os.path.join(tmp, "profil"), script)
reader.open_call_list()

result = {"login": False, "phase": "login", "since": 0}
reader.login_required.connect(lambda: result.update(login=True))


def calls_count():
    try:
        return len(json.load(open(calls_file, encoding="utf-8")))
    except (OSError, ValueError):
        return 0


def tick():
    # Geduldig abfragen statt fester Wartezeiten (Build-Rechner sind unterschiedlich schnell)
    result["since"] += 1
    if result["phase"] == "login":
        if result["login"]:
            reader.page.runJavaScript("document.querySelector('form button').click()")
            result["phase"] = "liste"
        else:
            reader.read()
    elif result["phase"] == "liste":
        if calls_count() >= 8:
            app.quit()
        else:
            reader.read()


timer = QTimer()
timer.timeout.connect(tick)
timer.start(1500)
QTimer.singleShot(90000, app.quit)  # Notbremse
app.exec_()

assert result["login"], "Anmeldeseite nicht erkannt"
calls = json.load(open(calls_file, encoding="utf-8"))
print(f"{len(calls)} Anrufe gelesen")
for c in calls:
    print(" ", c)
assert len(calls) == 8, "Es sollten 8 Anrufe sein"
names = {c["name"] for c in calls}
assert {"Sara Beispiel", "Hanna Dr. Kurz", "ABC GmbH", "015100000001"} <= names, names
print("3CX-Test ok")
