"""
Personalzeiten aus der ITM-Zeiterfassung (app.itm-gruppe.com) lesen.

Wie beim 3CX-Auslesen läuft Edge unsichtbar mit eigenem Profil (Ordner
itm_profil). Zeitzeuge öffnet die Tagesübersicht eines Tages und merkt sich
die Antwort, mit der die Seite ihre Daten lädt (JSON mit "personalzeiten").
Die Adresse dieser Abfrage muss Zeitzeuge dafür nicht kennen.

Gelesene Tage landen in personalzeiten.json. Heute wird alle 5 Minuten neu
gelesen, andere Tage einmal, sobald sie angezeigt werden.

Anmeldung (itm_auth.py): Zeitzeuge erneuert das Zugangstoken selbst mit dem
refreshToken (gilt 7 Tage, wird bei jedem Erneuern verlängert). Das refreshToken kommt
aus einer Anmeldung mit Benutzer, Mandant und Passwort oder aus dem Cookie der Web-App
nach einer Anmeldung im Edge-Fenster. Edge startet nur noch, wenn das nicht klappt.

Aus dem alten ITM-Backend holt Zeitzeuge alle 30 Minuten die eigenen Buchungen der
letzten 45 Tage: fehlende Tage werden damit aufgefüllt, und fehlerhafte Buchungen
(offen seit über 12 Stunden, Ende vor Start …) meldet Zeitzeuge einmal.
"""

import base64
import json
import os
import re
import threading
import time
from datetime import date, datetime
import urllib.error
import urllib.request
from urllib.parse import unquote, urlsplit

from PySide6.QtCore import Signal

import datastore
import safe_io
from itm_auth import (AuthError, AuthNetworkError, ItmAuth, booking_issues, bookings_from_legacy,
                      days_from_bookings)
from pbx_reader import BrowserReader

# Läuft in der Seite vor deren eigenem Code und merkt sich jede Antwort mit Tagesdaten
CAPTURE_JS = r"""
(function () {
  window.__zz = {};
  function keep(d) {
    if (typeof d === "string") { try { d = JSON.parse(d); } catch (e) { return; } }
    if (d && d.datum && Array.isArray(d.personalzeiten)) window.__zz[String(d.datum).slice(0, 10)] = d;
  }
  const origFetch = window.fetch;
  if (origFetch) window.fetch = function () {
    return origFetch.apply(this, arguments).then(function (r) {
      try { r.clone().text().then(keep, function () {}); } catch (e) {}
      return r;
    });
  };
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function () {
    this.addEventListener("load", function () {
      try { keep(this.responseType === "json" ? this.response : this.responseText); } catch (e) {}
    });
    return send.apply(this, arguments);
  };
})();
"""

STATE_JS = (
    "JSON.stringify({host: location.host, path: location.pathname,"
    " password: !!document.querySelector('input[type=password]'),"
    " data: (window.__zz || {})[%s] || null})"
)


def _time(text):
    """'2026-10-20T08:10:00' -> '2026-10-20 08:10:00'"""
    return text.replace("T", " ")[:19] if text else None


def day_from_api(data):
    """Antwort der Tagesübersicht auf das kürzen, was Zeitzeuge braucht."""
    numbers = data.get("kennzahlen") or {}
    times = [
        {"start": _time(p["start"]), "end": _time(p.get("ende"))}
        for p in data.get("personalzeiten") or [] if p.get("start")
    ]
    return {
        "soll": numbers.get("sollMinuten"),
        "gewertet": numbers.get("gewerteteDauerMinuten"),
        "pause": (numbers.get("pause") or {}).get("summeMinuten"),
        "zeiten": sorted(times, key=lambda t: t["start"]),
    }


class DirectFailed(Exception):
    """Die Direkt-Abfrage klappt nicht (anderes Format, unerwartete Antwort …)."""


class NetworkError(OSError):
    """Server gerade nicht erreichbar (kein Internet, Zeitüberschreitung). Nur ein
    Fehlversuch: Die Direkt-Abfrage bleibt an, es wird später erneut versucht."""


# Diese HTTP-Fehler sind vorübergehend (Server überlastet, Wartung), kein anderes Format
TEMPORARY_HTTP = {408, 429, 500, 502, 503, 504}


def session_token(cookies, host):
    """JwtToken aus dem Cookie "session" der App (JSON, evtl. URL- oder Base64-kodiert)."""
    return session_data(cookies, host).get("JwtToken")


def session_data(cookies, host):
    """Inhalt des Cookies "session" der App (JwtToken, RefreshToken), {} wenn keins."""
    for c in cookies:
        if c.get("name") != "session" or not host.endswith(c.get("domain", "").lstrip(".")):
            continue
        value = c.get("value") or ""
        for text in (unquote(value), value):
            for candidate in (text, _b64(text)):
                try:
                    data = json.loads(candidate) if candidate else None
                except ValueError:
                    continue
                if isinstance(data, dict) and data.get("JwtToken"):
                    return data
    return {}


def _b64(text):
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def token_expiry(token):
    """Ablauf (Unix-Zeit) eines JWT, 0 wenn unlesbar."""
    try:
        part = token.split(".")[1]
        return float(json.loads(_b64(part)).get("exp", 0))
    except (IndexError, ValueError, AttributeError, TypeError):
        return 0


def load_days(path):
    """Gespeicherte Tage (Ablage "personalzeiten" in der Datenbank). Kaputte Tage übersprungen."""
    try:
        store, name = datastore.locate(path, "days")
        data = store.all(name)
    except (datastore.Busy, datastore.Locked) as e:
        safe_io.log(f"Personalzeiten gerade nicht lesbar: {e}")
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)}


def save_day(path, date_str, day):
    try:
        store, name = datastore.locate(path, "days")
        store.put(name, date_str, day)
    except (datastore.Busy, datastore.Locked) as e:
        safe_io.report(f"Personalzeiten: Speichern fehlgeschlagen ({e})")


class ItmReader(BrowserReader):
    day_read = Signal(str)  # Datum (YYYY-MM-DD), dessen Personalzeiten neu sind
    issues_found = Signal(list)  # neue fehlerhafte Buchungen (Texte), je Buchung einmal
    login_finished = Signal(str)  # Anmeldung mit Passwort: "" = geklappt, sonst Fehlertext

    NAME = "ITM"
    READ_INTERVAL = 5 * 60  # heute alle 5 Minuten neu lesen
    LOAD_TIMEOUT = 25       # so lange auf die Daten einer Seite warten
    TOKEN_TIMEOUT = 90      # so lange darf Edge zum Erneuern der Anmeldung laufen
    # Edge läuft nicht dauerhaft: Die Daten fragt Zeitzeuge direkt ab, Edge startet nur
    # kurz, wenn das Zugangstoken (gilt etwa 1 Stunde) erneuert werden muss.
    START_BROWSER = False
    LEGACY_INTERVAL = 30 * 60  # eigene Buchungen aus dem alten Backend so oft holen
    LEGACY_DAYS = 45

    def __init__(self, base_url, data_file, profile_dir, parent=None, auth_file=None, auth_url=""):
        # Steht in der Einstellung schon die Seite (…/zeiterfassung/tageszeiten), würde
        # sie sonst doppelt angehängt und ITM zeigt "Not found".
        base_url = base_url.strip().split("?")[0].split("#")[0]
        base_url = re.sub(r"/zeiterfassung(/.*)?$", "", base_url.rstrip("/"))
        super().__init__(base_url, profile_dir, parent)
        self.data_file = data_file
        self.days = load_days(data_file)
        self._wanted = set()
        self._checked = set()  # in dieser Sitzung schon gelesene Tage
        self._lock = threading.Lock()
        self._today_read = 0
        self._token = None      # JwtToken aus dem Cookie "session"
        self._api = None        # Adresse der Daten-API (aus appsettings.Live.json)
        self._direct_ok = True  # False: Direkt-Abfrage klappt nicht, über die Webseite lesen
        # Anmeldung ohne Edge (refreshToken). Adresse: Einstellung, sonst ApiUri der App
        self._auth_url = (auth_url or "").strip().rstrip("/")
        self.auth = ItmAuth(self._auth_url, auth_file or os.path.join(
            os.path.dirname(os.path.abspath(profile_dir)), "itm_anmeldung.json"))
        self._auth_for_v2 = True   # False: die Tages-API nimmt das Token des Anmeldedienstes nicht
        self._token_from_auth = False
        self.username = ""         # gesetzt: Anmeldung mit Passwort statt Edge-Fenster
        self.mandant = 0
        self.password_prompt = None  # Funktion(parent), fragt das Passwort ab (Hauptfenster)
        self._legacy_next = 0
        self._legacy_bookings = []
        self._issues_told = set()
        self.issues = []           # aktuelle fehlerhafte Buchungen (Texte)

    def day_url(self, date_str):
        return f"{self.base_url}/zeiterfassung/tageszeiten?date={date_str}"

    def start_url(self):
        return self.day_url(date.today().isoformat())

    def day(self, date_str):
        """Gespeicherte Personalzeiten eines Tages oder None."""
        return self.days.get(date_str)

    def want(self, date_str):
        """Tag lesen lassen, z. B. weil er angezeigt wird (einmal pro Sitzung,
        damit nachträgliche Korrekturen in ITM ankommen)."""
        if date_str >= date.today().isoformat() or date_str in self._checked:
            return  # heute liest die Schleife selbst, Zukunft gibt es nicht
        with self._lock:
            self._wanted.add(date_str)
        if not self.needs_login:  # ohne Anmeldung erst nach dem Anmelden lesen
            self._wake.set()

    # ------------------------------------------------------------ Lesen

    def _on_browser_started(self):
        self._tools.call("Page.enable")  # sonst wird das Skript nicht eingespielt
        self._tools.call("Page.addScriptToEvaluateOnNewDocument", source=CAPTURE_JS)
        # Tagesdaten immer frisch vom Server holen: Aus dem Zwischenspeicher käme sonst
        # beim erneuten Lesen von heute der Stand vom Morgen (z. B. nur "eingestempelt seit 08:09")
        self._tools.call("Network.enable")
        self._tools.call("Network.setCacheDisabled", cacheDisabled=True)
        self._tools.call("Network.setBypassServiceWorker", bypass=True)

    def _tick(self):
        today = date.today().isoformat()
        with self._lock:
            todo = sorted(self._wanted, reverse=True)
            self._wanted.clear()
        if time.time() - self._today_read > self.READ_INTERVAL - 10:
            todo.insert(0, today)
        for i, date_str in enumerate(todo):
            try:
                ok = not self._stop.is_set() and not self._login_open and self._read_day(date_str)
            except Exception:  # z. B. offline: angeforderte Tage nicht vergessen
                with self._lock:
                    self._wanted.update(d for d in todo[i:] if d != today)
                raise
            if not ok:
                with self._lock:  # später nachholen
                    self._wanted.update(d for d in todo[i:] if d != today)
                return
            if date_str == today:
                self._today_read = time.time()
        self._read_legacy()
        self._check_issues()

    def _read_day(self, date_str):
        """Einen Tag lesen. False, wenn eine Anmeldung nötig ist."""
        if self._direct_ok:
            try:
                return self._read_day_direct(date_str)
            except DirectFailed as e:
                # Schnittstelle geändert o. Ä.: wie früher über die Webseite lesen
                self._direct_ok = False
                self._set_status(f"ITM: Direkt-Abfrage geht nicht ({e}), lese über die Webseite")
        if not self._tools:
            self._start_browser()
        return self._read_day_browser(date_str)

    # ---- direkt (ohne Webseite)

    def _read_day_direct(self, date_str):
        self._set_status(f"ITM: lese {date_str} …")
        retried = False
        for _ in range(3):
            token = self._valid_token()
            if not token:
                self._need_login()
                return False
            try:
                data = self._api_get(f"tagesuebersicht?datum={date_str}", token)
            except urllib.error.HTTPError as e:
                if e.code == 401 and self._token_from_auth:
                    # Token des Anmeldedienstes gilt hier nicht: wie bisher über Edge
                    self._auth_for_v2 = False
                    safe_io.log("ITM: Tagesübersicht nimmt das erneuerte Token nicht an, nehme Edge")
                    continue
                if e.code == 401 and not retried:
                    retried = True
                    self._token = None  # abgelaufen: neues holen und noch einmal
                    continue
                if e.code in TEMPORARY_HTTP:
                    raise NetworkError(f"ITM-Server meldet {e.code}") from e
                raise DirectFailed(f"HTTP {e.code}") from e
            except ValueError as e:  # Antwort ist kein JSON: anderes Format
                raise DirectFailed(str(e)) from e
            except OSError as e:  # kein Netz, Zeitüberschreitung: später noch einmal
                raise NetworkError(f"ITM nicht erreichbar ({e})") from e
            if not isinstance(data, dict) or not isinstance(data.get("personalzeiten"), list):
                raise DirectFailed("Antwort ohne Personalzeiten")
            self.needs_login = False
            self._checked.add(date_str)
            self._save(date_str, day_from_api(data))
            self._set_status(f"ITM gelesen {datetime.now():%H:%M}")
            return True
        raise DirectFailed("Anmeldung wird nicht angenommen")

    def _api_base(self):
        """Adresse der Daten-API, so wie die App sie aus ihren Einstellungen liest."""
        if self._api:
            return self._api
        api = None
        network_error = None
        for name in ("appsettings.Live.json", "appsettings.json"):
            try:
                with urllib.request.urlopen(f"{self.base_url}/{name}", timeout=15) as resp:
                    uris = json.load(resp).get("BaseUriConfiguration") or {}
                api = uris.get("V2BackendUri") or uris.get("ApiUri")
                legacy = uris.get("ApiUri") or ""
                if legacy and "localhost" not in legacy and not self._auth_url:
                    # Altes Backend mit Anmeldedienst ({url}/auth, {url}/api)
                    self.auth.base_url = re.sub(r"/api/?$", "", legacy.rstrip("/"))
            except urllib.error.HTTPError as e:
                if e.code in TEMPORARY_HTTP:
                    network_error = e
                continue
            except (ValueError, AttributeError):
                continue
            except OSError as e:  # kein Netz: das ist kein Grund, die Direkt-Abfrage abzuschalten
                network_error = e
                continue
            if api and "localhost" not in api:
                break
            api = None
        if not api and network_error is not None:
            raise NetworkError(f"ITM nicht erreichbar ({network_error})")
        if not api:
            raise DirectFailed("Adresse der Schnittstelle nicht gefunden")
        self._api = api.rstrip("/") + "/"
        return self._api

    def _api_get(self, path, token):
        req = urllib.request.Request(self._api_base() + path, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)

    def _valid_token(self):
        """Gültiges Zugangstoken oder None (dann ist eine Anmeldung nötig).

        Zuerst ohne Edge mit dem refreshToken, sonst wie bisher über Edge. Wer sich mit
        Passwort anmeldet (username gesetzt), braucht Edge gar nicht."""
        self._token_from_auth = False
        if self._auth_for_v2 and self.auth.has_login:
            try:
                token = self._auth_token()
            except NetworkError as e:  # Anmeldedienst nicht erreichbar: wie bisher über Edge
                safe_io.log(f"ITM: {e}")
                token = None
            if token:
                self._token_from_auth = True
                return token
        if self._token and token_expiry(self._token) > time.time() + 60:
            return self._token
        if self.username and self._auth_for_v2:
            return None  # Passwort nötig (show_login fragt danach)
        self._token = self._fetch_token()
        return self._token

    def _auth_token(self):
        """Token vom Anmeldedienst (erneuert bei Bedarf), None ohne gültige Anmeldung."""
        self._api_base()  # liest die Adresse des Anmeldedienstes mit
        try:
            return self.auth.token()
        except AuthNetworkError as e:
            raise NetworkError(str(e)) from e

    def _fetch_token(self):
        """Edge kurz unsichtbar starten: Die App erneuert dabei ihr Token und legt es im
        Cookie "session" ab. Danach wird Edge wieder beendet."""
        self._set_status("ITM: erneuere Anmeldung …")
        own = not self._tools
        if own:
            self._start_browser()
        self._tools.call("Page.navigate", url=self.start_url())
        token = None
        try:
            deadline = time.time() + self.TOKEN_TIMEOUT
            while time.time() < deadline and not self._stop.is_set():
                time.sleep(1)
                cookies = self._tools.call("Network.getAllCookies").get("cookies", [])
                session = session_data(cookies, urlsplit(self.base_url).hostname)
                token = session.get("JwtToken") or token
                # Mit dem refreshToken der App erneuert Zeitzeuge künftig selbst, ohne Edge
                self.auth.adopt(session.get("RefreshToken"))
                if token and token_expiry(token) > time.time() + 120:
                    return token
                try:
                    state = json.loads(self._evaluate(STATE_JS % '""', timeout=5) or "null")
                except (RuntimeError, ValueError):
                    continue
                if state and (state["password"] or "login" in state["path"].lower()
                              or state["host"] != urlsplit(self.base_url).netloc):
                    return None  # Anmeldeseite: du musst dich anmelden
            if token and token_expiry(token) > time.time():
                return token  # gilt nur noch kurz, reicht aber für diesen Durchlauf
            if token:
                raise DirectFailed("Anmeldung wurde nicht erneuert")
            return None
        finally:
            if own:
                # Sauber beenden: Hart beendet schreibt Edge die erneuerte Anmeldung
                # (Cookies, Speicher der Seite) unter Windows nicht mehr ins Profil, und
                # beim nächsten Erneuern hieße es "Anmeldung nötig"
                port = getattr(self, "_port", None)
                if port and self._tools:
                    self._close_gracefully(port)
                self._close_browser()

    # ---- über die Webseite (Rückfall)

    def _read_day_browser(self, date_str):
        self._set_status(f"ITM: lese {date_str} …")
        try:  # Daten der noch angezeigten Seite vergessen, damit nur die neue Seite zählt
            self._evaluate("window.__zz = {}", timeout=5)
        except Exception:
            pass  # z. B. leere Seite direkt nach dem Start
        self._tools.call("Page.navigate", url=self.day_url(date_str))
        js = STATE_JS % json.dumps(date_str)
        state = None
        deadline = time.time() + self.LOAD_TIMEOUT
        while time.time() < deadline and not self._stop.is_set():
            time.sleep(0.5)
            try:
                state = json.loads(self._evaluate(js) or "null")
            except (RuntimeError, ValueError):
                continue  # Seite wird gerade neu aufgebaut
            if state and state["data"]:
                self.needs_login = False
                self._checked.add(date_str)
                self._save(date_str, day_from_api(state["data"]))
                self._set_status(f"ITM gelesen {datetime.now():%H:%M}")
                return True

        if state and (state["password"] or "login" in state["path"].lower()
                      or state["host"] != urlsplit(self.base_url).netloc):
            self._need_login()
            return False
        self._set_status(f"ITM: keine Personalzeiten für {date_str} gefunden")
        return True

    # ---- altes Backend: eigene Buchungen, fehlerhafte Buchungen

    def _read_legacy(self):
        """Eigene Buchungen der letzten Tage aus dem alten Backend (alle 30 Minuten).
        Fehler hier stören das normale Lesen nicht."""
        if time.time() < self._legacy_next or self._stop.is_set():
            return
        self._legacy_next = time.time() + self.LEGACY_INTERVAL
        try:
            token = self._auth_token() if self.auth.has_login else None
            if not token and self._token and token_expiry(self._token) > time.time() + 30:
                token = self._token  # Token aus Edge; ob das alte Backend es nimmt, zeigt sich
            if not token:
                return
            rows = self.auth.get(f"Personalzeit/view/minimal/tage/{self.LEGACY_DAYS}", token)
        except (AuthError, DirectFailed, NetworkError, OSError, ValueError) as e:
            safe_io.log(f"ITM: eigene Buchungen aus dem alten Backend nicht gelesen ({e})")
            return
        self._legacy_bookings = bookings_from_legacy(rows)
        today = date.today().isoformat()
        for day, data in days_from_bookings(self._legacy_bookings).items():
            known = self.days.get(day)
            # Nur auffüllen: Tage aus der Tagesübersicht haben Soll und Pause und bleiben
            if day < today and (known is None or known.get("quelle") == "ITM alt"):
                self._save(day, data)

    def _check_issues(self):
        """Fehlerhafte Buchungen suchen und neue einmal melden."""
        today = (self.days.get(date.today().isoformat()) or {}).get("zeiten") or []
        found = dict(booking_issues(self._legacy_bookings) + booking_issues(today))
        self.issues = list(found.values())
        new = [text for key, text in found.items() if key not in self._issues_told]
        self._issues_told.update(found)
        if new:
            self.issues_found.emit(new)

    # ---- Anmeldung mit Passwort (ohne Edge)

    def show_login(self, parent=None):
        """Mit Benutzername: Passwort abfragen. Sonst Edge-Fenster wie bisher."""
        if self.username and self.password_prompt:
            self.password_prompt(parent)
        else:
            super().show_login(parent)

    def login_password(self, username, password, mandant):
        """Im Hintergrund anmelden. Ergebnis über login_finished."""
        def run():
            self._set_status("ITM: melde an …")
            try:
                try:
                    self._api_base()  # Adresse des Anmeldedienstes aus der App
                except (DirectFailed, NetworkError):
                    pass  # dann die Standardadresse
                profile = self.auth.login(username, password, mandant)
            except (AuthError, AuthNetworkError, ValueError) as e:
                self._set_status(f"ITM: Anmeldung fehlgeschlagen ({e})")
                self.login_finished.emit(str(e))
                return
            self._auth_for_v2 = True
            self.needs_login = False
            name = f"{profile.get('firstName') or ''} {profile.get('lastName') or ''}".strip()
            self._set_status(f"ITM: angemeldet{' als ' + name if name else ''}, lese …")
            self.login_finished.emit("")
            self._wake.set()
        threading.Thread(target=run, daemon=True, name="ITM-Anmeldung").start()

    def _save(self, date_str, day):
        if self.days.get(date_str) == day:
            return
        self.days[date_str] = day
        save_day(self.data_file, date_str, day)
        self.day_read.emit(date_str)

    def _login_done(self):
        try:  # Tagesdaten kamen an: angemeldet (Skript zum Merken läuft im Anmeldefenster mit)
            return bool(self._evaluate("Object.keys(window.__zz || {}).length", timeout=5))
        except Exception:
            return False
