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
mockup.resize(640, 380)
mockup.show()
QTest.qWait(50)
mockup.grab()  # einmal zeichnen: legt die klickbaren Bereiche an
picked = []
mockup.picked.connect(lambda key, _pos: picked.append(key))
# Kopfleiste, Hintergrund (Rand), Timeline-Fläche, Beschriftung, Schalter, Jetzt-Linie,
# Balken Dokumentation, VPN, Anruf ausgehend
left = 14 + 92
for x, y in [(300, 15), (5, 370), (300, 105), (40, 99), (533, 53), (left + 380, 150),
             (left + 30, 98 + 22 + 7), (left + 150, 98 + 3 * 22 + 7), (left + 210, 98 + 2 * 22 + 7)]:
    QTest.mouseClick(mockup, Qt.LeftButton, pos=QPoint(x, y))
assert picked == ["band", "bg", "surface", "text", "accent", "now", "row:doc", "row:vpn",
                  "row:call:Ausgehend"], picked

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

    def row_color(self, key):
        return (self.config.get("row_colors") or {}).get(key, "#4682B4")

    def call_color(self, direction):
        return (self.config.get("call_colors") or {}).get(direction, "#1F5FD6")

    def set_row_color(self, key, color):
        rows = dict(self.config.get("row_colors") or {})
        if color:
            rows[key] = color
        else:
            rows.pop(key, None)
        self.config["row_colors"] = rows

    def set_call_color(self, direction, color):
        self.config.setdefault("call_colors", {})[direction] = color


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

# Jetzt-Linie ist eine Grundfarbe
dialog.color_menu("now").swatches[1][1].click()
assert dialog.colors["now"] == SWATCHES["dark"]["now"][1]

# Balken: Farbfeld setzt die Zeilenfarbe, Standardfarbe nimmt sie wieder weg
from theme import BAR_SWATCHES  # noqa: E402
menu = dialog.color_menu("row:vpn")
assert [a.text() for a in menu.actions() if a.text() == "&Standardfarbe"][0]
menu.swatches[4][1].click()
assert main.config["row_colors"]["vpn"] == BAR_SWATCHES[4]
assert dialog.mockup.bar_colors["row:vpn"] == BAR_SWATCHES[4]
dialog.color_menu("row:call:Eingehend").swatches[0][1].click()
assert main.config["call_colors"]["Eingehend"] == BAR_SWATCHES[0]
# Abbrechen: auch die Balkenfarben wie vorher (vorher gab es keine eigenen)
dialog.reject()
assert "row_colors" not in main.config and "call_colors" not in main.config, main.config
print("ok")
os._exit(0)
