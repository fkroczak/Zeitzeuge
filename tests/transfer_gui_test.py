"""Export vom Arbeits-PC, Übernahme auf der PAW, PAW-Modus (kein Edge, keine Leser)."""
import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

import main_timeline  # noqa: E402
import transfer  # noqa: E402
from PySide6.QtCore import QDate  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from timeline_only import entry_menu_items  # noqa: E402

app = QApplication(sys.argv)
app.setStyle(main_timeline.AppStyle())
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)  # Rückfragen bejahen
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
window = main_timeline.TimelineApp()
window.show()
for _ in range(20):
    app.processEvents()

d = date.today() - timedelta(days=1)
D = d.isoformat()
qd = QDate(d.year, d.month, d.day)

# ---- "Arbeits-PC": Anruf, Tätigkeit, Personalzeit, Matrix42
window.timeline.activities.append({"start": f"{D} 09:00:00", "end": f"{D} 09:40:00",
                                   "type": "Telefonat", "customer_name": "Müller GmbH"})
window.journal.add({"start": f"{D} 09:00:00", "end": f"{D} 09:40:00", "customer": "Müller GmbH",
                    "category": "Telefonsupport", "text": "Drucker eingerichtet"})
main_timeline.safe_io.write_json(main_timeline.ITM_FILE, {D: {"zeiten": [
    {"start": f"{D} 08:00:00", "end": f"{D} 12:00:00"}]}})
main_timeline.safe_io.write_json(main_timeline.M42_FILE, {"tage": {D: [
    {"start": f"{D} 09:00:00", "end": f"{D} 10:00:00", "customer": "Müller GmbH",
     "ticket": "TCK1", "subject": "Drucker", "entry": "TE1"}]}, "gelesen": {}})
window.timeline._tv_index = window.timeline._tv_index or __import__("log_parsers").ConnectionIndex([])
window.timeline._rdm_index = window.timeline._rdm_index or __import__("log_parsers").ConnectionIndex([])
window.timeline._vpn_index = window.timeline._vpn_index or __import__("log_parsers").ConnectionIndex([])
export = window.collect_export(3)
export["pc"] = "ARBEITS-PC"
day = export["tage"][D]
assert day["verbindungen"][0]["customer_name"] == "Müller GmbH", day
assert day["personalzeit"]["zeiten"] and day["m42"][0]["ticket"] == "TCK1"
assert day["taetigkeiten"]["items"][0]["text"] == "Drucker eingerichtet"
data = transfer.to_bytes(export)

# ---- "PAW": eigene Daten leeren, dann übernehmen
window.timeline.activities.clear()
window.journal.delete(window.journal.load(D)["items"][0])
os.remove(main_timeline.ITM_FILE)
os.remove(main_timeline.M42_FILE)
window.timeline._remote_cache.clear()
assert window.import_export(transfer.parse(data))
assert os.path.exists(main_timeline.IMPORT_FILE)

calls = [a for a in window.timeline.activities_for(qd) if a.get("type") == "Telefonat"]
assert calls and calls[0]["source_pc"] == "ARBEITS-PC" and "von ARBEITS-PC" in calls[0]["details"], calls
docs = window.journal.entries(D)
assert docs and docs[0]["doc_item"]["von_pc"] == "ARBEITS-PC"
assert [i[1] for i in entry_menu_items(docs[0]) if i] == ["copy"], "übernommene Tätigkeit nur kopieren"
assert not window.doc_candidates(D), "dokumentierter Anruf gilt auch auf der PAW als dokumentiert"
assert window.personal_day_for(D)["zeiten"][0]["start"].endswith("08:00:00")
band = window.m42_band(D)
assert any(e.get("m42") for e in band) and any(e.get("m42_gap") for e in band), band
assert window.collect_export(3)["tage"].get(D, {}).get("verbindungen") in (None, []), \
    "Export der PAW enthält keine übernommenen Daten"

# ---- PAW-Modus: kein Edge, keine Leser
window.paw_action.setChecked(True)
assert window.config["pc_role"] == "paw" and not window.config["teamviewer_enabled"]
assert window.config["prompt_mode"] == "off" and not window.tracking_action.isChecked()
assert window.config["rdm_enabled"]
window.start_pbx_reader()
window.start_itm_reader()
window.config["m42_reader_enabled"] = True
window.start_m42_reader()
assert not window.all_readers(), "auf der PAW startet kein Edge-Leser"
window.paw_action.setChecked(False)
assert window.config["pc_role"] == ""

window.quit_app()
print("Übertragen ok")
sys.stdout.flush()
os._exit(0)
