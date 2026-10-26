"""Kundenliste und Lernen aus Korrekturen in der Oberfläche (Nachfrage, Tagesliste, Menü).

Läuft ohne Bildschirm mit einem leeren Datenordner, als eigener Prozess (Skript).
Die Logik ohne Oberfläche prüft customers_test.py.
"""
import faulthandler
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

FMT = "%Y-%m-%d %H:%M:%S"


def t(dt):
    return dt.strftime(FMT)


def flush_deletes():
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def gui_test():
    global app, window
    import main_timeline  # noqa: E402
    from PySide6.QtTest import QTest  # noqa: E402
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())
    window = main_timeline.TimelineApp()
    window.tray.showMessage = lambda *a: None
    window.show()

    now = datetime.now().replace(microsecond=0)
    if now.hour == 0 and now.minute < 50:
        print("Kurz nach Mitternacht: Oberflächentest übersprungen")
        window.quit_app()
        return

    # Menü „Einstellungen“ hat den Eintrag „Kundenliste …“
    texts = [a.text() for a in window.menu_button.menu().actions()]
    assert "Kunden&liste …" in texts, texts

    # RDM-Verbindung ohne Kunde: Rechtsklick bietet „Kunde zuordnen …“
    rdm = {"start": t(now - timedelta(minutes=40)), "end": t(now - timedelta(minutes=20)),
           "type": "RDP-Verbindung", "customer_name": "srv01", "details": "", "is_suggestion": True}
    window.activities.append(rdm)
    window.timeline.draw_timeline(window.current_date)
    from timeline_only import entry_menu_items
    assert "assign_customer" in [i[1] for i in entry_menu_items(rdm) if i]
    assert "assign_customer" not in [i[1] for i in entry_menu_items(rdm, True) if i]

    # Nachfrage: Kunde und Kategorie ändern, beides merken
    window.check_prompts()
    prompt = window._prompt_window
    assert prompt is not None, "keine Nachfrage"
    form = prompt.form
    assert form.customer_edit.currentText() == "srv01"
    assert form.remember_tv.isHidden(), "Kunde nicht geändert: kein Haken nötig"
    assert form.learn_rule.isHidden()
    form.customer_edit.setCurrentText("Müller GmbH")
    assert not form.remember_tv.isHidden() and form.remember_tv.isChecked()
    assert "RDM-Eintrag „srv01“" in form.remember_tv.text()
    old_category = form.category_edit.currentText()
    new_category = next(c for c in window.categories() if c != old_category)
    form.category_edit.setCurrentText(new_category)
    assert not form.learn_rule.isHidden() and not form.learn_rule.isChecked(), "Regel nie ungefragt"
    assert new_category in form.learn_rule.text()
    form.learn_rule.setChecked(True)
    form.text_edit.setPlainText("Updates eingespielt")
    rules_before = len(window.config["rules"])
    prompt.save_btn.click()
    QTest.qWait(600)
    flush_deletes()

    assert window.customer_index().customer_for(rdm) == "Müller GmbH"
    assert len(window.config["rules"]) == rules_before + 1
    learned = [r for r in window.config["rules"] if r.get("learned")]
    assert learned and learned[0]["category"] == new_category
    assert "gemerkt" in window.statusBar().currentMessage(), window.statusBar().currentMessage()
    # Nutzdaten: Kundenliste verschlüsselt in der Datenbank, nicht in der Config-Datei
    stored = window.data_store.get("kunden")
    assert stored and stored[0]["name"] == "Müller GmbH", stored
    with open(main_timeline.CONFIG_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    assert "customers" not in saved and "teamviewer_names" not in saved
    # Gelernte Regeln nennen Kunden: nur in der Datenbank, die Datei hat die übrigen Regeln
    assert not any(r.get("learned") for r in saved["rules"]), "gelernte Regel im Klartext"
    assert "Müller GmbH" not in json.dumps(saved, ensure_ascii=False)
    stored_rules = window.data_store.get("regeln")
    assert stored_rules[0].get("learned"), "gelernte Regel vor den Standardregeln"
    reloaded = main_timeline.load_config_with_defaults()
    assert reloaded["rules"] == window.config["rules"], "Regeln nach dem Neuladen anders"
    # Ausnahmen des Abrechnungstakts (Kundennamen) ebenfalls nur in der Datenbank
    window.config["billing_customers"] = {"Geheim AG": {"step": 30, "mode": "up"}}
    main_timeline.save_config(window.config)
    with open(main_timeline.CONFIG_FILE, encoding="utf-8") as f:
        assert "Geheim AG" not in f.read()
    assert main_timeline.load_config_with_defaults()["billing_customers"] == {
        "Geheim AG": {"step": 30, "mode": "up"}}
    # Datei von Hand geändert (Regel entfernt): gelernte Regeln bleiben, Datei gilt
    with open(main_timeline.CONFIG_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    raw["rules"] = raw["rules"][1:]
    with open(main_timeline.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(raw, f)
    merged = main_timeline.load_config_with_defaults()["rules"]
    assert merged[0].get("learned") and len(merged) == len(window.config["rules"]) - 1, merged[:2]
    main_timeline.save_config(window.config)  # Stand des Tests wiederherstellen

    # Tagesliste zeigt den Kunden zur Verbindung
    window.change_view("single")
    texts = [window.table.item(r, 4).text() for r in range(window.table.rowCount())]
    assert "Müller GmbH · srv01" in texts, texts

    # Nächste Verbindung zu srv01: Kunde und Kategorie kommen von selbst
    rdm2 = dict(rdm, start=t(now - timedelta(minutes=12)), end=t(now - timedelta(minutes=4)))
    window.activities.append(rdm2)
    window._prompt_asked.clear()
    window.check_prompts()
    prompt = window._prompt_window
    assert prompt is not None
    assert prompt.form.customer_edit.currentText() == "Müller GmbH"
    assert prompt.form.category_edit.currentText() == new_category
    prompt._answer("ignore")
    QTest.qWait(600)
    flush_deletes()

    # Dialog „Kundenliste“: Spur hinzufügen, umbenennen, übernehmen
    import customers_dialogs
    dialog = customers_dialogs.CustomersDialog(window.config, window)
    assert dialog.customer_list.count() == 1
    assert dialog.add_trace("phone", "+49 711 123456")
    assert not dialog.add_trace("tv", "abc") and "⚠" in dialog.message.text()
    assert dialog.add_trace("tv", "123 456 789")
    assert dialog.rename_customer("Müller AG")
    assert dialog.add_customer("Meier KG") and not dialog.add_customer("meier kg")
    dialog.apply()
    main_timeline.save_config(window.config)
    assert window.config["teamviewer_names"] == {"123456789": "Müller AG"}
    call = {"start": t(now), "end": t(now), "type": "Telefonat",
            "customer_name": "Max (0711 123456)", "phone": "0711 123456"}
    assert window.customer_index().customer_for(call) == "Müller AG"
    assert window.data_store.get("teamviewer_names") == {"123456789": "Müller AG"}

    # „TeamViewer-ID benennen …“ bleibt und hält die Kundenliste gleich
    from PySide6.QtWidgets import QInputDialog
    QInputDialog.getText = staticmethod(lambda *a, **k: ("Neu GmbH", True))
    window.name_teamviewer_id({"tv_id": "123456789"})
    names = {c["name"]: c for c in window.config["customers"]}
    assert any(t["value"] == "123456789" for t in names["Neu GmbH"]["traces"])
    assert not any(t["kind"] == "tv" for t in names["Müller AG"]["traces"])
    dialog.close()

    # Merken-Haken dürfen das Textfeld nicht vorbelegen (Text bleibt leer bzw. wie übergeben)
    import journal_dialogs
    for trace in (("tv", "123456789"), ("rdm", "srv01")):
        d = journal_dialogs.EntryDialog(datetime(2026, 10, 20, 9), datetime(2026, 10, 20, 9, 30),
                                        ["Müller AG"], ["Fernwartung"], trace=trace,
                                        rule_subject="srv01", parent=window)
        assert d.form.text_edit.toPlainText() == "", d.form.text_edit.toPlainText()
        d.close()

    window.quit_app()


try:
    gui_test()
except BaseException:
    traceback.print_exc(file=sys.stdout)
    sys.stdout.flush()
    os._exit(1)
print("Kundenliste ok")
sys.stdout.flush()
os._exit(0)
