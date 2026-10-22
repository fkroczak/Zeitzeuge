"""Tagesliste mit vollem PC-Verlauf muss schnell gezeichnet werden.

Früher maß Qt die Spaltenbreiten nach jeder Zelle neu: Bei ~1000 Fensterwechseln
hing das Fenster über 20 s (alle 30 s bei aktiver Aufzeichnung).
"""
import json
import os
import random
import sys
import tempfile
import time
from datetime import datetime, timedelta

data = tempfile.mkdtemp()
os.environ["ZEITZEUGE_DATA"] = data
os.makedirs(os.path.join(data, "aktivitaet"))
start = datetime.now().replace(hour=6, minute=0, second=0, microsecond=0)
apps = ["msedge.exe", "ms-teams.exe", "chrome.exe", "OUTLOOK.EXE", "mstsc.exe"]
with open(os.path.join(data, "aktivitaet", f"{start:%Y-%m-%d}.jsonl"), "w", encoding="utf-8") as f:
    t = start
    for i in range(1000):
        e = t + timedelta(seconds=random.randint(30, 60))
        f.write(json.dumps({"start": f"{t:%Y-%m-%d %H:%M:%S}", "end": f"{e:%Y-%m-%d %H:%M:%S}",
                            "app": random.choice(apps), "title": f"Fenster {i % 90}"}) + "\n")
        t = e
with open(os.path.join(data, "zeitzeuge_config.json"), "w", encoding="utf-8") as f:
    json.dump({"tracking_enabled": True, "show_pc_in_list": True}, f)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main_timeline  # noqa: E402  (erst nach ZEITZEUGE_DATA laden)
from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
window = main_timeline.TimelineApp()
window.show()
wait = time.time() + 5  # Logs werden im Hintergrund eingelesen
while time.time() < wait and window.table.rowCount() < 150:
    app.processEvents()
    time.sleep(0.05)
t0 = time.perf_counter()
window.timeline.draw_timeline(window.current_date)
app.processEvents()
took = time.perf_counter() - t0
rows = window.table.rowCount()
print(f"Tagesliste: {rows} Zeilen in {took:.2f} s")
if rows < 150 or took > 2:
    print(f"::error title=Tagesliste::{rows} Zeilen brauchen {took:.1f} s (erlaubt: 2 s)")
    sys.stdout.flush()
    os._exit(1)
print("Tagesliste schnell genug")
sys.stdout.flush()
os._exit(0)
