"""
Spuren vom eigenen PC (ohne Netzwerk, ohne Anmeldung):

- PC-Zustand: gesperrt (selbst alle 30 Sekunden geprüft), Ruhezustand, ausgeschaltet und
  abgemeldet (aus dem Windows-Ereignisprotokoll „System“, das jeder Benutzer lesen darf).
- SSH und PowerShell: offene Sitzungen (ssh.exe, PuTTY, KiTTY, plink, WinSCP,
  Enter-PSSession) alle 30 Sekunden, mit Ziel aus der Befehlszeile oder dem Fenstertitel.
- Zuletzt geöffnete Dateien: Verknüpfungen in %APPDATA%\\Microsoft\\Windows\\Recent.
- Browser-Verlauf von Edge und Chrome: nur Domain und Ticketnummer, keine Adressen.
- WLAN: mit welchem Netz der PC verbunden war (z. B. beim Kunden vor Ort).

Alles landet in der Datenbank (Ablage "lokal_spuren"), damit es erhalten bleibt, wenn
Windows die Listen kürzt. Langsame Abfragen (Ereignisprotokoll, netsh, Browser) laufen
in einem Hintergrund-Thread, die Oberfläche wartet nie darauf.
"""

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import datastore
import safe_io
import tickets

TIME_FMT = "%Y-%m-%d %H:%M:%S"
SAMPLE_SECONDS = 30
SLOW_SECONDS = 120          # Ereignisprotokoll, WLAN, Dateien, Browser: alle 2 Minuten
MIN_SESSION_SECONDS = 20    # kürzere SSH-Fenster weglassen
FILE_MINUTES = 2            # so breit steht eine geöffnete Datei in der Timeline
BROWSER_GAP_MINUTES = 5     # Aufrufe derselben Domain mit kürzeren Pausen sind ein Block
BROWSER_DAYS = 14           # so weit zurück liest Zeitzeuge den Verlauf

# Typen in der Timeline (eigene Zeilen, keine Nachfragen)
LOCKED, SLEEP, OFF, LOGGED_OFF = "PC gesperrt", "Ruhezustand", "PC aus", "Abgemeldet"
PC_STATE_TYPES = (LOCKED, SLEEP, OFF, LOGGED_OFF)
WLAN_TYPE = "WLAN"          # ältere Einträge (nur WLAN)
NET_TYPE = "Netzwerk"       # WLAN und Kabel, Name des Netzwerkprofils von Windows
FILE_TYPE = "Datei geöffnet"
BROWSER_TYPE = "Browser"
LOCAL_TYPES = PC_STATE_TYPES + (WLAN_TYPE, NET_TYPE, FILE_TYPE, BROWSER_TYPE)
# Kontrast mindestens 3:1 auf hellem und dunklem Grund (ui_audit_test.py)
COLORS = {LOCKED: "#6B7280", SLEEP: "#64748B", OFF: "#7B8494", LOGGED_OFF: "#8B7AA8",
          WLAN_TYPE: "#0EA5A4", NET_TYPE: "#0EA5A4", FILE_TYPE: "#D97706", BROWSER_TYPE: "#2563EB",
          "PowerShell-Sitzung": "#3F73D0"}

DEFAULT_RECENT_DIR = r"%APPDATA%\Microsoft\Windows\Recent"
DEFAULT_BROWSER_HISTORY = [
    r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\History",
    r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\History",
]
DEFAULT_BROWSER_IGNORE = ["google.com", "google.de", "bing.com", "duckduckgo.com",
                          "login.microsoftonline.com", "login.live.com", "localhost"]


def _fmt(when):
    return when.strftime(TIME_FMT)


def _t(text):
    return datetime.strptime(text, TIME_FMT)


def _no_window():
    return {"creationflags": 0x08000000} if sys.platform == "win32" else {}  # CREATE_NO_WINDOW


def _entry(start, end, kind, name, details, **extra):
    return {"start": _fmt(start), "end": _fmt(end), "type": kind, "customer_name": name,
            "details": details, "local": True, "is_suggestion": True, **extra}


# ------------------------------------------------------------------ PC-Zustand

def is_locked():
    """Ist der Bildschirm gesperrt? (nur Windows; sonst False)"""
    if sys.platform != "win32":
        return False
    import ctypes
    user32 = ctypes.windll.user32
    desk = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
    if not desk:
        return True  # Sperrbildschirm: kein Zugriff auf den Eingabe-Desktop
    try:
        return not user32.SwitchDesktop(desk)
    finally:
        user32.CloseDesktop(desk)


# Ereignisse im Protokoll „System“: (Anbieter-Teil, ID) -> Bedeutung
EVENTS = {
    ("Kernel-Power", 42): "sleep",          # Wechsel in den Ruhezustand
    ("Kernel-Power", 107): "wake",          # Fortsetzen
    ("Power-Troubleshooter", 1): "wake",    # aus dem Ruhezustand aufgewacht
    ("Kernel-General", 13): "off",          # Betriebssystem fährt herunter
    ("Kernel-General", 12): "on",           # Betriebssystem gestartet
    ("Winlogon", 7002): "logoff",
    ("Winlogon", 7001): "logon",
}
EVENT_QUERY = ("*[System[(EventID=42 or EventID=107 or EventID=1 or EventID=12 or EventID=13 "
               "or EventID=7001 or EventID=7002)]]")
_NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"


def read_system_events(days=BROWSER_DAYS):
    """[(Zeit, Bedeutung)] aus dem Ereignisprotokoll, älteste zuerst (Windows, sonst [])."""
    if sys.platform != "win32":
        return []
    try:
        out = subprocess.run(["wevtutil", "qe", "System", f"/q:{EVENT_QUERY}", "/f:xml",
                              "/c:2000", "/rd:true"], capture_output=True, timeout=20,
                             **_no_window()).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    text = out.decode("utf-8", errors="replace")
    return parse_events(f"<Events>{text}</Events>", datetime.now() - timedelta(days=days))


def parse_events(xml_text, since=None):
    """XML von wevtutil -> [(Ortszeit, Bedeutung)], älteste zuerst."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    found = []
    for event in root.iter(f"{_NS}Event"):
        system = event.find(f"{_NS}System")
        if system is None:
            continue
        provider = system.find(f"{_NS}Provider")
        event_id = system.find(f"{_NS}EventID")
        created = system.find(f"{_NS}TimeCreated")
        if provider is None or event_id is None or created is None:
            continue
        name = provider.get("Name", "")
        try:
            number = int(event_id.text)
        except (TypeError, ValueError):
            continue
        meaning = next((m for (part, no), m in EVENTS.items() if no == number and part in name), None)
        if not meaning:
            continue
        when = _utc_to_local(created.get("SystemTime", ""))
        if when and (since is None or when >= since):
            found.append((when, meaning))
    return sorted(found)


def _utc_to_local(text):
    m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", text or "")
    if not m:
        return None
    when = datetime.strptime(f"{m.group(1)} {m.group(2)}", TIME_FMT).replace(tzinfo=timezone.utc)
    return when.astimezone().replace(tzinfo=None)


def event_spans(events):
    """Ruhezustand, PC aus und Abgemeldet als [(Beginn, Ende, Typ)]."""
    pairs = {"sleep": ("wake", SLEEP), "off": ("on", OFF), "logoff": ("logon", LOGGED_OFF)}
    result, open_ = [], {}
    for when, meaning in events:
        if meaning in pairs:
            open_.setdefault(meaning, when)
            continue
        for begin, (end_meaning, kind) in pairs.items():
            # Ein Start beendet auch Ruhezustand und Abmeldung (z. B. nach Stromausfall)
            if begin in open_ and (meaning == end_meaning or meaning == "on"):
                start = open_.pop(begin)
                if when > start:
                    result.append((start, when, kind))
    return result


# ------------------------------------------------------------------ SSH / PowerShell

_SSH_VALUE_OPTS = set("bcDEeFIiJLlmOoPpQRSWw")


def ssh_target(args):
    """Ziel aus ssh.exe-Argumenten: user@host oder host (ohne Optionen)."""
    skip = False
    for arg in args[1:]:
        if skip:
            skip = False
            continue
        if arg.startswith("-") and len(arg) >= 2:
            if arg[1] in _SSH_VALUE_OPTS and len(arg) == 2:
                skip = True
            continue
        return arg.split("@")[-1]
    return ""


def putty_target(args):
    """Ziel aus PuTTY/KiTTY/plink: -load "Sitzung" oder Host."""
    skip = False
    for i, arg in enumerate(args[1:], 1):
        low = arg.lower()
        if low == "-load" and i + 1 < len(args):
            return args[i + 1]
        if skip:
            skip = False
            continue
        if low in ("-l", "-pw", "-p", "-P", "-i", "-L", "-R", "-D", "-m", "-serial", "-sercfg"):
            skip = True
            continue
        if arg.startswith("-"):
            continue
        return arg.split("@")[-1]
    return ""


def winscp_target(args):
    for arg in args[1:]:
        m = re.match(r"^(?:s?ftps?|scp|webdavs?)://(?:[^@/]*@)?([^/:]+)", arg, re.I)
        if m:
            return m.group(1)
    return ""


def pssession_target(args):
    text = " ".join(args)
    if "pssession" not in text.lower() and "-computername" not in text.lower():
        return None  # normale PowerShell, keine Fernsitzung
    m = re.search(r"-ComputerName\s+['\"]?([^'\"\s;]+)", text, re.I)
    return m.group(1) if m else ""


_TITLE_HOST = re.compile(r"^(?:[^@\s]+@)?([^\s:]+)(?::.*)?\s+-\s+(PuTTY|KiTTY|WinSCP)\b", re.I)

# Programm -> (Typ in der Timeline, Ziel aus der Befehlszeile)
PROGRAMS = {
    "ssh.exe": ("SSH-Verbindung", ssh_target),
    "putty.exe": ("SSH-Verbindung", putty_target),
    "kitty.exe": ("SSH-Verbindung", putty_target),
    "plink.exe": ("SSH-Verbindung", putty_target),
    "winscp.exe": ("FTP-Verbindung", winscp_target),
    "powershell.exe": ("PowerShell-Sitzung", pssession_target),
    "pwsh.exe": ("PowerShell-Sitzung", pssession_target),
}


def session_processes():
    """Laufende SSH-/PowerShell-Programme: [(pid, Startzeit, Name, Befehlszeile)]."""
    try:
        import psutil
    except ImportError:
        return []
    result = []
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name not in PROGRAMS:
                continue
            try:
                args = proc.cmdline()
            except Exception:
                args = []
            result.append((proc.info["pid"], proc.info.get("create_time") or 0, name, args))
        except Exception:
            continue
    return result


def session_target(name, args, titles=()):
    """(Typ, Ziel) einer Sitzung, None = keine Fernsitzung (z. B. lokale PowerShell)."""
    kind, func = PROGRAMS[name]
    target = func(args)
    if target is None:
        return None
    if not target:
        target = next((m.group(1) for m in map(_TITLE_HOST.match, titles) if m), "")
    if not target and name == "ssh.exe":
        return None  # ssh ohne Ziel (z. B. ssh-agent-Hilfe)
    return kind, target or name.split(".")[0]


# ------------------------------------------------------------------ Dateien

def recent_files(folder):
    """Zuletzt geöffnete Dateien: [(Zeit, Dateiname)] aus den Verknüpfungen in Recent."""
    folder = os.path.expandvars(folder)
    result = []
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    for name in names:
        if not name.lower().endswith(".lnk"):
            continue
        shown = name[:-4]
        if "." not in shown.strip("."):
            continue  # Ordner (keine Endung)
        try:
            when = datetime.fromtimestamp(os.path.getmtime(os.path.join(folder, name)))
        except (OSError, OverflowError, ValueError):
            continue
        result.append((when.replace(microsecond=0), shown))
    return sorted(result)


# ------------------------------------------------------------------ Browser

def domain_of(url):
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _ignored(domain, ignore):
    return any(domain == d or domain.endswith("." + d) for d in ignore)


def read_history(path, since):
    """Aufrufe aus einer Chromium-History-Datei: [(Zeit, URL, Titel)] (Kopie, die Datei ist offen)."""
    path = os.path.expandvars(path)
    if not os.path.isfile(path):
        return []
    tmp = tempfile.mkdtemp(prefix="zz-history-")
    copy = os.path.join(tmp, "History")
    try:
        shutil.copy2(path, copy)
        con = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
        try:
            webkit = int((since - datetime(1601, 1, 1)).total_seconds() * 1_000_000)
            rows = con.execute("SELECT v.visit_time, u.url, u.title FROM visits v "
                               "JOIN urls u ON v.url = u.id WHERE v.visit_time > ? "
                               "ORDER BY v.visit_time", (webkit,)).fetchall()
        finally:
            con.close()
    except (OSError, sqlite3.Error):
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    result = []
    for visit, url, title in rows:
        try:
            utc = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=int(visit))
        except (OverflowError, TypeError, ValueError):
            continue
        result.append((utc.astimezone().replace(tzinfo=None, microsecond=0), url or "", title or ""))
    return result


def browser_blocks(visits, ignore=(), patterns=None, gap_minutes=BROWSER_GAP_MINUTES):
    """Aufrufe zu Blöcken je Domain: [{"start", "end", "domain", "tickets"}]. Nur Domain und
    Ticketnummer bleiben, keine Adressen und keine Seitentitel."""
    compiled, _errors = tickets.compile_patterns(patterns or tickets.DEFAULT_PATTERNS)
    blocks, last = [], {}
    for when, url, title in sorted(visits):
        domain = domain_of(url)
        if not domain or _ignored(domain, ignore):
            continue
        found = tickets.find_tickets(f"{url} {title}", compiled)
        block = last.get(domain)
        if block and (when - block["last"]).total_seconds() <= gap_minutes * 60:
            block["last"] = when
        else:
            block = {"start": when, "last": when, "domain": domain, "tickets": []}
            blocks.append(block)
            last[domain] = block
        for t in found:
            if t not in block["tickets"]:
                block["tickets"].append(t)
    return [{"start": b["start"], "end": b["last"] + timedelta(minutes=1), "domain": b["domain"],
             "tickets": b["tickets"]} for b in blocks]


# ------------------------------------------------------------------ WLAN

def current_wlan():
    """Name (SSID) des verbundenen WLANs oder "" (nur Windows)."""
    if sys.platform != "win32":
        return ""
    try:
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True,
                             timeout=10, **_no_window()).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    return parse_netsh(out.decode("cp850", errors="replace"))


def parse_netsh(text):
    """SSID aus „netsh wlan show interfaces“ (deutsch oder englisch), nur wenn verbunden."""
    ssid, connected = "", None
    for line in text.splitlines():
        key, _sep, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key in ("status", "state"):
            connected = value.lower() in ("verbunden", "connected")
        elif key == "ssid" and value:
            ssid = value
    return ssid if ssid and connected is not False else ""


# Adapter, die kein Ort sind (VPN, virtuelle Netze): Teil von Name oder Adapter, ohne Groß/Klein
DEFAULT_NETWORK_IGNORE = ["vpn", "fortinet", "sophos", "tap-", "wireguard", "vethernet",
                          "loopback", "hyper-v", "virtualbox", "vmware"]
CATEGORIES = {"domainauthenticated": "Domäne", "private": "privat", "public": "öffentlich",
              "0": "öffentlich", "1": "privat", "2": "Domäne"}
_NET_SCRIPT = ("Get-NetConnectionProfile | ForEach-Object { "
               "\"$($_.Name)`t$($_.InterfaceAlias)`t$($_.NetworkCategory)\" }")


def current_networks():
    """Verbundene Netzwerke: [{"name", "adapter", "category", "wireless"}] (nur Windows)."""
    if sys.platform != "win32":
        return []
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _NET_SCRIPT],
                             capture_output=True, timeout=20, **_no_window()).stdout
        nets = parse_profiles(out.decode("utf-8", errors="replace"))
    except (OSError, subprocess.SubprocessError):
        nets = []
    if not nets:  # ohne PowerShell: wenigstens das WLAN
        ssid = current_wlan()
        nets = [{"name": ssid, "adapter": "WLAN", "category": "", "wireless": True}] if ssid else []
    return nets


def parse_profiles(text):
    """Zeilen "Name<TAB>Adapter<TAB>Kategorie" -> Netzwerke."""
    result = []
    for line in text.splitlines():
        parts = line.rstrip("\r").split("\t")
        if len(parts) < 2 or not parts[0].strip():
            continue
        adapter = parts[1].strip()
        result.append({"name": parts[0].strip(), "adapter": adapter,
                       "category": CATEGORIES.get(parts[2].strip().lower(), "") if len(parts) > 2 else "",
                       "wireless": bool(re.search(r"wlan|wi-?fi|wireless|drahtlos", adapter, re.I))})
    return result


def location_networks(nets, ignore):
    ignore = [i.lower() for i in ignore]
    return [n for n in nets
            if not any(i in n["name"].lower() or i in n["adapter"].lower() for i in ignore)]


# ------------------------------------------------------------------ Leser

class LocalReader:
    """Alle lokalen Spuren aufzeichnen (sample) und für die Timeline liefern (entries)."""

    def __init__(self, config=None, archive_file=None, funcs=None):
        self.config = config if config is not None else {}
        self.archive_file = archive_file
        f = funcs or {}
        self.locked_func = f.get("locked", is_locked)
        self.process_func = f.get("processes", session_processes)
        if "titles" in f:
            self.title_func = f["titles"]
        else:
            from rdp_reader import window_titles
            self.title_func = window_titles
        self.events_func = f.get("events", read_system_events)
        self.wlan_func = f.get("wlan", current_wlan)
        if "networks" in f:
            self.network_func = f["networks"]
        elif "wlan" in f:  # Tests: nur ein WLAN-Name
            self.network_func = lambda: [{"name": s, "adapter": "WLAN", "category": "", "wireless": True}
                                         for s in [self.wlan_func()] if s]
        else:
            self.network_func = current_networks
        self.history_func = f.get("history", read_history)
        self.threaded = f.get("threaded", True)
        self._data = None
        self._lock = threading.Lock()
        self._last_sample = None
        self._last_slow = None
        self._slow_thread = None
        self._pending = None  # Ergebnis des Hintergrund-Threads, übernommen beim nächsten sample()

    def on(self, key):
        return bool(self.config.get(key, True))

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
            parsed = {}
            for key in ("locked", "sessions", "wlan", "events", "files", "browser"):
                value = data.get(key) if isinstance(data, dict) else None
                parsed[key] = [v for v in value or [] if isinstance(v, dict) and self._valid(v)]
            if locked:
                return parsed
            self._data = parsed
        return self._data

    @staticmethod
    def _valid(v):
        try:
            _t(v["start"]), _t(v["end"])
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
            safe_io.report(f"Spuren vom PC: Speichern fehlgeschlagen ({e})")

    # ------------------------------------------------------------ Aufzeichnung

    @staticmethod
    def _track(items, live, now, gap):
        """Laufende Einträge (live: Schlüssel -> Felder) fortschreiben. True = geändert."""
        stamp, changed, still = _fmt(now), False, set()
        for item in items:
            if not item.get("running"):
                continue
            if gap or item["id"] not in live:
                item["running"] = False
            else:
                item["end"] = stamp
                still.add(item["id"])
            changed = True
        for key, fields in live.items():
            if key not in still:
                start = fields.pop("_start", None) or now
                items.append({"id": key, "start": _fmt(start), "end": stamp, "running": True, **fields})
                changed = True
        return changed

    def sample(self, now=None):
        """Alle 30 Sekunden: Sperre und Sitzungen; alle 2 Minuten zusätzlich den Rest. True = geändert."""
        now = now or datetime.now()
        gap = self._last_sample is None or (now - self._last_sample).total_seconds() > 3 * SAMPLE_SECONDS
        self._last_sample = now
        changed = False
        pending, self._pending = self._pending, None
        if pending is not None:  # Datenbank nur aus diesem Thread beschreiben
            changed |= self._merge(pending, now, gap)
        with self._lock:
            data = self._archive()
            if self.on("pcstate_enabled"):
                try:
                    live = {"locked": {}} if self.locked_func() else {}
                except Exception:
                    live = {}
                changed |= self._track(data["locked"], live, now, gap)
            if self.on("shell_enabled"):
                changed |= self._track(data["sessions"], self._live_sessions(now, gap), now, gap)
            if changed:
                self._save()
        if self._last_slow is None or (now - self._last_slow).total_seconds() >= SLOW_SECONDS:
            self._last_slow = now
            if self.threaded:
                if not (self._slow_thread and self._slow_thread.is_alive()):
                    self._slow_thread = threading.Thread(target=self._collect_later, args=(now,), daemon=True)
                    self._slow_thread.start()
            else:
                changed |= self._merge(self._collect(now), now, gap)
        return changed

    def _collect_later(self, now):
        self._pending = self._collect(now)

    def _live_sessions(self, now, gap):
        try:
            procs = self.process_func()
        except Exception:
            return {}
        titles = {}
        if procs and self.title_func:
            try:
                titles = self.title_func()
            except Exception:
                titles = {}
        live = {}
        for pid, created, name, args in procs:
            found = session_target(name, args, titles.get(pid, []))
            if not found:
                continue
            kind, target = found
            try:
                start = datetime.fromtimestamp(created) if created else now
            except (OverflowError, OSError, ValueError):
                start = now
            if gap or start > now or (now - start).total_seconds() > 2 * SAMPLE_SECONDS:
                start = now
            live[f"{pid}-{int(created)}"] = {"kind": kind, "host": target, "program": name, "_start": start}
        return live

    def _collect(self, now):
        """Ereignisprotokoll, WLAN, Dateien und Browser lesen (darf im Hintergrund laufen)."""
        results = {}
        try:
            if self.on("pcstate_enabled"):
                results["events"] = [{"start": _fmt(a), "end": _fmt(b), "kind": k}
                                     for a, b, k in event_spans(self.events_func())]
            if self.on("wlan_enabled"):
                results["networks"] = location_networks(
                    self.network_func(), self.config.get("network_ignore", DEFAULT_NETWORK_IGNORE))
            if self.on("recent_files_enabled"):
                results["files"] = []
                for folder in self.config.get("recent_files_dirs") or [DEFAULT_RECENT_DIR]:
                    results["files"] += recent_files(folder)
            if self.on("browser_enabled"):
                since = now - timedelta(days=BROWSER_DAYS)
                visits = []
                for path in self.config.get("browser_paths") or DEFAULT_BROWSER_HISTORY:
                    visits += self.history_func(path, since)
                results["browser"] = browser_blocks(
                    visits, self.config.get("browser_ignore_domains", DEFAULT_BROWSER_IGNORE),
                    self.config.get("ticket_patterns"))
        except Exception as e:  # Spuren dürfen das Programm nie stören
            safe_io.log(f"Spuren vom PC: {e!r}")
        return results

    def _merge(self, results, now, gap):
        with self._lock:
            return self._merge_locked(results, now, gap)

    def _merge_locked(self, results, now, gap):
        data = self._archive()
        changed = False
        if "events" in results:
            known = {(e["start"], e["kind"]) for e in data["events"]}
            for e in results["events"]:
                if (e["start"], e["kind"]) not in known:
                    data["events"].append(e)
                    changed = True
        if "networks" in results:
            live = {f"net-{n['name']}": {"ssid": n["name"], "adapter": n["adapter"],
                                          "category": n["category"], "wireless": n["wireless"]}
                    for n in results["networks"]}
            changed |= self._track(data["wlan"], live, now, gap)
        if "files" in results:
            known = {(f["start"], f["name"]) for f in data["files"]}
            for when, name in results["files"]:
                if (_fmt(when), name) not in known:
                    data["files"].append({"start": _fmt(when), "end": _fmt(when), "name": name})
                    changed = True
        if "browser" in results:
            stored = {(b["start"], b["domain"]): b for b in data["browser"]}
            for b in results["browser"]:
                item = {"start": _fmt(b["start"]), "end": _fmt(b["end"]), "domain": b["domain"],
                        "tickets": b["tickets"]}
                old = stored.get((item["start"], item["domain"]))
                if old != item:
                    if old:
                        data["browser"].remove(old)
                    data["browser"].append(item)
                    changed = True
        if changed:
            self._save()
        return changed

    # ------------------------------------------------------------ Anzeige

    def entries(self):
        """Alle Spuren für die Timeline (nur eingeschaltete Quellen)."""
        with self._lock:
            data = self._archive()
            result = []
            if self.on("pcstate_enabled"):
                for s in data["locked"]:
                    if (_t(s["end"]) - _t(s["start"])).total_seconds() >= SAMPLE_SECONDS or s.get("running"):
                        result.append(_entry(_t(s["start"]), _t(s["end"]), LOCKED, "gesperrt",
                                             "Bildschirm gesperrt (von Zeitzeuge aufgezeichnet)"))
                for e in data["events"]:
                    kind = e.get("kind", SLEEP)
                    result.append(_entry(_t(e["start"]), _t(e["end"]), kind, kind,
                                         f"{kind} (Windows-Ereignisprotokoll)"))
            if self.on("shell_enabled"):
                for s in data["sessions"]:
                    start, end = _t(s["start"]), _t(s["end"])
                    if not s.get("running") and (end - start).total_seconds() < MIN_SESSION_SECONDS:
                        continue
                    kind, host = s.get("kind", "SSH-Verbindung"), s.get("host") or ""
                    result.append({"start": s["start"], "end": s["end"], "type": kind,
                                   "customer_name": host, "is_suggestion": True,
                                   "details": f"{kind} {host} ({s.get('program', '')}, von Zeitzeuge aufgezeichnet)"})
            if self.on("wlan_enabled"):
                for w in data["wlan"]:
                    name = w.get("ssid", "")
                    if "adapter" not in w:  # ältere Einträge: nur WLAN
                        result.append(_entry(_t(w["start"]), _t(w["end"]), WLAN_TYPE, name, f"WLAN {name}"))
                        continue
                    how = "WLAN" if w.get("wireless") else "Kabel"
                    extra = f", {w['category']}" if w.get("category") else ""
                    result.append(_entry(_t(w["start"]), _t(w["end"]), NET_TYPE, name,
                                         f"Netzwerk {name} ({how}, {w.get('adapter', '')}{extra})"))
            if self.on("recent_files_enabled"):
                for f in data["files"]:
                    start = _t(f["start"])
                    result.append(_entry(start, start + timedelta(minutes=FILE_MINUTES), FILE_TYPE,
                                         f["name"], f"Datei geöffnet: {f['name']}"))
            if self.on("browser_enabled"):
                for b in data["browser"]:
                    ticket = " · ".join(b.get("tickets") or [])
                    name = f"{b['domain']} · {ticket}" if ticket else b["domain"]
                    result.append(_entry(_t(b["start"]), _t(b["end"]), BROWSER_TYPE, name,
                                         f"Browser: {name}", tickets=list(b.get("tickets") or [])))
        return sorted(result, key=lambda e: e["start"])
