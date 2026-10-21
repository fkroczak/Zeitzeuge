import os
import re
import sys
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List

from PyQt5.QtWidgets import QApplication

DEBUG = False


class BaseConnectionParser(ABC):
    def __init__(self, debug=False):
        self.DEBUG = debug
        # Cache: (path, tz) -> (mtime, [connections])
        self._cache = {}
        self.files_read = None  # None = noch nicht gelesen

    def get_config_values(self, config_key):
        app = QApplication.instance()
        if not app:
            return self.default_paths, 2

        for widget in app.topLevelWidgets():
            if hasattr(widget, "config") and isinstance(widget.config, dict):
                paths = widget.config.get(f"{config_key}_paths", self.default_paths)
                tz_correction = widget.config.get(
                    f"{config_key}_timezone_correction",
                    widget.config.get("timezone_correction", 2),
                )
                return paths, tz_correction

        return self.default_paths, 2

    @property
    @abstractmethod
    def default_paths(self):
        pass

    @abstractmethod
    def parse_line(self, line, tz_correction):
        pass

    def parse_logs(self):
        connections = []
        config_key = self.__class__.__name__.replace("Parser", "").lower()
        log_paths, tz_correction = self.get_config_values(config_key)
        self.files_read = 0  # für den Hinweis "keine Logdatei gefunden"

        if DEBUG:
            print(f"\n{self.__class__.__name__} sucht in Pfaden: {log_paths}")
            print(f"Zeitzonenkorrektur: {tz_correction}h")

        for log_path in log_paths:
            expanded_path = os.path.expandvars(log_path)

            if DEBUG:
                print(f"\nPrüfe Pfad: {expanded_path}")
                print(f"Existiert: {os.path.exists(expanded_path)}")

            if not os.path.exists(expanded_path):
                if DEBUG:
                    print(f"Log nicht gefunden: {expanded_path}")
                continue

            cache_key = (expanded_path, tz_correction)
            try:
                mtime = os.path.getmtime(expanded_path)

                # Cache-Hit?
                if cache_key in self._cache and self._cache[cache_key][0] == mtime:
                    file_connections = self._cache[cache_key][1]
                    if DEBUG:
                        print(
                            f"Cache-Hit für {expanded_path}, "
                            f"{len(file_connections)} Einträge"
                        )
                else:
                    if DEBUG:
                        print(f"Lese Logdatei neu: {expanded_path}")
                    file_connections = []
                    with open(
                        expanded_path, "r", encoding="utf-8", errors="ignore"
                    ) as f:
                        for line in f:
                            connection = self.parse_line(line, tz_correction)
                            if connection:
                                file_connections.append(connection)
                    self._cache[cache_key] = (mtime, file_connections)
                    if DEBUG:
                        print(
                            f"Gefundene Verbindungen in dieser Datei: "
                            f"{len(file_connections)}"
                        )

                connections.extend(file_connections)
                self.files_read += 1

            except Exception as e:
                print(f"Fehler beim Lesen der Logdatei {expanded_path}: {str(e)}")

        if DEBUG:
            print(f"\n{self.__class__.__name__} Ergebnis:")
            print(f"Gesamtverbindungen gefunden: {len(connections)}")
            for i, conn in enumerate(connections[:3], 1):
                print(f"Beispiel {i}: {conn}")

        return connections


class TeamViewerParser(BaseConnectionParser):
    @property
    def default_paths(self):
        paths = [
            os.path.expandvars(r"%APPDATA%\TeamViewer\Connections.txt"),
            os.path.expandvars(r"%PROGRAMDATA%\TeamViewer\Connections.txt"),
            r"C:\Program Files (x86)\TeamViewer\Connections.txt",
            r"C:\Program Files\TeamViewer\Connections.txt",
        ]
        if DEBUG:
            print(f"TeamViewer Standardpfade: {paths}")
        return paths

    def parse_line(self, line, tz_correction):
        pattern = (
            r"^(\d+)\s+(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})\s+"
            r"(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})"
        )
        match = re.search(pattern, line)
        if not match:
            if DEBUG and line.strip():
                print(f"Kein Match für Zeile: {line.strip()}")
            return None

        session_id, start_str, end_str = match.groups()

        try:
            if DEBUG:
                print(f"Rohe Zeiten - Start: {start_str}, Ende: {end_str}")

            start_utc = datetime.strptime(start_str, "%d-%m-%Y %H:%M:%S")
            end_utc = datetime.strptime(end_str, "%d-%m-%Y %H:%M:%S")

            if DEBUG:
                print(f"UTC Zeiten - Start: {start_utc}, Ende: {end_utc}")

            start_local = start_utc + timedelta(hours=tz_correction)
            end_local = end_utc + timedelta(hours=tz_correction)

            duration = (end_local - start_local).total_seconds()
            if duration >= 60:
                result = {
                    "start": start_local.strftime("%Y-%m-%d %H:%M:%S"),
                    "end": end_local.strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "TeamViewer",
                    "customer_name": f"TeamViewer (ID: {session_id})",
                    "is_suggestion": True,
                }
                if DEBUG:
                    print(f"Erfolgreich geparst: {result}")
                return result
            elif DEBUG:
                print(f"Verbindung zu kurz ({duration}s), ignoriert")

        except ValueError as e:
            if DEBUG:
                print(f"Fehler beim Parsen der Zeiten: {str(e)}")
                print(f"Problemzeile: {line.strip()}")

        return None


class RdmParser(BaseConnectionParser):
    def __init__(self, debug=False):
        super().__init__(debug)
        self.current_sessions = {}

    @property
    def default_paths(self):
        return [
            os.path.expandvars(
                r"%LOCALAPPDATA%\Devolutions\RemoteDesktopManager\Connections.log"
            )
        ]

    def parse_line(self, line, tz_correction):
        pattern = (
            r"^\[(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2})\] "
            r"(.*?) - '(.*?)' \((.*?)\)"
        )
        match = re.search(pattern, line)
        if not match:
            return None

        timestamp_str, action, entry_name, entry_type = match.groups()
        try:
            timestamp = datetime.strptime(timestamp_str, "%d.%m.%Y %H:%M:%S")
            timestamp += timedelta(hours=tz_correction)
            return {
                "timestamp": timestamp,
                "action": action.strip(),
                "entry_name": entry_name,
                "entry_type": entry_type,
                "raw_line": line.strip(),
            }
        except ValueError as e:
            if self.DEBUG:
                print(f"Fehler beim Parsen der Zeit: {timestamp_str} - {str(e)}")
            return None

    def parse_logs(self):
        connections = []
        config_key = self.__class__.__name__.replace("Parser", "").lower()
        log_paths, tz_correction = self.get_config_values(config_key)
        self.files_read = 0

        for log_path in log_paths:
            expanded_path = os.path.expandvars(log_path)
            if not os.path.exists(expanded_path):
                if self.DEBUG:
                    print(f"RDM Log nicht gefunden: {expanded_path}")
                continue

            cache_key = (expanded_path, tz_correction)
            try:
                mtime = os.path.getmtime(expanded_path)

                if cache_key in self._cache and self._cache[cache_key][0] == mtime:
                    if self.DEBUG:
                        print(f"Cache-Hit für {expanded_path}")
                    file_connections = self._cache[cache_key][1]
                else:
                    file_connections = []
                    with open(
                        expanded_path, "r", encoding="utf-8", errors="ignore"
                    ) as f:
                        for line in f:
                            data = self.parse_line(line, tz_correction)
                            if not data:
                                continue
                            self._process_activity(data, file_connections)
                    self._finalize_sessions(file_connections)
                    self._cache[cache_key] = (mtime, file_connections)

                connections.extend(file_connections)
                self.files_read += 1

            except Exception as e:
                print(f"Fehler beim Lesen der RDM-Logdatei {expanded_path}: {str(e)}")

        if self.DEBUG:
            print(f"RDM Parser: {len(connections)} Verbindungen gefunden")
        return connections

    def _process_activity(self, data, connections):
        entry_key = f"{data['entry_name']}_{data['entry_type']}"
        action_lower = data["action"].lower()
        entry_type_lower = data["entry_type"].lower()

        action_map = {
            "passwort angezeigt": "Passwortaktion",
            "one-time password angezeigt": "OTP-Anzeige",
            "benutzername angezeigt": "Benutzername angezeigt",
            "eintrag angezeigt": "Eintrag angezeigt",
        }

        if action_lower in action_map:
            start = data["timestamp"]
            end = start + timedelta(seconds=10)
            connections.append(
                self._create_connection(
                    start,
                    end,
                    data["entry_name"],
                    action_map[action_lower],
                    f"{action_map[action_lower]}: "
                    f"{data['entry_name']} ({data['entry_type']})",
                )
            )
            return

        connection_types = {
            "rdp": "RDP",
            "remote desktop": "RDP",
            "ssh": "SSH",
            "terminal": "SSH",
            "ftp": "FTP",
            "sftp": "FTP",
            "scp": "FTP",
            "website": "Website",
            "vpn": "VPN",
            "tunnel": "VPN",
            "gateway": "VPN",
        }

        for key, protocol in connection_types.items():
            if key in entry_type_lower and action_lower in ("verbinden", "connect", "getrennt", "disconnect"):
                if action_lower in ("verbinden", "connect"):
                    self.current_sessions[entry_key] = {
                        "start": data["timestamp"],
                        "entry_name": data["entry_name"],
                        "entry_type": protocol,
                    }
                elif entry_key in self.current_sessions:
                    session = self.current_sessions[entry_key]
                    connections.append(
                        self._create_connection(
                            session["start"],
                            data["timestamp"],
                            session["entry_name"],
                            f"{protocol}-Verbindung",
                            f"{protocol}-Verbindung {session['entry_name']}",
                        )
                    )
                    del self.current_sessions[entry_key]
                return

    def _finalize_sessions(self, connections):
        for entry_key, session in list(self.current_sessions.items()):
            endtime = session["start"] + timedelta(seconds=60)
            connections.append(
                self._create_connection(
                    session["start"],
                    endtime,
                    session["entry_name"],
                    f"{session['entry_type']}-Sitzung",
                    f"Aktive Sitzung {session['entry_name']}",
                )
            )
            del self.current_sessions[entry_key]

    def _create_connection(self, start, end, entry_name, connection_type, details):
        return {
            "start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end": end.strftime("%Y-%m-%d %H:%M:%S"),
            "type": connection_type,
            "customer_name": entry_name,
            "is_suggestion": True,
            "details": details,
        }



class ConnectionIndex:
    """
    Baut einen Index nach Datum (YYYY-MM-DD) für schnellere Abfragen
    in der Timeline.
    """

    def __init__(self, connections: List[dict]) -> None:
        self.by_date: Dict[str, List[dict]] = defaultdict(list)
        for conn in connections:
            start = conn.get("start")
            if not start or len(start) < 10:
                continue
            date_str = start[:10]  # 'YYYY-MM-DD'
            self.by_date[date_str].append(conn)

    def get_for_date(self, date_str: str) -> List[dict]:
        """Alle Verbindungen für ein bestimmtes Datum."""
        return self.by_date.get(date_str, [])
