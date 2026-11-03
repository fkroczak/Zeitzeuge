"""Tagesabschluss im Hauptfenster: Vorschläge zeigen, ändern, dokumentieren, nacheinander buchen.

Ohne Browser: ein nachgebauter Leser beantwortet die Buchungen wie M42Reader (m42_booking_gui_test.py).
"""
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

D = "2026-10-19"  # Montag


def wait(app, condition, seconds=5):
    import time
    end = time.time() + seconds
    while time.time() < end and not condition():
        app.processEvents()
        time.sleep(0.01)
    return condition()


def gui_test():
    global app, window
    from datetime import datetime, timedelta

    import main_timeline
    from PySide6.QtCore import QObject, Qt, QTimer, Signal
    from PySide6.QtWidgets import QApplication

    import day_close
    import day_close_dialog

    app = QApplication(sys.argv)
    window = main_timeline.TimelineApp()

    # 1. Echte Rechnung mit den Daten des Hauptfensters: läuft auch an einem leeren Tag
    window.journal.add({"start": f"{D} 08:00:00", "end": f"{D} 08:30:00", "customer": "Systems",
                        "category": "Fernwartung", "text": "Server geprüft", "ticket": "TCK0000000001"})
    real = window.day_close_plan(D)
    assert real["rows"] and real["rows"][0]["kind"] == "doc", real["rows"][:1]
    assert real["rows"][0]["ticket"] == "TCK0000000001"

    class FakeReader(QObject):
        booking_done = Signal(object)
        activity_types_loaded = Signal(object)
        tickets_found = Signal(object)
        NAME = "Matrix42"
        needs_login = False
        status = "Matrix42 gelesen"
        activity_types = []

        def __init__(self):
            super().__init__()
            self.requests, self.booking, self.busy_once = [], False, True

        def health(self):
            return "ok", ""

        def stop(self):
            pass

        def day(self, d):
            return [{"start": f"{D} 12:00:00", "end": f"{D} 12:30:00", "ticket": "TCK0000000009",
                     "subject": "Schon gebucht"}]

        def want(self, d):
            pass

        def load_activity_types(self):
            self.activity_types_loaded.emit([(10, "Administration")])

        def search_tickets(self, text, ticket_list=None):
            pass

        def book(self, request):
            if self.busy_once:  # einmal „bucht gerade“: der Abschluss wartet und versucht es erneut
                self.busy_once = False
                return False
            self.requests.append(request)
            n = len(self.requests)
            QTimer.singleShot(20, lambda: self.booking_done.emit(
                {"ok": True, "entry": f"TE00000000{n:02d}", "request": request}))
            return True

    reader = FakeReader()
    window.m42_reader = reader
    day_close_dialog.RETRY_MS = 30

    # 2. Vorschläge aus nachgebauten Spuren: A mit Ticket aus dem Fenstertitel, B ohne Ticket,
    #    dazwischen freie Zeit
    day = datetime(2026, 10, 19)

    def conn(a, b, name):
        return {"start": f"{D} {a}:00", "end": f"{D} {b}:00", "type": "RDP-Sitzung", "customer_name": name}

    def fake_plan(date_str, now=None):
        evidence = [(1, conn("09:00", "09:07", "Kanzlei - DC01")), (1, conn("09:07", "10:00", "Müller - srv")),
                    (1, conn("11:00", "11:50", "Kanzlei - DC02"))]
        return day_close.build(
            date_str, [(day.replace(hour=8), day.replace(hour=13))],
            [i for i in window.journal.items(date_str)], evidence, reader.day(date_str),
            hint=lambda e: (e["customer_name"].split(" - ")[0], "Fernwartung"),
            ticket_for=lambda s, e: ("TCK0000000002", "Outlook") if s.hour in (9, 11) and s.minute == 0 else ("", ""))

    window.day_close_plan = fake_plan
    seen = {}

    def drive():
        dialog = next(w for w in app.topLevelWidgets()
                      if isinstance(w, day_close_dialog.DayCloseDialog) and w.isVisible())
        rows = dialog.rows
        seen["rows"] = [(r["kind"], r["start"][11:16], r["end"][11:16], r["customer"], r["ticket"]) for r in rows]
        seen["summary_before"] = dialog.summary.text()
        # Müller hat kein Ticket: in der Tabelle eintragen (klein geschrieben wird normalisiert)
        mueller = next(i for i, r in enumerate(rows) if r["customer"] == "Müller")
        dialog.table.item(mueller, day_close_dialog.COL_TICKET).setText("tck0000000003")
        seen["mueller_ticket"] = rows[mueller]["ticket"]
        # freie Zeit: bleibt ohne Haken
        seen["gap_checked"] = [r["checked"] for r in rows if r["kind"] == "gap"]
        dialog.book_button.click()
        seen["finished"] = wait(app, lambda: not dialog.busy() and "Fertig" in dialog.status.text())
        seen["status"] = dialog.status.text()
        seen["notes"] = [dialog.table.item(i, day_close_dialog.COL_NOTE).text() for i in range(len(rows))]
        seen["summary_after"] = dialog.summary.text()
        dialog.reject()

    QTimer.singleShot(200, drive)
    window.show_day_close(D)

    assert ("doc", "08:00", "08:30", "Systems", "TCK0000000001") in seen["rows"], seen["rows"]
    assert ("draft", "09:00", "10:00", "Müller", "") in seen["rows"] or any(
        r[3] == "Müller" for r in seen["rows"]), seen["rows"]
    assert seen["mueller_ticket"] == "TCK0000000003", seen
    assert seen["gap_checked"] and not any(seen["gap_checked"]), seen
    assert seen["finished"], seen["status"]
    tickets = [r["ticket"] for r in reader.requests]
    assert "TCK0000000001" in tickets and "TCK0000000003" in tickets and "TCK0000000002" in tickets, tickets
    # Abrechnungstakt: keine Überschneidung zwischen den eigenen Buchungen
    spans = sorted((r["start"], r["end"]) for r in reader.requests)
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), spans
    assert "in Matrix42 gebucht" in seen["status"], seen["status"]
    assert any(n.startswith("✓ gebucht TE") for n in seen["notes"]), seen["notes"]
    items = window.journal.items(D)
    assert len(items) >= 3 and all(i.get("m42_entry") for i in items), items
    assert all(i.get("source") == "Tagesabschluss" for i in items if i["start"][11:16] != "08:00")
    # beantwortet: Nachfragen zu dieser Zeit kommen nicht mehr
    assert all(isinstance(i.get("answered"), dict) for i in items if i.get("source") == "Tagesabschluss")

    # 3. Noch einmal öffnen: Gebuchtes steht nicht mehr da, nur die freie Zeit
    again = fake_plan(D)
    assert all(r["kind"] == "gap" for r in again["rows"]), again["rows"]
    assert again["percent_now"] == 60, again  # 3 von 5 h gebucht

    # 4. Ohne Matrix42: nur dokumentieren, Buchen-Knopf aus
    window.m42_reader = None
    D2 = "2026-10-20"

    def plan2(date_str, now=None):
        return day_close.build(date_str, [(day.replace(day=20, hour=8), day.replace(day=20, hour=9))], [],
                               [(1, {"start": f"{D2} 08:00:00", "end": f"{D2} 09:00:00", "type": "TeamViewer",
                                     "customer_name": "Beta"})])
    window.day_close_plan = plan2

    def drive2():
        dialog = next(w for w in app.topLevelWidgets()
                      if isinstance(w, day_close_dialog.DayCloseDialog) and w.isVisible())
        seen["book_enabled"] = dialog.book_button.isEnabled()
        dialog.doc_button.click()
        seen["status2"] = dialog.status.text()
        dialog.reject()

    QTimer.singleShot(200, drive2)
    window.show_day_close(D2)
    assert seen["book_enabled"] is False, seen
    assert "1 dokumentiert" in seen["status2"], seen
    assert [i["customer"] for i in window.journal.items(D2)] == ["Beta"]

    # 5. Hinweis für die Meldung bei Feierabend
    window.day_close_plan = fake_plan
    assert window.day_close_hint(D) == ""  # alles gebucht, nur freie Zeit übrig
    window.day_close_plan = lambda d, now=None: day_close.build(
        d, [(day.replace(hour=14), day.replace(hour=15))], [],
        [(1, {"start": f"{D} 14:00:00", "end": f"{D} 15:00:00", "type": "TeamViewer", "customer_name": "Gamma"})])
    assert "1 Vorschlag" in window.day_close_hint(D) and "100 %" in window.day_close_hint(D)
    window.config["day_close_end_of_day"] = False
    assert window.day_close_hint(D) == ""
    assert Qt and timedelta
    window.quit_app()


try:
    gui_test()
except BaseException:
    traceback.print_exc(file=sys.stdout)
    sys.stdout.flush()
    os._exit(1)
print("Tagesabschluss ok")
sys.stdout.flush()
os._exit(0)
