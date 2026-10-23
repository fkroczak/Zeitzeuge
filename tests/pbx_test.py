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

from PySide6.QtCore import QCoreApplication

from pbx_reader import PbxReader, find_browser, login_window_open, profile_in_use

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


def run(url, until, what, days=14):
    reader = PbxReader(url, calls_file, profile, script, days_back=days)
    reader.READ_INTERVAL = 2
    reader.start()
    deadline = time.time() + 60
    while time.time() < deadline and not until(reader):
        time.sleep(0.5)
    if not until(reader):
        fail(what, reader)
    print("ok:", what, "|", reader.status)
    # Die Profil-Sperre muss erkannt werden (darauf wartet das Anmeldefenster)
    if not profile_in_use(profile):
        fail("Profil-Sperre bei laufendem Browser nicht erkannt", reader)
    # Der unsichtbare Edge darf nicht als offenes Anmeldefenster gelten
    if login_window_open(profile):
        fail("Unsichtbarer Browser wird als Anmeldefenster erkannt", reader)
    reader.stop()
    time.sleep(2)  # Browser sauber beenden lassen (Profil freigeben)
    if profile_in_use(profile):
        fail("Profil nach dem Beenden noch gesperrt", reader)


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

# 4. Erster Lauf liest 14 Tage zurück, Blättern auf ältere Tage liest nach
from datetime import date, timedelta


def days_back(n):
    return (date.today() - timedelta(days=n)).isoformat()


def has_call(n):
    return any(c["name"] == "Alt Kunde" and c["start"].startswith(days_back(n)) for c in calls())


state = os.path.join(tmp, "anrufe_stand.json")
for path in (calls_file, state):  # Stand der Schritte 1–3 verwerfen
    if os.path.exists(path):
        os.remove(path)
run("http://127.0.0.1:8812", lambda r: has_call(15) and os.path.exists(state),
    "14 Tage zurück gelesen")
assert not has_call(25), "zu weit gelesen"
assert json.load(open(state))["vollstaendig_ab"] == days_back(14)


def want(n):
    def until(reader):
        reader.want(days_back(n))
        return has_call(n + 1)
    return until


run("http://127.0.0.1:8812", want(25), "beim Blättern auf 25 Tage zurück nachgelesen")
assert json.load(open(state))["vollstaendig_ab"] == days_back(25)
# Mehr Tage eingestellt: liest von selbst weiter zurück
run("http://127.0.0.1:8812",
    lambda r: json.load(open(state))["vollstaendig_ab"] == days_back(30),
    "Einstellung 30 Tage nachgelesen", days=30)
run("http://127.0.0.1:8812",
    lambda r: (r.want(days_back(60)), json.load(open(state))["vollstaendig_ab"] == days_back(40))[1],
    "Listenende erkannt")

names = {c["name"] for c in calls()}
assert {"Sara Beispiel", "Hanna Dr. Kurz", "ABC GmbH", "015100000001"} <= names, names
# Dauer, Richtung und "via" müssen stimmen, auch wenn der Trennpunkt nur per CSS da ist
by_name = {c["name"]: c for c in calls()}
checks = [
    (by_name["Sara Beispiel"]["duration_s"], 552),
    (by_name["ABC GmbH"]["duration_s"], 3723),
    (by_name["Hanna Dr. Kurz"]["via"], "Carla Test 702"),
    (by_name["Info Cafeteria"]["direction"], "Ausgehend"),
    (by_name["Carla Test"]["direction"], "Verpasst"),
    # verschiedene Anrufer zählen: läuft der Test über Mitternacht, verschiebt die
    # nachgebaute Seite "Heute"/"Gestern" und dieselben Anrufe kommen mit neuem Datum
    (len({c["name"] for c in calls() if c["duration_s"] > 0 and c["name"] != "Alt Kunde"}), 7),
]
for got, want in checks:
    if got != want:
        print(f"::error title=3CX-Test::erwartet {want!r}, gelesen {got!r}")
        sys.exit(1)

# 5. Neue Anrufe kommen nur nach echtem Neuladen der Seite (3CX aktualisiert sich nicht selbst)
assert "Neu Anrufer" not in {c["name"] for c in calls()}, "neuer Anruf schon vor dem Neuladen"
PbxReader.RELOAD_INTERVAL = 3
run("http://127.0.0.1:8812", lambda r: "Neu Anrufer" in {c["name"] for c in calls()},
    "nach dem Neuladen neuen Anruf gelesen")

# 6. Anmeldefenster schließt sich nach der Anmeldung von selbst, die Anmeldung bleibt erhalten
profile = os.path.join(tmp, "profil_anmeldung")
os.remove(calls_file)
login = PbxReader("http://127.0.0.1:8812/?login=1", calls_file, profile, script)
login.show_login()
deadline = time.time() + 25  # ohne Automatik bliebe das Fenster offen
while time.time() < deadline and login._login_open:
    time.sleep(0.5)
if login._login_open or profile_in_use(profile):
    fail("Anmeldefenster nach der Anmeldung nicht geschlossen", login)
print("ok: Anmeldefenster nach der Anmeldung geschlossen |", login.status)
run("http://127.0.0.1:8812", lambda r: len(calls()) >= 8, "nach dem Anmeldefenster gelesen")
print("3CX-Test ok")
