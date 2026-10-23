"""3CX direkt abfragen (ohne Webseite) gegen einen nachgebauten 3CX-Server.

Prüft Anmeldung mit dem Refresh-Cookie, Sitzung, Blättern der Anrufliste (Protobuf)
und den Prüfbericht, der Namen und Nummern nur maskiert enthält.
"""
import base64
import http.server
import json
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402

from pbx_direct import LoginRequired, PbxClient, pb_decode, pb_field  # noqa: E402
from pbx_reader import PbxReader  # noqa: E402

COOKIE = "refresh-4711"
SESSION = "sitzung-0815"
b64 = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")
TOKEN = b64({"alg": "HS256"}) + "." + b64({"unique_name": "769", "exp": int(time.time()) + 3600}) + ".c2ln"
REQUESTS = []


def when(h, m, s):
    return b"".join(pb_field(i, v) for i, v in enumerate((2026, 10, 22, h, m, s), 1))


def call(no, h, m, name, number):
    c = (pb_field(1, no) + pb_field(2, when(h, m, 0)) + pb_field(3, when(h, m, 5))
         + pb_field(4, when(h, m + 2, 0)) + pb_field(5, number) + pb_field(6, 1)
         + pb_field(7, name) + pb_field(14, 3))
    return pb_field(1, "769") + pb_field(2, no) + pb_field(3, pb_field(1, c)) + pb_field(5, 0)


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body, kind):
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        REQUESTS.append(self.path)
        if self.path == "/connect/token":
            if f"RefreshTokenCookie={COOKIE}" not in self.headers.get("Cookie", ""):
                self.send_error(400)
                return
            self._send(json.dumps({"access_token": TOKEN, "expires_in": 3600}).encode(), "application/json")
        elif self.path == "/webclient/api/MyPhone/session":
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                self.send_error(401)
                return
            self._send(json.dumps({"sessionKey": SESSION, "pass": "x"}).encode(), "application/json")
        elif self.path == "/MyPhone/MPWebService.asmx":
            if self.headers.get("MyPhoneSession") != SESSION:
                self.send_error(403)
                return
            req = pb_decode(pb_decode(body)[106][0])
            assert req[2] == [b"769"], req  # eigene Nebenstelle aus dem Token
            offset, count = req[4][0], req[3][0]
            calls = [call(1000 + i, 8 + i // 30, i % 30, f"Müller {i}", f"0251{i:04d}")
                     for i in range(offset, min(offset + count, 120))]
            self._send(pb_field(1, 204) + pb_field(204, b"".join(pb_field(1, c) for c in calls)),
                       "application/octet-stream")
        else:
            self.send_error(404)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def base():
    """Nachgebauter 3CX-Server auf einem freien Port."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_falsches_cookie(base):
    """1. Falsches Cookie: Anmeldung nötig."""
    with pytest.raises(LoginRequired):
        PbxClient(base, "falsch").login()


def test_anmelden_und_blaettern(base):
    """2. Anmelden und blättern."""
    client = PbxClient(base, COOKIE)
    first, second = client.call_history(0), client.call_history(80)
    assert client.extension == "769" and len(first) == 80 and len(second) == 40, \
        f"Blättern: Nebenstelle {client.extension}, {len(first)} + {len(second)} Anrufe"
    c = first[0]
    assert c["name"] == "Müller 0" and c["number"] == "02510000" and c["end"] is not None \
        and c["start"] < c["end"], f"Anruf falsch zerlegt: {c}"


def test_pruefbericht(base, tmp_path):
    """3. Prüfbericht über den 3CX-Leser (Cookie kommt sonst aus dem Edge-Profil)."""
    first = PbxClient(base, COOKIE).call_history(0)
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    tmp = str(tmp_path)
    calls_file = os.path.join(tmp, "anrufe.json")
    start = first[0]["start"].strftime("%Y-%m-%d %H:%M:%S")
    with open(calls_file, "w", encoding="utf-8") as f:
        json.dump([{"start": start, "duration_s": 100, "name": "Müller 0", "number": "02510000",
                    "direction": "Anruf", "via": ""}], f)
    with open(os.path.join(ROOT, "zeitzeuge_anrufe.user.js"), encoding="utf-8") as f:
        script = f.read()
    reader = PbxReader(base, calls_file, os.path.join(tmp, "profil"), script)
    reader.browser_cookies = lambda: [{"name": "RefreshTokenCookie", "value": COOKIE}]
    results = []
    reader.check_done.connect(lambda path, text: results.append((path, text)))
    out = os.path.join(tmp, "pruefung.json")
    reader.check_direct(out)
    deadline = time.time() + 20
    while time.time() < deadline and not results:
        app.processEvents()
        time.sleep(0.1)
    assert results and results[0][0], f"kein Prüfbericht: {results} | {reader.status}"
    with open(out, encoding="utf-8") as f:
        text = f.read()
    report = json.loads(text)
    assert "Müller" not in text and "0251" not in text, "Prüfbericht enthält Namen oder Nummern im Klartext"
    assert report["anrufe"] == 120 and report["vergleich"][0]["in_anrufe_json"], \
        f"Prüfbericht unvollständig: {report['anrufe']} Anrufe, {report['vergleich'][0]}"
    print("ok: Prüfbericht |", results[0][1])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
