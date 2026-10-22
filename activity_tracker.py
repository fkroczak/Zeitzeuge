"""
Aktivitätsprotokoll: merkt sich, welches Fenster gerade im Vordergrund ist.

Alle paar Sekunden wird das aktive Fenster (Programm + Fenstertitel) abgefragt.
Gleiche Fenster hintereinander werden zu einem Abschnitt zusammengefasst und
pro Tag in aktivitaet/JJJJ-MM-TT.jsonl gespeichert. Ohne Maus/Tastatur
(Leerlauf) oder bei gesperrtem PC wird nichts aufgezeichnet.

Filter (Einstellungen → Fenster-Filter):
- Sperrliste, Stufe 1 `tracking_ignore`: Titel wird „(ausgeblendet)“, die Zeit zählt weiter.
- Sperrliste, Stufe 2 `tracking_skip`: gar nicht aufzeichnen, die Zeit wird eine Lücke.
- `tracking_mode` "whitelist": nur Fenster aus `tracking_allow` aufzeichnen. Andere werden
  je nach `tracking_whitelist_other` als „(andere)“ / „(nicht erfasst)“ gespeichert ("mask")
  oder übersprungen ("skip"). Die Sperrliste gilt in beiden Modi.
Ein Eintrag passt auf den Programmnamen oder einen Teil des Fenstertitels (ohne Groß/Klein),
mit „re:“ davor ist er ein regulärer Ausdruck. Ungültige Einträge werden übersprungen.

Die Daten bleiben nur auf diesem PC.
"""

import ctypes
import json
import os
import sys
from datetime import datetime, timedelta

import safe_io
from rules import compile_pattern

TIME_FMT = "%Y-%m-%d %H:%M:%S"
# Programme, die "nicht am PC" bedeuten (Sperrbildschirm usw.)
IDLE_APPS = {"lockapp.exe", "logonui.exe", "scrnsave.scr"}


# ---------------------------------------------------------------- Windows-API

if sys.platform == "win32":
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    def foreground_window():
        """(programm.exe, fenstertitel) des aktiven Fensters oder None."""
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None
        # Kein GetWindowTextLengthW: Das schickt dem Fenster eine Nachricht und wartet,
        # bis es antwortet. Hängt das Fenster, hinge sonst auch Zeitzeuge.
        buf = ctypes.create_unicode_buffer(512)
        _user32.InternalGetWindowText(hwnd, buf, 512)

        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        app = ""
        handle = _kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if handle:
            size = wintypes.DWORD(1024)
            path = ctypes.create_unicode_buffer(1024)
            if _kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                app = os.path.basename(path.value)
            _kernel32.CloseHandle(handle)
        return app or "unbekannt", buf.value

    def idle_seconds():
        """Sekunden seit der letzten Maus-/Tastatureingabe."""
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not _user32.GetLastInputInfo(ctypes.byref(info)):
            return 0
        return ((_kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0

else:  # andere Systeme: kein Protokoll
    def foreground_window():
        return None

    def idle_seconds():
        return 0


# ---------------------------------------------------------------- Filter

MODES = ("blacklist", "whitelist")
OTHER_APP, OTHER_TITLE = "(andere)", "(nicht erfasst)"
HIDDEN_TITLE = "(ausgeblendet)"


def compile_list(items):
    """Einträge einer Filterliste kompilieren. Gibt (Muster, Fehler) zurück.

    Fehler = [(Zeile ab 1, Eintrag, Meldung)]; ungültige Einträge fehlen in Muster.
    """
    patterns, errors = [], []
    for no, item in enumerate(items or [], 1):
        item = str(item).strip()
        if not item:
            continue
        try:
            patterns.append(compile_pattern(item))
        except ValueError as e:
            errors.append((no, item, str(e)))
    return patterns, errors


def matches(patterns, app, title):
    return any(p.search(app) or p.search(title) for p in patterns)


def tracking_filters(config):
    """Filter-Einstellungen aus der Config, passend für ActivityTracker und set_filters."""
    return {
        "ignore": config.get("tracking_ignore", []),
        "skip": config.get("tracking_skip", []),
        "allow": config.get("tracking_allow", []),
        "mode": config.get("tracking_mode", "blacklist"),
        "whitelist_other": config.get("tracking_whitelist_other", "mask"),
    }


# ---------------------------------------------------------------- Protokoll

class ActivityTracker:
    MAX_PENDING = 2000  # so viele ungespeicherte Zeilen merken, falls die Platte klemmt

    def __init__(self, folder, idle_limit=300, ignore=(), skip=(), allow=(),
                 mode="blacklist", whitelist_other="mask"):
        self.folder = folder
        self.idle_limit = idle_limit
        self.current = None  # {"app", "title", "raw", "start", "last"}
        self.pending = []    # Zeilen, die (noch) nicht geschrieben werden konnten
        self.set_filters(ignore, skip, allow, mode, whitelist_other)

    def set_filters(self, ignore=(), skip=(), allow=(), mode="blacklist", whitelist_other="mask"):
        """Neue Filter sofort anwenden, auch auf das gerade laufende Fenster."""
        self._ignore, e1 = compile_list(ignore)
        self._skip, e2 = compile_list(skip)
        self._allow, e3 = compile_list(allow)
        self.errors = e1 + e2 + e3
        self.mode = mode if mode in MODES else "blacklist"
        self.whitelist_other = whitelist_other if whitelist_other in ("mask", "skip") else "mask"
        cur = self.current
        if cur:
            key = self.filter(*cur["raw"])
            if key is None:
                self.current = None  # soll nicht mehr aufgezeichnet werden: verwerfen
            else:
                cur["app"], cur["title"] = key

    def filter(self, app, title):
        """(app, titel) so, wie es gespeichert wird, oder None = nicht aufzeichnen."""
        title = (title or "").strip()
        if matches(self._skip, app, title):
            return None
        if self.mode == "whitelist" and not matches(self._allow, app, title):
            return None if self.whitelist_other == "skip" else (OTHER_APP, OTHER_TITLE)
        if matches(self._ignore, app, title):
            return app, HIDDEN_TITLE
        return app, title

    def sample(self, now=None):
        """Einmal abfragen. Gibt True zurück, wenn ein Abschnitt endete oder begann."""
        now = now or datetime.now()
        try:
            info = foreground_window()
        except Exception as e:  # Windows-API kann scheitern (Rechte, Abmelden …)
            safe_io.log(f"Aktives Fenster nicht lesbar: {e}")
            info = None
        try:
            idle = idle_seconds() or 0
        except Exception:
            idle = 0

        away = not info or idle >= self.idle_limit or str(info[0]).lower() in IDLE_APPS
        key = raw = None
        if not away:
            raw = (str(info[0] or "unbekannt"), str(info[1] or ""))
            key = self.filter(*raw)

        cur = self.current
        if cur and key == (cur["app"], cur["title"]) and now - cur["last"] < timedelta(minutes=2):
            cur["last"] = now
            cur["raw"] = raw
            return False

        changed = False
        if cur:
            if now - cur["last"] > timedelta(minutes=2):
                end = cur["last"]  # PC war im Standby, Zeitzeuge pausiert
            elif away and idle:
                end = now - timedelta(seconds=idle)  # Ende = letzte Eingabe
            else:
                end = now
            self._write(cur["app"], cur["title"], cur["start"], max(cur["start"], end))
            self.current = None
            changed = True
        if key:
            self.current = {"app": key[0], "title": key[1], "raw": raw,
                            "start": now, "last": now}
            changed = True
        return changed

    def stop(self):
        """Laufenden Abschnitt speichern (z. B. beim Beenden)."""
        if self.current:
            cur = self.current
            self._write(cur["app"], cur["title"], cur["start"], cur["last"])
            self.current = None

    def _write(self, app, title, start, end):
        """Abschnitt anhängen. Klappt das nicht (Platte voll, Datei gesperrt), bleibt die
        Zeile im Speicher und wird beim nächsten Abschnitt erneut versucht. Nie mit Ausnahme."""
        if (end - start).total_seconds() < 2:
            return
        self.pending.append({"start": start.strftime(TIME_FMT), "end": end.strftime(TIME_FMT),
                             "app": app, "title": title})
        self.flush()

    def flush(self):
        """Ungespeicherte Zeilen schreiben. True, wenn nichts mehr offen ist."""
        while self.pending:
            line = self.pending[0]
            path = os.path.join(self.folder, f"{line['start'][:10]}.jsonl")
            if not safe_io.append_line(path, json.dumps(line, ensure_ascii=False)):
                del self.pending[:-self.MAX_PENDING]
                return False
            self.pending.pop(0)
        return True

    def segments_for(self, date_str):
        """Alle Abschnitte eines Tages, auch der laufende und noch nicht gespeicherte."""
        result = read_segments(self.folder, date_str)
        result += [dict(p) for p in self.pending if p["start"].startswith(date_str)]
        cur = self.current
        if cur and cur["start"].strftime("%Y-%m-%d") == date_str:
            result.append({"start": cur["start"].strftime(TIME_FMT),
                           "end": cur["last"].strftime(TIME_FMT),
                           "app": cur["app"], "title": cur["title"]})
        return result


def _valid_segment(seg):
    return (isinstance(seg, dict)
            and all(isinstance(seg.get(k), str) for k in ("start", "end", "app", "title"))
            and len(seg["start"]) == 19 and len(seg["end"]) == 19)


def read_segments(folder, date_str):
    """Gespeicherte Abschnitte eines Tages, auch wenn die Aufzeichnung gerade pausiert ist.
    Kaputte Zeilen werden übersprungen."""
    result = []
    path = os.path.join(folder, f"{date_str}.jsonl")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    seg = json.loads(line)
                except ValueError:
                    continue
                if _valid_segment(seg):
                    result.append(seg)
    except OSError:  # fehlt oder gerade gesperrt
        pass
    return result


def top_apps(folder, days=7, today=None, limit=15):
    """Die in den letzten Tagen am längsten aufgezeichneten Programme: [(app, Sekunden)]."""
    today = today or datetime.now()
    totals = {}
    for d in range(days):
        date_str = (today - timedelta(days=d)).strftime("%Y-%m-%d")
        for seg in read_segments(folder, date_str):
            app = seg["app"]
            if app in (OTHER_APP, "unbekannt", ""):
                continue
            try:
                secs = (datetime.strptime(seg["end"], TIME_FMT)
                        - datetime.strptime(seg["start"], TIME_FMT)).total_seconds()
            except ValueError:
                continue
            name, total = totals.get(app.lower(), (app, 0))
            totals[app.lower()] = (name, total + max(0, secs))
    return sorted(totals.values(), key=lambda x: -x[1])[:limit]


def merge_segments(segments, min_seconds=30, max_gap=60):
    """Gleiche Fenster mit kurzen Lücken zusammenfassen, sehr kurze weglassen."""
    merged = []
    for s in sorted(segments, key=lambda s: s["start"]):
        if (merged and merged[-1]["app"] == s["app"] and merged[-1]["title"] == s["title"]
                and (datetime.strptime(s["start"], TIME_FMT)
                     - datetime.strptime(merged[-1]["end"], TIME_FMT)).total_seconds() <= max_gap):
            merged[-1]["end"] = max(merged[-1]["end"], s["end"])
        else:
            merged.append(dict(s))
    return [m for m in merged
            if (datetime.strptime(m["end"], TIME_FMT)
                - datetime.strptime(m["start"], TIME_FMT)).total_seconds() >= min_seconds]


def app_label(app):
    name = app[:-4] if app.lower().endswith(".exe") else app
    return {"mstsc": "Remotedesktop", "chrome": "Chrome", "msedge": "Edge",
            "outlook": "Outlook", "winword": "Word", "excel": "Excel",
            "teams": "Teams", "ms-teams": "Teams", "putty": "PuTTY",
            "explorer": "Explorer", "teamviewer": "TeamViewer"}.get(name.lower(), name)
