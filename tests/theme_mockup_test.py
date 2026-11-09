"""Dialog „Eigene Farben“: Klick in die Skizze öffnet ein Farbmenü für den passenden Bereich.

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
mockup.picked.connect(lambda key, _pos: picked.append(key))
# Kopfleiste, Hintergrund (Rand), Timeline-Fläche, Beschriftung, Schalter
for x, y in [(300, 15), (5, 320), (300, 190), (40, 104), (533, 53)]:
    QTest.mouseClick(mockup, Qt.LeftButton, pos=QPoint(x, y))
assert picked == ["band", "bg", "surface", "text", "accent"], picked

# Tastatur: Pfeiltaste wählt den ersten Bereich, Eingabe meldet ihn
picked.clear()
mockup.setFocus()
QTest.keyClick(mockup, Qt.Key_Right)
QTest.keyClick(mockup, Qt.Key_Return)
assert picked == ["bg"], picked

# Menü im Dialog: Farbfeld setzt die Farbe, „Standardfarbe“ stellt sie zurück
from PySide6.QtWidgets import QWidget  # noqa: E402
from theme import SWATCHES  # noqa: E402
from theme_dialog import CustomColorsDialog  # noqa: E402


class FakeMain(QWidget):
    config, dark_mode, themes = {}, True, []

    def set_theme(self, name, save=True):
        self.themes.append(name)


main = FakeMain()
dialog = CustomColorsDialog(main)
assert not hasattr(dialog, "buttons"), "keine Liste mit Farben mehr"
menu = dialog.color_menu("accent")
color, button = menu.swatches[3]
assert color == SWATCHES["dark"]["accent"][3]
button.click()
assert dialog.colors["accent"] == color and main.config["custom_colors"]["accent"] == color
menu = dialog.color_menu("accent")
standard = [a for a in menu.actions() if a.text() == "&Standardfarbe"][0]
assert standard.isEnabled()
standard.trigger()
assert dialog.colors["accent"] == SWATCHES["dark"]["accent"][0]
dialog.reject()
print("ok")
os._exit(0)
