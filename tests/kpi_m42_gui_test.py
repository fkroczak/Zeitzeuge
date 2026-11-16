"""Kachel „Erfasst“: grüner Balken selbst erfasst, blauer Balken in Matrix42 gebucht
(nur mit Matrix42). Die Kachel wird mit dem zweiten Balken nicht größer. Skript."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import day_summary  # noqa: E402

app = QApplication(sys.argv)
w = day_summary.DaySummary()
data = {"booked_s": 7 * 60, "target_s": 25 * 60, "target_basis": "bis jetzt", "open": 0, "suggestions": 0,
        "customers": []}
w.show_numbers(dict(data))
w.show()
app.processEvents()
kpi = w.booked
size = kpi.sizeHint()
assert not kpi.bar_m42.isVisibleTo(kpi) and kpi.percent.text() == "28 %" and kpi.value.text() == "0:07 h" and kpi.head.text() == "Erfasst"  # ohne Matrix42 nur grün

w.show_numbers(dict(data, m42_s=15 * 60))
app.processEvents()
assert kpi.bar_m42.isVisibleTo(kpi) and kpi.bar_m42.value() == 60 and kpi.percent_m42.text() == "60 %"
assert kpi.bar.value() == 28 and kpi.value.text() == "0:15 h"  # Zahl: Matrix42
assert kpi.head.text() == "In Matrix42 gebucht"
assert "Matrix42 gebucht 0:15 h" in kpi.toolTip()
assert kpi.sizeHint().width() <= size.width() + 4 and kpi.sizeHint().height() == size.height(), \
    (kpi.sizeHint(), size)  # Kachel nicht größer (Ziffern sind verschieden breit)
# Farben wie die Zeilen der Timeline: Neongrün ist als Schrift auf Weiß nicht lesbar
kpi.set_colors("#00FF00", "#2272AD", "#FFFFFF")
assert "#00FF00" in kpi.bar.styleSheet() and "#2272AD" in kpi.bar_m42.styleSheet()
assert "#00FF00" not in kpi.percent.styleSheet() and "#2272AD" in kpi.percent_m42.styleSheet()
assert kpi.sizeHint().height() == size.height()

# Im Hauptfenster: Zeilenfarbe ändern färbt die Kachel mit
import tempfile  # noqa: E402
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()
import main_timeline  # noqa: E402
from PySide6.QtWidgets import QSystemTrayIcon  # noqa: E402
QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
window = main_timeline.TimelineApp()
window.tray.showMessage = lambda *a: None
window.show()
app.processEvents()
window.set_row_color("doc", "#00FF00")
window.set_row_color("m42", "#7C4DCC")
for _ in range(20):
    app.processEvents()
app.processEvents()
booked = window.day_summary.booked
assert "#00FF00" in booked.bar.styleSheet().upper() and "#7C4DCC" in booked.bar_m42.styleSheet().upper(), \
    (booked.bar.styleSheet(), booked.bar_m42.styleSheet())
window.quit_app()  # Hintergrund-Threads stoppen, sonst bleibt der Prozess unter Windows hängen
print("Kachel Erfasst/Matrix42: OK")
import safe_io  # noqa: E402  Ende ohne Qt-Aufräumen (Absturz/Hänger unter Windows)
safe_io.hard_exit(0)
