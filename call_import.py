"""
Anruf-Import für Zeitzeuge.

Das Tampermonkey-Skript (zeitzeuge_anrufe.user.js) liest die Anrufliste
im 3CX-Webclient aus und schickt sie per HTTP an 127.0.0.1.
Hier läuft dafür ein kleiner Server, der die Anrufe in anrufe.json sammelt.
"""

import json
import os
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TIME_FMT = "%Y-%m-%d %H:%M:%S"
_lock = threading.Lock()

# Zuletzt gesehen: für die Statusanzeige im Einrichtungsassistenten
status = {"last_ping": None, "script_version": None, "last_post": None, "last_count": 0}


def _key(call):
    # Gleicher Anruf = gleiche Startminute + gleiche Nummer/Name
    return f"{call['start'][:16]}|{call.get('number') or call.get('name')}"


def merge_calls(path, new_calls):
    """Neue Anrufe in die JSON-Datei übernehmen. Gibt Anzahl neuer Einträge zurück."""
    with _lock:
        calls = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    calls = {_key(c): c for c in json.load(f)}
            except Exception as e:
                print(f"anrufe.json nicht lesbar, wird neu angelegt: {e}")

        added = 0
        for c in new_calls:
            try:
                datetime.strptime(c["start"], TIME_FMT)
            except (KeyError, TypeError, ValueError):
                continue
            k = _key(c)
            if k not in calls:
                added += 1
            calls[k] = c  # neuere Daten (z. B. Name aus CRM) gewinnen

        if added:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(sorted(calls.values(), key=lambda c: c["start"]),
                          f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        return added


_file_cache = {"mtime": None, "calls": []}


def load_call_suggestions(path, ignore_missed=True, min_seconds=0):
    """Anrufe aus anrufe.json als Timeline-Vorschläge (gleiches Format wie TeamViewer/RDM)."""
    if not os.path.exists(path):
        return []
    mtime = os.path.getmtime(path)
    if _file_cache["mtime"] != mtime:
        try:
            with open(path, "r", encoding="utf-8") as f:
                _file_cache["calls"] = json.load(f)
            _file_cache["mtime"] = mtime
        except Exception as e:
            print(f"Fehler beim Lesen von {path}: {e}")
            return []

    result = []
    for c in _file_cache["calls"]:
        seconds = int(c.get("duration_s") or 0)
        if seconds == 0 and ignore_missed:
            continue
        if seconds < min_seconds:
            continue
        start = datetime.strptime(c["start"], TIME_FMT)
        end = start + timedelta(seconds=max(seconds, 60))  # min. 1 min, damit sichtbar

        name = c.get("name") or c.get("number") or "Unbekannt"
        number = c.get("number") or ""
        customer = f"{name} ({number})" if number and number != name else name

        details = [f"{c.get('direction', 'Anruf')}, Dauer {seconds // 60}:{seconds % 60:02d}"]
        if c.get("via"):
            details.append(f"via {c['via']}")
        result.append({
            "start": start.strftime(TIME_FMT),
            "end": end.strftime(TIME_FMT),
            "type": "Telefonat",
            "customer_name": customer,
            "details": ", ".join(details),
            "is_suggestion": True,
        })
    return result


def start_call_server(path, port=8765, on_update=None, script_provider=None):
    """Startet den Empfangsserver im Hintergrund.

    on_update(): wird nach neuen Anrufen aufgerufen.
    script_provider(): liefert den Text des Tampermonkey-Skripts (zum Installieren).
    """

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, content_type):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            route, _, query = self.path.partition("?")
            if route == "/zeitzeuge_anrufe.user.js" and script_provider:
                self._send(200, script_provider(), "text/javascript; charset=utf-8")
            elif route == "/ping":
                status["last_ping"] = datetime.now()
                status["script_version"] = query.replace("v=", "") or None
                self._send(200, "ok", "text/plain")
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != "/anrufe":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                calls = json.loads(self.rfile.read(length).decode("utf-8"))
                added = merge_calls(path, calls)
            except Exception as e:
                self.send_error(400, str(e))
                return
            status["last_post"] = datetime.now()
            status["last_count"] = len(calls)
            self._send(200, json.dumps({"neu": added}), "application/json")
            if added and on_update:
                on_update()

        def log_message(self, *args):
            pass  # keine Konsolenausgabe pro Request

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        print(f"Anruf-Empfang auf Port {port} nicht möglich: {e}")
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
