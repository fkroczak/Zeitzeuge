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
from PySide6.QtCore import QPoint  # noqa: E402
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

# „Nach Kunde“: Chips in höchstens zwei Zeilen, Rest im letzten Chip, Ansprechperson nur im Tooltip
chips = window.day_summary.customers.value
names = [("Jugendhilfe Olsberg - Jörg Spiekermann", 4440)] + [(f"Kunde {i:02d} GmbH", 600 - i) for i in range(12)]
chips.set_customers(names, "leer")
widths = []
for width in (1400, 700):  # Fensterbreite: die Kachel bekommt ihren Platz vom Layout
    window.resize(width, window.height())
    app.processEvents()
    widths.append(chips.width())
    parts = chips.parts()
    assert parts[0] == "Jugendhilfe Olsberg 1:14", parts
    shown = [c for c in chips._chips if c.isVisible()]
    rows = {c.y() for c in shown}
    assert len(rows) <= 2 and all(c.geometry().right() < chips.width() for c in shown), \
        (width, chips.width(), [(c.accessibleName(), c.geometry().getRect()) for c in shown])
    assert parts[-1].startswith("+") and "weitere" in parts[-1], parts
assert widths[1] < widths[0], widths
assert "Jörg Spiekermann" in shown[0].toolTip()
# Klick auf einen Chip filtert die Tagesliste, zweiter Klick hebt den Filter auf
window.date_edit.setDate(window.date_edit.date().addDays(1))  # zurück auf heute (30 Verbindungen)
end = time.time() + 20
while time.time() < end and (window.timeline.loading or not window.list_entries):
    app.processEvents()
before = len(window.list_entries)
assert before, "Tagesliste hat Einträge"
chips.set_customers(names, "leer")
seen = []
window.day_summary.customer_clicked.connect(seen.append)
chips._chips[0].clicked.emit()
assert seen == ["Jugendhilfe Olsberg - Jörg Spiekermann"], seen
assert window.customer_filter == seen[0] and window.list_entries == []
assert window.view_chips.filter_chip.isVisibleTo(window.view_chips)
assert chips._chips[0].property("on") is True
window.view_chips.filter_chip.click()
assert window.customer_filter == "" and len(window.list_entries) == before
assert not window.view_chips.filter_chip.isVisibleTo(window.view_chips)
from app_daylist import customer_matches
assert customer_matches({"customer_name": "Jugendhilfe Olsberg"}, "Jugendhilfe Olsberg - Jörg Spiekermann")
assert customer_matches({"customer_name": ""}, "ohne Kunde")
assert not customer_matches({"customer_name": "ITM"}, "WiRoPa GmbH")
# Timeline: Balken unter der Maus über dem Nebel, beim Verlassen ist alles wieder normal
tl = window.timeline
bar = next(iter(tl.activity_rects))
z_before = bar.zValue()
assert timeline_only.hover_style({}) == timeline_only.HOVER_STYLES["glow"], "Standard: nur Leuchten"
tl.config["hover_focus"] = "cone"
tl._focus_block(bar)
assert tl._fog.isVisible() and bar.zValue() > tl._fog.zValue() > z_before
others = [r for r in tl.activity_rects if r is not bar]
assert all(r.zValue() < tl._fog.zValue() for r in others)
tl._focus_block(None)
assert not tl._fog.isVisible() and bar.zValue() == z_before and tl._focused is None
assert bar.graphicsEffect() is None
# Hervorhebung wählbar: Aus = kein Nebel, Nur Leuchten = kein Nebel aber Leuchten, Eigene = Regler
tl.config["hover_focus"] = "off"
tl._focus_block(bar)
assert not tl._fog.isVisible() and bar.graphicsEffect() is None and bar.zValue() == z_before
tl._focus_block(None)
tl.config["hover_focus"] = "glow"
tl._focus_block(bar)
assert not tl._fog.isVisible() and bar.graphicsEffect() is not None
tl._focus_block(None)
tl.config["hover_focus"] = "custom"
tl.config["hover_custom"] = {"fog": 80, "cone": 0, "glow": 0, "outline": False}
pen_before = bar.pen()
tl._focus_block(bar)
assert tl._fog.isVisible() and tl._fog.brush().color().alpha() == 204 and bar.graphicsEffect() is None
assert bar.pen() == pen_before
tl._focus_block(None)
tl.config.pop("hover_focus")
tl.config.pop("hover_custom")
# Timeline-Tooltip: lange Zeilen werden umbrochen, der Hinweis bleibt im sichtbaren Bereich
tl.tooltip.setText("Beschreibung " * 80)
tl._move_tooltip(QPoint(tl.width() - 5, 5))
screen = tl.screen().availableGeometry()
assert tl.tooltip.width() <= tl.TIP_MAX_W and screen.contains(tl.tooltip.geometry())
tl.tooltip.hide()
chips.set_customers([], "leer")
assert chips.empty_label.isVisible() and not chips.parts()
print("OK")
window.quit_app()
sys.stdout.flush()
import safe_io  # Ende ohne Qt-Aufräumen (Absturz unter Windows)
safe_io.hard_exit(0)
