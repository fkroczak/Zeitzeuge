"""Export vom Arbeits-PC, Übernahme auf der PAW, PAW-Modus (kein Edge, keine Leser)."""
import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

import main_timeline  # noqa: E402
import datakey  # noqa: E402
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
window.data_store.put("personalzeiten", D, {"zeiten": [
    {"start": f"{D} 08:00:00", "end": f"{D} 12:00:00"}]})
window.data_store.put("m42_buchungen", D, {"items": [
    {"start": f"{D} 09:00:00", "end": f"{D} 10:00:00", "customer": "Müller GmbH",
     "ticket": "TCK1", "subject": "Drucker", "entry": "TE1"}], "gelesen": ""})
window.ai_store.save(D, {"items": [
    {"von": "09:00", "bis": "09:40", "kunde": "Müller GmbH", "kategorie": "Telefonsupport",
     "beschreibung": "Druckerproblem am Telefon gelöst", "sicherheit": 0.9},
    {"von": "11:00", "bis": "11:30", "kunde": "Meier", "kategorie": "Fernwartung",
     "beschreibung": "Update", "sicherheit": 0.7},
    {"von": "13:00", "bis": "13:30", "kunde": "Weg", "status": "verworfen"}]})
window.timeline._tv_index = window.timeline._tv_index or __import__("log_parsers").ConnectionIndex([])
window.timeline._rdm_index = window.timeline._rdm_index or __import__("log_parsers").ConnectionIndex([])
window.timeline._vpn_index = window.timeline._vpn_index or __import__("log_parsers").ConnectionIndex([])
export = window.collect_export(3)
export["pc"] = "ARBEITS-PC"
day = export["tage"][D]
assert day["verbindungen"][0]["customer_name"] == "Müller GmbH", day
assert day["personalzeit"]["zeiten"] and day["m42"][0]["ticket"] == "TCK1"
assert day["taetigkeiten"]["items"][0]["text"] == "Drucker eingerichtet"
assert len(day["ki"]["items"]) == 3
window._save_transfer_code(datakey.new_code())  # wie „Übertragungsschlüssel eingeben“ auf beiden PCs
data = transfer.to_bytes(export, window.transfer_code())
assert transfer.is_encrypted(data)

# ---- "PAW": eigene Daten leeren, dann übernehmen
window.timeline.activities.clear()
window.journal.delete(window.journal.load(D)["items"][0])
for name in ("personalzeiten", "m42_buchungen", "ki_vorschlaege"):
    window.data_store.delete(name, D)
window.ai_store._cache.clear()
window.timeline._remote_cache.clear()
assert window.import_export(window.parse_export(data))
assert window.data_store.has("uebernommen")

calls = [a for a in window.timeline.activities_for(qd) if a.get("type") == "Telefonat"]
assert calls and calls[0]["source_pc"] == "ARBEITS-PC" and "von ARBEITS-PC" in calls[0]["details"], calls
docs = window.journal.entries(D)
assert docs and docs[0]["doc_item"]["von_pc"] == "ARBEITS-PC"
assert [i[1] for i in entry_menu_items(docs[0]) if i] == ["copy"], "übernommene Tätigkeit nur kopieren"
assert not window.doc_candidates(D), "dokumentierter Anruf gilt auch auf der PAW als dokumentiert"
assert window.personal_day_for(D)["zeiten"][0]["start"].endswith("08:00:00")
band = window.m42_band(D)
assert any(e.get("m42") for e in band) and any(e.get("m42_gap") for e in band), band
# KI-Vorschläge vom Arbeits-PC (der verworfene nicht); der zur Tätigkeit passende gilt als übernommen
ai = window.ai_day_entries(D)
assert [(e["start"][11:16], e["von_pc"]) for e in ai] == [("09:00", "ARBEITS-PC"), ("11:00", "ARBEITS-PC")], ai
assert ai[0]["status"] == "übernommen" and ai[1]["status"] == "", ai
assert "reject" not in [i[1] for i in entry_menu_items(ai[1]) if i], "fremde Vorschläge nicht verwerfen"
window.on_ai_action(ai[1], "verwerfen")  # geht nicht, ändert nichts
window.on_ai_action(ai[1], "übernehmen")  # wird hier zur Tätigkeit
assert [e["status"] for e in window.ai_day_entries(D)] == ["übernommen", "übernommen"]
assert not window.data_store.has("ki_vorschlaege", D), "eigene KI-Ablage bleibt unberührt"
window.date_edit.setDate(qd)
window.change_view("ai")
assert len(window.list_entries) == 2, window.list_entries
window.change_view("grouped")
assert window.collect_export(3)["tage"].get(D, {}).get("ki") is None, "übernommene KI nicht weiterexportieren"
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
