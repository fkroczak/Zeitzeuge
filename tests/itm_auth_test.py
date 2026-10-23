"""ITM-Anmeldung ohne Edge (refreshToken), altes Backend und fehlerhafte Buchungen.

Ein nachgebauter Server spielt Anmeldedienst, altes Backend und Tagesübersicht.
"""
import base64
import http.server
import json
import os
import threading
import time
from datetime import date, datetime, timedelta

import pytest
from PySide6.QtCore import QCoreApplication

import itm_auth
from itm_auth import AuthError, ItmAuth, booking_issues, bookings_from_legacy
from itm_reader import ItmReader, session_data


def jwt(seconds, name="x"):
    def part(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{part({'alg': 'none'})}.{part({'exp': int(time.time()) + seconds, 'sub': name})}.sig"


class State:
    def __init__(self):
        self.refresh = "r1"        # gültiges refreshToken
        self.jwt_seconds = 60      # wie das alte Backend: 1 Minute
        self.v2_takes_auth = True  # nimmt die Tagesübersicht das Token des Anmeldedienstes?
        self.logins = self.refreshes = 0
        self.issued = set()
        self.bookings = []


STATE = State()


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, data=None):
        body = json.dumps(data).encode() if data is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _issue(self):
        token = jwt(STATE.jwt_seconds, f"auth{len(STATE.issued)}")
        STATE.issued.add(token)
        return token

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/auth/authenticate":
            if body != {"username": "mmuster", "password": "geheim", "mandantID": 7}:
                return self._send(401, {"message": "Login fehlgeschlagen"})
            STATE.logins += 1
            return self._send(200, {"jwtToken": self._issue(), "refreshToken": STATE.refresh,
                                    "firstName": "Max", "lastName": "Muster", "personalnummer": "1001"})
        if self.path == "/auth/refresh-token-body":
            if body.get("token") != STATE.refresh:
                return self._send(400, {"message": "Invalid token"})
            STATE.refreshes += 1
            STATE.refresh = f"r{STATE.refreshes + 1}"  # wird bei jedem Erneuern gewechselt
            return self._send(200, {"jwtToken": self._issue(), "refreshToken": STATE.refresh})
        self._send(404)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if path == "/appsettings.Live.json":
            return self._send(200, {"BaseUriConfiguration": {
                "V2BackendUri": f"{BASE}/v2/", "ApiUri": f"{BASE}/api/"}})
        if path == "/v2/tagesuebersicht":
            ok = token == "edge" or (token in STATE.issued and STATE.v2_takes_auth)
            if not ok:
                return self._send(401)
            day = query.split("=", 1)[1]
            return self._send(200, {"datum": day, "kennzahlen": {"sollMinuten": 480},
                                    "personalzeiten": [{"start": f"{day}T08:00:00", "ende": f"{day}T16:00:00"}]})
        if path == "/api/Personalzeit/view/minimal/tage/45":
            if token not in STATE.issued:
                return self._send(401)
            return self._send(200, STATE.bookings) if STATE.bookings else self._send(204)
        self._send(404)

    def log_message(self, *args):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
BASE = f"http://127.0.0.1:{SERVER.server_port}"
threading.Thread(target=SERVER.serve_forever, daemon=True).start()


@pytest.fixture(autouse=True)
def fresh_state():
    global STATE
    STATE = State()


def make_reader(tmp_path):
    reader = ItmReader(BASE, str(tmp_path / "pz.json"), str(tmp_path / "itm_profil"))

    def no_edge():
        raise AssertionError("Edge darf nicht starten")
    reader._fetch_token = no_edge
    return reader


def test_login_store_and_refresh(tmp_path):
    store = str(tmp_path / "anmeldung.json")
    auth = ItmAuth(BASE, store)
    auth.login("mmuster", "geheim", 7)
    assert auth.profile["personalnummer"] == "1001"
    text = open(store, encoding="utf-8").read()
    assert "geheim" not in text and '"r1"' not in text  # Passwort nie, Token nur kodiert

    # Neuer Start: refreshToken aus der Ablage, jwtToken wird erneuert und gewechselt
    auth2 = ItmAuth(BASE, store)
    assert auth2.refresh_token == "r1"
    assert auth2.token() in STATE.issued and STATE.refreshes == 1
    assert ItmAuth(BASE, store).refresh_token == "r2"  # neues refreshToken gespeichert
    # Noch gültig: kein weiteres Erneuern
    auth2.token()
    assert STATE.refreshes == 1


def test_refresh_expired_and_wrong_password(tmp_path):
    auth = ItmAuth(BASE, str(tmp_path / "a.json"))
    auth.adopt("abgelaufen")
    assert auth.token() is None and not auth.has_login  # nicht immer wieder versuchen
    with pytest.raises(AuthError, match="IP-Adresse"):
        auth.login("mmuster", "falsch", 7)


def test_unreachable_is_network_error(tmp_path):
    auth = ItmAuth("http://127.0.0.1:9", str(tmp_path / "a.json"))
    auth.adopt("r1")
    with pytest.raises(itm_auth.AuthNetworkError):
        auth.token()
    assert auth.refresh_token == "r1"  # offline: Anmeldung bleibt


def test_protect_roundtrip():
    assert itm_auth.unprotect(itm_auth.protect("abc")) == "abc"
    assert itm_auth.unprotect("kaputt") == ""


def test_session_cookie_refresh_token():
    value = json.dumps({"JwtToken": "j", "RefreshToken": "r"})
    cookies = [{"name": "session", "domain": "app.example.com", "value": value}]
    assert session_data(cookies, "app.example.com") == {"JwtToken": "j", "RefreshToken": "r"}


def test_reader_reads_without_edge(tmp_path):
    reader = make_reader(tmp_path)
    reader.auth.adopt("r1")  # z. B. aus dem Cookie der App übernommen
    day = date.today().isoformat()
    assert reader._read_day_direct(day) is True
    assert reader.day(day)["soll"] == 480
    assert reader.auth.base_url == BASE  # Anmeldedienst aus ApiUri der App


def test_reader_falls_back_to_edge(tmp_path):
    STATE.v2_takes_auth = False
    reader = make_reader(tmp_path)
    reader.auth.adopt("r1")
    calls = []
    reader._fetch_token = lambda: calls.append(1) or "edge"
    assert reader._read_day_direct("2026-10-20") is True
    assert calls == [1] and not reader._auth_for_v2


def test_password_user_needs_login_without_edge(tmp_path):
    reader = make_reader(tmp_path)
    reader.username = "mmuster"
    assert reader._read_day_direct("2026-10-20") is False and reader.needs_login

    done = []
    reader.login_finished.connect(done.append)
    reader.login_password("mmuster", "geheim", 7)
    app = QCoreApplication.instance() or QCoreApplication([])
    deadline = time.time() + 10
    while not done and time.time() < deadline:
        app.processEvents()  # Signal aus dem Anmelde-Thread zustellen
        time.sleep(0.05)
    assert done == [""] and not reader.needs_login
    assert reader._read_day_direct("2026-10-20") is True


def test_legacy_backfill_and_issues(tmp_path):
    now = datetime.now()
    old = (now - timedelta(days=3)).replace(microsecond=0)
    known = (now - timedelta(days=2)).date().isoformat()
    open_start = (now - timedelta(hours=13)).replace(microsecond=0)
    STATE.bookings = [
        {"personalzeitID": 1, "start": old.replace(hour=8, minute=0).isoformat(),
         "ende": old.replace(hour=12, minute=0).isoformat(), "gewertetDauer": 240},
        {"personalzeitID": 2, "start": old.replace(hour=13, minute=0).isoformat(),
         "ende": old.replace(hour=12, minute=30).isoformat(), "gewertetDauer": 0},
        {"personalzeitID": 3, "start": f"{known}T09:00:00", "ende": f"{known}T10:00:00", "gewertetDauer": 60},
        {"personalzeitID": 4, "start": open_start.isoformat(), "ende": None, "gewertetDauer": None},
    ]
    reader = make_reader(tmp_path)
    reader.auth.adopt("r1")
    reader.days[known] = {"soll": 480, "gewertet": 999, "pause": 30, "zeiten": []}
    found = []
    reader.issues_found.connect(found.append)

    reader._read_legacy()
    reader._check_issues()
    old_day = reader.day(old.date().isoformat())
    assert old_day["gewertet"] == 240 and old_day["quelle"] == "ITM alt" and len(old_day["zeiten"]) == 2
    assert reader.day(known)["gewertet"] == 999  # Tag aus der Tagesübersicht bleibt
    assert len(found) == 1 and len(found[0]) == 2, found
    assert any("Ende liegt vor dem Start" in t for t in found[0])
    assert any("12 Stunden offen" in t for t in found[0])

    # Dieselben Buchungen nicht noch einmal melden, und erst nach 30 Minuten neu holen
    reader._check_issues()
    reader._read_legacy()
    assert len(found) == 1


def test_booking_issues_rules():
    now = datetime(2026, 10, 23, 20, 0)
    rows = bookings_from_legacy([
        {"Start": "2026-10-23T06:00:00", "Ende": None},          # 14 h offen
        {"Start": "2026-10-23T12:00:00", "Ende": None},          # 8 h offen: ok
        {"GewertetStart": "2026-10-20T06:00:00", "GewertetEnde": "2026-10-20T19:00:00"},  # 13 h
        {"Start": "2026-10-21T08:00:00", "Ende": "2026-10-21T16:00:00"},  # ok
    ])
    texts = [t for _, t in booking_issues(rows, now)]
    assert len(texts) == 2 and "offen" in texts[1] and "länger als 12 Stunden" in texts[0]


def test_auth_unreachable_uses_edge(tmp_path):
    reader = make_reader(tmp_path)
    reader._api_base()
    reader.auth.base_url = "http://127.0.0.1:9"  # Anmeldedienst nicht erreichbar
    reader.auth.adopt("r1")
    reader._fetch_token = lambda: "edge"
    assert reader._read_day_direct("2026-10-20") is True
    assert reader.auth.refresh_token == "r1"  # Anmeldung bleibt für später
