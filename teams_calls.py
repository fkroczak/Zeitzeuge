"""
Teams-Anrufe erkennen (neues Teams und klassisches Teams), ohne Admin-Rechte.

Zwei Quellen, beide nur lesend:

1. Mikrofon-Nutzung (Hauptquelle). Windows merkt sich für die Anzeige "App verwendet
   dein Mikrofon" je App Beginn und Ende der letzten Nutzung:
     HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\
         ConsentStore\\microphone\\MSTeams_8wekyb3d8bbwe          (neues Teams)
         ConsentStore\\microphone\\NonPackaged\\C:#…#Teams.exe     (klassisches Teams)
     Werte LastUsedTimeStart / LastUsedTimeStop (FILETIME, UTC; Stop = 0: läuft noch).
   Zeitzeuge schaut alle 30 Sekunden nach und hält jede Nutzung fest. Ein Teams-Anruf
   oder eine Teams-Besprechung hält das Mikrofon offen, auch stummgeschaltet.
   Kurze Nutzungen (Gerätetest) fallen weg (teams_min_seconds).

2. Teams-Logs (Ergänzung, Format nicht dokumentiert). Neues Teams schreibt unter
   %LOCALAPPDATA%\\Packages\\MSTeams_8wekyb3d8bbwe\\LocalCache\\Microsoft\\MSTeams\\Logs\\
   MSTeams_*.log Zeilen mit "desktop_call_state_change_send" und "isOngoing: true/false".
   Daraus kommen Anrufe, die vor dem Start von Zeitzeuge lagen. Passt das Format nicht
   (mehr), findet der Parser einfach nichts.

Ablage "teams_anrufe" in der Datenbank, je Tag eine Liste
{"start", "end", "source": "mikrofon"|"log", "app", "running"}.

Rein funktional bis auf mic_readings (Registry) und den Dateizugriff in read_logs.
"""

import glob
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import datastore
import safe_io

TIME_FMT = "%Y-%m-%d %H:%M:%S"
STORE_NAME = "teams_anrufe"
TYPE = "Teams-Anruf"
MIN_SECONDS = 30          # kürzere Mikrofon-Nutzung (Gerätetest) zählt nicht als Anruf
MERGE_SECONDS = 60        # Abschnitte mit kürzerer Lücke werden ein Anruf
SAMPLE_SECONDS = 30
LOG_DAYS = 14             # Logdateien, die höchstens so alt sind, lesen
MAX_RUNNING = timedelta(hours=10)  # "läuft noch" seit länger: unplausibel, weglassen

MIC_KEY = (r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager"
           r"\ConsentStore\microphone")
LOG_GLOBS = [
    r"%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\Logs\MSTeams_*.log",
]


# ------------------------------------------------------------------ Mikrofon (Registry)

def filetime_to_local(value):
    """FILETIME (100 ns seit 1601, UTC) -> lokale Zeit ohne Zeitzone, 0/None -> None."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    try:
        utc = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=value // 10)
        return utc.astimezone().replace(tzinfo=None, microsecond=0)
    except (OverflowError, OSError, ValueError):
        return None


def is_teams_key(name):
    """Registry-Schlüssel einer Teams-App? (neues Teams: MSTeams_…, klassisch: …#Teams.exe)"""
    low = name.lower()
    return low.startswith("msteams_") or low.endswith("#teams.exe") or low.endswith("#ms-teams.exe")


def app_label(name):
    return "Teams (klassisch)" if name.lower().endswith("#teams.exe") else "Teams"


def mic_readings():
    """[(Schlüsselname, Beginn, Ende oder None)] der Teams-Apps. Außer Windows: []."""
    if sys.platform != "win32":
        return []
    import winreg
    result = []

    def scan(path):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            return
        with key:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                if sub == "NonPackaged":
                    continue
                if not is_teams_key(sub):
                    continue
                try:
                    with winreg.OpenKey(key, sub) as k:
                        start = winreg.QueryValueEx(k, "LastUsedTimeStart")[0]
                        stop = winreg.QueryValueEx(k, "LastUsedTimeStop")[0]
                except OSError:
                    continue
                result.append((sub, start, stop))

    scan(MIC_KEY)
    scan(MIC_KEY + r"\NonPackaged")
    return [(name, filetime_to_local(a), filetime_to_local(b)) for name, a, b in result]


def sessions_from_readings(readings, now):
    """Registry-Werte -> Nutzungen [{start, end, app, running, source}].
    Beginn fehlt: weglassen. Ende fehlt oder liegt vor dem Beginn: läuft noch (bis jetzt)."""
    result = []
    for name, start, stop in readings:
        if start is None or start > now + timedelta(minutes=5):
            continue
        running = stop is None or stop < start
        if running and now - start > MAX_RUNNING:
            continue  # Ende nie gemeldet (z. B. Absturz): kein Anruf über Stunden
        end = now if running else stop
        result.append({"start": start.strftime(TIME_FMT), "end": max(end, start).strftime(TIME_FMT),
                       "app": app_label(name), "running": running, "source": "mikrofon"})
    return result


# ------------------------------------------------------------------ Teams-Logs

# 2026-10-26T09:15:02.123456+01:00 0x00001234 <INFO> … desktop_call_state_change_send … isOngoing: true
_LOG_TIME = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:[.,]\d+)?\s*(Z|[+-]\d{2}:?\d{2})?")
_CALL_STATE = re.compile(r"desktop_call_state_change_send.*?\bisOngoing\b\W{0,4}(true|false)", re.I)


def _log_time(match):
    t = datetime.strptime(f"{match.group(1)} {match.group(2)}", TIME_FMT)
    zone = match.group(3)
    if not zone:
        return t  # ohne Zeitzone: schon lokale Zeit
    if zone == "Z":
        tz = timezone.utc
    else:
        sign = -1 if zone[0] == "-" else 1
        hh, mm = int(zone[1:3]), int(zone[-2:])
        tz = timezone(sign * timedelta(hours=hh, minutes=mm))
    return t.replace(tzinfo=tz).astimezone().replace(tzinfo=None)


def parse_log(lines, now=None):
    """Zeilen eines Teams-Logs -> Anrufe [{start, end, running, source: "log"}]."""
    now = now or datetime.now()
    result, start = [], None
    for line in lines:
        m = _CALL_STATE.search(line)
        if not m:
            continue
        t = _LOG_TIME.match(line)
        if not t:
            continue
        try:
            when = _log_time(t)
        except (ValueError, OverflowError):
            continue
        if m.group(1).lower() == "true":
            start = start or when
        elif start is not None:
            if when >= start:
                result.append({"start": start.strftime(TIME_FMT), "end": when.strftime(TIME_FMT),
                               "app": "Teams", "running": False, "source": "log"})
            start = None
    if start is not None and now - start <= MAX_RUNNING:
        result.append({"start": start.strftime(TIME_FMT), "end": max(now, start).strftime(TIME_FMT),
                       "app": "Teams", "running": True, "source": "log"})
    return result


def log_files(globs=None, days=LOG_DAYS, now=None):
    """Teams-Logdateien der letzten Tage (älteste zuerst)."""
    now = now or datetime.now()
    limit = (now - timedelta(days=days)).timestamp()
    files = []
    for pattern in globs or LOG_GLOBS:
        for path in glob.glob(os.path.expandvars(pattern)):
            try:
                if os.path.getmtime(path) >= limit:
                    files.append(path)
            except OSError:
                continue
    return sorted(files, key=lambda p: (os.path.getmtime(p), p))


def read_logs(files, now=None):
    """Anrufe aus allen Logdateien (ein Anruf kann über zwei Dateien gehen: alles am Stück)."""
    lines = []
    for path in files:
        try:
            lines.extend(safe_io.log_lines(path))
        except OSError:
            continue
    return parse_log(lines, now)


# ------------------------------------------------------------------ Zusammenführen

def _t(text):
    return datetime.strptime(text, TIME_FMT)


def merge_sessions(sessions, gap_seconds=MERGE_SECONDS):
    """Überlappende oder fast anschließende Abschnitte (beide Quellen) zu Anrufen verbinden."""
    out = []
    for s in sorted(sessions, key=lambda s: s["start"]):
        if out and (_t(s["start"]) - _t(out[-1]["end"])).total_seconds() <= gap_seconds:
            last = out[-1]
            last["end"] = max(last["end"], s["end"])
            last["running"] = last.get("running") or s.get("running")
            last["sources"] = sorted(set(last["sources"]) | {s.get("source", "")})
        else:
            out.append({"start": s["start"], "end": s["end"], "app": s.get("app", "Teams"),
                        "running": bool(s.get("running")), "sources": [s.get("source", "")]})
    return out


def _overlap(a_start, a_end, b_start, b_end):
    return max(0.0, (min(a_end, b_end) - max(a_start, b_start)).total_seconds())


def call_entries(sessions, meetings=(), min_seconds=MIN_SECONDS):
    """Anrufe eines Tages -> Timeline-Einträge (Zeile "Tel" wie 3CX).

    meetings: Teams-Besprechungen aus Outlook. Liegt ein Anruf zur Hälfte in einer, trägt
    er deren Betreff und Teilnehmer-Domains."""
    result = []
    for c in merge_sessions(sessions):
        start, end = _t(c["start"]), _t(c["end"])
        seconds = int((end - start).total_seconds())
        if seconds < min_seconds and not c["running"]:
            continue
        meeting = None
        for m in meetings:
            try:
                ms, me = _t(m["start"]), _t(m["end"])
            except (KeyError, ValueError):
                continue
            if _overlap(start, end, ms, me) >= max(1, seconds) * 0.5:
                meeting = m
                break
        sources = " und ".join(label for key, label in (("mikrofon", "Mikrofon"), ("log", "Teams-Log"))
                               if key in c["sources"])
        details = [f"Dauer {seconds // 60}:{seconds % 60:02d}"]
        if c["running"]:
            details[0] = "läuft noch"
        if meeting:
            details.append(f"in Besprechung „{meeting.get('customer_name', '')}“")
        if sources:
            details.append(f"erkannt über {sources}")
        result.append({
            "start": c["start"],
            "end": (start + timedelta(seconds=max(seconds, 60))).strftime(TIME_FMT),
            "type": TYPE,
            "direction": "Anruf",  # Zeile "Tel"; Richtung kennt Teams hier nicht
            "duration_s": seconds,
            "customer_name": (meeting or {}).get("customer_name", ""),
            "details": ", ".join(details),
            "email_domains": list((meeting or {}).get("email_domains") or []),
            "running": bool(c["running"]),
            "teams_meeting": bool(meeting),
            "is_suggestion": True,
        })
    return result


# ------------------------------------------------------------------ Ablage

def _store(path):
    return datastore.locate(path, "days")


def _key(s):
    return (s.get("source"), s.get("app"), s.get("start"))


def store_sessions(path, sessions):
    """Neue oder geänderte Abschnitte übernehmen (je Tag des Beginns). -> geänderte Tage."""
    by_day = {}
    for s in sessions:
        by_day.setdefault(s["start"][:10], []).append(s)
    if not by_day:
        return []
    try:
        store, name = _store(path)
        changed = {}
        for day, items in by_day.items():
            old = store.get(name, day) or []
            merged = {_key(s): s for s in old if isinstance(s, dict) and "start" in s and "end" in s}
            dirty = False
            for s in items:
                k = _key(s)
                prev = merged.get(k)
                if prev is not None and not prev.get("running") and s.get("running"):
                    continue  # abgeschlossen bleibt abgeschlossen
                if prev != s:
                    merged[k] = dict(s)
                    dirty = True
            if dirty:
                changed[day] = sorted(merged.values(), key=lambda s: s["start"])
        if changed:
            store.put_many(name, changed)
        return list(changed)
    except (datastore.Busy, datastore.Locked) as e:
        safe_io.report(f"Teams-Anrufe: Speichern fehlgeschlagen ({e})")
        return []


def finish_stale(path, source, current, days):
    """Als laufend gespeicherte Abschnitte einer Quelle, die gerade nicht mehr laufen
    (z. B. Zeitzeuge war während des Anrufs aus), enden beim letzten Blick. -> geänderte Tage"""
    keep = {_key(s) for s in current if s.get("running")}
    try:
        store, name = _store(path)
        changed = {}
        for day in days:
            items = store.get(name, day) or []
            dirty = False
            for s in items:
                if (isinstance(s, dict) and s.get("running") and s.get("source") == source
                        and _key(s) not in keep):
                    s["running"] = False
                    dirty = True
            if dirty:
                changed[day] = items
        if changed:
            store.put_many(name, changed)
        return list(changed)
    except (datastore.Busy, datastore.Locked) as e:
        safe_io.report(f"Teams-Anrufe: Speichern fehlgeschlagen ({e})")
        return []


def load_day(path, day):
    try:
        store, name = _store(path)
        data = store.get(name, day) or []
    except (datastore.Busy, datastore.Locked):
        return []
    return [s for s in data if isinstance(s, dict) and _valid(s)]


def _valid(s):
    try:
        return _t(s["start"]) <= _t(s["end"])
    except (KeyError, TypeError, ValueError):
        return False


class TeamsCallTracker:
    """Mikrofon alle 30 Sekunden prüfen, Logs bei Änderung lesen, alles in die Ablage."""

    def __init__(self, archive_file, mic_func=None, log_globs=None, use_logs=True):
        self.archive_file = archive_file
        self.mic_func = mic_func or mic_readings
        self.log_globs = log_globs
        self.use_logs = use_logs
        self._log_sig = None

    def sample(self, now=None):
        """Einmal prüfen und speichern. -> geänderte Tage."""
        now = now or datetime.now()
        try:
            readings = self.mic_func()
        except Exception as e:
            safe_io.log(f"Teams: Mikrofon-Nutzung nicht lesbar: {e!r}")
            readings = []
        sessions = sessions_from_readings(readings, now)
        changed = store_sessions(self.archive_file, sessions)
        days = [(now - timedelta(days=1)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")]
        changed += finish_stale(self.archive_file, "mikrofon", sessions, days)
        if self.use_logs:
            changed += self.update_logs(now)
        return sorted(set(changed))

    def update_logs(self, now=None):
        files = log_files(self.log_globs, now=now)
        sig = tuple((f, os.path.getsize(f), os.path.getmtime(f)) for f in files if os.path.exists(f))
        if sig == self._log_sig:
            return []
        self._log_sig = sig
        sessions = read_logs(files, now)
        days = [(now - timedelta(days=1)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")]
        return (store_sessions(self.archive_file, sessions)
                + finish_stale(self.archive_file, "log", sessions, days))
