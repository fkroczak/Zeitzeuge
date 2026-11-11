"""Einstellungsfenster nach der Neugliederung: Bereiche, Abschnitte, Kacheln, Tastatur, Größe.

Prüft: Reihenfolge der Bereiche, Abschnitte auf Aufzeichnung (Quellen nach Art) und Darstellung,
jede Quelle genau einmal, Übersicht mit Zustand und Sprung, Skelett-Bilder für jede Kachel in
beiden Designs, eindeutige Alt-Buchstaben je Seite, Namen für Kacheln, Menüeinträge führen zur
passenden Seite, und bei 150 % und 200 % (Full HD) keine waagerechte Scrollleiste.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import faulthandler
import os
import re
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()


def mnemonics(widgets):
    """Alt-Buchstaben der sichtbaren Bedienelemente: {Buchstabe: [Texte]}."""
    found = {}
    for w in widgets:
        text = w.text() if hasattr(w, "text") else ""
        match = re.search(r"&([^&\s])", text.replace("&&", ""))
        if match and w.isVisible():
            found.setdefault(match.group(1).lower(), []).append(text)
    return found


def gui_test():
    global app, window
    import main_timeline
    import settings_skeletons
    import theme
    from settings_window import PAGES, ROWS, SOURCE_TILES, TILE_GROUPS, row_page, row_section
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (QAbstractButton, QApplication, QLabel, QScrollArea,
                                   QSystemTrayIcon, QWidget)

    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())
    window = main_timeline.TimelineApp()
    window.tray.showMessage = lambda *a: None
    window.show()
    settings = window.show_settings()
    QTest.qWait(100)

    # Bereiche in der Reihenfolge des Arbeitstags, je ein Wort
    assert [k for k, *_r in PAGES] == ["home", "sources", "prompts", "mapping", "booking", "view", "data", "about"]
    assert all(" " not in name and "&" not in name for _k, name, *_r in PAGES)
    # Jede Quelle steht in genau einem Abschnitt der Aufzeichnung
    grouped = [k for _g, keys in TILE_GROUPS for k in keys]
    assert sorted(grouped) == sorted(spec[0] for spec in SOURCE_TILES) and len(grouped) == len(set(grouped))
    assert len(settings.tiles) == len(SOURCE_TILES)
    # Abschnitte: höchstens 6 Zeilen je Abschnitt
    for key, *_r in PAGES:
        sections = {}
        for spec in ROWS:
            if row_page(spec) == key:
                sections.setdefault(row_section(spec), []).append(spec[3])
        for section, titles in sections.items():
            assert len(titles) <= 6, (key, section, titles)
    # Textbausteine unter Zuordnung, Arbeitszeiten unter Buchung (wie entschieden)
    where = {spec[3]: row_page(spec) for spec in ROWS if row_page(spec) != "home"}
    assert where["Textbausteine"] == "mapping" and where["Arbeitszeiten"] == "booking"

    # Übersicht: Knopf springt zum Bereich
    settings.show_page("home")
    button = next(b for b in settings.findChildren(QAbstractButton) if b.text() == "Aufzeichnung …")
    button.click()
    assert settings.current_page() == "sources"

    # Skelett-Bilder: jede Kachel hat ein Bild, in beiden Designs
    for dark in (False, True):
        tokens = theme.THEMES["dark" if dark else "light"]
        for spec in ROWS:
            if spec[1] != "tiles":
                continue
            options = spec[6](window) if callable(spec[6]) else spec[6]
            for value, _label in options:
                pixmap = settings_skeletons.preview(spec[5], value, tokens, window.config.get("custom_colors"))
                assert not pixmap.isNull() and pixmap.width() == 192, (spec[5], value)
    for row in settings.rows:
        for tile in row.tiles.values():
            assert tile.accessibleName() and not tile.icon().isNull(), row.spec[3]

    # Alt-Buchstaben je Seite eindeutig (Seite Nachfragen hat die meisten)
    for key, *_r in PAGES:
        settings.show_page(key)
        QTest.qWait(30)
        page = settings.stack.currentWidget()
        found = mnemonics(page.findChildren(QAbstractButton) + page.findChildren(QLabel))
        doubles = {k: v for k, v in found.items() if len(v) > 1}
        assert not doubles, (key, doubles)

    # Menüeinträge führen zur passenden Seite
    window.edit_prompt_settings()
    assert settings.current_page() == "prompts"
    window.show_settings("customers")
    assert settings.current_page() == "mapping"
    texts = [a.text().replace("&", "") for a in window.menu_button.menu().actions()]
    assert "Nachfragen …" in texts and "Aufzeichnung …" in texts, texts

    # Schmales Fenster (Full HD bei 200 %: 960 × 540): keine waagerechte Scrollleiste
    settings.resize(settings.minimumSize())
    # Schriftmaß prüfen: Der Windows-Runner misst offscreen Texte etwa doppelt so breit wie echtes
    # Windows oder Linux („Darstellung“ in 12 px: 132 statt ~68 px). Dann gilt die Grenze im
    # gleichen Verhältnis, sonst misst die Prüfung die kaputte Schrift statt des Layouts.
    from PySide6.QtGui import QFont, QFontMetrics
    probe = QFont(app.font())
    probe.setPixelSize(theme.FONT_BASE)
    stretch = max(1.0, QFontMetrics(probe).horizontalAdvance("Darstellung") / 80)
    print("Schriftmaß", round(stretch, 2), "DPI", app.primaryScreen().logicalDotsPerInch())
    for key, *_r in PAGES:
        settings.show_page(key)
        QTest.qWait(50)
        for area in settings.stack.currentWidget().findChildren(QScrollArea) + (
                [settings.stack.currentWidget()] if isinstance(settings.stack.currentWidget(), QScrollArea) else []):
            bar = area.horizontalScrollBar()
            too_wide = area.widget().minimumSizeHint().width() > area.viewport().width() * stretch
            if too_wide:  # welches Element ist zu breit?
                inner = area.widget()
                print(key, "Sicht", area.viewport().width(), "Inhalt", inner.minimumSizeHint().width())
                for child in inner.findChildren(QWidget):
                    if child.isVisible() and child.minimumSizeHint().width() > area.viewport().width() - 80:
                        print("  ", type(child).__name__, child.objectName(), child.minimumSizeHint().width(),
                              child.minimumWidth(), getattr(child, "text", lambda: "")()[:40]
                              if callable(getattr(child, "text", None)) else "")
                        for part in child.findChildren(QWidget):  # Teile der zu breiten Zeile
                            if part.isVisible():
                                text = part.text()[:30] if callable(getattr(part, "text", None)) else ""
                                print("      ", type(part).__name__, part.objectName(), "min",
                                      part.minimumSizeHint().width(), "fest", part.minimumWidth(),
                                      "hint", part.sizeHint().width(), "font", part.font().family(),
                                      part.font().pixelSize(), part.font().pointSize(), repr(text))
            assert not too_wide, (key, area.widget().minimumSizeHint().width(), area.viewport().width())
            if stretch == 1.0:
                assert not (bar.isVisible() and bar.maximum() > 0), (key, bar.maximum())
    assert settings.minimumWidth() <= 960 and settings.minimumHeight() <= 540

    settings.hide()
    window.quit_app()
    print("Einstellungen: OK")


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
