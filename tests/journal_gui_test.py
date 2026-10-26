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
    # Global halten: Würde QApplication beim Verlassen der Funktion vor den Fenstern
    # aufgeräumt, stürzt Qt unter Windows ab (Zugriffsfehler).
    global app, window
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
    # Offenes fällt auf: Knopf in der Statuszeile, ein Klick öffnet das Eintragen
    button = window.open_docs_button
    assert not button.isHidden() and button.text().startswith("1 offen"), button.text()
    opened = []
    window.add_doc = lambda entry=None, minute=None: opened.append(entry)
    button.click()
    assert opened and opened[0].get("tv_id") == "987654321", opened
    del window.add_doc  # wieder die echte Methode

    # Rechtsklick-Menü: nur passende Befehle, gleiche Texte in Timeline und Tagesliste
    from timeline_only import entry_menu_items
    keys = lambda e: [i[1] for i in entry_menu_items(e) if i]
    assert keys(bands["doc"][0]) == ["add", "ignore"]
    tv_keys = keys(opened[0])
    assert "name_tv" in tv_keys and "reject" not in tv_keys and "delete" not in tv_keys, tv_keys

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
    # Abrechnungstakt neben der Dauer (35 min -> 0:45 h)
    assert "abgerechnet 0:45 h" in prompt.form.duration.text(), prompt.form.duration.text()
    prompt.form.text_edit.setPlainText("Outlook-Profil neu angelegt")
    prompt.save_btn.click()
    QTest.qWait(600)
    flush_deletes()
    items = window.journal.items(now.strftime("%Y-%m-%d"))
    assert [i["text"] for i in items] == ["Outlook-Profil neu angelegt"], items
    assert items[0]["customer"] == "Beispiel AG" and items[0]["source"] == "TeamViewer"
    assert window.config["teamviewer_names"]["987654321"] == "Beispiel AG"
    # Kundennamen sind Nutzdaten: verschlüsselt in der Datenbank, nicht in der Config-Datei
    assert window.data_store.get("teamviewer_names")["987654321"] == "Beispiel AG"
    with open(main_timeline.CONFIG_FILE, encoding="utf-8") as f:
        assert "teamviewer_names" not in json.load(f)
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
    # Abrechnungstakt (Standard 15 min, angefangene Viertelstunde): Kopie, Liste, Statuszeile
    assert "(35 min → abgerechnet 0:45 h)" in QApplication.clipboard().text(), QApplication.clipboard().text()
    assert "abgerechnet 0:45 h" in window.table.item(0, 2).text()
    assert "abgerechnet 0:45 h" in window.info_label.text(), window.info_label.text()
    window.config["billing_customers"] = {"beispiel ag": {"step": 30, "mode": "up"}}
    window.update_day_list(window.day_activities, window.pc_activities)
    window.table.selectRow(0)
    window.copy_selection()
    assert "abgerechnet 1:00 h" in QApplication.clipboard().text()
    window.config["billing_customers"] = {}
    window.config["billing_mode"] = "off"  # abschaltbar: genau wie bisher
    window.update_day_list(window.day_activities, window.pc_activities)
    window.table.selectRow(0)
    window.copy_selection()
    assert "abgerechnet" not in QApplication.clipboard().text()
    assert "abgerechnet" not in window.info_label.text() and window.table.item(0, 2).text() == "35 min"
    window.config["billing_mode"] = "up"

    # PC-Verlauf automatisch löschen: standardmäßig aus, eingeschaltet nur Alte weg
    import datastore
    store, name = datastore.locate(main_timeline.ACTIVITY_DIR, "row_files")
    old = (now - timedelta(days=200)).strftime("%Y-%m-%d")
    seg = {"start": f"{old} 09:00:00", "end": f"{old} 09:05:00", "app": "x.exe", "title": "alt"}
    store.append_many(name, [(old, seg)] * 3)
    window.retention.check(force=True)
    QTest.qWait(200)
    assert store.row_count(name, old) == 3, "trotz Standard „aus“ gelöscht"
    window.config["pc_history_purge"] = True
    window.retention.check(force=True)
    QTest.qWait(300)
    assert store.row_count(name, old) == 0, "alter PC-Verlauf nicht gelöscht"
    assert window.journal.items(now.strftime("%Y-%m-%d")), "Tätigkeiten dürfen bleiben"
    window.config["pc_history_purge"] = False
    window.update_day_list(window.day_activities, window.pc_activities)
    window.table.selectRow(0)
    # Ticket-Format „- “ / „-- “ beim Kopieren (Standard aus)
    window.config["ticket_format"] = "dash"
    window.copy_selection()
    assert "Fernwartung:\n- Outlook-Profil neu angelegt" in QApplication.clipboard().text()
    window.config["ticket_format"] = ""

    # Eintragen-Hilfen: Bausteine, letzte Texte zum Kunden, Ticket-Vorschlag aus dem PC-Verlauf
    pc = [{"start": t(start), "end": t(end), "type": "PC: Outlook", "app": "outlook.exe",
           "customer_name": "Systems - TCK0000049374 - Drucker"}]
    window.timeline.pc_entries_for = lambda date, min_seconds=30, max_gap=60: pc
    opts = window.entry_form_options(start, end)
    assert opts["ticket_suggestions"][0]["label"].startswith("TCK0000049374 (Outlook"), opts
    assert opts["recent_texts"]("Beispiel AG") == ["Outlook-Profil neu angelegt"]
    from journal_dialogs import PromptWindow
    helper = PromptWindow({"start": t(start), "end": t(end), "type": "TeamViewer",
                           "customer_name": ""}, [], [], parent=window, **opts)
    form = helper.form
    form.customer_edit.setCurrentText("Beispiel AG")
    form._fill_insert_menu()
    labels = [a.text() for a in form.insert_menu.actions()]
    assert "&1 Windows-Updates installiert" in labels, labels
    assert any("Outlook-Profil neu angelegt" in x for x in labels), labels
    form.text_edit.setPlainText("Drucker geprüft")
    form.text_edit.moveCursor(form.text_edit.textCursor().MoveOperation.End)
    form.insert_text("Windows-Updates installiert")
    assert form.text_edit.toPlainText() == "Drucker geprüft\nWindows-Updates installiert"
    form.outline_text()
    assert form.text_edit.toPlainText() == "- Drucker geprüft\n-- Windows-Updates installiert"
    # Ticket nur als Vorschlag: erst nach „Übernehmen“ im Eintrag
    assert form.item()["ticket"] == "" and form.ticket_take.isVisibleTo(helper)
    form.ticket_take.click()
    assert form.item()["ticket"] == "TCK0000049374" and not form.ticket_take.isVisibleTo(helper)
    helper._done = True
    helper.close()
    helper.deleteLater()
    flush_deletes()
    del window.timeline.pc_entries_for  # wieder die echte Methode

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
