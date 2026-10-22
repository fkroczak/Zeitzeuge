"""Tätigkeiten nachtragen: Nachfrage, Eintragen, Erinnerung und Beenden in der Oberfläche.

Läuft ohne Bildschirm mit einem leeren Datenordner, als eigener Prozess (Skript).
Die Ablage ohne Oberfläche prüft journal_test.py.
"""
import faulthandler
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Unter Windows geht gepufferte Ausgabe bei einem harten Ende verloren: sofort schreiben
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

FMT = "%Y-%m-%d %H:%M:%S"


def t(dt):
    return dt.strftime(FMT)


def flush_deletes():
    """Gelöschte Fenster (deleteLater) jetzt wirklich löschen. In der App passiert das in der
    Ereignisschleife; der Test läuft ohne app.exec(), sonst geschähe es erst im nächsten Dialog."""
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def gui_test():
    # --------------------------------------------------------------- Oberfläche

    import main_timeline  # noqa: E402
    from PySide6.QtCore import QTimer  # noqa: E402
    from PySide6.QtTest import QTest  # noqa: E402
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())  # wie die App (Fusion), Windows-Stil stürzt ohne Bildschirm ab
    window = main_timeline.TimelineApp()
    # Ohne Bildschirm gibt es keinen echten Infobereich: Sprechblasen an einem nur
    # vorgetäuschten Symbol stürzen unter Windows in Qt ab. Meldungen hier mitschreiben.
    tray_messages = []
    window.tray.showMessage = lambda title, text, *a: tray_messages.append(title)
    window.show()

    now = datetime.now().replace(microsecond=0)
    if now.hour == 0 and now.minute < 50:
        print("Kurz nach Mitternacht: Oberflächentest übersprungen")
        return
    start, end = now - timedelta(minutes=45), now - timedelta(minutes=10)
    window.activities.append({"start": t(start), "end": t(end), "type": "TeamViewer",
                              "customer_name": "", "details": "", "tv_id": "987654321",
                              "is_suggestion": True})
    window.timeline.draw_timeline(window.current_date)

    # Zeile "Doku" zeigt den offenen Eintrag gestrichelt
    bands = dict((k, e) for k, _t, e in window.timeline._bands)
    assert "doc" in bands and len(bands["doc"]) == 1 and bands["doc"][0]["open"], bands
    assert "offen" in window.info_label.text(), window.info_label.text()

    # Nachfrage erscheint
    window.check_prompts()
    prompt = window._prompt_window
    assert prompt is not None, "keine Nachfrage"
    assert "TeamViewer" in prompt.findChildren(main_timeline.QLabel)[0].text()
    assert prompt.form.category_edit.currentText() == "Fernwartung"
    assert prompt.remember_tv(), "TeamViewer-Name merken sollte vorausgewählt sein"
    # Gleicher Eintrag wird nicht doppelt gefragt
    window.check_prompts()
    assert len(window._prompt_queue) == 1

    # Später fragen: Fenster zu, vor Ablauf keine neue Nachfrage
    prompt.reject()
    QTest.qWait(600)
    flush_deletes()
    assert window._prompt_window is None
    window.check_prompts()
    assert window._prompt_window is None, "trotz „Später“ sofort wieder gefragt"

    # Ablauf der Wartezeit simulieren, dann eintragen
    window._prompt_asked.clear()
    window.check_prompts()
    prompt = window._prompt_window
    prompt.form.customer_edit.setCurrentText("Beispiel AG")
    prompt.form.text_edit.setPlainText("Outlook-Profil neu angelegt")
    prompt.save_btn.click()
    QTest.qWait(600)
    flush_deletes()
    items = window.journal.items(now.strftime("%Y-%m-%d"))
    assert [i["text"] for i in items] == ["Outlook-Profil neu angelegt"], items
    assert items[0]["customer"] == "Beispiel AG" and items[0]["source"] == "TeamViewer"
    assert window.config["teamviewer_names"]["987654321"] == "Beispiel AG"
    with open(main_timeline.CONFIG_FILE, encoding="utf-8") as f:
        assert json.load(f)["teamviewer_names"]["987654321"] == "Beispiel AG"
    assert window._prompt_window is None and not window._prompt_queue
    # Feierabend-Erinnerung: höchstens einmal am Tag, nur nach Ende der Arbeitszeit
    reminders = [m for m in tray_messages if m.startswith("Feierabend")]
    assert len(reminders) <= 1, tray_messages

    bands = dict((k, e) for k, _t, e in window.timeline._bands)
    assert len(bands["doc"]) == 1 and bands["doc"][0]["doc"], bands["doc"]

    # Ansicht "Dokumentation" in der Tagesliste, STRG + C gibt die Ticketzeile
    window.change_view("doc")
    assert window.table.rowCount() == 1
    window.table.selectRow(0)
    window.copy_selection()
    assert "Beispiel AG · Fernwartung: Outlook-Profil neu angelegt" in QApplication.clipboard().text()

    # Zeilen der Timeline abschaltbar
    window.row_actions["doc"].setChecked(False)
    assert not any(k == "doc" for k, _t, _e in window.timeline._bands)
    window.row_actions["doc"].setChecked(True)

    # Beenden mit offener Tätigkeit: erst nachfragen
    window.activities.append({"start": t(now - timedelta(minutes=9)), "end": t(now - timedelta(minutes=4)),
                              "type": "SSH-Verbindung", "customer_name": "fw01",
                              "details": "", "is_suggestion": True})
    window.change_view("grouped")
    # Meldungsboxen stürzen unter Windows ohne Bildschirm in Qt ab: Rückfrage ersetzen
    asked = []
    window.ask_document_first = lambda count: asked.append(count) or True  # "Nachtragen"
    window.request_quit()
    assert asked == [1], asked
    assert not window._quitting, "trotz „Nachtragen“ beendet"
    assert window.config["list_view"] == "doc"

    window.quit_app()


try:
    gui_test()
except BaseException:
    traceback.print_exc(file=sys.stdout)
    sys.stdout.flush()
    os._exit(1)
print("Nachtragen und Nachfragen ok")
sys.stdout.flush()
os._exit(0)
