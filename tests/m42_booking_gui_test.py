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
        my_tickets_loaded = Signal(object)
        NAME = "Matrix42"
        my_tickets = None
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

        def load_my_tickets(self):
            self.my_tickets = {"at": "10:42", "error": "", "rows": [
                {"ticket": "TCK0000000002", "id": "2", "subject": "Drucker", "customer": "Müller",
                 "state": "Neu", "initiator": "Huber, Max", "recipient": "Kroczak, Filip", "created": ""}]}
            self.my_tickets_loaded.emit(self.my_tickets)

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
    # Kulanz und Reise: Angaben erscheinen erst mit dem Haken, Reise wird vorbelegt
    form = doc.form
    assert not form.goodwill_panel.isVisibleTo(doc) and not form.travel_panel.isVisibleTo(doc)
    form.goodwill_box.setChecked(True)
    assert form.goodwill_panel.isVisibleTo(doc) and form.goodwill_minutes.value() == form._minutes()
    form.travel_guess = lambda a, b: {"there_km": 42, "back_km": 40, "label": "Hinfahrt 09:25–10:00"}
    form.travel_box.setChecked(True)
    details = form.flag_details()
    assert details["travel_km_there"] == 42 and details["travel_km_back"] == 40, details
    assert details["goodwill_reason"] == "Kulanz", details
    form.goodwill_box.setChecked(False)
    form.travel_box.setChecked(False)
    assert form.flag_details() == {}
    # Ticketfeld liegt hinter „+ Ticket“ (wie in der Nachfrage-Karte)
    assert doc.form.ticket_search_button is not None and not doc.ticket_row.isVisibleTo(doc)
    doc.ticket_add.click()
    assert doc.form.ticket_edit.isVisibleTo(doc) and doc.form.ticket_search_button.isVisibleTo(doc)

    def pick():
        search = next(w for w in app.topLevelWidgets()
                      if isinstance(w, m42_booking_dialogs.TicketSearchDialog) and w.isVisible())
        app.processEvents()
        seen["doc_search"] = search.search_edit.text()
        seen["doc_rows"] = search.results.rowCount()
        seen["new_button"] = search.new_button.isVisible() and search.new_button.isEnabled()
        search.take_button.click()

    reader.searches.clear()
    QTimer.singleShot(300, pick)
    doc.form.ticket_search_button.click()
    assert seen["doc_search"] == "Systems" and seen["doc_rows"] == 1, seen
    assert reader.searches == ["Systems"], reader.searches
    assert seen["new_button"], "Ticket suchen bietet „Neues Ticket …“ an"
    # Neu angelegtes Ticket wird wie ein Treffer übernommen, Kunde aus dem Melder
    row = m42_booking_dialogs.new_ticket_row({"ticket": "TCK0000050000", "id": "n1"},
                                             {"subject": "Drucker"}, {"name": "Huber, Max - Systems"})
    assert row["ticket"] == "TCK0000050000" and row["customer"] == "Systems" and row["subject"] == "Drucker"
    assert doc.item()["ticket"] == "TCK0000049374", doc.item()
    doc.deleteLater()

    # Aus dem Nachfrage-Fenster (immer im Vordergrund): Suche liegt darüber und sperrt
    # nur dieses Fenster, nicht das ganze Programm (sonst wirkt Zeitzeuge aufgehängt)
    from PySide6.QtCore import Qt
    from journal_dialogs import PromptWindow
    prompt = PromptWindow({"start": f"{D} 08:45:00", "end": f"{D} 11:09:00", "idle": True},
                          ["Systems"], ["Fernwartung"], parent=window,
                          **window.entry_form_options(start, end))
    prompt.show()

    def check_prompt_search():
        search = next(w for w in app.topLevelWidgets()
                      if isinstance(w, m42_booking_dialogs.TicketSearchDialog) and w.isVisible())
        seen["on_top"] = bool(search.windowFlags() & Qt.WindowStaysOnTopHint)
        seen["modality"] = search.windowModality()
        search.reject()

    QTimer.singleShot(300, check_prompt_search)
    prompt.form.ticket_search_button.click()
    assert seen["on_top"] and seen["modality"] == Qt.WindowModal, seen
    prompt._done = True
    prompt.close()
    prompt.deleteLater()

    # Direkt im Feld Ticket suchen: tippen, Treffer erscheinen darunter, Auswahl setzt die Nummer
    from PySide6.QtTest import QTest
    doc = EntryDialog(start, end, ["Systems"], ["Fernwartung"], **window.entry_form_options(start, end))
    doc.show()
    doc.ticket_add.click()
    form = doc.form
    reader.searches.clear()
    form.ticket_edit.lineEdit().textEdited.emit("Prakt")  # wie getippt
    form.ticket_edit.setEditText("Prakt")
    QTest.qWait(form.LOOKUP_DELAY_MS + 200)
    assert reader.searches == ["Prakt"], reader.searches
    assert form._lookup_model.rowCount() == 1, form._lookup_model.rowCount()
    assert "1 Ticket in Matrix42" in form.ticket_status.text(), form.ticket_status.text()
    form._pick_lookup(form._lookup_model.index(0, 0))
    QTest.qWait(20)
    assert form.ticket_edit.currentText() == "TCK0000049374"
    assert form.customer_edit.currentText() == "Systems", "Kunde aus dem Ticket, wenn leer"
    # Ticketnummer getippt: keine Suche
    reader.searches.clear()
    form.ticket_edit.setEditText("TCK0000049374")
    form.ticket_edit.lineEdit().textEdited.emit("TCK0000049374")
    QTest.qWait(form.LOOKUP_DELAY_MS + 100)
    assert reader.searches == [], reader.searches
    doc.close()
    doc.deleteLater()

    # Vorschlag aus dem Fenstertitel: Titel und Kunde aus Matrix42 dazu, Übernehmen setzt den Kunden
    reader.searches.clear()
    options = dict(window.entry_form_options(start, end),
                   ticket_suggestions=[{"ticket": "TCK0000049374", "seconds": 660, "sources": ["PC"],
                                        "label": "TCK0000049374 (PC, 11 min)"}])
    doc = EntryDialog(start, end, ["Systems"], ["Fernwartung"], **options)
    doc.show()
    form = doc.form
    QTest.qWait(50)
    assert reader.searches == ["TCK0000049374"], reader.searches
    assert form.ticket_take.text() == "Vorschlag: TCK0000049374 · Praktikanten · Systems (PC, 11 min)", \
        form.ticket_take.text()
    assert "Neu" in form.ticket_take.toolTip(), form.ticket_take.toolTip()
    form.customer_edit.setCurrentText("")
    form.ticket_take.click()
    assert form.ticket_edit.currentText() == "TCK0000049374"
    assert form.customer_edit.currentText() == "Systems"
    doc.close()
    doc.deleteLater()

    # Ohne Matrix42 kein Knopf
    window.m42_reader = None
    assert window.entry_form_options(start, end)["ticket_search"] is None
    assert window.entry_form_options(start, end)["ticket_lookup"] is None
    window.m42_reader = reader

    # Meine Tickets: Kachel über der Timeline, Klick öffnet die Liste
    tile = window.day_summary.tickets
    assert not tile.isVisibleTo(window)
    reader.my_tickets_loaded.connect(window.day_summary.show_my_tickets)
    window.show_my_tickets()  # liest beim ersten Öffnen
    app.processEvents()
    from tickets_dialogs import TicketsDialog
    mine = window._my_tickets_dialog
    assert isinstance(mine, TicketsDialog) and mine.table.rowCount() == 1
    cells = [mine.table.item(0, c).text() for c in range(mine.table.columnCount())]
    assert cells[:6] == ["TCK0000000002", "Drucker", "Müller", "Huber, Max", "", "Neu"], cells  # Art leer: ohne Sys-Entity
    mine.table.select_first()
    assert "1 offenes Ticket" in mine.status.text(), mine.status.text()
    assert tile.isVisibleTo(window) and tile.value.text() == "1" and "TCK0000000002" in tile.toolTip()
    mine.copy_button.click()
    assert app.clipboard().text() == "TCK0000000002"
    window.show_my_tickets()  # nur ein Fenster
    assert window._my_tickets_dialog is mine
    # Anordnung: Standard 1, über Ansicht → Ticketfenster umschaltbar (gespeichert, gilt sofort)
    assert mine.layout_no == 1
    window.ticket_layout_actions[3].trigger()
    assert window.config["ticket_layout"] == 3 and mine.layout_no == 3
    mine.choose_layout(2)  # Menü im Fenster: landet in der Einstellung
    assert window.config["ticket_layout"] == 2
    mine.pin("all", False)
    assert window.config["ticket_favorites"] == ["mine", "tk"]
    mine.close()
    window.day_summary.show_my_tickets(None)
    assert not tile.isVisibleTo(window)
    assert QDialog  # (Import für den Typ oben)
    window.quit_app()


try:
    gui_test()
except BaseException:
    traceback.print_exc(file=sys.stdout)
    sys.stdout.flush()
    import safe_io
    safe_io.hard_exit(1)
print("Matrix42 buchen ok")
sys.stdout.flush()
import safe_io  # Ende ohne Qt-Aufräumen (Absturz unter Windows)
safe_io.hard_exit(0)
