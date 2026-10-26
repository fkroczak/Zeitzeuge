"""Start im PAW-Modus: kein Edge-Leser, keine Prozesssuche, Edge-Steuerung nicht geladen.

Auf der PAW läuft ein EDR (Cortex XDR). Zeitzeuge darf dort nichts tun, was nach
Angriff aussieht: Browser mit Fernsteuerung starten, Cookies lesen, Prozesse beenden.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
data = tempfile.mkdtemp()
os.environ["ZEITZEUGE_DATA"] = data
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()  # eigene Profilordner, damit sie "existieren"
for name in ("3cx_profil", "itm_profil", "m42_profil"):
    os.makedirs(os.path.join(os.environ["LOCALAPPDATA"], "Zeitzeuge", name))
with open(os.path.join(data, "zeitzeuge_config.json"), "w", encoding="utf-8") as f:
    json.dump({"pc_role": "paw", "pbx_reader_enabled": True, "itm_reader_enabled": True,
               "m42_reader_enabled": True, "m42_url": "https://example.invalid/kalender"}, f)

import main_timeline  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
window = main_timeline.TimelineApp()
window.show()
for _ in range(30):
    app.processEvents()
assert not window.all_readers(), window.all_readers()
for mod in ("pbx_reader", "itm_reader", "m42_reader"):  # Edge-Steuerung und Prozess-Beenden
    assert mod not in sys.modules, f"{mod} auf der PAW geladen"
window.quit_app()
print("PAW-Start ok")
sys.stdout.flush()
os._exit(0)
