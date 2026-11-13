"""Matrix42-Buchungen mit echtem Edge/Chromium gegen einen Nachbau der Kalenderseite lesen.

Die Seite startet in der Tagesansicht (wie zuletzt benutzt), Zeitzeuge muss auf die Woche
umschalten, die aktuelle und die letzte Woche lesen und beim Blättern eine ältere Woche.
Die Einträge kommen verzögert per Abfrage, wie im Original.

Danach dieselbe Seite mit Token im localStorage: Zeitzeuge liest über die Schnittstelle
(POST /m42Services/api/WidgetList/GetData/<Widget>, wie im Mitschnitt vom 02.11.2026), ohne
den Kalender anzufassen.

Zum Schluss eine Buchung wie im Buchungs-Mitschnitt: Ticket suchen, Vorlage holen, Ticketbezug
holen, Zeiterfassung speichern (m42_booking.py, M42Reader.book).
"""
import http.server
import json
import os
import sys
import tempfile
import threading
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from m42_reader import M42Reader, load_store, week_start  # noqa: E402

MOCK = os.path.join(ROOT, "tests", "mock_m42")
LOGIN = [True]  # erster Aufruf: Anmeldeseite
monday = date.fromisoformat(week_start(date.today().isoformat()))


def events_for(day):
    """Zwei Buchungen je Werktag, eine überlappend (wie im echten Kalender)."""
    if day.weekday() >= 5:
        return []
    d = day.isoformat()
    return [
        {"date": d, "from": "08:10", "to": "08:55", "te": "TE0000087192",
         "title": "Systems - TCK0000049374 - Praktikanten / Azubi Oktober 2026"},
        {"date": d, "from": "08:38", "to": "08:53", "te": "TE0000087193",
         "title": "Elektroanlagen Röring GmbH  - TCK0000048883 - Computer Verdacht auf Viren"},
        {"date": d, "from": "14:20", "to": "16:40", "te": "TE0000086853",
         "title": "A.Fasselt Engineering GmbH  - TCK0000049191 - Netscaler"},
    ]


TOKEN = "eyJ0ZXN0.eyJ0ZXN0.c2ln"
WIDGET = "05d8b58d-5764-ef11-debc-0050569e2f05"
API_CALLS = []
# Kalenderseite mit Anmeldung über das Token (ohne Kalender: liest nur die Schnittstelle)
API_PAGE = ("<html><body><script>localStorage.setItem('mx.auth.session.token', '%s');</script>"
            "<div id='leer'>Kalender</div></body></html>" % TOKEN).encode("utf-8")


def api_items(a, b):
    """Einträge wie die Schnittstelle sie liefert: Zeit in UTC, Kunde mit Nummer, Status."""
    out, day = [], a.date()
    while datetime.combine(day, datetime.min.time()) < b:
        for e in events_for(day):
            s = datetime.fromisoformat(f"{e['date']} {e['from']}").astimezone(timezone.utc)
            t = datetime.fromisoformat(f"{e['date']} {e['to']}").astimezone(timezone.utc)
            customer, ticket, subject = [x.strip() for x in e["title"].split(" - ", 2)]
            out.append({"Sys-Entity": "ITMTimeEntryType", "ObjectId": e["te"],
                        "Customer": f"{customer}  (273)", "Activity": f"{ticket} - {subject}",
                        "TicketInfo": e["title"], "State": "Neu", "ActivityType": "Administration",
                        "Start": s.strftime("%Y-%m-%dT%H:%M:%SZ"), "End": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "WorktimeRounded": 45, "Anwender": "nicht gebraucht",
                        "Anwender_Value": "user-1"})
        day += timedelta(days=1)
    return out


BOOKED = []  # gespeicherte Zeiterfassungen (UpdateData)
IDS = {"ticket_list": "31db2d14-df00-cddd-4759-08dcbac24c70",
       "dialog": "98661499-140b-ce9b-55da-08dc798f2fc8",
       "target_source": "b949cab7-a12d-a5bd-b855-d32a6a00074e"}
API = "/m42Services/api"


class Handler(http.server.BaseHTTPRequestHandler):
    def _json(self, value, status=200):
        data = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)

    def _booking(self, path, body):
        """Buchen wie im Mitschnitt. True, wenn die Abfrage hierher gehörte."""
        text = body.decode("utf-8")
        ctype = self.headers.get("Content-Type", "")
        if path == f"{API}/WidgetList/GetData/{IDS['ticket_list']}":
            cond = json.loads(text)["Groups"][0]["Conditions"][0]
            field, value = cond["Property"], cond["Value"][0].lower()
            if field == "Initiator":  # ein Feld, das die Liste nicht kennt: nur dieses fehlt
                self._json({"Message": "unbekannte Spalte"}, 400)
                return True
            hits = [{"Sys-Entity": "SPSActivityTypeServiceRequest", "TicketNumber": "TCK0000049374",
                     "Id": "teil-1", "Sys-ObjectId": "ticket-1",  # wie im Original: zwei Kennungen
                     "Subject": "Praktikanten", "Customer": "Systems  (999830)",
                     "Recipient": "Kroczak, Filip - Systems", "State": "In Bearbeitung",
                     "CreatedDate": "2026-10-01T08:00:00Z"},
                    {"TicketNumber": "TCK0000049374999", "Id": "falsch", "Subject": "Anderes",
                     "Customer": "Müller GmbH  (12)", "CreatedDate": "2026-10-02T08:00:00Z"}]
            self._json([h for h in hits if value in (h.get(field) or "").lower()])
        elif path == f"{API}/WidgetDialog/GetNewData/{IDS['dialog']}":
            ok = text == "'\"objectType=ITMTimeEntryType&selectedObjects=ticket-1\"'" and "text/plain" in ctype
            self._json({"Entity": {"Sys-Entity": "ITMTimeEntryType", "ID": "neu-1", "Sys-IsNew": True,
                                   "SPSCommonClassBase": {"CostCenter": "cc", "OU": "ou", "Location": "loc"},
                                   "ITMTimeEntryClassBase": {"Pause": 0}, "ITMILVClassBase": {"State": None}}}
                       if ok else {"Message": "falscher Inhalt"}, 200 if ok else 400)
        elif path == f"{API}/WidgetCommon/{IDS['dialog']}/{IDS['target_source']}/custom_Target.ITMTimeEntryClassTarget":
            ok = json.loads(text) == [{"Name": "@id", "Value": "ticket-1", "Type": 1}]
            self._json({"Entity": {"ITMTimeEntryClassTarget": [{"ID": "target-1", "TargetSLA": "sla-1", "TargetOU": "kunde-ou"}]}}
                       if ok else {}, 200 if ok else 400)
        elif path == f"{API}/WidgetDialog/UpdateData/{IDS['dialog']}":
            if not (text.startswith("'{") and text.endswith("}'")):
                self._json({"Message": "Inhalt nicht in Anführungszeichen"}, 400)
                return True
            BOOKED.append(json.loads(text[1:-1]))
            self._json({"Entity": {"Sys-Entity": "ITMTimeEntryType", "ID": "neu-1", "Sys-Name": "TE0000099999"}})
        else:
            return False
        return True

    def do_POST(self):
        parts = urlsplit(self.path)
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self.send_error(401)
            return
        if self._booking(parts.path, body):
            return
        if not parts.path.startswith("/m42Services/api/WidgetList/GetData/"):
            self.send_error(404)
            return
        if parts.path.rsplit("/", 1)[-1] != WIDGET:
            self.send_error(400)
            return
        # Zeitraum aus dem Filter (wie im Mitschnitt: Start >= a … End <= b)
        values = [c["Value"] for g in json.loads(body)["Groups"][1]["Groups"][:1] for c in g["Conditions"]]
        a = datetime.fromisoformat(values[0][0].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        b = datetime.fromisoformat(values[1][1].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        API_CALLS.append((a, b))
        items = api_items(a, b)
        data = json.dumps(items).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("TotalCount", str(len(items)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path.endswith("/kalender-api"):
            body, kind = API_PAGE, "text/html"
        elif parts.path.endswith("/kalender"):
            if LOGIN[0]:
                body = b'<html><body><form><input type="password"></form></body></html>'
            else:
                body = open(os.path.join(MOCK, "index.html"), "rb").read()
            kind = "text/html"
        elif parts.path.endswith("/events.json"):
            q = parse_qs(parts.query)
            a, b = date.fromisoformat(q["from"][0]), date.fromisoformat(q["to"][0])
            items = []
            while a <= b:
                items += events_for(a)
                a += timedelta(days=1)
            time.sleep(0.4)  # Server braucht etwas
            body, kind = json.dumps(items).encode("utf-8"), "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Edge wurde beim Beenden mitten im Laden geschlossen

    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 8815), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()

app = QCoreApplication(sys.argv)
tmp = tempfile.mkdtemp()
data_file = os.path.join(tmp, "m42_buchungen.json")
profile = os.path.join(tmp, "profil")
URL = "http://127.0.0.1:8815/wm/app-ServiceDesk/kalender"


def saved():
    return load_store(data_file)[0]  # aus der Datenbank (früher m42_buchungen.json)


def run(until, what, setup=None, url=None):
    reader = M42Reader(url or URL, data_file, profile, weeks_back=1)
    reader.start()
    if setup:
        setup(reader)
    deadline = time.time() + 90
    while time.time() < deadline and not until(reader):
        time.sleep(0.5)
    ok = until(reader)
    print("ok:" if ok else "FEHLER:", what, "|", reader.status)
    reader.stop()
    time.sleep(2)
    if not ok:
        print(f"::error title=Matrix42-Test::{what} | Status: {reader.status}")
        sys.exit(1)


# 1. Anmeldeseite wird erkannt
run(lambda r: r.needs_login, "Anmeldeseite erkannt")
LOGIN[0] = False

# 2. Aktuelle und letzte Woche lesen (Seite startet in der Tagesansicht)
last_monday = monday - timedelta(weeks=1)
run(lambda r: monday.isoformat() in saved() and last_monday.isoformat() in saved(),
    "aktuelle und letzte Woche gelesen")
days = saved()
for d in (monday, last_monday):
    items = days[d.isoformat()]
    assert len(items) == 3, items
    first = items[0]
    assert first["start"] == f"{d} 08:10:00" and first["end"] == f"{d} 08:55:00", first
    assert first["customer"] == "Systems" and first["ticket"] == "TCK0000049374", first
    assert first["subject"] == "Praktikanten / Azubi Oktober 2026" and first["entry"] == "TE0000087192"
    assert items[1]["customer"] == "Elektroanlagen Röring GmbH", items[1]
sunday = (monday + timedelta(days=6)).isoformat()
assert days.get(sunday) == [], "auch leere Tage der Woche gelten als gelesen"

# 3. Beim Blättern eine ältere Woche nachlesen
old = monday - timedelta(weeks=5)
run(lambda r: old.isoformat() in saved(), "ältere Woche beim Blättern gelesen",
    setup=lambda r: r.want((old + timedelta(days=2)).isoformat()))
assert len(saved()[old.isoformat()]) == 3
assert not API_CALLS, "ohne Token liest Zeitzeuge aus der Seite"

# 4. Über die Schnittstelle (Seite hat ein Token, aber keinen Kalender)
data_file = os.path.join(tempfile.mkdtemp(), "m42_buchungen.json")  # eigener Speicher, ohne 2./3.
run(lambda r: monday.isoformat() in saved() and last_monday.isoformat() in saved(),
    "Woche über die Schnittstelle gelesen", url=URL + "-api")
assert API_CALLS, "Schnittstelle nicht abgefragt"
assert API_CALLS[0][0] == datetime.combine(monday, datetime.min.time()), API_CALLS[0]
assert API_CALLS[0][1] == datetime.combine(monday + timedelta(days=7), datetime.min.time()), API_CALLS[0]
items = saved()[monday.isoformat()]
assert len(items) == 3, items
first = items[0]
assert first["start"] == f"{monday} 08:10:00" and first["end"] == f"{monday} 08:55:00", first
assert first["customer"] == "Systems" and first["ticket"] == "TCK0000049374", first
assert first["entry"] == "TE0000087192" and first["state"] == "Neu", first
assert items[1]["customer"] == "Elektroanlagen Röring GmbH", items[1]
assert saved().get(sunday) == []

# 5. Buchen wie im Buchungs-Mitschnitt (Benutzer aus den gelesenen Buchungen)
results = []
reader = M42Reader(URL + "-api", data_file, profile, weeks_back=0)
reader.booking_done.connect(results.append)
reader.start()
deadline = time.time() + 60
while time.time() < deadline and not reader.user_id:
    time.sleep(0.5)
assert reader.user_id == "user-1", reader.user_id
start = datetime.combine(monday, datetime.min.time()).replace(hour=15, minute=50)
assert reader.book({"ticket": "tck0000049374", "start": start, "end": start + timedelta(minutes=30),
                    "minutes": 30, "text": "- Praktikantenbetreuung", "activity_type": 20})
deadline = time.time() + 60
while time.time() < deadline and not results:  # Signal aus dem Hintergrund: Ereignisse abarbeiten
    app.processEvents()
    time.sleep(0.2)
reader.stop()
time.sleep(2)
assert results and results[0]["ok"], results
assert results[0]["entry"] == "TE0000099999" and results[0]["ticket"]["customer"] == "Systems"
entry = BOOKED[0]
base = entry["ITMTimeEntryClassBase"]
assert entry["ID"] == "neu-1" and entry["ITMILVClassBase"] == {"State": 10}
assert (base["Target"], base["SLA"], base["User"], base["ActivityType"]) == ("target-1", "sla-1", "user-1", 20)
assert base["Start"] == start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
assert base["WorktimeRounded"] == 30 and base["Description"] == "- Praktikantenbetreuung"
assert entry["SPSCommonClassBase"]["CostCenter"] == "cc"
assert entry["SPSCommonClassBase"]["OU"] == "kunde-ou"  # Kunde des Tickets, nicht die eigene OU
print("ok: Buchung angelegt |", reader.status)

# 6. Tickets suchen: Kunde, Benutzer, Ticketnummer oder Titel (ein Feld geht nicht: egal)
found = []
reader = M42Reader(URL + "-api", data_file, profile, weeks_back=0)
reader.tickets_found.connect(found.append)
reader.start()
for text in ("systems", "prakt", "kroczak", "müller"):
    reader.search_tickets(text)
    deadline = time.time() + 60
    while time.time() < deadline and len(found) < 1:
        app.processEvents()
        time.sleep(0.2)
    assert found and not found[0]["error"], found
    numbers = [r["ticket"] for r in found.pop()["rows"]]
    want = ["TCK0000049374999"] if text == "müller" else ["TCK0000049374"]
    assert numbers == want, (text, numbers)
reader.stop()
time.sleep(2)
print("ok: Tickets gesucht")

print("Matrix42 ok")
sys.stdout.flush()
import safe_io  # Ende ohne Qt-Aufräumen (Absturz unter Windows)
safe_io.hard_exit(0)
