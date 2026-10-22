"""Tätigkeiten nachtragen, offene erkennen, nachfragen und erinnern.

Läuft ohne Bildschirm mit einem leeren Datenordner.
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

import journal  # noqa: E402
from journal import Journal, entry_key, ticket_line  # noqa: E402

FMT = "%Y-%m-%d %H:%M:%S"


def t(dt):
    return dt.strftime(FMT)


# --------------------------------------------------------------- Ablage (ohne Oberfläche)

folder = tempfile.mkdtemp()
j = Journal(folder)
day = "2026-10-20"
tv = {"start": f"{day} 10:00:00", "end": f"{day} 10:40:00", "type": "TeamViewer",
      "customer_name": "TeamViewer 123 456 789", "tv_id": "123456789"}
call = {"start": f"{day} 11:00:00", "end": f"{day} 11:03:00", "type": "Telefonat",
        "customer_name": "Max (0711 1234)", "direction": "Eingehend"}
vpn = {"start": f"{day} 12:00:00", "end": f"{day} 13:00:00", "type": "VPN-Verbindung",
       "customer_name": "Kunde X", "running": True}
now = datetime(2026, 10, 20, 18, 0)

open_ = j.open_items([tv, call, vpn], day, min_minutes=5, now=now)
assert open_ == [tv], open_  # Anruf zu kurz, VPN läuft noch

item = j.add({"start": f"{day} 10:00:00", "end": f"{day} 10:30:00", "customer": "Müller GmbH",
              "category": "Fernwartung", "text": "Drucker eingerichtet"})
assert j.open_items([tv], day, now=now) == [], "zu 3/4 dokumentiert gilt als erledigt"
assert ticket_line(item) == "10:00–10:30 (30 min)  Müller GmbH · Fernwartung: Drucker eingerichtet"

# Neu laden von der Platte
j2 = Journal(folder)
assert [i["text"] for i in j2.items(day)] == ["Drucker eingerichtet"]
assert j2.customers(today=datetime(2026, 10, 21)) == ["Müller GmbH"]

# Ändern auf einen anderen Tag verschiebt die Datei
moved = j2.update(item, {"start": "2026-10-21 08:00:00", "end": "2026-10-21 08:30:00"})
assert j2.items(day) == [] and j2.items("2026-10-21")[0]["id"] == moved["id"]
j2.delete(moved)
assert j2.items("2026-10-21") == []

# Ende vor Beginn wird abgelehnt
try:
    j2.add({"start": f"{day} 10:00:00", "end": f"{day} 09:00:00"})
    raise AssertionError("ungültige Zeit gespeichert")
except ValueError:
    pass

# Ignorieren
j2.ignore(tv)
assert j2.is_ignored(tv) and j2.open_items([tv], day, now=now) == []
assert entry_key(tv) == f"TeamViewer|123456789|{day} 10:00"

# Kaputte Tagesdatei: beiseitelegen, nicht überschreiben
bad = os.path.join(folder, "2026-10-19.json")
with open(bad, "w", encoding="utf-8") as f:
    f.write('{"items": [ {kaputt')
j3 = Journal(folder)
assert j3.items("2026-10-19") == []
assert any(n.startswith("2026-10-19.json.defekt-") for n in os.listdir(folder)), os.listdir(folder)

# Vorschläge für Kunde und Kategorie
cats = ["Fernwartung", "Telefonsupport", "Zugangsdaten / Sicherheit"]
assert journal.suggest_category(tv, cats) == "Fernwartung"
assert journal.suggest_category(call, cats) == "Telefonsupport"
assert journal.suggest_customer(call) == "Max"
assert journal.suggest_customer({"customer_name": "+49 711 1234"}) == ""
assert journal.suggest_customer(tv, {"123456789": "Müller GmbH"}) == "Müller GmbH"
print("Ablage ok")

def flush_deletes():
    """Gelöschte Fenster (deleteLater) jetzt wirklich löschen. In der App passiert das in der
    Ereignisschleife; der Test läuft ohne app.exec_(), sonst geschähe es erst im nächsten Dialog."""
    from PyQt5.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def gui_test():
    # --------------------------------------------------------------- Oberfläche

    import main_timeline  # noqa: E402
    from PyQt5.QtCore import QTimer  # noqa: E402
    from PyQt5.QtTest import QTest  # noqa: E402
    from PyQt5.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

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
