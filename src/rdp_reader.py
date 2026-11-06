"""
Remotedesktop-Sitzungen: RDM Better (launcher.log) und mstsc selbst aufgezeichnet.

RDM Better schreibt nur den Start einer Sitzung in launcher.log (Zeit in UTC):
  2026-11-03T10:11:53.181Z [INFO] launch host=10.10.80.35:3389 user=Administrator type=1 ...
Das Ende kennt nur Windows. Darum prüft Zeitzeuge alle 30 Sekunden, welche
mstsc.exe laufen (Remotedesktopverbindung), und hält Beginn und Ende in der
Datenbank fest. Ein Start aus RDM Better bekommt so sein Ende von der passenden
mstsc-Sitzung. Ohne passende Sitzung steht er 1 Minute in der Timeline.

Zusätzlich liest Zeitzeuge das Windows-Ereignisprotokoll des RDP-Clients
(Microsoft-Windows-TerminalServices-RDPClient/Operational): Verbindungsaufbau (1024)
und Trennung (1026) je Sitzung. Das füllt Zeiten, in denen Zeitzeuge nicht lief,
und macht Beginn und Ende sekundengenau.
"""

import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import datastore
import retention
import safe_io
import timefmt

TIME_FMT = "%Y-%m-%d %H:%M:%S"
TYPE = "RDP-Verbindung"
SAMPLE_SECONDS = 30
MIN_SECONDS = 20        # kürzere mstsc-Fenster (Fehlversuch, gleich geschlossen) weglassen
MATCH_SECONDS = 120     # so lange darf mstsc nach dem Start aus RDM Better brauchen
DEFAULT_LAUNCHER_LOG = r"%LOCALAPPDATA%\RDM Better\launcher.log"

_LAUNCH = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?\s+"
                     r"\[\w+\]\s+launch\b(.*)$")
_FIELD = re.compile(r"(\w+)=(\S+)")
# Fenstertitel von mstsc: "DC01 - Remotedesktopverbindung" / "DC01 - Remote Desktop Connection"
_TITLE = re.compile(r"^(.+?)\s+-\s+(Remotedesktopverbindung|Remote Desktop Connection)$", re.I)


def short_host(host):
    """'10.10.80.35:3389' -> '10.10.80.35' (Standardport weg, anderer Port bleibt)."""
    host = (host or "").strip()
    return host[:-5] if host.endswith(":3389") else host


# ------------------------------------------------------------------ RDM Better

def _local(stamp, zone):
    """Zeit aus dem Log in Ortszeit (ohne Zeitzone, wie überall in Zeitzeuge)."""
    when = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S")
    if not zone:
        return when  # ohne Angabe: schon Ortszeit
    if zone == "Z":
        when = when.replace(tzinfo=timezone.utc)
    else:
        sign = 1 if zone[0] == "+" else -1
        hours, minutes = int(zone[1:3]), int(zone[-2:])
        when = when.replace(tzinfo=timezone(sign * timedelta(hours=hours, minutes=minutes)))
    return when.astimezone().replace(tzinfo=None)


def parse_launcher(lines):
    """Starts aus launcher.log: [{"time", "host", "user", "type"}]. Andere Zeilen zählen nicht."""
    result = []
    for line in lines:
        m = _LAUNCH.match(line.strip())
        if not m:
            continue
        try:
            when = _local(m.group(1), m.group(2))
        except (ValueError, OverflowError):
            continue
        fields = dict(_FIELD.findall(m.group(3)))
        if not fields.get("host"):
            continue
        result.append({"time": when, "host": short_host(fields["host"]),
                       "user": fields.get("user", ""), "type": fields.get("type", "")})
    return result


class LauncherLog:
    """launcher.log lesen, nur neu wenn sich die Datei geändert hat."""

    def __init__(self, config):
        self.config = config
        self._cache = {}
        self.files_read = None

    def paths(self):
        return self.config.get("rdmbetter_paths") or [DEFAULT_LAUNCHER_LOG]

    def launches(self):
        result = []
        self.files_read = 0
        for p in self.paths():
            path = os.path.expandvars(p)
            if not os.path.isfile(path):
                continue
            try:
                mtime = os.path.getmtime(path)
                if self._cache.get(path, (None,))[0] != mtime:
                    self._cache[path] = (mtime, parse_launcher(safe_io.log_lines(path)))
                result += self._cache[path][1]
                self.files_read += 1
            except OSError as e:
                print(f"Fehler beim Lesen von {path}: {e}")
        return result


# ------------------------------------------------------------------ mstsc

def _rdp_file_host(path):
    """'full address:s:host' aus einer .rdp-Datei (kann UTF-16 sein)."""
    try:
        for line in safe_io.log_lines(path):
            line = line.strip().lstrip("﻿")
            if line.lower().startswith("full address:s:"):
                return short_host(line.split(":", 2)[2])
    except OSError:
        pass
    return ""


def host_from_cmdline(args, file_name=True):
    """Ziel aus der Befehlszeile von mstsc: /v:host oder eine .rdp-Datei.

    file_name: ist die .rdp-Datei nicht lesbar, ihr Name (RDM Better nutzt temporäre Dateien,
    dort ist der Fenstertitel besser)."""
    for i, arg in enumerate(args[1:], 1):
        low = arg.lower()
        if low.startswith(("/v:", "-v:")):
            return short_host(arg[3:])
        if low in ("/v", "-v") and i + 1 < len(args):
            return short_host(args[i + 1])
    for arg in args[1:]:
        if arg.lower().endswith(".rdp"):
            host = _rdp_file_host(arg)
            if host:
                return host
            if file_name:
                return os.path.splitext(os.path.basename(arg.replace("\\", "/")))[0]
    return ""


def host_from_title(title):
    m = _TITLE.match((title or "").strip())
    return m.group(1).strip() if m else ""


def mstsc_processes():
    """Laufende mstsc.exe: [(pid, Startzeit, Befehlszeile)]."""
    try:
        import psutil
    except ImportError:
        return []
    result = []
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            if (proc.info.get("name") or "").lower() != "mstsc.exe":
                continue
            try:
                args = proc.cmdline()
            except Exception:
                args = []
            result.append((proc.info["pid"], proc.info.get("create_time") or 0, args))
        except Exception:
            continue
    return result


def window_titles():
    """pid -> Titel der sichtbaren Fenster (nur Windows)."""
    if sys.platform != "win32":
        return {}
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    titles = {}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                titles.setdefault(pid.value, []).append(buf.value)
        return True

    try:
        user32.EnumWindows(each, 0)
    except Exception:
        return {}
    return titles


# ------------------------------------------------------------------ Ereignisprotokoll

RDP_EVENT_LOG = "Microsoft-Windows-TerminalServices-RDPClient/Operational"
RDP_EVENT_QUERY = "*[System[(EventID=1024 or EventID=1026 or EventID=1027 or EventID=1102)]]"
EVENT_CACHE_SECONDS = 60
_NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"


def read_rdp_events():
    """XML-Text der RDP-Client-Ereignisse, neueste zuerst (nur Windows, sonst "")."""
    if sys.platform != "win32":
        return ""
    try:
        out = subprocess.run(["wevtutil", "qe", RDP_EVENT_LOG, f"/q:{RDP_EVENT_QUERY}", "/f:xml",
                              "/c:5000", "/rd:true"], capture_output=True, timeout=20,
                             creationflags=0x08000000).stdout  # CREATE_NO_WINDOW
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.decode("utf-8", errors="replace")


def _event_time(text):
    """SystemTime (UTC) -> Ortszeit ohne Zeitzone."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", text or "")
    if not m:
        return None
    when = datetime.strptime(f"{m.group(1)} {m.group(2)}", TIME_FMT).replace(tzinfo=timezone.utc)
    return when.astimezone().replace(tzinfo=None)


def parse_rdp_events(xml_text):
    """Ereignisse des RDP-Clients -> [{"start", "end" (None = keine Trennung), "host"}].

    1024 „versucht, eine Verbindung herzustellen (Ziel)“ beginnt eine Sitzung, 1026 „getrennt“
    beendet sie. Zusammengehörige Ereignisse tragen dieselbe ActivityID, sonst dieselbe Prozess-ID.
    1102 liefert die IP, falls 1024 kein Ziel hat.
    """
    try:
        root = ET.fromstring(f"<Events>{xml_text}</Events>")
    except ET.ParseError:
        return []
    events = []
    for event in root.iter(f"{_NS}Event"):
        system = event.find(f"{_NS}System")
        if system is None:
            continue
        try:
            number = int(system.findtext(f"{_NS}EventID", ""))
        except ValueError:
            continue
        created = system.find(f"{_NS}TimeCreated")
        when = _event_time(created.get("SystemTime", "") if created is not None else "")
        if when is None:
            continue
        corr = system.find(f"{_NS}Correlation")
        execution = system.find(f"{_NS}Execution")
        activity = corr.get("ActivityID", "") if corr is not None else ""
        pid = execution.get("ProcessID", "") if execution is not None else ""
        data = event.find(f"{_NS}EventData")
        value = ""
        if data is not None:
            items = list(data)
            named = [d for d in items if d.get("Name") == "Value"]
            value = ((named or items)[0].text or "").strip() if (named or items) else ""
        events.append((when, number, activity, pid, value))
    events.sort(key=lambda e: e[0])

    sessions, open_ = [], {}  # Schlüssel (ActivityID oder pid) -> Sitzung
    for when, number, activity, pid, value in events:
        key = activity or f"pid:{pid}"
        if number == 1024:
            if key not in open_:
                s = {"start": when, "end": None, "host": short_host(value), "pid": pid}
                open_[key] = s
                sessions.append(s)
            continue
        s = open_.get(key) or next((o for o in reversed(list(open_.values())) if pid and o["pid"] == pid),
                                   None)
        if s is None:
            continue
        if number == 1102 and not s["host"]:
            s["host"] = short_host(value)
        elif number == 1026:
            s["end"] = when
            open_ = {k: o for k, o in open_.items() if o is not s}
    for s in sessions:
        s.pop("pid", None)
    return sessions


def _t(text):
    return timefmt.parse(text)  # wie strptime, aber schnell (Archiv mit Tausenden Einträgen)


class RdpReader:
    """
    Hält mstsc-Sitzungen in archive_file fest ("sessions") und verbindet sie für
    die Timeline mit den Starts aus RDM Better.
    """

    def __init__(self, config=None, archive_file=None, proc_func=None, title_func=None, event_func=None):
        self.config = config if config is not None else {}
        self.archive_file = archive_file
        self.proc_func = proc_func or mstsc_processes
        self.title_func = title_func or window_titles
        self.event_func = event_func or read_rdp_events
        self._events = None       # (Zeitpunkt des Lesens, Sitzungen aus dem Ereignisprotokoll)
        self.launcher = LauncherLog(self.config)
        self._data = None
        self._last_sample = None

    # ------------------------------------------------------------ Archiv

    def _archive(self):
        if self._data is None:
            data, locked = {}, False
            if self.archive_file:
                try:
                    store, name = datastore.locate(self.archive_file, "single")
                    data = store.get(name, "", {})
                except (datastore.Busy, datastore.Locked):
                    locked = True
            sessions = data.get("sessions") if isinstance(data, dict) else None
            sessions = [s for s in sessions or [] if isinstance(s, dict) and self._valid(s)]
            if locked:
                return {"sessions": sessions}
            self._data = {"sessions": sessions}
        return self._data

    def prune(self, before):
        """Einträge, die vor before enden, aus dem Archiv löschen (Spuren-Verlauf begrenzen)."""
        self._archive()
        if self._data is None:  # gerade gesperrt: beim nächsten Lauf
            return 0
        removed = retention.prune_entries(self._data, before)
        if removed:
            self._save()
        return removed

    @staticmethod
    def _valid(s):
        try:
            _t(s["start"]), _t(s["end"])
            return True
        except (KeyError, TypeError, ValueError):
            return False

    def _save(self):
        if not self.archive_file or self._data is None:
            return
        try:
            store, name = datastore.locate(self.archive_file, "single")
            store.put(name, "", self._data)
        except (datastore.Busy, datastore.Locked) as e:
            safe_io.report(f"Remotedesktop-Sitzungen: Speichern fehlgeschlagen ({e})")

    # ------------------------------------------------------------ Aufzeichnung

    def sample(self, now=None):
        """Laufende mstsc prüfen und sofort speichern. True, wenn sich etwas geändert hat."""
        now = now or datetime.now()
        try:
            procs = self.proc_func()
        except Exception as e:
            print(f"mstsc-Prozesse nicht lesbar: {e}")
            return False
        titles = {}
        if procs:
            try:
                titles = self.title_func()
            except Exception:
                titles = {}
        gap = (self._last_sample is None
               or (now - self._last_sample).total_seconds() > 3 * SAMPLE_SECONDS)
        self._last_sample = now
        stamp = now.strftime(TIME_FMT)
        live = {}
        for pid, created, args in procs:
            key = f"{pid}-{int(created)}"
            title_host = next((h for h in map(host_from_title, titles.get(pid, [])) if h), "")
            host = host_from_cmdline(args, file_name=False) or title_host or host_from_cmdline(args)
            live[key] = (created, host, title_host)

        sessions = self._archive()["sessions"]
        changed = False
        still_open = set()
        for s in sessions:
            if not s.get("running"):
                continue
            if gap or s.get("id") not in live:
                s["running"] = False
            else:
                s["end"] = stamp
                created, host, title_host = live[s["id"]]
                if not s.get("host") and host:
                    s["host"] = host
                still_open.add(s["id"])
            changed = True
        for key, (created, host, _title) in live.items():
            if key in still_open:
                continue
            # Startzeit des Prozesses, wenn er erst seit dem letzten Blick läuft
            try:
                start = datetime.fromtimestamp(created) if created else now
            except (OverflowError, OSError, ValueError):
                start = now
            if gap or start > now or (now - start).total_seconds() > 2 * SAMPLE_SECONDS:
                start = now  # lief schon vorher (Zeitzeuge war aus): nicht raten
            sessions.append({"id": key, "host": host, "start": start.strftime(TIME_FMT),
                             "end": stamp, "running": True})
            changed = True
        if changed:
            self._save()
        return changed

    # ------------------------------------------------------------ Ereignisprotokoll

    def event_sessions(self):
        """Sitzungen aus dem Ereignisprotokoll (höchstens einmal pro Minute gelesen)."""
        if not self.config.get("mstsc_events_enabled", True):
            return []
        if self._events is None or time.monotonic() - self._events[0] > EVENT_CACHE_SECONDS:
            try:
                found = parse_rdp_events(self.event_func() or "")
            except Exception as e:  # Ereignisprotokoll darf die Timeline nie leeren
                print(f"RDP-Ereignisprotokoll nicht lesbar: {e}")
                found = []
            self._events = (time.monotonic(), found)
        return self._events[1]

    def _merge_events(self, sessions):
        """Sitzungen aus dem Ereignisprotokoll mit den aufgezeichneten zusammenführen.

        Überlappt eine aufgezeichnete Sitzung (gleiches oder unbekanntes Ziel), bekommt sie die
        genaueren Zeiten aus dem Protokoll; sonst kommt die Sitzung neu dazu. Ohne Trennung im
        Protokoll und ohne Aufzeichnung ist das Ende unbekannt: 1 Minute, wie bei RDM Better.
        """
        for e in self.event_sessions():
            start, end = e["start"], e["end"]
            if end is not None and (end - start).total_seconds() < MIN_SECONDS:
                continue  # Fehlversuch
            probe_end = end or start + timedelta(seconds=MATCH_SECONDS)
            match = next((s for s in sessions if s["start"] < probe_end and start < s["end"]
                          and (not s["host"] or not e["host"] or s["host"].lower() == e["host"].lower())),
                         None)
            if match:
                match["start"] = min(match["start"], start)
                if end is not None and not match.get("running"):
                    match["end"] = max(match["end"], end)
                match["host"] = match["host"] or e["host"]
                match["events"] = True
            else:
                sessions.append({"start": start, "end": end or start + timedelta(minutes=1),
                                 "host": e["host"], "launch": None, "events": True,
                                 "open_end": end is None})
        sessions.sort(key=lambda s: s["start"])

    # ------------------------------------------------------------ Anzeige

    def connections(self):
        """mstsc-Sitzungen und Starts aus RDM Better für die Timeline."""
        use_mstsc = self.config.get("mstsc_enabled", True)
        use_launcher = self.config.get("rdmbetter_enabled", True)
        sessions = []
        if use_mstsc or use_launcher:  # RDM Better braucht die Sitzungen für das Ende
            for s in self._archive()["sessions"]:
                start, end = _t(s["start"]), _t(s["end"])
                if not s.get("running") and (end - start).total_seconds() < MIN_SECONDS:
                    continue
                sessions.append({"start": start, "end": end, "host": s.get("host") or "", "launch": None,
                                 "running": bool(s.get("running"))})
            self._merge_events(sessions)
        sessions.sort(key=lambda s: s["start"])

        launches = sorted(self.launcher.launches(), key=lambda l: l["time"]) if use_launcher else []
        extra = []
        for launch in launches:
            match = None
            for s in sessions:
                if s["launch"] is not None:
                    continue
                delta = (s["start"] - launch["time"]).total_seconds()
                if -SAMPLE_SECONDS <= delta <= MATCH_SECONDS and (
                        not s["host"] or s["host"].lower() == launch["host"].lower()):
                    match = s
                    break
            if match:
                match["launch"] = launch
                match["host"] = match["host"] or launch["host"]
            else:
                extra.append(launch)

        result = []
        for s in sessions:
            launch = s["launch"]
            if launch is None and not use_mstsc:
                continue
            name = s["host"] or "Remotedesktop"
            if launch:
                details = f"RDP-Verbindung {name} über RDM Better"
                if launch["user"]:
                    details += f" (Benutzer {launch['user']})"
            elif s.get("open_end"):
                details = f"RDP-Verbindung {name} (mstsc, Windows-Ereignisprotokoll, Ende unbekannt)"
            elif s.get("events"):
                details = f"RDP-Verbindung {name} (mstsc, Windows-Ereignisprotokoll)"
            else:
                details = f"RDP-Verbindung {name} (mstsc, von Zeitzeuge aufgezeichnet)"
            result.append(self._conn(s["start"], s["end"], name, details,
                                     "RDM Better" if launch else "mstsc"))
        for launch in extra:
            details = f"RDP-Verbindung {launch['host']} über RDM Better, Ende unbekannt"
            if launch["user"]:
                details += f" (Benutzer {launch['user']})"
            result.append(self._conn(launch["time"], launch["time"] + timedelta(minutes=1),
                                     launch["host"], details, "RDM Better"))
        return sorted(result, key=lambda c: c["start"])

    @staticmethod
    def _conn(start, end, name, details, source):
        return {"start": start.strftime(TIME_FMT), "end": end.strftime(TIME_FMT), "type": TYPE,
                "customer_name": name, "details": details, "rdp_source": source,
                "is_suggestion": True}
