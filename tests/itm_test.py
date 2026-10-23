"""ITM-Personalzeiten mit echtem Edge/Chromium gegen eine nachgebaute Zeiterfassung testen.

Ablauf: Anmeldeseite erkennen -> "anmelden" -> heute lesen -> beim Blättern gestern lesen.
"""
import http.server
import json
import os
import sys
import tempfile
import threading
import time
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QCoreApplication

from itm_reader import ItmReader
from pbx_reader import profile_processes

MOCK = os.path.join(ROOT, "tests", "mock_itm")


LATER = False  # True: Tag hat sich in ITM geändert (wieder eingestempelt, noch offen)
DIRECT = []    # Tage, die Zeitzeuge direkt über die Schnittstelle abgefragt hat


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path.endswith("/zeiterfassung/tageszeiten"):
            body, kind = open(os.path.join(MOCK, "index.html"), "rb").read(), "text/html"
        elif path.endswith("/appsettings.Live.json"):
            body = json.dumps({"BaseUriConfiguration": {"V2BackendUri": "http://127.0.0.1:8814/api/"}})
            body, kind = body.encode("utf-8"), "application/json"
        elif path == "/api/tagesuebersicht":
            if not self.headers.get("Authorization", "").startswith("Bearer eyJ"):
                self.send_error(401)
                return
            day = query.split("=", 1)[1]
            DIRECT.append(day)
            body = open(os.path.join(MOCK, "tag.json"), encoding="utf-8").read()
            if LATER:
                body = body.replace('"DATUMT17:41:00"', 'null')
            body, kind = body.replace("DATUM", day).encode("utf-8"), "application/json"
        elif path == "/api/tag":
            day = query.split("=", 1)[1]
            body = open(os.path.join(MOCK, "tag.json"), encoding="utf-8").read()
            if LATER:
                body = body.replace('"DATUMT17:41:00"', 'null')
            body = body.replace("DATUM", day)
            body, kind = body.encode("utf-8"), "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        if kind == "application/json":  # Browser darf die Antwort zwischenspeichern
            self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 8814), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

app = QCoreApplication(sys.argv)
tmp = tempfile.mkdtemp()
data_file = os.path.join(tmp, "personalzeiten.json")
profile = os.path.join(tmp, "profil")
today = date.today().isoformat()
yesterday = (date.today() - timedelta(days=1)).isoformat()


def saved():
    try:
        return json.load(open(data_file, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run(url, until, what, linger=0):
    reader = ItmReader(url, data_file, profile)
    reader.LOAD_TIMEOUT = 8
    reader.start()
    deadline = time.time() + 60
    while time.time() < deadline and not until(reader):
        time.sleep(0.5)
    if not until(reader):
        print(f"::error title=ITM-Test::{what} | Status: {reader.status}")
        reader.stop()
        sys.exit(1)
    print("ok:", what, "|", reader.status)
    if not linger:
        time.sleep(1)
        if profile_processes(profile):
            print(f"::error title=ITM-Test::Edge läuft nach dem Lesen weiter ({what})")
            reader.stop()
            sys.exit(1)
    time.sleep(linger)
    reader.stop()
    time.sleep(2)  # Browser sauber beenden lassen (Profil freigeben)


# 1. Ohne Anmeldung: Anmeldeseite muss erkannt werden
run("http://127.0.0.1:8814", lambda r: r.needs_login, "Anmeldeseite erkannt")
# 2. Anmelden, dann muss heute gelesen werden
# (Edge kurz weiterlaufen lassen, damit die Anmeldung im Profil gespeichert wird)
run("http://127.0.0.1:8814/ok", lambda r: today in saved(), "heute gelesen", linger=10)
# 3. Neustart, Anmeldung erhalten, Blättern auf gestern liest gestern nach
run("http://127.0.0.1:8814", lambda r: (r.want(yesterday), yesterday in saved())[1],
    "gestern beim Blättern gelesen")

# Direkt abgefragt, und Edge läuft danach nicht mehr (nur kurz zum Erneuern der Anmeldung)
if yesterday not in DIRECT:
    print(f"::error title=ITM-Test::nicht direkt abgefragt: {DIRECT}")
    sys.exit(1)
print("ok: direkt abgefragt:", sorted(set(DIRECT)))

day = saved()[today]
assert day["soll"] == 480 and day["gewertet"] == 517 and day["pause"] == 54, day
assert day["zeiten"] == [
    {"start": f"{today} 08:10:00", "end": f"{today} 12:39:00"},
    {"start": f"{today} 13:33:00", "end": f"{today} 17:41:00"},
], day["zeiten"]

# 4. Heute erneut lesen, nachdem sich der Tag in ITM geändert hat: Zeitzeuge darf
# nicht die Daten der vorigen, noch geladenen Seite übernehmen
def reread_today(reader):
    global LATER
    if not LATER and reader._today_read:  # erst nach dem ersten Lesen ändern
        LATER = True
        reader._today_read = 0
        reader._wake.set()
    return LATER and saved()[today]["zeiten"][-1]["end"] is None


run("http://127.0.0.1:8814", reread_today, "heute nach Änderung erneut gelesen")
print("ITM-Test ok")
