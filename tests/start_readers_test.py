"""Starttest mit eingeschaltetem 3CX- und ITM-Leser (Edge wird dabei nicht gestartet).

Hier stürzte 4.0.0 beim Start ab: Der 3CX-Leser startete, bevor itm_reader angelegt war.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import itm_reader
import main_timeline
import pbx_reader
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

pbx_reader.BrowserReader.start = lambda self: None  # kein Edge im Test
load = main_timeline.load_config_with_defaults


def with_readers():
    config = load()
    config["pbx_reader_enabled"] = True
    config["itm_reader_enabled"] = True
    return config


main_timeline.load_config_with_defaults = with_readers
app = QApplication(sys.argv)
window = main_timeline.TimelineApp()
assert isinstance(window.pbx_reader, pbx_reader.PbxReader), window.pbx_reader
assert isinstance(window.itm_reader, itm_reader.ItmReader), window.itm_reader
window.show()
QTimer.singleShot(500, window.quit_app)
app.exec()
print("Start mit 3CX und ITM ok")
sys.stdout.flush()
os._exit(0)
