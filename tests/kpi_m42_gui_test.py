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
assert not kpi.bar_m42.isVisibleTo(kpi) and kpi.percent.text() == "28 %"  # ohne Matrix42 nur grün

w.show_numbers(dict(data, m42_s=15 * 60))
app.processEvents()
assert kpi.bar_m42.isVisibleTo(kpi) and kpi.bar_m42.value() == 60 and kpi.percent_m42.text() == "60 %"
assert kpi.bar.value() == 28 and kpi.value.text() == "0:07 h"
assert "Matrix42 gebucht 0:15 h" in kpi.toolTip()
assert kpi.sizeHint() == size, (kpi.sizeHint(), size)  # Kachel nicht größer
print("Kachel Erfasst/Matrix42: OK")
sys.stdout.flush()
os._exit(0)
