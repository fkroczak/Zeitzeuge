"""
Speicherort der Zeitzeuge-Daten.

Standard: Dokumente\\Zeitzeuge (Config, Anrufe, Aktivitätsprotokoll).
Ein anderer Ordner kann im Menü gewählt werden; er wird in
%APPDATA%\\Zeitzeuge\\speicherort.txt gemerkt.

Die 3CX-Anmeldung (Browserprofil) liegt immer lokal unter
%LOCALAPPDATA%\\Zeitzeuge, weil "Dokumente" oft mit OneDrive synchronisiert wird.
"""

import os
import shutil

from PyQt5.QtCore import QStandardPaths

APP = "Zeitzeuge"
# Was zu den Daten gehört (wird beim Umziehen mitgenommen)
DATA_ITEMS = ["zeitzeuge_config.json", "anrufe.json", "anrufe_stand.json",
              "personalzeiten.json", "aktivitaet", "ki_vorschlaege",
              "vpn_verbindungen.json", "taetigkeiten"]


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


def move_data(src, dst):
    """Daten von src nach dst verschieben. Bereits vorhandenes in dst bleibt unberührt."""
    if not src or os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst)):
        return []
    os.makedirs(dst, exist_ok=True)
    moved = []
    for name in DATA_ITEMS:
        old, new = os.path.join(src, name), os.path.join(dst, name)
        if os.path.exists(old) and not os.path.exists(new):
            shutil.move(old, new)
            moved.append(name)
    return moved
