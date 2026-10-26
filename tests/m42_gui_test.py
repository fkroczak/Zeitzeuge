"""Matrix42 im Hauptfenster: Zeile "Matrix42", Lücken ohne Buchung, Statuszeile, Liste."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

import main_timeline  # noqa: E402
import m42_data  # noqa: E402
from PySide6.QtCore import QDate  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from timeline_only import entry_menu_items, type_label  # noqa: E402

D = "2026-10-19"


class FakeM42:
    NAME = "Matrix42"
    needs_login = False
    status = "Matrix42 gelesen 12:00"
    stopped = False

    def __init__(self):
        self.wanted = []
        events = [{"date": D, "time": t, "title": title, "description": "TE1"} for t, title in [
            ("08:10 - 08:55", "Systems - TCK0000049374 - Praktikanten / Azubi Oktober 2026"),
            ("09:10 - 12:00", "Kropff - TCK0000049378 - Salto"),
            ("12:30 - 16:00", "A.Fasselt Engineering GmbH  - TCK0000049191 - Netscaler"),
        ]]
        self.days = m42_data.bookings_by_day([D], events)

    def day(self, d):
        return self.days.get(d)

    def want(self, d):
        self.wanted.append(d)

    def health(self):
        return "ok", "12:00"

    def busy(self):
        return False

    def first_load(self):
        return False

    def stop(self):
        pass


app = QApplication(sys.argv)
app.setStyle(main_timeline.AppStyle())
window = main_timeline.TimelineApp()
window.show()
window.config["work_days"]["Mo"] = "08:00-17:00"
window.m42_reader = FakeM42()
# Verbindung ohne Buchung (17:00–17:30 nach Feierabend) und eine gebuchte
window.timeline.activities.extend([
    {"start": f"{D} 17:00:00", "end": f"{D} 17:30:00", "type": "TeamViewer", "customer_name": "X"},
    {"start": f"{D} 13:00:00", "end": f"{D} 14:00:00", "type": "RDP-Verbindung", "customer_name": "Y"},
])
window.date_edit.setDate(QDate.fromString(D, "yyyy-MM-dd"))
app.processEvents()
assert D in window.m42_reader.wanted, "beim Blättern Woche nachlesen"

band = window.m42_band(D)
booked = [e for e in band if e.get("m42")]
missing = [(e["start"][11:16], e["end"][11:16]) for e in band if e.get("m42_gap")]
assert len(booked) == 3 and booked[0]["customer_name"] == "Systems", booked
assert missing == [("08:00", "08:10"), ("08:55", "09:10"), ("12:00", "12:30"), ("16:00", "17:00")], missing

window.timeline.draw_timeline(window.current_date)
names = [n for _y, _h, n, _c in window.timeline._legend]
assert "Matrix42" in names, names
assert any(k == "m42" for k, _t, _e in window.timeline._bands)

text = window.info_label.text()
assert "Matrix42 gebucht 7:05 h" in text and "nicht gebucht 1:55 h" in text, text
assert "1 Verbindung ohne Buchung" in text, text

unbooked = window.m42_unbooked(D)
assert len(unbooked) == 1 and type_label(unbooked[0]) == "Nicht gebucht: TeamViewer", unbooked

gap = next(e for e in band if e.get("m42_gap"))
assert entry_menu_items(gap)[0][1] == "add_at" and "08:00" in entry_menu_items(gap)[0][0]
assert [i[1] for i in entry_menu_items(booked[0]) if i] == ["details", "copy"]

# Liste: Ansicht "Matrix42-Abgleich"
window.change_view("m42")
types = [type_label(e) for e in window.list_entries]
assert types.count("Nicht gebucht") == 4 and "Nicht gebucht: TeamViewer" in types, types
assert window.table.rowCount() == len(window.list_entries) == 8

# Zeile ausblenden
window.row_actions["m42"].setChecked(False)
assert "Matrix42" not in [n for _y, _h, n, _c in window.timeline._legend]

# Ohne gelesene Daten: nichts behaupten
window.m42_reader.days = {}
assert window.m42_band(D) == [] and window.m42_summary(D) == ""

window.change_view("grouped")
window.m42_reader = None
window.quit_app()
print("Matrix42 im Hauptfenster ok")
sys.stdout.flush()
