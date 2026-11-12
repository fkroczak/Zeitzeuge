"""Fenster „Neues Ticket“ und „Ticket schließen“ aus „Meine Tickets“, ohne Browser.

Ein nachgebauter Leser beantwortet ticket_task wie M42Reader (Melder, Kategorien, Anlegen,
Schließen). Die Abfragen selbst prüft m42_tickets_test.py.
"""
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()


def gui_test():
    global app
    from PySide6.QtCore import QObject, Qt, QTimer, Signal
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog

    import m42_tickets as mt
    from my_tickets_dialogs import MyTicketsDialog
    from ticket_dialogs import CloseTicketDialog, NewTicketDialog

    app = QApplication(sys.argv)
    ROW = {"ticket": "TCK0000000002", "id": "t2", "subject": "Drucker", "customer": "Müller", "state": "Neu",
           "initiator": "Huber, Max", "recipient": "Kroczak, Filip", "recipient_id": "me",
           "type": "SPSActivityTypeIncident", "created": ""}

    class FakeReader(QObject):
        my_tickets_loaded = Signal(object)
        ticket_task_done = Signal(object)
        my_tickets = {"at": "10:42", "error": "", "rows": [ROW]}

        def __init__(self):
            super().__init__()
            self.tasks = []
            self.fail = set()

        def load_my_tickets(self):
            self.my_tickets_loaded.emit(self.my_tickets)

        def ticket_task(self, kind, **args):
            self.tasks.append((kind, args))
            data = {"users": [{"id": "melder-1", "name": "Brüning, Gerd - WiRoPa GmbH"}],
                    "categories": [{"id": "cat-in", "path": "weitere Dienstleistungen > Default > Ticketeingang"},
                                   {"id": "cat-fs", "path": "Visaas > Server > Fileserver"}],
                    "create": {"ticket": "TCK0000050866", "id": "x", "type": "SPSActivityTypeIncident",
                               "taken_over": True, "warning": ""},
                    "close": {"ticket": ROW["ticket"]}}[kind]
            result = {"kind": kind, "args": args, "ok": kind not in self.fail, "data": data}
            if kind in self.fail:
                result.update(error="Zeitüberschreitung", unclear=True)
            QTimer.singleShot(0, lambda: self.ticket_task_done.emit(result))
            return True

    reader = FakeReader()
    mine = MyTicketsDialog(reader)
    mine.show()
    assert mine.results.count() == 1 and mine.close_button.isEnabled()

    # ---- Neues Ticket: Melder suchen und wählen, Kategorie vorbelegt mit „Ticketeingang“
    seen = {}

    def fill_new():
        dialog = next(w for w in app.topLevelWidgets() if isinstance(w, NewTicketDialog) and w.isVisible())
        QTest.qWait(20)
        seen["category"] = dialog.category()
        seen["ok_before"] = dialog.ok_button.isEnabled()
        QTest.keyClicks(dialog.user_edit, "brun")
        QTest.qWait(500)  # Suche nach kurzer Pause
        seen["users"] = dialog.users.count()
        dialog._take_user(dialog.users.item(0))
        dialog.category_edit.setCurrentText("Visaas > Server > Fileserver")
        dialog.subject_edit.setText("Rückmeldung zu den ZRO-Ordnern")
        dialog.description_edit.setPlainText("Anpassungen an ZRO-Ordnern")
        dialog.type_edit.setCurrentIndex(dialog.type_edit.findData(mt.SERVICE_REQUEST))
        seen["ok_after"] = dialog.ok_button.isEnabled()
        dialog.ok_button.click()
    QTimer.singleShot(0, fill_new)
    mine.new_button.click()
    assert seen == {"category": "cat-in", "ok_before": False, "users": 1, "ok_after": True}, seen
    kind, args = reader.tasks[-1]
    assert kind == "create", reader.tasks
    assert {k: v for k, v in args["request"].items()} == {
        "type": 6, "initiator": "melder-1", "category": "cat-fs", "subject": "Rückmeldung zu den ZRO-Ordnern",
        "description": "Anpassungen an ZRO-Ordnern", "take_over": True}, args
    assert ("users", {"owner": args["owner"], "text": "brun"}) in reader.tasks
    assert "TCK0000050866 angelegt und übernommen" in mine.status.text(), mine.status.text()
    assert app.clipboard().text() == "TCK0000050866"
    reader.load_my_tickets()  # Liste neu gelesen: Meldung bleibt stehen
    app.processEvents()
    assert "TCK0000050866 angelegt" in mine.status.text(), mine.status.text()

    # ---- Schließen: Fehler „unklar“ sperrt den Knopf, beim zweiten Fenster klappt es
    reader.fail.add("close")
    dialog = CloseTicketDialog(reader, ROW)
    assert not dialog.ok_button.isEnabled()  # ohne Lösungstext nicht
    dialog.solution_edit.setPlainText("Treiber neu installiert")
    dialog.ok_button.click()
    QTest.qWait(20)
    assert "unklar" not in dialog.status.text() and "Zeitüberschreitung" in dialog.status.text(), dialog.status.text()
    assert not dialog.ok_button.isEnabled() and not dialog.closed
    dialog.reject()
    reader.fail.clear()

    def fill_close():
        dlg = next(w for w in app.topLevelWidgets() if isinstance(w, CloseTicketDialog) and w.isVisible())
        dlg.solution_edit.setPlainText("Treiber neu installiert")
        dlg.notify.setChecked(False)
        dlg.ok_button.click()
    QTimer.singleShot(0, fill_close)
    mine.results.setCurrentRow(0)
    mine.close_button.click()
    kind, args = reader.tasks[-1]
    assert kind == "close" and args["request"] == {"id": "t2", "type": "SPSActivityTypeIncident",
                                                   "ticket": "TCK0000000002", "solution": "Treiber neu installiert",
                                                   "notify": False}, args
    assert mine.results.count() == 0 and "TCK0000000002 geschlossen" in mine.status.text()
    assert QDialog and Qt  # (Importe für Typen oben)
    mine.close()
    print("Ticket-Fenster ok")


try:
    gui_test()
except Exception:
    traceback.print_exc()
    sys.stdout.flush()
    os._exit(1)
sys.stdout.flush()
os._exit(0)
