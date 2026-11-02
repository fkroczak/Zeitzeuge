"""Menüs „Ansicht“ und „Einstellungen“, Einstellungsfenster, Hilfe zu den Ansichten, Anruffarben.

Läuft ohne Bildschirm mit einem leeren Datenordner, als eigener Prozess (Skript).
"""
import faulthandler
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()


def gui_test():
    global app, window
    import main_timeline
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QToolButton

    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())
    window = main_timeline.TimelineApp()
    window.tray.showMessage = lambda *a: None
    window.resize(1300, 800)
    window.show()
    QTest.qWait(200)

    # Schnellzugriffe bleiben in der Werkzeugleiste: Tag zurück/vor, Heute, Ganzer Tag, Arbeitszeit
    tips = [a.toolTip() for a in window.findChildren(type(window.whole_day_action))]
    for text in ("Vorheriger Tag", "Nächster Tag", "Heute zeigen", "Ganzen Tag zeigen", "Arbeitszeit des Tages"):
        assert any(t.startswith(text) for t in tips), (text, tips)
    assert window._today_button.toolButtonStyle() == Qt.ToolButtonTextBesideIcon

    # Ansicht: Ansichten mit Hilfe, Zeilen mit sichtbarem Kästchen, Design
    menu = window.view_button.menu()
    texts = [a.text().replace("&", "").split("\t")[0] for a in menu.actions()]
    for text in ("Zusammengefasst", "Einzeln", "Was zeigen die Ansichten? …", "Dunkles Design",
                 "Ganzer Tag", "Wochenabschluss …"):
        assert text in texts, (text, texts)
    assert "5 Minuten" in window.view_actions["grouped"].toolTip()
    assert "Logs" in window.view_actions["single"].toolTip()
    proxy = window._check_proxies[window.row_actions["doc"]]
    proxy.trigger()
    assert not window.row_actions["doc"].isChecked() and not window.config["timeline_rows"]["doc"]
    proxy.trigger()
    assert window.row_actions["doc"].isChecked()

    # Einstellungen: Klick öffnet das Fenster, Strg+, ebenso
    window.menu_button.click()
    settings = window._settings_window
    assert settings is not None and settings.isVisible()
    pages = [settings.nav.item(i).text() for i in range(settings.nav.count())]
    assert pages[:2] == ["Allgemein", "Datenquellen"], pages

    # Datenquellen: Kacheln schalten dieselben Aktionen wie das Menü
    settings.show_page("sources")
    tile = next(t for t in settings.tiles if t.spec[0] == "rdm_enabled")
    assert tile.switch.isChecked() and tile.switch.text() == "An"
    tile.switch.setChecked(False)
    assert not window.source_actions["rdm_enabled"].isChecked() and window.config["rdm_enabled"] is False
    assert tile.state == "off" and tile.switch.text() == "Aus"
    window.source_actions["rdm_enabled"].setChecked(True)  # von außen: Kachel zieht mit
    assert tile.switch.isChecked() and tile.state != "off"

    # Grenzwert ändern wirkt sofort
    row = next(r for r in settings.rows if r.spec[5] == "idle_prompt_minutes")
    row.control.setValue(25)
    assert window.config["idle_prompt_minutes"] == 25 and window.idle_watch.minutes == 25

    # Suche findet über Bereiche hinweg, auch über die Einheit
    settings.search.setText("minuten")
    assert settings.results_found >= 5, settings.results_found
    settings.search.setText("pin")
    assert settings.results_found >= 1
    settings.search.setText("vpn")
    assert settings.results_found >= 2
    settings.search.clear()
    assert settings.stack.currentIndex() != settings.results_index

    # Dunkles Design aus dem Fenster: Fenster baut sich neu auf und bleibt offen
    next(r for r in settings.rows if r.spec[5] == "dark_action").control.setChecked(True)
    QTest.qWait(50)
    assert window.dark_mode and window._settings_window is not None and window._settings_window.isVisible()

    # Hilfe zu den Ansichten
    from view_help import ViewHelpDialog
    help_dialog = ViewHelpDialog(window.VIEWS, window.config, "#000000", "grouped", window)
    help_dialog.show()
    help_dialog.close()

    # Anrufe: ein- und ausgehend verschieden gefärbt, mit Pfeil
    from timeline_only import CALL_MARKS, entry_color
    incoming = entry_color({"type": "Telefonat", "direction": "Eingehend"}, window.config)
    outgoing = entry_color({"type": "Telefonat", "direction": "Ausgehend"}, window.config)
    assert incoming.name() != outgoing.name()
    def lum(c):
        ch = [v / 255 for v in (c.red(), c.green(), c.blue())]
        ch = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    light, dark = sorted((lum(incoming), lum(outgoing)))
    assert (dark + 0.05) / (light + 0.05) > 1.8, "nur am Farbton unterscheidbar"
    assert CALL_MARKS["Eingehend"] != CALL_MARKS["Ausgehend"]

    # Schmales Fenster: Ansicht und Einstellungen bleiben sichtbar
    window.resize(640, 480)
    QTest.qWait(150)
    assert window.view_button.isVisible() and window.menu_button.isVisible()
    assert isinstance(window.view_button, QToolButton)
    window.quit_app()
    print("Menüs und Einstellungen: OK")


try:
    gui_test()
except Exception:
    traceback.print_exc()
    sys.stdout.flush()
    os._exit(1)
sys.stdout.flush()
os._exit(0)
