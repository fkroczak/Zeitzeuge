"""Startzeit mit vollen Daten (wie heavy_bench.py): erstes Bild, Daten da.

Aufruf:  python tests/heavy_start_bench.py [Durchläufe] [--data ORDNER] [--src ORDNER] [--profile]
Legt die Lastdaten von heavy_bench.py an (oder nimmt --data, z. B. für einen Vergleich mit
einem älteren Stand über --src) und startet je Durchlauf einen frischen Python-Prozess darauf
(kalter Import wie beim echten Start).
  import  Module geladen
  build   Hauptfenster gebaut
  paint   erstes Bild der Timeline (Umrisse oder Daten), ab Prozessstart
  data    Timeline mit Daten und Logs gezeichnet, Tagesliste gefüllt, ab Prozessstart
--profile druckt für einen Durchlauf die 30 teuersten Funktionen bis "data".
Kein Test (läuft nicht in pytest).
"""
import json
import os
import statistics
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

CHILD = r"""
import os, sys, time, json
t0 = time.perf_counter()
PROFILE = os.environ.get("ZZ_PROFILE") == "1"
if PROFILE:
    import cProfile, pstats, io
    prof = cProfile.Profile(); prof.enable()
sys.path.insert(0, SRC)
import main_timeline
from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication
t1 = time.perf_counter()
app = QApplication(sys.argv)
w = main_timeline.TimelineApp()
t2 = time.perf_counter()
first_paint = []
class Spy(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Paint and not first_paint:
            first_paint.append(time.perf_counter())
        return False
spy = Spy()
tl = w.timeline
tl.viewport().installEventFilter(spy)
w.show()
while (getattr(tl, "loading", False) or tl._tv_index is None or not getattr(tl, "_day_data", None)
       or not first_paint):
    app.processEvents()
    time.sleep(0.001)
app.processEvents()
t4 = time.perf_counter()
if PROFILE:
    prof.disable()
    out = io.StringIO()
    pstats.Stats(prof, stream=out).sort_stats("cumulative").print_stats(30)
    print(out.getvalue(), file=sys.stderr)
print(json.dumps({"import": t1 - t0, "build": t2 - t1, "paint": first_paint[0] - t0, "data": t4 - t0}))
w.quit_app()
"""


def prepare():
    import heavy_bench as hb  # legt DATA an und setzt ZEITZEUGE_DATA
    hb.make_logs()
    import main_timeline as mt
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    w = mt.TimelineApp()
    hb.fill_db(mt)
    w.quit_app()
    app.processEvents()
    return hb.DATA


def _arg(name, default=None):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


def main():
    skip = {_arg("--data"), _arg("--src")}
    args = [a for a in sys.argv[1:] if not a.startswith("--") and a not in skip]
    runs = int(args[0]) if args else 5
    data = _arg("--data") or prepare()
    src = os.path.abspath(_arg("--src", os.path.join(ROOT, "src")))
    env = dict(os.environ, QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
               ZEITZEUGE_DATA=data)
    code = f"SRC={src!r}\n" + CHILD
    if "--profile" in sys.argv:
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                             env=dict(env, ZZ_PROFILE="1"), capture_output=True, text=True, timeout=120)
        print("\n".join(l for l in out.stderr.splitlines() if "propagateSizeHints" not in l)[:12000])
    results = []
    for _ in range(runs):
        out = subprocess.run([sys.executable, "-c", code], env=env,
                             capture_output=True, text=True, cwd=ROOT, timeout=120)
        line = [l for l in out.stdout.splitlines() if l.startswith("{")]
        if not line:
            sys.exit(out.stderr)
        results.append(json.loads(line[-1]))
    for key in ("import", "build", "paint", "data"):
        values = [r[key] * 1000 for r in results]
        print(f"{key:7s} Median {statistics.median(values):7.1f} ms   "
              f"(min {min(values):6.1f}, max {max(values):6.1f})")


if __name__ == "__main__":
    main()
