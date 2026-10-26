"""
Speicherort der Zeitzeuge-Daten.

Datenordner, Standard: Dokumente\\Zeitzeuge (Config, fehler.log, Sicherung der Datenbank).
Ein anderer Ordner kann im Menü gewählt werden; er wird in
%APPDATA%\\Zeitzeuge\\speicherort.txt gemerkt.

Die Datenbank (zeitzeuge.db, verschlüsselt) liegt lokal unter %LOCALAPPDATA%\\Zeitzeuge.
SQLite verträgt keine Synchronisierung mitten im Schreiben (OneDrive lädt sonst halbe
Stände oder die -wal-Datei einzeln hoch). Im Datenordner liegt darum nur eine
vollständige Sicherung (zeitzeuge-sicherung.db), die atomar ersetzt wird.

Die 3CX-Anmeldung (Browserprofil) liegt immer lokal unter
%LOCALAPPDATA%\\Zeitzeuge, weil "Dokumente" oft mit OneDrive synchronisiert wird.
"""

import os
import shutil

from PySide6.QtCore import QStandardPaths

APP = "Zeitzeuge"
# Was zu den Daten gehört (wird beim Umziehen mitgenommen)
DATA_ITEMS = ["zeitzeuge_config.json", "zeitzeuge-sicherung.db", "zeitzeuge.db",
              # alte Ablagen (vor der Datenbank), falls noch nicht übernommen
              "anrufe.json", "anrufe_stand.json", "personalzeiten.json", "m42_buchungen.json",
              "uebernommen.json", "aktivitaet", "ki_vorschlaege", "vpn_verbindungen.json",
              "taetigkeiten"]
DB_NAME = "zeitzeuge.db"
BACKUP_NAME = "zeitzeuge-sicherung.db"


def _pointer_file():
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return os.path.join(base, APP, "speicherort.txt")


def default_data_dir():
    docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    return os.path.join(docs or os.path.expanduser("~/Documents"), APP)


def data_dir():
    """Aktueller Datenordner (ZEITZEUGE_DATA überschreibt, z. B. für Tests)."""
    if os.environ.get("ZEITZEUGE_DATA"):
        return os.environ["ZEITZEUGE_DATA"]
    try:
        with open(_pointer_file(), encoding="utf-8") as f:
            path = f.read().strip()
        if path:
            return path
    except OSError:
        pass
    return default_data_dir()


def set_data_dir(path):
    pointer = _pointer_file()
    os.makedirs(os.path.dirname(pointer), exist_ok=True)
    with open(pointer, "w", encoding="utf-8") as f:
        f.write(path)


def local_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP)


def db_file(data=None):
    """Pfad der Datenbank. ZEITZEUGE_DB setzt ihn fest; mit ZEITZEUGE_DATA (Tests) liegt
    sie im Datenordner, sonst lokal."""
    if os.environ.get("ZEITZEUGE_DB"):
        return os.environ["ZEITZEUGE_DB"]
    if os.environ.get("ZEITZEUGE_DATA"):
        return os.path.join(data or data_dir(), DB_NAME)
    return os.path.join(local_dir(), DB_NAME)


def backup_file(data=None):
    """Sicherung im Datenordner, oder None, wenn die Datenbank selbst dort liegt."""
    data = data or data_dir()
    db = db_file(data)
    if os.path.normcase(os.path.dirname(os.path.abspath(db))) == os.path.normcase(os.path.abspath(data)):
        return None
    return os.path.join(data, BACKUP_NAME)


def alt_folders(folder):
    """Ordner alt-<Datum> mit übernommenen alten Dateien."""
    try:
        return sorted(n for n in os.listdir(folder) if n.startswith("alt-")
                      and os.path.isdir(os.path.join(folder, n)))
    except OSError:
        return []


def move_data(src, dst):
    """Daten von src nach dst verschieben. Bereits vorhandenes in dst bleibt unberührt."""
    if not src or os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst)):
        return []
    os.makedirs(dst, exist_ok=True)
    moved = []
    for name in DATA_ITEMS + alt_folders(src):
        old, new = os.path.join(src, name), os.path.join(dst, name)
        if os.path.exists(old) and not os.path.exists(new):
            shutil.move(old, new)
            moved.append(name)
    return moved
