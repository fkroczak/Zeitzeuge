"""Mitschnitt der Abfragen testen: Schwärzen von Geheimnissen und ein echter Lauf mit Edge/Chromium.

Die nachgebaute Seite meldet sich per POST mit Passwort an, bekommt ein JWT und
ein Sitzungs-Cookie und lädt dann Daten. Nichts davon darf im Klartext in der Datei stehen.
"""
import base64
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

from pbx_reader import BrowserReader, find_browser, profile_processes
from request_recorder import redact_url, summarize_body

PASSWORD = "Geheim-Passwort-123"
COOKIE = "sitzungswert-4711"
now = int(time.time())
claims = base64.urlsafe_b64encode(json.dumps({"sub": "fk", "iat": now, "exp": now + 3600}).encode())
JWT = "eyJhbGciOiJIUzI1NiJ9." + claims.decode().rstrip("=") + ".c2lnbmF0dXJlLXNpZw"

PAGE = """<!doctype html><html><body><div id="app">Lädt …</div><script>
fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"},
  body: JSON.stringify({user: "fk", password: "%s"})})
  .then((r) => r.json()).then((d) => {
    localStorage.setItem("auth", JSON.stringify({token: d.access_token, expires_in: 3600}));
    return fetch("/api/anrufe?token=" + d.access_token + "&tage=14",
                 {headers: {Authorization: "Bearer " + d.access_token}});
  }).then((r) => r.json()).then((d) => { document.getElementById("app").textContent = d.length; });
</script></body></html>""" % PASSWORD


loaded = threading.Event()  # Seite hat ihre Daten geholt


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body, kind, extra=()):
        body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", kind)
        for k, v in extra:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/anrufe"):
            calls = [{"start": f"2026-10-{d:02d} 09:00", "nummer": "+49 30 123"} for d in range(1, 11)]
            self._send(json.dumps(calls), "application/json")
            loaded.set()
        else:
            self._send(PAGE, "text/html")

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._send(json.dumps({"access_token": JWT, "expires_in": 3600}), "application/json",
                   [("Set-Cookie", f"sitzung={COOKIE}; Path=/; HttpOnly; Max-Age=86400")])

    def log_message(self, *a):
        pass


def fail(problem):
    print(f"::error title=Mitschnitt-Test::{problem}")
    sys.exit(1)


# 1. Schwärzen ohne Browser
url = redact_url("https://x.de/login?user=fk&password=abc&code=123#access_token=" + JWT)
if "abc" in url or "123" in url or JWT in url:
    fail(f"Adresse nicht geschwärzt: {url}")
body = json.dumps(summarize_body(json.dumps({"user": "fk", "password": "abc", "liste": list(range(50))})))
if '"abc"' in body or "47 weitere" not in body:
    fail(f"JSON nicht geschwärzt oder gekürzt: {body}")
print("ok: Schwärzen ohne Browser")

# 2. Echter Mitschnitt im unsichtbaren Browser
server = http.server.ThreadingHTTPServer(("127.0.0.1", 8814), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
app = QCoreApplication(sys.argv)
print("Browser:", find_browser())


class Page(BrowserReader):
    NAME = "Test"

    def start_url(self):
        return "http://127.0.0.1:8814/"

    def _tick(self):
        pass


tmp = tempfile.mkdtemp()
out = os.path.join(tmp, "mitschnitt.json")
reader = Page("http://127.0.0.1:8814", os.path.join(tmp, "profil"))
results = []
reader.recording_done.connect(results.append)
reader.record(out, mode="headless", max_seconds=60)
deadline = time.time() + 40
if loaded.wait(30):
    time.sleep(2)  # letzte Antworten und Cookies abholen lassen
reader.stop_recording()
while time.time() < deadline and reader._login_open:
    time.sleep(0.2)
app.processEvents()

if not os.path.exists(out):
    fail(f"keine Datei geschrieben | Status: {reader.status}")
text = open(out, encoding="utf-8").read()
data = json.loads(text)
for secret in (PASSWORD, COOKIE, JWT, JWT.split(".")[1]):
    if secret in text:
        fail(f"Geheimnis im Klartext: {secret[:12]}…")
urls = [a["adresse"] for a in data["abfragen"]]
if not any("/api/login" in u for u in urls) or not any("/api/anrufe" in u for u in urls):
    fail(f"Abfragen fehlen: {urls}")
anrufe = next(a for a in data["abfragen"] if "/api/anrufe" in a["adresse"])
if "7 weitere" not in json.dumps(anrufe.get("antwort"), ensure_ascii=False):
    fail(f"Antwort nicht gekürzt: {anrufe.get('antwort')}")
if not anrufe["anfrage_koepfe"].get("Authorization", {}).get("jwt", {}).get("gueltig_minuten") == 60:
    fail(f"Ablauf des Tokens fehlt: {anrufe['anfrage_koepfe']}")
if not any(c["name"] == "sitzung" for c in data["cookies"]):
    fail(f"Cookie-Name fehlt: {data['cookies']}")
if "auth" not in data["seitenspeicher"].get("localStorage", {}):
    fail(f"localStorage fehlt: {data['seitenspeicher']}")
if profile_processes(os.path.join(tmp, "profil")):
    fail("Browser läuft nach dem Mitschnitt noch")
print("ok: Mitschnitt mit", len(urls), "Abfragen, nichts im Klartext |", reader.status)
