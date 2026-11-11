"""Abwesenheit am PC: Nachfrage bei der ersten Eingabe, Schnellauswahl, Später, Speichern.

Läuft ohne Bildschirm mit einem leeren Datenordner, als eigener Prozess (Skript).
Die Logik ohne Oberfläche prüft idle_watch_test.py.
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


def gui_test():
    global app, window
    import main_timeline
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())
    window = main_timeline.TimelineApp()
    window.tray.showMessage = lambda *a: None
    window.idle_timer.stop()  # Proben gibt der Test selbst vor
    window.show()

    now = datetime.now().replace(microsecond=0)
    if now.hour == 0 and now.minute < 30:
        print("Kurz nach Mitternacht: übersprungen")
        return
    assert window.idle_watch.minutes == 15
    back = now
    away = now - timedelta(minutes=20)
    window.idle_sample(away, 0)              # letzte Eingabe vor der Pause
    window.idle_sample(back - timedelta(seconds=5), 20 * 60 - 5)  # noch weg: nichts
    assert window._prompt_window is None
    window.idle_sample(back, 1)              # erste Eingabe: Nachfrage
    prompt = window._prompt_window
    assert prompt is not None and prompt.entry.get("idle"), "keine Nachfrage nach Abwesenheit"
    assert len(prompt.quick_buttons) == 5
    # unten rechts mit Abstand, nie in der Taskleiste – auch wenn das Fenster wächst
    area = app.primaryScreen().availableGeometry()
    for grow in (0, 120):
        prompt.resize(prompt.width(), prompt.height() + grow)
        app.processEvents()
        frame = prompt.frameGeometry()
        assert frame.bottom() <= area.bottom() - 8, (frame, area)
        assert frame.right() <= area.right() - 8, (frame, area)

    # Später fragen: Fenster weg, nicht sofort wieder, aber noch offen
    prompt._answer("later")
    window.check_prompts()
    assert window._prompt_window is None and len(window._idle_open) == 1
    window._prompt_asked.clear()             # Zeit "vergangen"
    window._prompt_asked_spans.clear()
    window.check_prompts()
    prompt = window._prompt_window
    assert prompt is not None and prompt.entry.get("idle"), "nach „Später“ nicht wieder gefragt"

    # Schnellauswahl Telefonat, speichern: Tätigkeit steht im Journal, nicht mehr offen
    prompt.quick_choice("Telefonsupport", "Telefonat", {})
    prompt._answer("save")
    items = window.journal.items(away.strftime("%Y-%m-%d"))
    assert any(i.get("text") == "Telefonat" and i.get("category") == "Telefonsupport" for i in items), items
    assert not window._idle_open
    window.check_prompts()
    assert window._prompt_window is None or not window._prompt_window.entry.get("idle")

    # Abgeschaltet: keine Nachfrage
    window.idle_watch.minutes = 0
    window.idle_sample(now + timedelta(minutes=30), 0)
    window.idle_sample(now + timedelta(minutes=60), 0)
    assert not window._idle_open
    window.quit_app()  # Leser-Threads sauber beenden, sonst Absturz beim Prozessende unter Windows
    print("Abwesenheit am PC: OK")


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
