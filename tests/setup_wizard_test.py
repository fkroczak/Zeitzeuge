"""Einrichtungsassistent: Auswahl, Schritte, Schalter wie im Menü, Abbrechen eines Dialogs.

Läuft ohne Bildschirm mit einem leeren Datenordner, als eigener Prozess (Skript).
Keine Browser-Leser starten: 3CX/ITM/Matrix42 werden nur mit ersetzten Dialogen geprüft.
"""
import faulthandler
import json
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
DATA = tempfile.mkdtemp()
os.environ["ZEITZEUGE_DATA"] = DATA
TV = os.path.join(DATA, "Connections.txt")
open(TV, "w").close()
with open(os.path.join(DATA, "zeitzeuge_config.json"), "w", encoding="utf-8") as f:
    json.dump({"teamviewer_paths": [TV], "rdm_paths": [os.path.join(DATA, "fehlt.log")],
               "sophos_connect_dirs": [os.path.join(DATA, "kein-sophos")],
               "vpn_paths": [os.path.join(DATA, "kein-vpn")],
               "tracking_enabled": False, "prompt_mode": "off"}, f)


def flush_deletes():
    """Gelöschte Fenster (deleteLater) jetzt wirklich löschen (Test läuft ohne app.exec())."""
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def gui_test():
    # Global halten: Würde QApplication beim Verlassen der Funktion vor den Fenstern
    # aufgeräumt, stürzt Qt unter Windows ab (Zugriffsfehler).
    global app, window, wizard
    import main_timeline
    import setup_wizard
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())
    window = main_timeline.TimelineApp()
    window.show()
    assert not window._wizard_pending, "Mit eigenem Datenordner (Tests) nie von selbst starten"

    wizard = setup_wizard.SetupWizard(window)
    wizard.show()
    c = wizard.choices
    # Vorauswahl: gefundene Dateien an, fehlende aus, Webseiten wie eingestellt (aus)
    assert c["teamviewer"].isChecked() and "(gefunden)" in c["teamviewer"].text()
    assert not c["rdm"].isChecked() and "(nicht gefunden)" in c["rdm"].text()
    assert not c["sophos"].isChecked() and not c["pbx"].isChecked() and not c["outlook"].isChecked()
    assert c["recovery"].isChecked(), "Ohne Wiederherstellungsschlüssel vorausgewählt"
    assert not wizard.back_button.isEnabled()

    # Auswahl: TeamViewer, Fenster, 3CX, Schlüssel; der Rest aus
    for sid, check in c.items():
        check.setChecked(sid in ("teamviewer", "tracking", "pbx", "recovery"))
    wizard.next()
    assert wizard.steps == ["teamviewer", "pbx", "tracking", "recovery"], wizard.steps
    assert window.config["rdm_enabled"] is False and not window.source_actions["rdm_enabled"].isChecked()
    assert window.config["sophos_enabled"] is False and window.config["vpn_enabled"] is False
    assert "Schritt 2 von 6" in wizard.step_label.text(), wizard.step_label.text()
    assert wizard.back_button.isEnabled()

    # TeamViewer: gefunden, verwenden bleibt an
    page = wizard.step_pages["teamviewer"]
    assert page.use.isChecked()
    wizard.next()

    # 3CX: Dialog abgebrochen -> Leser läuft nicht, Schalter bleibt aus
    calls = []
    window.open_pbx_settings = lambda: calls.append("pbx")
    wizard.run_setup("pbx")
    assert calls == ["pbx"]
    assert window.config["pbx_reader_enabled"] is False and window.pbx_reader is None
    assert "noch nicht eingerichtet" in wizard.step_pages["pbx"].state.text()
    wizard.step_pages["pbx"].use.setChecked(False)  # doch nicht: Weiter lässt 3CX aus
    wizard.next()
    assert window.pbx_reader is None and not window.config["pbx_reader_enabled"]

    # Fenster aufzeichnen: mit Weiter an, wie über das Menü
    assert window.tracker is None
    wizard.next()
    assert window.config["tracking_enabled"] and window.tracker is not None
    assert window.tracking_action.isChecked()

    # Wiederherstellungsschlüssel: Dialog bekommt den Assistenten als Eltern
    parents = []
    window.new_recovery_code = lambda parent=None: parents.append(parent)
    wizard.run_setup("recovery")
    assert parents == [wizard]
    wizard.next()

    # Übersicht und Fertig
    assert wizard.next_button.text() == "&Fertig"
    html = wizard.summary.text()
    assert "TeamViewer" in html and "Einrichtungsassistent" in html
    assert wizard.state_text("teamviewer") == "an" and wizard.state_text("rdm") == "aus"
    # Zurück auf die Auswahl und neu wählen: Seiten werden neu angelegt
    while wizard.index:
        wizard.back()
    for sid, check in c.items():
        check.setChecked(sid == "teamviewer")
    wizard.next()
    assert wizard.steps == ["teamviewer"] and wizard.stack.count() == 3
    assert not window.config["tracking_enabled"], "abgewählt: Aufzeichnung wieder aus"
    wizard.next()
    wizard.next()
    assert wizard.result() == wizard.DialogCode.Accepted
    wizard.deleteLater()
    flush_deletes()

    # Aus dem Menü: setzt setup_done, auch nach Abbrechen
    setup_wizard.SetupWizard.exec = lambda self: self.reject()
    window.config.pop("setup_done", None)
    window.show_setup_wizard()
    assert window.config["setup_done"] and not window._wizard_open
    with open(os.path.join(DATA, "zeitzeuge_config.json"), encoding="utf-8") as f:
        assert json.load(f)["setup_done"] is True
    flush_deletes()
    window.quit_app()


try:
    gui_test()
except BaseException:
    traceback.print_exc(file=sys.stdout)
    sys.stdout.flush()
    os._exit(1)
print("Einrichtungsassistent ok")
sys.stdout.flush()
os._exit(0)
