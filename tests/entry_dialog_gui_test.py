"""Dialog „Tätigkeit nachtragen/ändern“ (journal_dialogs.EntryDialog) im Stil der Nachfrage-Karte.

Prüft: feste Zeitzeile mit Stift (verrutscht nicht, Doppelklick öffnet, beim Nachtragen ohne
Zeitraum gleich offen), Beschriftung über den Feldern, „+ Ticket“ wird zum Chip, Vorschlag als
Link, Chips für Kulanz/Reise/Zuschlag, Merken-Chips lassen das Fenster wachsen, Spuren „In dieser
Zeit“ folgen der Zeit, Fehler bei Ende vor Beginn, Löschen links, Strg+Enter speichert und beide
Designs.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import faulthandler
import os
import sys
import tempfile
import traceback
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()


def gui_test():
    global app, window
    import main_timeline
    from journal_dialogs import EntryDialog
    from PySide6.QtCore import QPoint, Qt, QTime, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QSystemTrayIcon

    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())
    window = main_timeline.TimelineApp()
    window.tray.showMessage = lambda *a: None
    window.show()

    start, end = datetime(2026, 10, 20, 9, 15), datetime(2026, 10, 20, 10, 5)
    found = [{"ticket": "TCK0000049374", "label": "TCK0000049374 · Drucker druckt nicht"}]
    spans = []

    def context(s, e):
        spans.append((s, e))
        return [("TeamViewer", f"Praxis Weber · {s:%H:%M}–{e:%H:%M}")]

    d = EntryDialog(start, end, ["Praxis Weber"], ["Fernwartung"], "Praxis Weber", "Fernwartung",
                    info="Vorschlag aus deinem Kalender: Wartung", parent=window, context_for=context,
                    ticket_suggestions=found, snippets=["Updates installiert"])
    d.show()
    QTest.qWait(50)
    form = d.form

    # Kopf: Aufgabe als Titel, Vorschlag darunter
    assert d.title.full_text() == "Tätigkeit nachtragen" and "Kalender" in d.subtitle.full_text()

    # Zeitzeile: gesperrt, Stift öffnet, Zeile bleibt an derselben Stelle
    y = d.time_row.mapTo(d, QPoint(0, 0)).y()
    assert form.start_edit.isReadOnly() and not d.time_editing()
    assert d.time_btn.accessibleName(), "Stift braucht einen Namen"
    d.time_btn.click()
    assert d.time_editing() and not form.start_edit.isReadOnly()
    assert d.time_row.mapTo(d, QPoint(0, 0)).y() == y, "Zeitzeile verrutscht"
    d.time_btn.click()
    assert form.start_edit.isReadOnly()
    QTest.mouseDClick(form.end_edit, Qt.LeftButton)
    assert d.time_editing(), "Doppelklick auf die Zeit öffnet die Zeile"

    # Spuren folgen der Zeit
    form.end_edit.setTime(QTime(10, 30))
    assert spans[-1][1].minute == 30 and "In dieser Zeit" in [lab.text() for lab in d.findChildren(
        main_timeline.QLabel)], spans

    # Ende vor Beginn: Fehler als Text, Speichern gesperrt
    form.end_edit.setTime(QTime(9, 0))
    assert not d.save_btn.isEnabled() and form.error.isVisibleTo(d) and "Bis" in form.error.text()
    form.end_edit.setTime(QTime(10, 5))
    assert d.save_btn.isEnabled() and not form.error.isVisibleTo(d)

    # Beschriftung über dem Feld (nicht links daneben)
    labels = {lab.buddy(): lab for lab in d.findChildren(main_timeline.QLabel)
              if lab.objectName() == "prompt_label" and lab.buddy() is not None}
    for field in (form.customer_edit, form.category_edit, form.text_edit):
        label = labels[field]
        assert label.isVisibleTo(d)
        top = label.mapTo(d, QPoint(0, 0))
        below = field.mapTo(d, QPoint(0, 0))
        assert top.y() < below.y() and abs(top.x() - below.x()) < 4, (label.text(), top, below)

    # Ticket-Vorschlag als Link, danach Chip mit ✕
    assert form.ticket_take.isVisibleTo(d) and form.ticket_take.text().startswith("Vorschlag:")
    form.ticket_take.click()
    assert d.ticket_chip.isVisibleTo(d) and "TCK0000049374" in d.ticket_chip.text()
    assert "TCK0000049374" in d.ticket_chip.accessibleName()
    d.ticket_chip.click()
    assert d.ticket_add.isVisibleTo(d) and form.item()["ticket"] == ""
    # + Ticket: Feld, Enter macht daraus einen Chip
    d.ticket_add.click()
    assert d.ticket_row.isVisibleTo(d)
    form.ticket_edit.setCurrentText("TCK0000012345")
    d._close_ticket()
    assert d.ticket_chip.isVisibleTo(d) and not d.ticket_row.isVisibleTo(d)

    # Chips für Kulanz, Reise, Zuschlag
    for box in (form.goodwill_box, form.travel_box, form.surcharge_box):
        assert box.objectName() == "chip_check" and "&" in box.text()
    form.goodwill_box.click()
    form.text_edit.setPlainText("Server neu gestartet")
    item = form.item()
    assert item["goodwill"] and item["ticket"] == "TCK0000012345" and item["text"] == "Server neu gestartet"

    # Fuß: kein Löschen beim Nachtragen, genau eine Hauptaktion; Strg+Enter speichert
    assert d.delete_btn is None
    assert [b for b in d.findChildren(QPushButton) if b.isDefault()] == [d.save_btn]
    QTest.keyClick(form.text_edit, Qt.Key_Return, Qt.ControlModifier)
    assert d.result() == QDialog.Accepted and form.text_edit.toPlainText() == "Server neu gestartet"
    d.deleteLater()

    # Ändern: Löschen links und leise, Kunde als Untertitel
    d = EntryDialog(start, end, ["Beispiel AG"], ["Fernwartung"], "Beispiel AG", "Fernwartung", "x",
                    title="Tätigkeit ändern", can_delete=True, parent=window, ticket="TCK1", travel=True)
    d.show()
    QTest.qWait(50)
    assert d.subtitle.full_text() == "Beispiel AG" and d.ticket_chip.isVisibleTo(d)
    assert d.form.travel_box.isChecked() and d.delete_btn.objectName() == "quiet_button"
    assert d.delete_btn.mapTo(d, QPoint(0, 0)).x() < d.save_btn.mapTo(d, QPoint(0, 0)).x()
    d.delete_btn.click()
    assert d.deleted and d.result() == QDialog.Accepted
    d.deleteLater()

    # Merken-Chips erscheinen beim Ändern von Kunde/Kategorie, das Fenster wächst mit
    d = EntryDialog(start, end, ["Müller GmbH"], ["Fernwartung", "Beratung"], customer="srv01",
                    category="Fernwartung", trace=("rdm", "srv01"), rule_subject="srv01", parent=window)
    d.show()
    QTest.qWait(50)
    before = d.height()
    d.form.customer_edit.setCurrentText("Müller GmbH")
    d.form.category_edit.setCurrentText("Beratung")
    QTest.qWait(50)
    assert d.form.remember_tv.isVisibleTo(d) and d.form.learn_rule.isVisibleTo(d)
    assert d.form.learn_rule.objectName() == "chip_check"
    assert d.height() >= before
    bottom = max(w.mapTo(d, QPoint(0, w.height())).y() for w in (d.form.learn_rule, d.form.remember_tv))
    assert bottom <= d.save_btn.mapTo(d, QPoint(0, 0)).y(), "Chips liegen unter der Fußleiste"
    d.reject()
    d.deleteLater()

    # Beide Designs: Dialog baut sich auf, Fläche in surface, nichts fest eingetragen
    for dark in (False, True):
        window.config["dark_mode"] = dark
        window.apply_style()
        d = EntryDialog(start, end, ["A"], ["B"], parent=window)
        d.show()
        QTest.qWait(30)
        assert not d.grab().isNull()
        d.reject()
        d.deleteLater()

    # Nachtragen über das Menü (ohne Zeitraum): Zeitzeile gleich offen; Ändern heißt „Tätigkeit ändern“
    seen = {}

    def inspect():
        dialog = next(w for w in app.topLevelWidgets() if isinstance(w, EntryDialog) and w.isVisible())
        seen["editing"] = dialog.time_editing()
        seen["title"] = dialog.windowTitle()
        dialog.reject()

    QTimer.singleShot(200, inspect)
    window.add_doc(minute=9 * 60)
    assert seen == {"editing": True, "title": "Tätigkeit nachtragen"}, seen
    day = window.current_date.toPython()
    QTimer.singleShot(200, inspect)
    window.add_doc(span=(datetime.combine(day, datetime.min.time()).replace(hour=9),
                         datetime.combine(day, datetime.min.time()).replace(hour=10)))
    assert seen["editing"] is False, "gezogener Zeitraum: Zeitzeile gesperrt"
    QTimer.singleShot(200, inspect)
    window.edit_doc({"start": "2026-10-20 09:00:00", "end": "2026-10-20 09:30:00", "customer": "A",
                     "category": "B", "text": "x"})
    assert seen["title"] == "Tätigkeit ändern" and seen["editing"] is False, seen

    window.quit_app()
    print("Tätigkeit nachtragen: OK")


try:
    gui_test()
except Exception:
    traceback.print_exc()
    sys.stdout.flush()
    import safe_io
    safe_io.hard_exit(1)
sys.stdout.flush()
import safe_io  # Ende ohne Qt-Aufräumen (Absturz unter Windows)
safe_io.hard_exit(0)
