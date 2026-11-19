"""Suchfeld im Fenster „Tickets“ (tickets_dialogs.py, M42Reader.search_ticket_list).

Prüft mit dem echten M42Reader und erfundenen Antworten: sofort Treffer aus der geladenen Liste,
unter 3 Zeichen keine Abfrage, nach der Tipppause Suche in Matrix42 in der gewählten Kategorie,
ältere Treffer dazu, Statuszeile sagt, was gesucht wurde, „Geschlossene“ gilt, Leeren nimmt die
Suchtreffer wieder weg, Kategoriewechsel sucht dort.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from m42_reader import M42Reader  # noqa: E402
from tickets_dialogs import TicketsDialog  # noqa: E402
d = tempfile.mkdtemp()
r = M42Reader("https://m42.example/wm/", os.path.join(d, "m42.json"), os.path.join(d, "p"))
queries = []
def fetch(method, path, body=None, content_type=None):
    if "userinfo" in path:
        return {"Id": "me", "FirstName": "Filip", "LastName": "Kroczak"}
    cond = body["Groups"][0]["Conditions"]
    if not cond or cond[0]["Property"] == "Recipient" and cond[0]["Value"] == ["Kroczak"]:
        if "filters=" in path or not cond:  # Kategorie Alle
            return [{"TicketNumber": "TCK0000009001", "Id": "n1", "Subject": "Drucker neu", "State": "Offen",
                     "CreatedDate": "2026-11-18T08:00:00Z"}]
    queries.append((cond[0]["Property"], cond[0]["Value"][0]) if cond else None)
    if cond and cond[0]["Property"] == "Subject" and cond[0]["Value"] == ["drucker"]:
        return [{"TicketNumber": "TCK0000001234", "Id": "x1", "Subject": "Drucker spinnt", "State": "Offen",
                 "CreatedDate": "2025-03-01T08:00:00Z"},
                {"TicketNumber": "TCK0000009001", "Id": "n1", "Subject": "Drucker neu", "State": "Offen",
                 "CreatedDate": "2026-11-18T08:00:00Z"},
                {"TicketNumber": "TCK0000001235", "Id": "x2", "Subject": "Drucker tot", "State": "Geschlossen",
                 "CreatedDate": "2025-02-01T08:00:00Z"}]
    return []
r._fetch = fetch
r.own_name = "Kroczak, Filip"
r.load_my_tickets = lambda: r._read_my_tickets()
r.load_tickets = lambda key, fid="": r._read_tickets(key, fid)
r.load_ticket_filters = lambda: None
dlg = TicketsDialog(r); dlg.show(); app.processEvents()
dlg.category_buttons["all"].click(); app.processEvents()
queries.clear()  # nur die Suchabfragen zählen
def wait(ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents(); time.sleep(0.02)
QTest.keyClicks(dlg.filter_edit, "dr"); app.processEvents()
assert "Ab 3 Zeichen" in dlg.status.text() and len(dlg.visible_rows()) == 1, dlg.status.text()
assert not queries  # zu kurz: noch nicht in Matrix42
QTest.keyClicks(dlg.filter_edit, "ucker"); app.processEvents()
assert "suche auch ältere in Matrix42" in dlg.status.text() and len(dlg.visible_rows()) == 1, dlg.status.text()
assert not queries  # erst nach der Tipppause
wait(1500)
assert [x["ticket"] for x in dlg.visible_rows()] == ["TCK0000009001", "TCK0000001234"]  # neu oben, alt dazu
st = dlg.status.text()
assert "2 Treffer für „drucker“" in st and "ohne Datumsgrenze" in st and "1 geschlossene ausgeblendet" in st, st
assert all(q[1] == "drucker" for q in queries) and len(queries) == 4, queries
dlg.closed_switch.setChecked(True); app.processEvents()
assert len(dlg.visible_rows()) == 3 and "3 Treffer" in dlg.status.text()
assert not dlg.more_button.isVisible()
dlg.filter_edit.clear(); app.processEvents()
assert len(dlg.visible_rows()) == 1 and "Alle: 1 Ticket" in dlg.status.text(), dlg.status.text()  # Suchtreffer weg
n = len(queries)
QTest.keyClicks(dlg.filter_edit, "drucker"); QTest.keyClick(dlg.filter_edit, Qt.Key_Return)
assert len(dlg.visible_rows()) == 3 and len(queries) == n  # schon gesucht: Treffer sofort, keine neue Abfrage
dlg.category_buttons["mine"].click()  # andere Kategorie, Suchtext bleibt: dort suchen
wait(800)
assert "Meine Tickets: 0 Treffer für „drucker“" in dlg.status.text() and len(queries) > n, dlg.status.text()

print("Ticketsuche ok")
sys.stdout.flush()
import safe_io  # noqa: E402  Ende ohne Qt-Aufräumen (Absturz unter Windows)
safe_io.hard_exit(0)
