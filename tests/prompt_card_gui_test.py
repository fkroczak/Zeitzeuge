"""Nachfrage als Karte, kompakt und als Leiste (prompt_card.py) im Hauptfenster.

Prüft: Punkte springen zwischen offenen Nachfragen und behalten den Text, Stift macht die
Zeitzeile bearbeitbar (ohne dass sie sich verschiebt), „+ Ticket“ wird zum Chip, Ausblenden nach
der eingestellten Dauer, Leiste mit ✕ (nur die vorderste oder alle), „Offene Nachfragen“ im
Infobereich und der Dialog „Nachfragen und Benachrichtigungen“.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import faulthandler
import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

FMT = "%Y-%m-%d %H:%M:%S"


def flush_deletes():
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def gui_test():
    global app, window
    import main_timeline
    from journal_dialogs import DocPromptDialog, PromptStrip, PromptWindow
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())
    window = main_timeline.TimelineApp()
    window.tray.showMessage = lambda *a: None
    window.show()

    now = datetime.now().replace(microsecond=0, second=0)
    if now.hour < 2:
        print("Kurz nach Mitternacht: übersprungen")
        return
    base = now - timedelta(minutes=80)

    def at(minutes):
        return (base + timedelta(minutes=minutes)).strftime(FMT)

    def settle(ms=500):
        QTest.qWait(ms)
        flush_deletes()

    tv = {"start": at(0), "end": at(30), "type": "TeamViewer", "customer_name": "TeamViewer 123456789",
          "tv_id": "123456789", "details": "", "is_suggestion": True}
    call = {"start": at(45), "end": at(55), "type": "Telefonat", "direction": "Eingehend",
            "customer_name": "Praxis Weber (0521 987654)", "details": "", "is_suggestion": True}
    window.activities.extend([tv, call])
    window.timeline.draw_timeline(window.current_date)

    # 1. Karte mit zwei offenen Nachfragen: „1 von 2“ und Punkte
    window.check_prompts()
    prompt = window._prompt_window
    assert isinstance(prompt, PromptWindow) and len(window._prompt_queue) == 2, window._prompt_queue
    assert prompt.dots.isVisibleTo(prompt) and prompt.pending == 1
    assert window.tray_prompts_action.isEnabled() and "(2)" in window.tray_prompts_action.text()
    first = prompt.entry
    prompt.form.text_edit.setPlainText("Angefangen")

    # Stift: Zeitfelder bearbeitbar, Zeile bleibt an derselben Stelle
    y = prompt.time_row.mapTo(prompt, prompt.time_row.rect().topLeft()).y()
    assert prompt.form.start_edit.isReadOnly()
    prompt.time_btn.click()
    assert not prompt.form.start_edit.isReadOnly() and prompt.time_editing()
    assert prompt.time_row.mapTo(prompt, prompt.time_row.rect().topLeft()).y() == y
    prompt.time_btn.click()
    assert prompt.form.start_edit.isReadOnly()

    # + Ticket: Feld, Enter macht daraus einen Chip, ✕ am Chip entfernt
    assert prompt.ticket_add.isVisibleTo(prompt) and not prompt.ticket_row.isVisibleTo(prompt)
    prompt.ticket_add.click()
    assert prompt.ticket_row.isVisibleTo(prompt)
    prompt.form.ticket_edit.setCurrentText("TCK0000049374")
    prompt._close_ticket()
    assert prompt.ticket_chip.isVisibleTo(prompt) and "TCK0000049374" in prompt.ticket_chip.text()
    assert prompt.form.item()["ticket"] == "TCK0000049374"
    prompt.ticket_chip.click()
    assert prompt.form.item()["ticket"] == "" and prompt.ticket_add.isVisibleTo(prompt)

    # Punkt 2: zur anderen Nachfrage, Text der ersten bleibt erhalten
    dots = [w for w in prompt.dots.findChildren(main_timeline.QToolButton) if w.isEnabled()]
    assert len(dots) == 1, "nur der andere Punkt ist anklickbar"
    dots[0].click()
    settle()
    prompt = window._prompt_window
    assert prompt is not None and prompt.entry is not first, "nicht gewechselt"
    assert prompt.form.text_edit.toPlainText() == ""
    window.on_prompt_jump(1)
    settle()
    prompt = window._prompt_window
    assert prompt.entry is first and prompt.form.text_edit.toPlainText() == "Angefangen", "Text verloren"

    # 2. Anzeigedauer: ausgeblendet, bleibt aber unter „Offene Nachfragen“
    prompt._timed_out()
    settle()
    assert window._prompt_window is None
    window.check_prompts()
    assert window.open_prompt_count() == 2 and window.tray_prompts_action.isEnabled()
    window.show_open_prompts()  # Infobereich: alle wieder zeigen
    settle()
    assert isinstance(window._prompt_window, PromptWindow)
    assert window._prompt_window.form.text_edit.toPlainText() in ("Angefangen", "")
    window._close_prompt_silently()
    window._prompt_queue.clear()
    window._prompt_asked.clear()
    window._prompt_asked_spans.clear()

    # 3. Leiste: ✕ schließt nur die vorderste, Klick öffnet die Karte
    window.config.update({"prompt_mode": "strip", "prompt_timeout_seconds": 0, "prompt_strip_close": "front"})
    window.check_prompts()
    strip = window._prompt_window
    assert isinstance(strip, PromptStrip) and strip.badge.text() == "2", strip
    strip.close_btn.click()
    settle()
    strip = window._prompt_window
    assert isinstance(strip, PromptStrip) and len(window._prompt_queue) == 1, window._prompt_queue
    assert not strip.badge.isVisibleTo(strip)
    strip.opened.emit()
    settle()
    assert isinstance(window._prompt_window, PromptWindow), "Klick auf die Leiste öffnet keine Karte"
    window._prompt_window._answer("later")
    settle()

    # ✕ schließt alle
    window._prompt_asked.clear()
    window._prompt_asked_spans.clear()
    window.config["prompt_strip_close"] = "all"
    window.check_prompts()
    assert isinstance(window._prompt_window, PromptStrip)
    window._prompt_window.close_btn.click()
    settle()
    assert window._prompt_window is None and not window._prompt_queue

    # 4. Kompakt: dieselbe Karte, kleiner
    window._prompt_asked.clear()
    window._prompt_asked_spans.clear()
    window.config.update({"prompt_mode": "compact", "prompt_timeout_seconds": 10})
    window.check_prompts()
    prompt = window._prompt_window
    assert isinstance(prompt, PromptWindow) and prompt.style == "compact"
    assert prompt.card.width() < 500 and prompt._timeout_ms == 10000
    prompt.form.text_edit.setPlainText("x")  # Tippen hält die Karte
    assert prompt._paused()
    prompt._answer("ignore")
    settle()

    # 5. Einstellungen: Darstellung wechseln schlägt die Dauer vor, alles wird gespeichert
    dialog = DocPromptDialog(window.config, window)
    dialog.mode.setCurrentIndex(dialog.mode.findData("window"))
    assert dialog.timeout.currentData() == 0, "Karte: dauerhaft vorgeschlagen"
    dialog.mode.setCurrentIndex(dialog.mode.findData("strip"))
    assert dialog.timeout.currentData() == 10 and dialog.strip_close.isEnabled()
    dialog.dots.setChecked(False)
    dialog.apply()
    assert window.config["prompt_mode"] == "strip" and window.config["prompt_timeout_seconds"] == 10
    assert window.config["prompt_dots_clickable"] is False
    assert not dialog.position.isEnabled(), "Leiste: Position fest unten rechts"
    dialog.mode.setCurrentIndex(dialog.mode.findData("window"))
    assert dialog.position.isEnabled()
    dialog.position.setCurrentIndex(dialog.position.findData("top_left"))
    dialog.apply()
    assert window.config["prompt_position"] == "top_left"

    # 6. Position: Karte oben links, mit Abstand, nie außerhalb des Bildschirms
    window._close_prompt_silently()
    window._prompt_queue.clear()
    window._prompt_asked.clear()
    window._prompt_asked_spans.clear()
    window.config["prompt_timeout_seconds"] = 0
    window.check_prompts()
    prompt = window._prompt_window
    assert isinstance(prompt, PromptWindow) and prompt.position == "top_left"
    settle(100)
    area = app.primaryScreen().availableGeometry()
    frame = prompt.frameGeometry()
    assert frame.left() == area.left() + 8 and frame.top() == area.top() + 8, (frame, area)
    window._close_prompt_silently()
    window.config["prompt_position"] = "bottom_right"
    old = {"prompt_mode": "tray"}  # alter Name der Leiste
    assert DocPromptDialog(old, window).mode.currentData() == "strip"
    window.quit_app()
    print("Nachfrage-Karte: OK")


try:
    gui_test()
except Exception:
    traceback.print_exc()
    sys.stdout.flush()
    os._exit(1)
sys.stdout.flush()
os._exit(0)
