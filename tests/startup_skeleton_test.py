"""Start: Umrisse sofort, Logs im Hintergrund, der Tag wird genau einmal gezeichnet.

Prüft außerdem, dass die Tagesliste ihre Spaltenbreiten mit fit_text genauso misst wie mit
den vollen Zellen (make_row). Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
data = tempfile.mkdtemp()
os.environ["ZEITZEUGE_DATA"] = data

today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
tv = os.path.join(data, "Connections.txt")
with open(tv, "w", encoding="utf-8") as f:
    for i in range(30):
        s = today + timedelta(hours=8, minutes=15 * i)
        e = s + timedelta(minutes=10)
        f.write(f"{100000 + i}\t{s:%d-%m-%Y %H:%M:%S}\t{e:%d-%m-%Y %H:%M:%S}\tdemo\tRemoteControl\t{{x}}\n")
with open(os.path.join(data, "zeitzeuge_config.json"), "w", encoding="utf-8") as f:
    json.dump({"teamviewer_paths": [tv], "rdm_paths": [], "setup_done": True,
               "teamviewer_utc_auto": False, "teamviewer_timezone_correction": 0,
               "tracking_enabled": False}, f)

import main_timeline  # noqa: E402
import skeleton  # noqa: E402
import timeline_only  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

draws = []
_orig = timeline_only.TimelineView.draw_timeline


def counting(self, date):
    draws.append(self._tv_index is not None)  # True = mit gelesenen Logs gezeichnet
    return _orig(self, date)


timeline_only.TimelineView.draw_timeline = counting

app = QApplication(sys.argv)
window = main_timeline.TimelineApp()
tl = window.timeline

# Vor dem ersten Zeichnen: Umrisse in Timeline, Tagesliste und Kacheln, Zeitgeber läuft
assert tl._skeleton and window.table._skeleton, "Umrisse fehlen"
assert window.day_summary.booked.placeholder is not None
assert not window.day_summary.booked.value.isVisibleTo(window.day_summary.booked)
assert skeleton.pulse().watching() >= 3, skeleton.pulse().watching()
assert not draws, "vor dem Zeigen schon gezeichnet"

window.show()
end = time.time() + 10
while time.time() < end and (tl.loading or tl._tv_index is None or not draws):
    app.processEvents()
    time.sleep(0.005)
for _ in range(20):
    app.processEvents()
    time.sleep(0.005)

assert draws == [True], f"beim Start genau einmal und mit den Logs zeichnen, war: {draws}"
assert not tl._skeleton and not window.table._skeleton, "Umrisse nach dem Zeichnen noch da"
assert window.day_summary.booked.placeholder is None
assert window.day_summary.booked.value.isVisibleTo(window.day_summary.booked)
tv_rows = [r for r in range(window.table.rowCount()) if "TeamViewer" in window.table.item(r, 3).text()]
assert len(tv_rows) >= 10, window.table.rowCount()
print(f"Start: einmal gezeichnet, {window.table.rowCount()} Zeilen")

# fit_text misst dieselben Texte wie die Zellen
model = window.table.list_model
assert model.fit_text is not None
for row, entry in enumerate(model.entries):
    cells = model.cells(row)
    fit = model.fit_text(entry)
    for col in window.table.fit_columns:
        assert fit[col] == cells[col].text(), (row, col, fit[col], cells[col].text())
print("Spaltenbreiten: fit_text = Zellen")

# Ohne Skeleton-Rest: weitere Tage zeichnen ganz normal
draws.clear()
window.date_edit.setDate(window.date_edit.date().addDays(-1))
app.processEvents()
assert draws, "Tageswechsel zeichnet"
assert skeleton.pulse().watching() == 0, "Zeitgeber der Umrisse läuft noch"
print("OK")
window.quit_app()
sys.stdout.flush()
import safe_io  # Ende ohne Qt-Aufräumen (Absturz unter Windows)
safe_io.hard_exit(0)
