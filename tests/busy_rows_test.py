"""Ladeanzeige oben (Logs, 3CX, ITM, KI) und ein-/ausblendbare Zeilen der Timeline."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

import main_timeline  # noqa: E402
from PySide6.QtCore import QDate  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from timeline_only import TIMELINE_ROWS  # noqa: E402


class FakeReader:
    def __init__(self, busy, first=False):
        self._busy, self._first = busy, first
        self.needs_login = False
        self.status = "Test"

    def busy(self):
        return self._busy

    def first_load(self):
        return self._first

    def health(self):
        return ("busy" if self._busy else "ok"), "lädt …"

    def day(self, _date):
        return None


app = QApplication(sys.argv)
app.setStyle(main_timeline.AppStyle())
window = main_timeline.TimelineApp()
window.show()
bar = window.busy_bar


def settle(ms=50):
    end = main_timeline.time.monotonic() + ms / 1000
    while main_timeline.time.monotonic() < end:
        app.processEvents()


# ---- Ladeanzeige (erst das Einlesen der Logs beim Start abwarten)
for _ in range(200):
    settle()
    if window.timeline._tv_index is not None and not window.timeline.loading:
        break
window.update_busy_bar()
settle()
assert bar.isHidden(), "ohne Laden keine Anzeige"

# Erster Start von 3CX: sofort sichtbar, mit Namen
window.pbx_reader = FakeReader(True, first=True)
window.update_busy_bar()
settle()
assert bar.isVisible() and "3CX" in bar.label.text(), bar.label.text()

# Kurzes Lesen im Hintergrund: erst nach Verzögerung (kein Flackern)
window.pbx_reader = None
window.update_busy_bar()
settle()
assert bar.isHidden()
window.itm_reader = FakeReader(True)
window.update_busy_bar()
settle(100)
assert bar.isHidden(), "kurzes Hintergrund-Lesen darf nicht sofort aufblitzen"
settle(1700)
assert bar.isVisible() and "ITM" in bar.label.text(), bar.label.text()

# KI: sofort, mit Tag
window.itm_reader = None
window._ai_busy.add("2026-10-19")
window.update_busy_bar()
settle()
assert bar.isVisible() and "KI-Vorschläge" in bar.label.text() and "19.10." in bar.label.text()
window.on_ai_finished("2026-10-19", 0, 0.0)  # fertig: Anzeige weg
settle()
assert bar.isHidden() and not window._ai_busy

# ---- Zeilen der Timeline
assert set(window.row_actions) == {k for k, _t in TIMELINE_ROWS}, window.row_actions.keys()
day = QDate(2026, 10, 19)
window.timeline.activities.extend([
    {"start": "2026-10-19 09:00:00", "end": "2026-10-19 09:30:00", "type": "Telefonat",
     "customer_name": "A"},
    {"start": "2026-10-19 10:00:00", "end": "2026-10-19 11:00:00", "type": "RDP-Verbindung",
     "customer_name": "B"},
])
window.date_edit.setDate(day)
settle()


def legend():
    window.timeline.draw_timeline(day)
    return [name for _y, _h, name, _c in window.timeline._legend]


names = legend()
assert "Telefon" in names and "Remote / Weitere" in names, names
for key in ("call", "vpn", "tv", "other"):
    window.row_actions[key].setChecked(False)
names = legend()
assert not {"Telefon", "VPN", "TeamViewer", "Remote / Weitere"} & set(names), names
assert not window.timeline._day_entries, "ausgeblendete Zeilen dürfen nichts zeichnen"
assert len(window.list_entries) >= 2, "Tagesliste bleibt vollständig"
window.row_actions["doc"].setChecked(False)
assert "Dokumentation" not in legend()
window.show_all_rows()
names = legend()
assert {"Dokumentation", "Telefon", "VPN", "TeamViewer", "Remote / Weitere"} <= set(names), names
assert all(window.config["timeline_rows"][k] for k, _t in TIMELINE_ROWS)

window.quit_app()
print("Ladeanzeige und Zeilen ok")
sys.stdout.flush()
