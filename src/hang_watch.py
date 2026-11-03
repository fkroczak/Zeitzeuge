"""
Hänger-Wächter: merkt, wenn das Fenster nicht mehr reagiert, und schreibt auf, woran es hängt.

Ein Zeitgeber im Hauptthread meldet sich alle 200 ms. Bleibt die Meldung länger als
LIMIT Sekunden aus, schreibt ein Hintergrund-Thread die Aufrufstapel aller Threads in
haenger.log im Datenordner. Damit lässt sich die Ursache später finden.
"""

import os
import sys
import threading
import time
import traceback
from datetime import datetime

from PySide6.QtCore import QTimer

LIMIT = 2.0          # Sekunden ohne Rückmeldung, ab denen es als Hänger zählt
MAX_LOG = 512 * 1024  # haenger.log nicht endlos wachsen lassen


class HangWatch:
    def __init__(self, log_path, parent=None):
        self.log_path = log_path
        self._beat = time.monotonic()
        self._main = threading.main_thread().ident
        self._timer = QTimer(parent)
        self._timer.timeout.connect(self._tick)
        self._timer.start(200)
        threading.Thread(target=self._watch, daemon=True, name="Hänger-Wächter").start()

    def _tick(self):
        self._beat = time.monotonic()

    def _watch(self):
        logged_for = None  # Herzschlag, zu dem dieser Hänger schon gemeldet wurde
        while True:
            time.sleep(0.5)
            beat = self._beat
            stuck = time.monotonic() - beat
            if stuck < LIMIT:
                if logged_for is not None:
                    self._write(f"  … wieder frei (insgesamt etwa {stuck_total:.1f} s)\n")
                    logged_for = None
                continue
            stuck_total = stuck
            if logged_for != beat:
                logged_for = beat
                self._dump(stuck)

    def _dump(self, stuck):
        frames = sys._current_frames()
        names = {t.ident: t.name for t in threading.enumerate()}
        lines = [f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} Fenster reagiert seit {stuck:.1f} s nicht ===\n"]
        # Hauptthread zuerst: dort steht, was das Fenster blockiert
        for ident in sorted(frames, key=lambda i: i != self._main):
            if ident == threading.get_ident():
                continue
            label = "Hauptthread (Fenster)" if ident == self._main else names.get(ident, ident)
            lines.append(f"--- {label}\n")
            lines.extend(traceback.format_stack(frames[ident])[-12:])
        self._write("".join(lines))

    def _write(self, text):
        try:
            if os.path.exists(self.log_path) and os.path.getsize(self.log_path) > MAX_LOG:
                os.replace(self.log_path, self.log_path + ".alt")
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass
