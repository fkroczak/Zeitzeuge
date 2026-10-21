"""
Aktivitätsprotokoll: merkt sich, welches Fenster gerade im Vordergrund ist.

Alle paar Sekunden wird das aktive Fenster (Programm + Fenstertitel) abgefragt.
Gleiche Fenster hintereinander werden zu einem Abschnitt zusammengefasst und
pro Tag in aktivitaet/JJJJ-MM-TT.jsonl gespeichert. Ohne Maus/Tastatur
(Leerlauf) oder bei gesperrtem PC wird nichts aufgezeichnet.

Die Daten bleiben nur auf diesem PC.
"""

import ctypes
import json
import os
import sys
from datetime import datetime, timedelta

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
        length = _user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)

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


# ---------------------------------------------------------------- Protokoll

class ActivityTracker:
    def __init__(self, folder, idle_limit=300, ignore=()):
        self.folder = folder
        self.idle_limit = idle_limit
        self.ignore = [w.lower() for w in ignore if w]
        self.current = None  # {"app", "title", "start", "last"}

    def _clean_title(self, app, title):
        text = f"{app} {title}".lower()
        if any(word in text for word in self.ignore):
            return "(ausgeblendet)"
        return title.strip()

    def sample(self, now=None):
        """Einmal abfragen. Gibt True zurück, wenn ein Abschnitt endete oder begann."""
        now = now or datetime.now()
        info = foreground_window()
        idle = idle_seconds()

        key = None
        if info and idle < self.idle_limit and info[0].lower() not in IDLE_APPS:
            key = (info[0], self._clean_title(*info))

        cur = self.current
        if cur and key == (cur["app"], cur["title"]) and now - cur["last"] < timedelta(minutes=2):
            cur["last"] = now
            return False

        changed = False
        if cur:
            if now - cur["last"] > timedelta(minutes=2):
                end = cur["last"]  # PC war im Standby, Zeitzeuge pausiert
            elif key is None and idle:
                end = now - timedelta(seconds=idle)  # Ende = letzte Eingabe
            else:
                end = now
            self._write(cur["app"], cur["title"], cur["start"], max(cur["start"], end))
            self.current = None
            changed = True
        if key:
            self.current = {"app": key[0], "title": key[1], "start": now, "last": now}
            changed = True
        return changed

    def stop(self):
        """Laufenden Abschnitt speichern (z. B. beim Beenden)."""
        if self.current:
            cur = self.current
            self._write(cur["app"], cur["title"], cur["start"], cur["last"])
            self.current = None

    def _write(self, app, title, start, end):
        if (end - start).total_seconds() < 2:
            return
        os.makedirs(self.folder, exist_ok=True)
        path = os.path.join(self.folder, f"{start:%Y-%m-%d}.jsonl")
        line = {"start": start.strftime(TIME_FMT), "end": end.strftime(TIME_FMT),
                "app": app, "title": title}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    def segments_for(self, date_str):
        """Alle Abschnitte eines Tages (inkl. des gerade laufenden)."""
        result = []
        path = os.path.join(self.folder, f"{date_str}.jsonl")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        result.append(json.loads(line))
                    except ValueError:
                        continue
        cur = self.current
        if cur and cur["start"].strftime("%Y-%m-%d") == date_str:
            result.append({"start": cur["start"].strftime(TIME_FMT),
                           "end": cur["last"].strftime(TIME_FMT),
                           "app": cur["app"], "title": cur["title"]})
        return result


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
