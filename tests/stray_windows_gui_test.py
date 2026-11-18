"""Keine kleinen Streufenster beim Öffnen von Dialogen.

Ruft ein Dialog setVisible(True)/show() auf einem Feld auf, bevor es im Fenster hängt, zeigt Qt
das Feld kurz als eigenes kleines Fenster (Titelleiste mit „Zeitzeuge“); unter Windows blinkt das
sichtbar auf. Geprüft für „In Matrix42 buchen“ (mit Kulanz und Kein Zuschlag) und die Hinweiskarte.
"""
import os
import sys
import tempfile
import traceback
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()


def main():
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import QApplication, QDialog, QWidget

    app = QApplication(sys.argv)
    stray = []

    class Spy(QObject):
        def eventFilter(self, obj, event):
            if (event.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow()
                    and not isinstance(obj, QDialog)):
                stray.append(f"{type(obj).__name__} {obj.objectName()!r}")
            return False

    spy = Spy()
    app.installEventFilter(spy)

    import m42_booking_dialogs
    plan = dict(start=datetime(2026, 11, 18, 8, 58), end=datetime(2026, 11, 18, 9, 13), ticket="TCK0000051151",
                customer="Creacam", minutes=15, goodwill=True, no_surcharge=True, text="Abstimmung")
    dialog = m42_booking_dialogs.BookingDialog(plan)
    assert not stray, f"In Matrix42 buchen: Streufenster {stray}"
    dialog.show()
    app.processEvents()
    assert not stray, f"In Matrix42 buchen (gezeigt): Streufenster {stray}"
    dialog.close()

    import notices
    card = notices.NoticeCard("Titel", "Text")
    assert not stray, f"Hinweiskarte: Streufenster {stray}"
    card.close()
    print("OK: keine Streufenster")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        os._exit(1)
    sys.stdout.flush()
    os._exit(0)
