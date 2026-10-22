"""
Personalzeiten aus der ITM-Zeiterfassung (app.itm-gruppe.com) lesen.

Wie beim 3CX-Auslesen läuft Edge unsichtbar mit eigenem Profil (Ordner
itm_profil). Zeitzeuge öffnet die Tagesübersicht eines Tages und merkt sich
die Antwort, mit der die Seite ihre Daten lädt (JSON mit "personalzeiten").
Die Adresse dieser Abfrage muss Zeitzeuge dafür nicht kennen.

Gelesene Tage landen in personalzeiten.json. Heute wird alle 5 Minuten neu
gelesen, andere Tage einmal, sobald sie angezeigt werden.
"""

import json
import os
import re
import threading
import time
from datetime import date, datetime
from urllib.parse import urlsplit

from PyQt5.QtCore import pyqtSignal

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


def load_days(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


class ItmReader(BrowserReader):
    day_read = pyqtSignal(str)  # Datum (YYYY-MM-DD), dessen Personalzeiten neu sind

    NAME = "ITM"
    READ_INTERVAL = 5 * 60  # heute alle 5 Minuten neu lesen
    LOAD_TIMEOUT = 25       # so lange auf die Daten einer Seite warten

    def __init__(self, base_url, data_file, profile_dir, parent=None):
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
            if self._stop.is_set() or self._login_open or not self._read_day(date_str):
                with self._lock:  # später nachholen
                    self._wanted.update(d for d in todo[i:] if d != today)
                return
            if date_str == today:
                self._today_read = time.time()

    def _read_day(self, date_str):
        """Einen Tag lesen. False, wenn eine Anmeldung nötig ist."""
        self._set_status(f"ITM: lese {date_str} …")
        try:  # Daten der noch angezeigten Seite vergessen, damit nur die neue Seite zählt
            self._evaluate("window.__zz = {}")
        except RuntimeError:
            pass
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

    def _save(self, date_str, day):
        if self.days.get(date_str) == day:
            return
        self.days[date_str] = day
        tmp = self.data_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.days, f, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, self.data_file)
        self.day_read.emit(date_str)

    def _login_done(self):
        try:  # Tagesdaten kamen an: angemeldet (Skript zum Merken läuft im Anmeldefenster mit)
            return bool(self._evaluate("Object.keys(window.__zz || {}).length", timeout=5))
        except Exception:
            return False
