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
    from PySide6.QtWidgets import QApplication, QDialog, QFormLayout, QToolButton

    import m42_booking as mb
    import m42_tickets as mt
    from tickets_dialogs import TicketsDialog
    from ticket_dialogs import CloseTicketDialog, EditTicketDialog, NewTicketDialog, ViewTicketDialog

    app = QApplication(sys.argv)

    def wait_for(done, ms):
        """Ereignisse verarbeiten, bis done() wahr ist (höchstens ms). Unter Windows brauchen
        Antworten über QueuedConnection länger als ein festes qWait(20)."""
        for _ in range(ms // 10):
            if done():
                return True
            QTest.qWait(10)
        return done()
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
            self.solution = ""  # Lösungstext von früher (close_info)

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
                    "close_info": {"solution": self.solution},
                    "load": {"id": "t2", "ticket": ROW["ticket"], "type": ROW["type"], "subject": "Drucker",
                             "description": "Druckt nicht", "category": "cat-in", "rich": False,
                             "stamp": "s1", "initiator": "melder-1", "callback": "0171 5"},
                    "edit": {"ticket": ROW["ticket"], "id": "t2", "type": ROW["type"],
                             "subject": "Drucker Empfang"},
                    "user_details": {"OrgUnit": "WiRoPa GmbH", "Phone": "02542 1", "Email": "info@example.com"},
                    "take_over": {"ticket": ROW["ticket"], "id": "t2", "user": "Kroczak, Filip"},
                    "melder": {"user": {"id": "melder-1", "name": ROW["initiator"]},
                               "details": {"OrgUnit": "WiRoPa GmbH", "Phone": "02542 1"}}}[kind]
            result = {"kind": kind, "args": args, "ok": kind not in self.fail, "data": data}
            if kind in self.fail:
                result.update(error="Zeitüberschreitung", unclear=True)
            QTimer.singleShot(0, lambda: self.ticket_task_done.emit(result))
            return True

    reader = FakeReader()
    mine = TicketsDialog(reader)
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
    assert wait_for(lambda: edit.loaded is not None and edit.categories, 3000)
    assert edit.description_edit.toPlainText() == "Druckt nicht" and edit.subject_edit.isEnabled()
    assert edit.category() == "cat-in" and not edit.rich_hint.isVisibleTo(edit)
    assert not edit.ok_button.isEnabled()  # nichts geändert
    edit.description_edit.setPlainText("Druckt nicht\nToner getauscht")
    assert edit.ok_button.isEnabled()
    edit.description_edit.setPlainText("Druckt nicht")
    assert not edit.ok_button.isEnabled()
    edit.category_edit.setCurrentIndex(edit.category_edit.findData("cat-fs"))
    assert edit.ok_button.isEnabled()
    edit.category_edit.setEditText("gibt es nicht")
    assert not edit.ok_button.isEnabled()  # getippter Text ist keine Kategorie
    edit.reject()

    def fill_edit():
        dlg = next(w for w in app.topLevelWidgets() if isinstance(w, EditTicketDialog) and w.isVisible())
        wait_for(lambda: dlg.loaded is not None and dlg.categories, 3000)
        dlg.subject_edit.setText("Drucker Empfang")
        dlg.description_edit.setPlainText("Drucker am Empfang druckt nicht")
        dlg.category_edit.setCurrentIndex(dlg.category_edit.findData("cat-fs"))
        dlg.ok_button.click()
    QTimer.singleShot(0, fill_edit)
    mine.table.select_first()
    assert mine.edit_button.isEnabled()
    mine.edit_button.click()
    kind, args = reader.tasks[-1]
    assert kind == "edit" and args["request"] == {"id": "t2", "ticket": "TCK0000000002", "stamp": "s1",
                                                  "subject": "Drucker Empfang", "category": "cat-fs",
                                                  "description": "Drucker am Empfang druckt nicht",
                                                  "initiator": None}, args
    assert "TCK0000000002 gespeichert" in mine.status.text(), mine.status.text()
    assert mine.visible_rows()[0]["subject"] == "Drucker Empfang"

    # ---- Bearbeiten: Stift in der Ticketzeile ändert den Melder
    edit = EditTicketDialog(reader, ROW)
    assert wait_for(lambda: edit.loaded is not None, 3000)
    assert not edit.melder_box.isVisibleTo(edit) and edit.pen_button.isEnabled()
    edit.pen_button.click()
    assert edit.melder_box.isVisibleTo(edit) and edit.user_edit.text() == "Huber, Max"
    edit.user_edit.clear()
    QTest.keyClicks(edit.user_edit, "Bru")
    assert wait_for(lambda: edit.users.count() == 1, 3000)
    edit._take_user(edit.users.item(0))
    assert edit.new_initiator() is None and not edit.ok_button.isEnabled()  # derselbe wie im Ticket
    edit.loaded["initiator"] = "melder-0"
    edit.validate()
    assert edit.new_initiator() == "melder-1" and edit.ok_button.isEnabled()
    edit.ok_button.click()
    kind, args = reader.tasks[-1]
    assert kind == "edit" and args["request"]["initiator"] == "melder-1", args
    # Übernehmen im Bearbeiten-Fenster
    edit = EditTicketDialog(reader, dict(ROW, recipient_id="jemand"))
    assert edit.take_over_button.isVisibleTo(edit)
    edit.take_over_button.click()
    assert wait_for(lambda: edit.taken_over is not None, 3000)
    assert edit.taken_over == "Kroczak, Filip" and not edit.take_over_button.isVisibleTo(edit)
    assert ("take_over", {"owner": id(edit), "id": "t2", "type": ROW["type"], "ticket": ROW["ticket"]}) in reader.tasks
    edit.reject()

    # ---- Ansehen: Beschreibung und Kontakt (Telefon/E-Mail als Link), nichts wird geändert
    view = ViewTicketDialog(reader, ROW)
    assert wait_for(lambda: view.contact_rows.rowCount() > 2, 3000), view.status.text()
    assert view.description_view.toPlainText() == "Druckt nicht" and view.description_view.isReadOnly()
    contact = {view.contact_rows.itemAt(i, QFormLayout.LabelRole).widget().text():
               view.contact_rows.itemAt(i, QFormLayout.FieldRole).widget().text()
               for i in range(view.contact_rows.rowCount())}
    assert contact["Name"] == "Huber, Max" and contact["Firma"] == "WiRoPa GmbH", contact
    assert 'href="tel:025421"' in contact["Telefon"] and 'href="mailto:info@example.com"' in contact["E-Mail"]
    assert 'href="tel:01715"' in contact["Rückruf"], contact
    assert ("user_details", {"owner": id(view), "user": "melder-1"}) in reader.tasks
    assert not any(k in ("edit", "close") for k, _ in reader.tasks[-2:])
    assert not view.cancel_button.isVisibleTo(view), "kein „Fertig“: schließen über ✕"
    view.ok_button.click()
    assert view.action == "edit"

    # kein Knopf blitzt beim Öffnen als eigenes Fenster auf (Übernehmen/Schließen erst einfügen, dann zeigen)
    from PySide6.QtCore import QEvent

    class ShowSpy(QObject):
        def __init__(self):
            super().__init__()
            self.windows = []

        def eventFilter(self, obj, event):
            if event.type() == QEvent.Show and obj.isWidgetType() and obj.isWindow():
                self.windows.append(type(obj).__name__)
            return False
    spy = ShowSpy()
    app.installEventFilter(spy)
    other = dict(ROW, recipient="Kollege", recipient_id="other")
    view = ViewTicketDialog(reader, other)
    app.removeEventFilter(spy)
    assert spy.windows == [], spy.windows
    assert view.take_over_button.isVisibleTo(view) and view.close_ticket_button.isVisibleTo(view)
    view.reject()

    # Ticket nicht ladbar (z. B. E-Mail, die Matrix42 nicht entschlüsseln kann): Telefon trotzdem
    reader.fail.add("load")
    view = ViewTicketDialog(reader, ROW)
    assert wait_for(lambda: view.contact_rows.rowCount() > 2, 3000), view.status.text()
    assert ("melder", {"owner": id(view), "name": ROW["initiator"]}) in reader.tasks
    assert "Laden fehlgeschlagen" in view.status.text()
    phone = next(view.contact_rows.itemAt(i, QFormLayout.FieldRole).widget().text()
                 for i in range(view.contact_rows.rowCount())
                 if view.contact_rows.itemAt(i, QFormLayout.LabelRole).widget().text() == "Telefon")
    assert 'href="tel:025421"' in phone
    view.reject()
    reader.fail.clear()

    # aus der Liste: Enter öffnet das Ticket, „Bearbeiten …“ dort führt ins Bearbeiten-Fenster
    def view_then_edit():
        dlg = next(w for w in app.topLevelWidgets() if isinstance(w, ViewTicketDialog) and w.isVisible())
        wait_for(lambda: dlg.loaded is not None, 3000)
        dlg.ok_button.click()

        def close_edit():  # Bearbeiten-Fenster öffnet erst, wenn „Ansehen“ zu ist
            edit = [w for w in app.topLevelWidgets() if isinstance(w, EditTicketDialog) and w.isVisible()]
            edit[0].reject() if edit else QTimer.singleShot(10, close_edit)
        QTimer.singleShot(10, close_edit)
    QTimer.singleShot(0, view_then_edit)
    mine.table.select_first()
    assert mine.view_button.isEnabled()
    loads = sum(1 for k, _ in reader.tasks if k == "load")
    mine.table.activated.emit(mine.current_row())
    assert sum(1 for k, _ in reader.tasks if k == "load") == loads + 2  # Ansehen, dann Bearbeiten

    # ---- Schließen: Fehler „unklar“ sperrt den Knopf, beim zweiten Fenster klappt es
    reader.fail.add("close")
    dialog = CloseTicketDialog(reader, ROW)
    assert not dialog.ok_button.isEnabled()  # ohne Lösungstext nicht
    dialog.solution_edit.setPlainText("Treiber neu installiert")
    dialog.ok_button.click()
    # Antwort kommt über zwei Ereignisrunden: warten, bis sie da ist (unter Windows dauert das länger als 20 ms)
    assert wait_for(lambda: "fehlgeschlagen" in dialog.status.text(), 3000), dialog.status.text()
    assert "unklar" not in dialog.status.text() and "Zeitüberschreitung" in dialog.status.text(), dialog.status.text()
    assert not dialog.ok_button.isEnabled() and not dialog.closed
    dialog.reject()
    reader.fail.clear()

    # Wieder eröffnetes Ticket: bisheriger Lösungstext steht schon drin, Getipptes bleibt
    reader.solution = "Lizenz erneuert"
    dialog = CloseTicketDialog(reader, ROW)
    assert wait_for(lambda: dialog.solution_edit.toPlainText(), 3000)
    assert dialog.solution_edit.toPlainText() == "Lizenz erneuert" and dialog.ok_button.isEnabled()
    assert ("close_info", {"owner": id(dialog), "id": "t2", "type": "SPSActivityTypeIncident"}) in reader.tasks
    dialog.reject()
    dialog = CloseTicketDialog(reader, ROW)
    dialog.solution_edit.setPlainText("Selbst getippt")
    QTest.qWait(50)
    assert dialog.solution_edit.toPlainText() == "Selbst getippt"
    dialog.reject()
    reader.solution = ""

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
    table_dialog = TicketsDialog(reader)
    table_dialog.show()
    app.processEvents()
    order = lambda: [r["ticket"][-1] for r in table_dialog.visible_rows()]  # noqa: E731
    assert order() == ["3", "2", "1"], order()  # Angelegt absteigend
    table_dialog.filter_edit.setText("drucker weber")
    assert order() == ["2"] and "1 passen zum Filter" in table_dialog.status.text(), table_dialog.status.text()
    table_dialog.filter_edit.setText("störung")  # Spalte Art
    assert len(order()) == 3 and table_dialog.table.item(0, 4).text() == "Störung"
    table_dialog.filter_edit.setText("serviceanfrage")
    assert order() == []
    table_dialog.filter_edit.clear()
    table_dialog.table.sort_by(2, Qt.AscendingOrder)  # Kunde
    assert [r["customer"] for r in table_dialog.visible_rows()] == ["Schmidt", "Weber", "Weber"]
    table_dialog.filter_edit.setFocus()
    QTest.keyClick(table_dialog.filter_edit, Qt.Key_Down)  # Pfeil runter: erste Zeile markiert
    assert table_dialog.current_row()["ticket"].endswith("3")
    opened = []

    def close_view():  # Enter öffnet „Ticket ansehen“
        views = [w for w in app.topLevelWidgets() if isinstance(w, ViewTicketDialog) and w.isVisible()]
        if views:
            opened.append(views[0].row["ticket"])
            views[0].reject()
        else:
            QTimer.singleShot(10, close_view)
    QTimer.singleShot(10, close_view)
    QTest.keyClick(table_dialog.table, Qt.Key_Return)
    assert opened == ["TCK0000000003"], opened
    table_dialog.copy_button.click()
    assert app.clipboard().text() == "TCK0000000003"

    # rechte Maustaste: Kontextmenü mit Ansehen, Bearbeiten, Übernehmen, Schließen, Nummer kopieren
    menus = []

    def read_menu():
        menu = app.activePopupWidget()
        if menu is None:
            QTimer.singleShot(10, read_menu)
            return
        menus.append([a.text() for a in menu.actions() if not a.isSeparator()])
        menu.close()
    QTimer.singleShot(10, read_menu)
    table = table_dialog.table
    table.customContextMenuRequested.emit(table.visualRect(table.model().index(1, 0)).center())
    assert menus == [["Ans&ehen …", "&Bearbeiten …", "Über&nehmen", "Ticket &schließen …", "Nummer &kopieren"]], menus
    picked = table_dialog.current_row()
    assert picked["id"] == table_dialog.visible_rows()[1]["id"]  # Rechtsklick markiert die Zeile
    table_dialog.take_over()
    assert ("take_over", {"owner": id(table_dialog), "id": picked["id"], "type": picked.get("type", ""),
                          "ticket": picked["ticket"]}) in reader.tasks
    assert wait_for(lambda: "übernommen" in table_dialog.status.text(), 3000), table_dialog.status.text()
    taken = next(r for r in table_dialog.visible_rows() if r["id"] == picked["id"])
    assert taken["recipient"] == "Kroczak, Filip", taken
    table_dialog.close()

    # ---- Pillen: Kategorien schalten um, „Geschlossene“ wirkt bei jeder, Filter sucht nur darin
    class CategoryReader(FakeReader):
        tickets_loaded = Signal(object)
        ticket_filters_loaded = Signal(object)
        ticket_filters = None

        def __init__(self):
            super().__init__()
            self.ticket_views, self.loads, self.filter_loads = {}, [], 0

        def load_tickets(self, key, filter_id=""):
            self.loads.append((key, filter_id))
            rows = [mk(4, "Telefon TK", "Weber", "Neu", "2026-11-12T08:00:00Z"),
                    mk(5, "Anlage TK alt", "Weber", "Geschlossen", "2026-11-01T08:00:00Z"),
                    mk(6, "Telefon pausiert", "Huber", "Angehalten", "2026-11-11T08:00:00Z")]
            self.ticket_views[key] = {"key": key, "rows": rows, "error": "", "at": "11:05", "time": 9e12}
            QTimer.singleShot(0, lambda: self.tickets_loaded.emit(self.ticket_views[key]))

        def load_ticket_filters(self):
            self.filter_loads += 1
            self.ticket_filters = [{"id": "f-neu", "title": "Neue Tickets"}]
            QTimer.singleShot(0, lambda: self.ticket_filters_loaded.emit(self.ticket_filters))

    creader = CategoryReader()
    closed_mine = mk(7, "Drucker erledigt", "Weber", "Gelöst", "2026-11-01T08:00:00Z")
    creader.my_tickets = dict(reader.my_tickets, all=reader.my_tickets["rows"] + [closed_mine])
    tickets = TicketsDialog(creader)
    tickets.show()
    assert wait_for(lambda: "f:f-neu" in tickets.category_buttons, 2000)
    def shown():
        """Sichtbare Knöpfe der Auswahl, in Anzeigereihenfolge (Zeilen, darin von links)."""
        app.processEvents()
        buttons = [b for b in tickets.selector.findChildren(QToolButton) if b.isVisibleTo(tickets)]
        return [b.text() for b in sorted(buttons, key=lambda b: (b.mapTo(tickets, b.rect().topLeft()).y(),
                                                                  b.mapTo(tickets, b.rect().topLeft()).x()))]
    def button(text):
        return next(b for b in tickets.selector.findChildren(QToolButton) if b.text() == text and b.isVisibleTo(tickets))
    # Anordnung 1 (Standard): Zeile „Ansicht“ und Zeile „Pools“, Geschlossene als Schalter
    assert tickets.layout_no == 1 and shown() == ["Meine Tickets", "Alle", "Neue Tickets", "TK-Tickets"], shown()
    assert tickets.closed_button is tickets.closed_switch and tickets.closed_switch.isVisibleTo(tickets)
    assert tickets.category_buttons["mine"].isChecked() and not tickets.closed_button.isChecked()
    assert tickets.windowTitle() == "Tickets" and len(tickets.visible_rows()) == 3  # offene von mir
    tickets.closed_button.click()  # Geschlossene an: auch erledigte von mir
    assert len(tickets.visible_rows()) == 4 and "davon 1 geschlossen" in tickets.status.text(), tickets.status.text()
    tickets.category_buttons["tk"].click()  # Kategorie wechseln, „Geschlossene“ bleibt an
    assert creader.loads == [("tk", mb.TK_FILTER)], creader.loads
    assert wait_for(lambda: len(tickets.visible_rows()) == 3, 2000)
    assert not tickets.category_buttons["mine"].isChecked() and tickets.closed_button.isChecked()
    tickets.filter_edit.setText("tk")  # Suche nur in der Kategorie: auch das geschlossene
    assert sorted(r["ticket"][-1] for r in tickets.visible_rows()) == ["4", "5"]
    tickets.closed_button.click()  # aus: nur offene und angehaltene
    assert [r["ticket"][-1] for r in tickets.visible_rows()] == ["4"]
    tickets.filter_edit.clear()
    assert sorted(r["state"] for r in tickets.visible_rows()) == ["Angehalten", "Neu"]
    tickets.closed_button.click()
    tickets.table.selectRow(next(r for r in range(tickets.table.rowCount())
                                 if tickets.table.row_at(r)["state"] == "Geschlossen"))
    assert not tickets.close_button.isEnabled() and tickets.edit_button.isEnabled()
    tickets.category_buttons["all"].click()
    tickets.category_buttons["tk"].click()  # schon gelesen und frisch: nicht nochmal
    assert [k for k, _f in creader.loads] == ["tk", "all"], creader.loads
    tickets.category_buttons["f:f-neu"].click()
    assert creader.loads[-1] == ("f:f-neu", "f-neu")

    # ---- Alle Anordnungen: Kategorie und „Geschlossene“ bleiben beim Wechsel erhalten
    tickets.choose("mine")
    creader.ticket_filters = [{"id": "f-neu", "title": "Neue Tickets"}, {"id": "f-tk", "title": "Neue TK Tickets"},
                              {"id": "f-a", "title": "Ticket_Pool_A"}, {"id": "f-v", "title": "Offen Vertrieb"}]
    tickets.show_filters([{"id": "f-tk", "title": "Neue TK Tickets"}, {"id": "f-a", "title": "Ticket Pool A"},
                          {"id": "f-v", "title": "Offen Vertrieb"}])
    assert shown() == ["Meine Tickets", "Alle", "Neue Tickets", "Offen Vertrieb",
                       "TK-Tickets", "Neue TK Tickets", "Ticket Pool A"], shown()
    # Kein Knopf „Anordnung“ mehr im Fenster (Einstellungen → Darstellung → Tickets)
    assert all(b.text() != "Anordnung" for b in tickets.findChildren(QToolButton))
    tickets.choose_layout(2)  # Kompakt: TK/Pools/Weitere als Menü
    assert shown() == ["Meine Tickets", "Alle", "Neue Tickets", "TK  ▾", "Pools  ▾", "Weitere  ▾"], shown()
    tk_menu = button("TK  ▾")
    tk_menu.menu().actions()[1].trigger()  # „Neue TK Tickets“
    assert tickets.category == "f:f-tk" and "TK: Neue TK Tickets  ▾" in shown(), shown()
    tickets.choose_layout(3)  # Seitenleiste: keine Pillen, Geschlossene als Pille neben der Suche
    assert shown() == [] and tickets.sidebar.isVisibleTo(tickets) and tickets.closed_button is tickets.closed_chip
    assert tickets.sidebar.currentItem().text().strip() == "Neue TK Tickets"
    item = next(tickets.sidebar.item(i) for i in range(tickets.sidebar.count())
                if tickets.sidebar.item(i).text().strip() == "Alle")
    tickets.sidebar.setCurrentItem(item)
    assert tickets.category == "all"
    was = tickets.closed()
    tickets.closed_button.click()
    assert tickets.closed() != was and tickets.closed_switch.isChecked() == tickets.closed()
    tickets.choose_layout(4)  # Bereich „Allgemein“ und seine Kategorien
    assert not tickets.sidebar.isVisibleTo(tickets)
    assert shown() == ["Meine", "Allgemein", "TK", "Pools", "Weitere", "Alle", "Neue Tickets"], shown()
    button("TK").click()
    assert tickets.category == "f:f-tk"  # zuletzt gewählte im Bereich TK
    tickets.category_buttons["tk"].click()
    assert tickets.category == "tk"
    favs = []
    tickets.favorites_changed.connect(favs.append)
    tickets.choose_layout(5)  # Favoriten, Rest über „+ Filter“
    assert shown() == ["Meine Tickets", "TK-Tickets", "Alle", "+ Filter", "Geschlossene"], shown()
    more = button("+ Filter")
    next(a for a in more.menu().actions() if a.text() == "Offen Vertrieb").trigger()
    assert tickets.category == "f:f-v" and "Offen Vertrieb" in shown()  # vorübergehend
    more = button("+ Filter")
    pin = next(a for a in more.menu().actions() if a.menu()).menu()
    next(a for a in pin.actions() if a.text() == "Ticket Pool A").trigger()
    assert favs == [["mine", "tk", "all", "f:f-a"]] and "Ticket Pool A" in shown()
    tickets.choose_layout(1)
    assert tickets.closed_button is tickets.closed_switch and tickets.category == "f:f-v"
    assert tickets.category_buttons["f:f-v"].isChecked() and tickets.layout_no == 1
    tickets.close()

    # ---- Reihenfolge wie im Service Desk sinnvoll gruppiert, Unbekannte nach Ähnlichkeit/ans Ende
    from tickets_dialogs import pill_rank
    names = ["Offen Vertrieb", "Ticket Pool PVS", "Ticket Pool A", "Ticket Pool TK", "Ohne Verantwortung",
             "Störungen extern", "Neue TK Tickets", "Neue Tickets", "Ticket Pool B", "TK Eskalation",
             "Ticket Pool Infrastruktur", "TK-Tickets", "Alle", "Meine Tickets"]
    assert sorted(names, key=pill_rank) == [
        "Meine Tickets", "Alle", "Neue Tickets", "Ohne Verantwortung", "TK-Tickets", "Neue TK Tickets",
        "Ticket Pool TK", "TK Eskalation", "Ticket Pool A", "Ticket Pool B", "Ticket Pool Infrastruktur",
        "Ticket Pool PVS", "Offen Vertrieb", "Störungen extern"]

    # ---- Seiten: 50 oder 100 Tickets je Seite, Filter und Kategorie fangen wieder bei Seite 1 an
    many = [dict(ROW, ticket=f"TCK{n:010d}", id=f"p{n}", subject=f"Thema {n}" + (" vpn" if n % 2 else ""),
                 created=f"2026-10-01T08:{n // 60:02d}:{n % 60:02d}Z") for n in range(120)]
    creader.my_tickets = {"at": "12:00", "error": "", "rows": many, "all": many}
    paged = TicketsDialog(creader)
    paged.show()
    app.processEvents()
    assert len(paged.visible_rows()) == 50 and paged.page_label.text() == "Seite 1 von 3"
    assert paged.visible_rows()[0]["id"] == "p119" and not paged.prev_button.isEnabled()
    assert "120 offene Tickets" in paged.status.text(), paged.status.text()
    paged.next_button.click()
    paged.next_button.click()
    assert len(paged.visible_rows()) == 20 and not paged.next_button.isEnabled()
    assert paged.visible_rows()[-1]["id"] == "p0"
    paged.size_combo.setCurrentIndex(1)  # 100 pro Seite: zurück auf Seite 1
    assert len(paged.visible_rows()) == 100 and paged.page_label.text() == "Seite 1 von 2"
    paged.next_button.click()
    paged.filter_edit.setText("vpn")  # 60 Treffer, wieder Seite 1
    assert paged.page_label.text() == "Seite 1 von 1" and len(paged.visible_rows()) == 60
    assert "60 passen zum Filter" in paged.status.text(), paged.status.text()
    paged.close()
    assert TicketsDialog(creader).size_combo.currentData() == 100  # Wahl gilt fürs nächste Fenster
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
