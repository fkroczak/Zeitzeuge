"""
3CX-Anrufliste direkt vom Server holen, ohne die Webseite in Edge offen zu halten.

So macht es auch der 3CX-Webclient (Version 20, siehe Mitschnitt):
1. POST /connect/token mit dem Cookie "RefreshTokenCookie" (gilt etwa 60 Tage)
   -> access_token (gilt 1 Stunde)
2. POST /webclient/api/MyPhone/session mit dem Token -> sessionKey
3. POST /MyPhone/MPWebService.asmx (Protobuf) mit Kopfzeile "MyPhoneSession".
   Nachricht 106 liefert die Anrufliste seitenweise (Anzahl, Versatz),
   die Antwort ist Nachricht 204 mit einem Eintrag je Anruf.

Das Cookie holt Zeitzeuge einmal aus seinem Edge-Profil (nach der Anmeldung).
"""

import base64
import json
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone

CLIENT_VERSION = "20.0.9.0"
PAGE_SIZE = 80


class LoginRequired(Exception):
    """Cookie fehlt oder ist abgelaufen: im Edge-Fenster neu anmelden."""


# ---------------------------------------------------------------- Protobuf (ohne Schema)

def _varint(value):
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def pb_field(number, value):
    """Ein Feld kodieren: int -> varint, bytes/str/bytes-Nachricht -> Länge + Inhalt."""
    if isinstance(value, int):
        return _varint(number << 3) + _varint(value)
    if isinstance(value, str):
        value = value.encode("utf-8")
    return _varint(number << 3 | 2) + _varint(len(value)) + value


def _read_varint(buf, pos):
    value = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            return value, pos


def pb_decode(buf):
    """Nachricht in {Feldnummer: [Werte]} zerlegen. Werte: int oder bytes."""
    fields, pos = {}, 0
    while pos < len(buf):
        key, pos = _read_varint(buf, pos)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _read_varint(buf, pos)
        elif wire == 2:
            size, pos = _read_varint(buf, pos)
            value, pos = bytes(buf[pos:pos + size]), pos + size
        elif wire == 1:
            value, pos = int.from_bytes(buf[pos:pos + 8], "little"), pos + 8
        elif wire == 5:
            value, pos = int.from_bytes(buf[pos:pos + 4], "little"), pos + 4
        else:
            raise ValueError(f"Protobuf: unbekannter Typ {wire}")
        fields.setdefault(number, []).append(value)
    return fields


def _first(fields, number, default=None):
    values = fields.get(number)
    return values[0] if values else default


def _text(fields, number):
    value = _first(fields, number, b"")
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def _sub(fields, number):
    value = _first(fields, number)
    return pb_decode(value) if isinstance(value, bytes) and value else {}


def _time(fields, number):
    """Zeitpunkt (Jahr, Monat, Tag, Stunde, Minute, Sekunde in UTC) als lokale Zeit."""
    t = _sub(fields, number)
    if not t:
        return None
    try:
        utc = datetime(*(_first(t, i, 0) for i in range(1, 7)), tzinfo=timezone.utc)
    except ValueError:
        return None
    return utc.astimezone().replace(tzinfo=None)


def call_history_request(extension, count=PAGE_SIZE, offset=0):
    """Nachricht 106: Anrufliste ab offset (neueste zuerst)."""
    inner = (pb_field(1, 0) + pb_field(2, extension) + pb_field(3, count)
             + pb_field(4, offset) + pb_field(5, ""))
    return pb_field(1, 106) + pb_field(106, inner)


def parse_call_history(data):
    """Antwort 204 in Rohdaten je Anruf zerlegen (Bedeutung einzelner Felder siehe call_record)."""
    top = pb_decode(data)
    if _first(top, 1) != 204:
        raise ValueError(f"3CX: unerwartete Antwort {_first(top, 1)}")
    body = _sub(top, 204)
    calls = []
    for raw in body.get(1, []):
        entry = pb_decode(raw)
        call = _sub(_sub(entry, 3), 1)
        contact = _sub(call, 15)
        calls.append({
            "id": _first(entry, 2),
            "start": _time(call, 2),
            "t3": _time(call, 3),      # vermutlich: Klingeln endet / angenommen
            "end": _time(call, 4),
            "number": _text(call, 5),
            "flags": _first(call, 6, 0),
            "name": _text(call, 7),
            "f8": _text(call, 8) if isinstance(_first(call, 8), bytes) else "",
            "status": _first(call, 14, 0),
            "company": _text(contact, 7),
        })
    return calls


# ---------------------------------------------------------------- HTTP

def _jwt_claims(token):
    try:
        part = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except (IndexError, ValueError):
        return {}


class PbxClient:
    def __init__(self, base_url, refresh_cookie, timeout=20):
        self.base_url = base_url.rstrip("/")
        self.refresh_cookie = refresh_cookie
        self.timeout = timeout
        self.token = None
        self.session = None
        self.extension = None
        self._ctx = ssl.create_default_context()

    def _post(self, path, body, headers):
        req = urllib.request.Request(self.base_url + path, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as resp:
                return resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403):
                raise LoginRequired(f"3CX meldet {e.code}") from e
            raise

    def login(self):
        body, headers = self._post(
            "/connect/token", b"client_id=Webclient&grant_type=refresh_token",
            {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
             "Accept": "application/json",
             "Cookie": f"RefreshTokenCookie={self.refresh_cookie}"})
        # Falls 3CX das Cookie erneuert, das neue merken
        for value in headers.get_all("Set-Cookie") or []:
            if value.startswith("RefreshTokenCookie="):
                self.refresh_cookie = value.split(";", 1)[0].split("=", 1)[1]
        data = json.loads(body)
        self.token = data.get("access_token")
        if not self.token:
            raise LoginRequired("3CX: kein Zugangstoken")
        self.extension = str(_jwt_claims(self.token).get("unique_name") or "")
        body, _ = self._post(
            "/webclient/api/MyPhone/session",
            json.dumps({"name": "Webclient", "version": CLIENT_VERSION, "isHuman": True}).encode(),
            {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
             "Accept": "application/json"})
        self.session = json.loads(body)["sessionKey"]

    def request(self, message):
        body, _ = self._post("/MyPhone/MPWebService.asmx", message,
                             {"MyPhoneSession": self.session,
                              "Content-Type": "application/octet-stream",
                              "Accept": "application/octet-stream"})
        return body

    def call_history(self, offset=0, count=PAGE_SIZE):
        if not self.session:
            self.login()
        return parse_call_history(self.request(call_history_request(self.extension, count, offset)))
