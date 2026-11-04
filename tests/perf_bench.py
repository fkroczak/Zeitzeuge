"""Leistung messen: Logs einlesen, Timeline zeichnen, Tag wechseln – mit einem Jahr Daten.

Aufruf:  python tests/perf_bench.py [Durchläufe]
Erzeugt ein Jahr TeamViewer- und RDM-Logs (je Arbeitstag ~20 bzw. ~30 Sitzungen) und
1000 Fensterwechsel für heute, alles in einem leeren Datenordner. Kein Test (läuft nicht in pytest).
"""
import json
import os
import random
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
DATA = tempfile.mkdtemp()
os.environ["ZEITZEUGE_DATA"] = DATA
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

DAYS = 365
rng = random.Random(1)
today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def make_logs():
    tv, rdm = os.path.join(DATA, "Connections.txt"), os.path.join(DATA, "Connections.log")
    with open(tv, "w", encoding="utf-8") as f_tv, open(rdm, "w", encoding="utf-8") as f_rdm:
        for d in range(DAYS, -1, -1):
            day = today - timedelta(days=d)
            if day.weekday() > 4:
                continue
            t = day + timedelta(hours=7)
            for _ in range(20):
                s = t + timedelta(minutes=rng.randint(1, 10))
                e = s + timedelta(minutes=rng.randint(2, 25))
                f_tv.write(f"{rng.randrange(10**9, 2 * 10**9)}\t{s:%d-%m-%Y %H:%M:%S}\t"
                           f"{e:%d-%m-%Y %H:%M:%S}\tdemo\tRemoteControl\t{{x}}\n")
                t = e
            t = day + timedelta(hours=7)
            for i in range(30):
                s = t + timedelta(minutes=rng.randint(1, 5))
                e = s + timedelta(minutes=rng.randint(2, 15))
                name = f"Kunde {i % 12} - SRV{i % 7:02d}"
                f_rdm.write(f"[{s:%d.%m.%Y %H:%M:%S}] Verbinden - '{name}' (RDP (Microsoft Remote Desktop))\n")
                f_rdm.write(f"[{e:%d.%m.%Y %H:%M:%S}] Getrennt - '{name}' (RDP (Microsoft Remote Desktop))\n")
                t = e
    os.makedirs(os.path.join(DATA, "aktivitaet"))
    apps = ["msedge.exe", "ms-teams.exe", "OUTLOOK.EXE", "mstsc.exe"]
    with open(os.path.join(DATA, "aktivitaet", f"{today:%Y-%m-%d}.jsonl"), "w", encoding="utf-8") as f:
        t = today + timedelta(hours=6)
        for i in range(1000):
            e = t + timedelta(seconds=rng.randint(20, 40))
            f.write(json.dumps({"start": f"{t:%Y-%m-%d %H:%M:%S}", "end": f"{e:%Y-%m-%d %H:%M:%S}",
                                "app": rng.choice(apps), "title": f"Fenster {i % 90}"}) + "\n")
            t = e
    with open(os.path.join(DATA, "zeitzeuge_config.json"), "w", encoding="utf-8") as f:
        json.dump({"teamviewer_paths": [tv], "rdm_paths": [rdm], "tracking_enabled": True,
                   "setup_done": True}, f)
    return tv, rdm


def ms(seconds):
    return f"{seconds * 1000:8.1f} ms"


def timed(fn, runs):
    values = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        values.append(time.perf_counter() - t0)
    return statistics.median(values)


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    tv, rdm = make_logs()
    print(f"Testdaten: TeamViewer {os.path.getsize(tv) / 1e6:.1f} MB, RDM {os.path.getsize(rdm) / 1e6:.1f} MB, "
          f"{DAYS} Tage")

    t0 = time.perf_counter()
    import main_timeline
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication
    import timeline_only
    print(f"Import                          {ms(time.perf_counter() - t0)}")

    app = QApplication(sys.argv)
    config = json.load(open(os.path.join(DATA, "zeitzeuge_config.json"), encoding="utf-8"))
    from log_parsers import RdmParser, TeamViewerParser

    def parse_cold():
        TeamViewerParser(config).parse_logs()
        RdmParser(config).parse_logs()
    print(f"Logs einlesen (ohne Cache)      {ms(timed(parse_cold, runs))}")

    t0 = time.perf_counter()
    w = main_timeline.TimelineApp()
    w.show()
    tl = w.timeline
    while getattr(tl, "loading", False) or tl._tv_index is None:
        app.processEvents()
        time.sleep(0.001)
    app.processEvents()
    print(f"Fenster bis Daten gezeichnet    {ms(time.perf_counter() - t0)}")

    def refresh():  # wie alle 2 Minuten: Logs unverändert, nur prüfen und neu zeichnen
        tl.refresh()
        while tl.loading:
            app.processEvents()
            time.sleep(0.001)
    print(f"Neu einlesen (unverändert)      {ms(timed(refresh, runs))}")

    date = QDate.currentDate()
    print(f"Timeline zeichnen (heute)       {ms(timed(lambda: tl.draw_timeline(date), runs))}")

    days = [date.addDays(-i) for i in range(1, 31)]

    def switch():
        for d in days:
            w.date_edit.setDate(d)
            app.processEvents()
    per_day = timed(switch, max(1, runs // 2)) / len(days)
    print(f"Tag wechseln (je Tag, 30 Tage)  {ms(per_day)}")
    w.date_edit.setDate(date)
    app.processEvents()
    print(f"Tagesliste heute: {w.table.rowCount()} Zeilen, Timeline {len(timeline_only.__name__) and 'ok'}")
    w.quit_app()


if __name__ == "__main__":
    main()
