"""Hinweise als Karte und Leiste statt Windows-Sprechblasen (notices.py, TrayMixin.notify).

Prüft: Leiste für Anmeldung nötig mit „Anmelden“, Karte für den Feierabend mit Liste und einer
Hauptaktion, gleiche Ecke wie die Nachfrage und darüber, gleicher Hinweis nicht doppelt,
Esc/✕ schließen, Ausblenden nach der Zeit, „Zeitzeuge läuft weiter“ als Info-Leiste,
„Als Windows-Benachrichtigung“ wie bisher als Sprechblase, beim Beenden weg, beide Designs.

Läuft ohne Bildschirm als eigener Prozess (Skript).
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


def gone(widget):
    """Geschlossen: unsichtbar oder schon gelöscht."""
    from shiboken6 import isValid
    return not isValid(widget) or not widget.isVisible()


def flush_deletes():
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def gui_test():
    global app, window
    import main_timeline
    from notices import NoticeCard, NoticeStrip
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QSystemTrayIcon

    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())
    window = main_timeline.TimelineApp()
    balloons = []
    window.tray.showMessage = lambda title, text, *a: balloons.append((title, text))
    window.show()
    area = QGuiApplication.primaryScreen().availableGeometry()

    for dark in (False, True):
        window.set_theme("dark" if dark else "light", save=False)
        # Anmeldung nötig: Leiste mit „Anmelden“, unten rechts, keine Sprechblase
        logins = []
        window.show_pbx_login = lambda: logins.append(1)
        window.on_pbx_login_required()
        strip = window._notices[-1]
        assert isinstance(strip, NoticeStrip) and strip.title.full_text() == "3CX-Anmeldung nötig"
        assert strip.action_button.text() == "Anmelden" and not balloons
        QTest.qWait(50)
        frame = strip.frameGeometry()
        assert frame.right() <= area.right() - 7 and frame.bottom() <= area.bottom() - 7, (frame, area)
        tile = strip.findChild(QLabel, "notice_warn")
        assert tile is not None and not tile.pixmap().isNull(), "gelbe Kachel mit Icon"
        # derselbe Hinweis noch einmal: ersetzt den alten statt zu stapeln
        window.on_pbx_login_required()
        flush_deletes()
        assert len([n for n in window._notices if n.isVisible()]) == 1
        window._notices[-1].action_button.click()
        assert logins == [1] and not [n for n in window._notices if n.isVisible()]
        flush_deletes()

    # Feierabend als Karte: Liste, eine Hauptaktion, Esc schließt
    card = window.notify("Feierabend: noch nicht alles dokumentiert", "Heute sind noch 2 Tätigkeiten offen.",
                         items=["A", "B", "C", "D", "E"], card=True, action="Nachtragen", on_action=lambda: None)
    assert isinstance(card, NoticeCard) and card.action_button.isDefault()
    texts = [label.text() for label in card.findChildren(QLabel)]
    assert "D" in texts and "E" not in texts and "und 1 weitere" in texts, texts
    QTest.keyClick(card, Qt.Key_Escape)
    assert gone(card)
    flush_deletes()

    # Gleiche Ecke wie die Nachfrage (oben links) und mit Abstand darunter, wenn sie offen ist
    window.config["prompt_position"] = "top_left"
    strip = window.notify("ITM-Zeiterfassung prüfen", "Buchung ohne Ende", timeout=0)
    QTest.qWait(50)
    first = strip.frameGeometry()
    assert first.left() == area.left() + 8 and first.top() == area.top() + 8, (first, area)
    second = window.notify("Matrix42-Anmeldung nötig", "Zeitzeuge kann nicht lesen.", timeout=0)
    QTest.qWait(50)
    assert second.frameGeometry().top() >= first.bottom(), "neuer Hinweis überdeckt den alten nicht"
    window.config["prompt_position"] = "bottom_right"
    for notice in list(window._notices):
        notice._finish(notice.closed)
    flush_deletes()

    # Ausblenden nach der Zeit
    strip = window.notify("Kurz", "blendet aus", timeout=1)
    strip._left_ms = 50
    QTest.qWait(250)
    assert gone(strip)
    flush_deletes()

    # Fenster schließen: „Zeitzeuge läuft weiter“ als blaue Info-Leiste
    window._tray_hint_shown = False
    window.config["tray_hint_on_close"] = True
    window.close()
    info = window._notices[-1]
    assert info.title.full_text() == "Zeitzeuge läuft weiter" and info.findChild(QLabel, "notice_info")
    assert info.action_button is None
    info._finish(info.closed)
    window.show()
    flush_deletes()

    # „Als Windows-Benachrichtigung“: Sprechblase mit dem bisherigen Text, Klick wie bisher
    window.config["notify_windows"] = True
    before = len(window._notices)
    window.on_pbx_login_required()
    assert balloons[-1][0] == "3CX-Anmeldung nötig" and "Klick hier" in balloons[-1][1], balloons
    assert len(window._notices) == before, "keine Leiste zusätzlich"
    window.config["notify_windows"] = False

    # Einstellung auf der Seite Nachfragen
    settings = window.show_settings("prompts")
    settings.prompt_settings.windows_notes.click()
    assert window.config["notify_windows"] is True
    settings.prompt_settings.windows_notes.click()
    assert window.config["notify_windows"] is False
    settings.hide()

    # Beenden: offene Hinweise verschwinden mit
    last = window.notify("Bleibt nicht", "", timeout=0)
    window.quit_app()
    assert gone(last)
    print("Hinweise: OK")


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
