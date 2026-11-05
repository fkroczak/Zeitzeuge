"""In Matrix42 buchen im Hauptfenster: Fenster, Ticketsuche, Buchen, Vermerk an der Tätigkeit.

Ohne Browser: ein nachgebauter Leser beantwortet Suche und Buchung wie M42Reader.
Den Weg über Edge prüft m42_test.py.
"""
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

D = "2026-10-19"


def gui_test():
    global app, window
    import main_timeline
    from PySide6.QtCore import QObject, QTimer, Signal
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

    import m42_booking_dialogs

    app = QApplication(sys.argv)
    window = main_timeline.TimelineApp()

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
            self.requests, self.searches, self.booking = [], [], False

        def health(self):
            return "ok", ""

        def stop(self):
            pass

        def day(self, d):
            return [{"start": f"{D} 08:15:00", "end": f"{D} 08:45:00", "ticket": "TCK0000000009",
                     "subject": "Schon gebucht"}]

        def want(self, d):
            pass

        def load_activity_types(self):
            self.activity_types_loaded.emit([(10, "Administration"), (30, "Consulting")])

        def search_tickets(self, text, ticket_list=None):
            self.searches.append(text)
            rows = [{"ticket": "TCK0000049374", "id": "t1", "subject": "Praktikanten",
                     "customer": "Systems", "state": "Neu", "initiator": "", "recipient": "", "created": ""}]
            self.tickets_found.emit({"text": text, "rows": rows, "error": ""})

        def book(self, request):
            self.requests.append(request)
            self.booking_done.emit({"ok": True, "entry": "TE0000099999", "request": request,
                                    "ticket": {"customer": "Systems"}})
            return True

    reader = FakeReader()
    window.m42_reader = reader
    item = window.journal.add({"start": f"{D} 08:00:00", "end": f"{D} 08:22:00", "customer": "Systems",
                               "category": "Fernwartung", "text": "Praktikanten betreut"})

    # Fenster: ohne Ticket sucht es gleich nach dem Kunden, ein Klick übernimmt das Ticket
    seen = {}

    def drive():
        dialog = next(w for w in app.topLevelWidgets()
                      if isinstance(w, m42_booking_dialogs.BookingDialog) and w.isVisible())
        app.processEvents()
        seen["search"] = list(reader.searches)
        seen["warning"] = dialog.warning.text()
        seen["times"] = (dialog.start_edit.time().toString("HH:mm"), dialog.end_edit.time().toString("HH:mm"))
        seen["types"] = [dialog.type_edit.itemText(i) for i in range(dialog.type_edit.count())]
        seen["book_before"] = dialog.book_button.isEnabled()
        dialog.take_ticket(dialog.results.item(0))
        dialog.type_edit.setCurrentIndex(dialog.type_edit.findData(30))
        seen["book_after"] = dialog.book_button.isEnabled()
        dialog.book_button.click()

    QTimer.singleShot(300, drive)
    assert window.book_in_m42(item) is True
    assert seen["search"] == ["Systems"], seen
    assert "schon gebucht" in seen["warning"] and "TCK0000000009" in seen["warning"], seen
    assert seen["times"] == ("08:00", "08:30"), seen  # Ende im 15-Minuten-Takt
    assert seen["types"] == ["Administration", "Consulting"], seen
    assert seen["book_before"] is False and seen["book_after"] is True, seen  # erst mit Ticket
    req = reader.requests[0]
    assert req["ticket"] == "TCK0000049374" and req["minutes"] == 30 and req["activity_type"] == 30
    saved = window.journal.items(D)[0]
    assert saved["m42_entry"] == "TE0000099999" and saved["ticket"] == "TCK0000049374", saved
    assert window.config["m42_activity_type"] == 30  # beim nächsten Mal vorbelegt

    # Schon gebucht: kein zweites Fenster, nur ein Hinweis
    QMessageBox.information = staticmethod(lambda *a, **k: seen.setdefault("info", a[2]))
    assert window.book_in_m42(saved) is None and "TE0000099999" in seen["info"]

    # Abbrechen bucht nichts
    other = window.journal.add({"start": f"{D} 10:00:00", "end": f"{D} 10:10:00", "text": "x",
                                "ticket": "TCK0000049374"})
    QTimer.singleShot(300, lambda: next(w for w in app.topLevelWidgets()
                                        if isinstance(w, m42_booking_dialogs.BookingDialog)
                                        and w.isVisible()).reject())
    assert window.book_in_m42(other) is None and len(reader.requests) == 1

    # Beim Dokumentieren: Knopf „Suchen …“ am Ticket öffnet die Matrix42-Suche
    from datetime import datetime
    from journal_dialogs import EntryDialog
    start, end = datetime(2026, 10, 19, 11, 0), datetime(2026, 10, 19, 11, 30)
    doc = EntryDialog(start, end, ["Systems"], ["Fernwartung"], customer="Systems",
                      **window.entry_form_options(start, end))
    assert doc.form.ticket_search_button is not None and doc.form.ticket_edit.isVisibleTo(doc)

    def pick():
        search = next(w for w in app.topLevelWidgets()
                      if isinstance(w, m42_booking_dialogs.TicketSearchDialog) and w.isVisible())
        app.processEvents()
        seen["doc_search"] = search.search_edit.text()
        seen["doc_rows"] = search.results.count()
        search.take_button.click()

    reader.searches.clear()
    QTimer.singleShot(300, pick)
    doc.form.ticket_search_button.click()
    assert seen["doc_search"] == "Systems" and seen["doc_rows"] == 1, seen
    assert reader.searches == ["Systems"], reader.searches
    assert doc.item()["ticket"] == "TCK0000049374", doc.item()
    doc.deleteLater()

    # Ohne Matrix42 kein Knopf
    window.m42_reader = None
    assert window.entry_form_options(start, end)["ticket_search"] is None
    window.m42_reader = reader
    assert QDialog  # (Import für den Typ oben)
    window.quit_app()


try:
    gui_test()
except BaseException:
    traceback.print_exc(file=sys.stdout)
    sys.stdout.flush()
    os._exit(1)
print("Matrix42 buchen ok")
sys.stdout.flush()
os._exit(0)
