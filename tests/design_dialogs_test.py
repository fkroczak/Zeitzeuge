"""Dialoge im neuen Aussehen: Arbeitszeiten (Pause nur bei Bedarf), Aktivitätstypen (Suche, Farbpunkt).

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from settings_dialogs import ActivityTypeSettingsDialog, WorkHoursDialog  # noqa: E402

# Arbeitszeiten: ohne Pause sind „Pause von“/„bis“ (Überschrift und Felder) ausgeblendet
config = {"work_hours": {}}
dialog = WorkHoursDialog(config)
dialog.show()
monday = dialog.rows[0]
active, t_from, t_to, total, has_pause, p_from, p_to = monday
for row in dialog.rows:
    row[4].setChecked(False)
assert not any(h.isVisible() for h in dialog.pause_heads), "Pausenspalten ohne Pause sichtbar"
assert not p_from.isVisible() and not p_to.isVisible()
# Pause an einem Tag: Spalten erscheinen, die Felder dieses Tages auch
has_pause.setChecked(True)
assert all(h.isVisible() for h in dialog.pause_heads)
assert p_from.isVisible() and p_to.isVisible()
assert not dialog.rows[1][5].isVisible(), "Dienstag ohne Pause zeigt keine Pausenfelder"
# Freier Tag: nur „frei“, keine Zeitfelder
sunday = dialog.rows[6]
sunday[0].setChecked(False)
assert not sunday[1].isVisible() and not sunday[2].isVisible() and sunday[3].text() == "frei"
dialog.close()

# Aktivitätstypen: Farbpunkt je Typ, Suche filtert die Liste
config = {"activity_types": ["VPN-Sitzung", "RDP-Sitzung", "TeamViewer"],
          "type_colors": {"VPN-Sitzung": "#0F9D8A"}}
types = ActivityTypeSettingsDialog(config)
assert all(not types.type_list.item(i).icon().isNull() for i in range(types.type_list.count()))
types.search.setText("rdp")
visible = [types.type_list.item(i).text() for i in range(types.type_list.count())
           if not types.type_list.item(i).isHidden()]
assert visible == ["RDP-Sitzung"], visible
types.search.setText("")
assert types.get_types() == ["VPN-Sitzung", "RDP-Sitzung", "TeamViewer"]

print("Dialoge OK")
os._exit(0)
