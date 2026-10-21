"""3CX-Direktauslesen mit echtem Edge/Chromium gegen eine nachgebaute 3CX-Seite testen.

Ablauf: Anmeldeseite erkennen -> "anmelden" -> Anrufe lesen -> neu starten,
Anmeldung muss erhalten bleiben.
"""
import functools
import http.server
import json
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt5.QtCore import QCoreApplication

from pbx_reader import PbxReader, find_browser

handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                            directory=os.path.join(ROOT, "tests", "mock_3cx"))
handler.log_message = lambda *a: None
server = http.server.ThreadingHTTPServer(("127.0.0.1", 8812), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

app = QCoreApplication(sys.argv)
print("Browser:", find_browser())
tmp = tempfile.mkdtemp()
calls_file = os.path.join(tmp, "anrufe.json")
profile = os.path.join(tmp, "profil")
script = open(os.path.join(ROOT, "zeitzeuge_anrufe.user.js"), encoding="utf-8").read()


def fail(problem, reader):
    print(f"::error title=3CX-Test::{problem} | Status: {reader.status}")
    reader.stop()
    sys.exit(1)


def run(url, until, what):
    reader = PbxReader(url, calls_file, profile, script)
    reader.READ_INTERVAL = 2
    reader.start()
    deadline = time.time() + 60
    while time.time() < deadline and not until(reader):
        time.sleep(0.5)
    if not until(reader):
        fail(what, reader)
    print("ok:", what, "|", reader.status)
    reader.stop()
    time.sleep(2)  # Browser sauber beenden lassen (Profil freigeben)


def calls():
    try:
        return json.load(open(calls_file, encoding="utf-8"))
    except (OSError, ValueError):
        return []


# 1. Ohne Anmeldung: Anmeldeseite muss erkannt werden
run("http://127.0.0.1:8812", lambda r: r.needs_login, "Anmeldeseite erkannt")
# 2. Anmeldung simulieren, dann müssen 8 Anrufe gelesen werden
run("http://127.0.0.1:8812/?login=1", lambda r: len(calls()) >= 8, "8 Anrufe gelesen")
# 3. Neustart: Anmeldung muss im Profil erhalten sein
os.remove(calls_file)
run("http://127.0.0.1:8812", lambda r: len(calls()) >= 8, "Anmeldung nach Neustart erhalten")

names = {c["name"] for c in calls()}
assert {"Sara Beispiel", "Hanna Dr. Kurz", "ABC GmbH", "015100000001"} <= names, names
print("3CX-Test ok")
