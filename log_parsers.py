"""TeamViewer- und RDM-Logs einlesen.

Beide Parser lesen eine Datei nur neu, wenn sie sich geändert hat (Cache nach
Pfad, Änderungszeit und Zeitzonenkorrektur).
"""
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta


def _dmy(text):
    """'21-10-2026 08:12:00' oder '21.10.2026 08:12:00' -> datetime.

    Etwa 10x schneller als strptime; bei großen Logs entscheidet das über die Startzeit.
    Das Format ist durch die Regex vorher schon geprüft, ungültige Werte geben ValueError.
    """
    return datetime(int(text[6:10]), int(text[3:5]), int(text[0:2]),
                    int(text[11:13]), int(text[14:16]), int(text[17:19]))


class BaseConnectionParser:
    config_key = ""      # "teamviewer" oder "rdm": Schlüssel in der Config
    default_paths = []

    def __init__(self, config=None):
        self.config = config if config is not None else {}
        self._cache = {}        # (path, tz) -> (mtime, [connections])
        self.files_read = None  # None = noch nicht gelesen

    def settings(self):
        paths = self.config.get(f"{self.config_key}_paths", self.default_paths)
        tz = self.config.get(f"{self.config_key}_timezone_correction",
                             self.config.get("timezone_correction", 2))
        return paths, tz

    def parse_logs(self):
        connections = []
        log_paths, tz_correction = self.settings()
        self.files_read = 0  # für den Hinweis "keine Logdatei gefunden"
        for log_path in log_paths:
            path = os.path.expandvars(log_path)
            if not os.path.exists(path):
                continue
            try:
                mtime = os.path.getmtime(path)
                cached = self._cache.get((path, tz_correction))
                if cached and cached[0] == mtime:
                    file_connections = cached[1]
                else:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        file_connections = self.parse_file(f, tz_correction)
                    self._cache[(path, tz_correction)] = (mtime, file_connections)
                connections.extend(file_connections)
                self.files_read += 1
            except Exception as e:
                print(f"Fehler beim Lesen der Logdatei {path}: {e}")
        return connections

    def parse_file(self, lines, tz_correction):
        raise NotImplementedError


class TeamViewerParser(BaseConnectionParser):
    config_key = "teamviewer"
    default_paths = [
        os.path.expandvars(r"%APPDATA%\TeamViewer\Connections.txt"),
        os.path.expandvars(r"%PROGRAMDATA%\TeamViewer\Connections.txt"),
        r"C:\Program Files (x86)\TeamViewer\Connections.txt",
        r"C:\Program Files\TeamViewer\Connections.txt",
    ]
    LINE = re.compile(r"^(\d+)\s+(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})\s+"
                      r"(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})")

    def parse_file(self, lines, tz_correction):
        result = []
        for line in lines:
            conn = self.parse_line(line, tz_correction)
            if conn:
                result.append(conn)
        return result

    def parse_line(self, line, tz_correction):
        match = self.LINE.match(line)
        if not match:
            return None
        session_id, start_str, end_str = match.groups()
        try:
            shift = timedelta(hours=tz_correction)  # TeamViewer speichert UTC
            start, end = _dmy(start_str) + shift, _dmy(end_str) + shift
        except ValueError:
            return None
        if (end - start).total_seconds() < 60:
            return None
        return {
            "start": str(start), "end": str(end),  # str(datetime) = "JJJJ-MM-TT hh:mm:ss"
            "type": "TeamViewer",
            "customer_name": f"TeamViewer (ID: {session_id})",
            "tv_id": session_id,
            "is_suggestion": True,
        }


class RdmParser(BaseConnectionParser):
    config_key = "rdm"
    default_paths = [os.path.expandvars(
        r"%LOCALAPPDATA%\Devolutions\RemoteDesktopManager\Connections.log")]
    LINE = re.compile(r"^\[(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2})\] (.*?) - '(.*?)' \((.*?)\)")

    # Anzeigen von Zugangsdaten -> Typ in der Timeline
    ACTIONS = {
        "passwort angezeigt": "Passwortaktion",
        "one-time password angezeigt": "OTP-Anzeige",
        "benutzername angezeigt": "Benutzername angezeigt",
        "eintrag angezeigt": "Eintrag angezeigt",
    }
    # Teil des RDM-Eintragstyps -> Protokoll (erster Treffer zählt)
    PROTOCOLS = {
        "rdp": "RDP", "remote desktop": "RDP", "ssh": "SSH", "terminal": "SSH",
        "ftp": "FTP", "sftp": "FTP", "scp": "FTP", "website": "Website",
        "vpn": "VPN", "tunnel": "VPN", "gateway": "VPN", "teamviewer": "TeamViewer",
    }
    CONNECT = ("verbinden", "connect")
    DISCONNECT = ("getrennt", "disconnect")

    def parse_line(self, line, tz_correction):
        match = self.LINE.match(line)
        if not match:
            return None
        timestamp_str, action, entry_name, entry_type = match.groups()
        try:
            timestamp = _dmy(timestamp_str) + timedelta(hours=tz_correction)
        except ValueError:
            return None
        return {"timestamp": timestamp, "action": action.strip(),
                "entry_name": entry_name, "entry_type": entry_type}

    def parse_file(self, lines, tz_correction):
        connections, sessions = [], {}
        for line in lines:
            data = self.parse_line(line, tz_correction)
            if data:
                self._process(data, connections, sessions)
        # Nicht getrennte Verbindungen: 1 Minute anzeigen
        for session in sessions.values():
            connections.append(self._connection(
                session["start"], session["start"] + timedelta(seconds=60), session["entry_name"],
                f"{session['entry_type']}-Sitzung", f"Aktive Sitzung {session['entry_name']}"))
        return connections

    def _process(self, data, connections, sessions):
        action = data["action"].lower()
        name, entry_type = data["entry_name"], data["entry_type"]
        if action in self.ACTIONS:
            kind = self.ACTIONS[action]
            connections.append(self._connection(
                data["timestamp"], data["timestamp"] + timedelta(seconds=10), name, kind,
                f"{kind}: {name} ({entry_type})"))
            return
        if action not in self.CONNECT + self.DISCONNECT:
            return
        type_lower = entry_type.lower()
        protocol = next((p for key, p in self.PROTOCOLS.items() if key in type_lower), None)
        if protocol is None:
            return
        key = f"{name}_{entry_type}"
        if action in self.CONNECT:
            sessions[key] = {"start": data["timestamp"], "entry_name": name, "entry_type": protocol}
        elif key in sessions:
            session = sessions.pop(key)
            conn = self._connection(session["start"], data["timestamp"], name,
                                    f"{protocol}-Verbindung", f"{protocol}-Verbindung {name}")
            if protocol == "TeamViewer" and name.replace(" ", "").isdigit():
                conn["tv_id"] = name.replace(" ", "")
            connections.append(conn)

    @staticmethod
    def _connection(start, end, entry_name, connection_type, details):
        return {"start": str(start), "end": str(end), "type": connection_type,
                "customer_name": entry_name, "is_suggestion": True, "details": details}


class ConnectionIndex:
    """Verbindungen nach Datum (JJJJ-MM-TT) für schnelle Abfragen in der Timeline."""

    def __init__(self, connections):
        self.by_date = defaultdict(list)
        for conn in connections:
            start = conn.get("start")
            if start and len(start) >= 10:
                self.by_date[start[:10]].append(conn)

    def get_for_date(self, date_str):
        return self.by_date.get(date_str, [])
