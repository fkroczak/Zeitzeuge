"""
Hintergrund-Leser für Outlook (Termine, gesendete Mails) und Teams-Anrufe.

Ein eigener Thread:
- Teams: alle 30 Sekunden die Mikrofon-Nutzung prüfen, die Logs bei Änderung lesen.
- Outlook: alle outlook_interval_minutes die letzten outlook_days_back Tage bis morgen
  lesen (PowerShell-Unterprozess mit Zeitlimit), ältere Tage beim Blättern (want).
Signale kommen aus dem Thread, Qt stellt sie im Fenster-Thread zu.
Schnittstelle wie die anderen Leser (start, stop, alive, check_hung, want, health, busy),
damit Wächter, Beenden und Blättern ihn mitnehmen.
"""

import threading
import time
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Signal

import outlook_data
import safe_io
import teams_calls


class OutlookReader(QObject):
    status_changed = Signal(str)
    day_read = Signal(str)   # Tag (JJJJ-MM-TT) mit neuen Daten
    trouble = Signal(str)    # einmal nach mehreren Fehlschlägen in Folge
    busy_changed = Signal()

    NAME = "Outlook"
    TICK = 30                 # Sekunden zwischen zwei Blicken (Teams-Mikrofon)
    TROUBLE_AFTER = 5

    def __init__(self, config, outlook_file, teams_file, parent=None, runner=None, mic_func=None,
                 log_globs=None):
        super().__init__(parent)
        self.config = config
        self.outlook_file = outlook_file
        self.teams_file = teams_file
        self.runner = runner  # Tests: Ersatz für den PowerShell-Aufruf
        self.teams = teams_calls.TeamsCallTracker(teams_file, mic_func=mic_func, log_globs=log_globs)
        self.status = "Outlook: startet …"
        self.needs_login = False
        self.last_ok = None
        self._failed = False
        self._failures = 0
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._next_outlook = 0.0
        self._wanted = []
        self._done = set()     # ältere Tage, die in dieser Sitzung schon gelesen wurden
        self._step_started = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ Steuerung

    def outlook_on(self):
        return bool(self.config.get("outlook_enabled"))

    def teams_on(self):
        return bool(self.config.get("teams_calls_enabled"))

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="Leser Outlook")
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    @property
    def stopped(self):
        return self._stop.is_set()

    def alive(self):
        return bool(self._thread and self._thread.is_alive())

    def check_hung(self):
        """PowerShell hat ein eigenes Zeitlimit; hier gibt es nichts abzubrechen."""
        return False

    def read_now(self):
        """Outlook beim nächsten Blick lesen (z. B. nach dem Einrichten)."""
        self._next_outlook = 0.0
        self._wake.set()

    def want(self, date_str):
        """Tag anzeigen: ältere Tage einmal je Sitzung nachlesen."""
        if not self.outlook_on() or date_str in self._done:
            return
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return
        if day >= self._range()[0] or day > datetime.now():
            return
        with self._lock:
            if date_str not in self._wanted:
                self._wanted.append(date_str)
        self._wake.set()

    # ------------------------------------------------------------ Zustand

    def health(self):
        if self._failed:
            return "warn", "Fehler"
        if not self.last_ok:
            return "busy", "lädt …"
        return "ok", f"{self.last_ok:%H:%M}"

    def busy(self):
        return self._step_started is not None

    def first_load(self):
        return not self.last_ok

    def _set_status(self, text):
        self.status = text
        self.status_changed.emit(text)

    # ------------------------------------------------------------ Lesen

    def _range(self, now=None):
        now = now or datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        back = max(0, int(self.config.get("outlook_days_back", 14) or 0))
        return today - timedelta(days=back), today + timedelta(days=1)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.step()
            except Exception as e:  # nie den Thread verlieren
                safe_io.log(f"Outlook-Leser: {e!r}")
            self._wake.wait(self.TICK)
            self._wake.clear()

    def step(self, now=None):
        """Ein Durchlauf (auch aus Tests direkt aufrufbar)."""
        now = now or datetime.now()
        if self.teams_on():
            self.teams.use_logs = self.config.get("teams_logs_enabled", True)
            for day in self.teams.sample(now):
                self.day_read.emit(day)
        if not self.outlook_on():
            return
        with self._lock:
            wanted, self._wanted = self._wanted, []
        for day in wanted:
            start = datetime.strptime(day, "%Y-%m-%d")
            self._read(start, start + timedelta(days=1), now)
            self._done.add(day)
        if time.monotonic() >= self._next_outlook:
            minutes = max(1, int(self.config.get("outlook_interval_minutes", 10) or 10))
            self._next_outlook = time.monotonic() + minutes * 60
            self._read(*self._range(now), now)

    def _read(self, start, end, now):
        self._step_started = time.time()
        self.busy_changed.emit()
        try:
            result = outlook_data.read_outlook(start, end, self.config, runner=self.runner)
        finally:
            self._step_started = None
            self.busy_changed.emit()
        if not result.get("ok"):
            self._failures += 1
            # "nicht geöffnet" ist kein Fehler: dann eben beim nächsten Mal
            self._failed = result.get("fehler") != "nicht_geoeffnet"
            if result.get("fehler") in ("nicht_geoeffnet", "zeitlimit"):
                self._next_outlook = min(self._next_outlook, time.monotonic() + 2 * 60)
            self._set_status(outlook_data.status_text(result, now))
            if self._failed and self._failures == self.TROUBLE_AFTER:
                self.trouble.emit(self.status)
            return
        self._failures = 0
        self._failed = False
        self.last_ok = now
        days = outlook_data.split_days(result, start, end, now,
                                       calendar=self.config.get("outlook_calendar_enabled", True),
                                       mails=self.config.get("outlook_mails_enabled", True))
        for day in outlook_data.save_days(self.outlook_file, days):
            self.day_read.emit(day)
        self._set_status(outlook_data.status_text(result, now))

    # ------------------------------------------------------------ Anzeige

    def entries(self, date_str):
        """Einträge eines Tages für die Timeline (gelesen aus der Ablage)."""
        return day_entries(self.config, self.outlook_file, self.teams_file, date_str)


def day_entries(config, outlook_file, teams_file, date_str):
    """Termine, Mails und Teams-Anrufe eines Tages aus der Ablage. Abgeschaltete Quellen
    liefern nichts (auch nicht, was früher gelesen wurde)."""
    result, meetings = [], []
    if config.get("outlook_enabled"):
        doc = outlook_data.load_day(outlook_file, date_str)
        result = outlook_data.day_entries(doc, config) if doc else []
        meetings = [e for e in result if e["type"] == outlook_data.TYPE_MEETING]
    if config.get("teams_calls_enabled"):
        sessions = teams_calls.load_day(teams_file, date_str)
        result += teams_calls.call_entries(sessions, meetings,
                                           config.get("teams_min_seconds", teams_calls.MIN_SECONDS))
    return sorted(result, key=lambda e: e["start"])
