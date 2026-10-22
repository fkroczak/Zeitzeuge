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
Zeitzeuge alles in vpn_verbindungen.json fest und zeichnet zusätzlich selbst auf:
Alle 30 Sekunden prüft es, ob ein VPN-Adapter (Sophos, Fortinet, ...) verbunden
ist. So bleiben die Zeiten erhalten, auch wenn die Logs fehlen oder gelöscht sind.
"""

import json
import os
import re
import sys
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


def adapters_up():
    """Beschreibungen und Namen aller verbundenen Netzwerkadapter."""
    if sys.platform == "win32":
        return _adapters_up_windows()
    try:
        import psutil
        return [name for name, st in psutil.net_if_stats().items() if st.isup]
    except Exception:
        return []


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _IpAdapterAddresses(ctypes.Structure):
        pass

    _IpAdapterAddresses._fields_ = [
        ("Length", wintypes.ULONG), ("IfIndex", wintypes.DWORD),
        ("Next", ctypes.POINTER(_IpAdapterAddresses)), ("AdapterName", ctypes.c_char_p),
        ("FirstUnicastAddress", ctypes.c_void_p), ("FirstAnycastAddress", ctypes.c_void_p),
        ("FirstMulticastAddress", ctypes.c_void_p), ("FirstDnsServerAddress", ctypes.c_void_p),
        ("DnsSuffix", ctypes.c_wchar_p), ("Description", ctypes.c_wchar_p),
        ("FriendlyName", ctypes.c_wchar_p), ("PhysicalAddress", ctypes.c_ubyte * 8),
        ("PhysicalAddressLength", wintypes.ULONG), ("Flags", wintypes.ULONG),
        ("Mtu", wintypes.ULONG), ("IfType", wintypes.ULONG), ("OperStatus", ctypes.c_int),
    ]

    def _adapters_up_windows():
        # Ohne Adressen/DNS abfragen: schnell genug für alle 30 Sekunden
        flags = 0x0001 | 0x0002 | 0x0004 | 0x0008  # ohne Unicast, Anycast, Multicast, DNS
        size = wintypes.ULONG(16384)
        for _ in range(3):
            buf = ctypes.create_string_buffer(size.value)
            ret = ctypes.windll.iphlpapi.GetAdaptersAddresses(0, flags, None, buf, ctypes.byref(size))
            if ret != 111:  # ERROR_BUFFER_OVERFLOW: mit größerem Puffer noch einmal
                break
        if ret != 0:
            return []
        result = []
        node = ctypes.cast(buf, ctypes.POINTER(_IpAdapterAddresses))
        while node:
            a = node.contents
            if a.OperStatus == 1:  # IfOperStatusUp
                result.append(f"{a.Description or ''} ({a.FriendlyName or ''})")
            node = a.Next
        return result


# Teil der Adapterbeschreibung -> Quelle (wie in den Logs, damit doppelte wegfallen)
DEFAULT_ADAPTERS = {"Sophos": "Sophos", "Fortinet": "FortiClient"}
LABELS = {"Sophos": "Sophos Connect"}
SAMPLE_SECONDS = 30


def vpn_sources(config):
    """Eingeschaltete VPN-Quellen laut Einstellungen (Menü "Datenquellen")."""
    return {source for source, key in (("Sophos", "sophos_enabled"), ("FortiClient", "forti_enabled"))
            if config.get(key, True)}


def _overlaps(a, b):
    return a["start"] < b["end"] and b["start"] < a["end"]


class VpnReader:
    """
    Hält alle VPN-Verbindungen in archive_file fest:
    - "connections": aus den Logs (mit Namen),
    - "adapter":     selbst aufgezeichnet (sample() alle 30 Sekunden),
    - "names":       Sophos-ID -> Verbindungsname.
    """

    def __init__(self, archive_file=None, dirs=None, adapters=None, adapter_func=None):
        self.archive_file = archive_file
        self.dirs = dirs or DEFAULT_DIRS
        self.adapters = adapters or DEFAULT_ADAPTERS
        self.adapter_func = adapter_func or adapters_up
        self.sources = None  # eingeschaltete Quellen ("Sophos", "FortiClient"); None = alle
        self.files_read = None
        self._sig = None
        self._data = None
        self._running_logs = []
        self._last_sample = None

    # ------------------------------------------------------------ Archiv

    def _archive(self):
        if self._data is None:
            data = {}
            if self.archive_file:
                try:
                    with open(self.archive_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except (OSError, ValueError):
                    data = {}
            if not isinstance(data, dict):
                data = {}
            self._data = {k: data.get(k, default) for k, default in
                          (("connections", []), ("adapter", []), ("names", {}))}
        return self._data

    def _save(self):
        if not self.archive_file:
            return
        try:
            os.makedirs(os.path.dirname(self.archive_file) or ".", exist_ok=True)
            tmp = self.archive_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.archive_file)
        except OSError as e:
            print(f"VPN-Verbindungen konnten nicht gespeichert werden: {e}")

    # ------------------------------------------------------------ eigene Aufzeichnung

    def sample(self, now=None):
        """Verbundene VPN-Adapter prüfen und sofort speichern. Gibt True zurück, wenn sich etwas geändert hat."""
        now = now or datetime.now()
        try:
            up_list = self.adapter_func()
        except Exception as e:
            print(f"Netzwerkadapter konnten nicht gelesen werden: {e}")
            return False
        up = {}
        for desc in up_list:
            for part, source in self.adapters.items():
                if self.sources is not None and source not in self.sources:
                    continue
                if part.lower() in desc.lower():
                    up[desc] = source
                    break

        # Lange Lücke (Ruhezustand, Zeitzeuge war aus): offene Einträge enden beim letzten Blick
        gap = (self._last_sample is None
               or (now - self._last_sample).total_seconds() > 3 * SAMPLE_SECONDS)
        self._last_sample = now
        live = self._archive()["adapter"]
        stamp = now.strftime(TIME_FMT)
        changed = False
        still_open = set()
        for c in live:
            if not c.get("running"):
                continue
            if gap or c["vpn_id"] not in up:
                c["running"] = False
            else:
                c["end"] = stamp
                still_open.add(c["vpn_id"])
            changed = True
        for desc, source in up.items():
            if desc not in still_open:
                name = LABELS.get(source, source)
                live.append(_conn(now, now, source, desc, name,
                                  f"{name}: Adapter {desc} (von Zeitzeuge aufgezeichnet)", True))
                changed = True
        if changed:
            self._save()
        return changed

    # ------------------------------------------------------------ Logs

    def update_from_logs(self):
        """Sophos-/charon-Logs lesen und Neues ins Archiv übernehmen (nur wenn sich Dateien geändert haben)."""
        folders = [os.path.expandvars(d) for d in self.dirs if os.path.isdir(os.path.expandvars(d))]
        self.files_read = len(folders)
        files = [os.path.join(d, n + s) for d in folders
                 for n in ("scvpn.log", "scgui.log", "charon.log") for s in ("", ".old")]
        sig = tuple(os.path.getmtime(f) if os.path.exists(f) else 0 for f in files)
        if sig == self._sig and not self._running_logs:
            return
        self._sig = sig

        data = self._archive()
        names = data["names"]
        found = []
        for d in folders:
            found += parse_sophos(_lines(d, "scvpn.log"), _lines(d, "scgui.log"), names)
            found += parse_fortinet(_lines(d, "charon.log"))

        def key(c):
            return (c.get("vpn_source"), c.get("vpn_id"), c.get("start"))

        merged = {key(c): c for c in data["connections"]}
        changed = False
        for c in found:
            if not c["running"] and merged.get(key(c)) != c:
                merged[key(c)] = c
                changed = True
        stored = sorted(merged.values(), key=lambda c: c["start"])
        # Neu gelernte Namen auch für ältere Einträge übernehmen
        for c in stored:
            if c.get("vpn_source") == "Sophos" and names.get(c.get("vpn_id")) not in (None, c["customer_name"]):
                c["customer_name"] = names[c["vpn_id"]]
                c["details"] = f"Sophos Connect: {c['customer_name']} ({c['vpn_id']})"
                changed = True
        data["connections"] = stored
        if changed:
            self._save()
        self._running_logs = [c for c in found if c["running"]]

    # ------------------------------------------------------------ Anzeige

    def connections(self):
        """Alle Verbindungen für die Timeline. Eigene Aufzeichnung nur, wo die Logs nichts haben."""
        self.update_from_logs()
        data = self._archive()
        from_logs = data["connections"] + self._running_logs
        result = [dict(c) for c in from_logs]
        for c in data["adapter"]:
            if not c.get("running") and (_t(c["end"]) - _t(c["start"])).total_seconds() < MIN_SECONDS:
                continue
            if any(l.get("vpn_source") == c.get("vpn_source") and _overlaps(l, c) for l in from_logs):
                continue
            result.append(dict(c))
        if self.sources is not None:
            result = [c for c in result if c.get("vpn_source") in self.sources]
        return sorted(result, key=lambda c: c["start"])


def _t(text):
    return datetime.strptime(text, TIME_FMT)
