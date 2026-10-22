"""
VPN-Verbindungen aus Sophos Connect (und FortiClient) lesen.

Sophos Connect schreibt in seinen Programmordner:
- scvpn.log:  "<ID> VPN state changed to connected/disconnected" (Beginn/Ende).
              Die ID ist die Adresse aus der Verbindungsdatei, z. B. 203.0.113.30.
- scgui.log:  "Verbindung <Name> hergestellt" mit dem Namen, den man in Sophos
              Connect vergeben hat. Daraus kommt der Name zur ID.
- charon.log: strongSwan merkt jede Änderung an Netzwerkadaptern, auch an den
              Adaptern von FortiClient ("Fortinet ... changed state from Down to Up").

Die Logs werden bei Neustarts und neuen Verbindungen überschrieben. Darum hält
Zeitzeuge alles Gefundene in vpn_verbindungen.json fest.
"""

import json
import os
import re
from datetime import datetime, timedelta

TIME_FMT = "%Y-%m-%d %H:%M:%S"
TYPE = "VPN-Verbindung"
MIN_SECONDS = 10      # kürzere Verbindungen (Fehlversuche, Flackern) weglassen
NAME_MATCH_SECONDS = 30  # so weit dürfen scvpn.log und scgui.log auseinander liegen

DEFAULT_DIRS = [
    r"C:\Program Files (x86)\Sophos\Connect",
    r"C:\Program Files\Sophos\Connect",
]

# 2026-10-22 09:25:48AM [30768] dbg 203.0.113.30 VPN state changed to connected
_SCVPN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}:\d{2}[AP]M) \[\d+\] \w+ (.*)$")
# 2026-10-22 09:26:00AM [6800] inf Verbindung Kunde Müller hergestellt
_GUI_UP = re.compile(r"^Verbindung (.+) hergestellt$")
# 2026-10-20 08:25:27AM 18[KNL] interface 20 'Fortinet ...' changed state from Down to Up
_CHARON = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}:\d{2}[AP]M) \d+\[(\w+)\] (.*)$")
_ADAPTER = re.compile(r"^interface \d+ '(Fortinet[^']*)' (?:changed state from (Up|Down) to (Up|Down)|disappeared)$")


def _time(text):
    """'2026-10-22 01:16:18PM' -> datetime (ohne Locale, %p hängt sonst davon ab)."""
    date, clock = text.split(" ")
    h, m, s = clock[:-2].split(":")
    h = int(h) % 12 + (12 if clock.endswith("PM") else 0)
    return datetime.strptime(f"{date} {h:02d}:{m}:{s[:2]}", TIME_FMT)


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().splitlines()
    except OSError:
        return []


def _lines(folder, name):
    """Erst die ältere .old-Datei, dann die aktuelle."""
    return _read(os.path.join(folder, name + ".old")) + _read(os.path.join(folder, name))


def _conn(start, end, source, conn_id, name, details, running=False):
    return {
        "start": start.strftime(TIME_FMT),
        "end": end.strftime(TIME_FMT),
        "type": TYPE,
        "customer_name": name,
        "details": details,
        "vpn_source": source,
        "vpn_id": conn_id,
        "running": running,
        "is_suggestion": True,
    }


def parse_sophos(scvpn_lines, scgui_lines, names=None, now=None):
    """Sophos-Verbindungen. names (ID -> Name) wird um neu gelernte Namen ergänzt."""
    names = names if names is not None else {}
    now = now or datetime.now()

    gui_up = []  # (Zeit, Name)
    for line in scgui_lines:
        m = _SCVPN.match(line)
        if m:
            up = _GUI_UP.match(m.group(2).strip())
            if up and not up.group(1).endswith(" wird"):
                gui_up.append((_time(m.group(1)), up.group(1)))

    sessions, open_ = [], {}  # open_: ID -> Beginn

    def close(conn_id, end):
        start = open_.pop(conn_id)
        sessions.append((conn_id, start, end, False))

    for line in scvpn_lines:
        m = _SCVPN.match(line)
        if not m:
            continue
        t, msg = _time(m.group(1)), m.group(2).strip()
        state = re.match(r"^(.+) VPN state changed to (\w+)$", msg)
        if state:
            conn_id, new = state.groups()
            if new == "connected":
                open_.setdefault(conn_id, t)
            elif new in ("disconnecting", "disconnected") and conn_id in open_:
                close(conn_id, t)
        elif msg in ("System is going to sleep", "Sophos Connect stopped") or msg.startswith("Starting Sophos"):
            # Beim Aufwachen meldet Sophos das Trennen erst später: Ende = Schlafbeginn
            for conn_id in list(open_):
                close(conn_id, t)
    for conn_id, start in open_.items():
        sessions.append((conn_id, start, max(now, start), True))

    result = []
    for conn_id, start, end, running in sessions:
        for t, name in gui_up:
            if abs((t - start).total_seconds()) <= NAME_MATCH_SECONDS:
                if name != conn_id:
                    names[conn_id] = name
                break
        if (end - start).total_seconds() < MIN_SECONDS:
            continue
        name = names.get(conn_id, conn_id)
        details = f"Sophos Connect: {name}" + (f" ({conn_id})" if name != conn_id else "")
        result.append(_conn(start, end, "Sophos", conn_id, name, details, running))
    return result


def parse_fortinet(charon_lines, now=None):
    """FortiClient-Verbindungen aus den Adapter-Meldungen in charon.log."""
    now = now or datetime.now()
    result, open_ = [], {}  # Adapter -> Beginn

    def close(adapter, end, running=False):
        start = open_.pop(adapter)
        if (end - start).total_seconds() >= MIN_SECONDS:
            result.append(_conn(start, end, "FortiClient", adapter, "FortiClient",
                                f"FortiClient: {adapter}", running))

    for line in charon_lines:
        m = _CHARON.match(line)
        if not m:
            continue
        t, msg = _time(m.group(1)), m.group(3).strip()
        if m.group(2) == "DMN" and (msg.startswith("Starting IKE service") or msg.startswith("service is stopping")):
            for adapter in list(open_):
                close(adapter, t)
            continue
        a = _ADAPTER.match(msg)
        if not a:
            continue
        adapter, _old, new = a.groups()
        if new == "Up":
            open_.setdefault(adapter, t)
        elif adapter in open_:  # Down oder disappeared
            close(adapter, t)
    for adapter in list(open_):
        close(adapter, max(now, open_[adapter]), running=True)
    return result


class VpnReader:
    """Liest die Logs, merkt sich alles in archive_file und liefert alle Verbindungen."""

    def __init__(self, archive_file=None, dirs=None):
        self.archive_file = archive_file
        self.dirs = dirs or DEFAULT_DIRS
        self.files_read = None
        self._sig = None
        self._result = []

    def _load_archive(self):
        try:
            with open(self.archive_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("connections", []), data.get("names", {})
        except (OSError, ValueError, TypeError, AttributeError):
            return [], {}

    def _save_archive(self, connections, names):
        try:
            os.makedirs(os.path.dirname(self.archive_file), exist_ok=True)
            tmp = self.archive_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"connections": connections, "names": names}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.archive_file)
        except OSError as e:
            print(f"VPN-Verbindungen konnten nicht gespeichert werden: {e}")

    def connections(self):
        folders = [os.path.expandvars(d) for d in self.dirs if os.path.isdir(os.path.expandvars(d))]
        self.files_read = len(folders)
        files = [os.path.join(d, n + s) for d in folders
                 for n in ("scvpn.log", "scgui.log", "charon.log") for s in ("", ".old")]
        sig = tuple(os.path.getmtime(f) if os.path.exists(f) else 0 for f in files)
        running = any(c.get("running") for c in self._result)
        if sig == self._sig and not running:
            return self._result

        archived, names = self._load_archive() if self.archive_file else ([], {})
        found = []
        for d in folders:
            found += parse_sophos(_lines(d, "scvpn.log"), _lines(d, "scgui.log"), names)
            found += parse_fortinet(_lines(d, "charon.log"))

        def key(c):
            return (c.get("vpn_source"), c.get("vpn_id"), c.get("start"))

        merged = {key(c): c for c in archived}
        changed = False
        for c in found:
            if c["running"]:
                continue
            if merged.get(key(c)) != c:
                merged[key(c)] = c
                changed = True
        stored = sorted(merged.values(), key=lambda c: c["start"])
        # Neu gelernte Namen auch für ältere Einträge übernehmen
        for c in stored:
            if c.get("vpn_source") == "Sophos" and names.get(c.get("vpn_id")) not in (None, c["customer_name"]):
                c["customer_name"] = names[c["vpn_id"]]
                c["details"] = f"Sophos Connect: {c['customer_name']} ({c['vpn_id']})"
                changed = True
        if changed and self.archive_file:
            self._save_archive(stored, names)

        self._sig = sig
        self._result = [dict(c) for c in stored] + [c for c in found if c["running"]]
        return self._result
