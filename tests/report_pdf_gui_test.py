"""Bericht als PDF (report_pdf.py) mit dem echten Hauptfenster: Menüeintrag, Knopf im
Wochenabschluss, Tages- und Wochenbericht werden als gültiges PDF geschrieben.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import faulthandler
import os
import sys
import tempfile
import traceback
from datetime import date, datetime, timedelta

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
    window = main_timeline.TimelineApp()
    window.tray.showMessage = lambda *a: None
    window.show()

    import report_pdf
    import week_dialogs
    assert window.report_action.text().replace("&", "") == "Bericht als PDF …"
    # eine Tätigkeit gestern, ohne Matrix42
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    window.journal.add({"start": f"{day} 08:00:00", "end": f"{day} 11:45:00", "customer": "Intern",
                        "category": "Besprechung", "text": "Jahresgespräch mit Vor- und Nachbereitung"})
    out = tempfile.mkdtemp()
    path = report_pdf.save_report(window, day, path=os.path.join(out, "tag.pdf"), open_after=False)
    data = open(path, "rb").read()
    assert data.startswith(b"%PDF") and len(data) > 2000, len(data)
    found = report_pdf.collect_day(window, day, datetime.now())
    assert found["items"][0]["what"].endswith("Jahresgespräch mit Vor- und Nachbereitung")
    path = report_pdf.save_report(window, day, week=True, path=os.path.join(out, "woche.pdf"),
                                  open_after=False)
    assert open(path, "rb").read().startswith(b"%PDF")
    # Zeitgraph: Bild in der angefragten Breite, auch mit leerem Tag
    import work_report
    image = report_pdf.draw_chart(work_report.chart(found), 2000)
    assert image.width() == 2000 and image.height() > 300
    assert b"/Subtype /Image" in data, "Zeitgraph als Bild im PDF"

    dialog = week_dialogs.WeekDialog(window, day)
    assert dialog.report_button.isEnabled() and dialog.report_button.isVisibleTo(dialog)
    dialog.reject()
    window.quit_app()
    print("Bericht als PDF: OK")


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
