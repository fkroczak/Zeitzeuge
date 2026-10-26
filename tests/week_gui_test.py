"""Wochenabschluss im Hauptfenster: Statuszeile, Dialog, Prüfung bei Feierabend, „kommt bald“."""
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

import main_timeline  # noqa: E402
import week_dialogs  # noqa: E402
from PySide6.QtCore import QDate  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from timeline_only import entry_menu_items  # noqa: E402

D = "2026-10-19"   # Montag
TUE = "2026-10-20"


def stamp(day, *pairs):
    return {"zeiten": [{"start": f"{day} {a}:00", "end": f"{day} {b}:00" if b else None}
                       for a, b in pairs]}


def bk(day, a, b, customer="Kunde", ticket="TCK1"):
    return {"start": f"{day} {a}:00", "end": f"{day} {b}:00", "customer": customer,
            "ticket": ticket, "subject": "", "entry": ""}


class FakeM42:
    NAME = "Matrix42"
    needs_login = False
    status = "Matrix42 gelesen"
    stopped = False

    def __init__(self, days):
        self.days = days
        self.wanted = []

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


class FakeTray:
    def __init__(self):
        self.messages = []

    def showMessage(self, title, text, *_args):
        self.messages.append((title, text))

    def setIcon(self, *_a):
        pass

    def setToolTip(self, *_a):
        pass

    def hide(self):
        pass


app = QApplication(sys.argv)
app.setStyle(main_timeline.AppStyle())
window = main_timeline.TimelineApp()
window.show()
window.config["work_days"]["Mo"] = "08:00-17:00"
window.config["work_days"]["Di"] = "08:00-17:00"

# Montag: 8 h gestempelt mit Pause, 7 h gebucht (87,5 %). Dienstag: 8 h, 5:20 h gebucht (67 %),
# eine Buchung nach dem Ausstempeln. Mittwoch: gestempelt, Matrix42 nicht gelesen.
personal = {
    D: stamp(D, ("08:00", "12:00"), ("12:30", "16:30")),
    TUE: stamp(TUE, ("08:00", "12:00"), ("12:30", "16:30")),
    "2026-10-21": stamp("2026-10-21", ("08:00", "12:00"), ("12:30", "16:30")),
}
window.personal_day_for = lambda d: personal.get(d)
m42 = {D: [bk(D, "08:00", "12:00"), bk(D, "12:30", "15:30")],
       TUE: [bk(TUE, "08:00", "10:00"), bk(TUE, "10:40", "12:00"), bk(TUE, "13:00", "14:00"),
             bk(TUE, "16:30", "17:30", "Spät GmbH")]}
window.m42_reader = FakeM42(m42)
now = datetime(2026, 10, 23, 18, 0)

# Dialog: Woche vom 19.10., Tage mit Quote und Hinweisen
dialog = week_dialogs.WeekDialog(window, D, now=now)
assert dialog.rows == ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"], dialog.rows
quote = dialog.table.item(0, 3).text()
assert quote.startswith("88 %") and "Ziel erreicht" in quote, quote
quote = dialog.table.item(1, 3).text()
assert quote.startswith("67 %") and "unter Ziel" in quote, quote
assert "nicht gelesen" in dialog.table.item(2, 3).text()
hints = [dialog.hints.item(i).text() for i in range(dialog.hints.count())]
assert "Dienstag: 3:40 h nicht gebucht" in hints, hints
assert any(h.startswith("Dienstag: Buchung 16:30–17:30 (Spät GmbH · TCK1)") for h in hints), hints
assert "Mittwoch: Matrix42 nicht gelesen" in hints, hints
text = dialog.seven_label.text()
# 7-Tage: Mo + Di zählen (16 h Personalzeit, 12:20 h gebucht), Mi ohne Matrix42-Daten
assert "77 %" in text and "21.10." in text and "Ohne Matrix42-Daten" in text, text
assert not dialog.book_button.isEnabled() and "Kommt bald" in dialog.book_button.toolTip()
assert not dialog.next_button.isEnabled(), "Zukunft nicht blättern"
dialog.move_week(-1)
assert dialog.rows[0] == "2026-10-12" and "2026-10-12" in window.m42_reader.wanted
dialog.move_week(1)
# Ziel ändern: Dienstag bleibt gelb, Montag wird mit 90 % Ziel gelb
dialog.target_spin.setValue(90)
assert window.config["booking_target_percent"] == 90
assert "unter Ziel (90 %)" in dialog.table.item(0, 3).text()
dialog.target_spin.setValue(80)
# Enter / Doppelklick springt zum Tag
dialog.open_day(1)
assert window.current_date.toString("yyyy-MM-dd") == TUE

# Statuszeile: heute und 7 Tage (mit echten heutigen Daten)
today = datetime.now()
t = today.strftime("%Y-%m-%d")
y = (today - timedelta(days=1)).strftime("%Y-%m-%d")
saved = dict(personal), dict(m42)
personal.clear()
m42.clear()
personal[y] = stamp(y, ("08:00", "12:00"), ("12:30", "16:30"))
m42[y] = [bk(y, "08:00", "10:00")]  # 25 % -> rot
window.update_status_text()
button = window.rate_button
assert not button.isHidden(), "Quote in der Statuszeile fehlt"
assert button.text().startswith("7 Tage 25 %") and "✗" in button.text(), button.text()
personal[t] = stamp(t, ("00:00", None))  # heute eingestempelt, noch nichts gebucht
m42[t] = []
window.update_status_text()
assert button.text().startswith("Quote heute 0 % · 7 Tage"), button.text()
personal.clear()
m42.clear()
personal.update(saved[0])
m42.update(saved[1])
assert button.objectName() == "rate_low" and "Wochenabschluss" in button.accessibleName()
window.m42_reader = None
saved_imported, window.imported = window.imported, None
window.update_status_text()
assert button.isHidden(), "ohne Matrix42 keine Quote"
window.imported = saved_imported
window.m42_reader = FakeM42(m42)

# Rechtsklick auf eine Tätigkeit: „In Matrix42 buchen“ sichtbar, aber deaktiviert
doc = {"doc": True, "doc_item": {"start": f"{D} 08:00:00", "end": f"{D} 09:00:00"},
       "start": f"{D} 08:00:00", "end": f"{D} 09:00:00"}
items = [i for i in entry_menu_items(doc) if i]
book = [i for i in items if i[1] == "m42_book"]
assert book and book[0][2] is False and "kommt bald" in book[0][0], items

# Prüfung bei Feierabend: Montag 18:00, ausgestempelt um 16:30, PC danach noch aktiv
window.tray = FakeTray()
window.timeline.pc_entries_for = lambda date, min_seconds=30, max_gap=60: [
    {"start": f"{D} 16:40:00", "end": f"{D} 17:20:00"}] if date.toString("yyyy-MM-dd") == D else []
mon_evening = datetime(2026, 10, 19, 18, 0)
window._reminded_day = None
window.end_of_day_reminder([], datetime(2026, 10, 19, 16, 45))  # vor dem geplanten Ende: nichts
assert window.tray.messages == []
window.end_of_day_reminder([], mon_evening)
assert len(window.tray.messages) == 1, window.tray.messages
title, text = window.tray.messages[0]
assert title == "Feierabend: bitte prüfen" and "aber ausgestempelt" in text, text
window.end_of_day_reminder([], mon_evening)
assert len(window.tray.messages) == 1, "nur einmal am Tag"
# mit offenen Tätigkeiten: bisherige Meldung bleibt, Befunde kommen dazu
window._reminded_day = None
window.end_of_day_reminder([{"x": 1}, {"x": 2}], mon_evening)
title, text = window.tray.messages[-1]
assert title == "Feierabend: noch nicht alles dokumentiert", title
assert text.startswith("Heute sind noch 2 Tätigkeiten offen.") and "Außerdem:" in text, text
# abgeschaltet: wieder nur die bisherige Erinnerung, ohne offene Tätigkeiten gar nichts
window.config["day_checks_enabled"] = False
window._reminded_day = None
count = len(window.tray.messages)
window.end_of_day_reminder([], mon_evening)
assert len(window.tray.messages) == count
window.end_of_day_reminder([{"x": 1}], mon_evening)
assert "Außerdem" not in window.tray.messages[-1][1]
window.config["day_checks_enabled"] = True

# Einstellung im Dialog „Nachfragen und Erinnerungen“
import journal_dialogs  # noqa: E402
prompt = journal_dialogs.DocPromptDialog(window.config, window)
prompt.day_checks.setChecked(False)
prompt.apply()
assert window.config["day_checks_enabled"] is False

window.tray = None
window.m42_reader = None
window.quit_app()
print("Wochenabschluss ok")
sys.stdout.flush()
os._exit(0)
