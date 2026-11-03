"""Menüs „Ansicht“ und „Einstellungen“, Einstellungsfenster, Hilfe zu den Ansichten, Anruffarben.

Läuft ohne Bildschirm mit einem leeren Datenordner, als eigener Prozess (Skript).
"""
import faulthandler
import os
import sys
import tempfile
import traceback

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
    from PySide6.QtWidgets import QApplication, QPushButton, QSystemTrayIcon, QToolButton

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
    # Heute, Ganzer Tag, Arbeitszeit nur als Symbol; PC-Verlauf und Wochenabschluss nur im Menü
    assert window._today_button.toolButtonStyle() == Qt.ToolButtonIconOnly
    bar = window.tools_bar.actions()
    assert window.pc_list_action not in bar and window.week_action not in bar
    assert bar.index(window.doc_button_action) < bar.index(window.ai_button_action)
    assert window.tools_bar.widgetForAction(window.whole_day_action).toolButtonStyle() == Qt.ToolButtonIconOnly

    # Ansicht: Ansichten mit Hilfe, Zeilen als Untermenü (auch per Rechtsklick auf die Legende).
    # Zeitraum steht nur in der Werkzeugleiste, Design in den Einstellungen.
    menu = window.view_button.menu()
    texts = [a.text().replace("&", "").split("\t")[0] for a in menu.actions()]
    for text in ("Zusammengefasst", "Einzeln", "Was zeigen die Ansichten? …", "Zeilen der Timeline",
                 "Wochenabschluss …"):
        assert text in texts, (text, texts)
    for text in ("Dunkles Design", "Ganzer Tag", "Arbeitszeit"):
        assert text not in texts, (text, texts)
    # Einträge ohne Überschriften. 15 seit dem Tagesabschluss (Gruppe „Übersichten“ hat 3 von 5),
    # 16 seit der Ansicht „Telefonate“
    assert len([t for t in texts if t]) <= 16, texts
    assert "Tagesabschluss …" in texts, texts
    settings_texts = [a.text().replace("&", "") for a in window.menu_button.menu().actions()]
    assert "Dunkles Design" in settings_texts and "Datenquellen …" in settings_texts, settings_texts
    # PC-Aktivität: Arbeitsblöcke <-> jedes Fenster, im Menü Ansicht und im Menü der Zeilen
    assert "PC-Aktivität als Arbeitsblöcke" in texts, texts
    assert any(a.text().replace("&", "") == "PC-Aktivität als Arbeitsblöcke"
               for a in window.rows_menu.actions())
    window._check_proxies[window.pc_blocks_action].trigger()
    assert window.config["pc_blocks"] is False and not window.pc_blocks_action.isChecked()
    window._rows_blocks_proxy.trigger()
    assert window.config["pc_blocks"] is True and window.pc_blocks_action.isChecked()
    # Zoom-Knöpfe: nur Ganzer Tag und Arbeitszeit, feiner per Tastatur/Strg+Mausrad
    assert window.zoom_in_action not in bar and window.zoom_out_action not in bar
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
    assert pages[:3] == ["Allgemein", "Ansicht", "Datenquellen"], pages

    # Seite Ansicht: Vorschau mit Beispieltag, Varianten beim Darüberfahren, Änderungen sofort
    settings.show_page("view")
    QTest.qWait(50)
    preview = settings.preview
    assert preview is not None and preview.isVisible()
    assert preview.table.rowCount() >= 5 and preview.timeline._legend, "Vorschau leer"
    row = next(r for r in settings.rows if r.spec[5] == "pc_blocks_action")
    QTest.mouseMove(row, row.rect().center())
    settings.preview_hover(row.spec)  # wie enterEvent
    assert preview.variant and preview.timeline.config["pc_blocks"] is False, preview.variant
    assert window.config.get("pc_blocks", True) is True, "Darüberfahren darf nichts speichern"
    assert not any(p.get("pc_block") for p in preview.timeline._pc_band)
    settings.preview_hover(None)
    assert preview.variant is None and any(p.get("pc_block") for p in preview.timeline._pc_band)
    # Vorschau bleibt sichtbar und kräftig, auch ohne Maus darüber (nicht verblasst)
    assert preview.timeline.isVisible() and preview.timeline.graphicsEffect() is None
    # Ansicht „Telefonate“: nur Anrufe
    preview.show_variant({"list_view": "calls"}, "Telefonate")
    kinds = [preview.table.item(r, 2).text() for r in range(preview.table.rowCount())]
    assert kinds and all(k.startswith("Telefonat") or k == "Teams-Anruf" for k in kinds), kinds
    preview.show_variant(None)
    assert "calls" in window.view_actions and "calls" in dict(window.VIEWS)
    # Auswahl: schon beim Durchgehen der Liste, gespeichert erst beim Wählen
    combo = next(r for r in settings.rows if r.spec[5] == "list_view").control
    single = combo.findData("single")
    combo.highlighted.emit(single)
    assert preview.timeline.config["list_view"] == "single" and window.config.get("list_view") != "single"
    rows_grouped = preview.table.rowCount()
    combo.activated.emit(single)
    QTest.qWait(20)
    assert window.config["list_view"] == "single" and preview.variant is None
    assert window.view_actions["single"].isChecked(), "Hauptfenster folgt der Auswahl"
    assert preview.table.rowCount() >= rows_grouped
    window.change_view("grouped")
    # Zahl ändern wirkt sofort auf die Vorschau
    spin = next(r for r in settings.rows if r.spec[5] == "merge_gap_minutes").control
    spin.setValue(0)
    QTest.qWait(20)
    assert preview.timeline.config["merge_gap_minutes"] == 0
    spin.setValue(5)
    # Zeitraum beim Start
    combo = next(r for r in settings.rows if r.spec[5] == "timeline_range").control
    combo.activated.emit(combo.findData("day"))
    QTest.qWait(20)
    assert window.config["timeline_range"] == "day" and window.timeline.fit_day
    combo.activated.emit(combo.findData("work"))

    # Datenquellen: Kacheln schalten dieselben Aktionen wie das Menü
    settings.show_page("sources")
    tile = next(t for t in settings.tiles if t.spec[0] == "rdm_enabled")
    assert tile.switch.isChecked() and tile.switch.text() == "An"
    tile.switch.setChecked(False)
    assert not window.source_actions["rdm_enabled"].isChecked() and window.config["rdm_enabled"] is False
    assert tile.state == "off" and tile.switch.text() == "Aus"
    window.source_actions["rdm_enabled"].setChecked(True)  # von außen: Kachel zieht mit
    assert tile.switch.isChecked() and tile.state != "off"

    # Fehlersuche & Analyse: Mitschnitte stehen hier, nicht mehr in den Einrichtungsdialogen
    settings.show_page("debug")
    debug_rows = [r.spec[3] for r in settings.rows if r.spec[0] == "debug"]
    assert "Matrix42: Buchung mitschneiden" in debug_rows and "3CX: Direkt-Abfrage prüfen" in debug_rows
    m42_dialog = window.build_reader_dialog("m42")
    assert not [b for b in m42_dialog.findChildren(QPushButton) if "mitschneiden" in b.text()]
    m42_dialog.deleteLater()
    calls = []
    window.record_source = lambda kind, booking=False: calls.append((kind, booking))
    next(r for r in settings.rows if r.spec[3] == "Matrix42: Buchung mitschneiden").control.click()
    assert calls == [("m42", True)], calls

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
