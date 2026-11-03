"""
Anmeldung am ITM-Anmeldedienst und Abfragen an das alte ITM-Backend (api.itm-gruppe.com).

Anmelden   POST {auth}/auth/authenticate {"username", "password", "mandantID"}
           -> jwtToken (gilt etwa 1 Minute) und refreshToken (gilt 7 Tage).
Erneuern   POST {auth}/auth/refresh-token-body {"token": <refreshToken>}
           -> neues jwtToken und meist ein neues refreshToken (wieder 7 Tage).

Zeitzeuge speichert nur das refreshToken, nie das Passwort. Unter Windows ist es mit
DPAPI verschlüsselt (nur dein Windows-Benutzer kann es lesen). Solange Zeitzeuge
mindestens einmal pro Woche läuft, bleibt die Anmeldung damit erhalten, ohne dass Edge
starten muss. Die Web-App legt dasselbe refreshToken in ihrem Cookie "session" ab:
Nach einer Anmeldung im Edge-Fenster übernimmt Zeitzeuge es von dort.

Dazu prüft booking_issues() die eigenen Buchungen auf Fehler wie im alten Backend
(offen seit mehr als 12 Stunden, länger als 12 Stunden, Ende vor dem Start).
"""

import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import safe_io

DEFAULT_URL = "https://api.itm-gruppe.com"
REFRESH_MARGIN = 15   # Sekunden vor Ablauf erneuern
TIMEOUT = 20
OPEN_LIMIT = timedelta(hours=12)  # wie Fehlerart 0 im alten Backend


class AuthError(Exception):
    """Anmeldung abgelehnt (falsches Passwort, abgelaufenes refreshToken …)."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class AuthNetworkError(OSError):
    """Anmeldedienst gerade nicht erreichbar: später noch einmal versuchen."""


def pick(data, key, default=None):
    """Feld ohne Rücksicht auf Groß-/Kleinschreibung (jwtToken, JwtToken …)."""
    if not isinstance(data, dict):
        return default
    if key in data:
        return data[key]
    lowered = key.lower()
    return next((v for k, v in data.items() if k.lower() == lowered), default)


def jwt_expiry(token):
    """Ablauf (Unix-Zeit) eines JWT, 0 wenn unlesbar. Die Signatur prüft nur der Server."""
    try:
        part = token.split(".")[1]
        return float(json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))["exp"])
    except (IndexError, ValueError, KeyError, TypeError, AttributeError):
        return 0


def server_message(body):
    """Fehlertext aus der Antwort des Servers (message, title, detail, errors)."""
    try:
        data = json.loads(body)
    except ValueError:
        return body.strip()[:300]
    if not isinstance(data, dict):
        return ""
    parts = [str(pick(data, k)) for k in ("message", "title", "detail") if pick(data, k)]
    errors = pick(data, "errors")
    if isinstance(errors, dict):
        parts += [f"{k}: {' '.join(map(str, v if isinstance(v, list) else [v]))}" for k, v in errors.items()]
    return " – ".join(parts)


def _request(url, body=None, token=None):
    """JSON senden/holen. None bei leerer Antwort (das alte Backend schickt 204 statt [])."""
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        if e.code in (408, 429, 500, 502, 503, 504):
            raise AuthNetworkError(f"ITM-Server meldet {e.code}") from None
        raise AuthError(e.code, f"HTTP {e.code}: {server_message(text) or e.reason}") from None
    except OSError as e:
        raise AuthNetworkError(f"ITM nicht erreichbar ({e})") from None
    return json.loads(raw) if raw.strip() else None


# ------------------------------------------------------------ refreshToken geschützt ablegen

def protect(text):
    """Text für die Ablage verschlüsseln (Windows: DPAPI, sonst nur kodiert)."""
    raw = text.encode("utf-8")
    if sys.platform == "win32":
        return "dpapi:" + base64.b64encode(_dpapi(raw, encrypt=True)).decode("ascii")
    return "plain:" + base64.b64encode(raw).decode("ascii")


def unprotect(text):
    """Gegenstück zu protect(). Leerer Text, wenn es nicht geht (anderer Benutzer/PC)."""
    try:
        kind, _, data = (text or "").partition(":")
        raw = base64.b64decode(data)
        if kind == "dpapi" and sys.platform == "win32":
            return _dpapi(raw, encrypt=False).decode("utf-8")
        if kind == "plain":
            return raw.decode("utf-8")
    except (ValueError, OSError, UnicodeDecodeError):
        pass
    return ""


def _dpapi(data, encrypt):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = Blob()
    crypt = ctypes.windll.crypt32
    func = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    ok = func(ctypes.byref(blob_in), None, None, None, None, 0x01, ctypes.byref(blob_out))  # UI_FORBIDDEN
    if not ok:
        raise OSError("DPAPI fehlgeschlagen")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


# ------------------------------------------------------------ Anmeldung

class ItmAuth:
    """Hält jwtToken und refreshToken und erneuert das kurzlebige jwtToken selbst."""

    def __init__(self, base_url, store_file):
        self.base_url = (base_url or DEFAULT_URL).strip().rstrip("/")
        self.store_file = store_file
        self.jwt = ""
        self.refresh_token = ""
        self.profile = {}  # Name, Personalnummer, Mandant (nach Anmeldung mit Passwort)
        self._lock = threading.Lock()
        self._load()

    # ---- Ablage

    def _load(self):
        data = safe_io.read_json(self.store_file, {}, expect=dict) if os.path.exists(self.store_file) else {}
        self.refresh_token = unprotect(data.get("refresh", ""))
        self.profile = data.get("profil") or {}

    def _save(self):
        os.makedirs(os.path.dirname(self.store_file) or ".", exist_ok=True)
        data = {"refresh": protect(self.refresh_token) if self.refresh_token else "",
                "profil": self.profile, "gespeichert": f"{datetime.now():%Y-%m-%d %H:%M:%S}"}
        safe_io.write_json(self.store_file, data)

    def forget(self):
        """Abmelden: Tokens verwerfen."""
        with self._lock:
            self.jwt = self.refresh_token = ""
            self.profile = {}
            self._save()

    @property
    def has_login(self):
        return bool(self.refresh_token)

    # ---- Anmelden und erneuern

    def login(self, username, password, mandant_id):
        """Mit Passwort anmelden. Gibt das Profil zurück (Name, Personalnummer, Rollen)."""
        body = {"username": username, "password": password, "mandantID": int(mandant_id)}
        try:
            data = _request(f"{self.base_url}/auth/authenticate", body)
        except AuthError as e:
            if e.status == 401:
                e.args = (f"{e} – Benutzer, Passwort oder Mandant falsch, oder der Mandant lässt "
                          "Anmeldungen von dieser IP-Adresse nicht zu (VPN?)",)
            raise
        with self._lock:
            self._store(data)
            self.profile = {k: pick(data, k) for k in
                            ("username", "firstName", "lastName", "personalnummer", "mitarbeiterID",
                             "mandantID", "mandantName")}
            self._save()
        return data

    def adopt(self, refresh_token):
        """refreshToken aus dem Cookie der Web-App übernehmen, wenn Zeitzeuge selbst keins hat."""
        if refresh_token and not self.refresh_token:
            with self._lock:
                self.refresh_token = refresh_token
                self._save()

    def token(self):
        """Gültiges jwtToken oder None (dann ist eine Anmeldung nötig).
        AuthNetworkError, wenn der Dienst gerade nicht erreichbar ist."""
        with self._lock:
            if self.jwt and jwt_expiry(self.jwt) > time.time() + REFRESH_MARGIN:
                return self.jwt
            if not self.refresh_token:
                return None
            try:
                data = _request(f"{self.base_url}/auth/refresh-token-body", {"token": self.refresh_token})
            except AuthError as e:
                # Abgelaufen oder widerrufen: nicht immer wieder versuchen
                safe_io.log(f"ITM: Anmeldung nicht erneuert ({e})")
                self.jwt = self.refresh_token = ""
                self._save()
                return None
            old = self.refresh_token
            self._store(data)
            if self.refresh_token != old:
                self._save()
            return self.jwt

    def drop_jwt(self):
        """jwtToken wurde abgelehnt: beim nächsten token() neu holen."""
        with self._lock:
            self.jwt = ""

    def _store(self, data):
        jwt = pick(data, "jwtToken")
        if not jwt:
            raise AuthError(0, "Antwort des Anmeldedienstes ohne jwtToken")
        self.jwt = jwt
        self.refresh_token = pick(data, "refreshToken") or self.refresh_token

    def get(self, path, token=None):
        """GET {base}/api/{path} mit jwtToken."""
        return _request(f"{self.base_url}/api/{path.lstrip('/')}", token=token or self.token())


# ------------------------------------------------------------ eigene Buchungen

def _time(text):
    """'2026-10-20T08:10:00.000' -> '2026-10-20 08:10:00'"""
    return str(text).replace("T", " ")[:19] if text else None


def bookings_from_legacy(rows):
    """Antwort von Personalzeit/view/minimal/tage/N -> [{"start", "end", "minutes"}]."""
    result = []
    for row in rows if isinstance(rows, list) else []:
        start = _time(pick(row, "Start") or pick(row, "GewertetStart"))
        if not start:
            continue
        end = _time(pick(row, "Ende") or pick(row, "GewertetEnde"))
        minutes = pick(row, "GewertetDauer")
        result.append({"start": start, "end": end,
                       "minutes": minutes if isinstance(minutes, int) else None})
    return sorted(result, key=lambda b: b["start"])


def days_from_bookings(bookings):
    """Buchungen nach Tagen, im Format von personalzeiten.json (ohne Soll und Pause)."""
    days = {}
    for b in bookings:
        day = days.setdefault(b["start"][:10], {"soll": None, "gewertet": 0, "pause": None,
                                                 "zeiten": [], "quelle": "ITM alt"})
        day["zeiten"].append({"start": b["start"], "end": b["end"]})
        day["gewertet"] += b["minutes"] or 0
    return days


def booking_issues(bookings, now=None):
    """Fehlerhafte Buchungen: [(Schlüssel, Text)], Schlüssel bleibt für dieselbe Buchung gleich."""
    now = now or datetime.now()
    issues = []
    for b in bookings:
        try:
            start = datetime.strptime(b["start"], "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(b["end"], "%Y-%m-%d %H:%M:%S") if b.get("end") else None
        except (KeyError, TypeError, ValueError):
            continue
        when = f"{start:%d.%m. %H:%M}"
        if end is None:
            if now - start > OPEN_LIMIT:
                issues.append((f"offen {b['start']}",
                               f"Buchung vom {when} ist seit über 12 Stunden offen – Ausstempeln vergessen?"))
        elif end <= start:
            issues.append((f"ende {b['start']}", f"Buchung vom {when}: Ende liegt vor dem Start"))
        elif end - start > OPEN_LIMIT:
            issues.append((f"lang {b['start']}", f"Buchung vom {when} dauert länger als 12 Stunden"))
    return issues
