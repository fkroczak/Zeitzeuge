"""Kleinere Dialoge im Stil der Nachfrage-Karte (card_dialog.modernize).

Je Dialog: Kopf mit Namen und kurzem Untertitel, Knöpfe in der Fußleiste (auch nach einer
Stiländerung, die QDialogButtonBox sonst zum Zurückholen nutzt), genau eine Hauptaktion,
Abbrechen/Speichern lösen weiter dasselbe aus, Formulare mit Beschriftung über dem Feld,
lange Einleitungen weg, Blättern im Tages- und Wochenabschluss, beide Designs.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import faulthandler
import os
import sys
import tempfile
import traceback
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()


def gui_test():
    global app, window
    import main_timeline
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFormLayout, QPushButton,
                                   QSystemTrayIcon)

    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())
    main_timeline.install_translator(app)
    window = main_timeline.TimelineApp()
    window.tray.showMessage = lambda *a: None
    window.show()

    import billing_dialogs
    import customers_dialogs
    import day_close_dialog
    import settings_dialogs
    import snippets_dialogs
    import travel_dialogs
    import week_dialogs
    today = date.today().strftime("%Y-%m-%d")
    cfg = window.config

    # Name im Kopf, Hauptaktion (Text) oder None (nur Schließen)
    builders = {
        "Kundenliste": (lambda: customers_dialogs.CustomersDialog(cfg, window), "Speichern"),
        "Textbausteine": (lambda: snippets_dialogs.SnippetsDialog(cfg, window), "Speichern"),
        "Abrechnung": (lambda: billing_dialogs.BillingDialog(cfg, ["Praxis Weber"], window), "Speichern"),
        "Regeln ohne KI": (lambda: settings_dialogs.RulesDialog(cfg, window), "Speichern"),
        "KI-Vorschläge": (lambda: settings_dialogs.AiSettingsDialog(cfg, 0.0, window), "Speichern"),
        "Fenster-Filter": (lambda: settings_dialogs.TrackingFilterDialog(cfg, main_timeline.ACTIVITY_DIR, window),
                           "Speichern"),
        "Orte und Fahrzeiten": (lambda: travel_dialogs.TravelSettingsDialog(cfg, ["Praxis Weber"], window),
                                "Speichern"),
        "Schutz deiner Daten": (window.build_protection_dialog, None),
        "Tagesabschluss": (lambda: day_close_dialog.DayCloseDialog(window, today, window),
                           "Dokumentieren und buchen"),
        "Wochenabschluss": (lambda: week_dialogs.WeekDialog(window, today), "Tag in Matrix42 buchen …"),
    }

    def visible_buttons(dialog):
        return [b for b in dialog.findChildren(QPushButton) if b.isVisible()]

    for dark in (False, True):
        window.set_theme("dark" if dark else "light", save=False)
        for name, (build, main) in builders.items():
            dialog = build()
            dialog.show()
            QTest.qWait(30)
            assert dialog.property("card") is True, name
            # Kopf: Name statt Frage, kurzer Untertitel
            assert dialog.card_title.full_text() == name and not name.endswith("?"), name
            subtitle = dialog.card_subtitle.text()
            assert subtitle and len(subtitle) <= 120, (name, subtitle)
            # Fußleiste: keine sichtbare Knopfleiste mehr, Knöpfe bleiben auch nach einer Stiländerung unten
            assert not [b for b in dialog.findChildren(QDialogButtonBox) if b.isVisible()], name
            dialog.setStyleSheet("QPushButton { }")
            QTest.qWait(20)
            foot = dialog.card_foot.parentWidget()
            in_foot = [b.text().replace("&", "") for b in foot.findChildren(QPushButton) if b.isVisible()]
            assert in_foot, name
            # genau eine Hauptaktion (Schutz: keine, nur Schließen)
            defaults = [b.text().replace("&", "") for b in visible_buttons(dialog) if b.isDefault()]
            assert defaults == ([main] if main else []), (name, defaults)
            if main:
                assert in_foot[-1] == main, (name, in_foot)
            assert not any(t in ("OK", "Cancel", "Close") for t in in_foot), (name, in_foot)
            assert ("Abbrechen" in in_foot) or ("Schließen" in in_foot), (name, in_foot)
            dialog.setStyleSheet("")
            dialog.reject()
            dialog.deleteLater()

    # Abbrechen und Speichern lösen weiter dasselbe aus (Signale der Knopfleiste)
    dialog = snippets_dialogs.SnippetsDialog(cfg, window)
    dialog.show()
    next(b for b in visible_buttons(dialog) if b.text() == "Abbrechen").click()
    assert dialog.result() == QDialog.Rejected
    dialog = billing_dialogs.BillingDialog(cfg, ["Praxis Weber"], window)
    dialog.show()
    next(b for b in visible_buttons(dialog) if b.text().replace("&", "") == "Speichern").click()
    assert QDialog.result(dialog) == QDialog.Accepted  # BillingDialog.result() liefert die Regeln
    # Enter löst die Hauptaktion aus
    dialog = snippets_dialogs.SnippetsDialog(cfg, window)
    dialog.show()
    dialog.activateWindow()
    QTest.keyClick(dialog, Qt.Key_Return)
    assert dialog.result() == QDialog.Accepted

    # Beschriftung über dem Feld, ohne Doppelpunkt
    dialog = billing_dialogs.BillingDialog(cfg, ["Praxis Weber"], window)
    forms = dialog.findChildren(QFormLayout)
    assert forms and all(f.rowWrapPolicy() == QFormLayout.WrapAllRows for f in forms)
    label = forms[0].itemAt(0, QFormLayout.LabelRole).widget()
    assert not label.text().endswith(":"), label.text()

    # Regeln und Fenster-Filter: lange Einleitung weg, kurzer Untertitel stattdessen
    for dialog in (settings_dialogs.RulesDialog(cfg, window),
                   settings_dialogs.TrackingFilterDialog(cfg, main_timeline.ACTIVITY_DIR, window)):
        dialog.show()
        assert not dialog.intro.isVisible() and dialog.card_subtitle.isVisible()
        dialog.reject()

    # Kundenliste: „+ Neuer Kunde“ im Kopf, alte Überschrift weg
    dialog = customers_dialogs.CustomersDialog(cfg, window)
    dialog.show()
    assert dialog.new_btn.parentWidget() is dialog.card_head.parentWidget()
    assert not [w for w in dialog.findChildren(type(dialog.card_subtitle))
                if w.objectName() == "page_title" and w.isVisible()]
    dialog.reject()

    # Tagesabschluss: Datum als Untertitel, Blättern im Kopf als Linien-Icons mit Namen
    dialog = day_close_dialog.DayCloseDialog(window, today, window)
    dialog.show()
    assert "Tagesabschluss" not in dialog.card_subtitle.text() and today[-2:] in dialog.card_subtitle.text()
    for button in (dialog.prev_button, dialog.next_button):
        assert not button.text() and not button.icon().isNull() and button.accessibleName()
    before = dialog.card_subtitle.text()
    dialog.prev_button.click()
    assert dialog.card_subtitle.text() != before, "Untertitel folgt dem Tag"
    dialog.reject()
    dialog = week_dialogs.WeekDialog(window, today)
    dialog.show()
    assert dialog.card_subtitle.text().startswith("Woche ")
    dialog.reject()

    window.quit_app()
    print("Dialoge im Karten-Stil: OK")


try:
    gui_test()
except Exception:
    traceback.print_exc()
    sys.stdout.flush()
    os._exit(1)
sys.stdout.flush()
os._exit(0)
