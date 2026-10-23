"""Startzeit messen: Import, Fenster bauen, Fenster sichtbar, Logs gezeichnet.

Aufruf:  python tests/start_bench.py [Durchläufe] [Ordner mit Connections.txt/.log]
Jeder Durchlauf ist ein frischer Python-Prozess (kalter Import wie beim echten Start).
"""
import json
import os
import statistics
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHILD = r"""
import os, sys, time, json
t0 = time.perf_counter()
sys.path.insert(0, ROOT)
import main_timeline
from PySide6.QtWidgets import QApplication
import timeline_only
draws = [0]
_orig = timeline_only.TimelineView.draw_timeline
def _count(self, *a):
    draws[0] += 1
    return _orig(self, *a)
timeline_only.TimelineView.draw_timeline = _count
t1 = time.perf_counter()
app = QApplication(sys.argv)
w = main_timeline.TimelineApp()
t2 = time.perf_counter()
w.show()
while draws[0] == 0:  # Fenster sichtbar und Timeline einmal gezeichnet
    app.processEvents()
t3 = time.perf_counter()
tl = w.timeline
# Alte Version liest die Logs beim ersten Zeichnen, neue im Hintergrund
while getattr(tl, "loading", False) or tl._tv_index is None:
    app.processEvents()
    time.sleep(0.001)
app.processEvents()
t4 = time.perf_counter()
print(json.dumps({"import": t1 - t0, "build": t2 - t1, "visible": t3 - t0, "data": t4 - t0,
                  "draws": draws[0]}))
w.quit_app()
"""


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    data = tempfile.mkdtemp()
    env = dict(os.environ, QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
               ZEITZEUGE_DATA=data)
    if len(sys.argv) > 2:  # große Beispiel-Logs statt der echten
        logs = os.path.abspath(sys.argv[2])
        with open(os.path.join(data, "zeitzeuge_config.json"), "w", encoding="utf-8") as f:
            json.dump({"teamviewer_paths": [os.path.join(logs, "Connections.txt")],
                       "rdm_paths": [os.path.join(logs, "Connections.log")]}, f)
    results = []
    for _ in range(runs):
        out = subprocess.run([sys.executable, "-c", f"ROOT={ROOT!r}\n" + CHILD], env=env,
                             capture_output=True, text=True, cwd=ROOT, timeout=60)
        line = [l for l in out.stdout.splitlines() if l.startswith("{")]
        if not line:
            sys.exit(out.stderr)
        results.append(json.loads(line[-1]))
    print(f"Zeichnen beim Start: {results[0]['draws']}x")
    for key in ("import", "build", "visible", "data"):
        values = [r[key] * 1000 for r in results]
        print(f"{key:7s} Median {statistics.median(values):7.1f} ms   "
              f"(min {min(values):6.1f}, max {max(values):6.1f})")


if __name__ == "__main__":
    main()
