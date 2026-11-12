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
    for text in ("<b>Vorheriger Tag</b>", "<b>Nächster Tag</b>", "Heute zeigen", "Ganzen Tag zeigen",
                 "Arbeitszeit des Tages"):
        assert any(text in t for t in tips), (text, tips)
    # Jeder Knopf der Werkzeugleiste nennt im Hinweis zuerst seinen Namen (nur Symbol sichtbar)
    for action in window.tools_bar.actions():
        if action.text() and not action.isSeparator():
            assert action.toolTip().startswith(f"<b>{action.text()}</b>"), action.toolTip()
    # Heute, Ganzer Tag, Arbeitszeit nur als Symbol; PC-Verlauf und Wochenabschluss nur im Menü
    assert window._today_button.toolButtonStyle() == Qt.ToolButtonIconOnly
    bar = window.tools_bar.actions()
    assert window.pc_list_action not in bar and window.week_action not in bar
    assert bar.index(window.doc_button_action) < bar.index(window.ai_button_action)
    assert window.tools_bar.widgetForAction(window.whole_day_action).toolButtonStyle() == Qt.ToolButtonIconOnly

    # Ansicht: Hilfe zu den Ansichten, Zeilen als Untermenü (auch per Rechtsklick auf die Legende).
    # Die Ansichten selbst stehen nur als Chips über der Liste, Zeitraum nur in der Werkzeugleiste,
    # Design in den Einstellungen.
    menu = window.view_button.menu()
    texts = [a.text().replace("&", "").split("\t")[0] for a in menu.actions()]
    for text in ("Was zeigen die Ansichten? …", "Zeilen der Timeline", "Wochenabschluss …",
                 "Hell", "Dunkel", "Eigene Farben …", "Darstellung anpassen …"):
        assert text in texts, (text, texts)
    # „Eigene Farben festlegen …“ entfällt: „Eigene Farben …“ öffnet gleich die Farben
    assert "Eigene Farben festlegen …" not in texts, texts
    for text in ("Zusammengefasst", "Einzeln", "Ganzer Tag", "Arbeitszeit"):
        assert text not in texts, (text, texts)
    # Design direkt im Menü Ansicht: Hell/Dunkel ziehen den Schalter „Dunkles Design“ mit
    was_dark = window.dark_mode
    window.theme_actions["light" if was_dark else "dark"].trigger()
    assert window.dark_mode is (not was_dark) and window.dark_action.isChecked() is (not was_dark)
    assert window.config["dark_mode"] is (not was_dark)
    window.theme_actions["dark" if was_dark else "light"].trigger()
    assert window.dark_mode is was_dark
    # Eigene Farben: Grundfarben gelten, der Rest wird abgeleitet; Hell/Dunkel schaltet zurück
    import theme
    window.config["custom_colors"] = {**theme.default_custom_colors("dark"), "accent": "#C4C7C5",
                                      "band": "#3C3C3C"}
    window.theme_actions["custom"].trigger()  # öffnet die Farben im Einstellungsfenster
    assert window.dark_mode and window.current_theme_key() == "custom"
    assert window._settings_window.current_page() == "view"
    window._settings_window.show_page("home")
    window._settings_window.hide()
    assert theme.theme_for(window.config)["accent"] == "#C4C7C5"
    assert window.theme_actions["custom"].font().bold()
    window.dark_action.setChecked(False)  # Schalter in den Einstellungen: zurück zum Standard
    assert window.current_theme_key() == "light" and not window.config["custom_theme"]
    window.set_theme("dark" if was_dark else "light")
    chips = window.view_chips.buttons
    assert set(chips) == set(dict(window.VIEWS)), "jede Ansicht hat einen Chip"
    chips["rules"][0].click()
    assert window.config["list_view"] == "rules" and chips["rules"][0].isChecked()
    assert not chips["grouped"][0].isChecked()
    window.change_view("grouped")
    # Einträge ohne Überschriften. 15 seit dem Tagesabschluss (Gruppe „Übersichten“ hat 3 von 5),
    # 16 seit der Ansicht „Telefonate“
    assert len([t for t in texts if t]) <= 16, texts
    assert "Tagesabschluss …" in texts, texts
    settings_texts = [a.text().replace("&", "") for a in window.menu_button.menu().actions()]
    # Design wählt man im Menü Ansicht (Wie Windows, Hell, Dunkel, Eigene Farben), nicht doppelt hier
    assert "Dunkles Design" not in settings_texts and "Aufzeichnung …" in settings_texts, settings_texts
    assert "Nachfragen …" in settings_texts and "Datenquellen …" not in settings_texts, settings_texts
    # PC-Aktivität: Arbeitsblöcke <-> jedes Fenster, nur im Menü der Zeilen (nicht doppelt in Ansicht)
    assert "PC-Aktivität als Arbeitsblöcke" not in texts, texts
    assert any(a.text().replace("&", "") == "PC-Aktivität als Arbeitsblöcke"
               for a in window.rows_menu.actions())
    # Zeilen der Timeline: Hinweise als Tooltip, keine grauen Zeilen mehr im Menü
    assert not [a for a in window.rows_menu.actions() if not a.isEnabled() and a.text()]
    window._rows_blocks_proxy.trigger()
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
    assert pages == ["Übersicht", "Aufzeichnung", "Nachfragen", "Zuordnung", "Buchung", "Darstellung",
                     "Datenschutz", "Info"], pages
    assert not any("&" in p for p in pages), "Bereiche heißen mit einem Wort, ohne „&“"
    assert settings.current_page() == "home"
    # Jede Einstellung genau einmal (außer den Abkürzungen auf der Übersicht)
    from settings_window import ROWS, row_page
    titles = [spec[3] for spec in ROWS if row_page(spec) != "home"]
    assert len(titles) == len(set(titles)), sorted(t for t in titles if titles.count(t) > 1)
    # Übersicht: Zustand je Bereich, Knopf springt hin
    settings.refresh_status()
    assert set(settings.status) == {"sources", "prompts", "booking", "data"}
    assert "Quellen an" in settings.status["sources"][1].full_text()
    # Gelbes Zeichen erklärt sich im Tooltip: welche Quelle, warum
    state, _words, why = settings._status_text("sources")
    mark, text = settings.status["sources"]
    if state == "warn":
        assert "Mit Problem:" in why and why in mark.toolTip() and why in text.toolTip()
    assert settings._status_text("data")[2], "Datenschutz begründet seinen Zustand"
    settings.show_page("general")  # alter Name leitet weiter
    assert settings.current_page() == "home"

    # Seite Darstellung: keine Vorschau oben, Auswahl über Kacheln, Änderungen sofort
    settings.show_page("view")
    QTest.qWait(50)
    assert not hasattr(settings, "preview"), "Vorschau oben ist entfallen"
    row = next(r for r in settings.rows if r.spec[5] == "pc_blocks_action")
    assert row.spec[1] == "tiles" and set(row.tiles) == {"on", "off"} and row.tiles["on"].isChecked()
    # Klick auf die Kachel schaltet um, das Menü Ansicht zieht mit
    row.tiles["off"].click()
    assert not window.pc_blocks_action.isChecked() and row.tiles["off"].isChecked()
    window.pc_blocks_action.setChecked(True)
    assert row.tiles["on"].isChecked()
    assert "calls" in window.view_actions and "calls" in dict(window.VIEWS)
    # Ansicht der Tagesliste: jede Ansicht eine Kachel, Hauptfenster folgt
    view_row = next(r for r in settings.rows if r.spec[5] == "list_view")
    assert list(view_row.tiles) == [k for k, _t in window.VIEWS], "jede Ansicht eine Kachel"
    view_row.tiles["single"].click()
    QTest.qWait(20)
    assert window.config["list_view"] == "single" and view_row.tiles["single"].isChecked()
    assert window.view_actions["single"].isChecked(), "Hauptfenster folgt der Auswahl"
    window.change_view("grouped")
    assert view_row.tiles["grouped"].isChecked() or settings.refresh() or view_row.tiles["grouped"].isChecked()
    # Zahl ändern wirkt sofort
    spin = next(r for r in settings.rows if r.spec[5] == "merge_gap_minutes").control
    spin.setValue(0)
    assert window.config["merge_gap_minutes"] == 0
    spin.setValue(5)
    # Zeitraum beim Start
    range_row = next(r for r in settings.rows if r.spec[5] == "timeline_range")
    range_row.tiles["day"].click()
    QTest.qWait(20)
    assert window.config["timeline_range"] == "day" and window.timeline.fit_day
    range_row.tiles["work"].click()

    # Datenquellen: Kacheln schalten dieselben Aktionen wie das Menü
    settings.show_page("sources")
    tile = next(t for t in settings.tiles if t.spec[0] == "rdm_enabled")
    assert tile.switch.isChecked() and tile.switch.text() == "An"
    tile.switch.setChecked(False)
    assert not window.source_actions["rdm_enabled"].isChecked() and window.config["rdm_enabled"] is False
    assert tile.state == "off" and tile.switch.text() == "Aus"
    window.source_actions["rdm_enabled"].setChecked(True)  # von außen: Kachel zieht mit
    assert tile.switch.isChecked() and tile.state != "off"

    # Jede Datenquelle hat ihr eigenes Einrichtungsfenster und einen eigenen Schalter darin
    from settings_window import SOURCE_TILES
    setups = [spec[4] for spec in SOURCE_TILES]
    assert len(set(setups)) == len(setups), setups
    from PySide6.QtWidgets import QDialog
    seen = []
    original_exec = QDialog.exec
    QDialog.exec = lambda self: seen.append(self) or QDialog.Rejected
    try:
        for spec in SOURCE_TILES:
            if spec[0] in ("tracking", "pbx_reader_enabled", "itm_reader_enabled", "m42_reader_enabled"):
                continue  # eigene Fenster mit Browser-Anmeldung
            before = len(seen)
            getattr(window, spec[4])()
            assert len(seen) == before + 1, spec
    finally:
        QDialog.exec = original_exec
    titles = [d.windowTitle() for d in seen]
    for title in ("Sophos Connect", "FortiClient", "Weitere VPN-Logs (OpenVPN …)", "RDM Better",
                  "Remotedesktop (mstsc)", "Outlook", "Teams-Anrufe"):
        assert title in titles, (title, titles)
    from PySide6.QtWidgets import QCheckBox
    for d in seen:
        assert d.findChildren(QCheckBox), d.windowTitle()  # eigener Schalter
    # Pfade bei Sophos sind Ordner aus sophos_connect_dirs
    sophos = next(d for d in seen if d.windowTitle() == "Sophos Connect")
    assert "sophos_connect_dirs" in sophos.values() and "sophos_enabled" in sophos.values()
    teams = next(d for d in seen if d.windowTitle() == "Teams-Anrufe")
    assert teams.outlook.parent() is None and teams.isAncestorOf(teams.teams)  # nur Teams im Fenster
    for d in seen:
        d.deleteLater()

    # Fehlersuche & Analyse: Mitschnitte stehen hier, nicht mehr in den Einrichtungsdialogen
    settings.show_page("debug")  # alter Name: jetzt Info → Fehlersuche, eingeklappt
    assert settings.current_page() == "about"
    toggle = settings.collapsed["about/Fehlersuche"]
    assert not toggle.isChecked()
    toggle.click()
    from settings_window import row_section
    debug_rows = [r.spec[3] for r in settings.rows if row_section(r.spec) == "Fehlersuche"]
    assert all(r.isVisible() for r in settings.rows if row_section(r.spec) == "Fehlersuche")
    assert "Matrix42: Buchung mitschneiden" in debug_rows and "3CX: Direkt-Abfrage prüfen" in debug_rows
    m42_dialog = window.build_reader_dialog("m42")
    assert not [b for b in m42_dialog.findChildren(QPushButton) if "mitschneiden" in b.text()]
    m42_dialog.deleteLater()
    calls = []
    window.record_source = lambda kind, booking=False, ticket=False: calls.append((kind, booking, ticket))
    next(r for r in settings.rows if r.spec[3] == "Matrix42: Buchung mitschneiden").control.click()
    next(r for r in settings.rows
         if r.spec[3] == "Matrix42: Ticket anlegen und schließen mitschneiden").control.click()
    assert calls == [("m42", True, False), ("m42", False, True)], calls

    # Seite Nachfragen: Grenzwert ändern wirkt sofort und wird gespeichert
    settings.show_page("prompts")
    settings.prompt_settings.idle_spin.setValue(25)
    assert window.config["idle_prompt_minutes"] == 25 and window.idle_watch.minutes == 25
    settings.prompt_settings.thresholds["calls"].setValue(3)
    assert window.config["prompt_thresholds"]["calls"] == 3

    # Suche findet über Bereiche hinweg, auch über die Einheit
    settings.search.setText("minuten")
    assert settings.results_found >= 5, settings.results_found
    settings.search.setText("pin")
    assert settings.results_found >= 1
    settings.search.setText("vpn")
    assert settings.results_found >= 2
    settings.search.setText("feierabend")  # findet auch die Seite Nachfragen und „Bei Feierabend prüfen“
    found = [w.text() for w in settings.findChildren(QPushButton) if w.objectName() == "result_link" and w.isVisible()]
    assert any("Nachfragen" in t for t in found), found
    rows = [settings.results_box.itemAt(i).widget() for i in range(settings.results_box.count())]
    assert any(getattr(r, "spec", (0,) * 6)[5] == "day_checks_enabled" for r in rows), [getattr(r, "spec", r) for r in rows]
    settings.search.clear()
    assert settings.stack.currentIndex() != settings.results_index

    # Design aus dem Fenster: Fenster färbt sich um, bleibt dasselbe und bleibt offen
    settings.show_page("view")
    design = next(r for r in settings.rows if r.spec[5] == "theme" and r.spec[1] == "tiles")
    design.tiles["dark"].click()
    QTest.qWait(50)
    assert window.dark_mode and window._settings_window is settings and settings.isVisible()
    assert settings.current_page() == "view" and design.tiles["dark"].isChecked()
    # Eigene Farben: klappt unter der Kachel auf, ohne eigenes Fenster
    assert not design.custom_panel.isVisible()
    design.tiles["custom"].click()
    QTest.qWait(50)
    assert window.current_theme_key() == "custom" and design.custom_panel.isVisible()
    assert window._settings_window is settings
    design.custom_panel.select("accent")
    design.custom_panel.swatches[3][1].click()
    assert window.config["custom_colors"]["accent"] == design.custom_panel.swatches[3][0]
    assert window._settings_window is settings, "Farbe ändern baut das Fenster nicht neu auf"
    window.set_theme("dark")
    assert not design.custom_panel.isVisible()
    # Menü Ansicht → „Eigene Farben …“ öffnet diese Stelle
    assert window.edit_custom_colors() is settings and design.custom_panel.isVisible()
    window.set_theme("dark")

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
    # Farbe je Richtung einstellbar (Menü Farben der Zeilen): eine alte Farbe für die ganze
    # Zeile Telefon bleibt für die andere Richtung erhalten
    colors_menu = next(a.menu() for a in window.rows_menu.actions()
                       if a.menu() and a.text().replace("&", "") == "Farben der Zeilen")
    entries = [a.text() for a in colors_menu.actions()]
    assert "Telefon eingehend …" in entries and "Telefon ausgehend …" in entries, entries
    assert "Telefon …" not in entries, entries
    window.set_row_color("call", "#112233")
    window.set_call_color("Ausgehend", "#AA5500")
    out = entry_color({"type": "Telefonat", "direction": "Ausgehend"}, window.config).name()
    inc = entry_color({"type": "Telefonat", "direction": "Eingehend"}, window.config).name()
    assert (out, inc) == ("#aa5500", "#112233"), (out, inc)
    assert "call" not in (window.config.get("row_colors") or {})
    window.set_row_color("call", None)  # Standardfarbe: beide Richtungen zurück
    assert not window.config.get("call_colors")
    assert entry_color({"type": "Telefonat", "direction": "Ausgehend"}, window.config).name() != "#aa5500"

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
    import safe_io
    safe_io.hard_exit(1)
sys.stdout.flush()
import safe_io  # Ende ohne Qt-Aufräumen (Absturz unter Windows)
safe_io.hard_exit(0)
