"""Starttest: Hauptfenster öffnen und nach 1 Sekunde wieder schließen."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main_timeline
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)
window = main_timeline.TimelineApp()
window.show()
QTimer.singleShot(1000, window.quit_app)
app.exec_()
print("Start ok")

# Direkt beenden: PyQt räumt beim Interpreter-Ende sporadisch in falscher Reihenfolge auf
# (Zugriffsfehler unter Windows, auch mit altem Code). Alle Prüfungen sind hier gelaufen.
sys.stdout.flush()
os._exit(0)
