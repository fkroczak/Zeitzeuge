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
    from PySide6.QtWidgets import QApplication, QDialog, QFormLayout

    import m42_tickets as mt
    from my_tickets_dialogs import MyTicketsDialog
    from ticket_dialogs import CloseTicketDialog, EditTicketDialog, NewTicketDialog

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
                    "close": {"ticket": ROW["ticket"]},
                    "load": {"id": "t2", "ticket": ROW["ticket"], "type": ROW["type"], "subject": "Drucker",
                             "description": "Druckt nicht", "stamp": "s1"},
                    "edit": {"ticket": ROW["ticket"], "id": "t2", "type": ROW["type"],
                             "subject": "Drucker Empfang"},
                    "user_details": {"OrgUnit": "WiRoPa GmbH", "Phone": "02542 1", "Email": "info@example.com"}}[kind]
            result = {"kind": kind, "args": args, "ok": kind not in self.fail, "data": data}
            if kind in self.fail:
                result.update(error="Zeitüberschreitung", unclear=True)
            QTimer.singleShot(0, lambda: self.ticket_task_done.emit(result))
            return True

    reader = FakeReader()
    mine = MyTicketsDialog(reader)
    mine.show()
    assert mine.table.rowCount() == 1 and not mine.close_button.isEnabled()  # erst nach Auswahl
    mine.table.select_first()
    assert mine.close_button.isEnabled()

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
        QTest.qWait(20)
        seen["card"] = [dialog.user_rows.itemAt(i, QFormLayout.FieldRole).widget().text()
                        for i in range(dialog.user_rows.rowCount())]
        dialog.category_edit.setCurrentText("Visaas > Server > Fileserver")
        dialog.subject_edit.setText("Rückmeldung zu den ZRO-Ordnern")
        dialog.description_edit.setPlainText("Anpassungen an ZRO-Ordnern")
        dialog.type_chips[mt.SERVICE_REQUEST].click()
        seen["incident_off"] = not dialog.type_chips[mt.INCIDENT].isChecked()
        seen["ok_after"] = dialog.ok_button.isEnabled()
        dialog.ok_button.click()
    QTimer.singleShot(0, fill_new)
    mine.new_button.click()
    assert seen == {"category": "cat-in", "ok_before": False, "users": 1, "ok_after": True, "incident_off": True,
                    "card": ["Brüning, Gerd", "WiRoPa GmbH", "02542 1", "info@example.com"]}, seen
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

    # ---- Bearbeiten: erst nach dem Laden änderbar, Speichern nur mit Änderung
    edit = EditTicketDialog(reader, ROW)
    assert not edit.subject_edit.isEnabled() and not edit.ok_button.isEnabled()
    QTest.qWait(20)
    assert edit.current_edit.toPlainText() == "Druckt nicht" and edit.subject_edit.isEnabled()
    assert not edit.ok_button.isEnabled()  # nichts geändert
    edit.addition_edit.setPlainText("Toner getauscht")
    assert edit.ok_button.isEnabled()
    edit.reject()

    def fill_edit():
        dlg = next(w for w in app.topLevelWidgets() if isinstance(w, EditTicketDialog) and w.isVisible())
        QTest.qWait(20)
        dlg.subject_edit.setText("Drucker Empfang")
        dlg.ok_button.click()
    QTimer.singleShot(0, fill_edit)
    mine.table.select_first()
    assert mine.edit_button.isEnabled()
    mine.edit_button.click()
    kind, args = reader.tasks[-1]
    assert kind == "edit" and args["request"] == {"id": "t2", "ticket": "TCK0000000002", "stamp": "s1",
                                                  "subject": "Drucker Empfang", "addition": ""}, args
    assert "TCK0000000002 gespeichert" in mine.status.text(), mine.status.text()
    assert mine.visible_rows()[0]["subject"] == "Drucker Empfang"

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
    mine.table.select_first()
    mine.close_button.click()
    kind, args = reader.tasks[-1]
    assert kind == "close" and args["request"] == {"id": "t2", "type": "SPSActivityTypeIncident",
                                                   "ticket": "TCK0000000002", "solution": "Treiber neu installiert",
                                                   "notify": False}, args
    assert mine.table.rowCount() == 0 and "TCK0000000002 geschlossen" in mine.status.text()

    # ---- Tabelle: neueste zuerst, Filter über alle Spalten, Klick auf eine Spalte sortiert
    def mk(n, subject, customer, state, created):
        return dict(ROW, ticket=f"TCK000000000{n}", id=f"t{n}", subject=subject, customer=customer,
                    state=state, created=created)
    reader.my_tickets = {"at": "11:00", "error": "", "rows": [
        mk(1, "VPN bricht ab", "Weber", "Neu", "2026-11-03T08:00:00Z"),
        mk(3, "Drucker Empfang", "Schmidt", "In Bearbeitung", "2026-11-10T08:00:00Z"),
        mk(2, "Drucker Lager", "Weber", "Neu", "2026-11-05T08:00:00Z")]}
    table_dialog = MyTicketsDialog(reader)
    table_dialog.show()
    app.processEvents()
    order = lambda: [r["ticket"][-1] for r in table_dialog.visible_rows()]  # noqa: E731
    assert order() == ["3", "2", "1"], order()  # Angelegt absteigend
    table_dialog.filter_edit.setText("drucker weber")
    assert order() == ["2"] and "1 passen zum Filter" in table_dialog.status.text(), table_dialog.status.text()
    table_dialog.filter_edit.clear()
    table_dialog.table.sort_by(2, Qt.AscendingOrder)  # Kunde
    assert [r["customer"] for r in table_dialog.visible_rows()] == ["Schmidt", "Weber", "Weber"]
    table_dialog.filter_edit.setFocus()
    QTest.keyClick(table_dialog.filter_edit, Qt.Key_Down)  # Pfeil runter: erste Zeile markiert
    assert table_dialog.current_row()["ticket"].endswith("3")
    QTest.keyClick(table_dialog.table, Qt.Key_Return)
    assert app.clipboard().text() == "TCK0000000003"
    table_dialog.close()
    assert QDialog  # (Import für Typen oben)
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
