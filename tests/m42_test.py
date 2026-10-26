"""Matrix42-Buchungen mit echtem Edge/Chromium gegen einen Nachbau der Kalenderseite lesen.

Die Seite startet in der Tagesansicht (wie zuletzt benutzt), Zeitzeuge muss auf die Woche
umschalten, die aktuelle und die letzte Woche lesen und beim Blättern eine ältere Woche.
Die Einträge kommen verzögert per Abfrage, wie im Original.
"""
import http.server
import json
import os
import sys
import tempfile
import threading
import time
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QCoreApplication  # noqa: E402

from m42_reader import M42Reader, load_store, week_start  # noqa: E402

MOCK = os.path.join(ROOT, "tests", "mock_m42")
LOGIN = [True]  # erster Aufruf: Anmeldeseite
monday = date.fromisoformat(week_start(date.today().isoformat()))


def events_for(day):
    """Zwei Buchungen je Werktag, eine überlappend (wie im echten Kalender)."""
    if day.weekday() >= 5:
        return []
    d = day.isoformat()
    return [
        {"date": d, "from": "08:10", "to": "08:55", "te": "TE0000087192",
         "title": "Systems - TCK0000049374 - Praktikanten / Azubi Oktober 2026"},
        {"date": d, "from": "08:38", "to": "08:53", "te": "TE0000087193",
         "title": "Elektroanlagen Röring GmbH  - TCK0000048883 - Computer Verdacht auf Viren"},
        {"date": d, "from": "14:20", "to": "16:40", "te": "TE0000086853",
         "title": "A.Fasselt Engineering GmbH  - TCK0000049191 - Netscaler"},
    ]


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path.endswith("/kalender"):
            if LOGIN[0]:
                body = b'<html><body><form><input type="password"></form></body></html>'
            else:
                body = open(os.path.join(MOCK, "index.html"), "rb").read()
            kind = "text/html"
        elif parts.path.endswith("/events.json"):
            q = parse_qs(parts.query)
            a, b = date.fromisoformat(q["from"][0]), date.fromisoformat(q["to"][0])
            items = []
            while a <= b:
                items += events_for(a)
                a += timedelta(days=1)
            time.sleep(0.4)  # Server braucht etwas
            body, kind = json.dumps(items).encode("utf-8"), "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Edge wurde beim Beenden mitten im Laden geschlossen

    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 8815), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

app = QCoreApplication(sys.argv)
tmp = tempfile.mkdtemp()
data_file = os.path.join(tmp, "m42_buchungen.json")
profile = os.path.join(tmp, "profil")
URL = "http://127.0.0.1:8815/wm/app-ServiceDesk/kalender"


def saved():
    return load_store(data_file)[0]  # aus der Datenbank (früher m42_buchungen.json)


def run(until, what, setup=None):
    reader = M42Reader(URL, data_file, profile, weeks_back=1)
    reader.start()
    if setup:
        setup(reader)
    deadline = time.time() + 90
    while time.time() < deadline and not until(reader):
        time.sleep(0.5)
    ok = until(reader)
    print("ok:" if ok else "FEHLER:", what, "|", reader.status)
    reader.stop()
    time.sleep(2)
    if not ok:
        print(f"::error title=Matrix42-Test::{what} | Status: {reader.status}")
        sys.exit(1)


# 1. Anmeldeseite wird erkannt
run(lambda r: r.needs_login, "Anmeldeseite erkannt")
LOGIN[0] = False

# 2. Aktuelle und letzte Woche lesen (Seite startet in der Tagesansicht)
last_monday = monday - timedelta(weeks=1)
run(lambda r: monday.isoformat() in saved() and last_monday.isoformat() in saved(),
    "aktuelle und letzte Woche gelesen")
days = saved()
for d in (monday, last_monday):
    items = days[d.isoformat()]
    assert len(items) == 3, items
    first = items[0]
    assert first["start"] == f"{d} 08:10:00" and first["end"] == f"{d} 08:55:00", first
    assert first["customer"] == "Systems" and first["ticket"] == "TCK0000049374", first
    assert first["subject"] == "Praktikanten / Azubi Oktober 2026" and first["entry"] == "TE0000087192"
    assert items[1]["customer"] == "Elektroanlagen Röring GmbH", items[1]
sunday = (monday + timedelta(days=6)).isoformat()
assert days.get(sunday) == [], "auch leere Tage der Woche gelten als gelesen"

# 3. Beim Blättern eine ältere Woche nachlesen
old = monday - timedelta(weeks=5)
run(lambda r: old.isoformat() in saved(), "ältere Woche beim Blättern gelesen",
    setup=lambda r: r.want((old + timedelta(days=2)).isoformat()))
assert len(saved()[old.isoformat()]) == 3

print("Matrix42 ok")
sys.stdout.flush()
os._exit(0)
