"""
Dateien sicher lesen und schreiben.

- Schreiben geht immer über eine .tmp-Datei und os.replace. Stürzt Zeitzeuge oder
  Windows mittendrin ab, bleibt die alte Datei heil.
- Ist eine JSON-Datei kaputt (halb geschrieben, falsches Format), wird sie nicht
  überschrieben, sondern als <name>.defekt-JJJJMMTT-HHMMSS daneben aufgehoben.
  Danach geht es mit dem Standardwert weiter. Was passiert ist, steht in `problems`
  (das Hauptfenster zeigt es an) und in fehler.log.
- Zu große Dateien werden nicht komplett in den Speicher geladen. Bei Logdateien
  liest Zeitzeuge dann nur das Ende (log_lines).
- Ist eine Datei kurz gesperrt (OneDrive, Virenscanner), wird es kurz erneut versucht.
"""

import io
import json
import os
import shutil
import threading
import time
from datetime import datetime

MAX_JSON_BYTES = 50 * 1024 * 1024  # größere JSON-Dateien gelten als kaputt
MAX_LOG_BYTES = 100 * 1024 * 1024  # größere Logdateien: nur das Ende lesen
TAIL_BYTES = 20 * 1024 * 1024      # so viel vom Ende einer zu großen Logdatei
RETRIES, RETRY_WAIT = 3, 0.2       # gesperrte Datei: so oft erneut versuchen


class FileLocked(OSError):
    """Datei ist gesperrt (auch nach mehreren Versuchen)."""

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


def read_json(path, default=None, expect=None, raise_locked=False):
    """JSON lesen. Fehlt die Datei: default. Ist sie kaputt oder hat sie den falschen
    Typ (expect, z. B. dict oder list): beiseitelegen und default zurückgeben.

    Ist sie gesperrt, wird es kurz erneut versucht. Danach default, oder FileLocked mit
    raise_locked=True (wer danach speichert, würde sonst die echten Daten überschreiben)."""
    if not os.path.exists(path):
        return default
    for attempt in range(RETRIES + 1):
        try:
            size = os.path.getsize(path)
            if size > MAX_JSON_BYTES:
                raise ValueError(f"zu groß: {size // (1024 * 1024)} MB")
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if expect is not None and not isinstance(data, expect):
                raise ValueError(f"unerwarteter Inhalt ({type(data).__name__})")
            return data
        except FileNotFoundError:
            return default
        except (ValueError, UnicodeDecodeError) as e:
            quarantine(path, str(e)[:120])
            return default
        except OSError as e:
            # Gesperrt (z. B. OneDrive synchronisiert gerade) oder Laufwerk kurz weg:
            # Inhalt ist nicht kaputt, also nicht beiseitelegen
            if attempt < RETRIES:
                time.sleep(RETRY_WAIT)
                continue
            log(f"{os.path.basename(path)} gerade nicht lesbar: {e}")
            if raise_locked:
                raise FileLocked(str(e)) from e
            return default
    return default


def write_json(path, data, indent=1, sort_keys=False):
    """JSON atomar schreiben. Gibt False zurück, wenn es nicht ging (Platte voll,
    Datei gesperrt …); der Fehler steht dann in fehler.log."""
    tmp = f"{path}.tmp"
    try:
        text = json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=sort_keys)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        for attempt in range(RETRIES + 1):
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(text)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, path)
                return True
            except PermissionError:
                # Gesperrt (OneDrive, Virenscanner, Explorer-Vorschau): kurz warten, noch einmal
                if attempt == RETRIES:
                    raise
                time.sleep(RETRY_WAIT)
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


# ---------------------------------------------------------------- Logdateien

_reported_big = set()


def _encoding(head):
    """Kodierung einer Logdatei anhand der ersten Bytes (BOM oder Nullbytes bei UTF-16)."""
    if head.startswith(b"\xff\xfe"):
        return "utf-16-le", 2
    if head.startswith(b"\xfe\xff"):
        return "utf-16-be", 2
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8", 3
    if len(head) >= 4 and head[1] == 0 and head[3] == 0 and head[0] and head[2]:
        return "utf-16-le", 0  # UTF-16 ohne BOM (manche Windows-Werkzeuge)
    return "utf-8", 0


def log_lines(path):
    """Zeilen einer Logdatei, nacheinander gelesen (Generator).

    - UTF-16 (TeamViewer und andere Windows-Werkzeuge schreiben das teils) wird erkannt.
    - Ungültige Bytes fallen weg, Nullbytes werden entfernt: Müll bricht nichts ab.
    - Ist die Datei größer als MAX_LOG_BYTES, nur die letzten TAIL_BYTES ab der nächsten
      vollen Zeile (einmal gemeldet)."""
    size = os.path.getsize(path)
    with open(path, "rb") as raw:
        encoding, bom = _encoding(raw.read(4))
        start = bom
        if size > MAX_LOG_BYTES:
            start = max(bom, size - TAIL_BYTES)
            if encoding.startswith("utf-16"):
                start -= (start - bom) % 2  # nicht mitten in einem Zeichen anfangen
            if path not in _reported_big:
                _reported_big.add(path)
                report(f"{os.path.basename(path)} ist sehr groß ({size // (1024 * 1024)} MB). "
                       f"Zeitzeuge liest nur die letzten {TAIL_BYTES // (1024 * 1024)} MB.")
        raw.seek(start)
        text = io.TextIOWrapper(raw, encoding=encoding, errors="ignore", newline=None)
        if start > bom:
            text.readline()  # angeschnittene erste Zeile überspringen
        for line in text:
            yield line.replace("\x00", "") if "\x00" in line else line
