"""Dialog „Eigene Farben“: Klick in die schematische Vorschau wählt die passende Grundfarbe.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from theme import default_custom_colors  # noqa: E402
from theme_mockup import ThemeMockup  # noqa: E402

mockup = ThemeMockup()
mockup.set_colors(default_custom_colors("dark"))
mockup.resize(640, 330)
mockup.show()
QTest.qWait(50)
mockup.grab()  # einmal zeichnen: legt die klickbaren Bereiche an
picked = []
mockup.picked.connect(picked.append)
# Kopfleiste, Hintergrund (Rand), Timeline-Fläche, Beschriftung, Schalter
for x, y in [(300, 15), (5, 320), (300, 190), (40, 104), (533, 53)]:
    QTest.mouseClick(mockup, Qt.LeftButton, pos=QPoint(x, y))
assert picked == ["band", "bg", "surface", "text", "accent"], picked
print("ok")
os._exit(0)
