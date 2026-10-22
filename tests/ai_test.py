"""KI-Vorschläge (ai_classifier.py) gegen einen nachgebauten Anthropic-Server.

Es wird nichts an Anthropic gesendet und kein API-Schlüssel gebraucht.
Geprüft wird: Anfrage (Modell, JSON-Schema, Fallback), Umwandlung der Antwort,
Ablage pro Tag, kein zweiter Aufruf bei unveränderten Einträgen, Übernehmen/Verwerfen.
"""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

import ai_classifier as ai

requests = []
ANSWER = {"taetigkeiten": [
    {"von": "09:00", "bis": "09:45", "kunde": "Müller GmbH", "kategorie": "Fernwartung",
     "beschreibung": "Fernwartung Server, Updates eingespielt", "sicherheit": 0.9},
    {"von": "10:15", "bis": "10:30", "kunde": "Max Muster", "kategorie": "Telefonsupport",
     "beschreibung": "Rückfrage zum Drucker", "sicherheit": 0.7},
    {"von": "11:00", "bis": "10:00", "kunde": "kaputt", "kategorie": "Fernwartung",
     "beschreibung": "Ende vor Beginn, wird verworfen", "sicherheit": 0.1},
]}


class FakeAnthropic(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        requests.append({"path": self.path, "body": body, "beta": self.headers.get("anthropic-beta")})
        reply = json.dumps({
            "id": "msg_test", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "text", "text": json.dumps(ANSWER, ensure_ascii=False)}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 2000, "output_tokens": 500},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass


server = HTTPServer(("127.0.0.1", 0), FakeAnthropic)
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{server.server_port}"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"

app = QCoreApplication(sys.argv)
D = "2026-10-20"
entries = [
    {"start": f"{D} 09:00:00", "end": f"{D} 09:40:00", "type": "TeamViewer",
     "customer_name": "Müller GmbH", "details": "TeamViewer-ID 1 076 789 144"},
    {"start": f"{D} 10:15:00", "end": f"{D} 10:30:00", "type": "Telefonat",
     "customer_name": "Max Muster", "details": "", "direction": "Eingehend"},
]
pc = [{"start": f"{D} 09:05:00", "end": f"{D} 09:30:00", "app": "mstsc.exe",
       "customer_name": "srv01 - Remotedesktopverbindung"}]

# Eingabetext
text = ai.build_day_text(entries, pc)
assert "09:00-09:40 | TeamViewer | Müller GmbH" in text, text
assert "Telefonat eingehend" in text and "mstsc.exe" in text, text
assert "Aktive Fenster" not in ai.build_day_text(entries, None)

config = {"ai_model": "claude-opus-5-5"}
store = ai.AiStore(os.path.join(tempfile.mkdtemp(), "ki_vorschlaege"))
classifier = ai.AiClassifier(store, config)
results = []
classifier.finished.connect(lambda d, n, c: results.append(("ok", d, n, c)))
classifier.failed.connect(lambda d, m: results.append(("fehler", d, m)))


def wait():
    loop = QEventLoop()
    QTimer.singleShot(10000, loop.quit)
    timer = QTimer()
    timer.timeout.connect(lambda: results and loop.quit())
    timer.start(20)
    loop.exec()


assert classifier.start(D, entries, pc)
wait()
assert results and results[0][0] == "ok", results
_, day, count, cost = results[0]
assert day == D and count == 3, results
assert abs(cost - (2000 * 4 + 500 * 20) / 1e6) < 1e-9, cost

# Anfrage: Opus mit Fallback, JSON-Schema mit den Kategorien, Einträge im Text
req = requests[0]
assert req["path"].startswith("/v1/messages"), req["path"]
assert "server-side-fallback-2026-07-01" in (req["beta"] or ""), req["beta"]
assert req["body"]["fallbacks"] == "default"
fmt = req["body"]["output_config"]["format"]
assert fmt["type"] == "json_schema"
enum = fmt["schema"]["properties"]["taetigkeiten"]["items"]["properties"]["kategorie"]["enum"]
assert enum == ai.DEFAULT_CATEGORIES, enum
assert "Müller GmbH" in req["body"]["messages"][0]["content"]
assert "thinking" not in req["body"] and "temperature" not in req["body"]

# Antwort: ungültige Zeile (Ende vor Beginn) fällt weg
shown = store.entries(D)
assert [(e["start"][11:16], e["end"][11:16]) for e in shown] == [("09:00", "09:45"), ("10:15", "10:30")]
assert shown[0]["type"] == ai.AI_TYPE and shown[0]["ai"] and shown[0]["customer_name"] == "Müller GmbH"

# Unveränderte Einträge: kein zweiter Aufruf
assert not classifier.start(D, entries, pc)
assert len(requests) == 1

# Übernehmen und Verwerfen
store.set_status(D, shown[0]["ai_id"], "übernommen")
store.set_status(D, shown[1]["ai_id"], "verworfen")
store._cache.clear()  # wirklich von der Platte lesen
shown = store.entries(D)
assert len(shown) == 1 and shown[0]["status"] == "übernommen", shown

# Neu erstellen: übernommene Vorschläge bleiben übernommen, Kosten werden mitgezählt
results.clear()
assert classifier.start(D, entries, pc, force=True)
wait()
assert results[0][0] == "ok", results
data = store.load(D)
assert data["items"][0]["status"] == "übernommen", data["items"][0]
assert data["earlier_cost_usd"] > 0

# Haiku: ohne Fallback-Beta (gibt es dort nicht)
config["ai_model"] = "claude-haiku-5-5"
results.clear()
assert classifier.start(D, entries, pc)
wait()
assert results[0][0] == "ok", results
assert requests[-1]["body"]["model"] == "claude-haiku-5-5"
assert "fallbacks" not in requests[-1]["body"]

# Ohne Schlüssel: verständliche Meldung statt Absturz
del os.environ["ANTHROPIC_API_KEY"]
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
results.clear()
assert not classifier.start("2026-10-21", entries, pc)
assert results and results[0][0] == "fehler" and "API-Schlüssel" in results[0][2], results

server.shutdown()
print("KI-Vorschläge ok")
