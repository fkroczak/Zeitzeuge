"""
Sitzungen aus SessionMGMT (schlanker Ersatz für den Remote Desktop Manager).

SessionMGMT schreibt jede Sitzung in sessions.log im Datenordner (Zeit in UTC):
  2026-11-11T08:18:53.616Z [INFO] launch session=3f9a1c host=192.168.1.26:3389 user=administrator type=1 vault="Kunde" entry="DC01" platform=win32 method=embedded
  2026-11-11T09:01:12.004Z [INFO] end session=3f9a1c host=... start=2026-11-11T08:18:53.616Z duration=00:42:18 reason=closed
launch und end gehören über session= zusammen. vault ist der Kunde (oberster Ordner im
Devolutions Server), entry der Name des Eintrags wie in RDM. Web-Einträge haben nur launch.

Den Datenordner legt der Installer in SessionMGMT.json neben der EXE fest; Zeitzeuge sucht die
Datei in den üblichen Programmordnern, sonst gilt %LOCALAPPDATA%\\SessionMGMT.
"""

import json
import os
import re
from datetime import datetime, timedelta

from log_parsers import BaseConnectionParser
from rdp_reader import _local, short_host

DEFAULT_LOG = r"%LOCALAPPDATA%\SessionMGMT\sessions.log"
CONFIG_DIRS = (r"%LOCALAPPDATA%\Programs\SessionMGMT", r"%PROGRAMFILES%\SessionMGMT")
OPEN_MINUTES = 1        # ohne Ende (Web, Absturz): so lange in der Timeline
MATCH_SECONDS = 120     # so weit dürfen Beginn/Ende anderer Quellen abweichen

_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?\s+"
                   r"\[\w+\]\s+(launch|end)\b(.*)$")
_FIELD = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S*)')
_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")

# DVLS-Verbindungstyp (Feld type=) -> Protokoll
TYPES = {"1": "RDP", "5": "Website", "77": "SSH", "74": "SSH", "20": "VPN"}
# Methode (Feld method=) -> Protokoll, wenn der Typ nichts sagt
METHODS = {"rdpfile": "RDP", "putty": "SSH", "browser": "Website", "sccli": "VPN", "forticlient": "VPN"}
METHOD_TEXT = {"embedded": "eingebettet", "rdpfile": "mstsc", "putty": "PuTTY", "browser": "Browser",
               "sccli": "Sophos Connect", "forticlient": "FortiClient", "application": "Anwendung"}


def _value(raw):
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return re.sub(r"\\(.)", r"\1", raw[1:-1])
    return raw


def _stamp(text):
    m = _STAMP.match(text or "")
    return _local(m.group(1), m.group(2)) if m else None


def protocol(fields):
    """RDP, SSH, Website, VPN oder '' (andere Anwendung)."""
    known = TYPES.get(fields.get("type", ""))
    if known:
        return known
    method = fields.get("method", "")
    if method in METHODS:
        return METHODS[method]
    port = fields.get("host", "").rpartition(":")[2]
    if method == "embedded":
        return "RDP" if port == "3389" else "SSH"
    return {"3389": "RDP", "22": "SSH", "23": "SSH"}.get(port, "")


def parse_sessions(lines):
    """Sitzungen aus sessions.log: [{"start", "end" (None = kein Ende), "fields", "reason"}].

    Eine end-Zeile ohne passende launch-Zeile (Anfang der Datei abgeschnitten) reicht auch:
    sie trägt den Beginn in start= und dieselben Felder."""
    sessions, by_id = [], {}
    for line in lines:
        m = _LINE.match(line.strip())
        if not m:
            continue
        try:
            when = _local(m.group(1), m.group(2))
        except (ValueError, OverflowError):
            continue
        fields = {k: _value(v) for k, v in _FIELD.findall(m.group(4))}
        sid = fields.get("session", "")
        if m.group(3) == "launch":
            s = {"start": when, "end": None, "fields": fields, "reason": ""}
            sessions.append(s)
            if sid:
                by_id[sid] = s
            continue
        s = by_id.pop(sid, None) if sid else None
        if s is None:
            try:
                start = _stamp(fields.get("start"))
            except (ValueError, OverflowError):
                start = None
            if start is None:
                continue
            s = {"start": start, "end": None, "fields": fields, "reason": ""}
            sessions.append(s)
        s["end"] = max(when, s["start"])
        s["reason"] = fields.get("reason", "")
    return sessions


def to_connection(session):
    """Sitzung -> Eintrag für die Timeline (wie RDM: "<Protokoll>-Verbindung", Name = Eintrag)."""
    f = session["fields"]
    proto = protocol(f)
    host = short_host(f.get("host", ""))
    entry = f.get("entry", "").strip()
    vault = f.get("vault", "").strip()
    name = entry or host or vault or "SessionMGMT"
    kind = f"{proto}-Verbindung" if proto else "Fernzugriff"
    start, end = session["start"], session["end"]
    details = f"{proto + '-Verbindung' if proto else 'Anwendung'} {name}"
    if host and host.casefold() != name.casefold():
        details += f" ({host})"
    if vault:
        details += f", Kunde {vault}"
    if f.get("user"):
        details += f", Benutzer {f['user']}"
    via = METHOD_TEXT.get(f.get("method", ""), f.get("method", ""))
    details += f" über SessionMGMT ({via})" if via else " über SessionMGMT"
    if end is None:
        details += ", Ende unbekannt" if proto != "Website" else ", im Browser geöffnet"
        end = start + timedelta(minutes=OPEN_MINUTES)
    elif session.get("reason") == "failed":
        details += ", Verbindung fehlgeschlagen"
    conn = {"start": str(start.replace(microsecond=0)), "end": str(end.replace(microsecond=0)),
            "type": kind, "customer_name": name, "details": details, "is_suggestion": True,
            "sm_source": True, "sm_host": host, "sm_open": session["end"] is None}
    if vault:
        conn["vault"] = vault
    return conn


def configured_log():
    """sessions.log im Datenordner aus SessionMGMT.json (vom Installer geschrieben) oder None."""
    for folder in CONFIG_DIRS:
        path = os.path.join(os.path.expandvars(folder), "SessionMGMT.json")
        try:
            with open(path, encoding="utf-8-sig") as f:
                data_dir = json.load(f).get("DataDir")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(data_dir, str) and data_dir.strip():
            return os.path.join(os.path.expandvars(data_dir.strip()), "sessions.log")
    return None


class SessionMgmtParser(BaseConnectionParser):
    """sessions.log lesen (nur neu, wenn sich die Datei geändert hat)."""
    config_key = "sessionmgmt"
    default_paths = [DEFAULT_LOG]

    def settings(self):
        paths = list(self.config.get("sessionmgmt_paths") or self.default_paths)
        extra = configured_log()
        if extra and all(os.path.normcase(os.path.expandvars(p)) != os.path.normcase(extra) for p in paths):
            paths.append(extra)
        return paths, 0  # Zeiten stehen in UTC im Log, keine Korrektur

    def parse_file(self, lines, tz_correction):
        result = []
        for s in parse_sessions(lines):
            if s["reason"] == "failed":
                continue  # nie verbunden
            result.append(to_connection(s))
        return result


# ------------------------------------------------------------------ Doppelte

def _overlap(a_start, a_end, b_start, b_end, slack=0):
    pad = timedelta(seconds=slack)
    return a_start - pad < b_end and b_start - pad < a_end


def _same_host(a, b):
    a, b = (a or "").casefold(), (b or "").casefold()
    return not a or not b or a == b or a.split(".")[0] == b.split(".")[0]


def _t(text):
    return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")


def merge(sm_conns, others):
    """Doppelte zwischen SessionMGMT und anderen Quellen eines Tages entfernen.

    RDP und SSH: SessionMGMT kennt Kunde und Eintrag, die eigene Aufzeichnung (mstsc,
    Ereignisprotokoll, PuTTY) zeigt dieselbe Sitzung noch einmal. Mit Ende zählt die Sitzung
    aus SessionMGMT, die andere fällt weg; ohne Ende (SessionMGMT abgestürzt) bleibt die andere
    und der Start aus SessionMGMT fällt weg.
    VPN: Sophos Connect und FortiClient kennen die echten Zeiten des Tunnels; SessionMGMT weiß
    nur, wann es den Aufbau angestoßen hat. Dort bleibt die Verbindung aus dem VPN-Log.

    Gibt (SessionMGMT-Einträge, andere Einträge) zurück."""
    if not sm_conns or not others:
        return list(sm_conns), list(others)
    drop_sm, drop_other = set(), set()
    parsed = [(_t(o["start"]), _t(o["end"])) for o in others]
    for i, s in enumerate(sm_conns):
        kind = s.get("type")
        if kind not in ("RDP-Verbindung", "SSH-Verbindung", "VPN-Verbindung"):
            continue
        s_start, s_end = _t(s["start"]), _t(s["end"])
        for j, o in enumerate(others):
            if j in drop_other or o.get("type") != kind:
                continue
            o_start, o_end = parsed[j]
            if kind == "VPN-Verbindung":
                if abs((o_start - s_start).total_seconds()) <= MATCH_SECONDS or (
                        not s.get("sm_open") and _overlap(s_start, s_end, o_start, o_end)):
                    drop_sm.add(i)
                    if s.get("vault"):
                        o.setdefault("vault", s["vault"])
                continue
            host = o.get("sm_host") or o.get("customer_name", "")
            if not _same_host(s.get("sm_host"), host):
                continue
            if s.get("sm_open"):
                if -MATCH_SECONDS <= (o_start - s_start).total_seconds() <= MATCH_SECONDS:
                    drop_sm.add(i)
                    if s.get("vault"):
                        o.setdefault("vault", s["vault"])
                    break
            elif _overlap(s_start, s_end, o_start, o_end, MATCH_SECONDS):
                drop_other.add(j)
    return ([s for i, s in enumerate(sm_conns) if i not in drop_sm],
            [o for j, o in enumerate(others) if j not in drop_other])
