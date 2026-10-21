"""Starttest: Hauptfenster öffnen und nach 1 Sekunde wieder schließen."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main_timeline  # zuerst laden (eingebauter Browser muss vor QApplication kommen)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication

assert main_timeline.PbxReader is not None, "Eingebauter Browser (PyQtWebEngine) fehlt"
QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
app = QApplication(sys.argv)
window = main_timeline.TimelineApp()
window.show()
QTimer.singleShot(1000, window.quit_app)
app.exec_()
print("Start ok")
