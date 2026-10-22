"""
Dateien sicher lesen und schreiben.

- Schreiben geht immer über eine .tmp-Datei und os.replace. Stürzt Zeitzeuge oder
  Windows mittendrin ab, bleibt die alte Datei heil.
- Ist eine JSON-Datei kaputt (halb geschrieben, falsches Format), wird sie nicht
  überschrieben, sondern als <name>.defekt-JJJJMMTT-HHMMSS daneben aufgehoben.
  Danach geht es mit dem Standardwert weiter. Was passiert ist, steht in `problems`
  (das Hauptfenster zeigt es an) und in fehler.log.
- Zu große Dateien werden nicht komplett in den Speicher geladen.
"""

import json
import os
import shutil
import threading
from datetime import datetime

MAX_JSON_BYTES = 50 * 1024 * 1024  # größere JSON-Dateien gelten als kaputt

_lock = threading.Lock()
problems = []        # Meldungen für die Oberfläche (neueste zuletzt)
_log_path = None     # fehler.log im Datenordner, setzt das Hauptfenster


def set_log_path(path):
    global _log_path
    _log_path = path


def log(text):
    """Eine Zeile in fehler.log schreiben (nie mit Fehler)."""
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {text}\n"
    print(line, end="")
    if not _log_path:
        return
    try:
        if os.path.exists(_log_path) and os.path.getsize(_log_path) > 1024 * 1024:
            os.replace(_log_path, _log_path + ".alt")
        with open(_log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def report(text):
    """Problem merken (für die Statuszeile) und ins Log schreiben."""
    with _lock:
        problems.append(text)
        del problems[:-20]
    log(text)


def take_problems():
    """Gemerkte Probleme abholen (danach ist die Liste leer)."""
    with _lock:
        result = list(problems)
        problems.clear()
    return result


def quarantine(path, reason=""):
    """Kaputte Datei beiseitelegen statt sie zu überschreiben. Gibt den neuen Pfad zurück."""
    target = f"{path}.defekt-{datetime.now():%Y%m%d-%H%M%S}"
    try:
        shutil.move(path, target)
    except OSError:
        try:
            shutil.copy2(path, target)
        except OSError:
            target = None
    name = os.path.basename(path)
    if target:
        report(f"{name} war beschädigt{f' ({reason})' if reason else ''}. "
               f"Gesichert als {os.path.basename(target)}, Zeitzeuge macht ohne weiter.")
    else:
        report(f"{name} ist beschädigt und konnte nicht gesichert werden ({reason}).")
    return target


def read_json(path, default=None, expect=None):
    """JSON lesen. Fehlt die Datei: default. Ist sie kaputt oder hat sie den falschen
    Typ (expect, z. B. dict oder list): beiseitelegen und default zurückgeben."""
    if not os.path.exists(path):
        return default
    try:
        size = os.path.getsize(path)
        if size > MAX_JSON_BYTES:
            raise ValueError(f"zu groß: {size // (1024 * 1024)} MB")
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if expect is not None and not isinstance(data, expect):
            raise ValueError(f"unerwarteter Inhalt ({type(data).__name__})")
        return data
    except PermissionError as e:
        # Datei gesperrt (z. B. OneDrive synchronisiert gerade): nicht beiseitelegen
        log(f"{os.path.basename(path)} gerade gesperrt: {e}")
        return default
    except (OSError, ValueError, UnicodeDecodeError) as e:
        quarantine(path, str(e)[:120])
        return default


def write_json(path, data, indent=1, sort_keys=False):
    """JSON atomar schreiben. Gibt False zurück, wenn es nicht ging (Platte voll,
    Datei gesperrt …); der Fehler steht dann in fehler.log."""
    tmp = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent, sort_keys=sort_keys)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except (OSError, TypeError, ValueError) as e:
        report(f"{os.path.basename(path)} konnte nicht gespeichert werden: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def append_line(path, text):
    """Eine Zeile anhängen (z. B. .jsonl). False bei Fehler, ohne Ausnahme."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(text.rstrip("\n") + "\n")
        return True
    except OSError as e:
        report(f"{os.path.basename(path)}: Schreiben fehlgeschlagen ({e})")
        return False
