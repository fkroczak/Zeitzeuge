"""Kommentieren, E-Mail senden, Pausieren, Weiterleiten: Felder wie im Mitschnitt vom 17.11.2026."""
from datetime import datetime, timedelta

import pytest

import m42_ticket_actions as ma
from m42_booking import BookingError

T = "7b9ec625-e0c2-c657-a1d0-08df3f48102c"
ME = "edc4be7d-2732-ef11-bcdb-0050569e3308"


def test_kommentar():
    body = ma.comment_body(T, "Kunde wünscht keine Mails", ME)
    assert body == {"ObjectId": T, "Comments": "<p>Kunde wünscht keine Mails</p>", "Publish": True, "EntryType": 0,
                    "Creator": ME, "FileIds": [], "IsFromEditDialog": False}
    assert ma.comment_body(T, "x", ME, public=False)["Publish"] is False
    with pytest.raises(BookingError):
        ma.comment_body(T, "  ", ME)


def test_mail_wie_im_dialog():
    body = ma.mail_body(T, "Kroczak <f.kroczak@itm-gruppe.com>; a@b.de", "#TCK1 - Test", "Hallo\nGruß",
                        signature="sig", known_users={"F.Kroczak@itm-gruppe.com": ME})
    assert body["To"] == {"Users": [ME], "BusinessPartners": [], "BusinessContacts": [], "Roles": [],
                          "Emails": "f.kroczak@itm-gruppe.com;a@b.de"}
    assert body["CC"]["Emails"] == "" and body["IsActiveCC"] is False and body["IsActiveBCC"] is False
    assert body["Text"] == "<p>Hallo</p><p>Gruß</p>" and body["Signature"] == "sig"
    assert body["SendersEmailAddress"] == "support@itm-gruppe.com" and body["IncidentId"] == T
    assert body["Attachments"] is None and body["ReplyText"] == ""
    assert ma.mail_body(T, "a@b.de", "s", "t", cc="c@d.de")["IsActiveCC"] is True
    with pytest.raises(BookingError):
        ma.mail_body(T, "kein Empfänger", "s", "t")
    assert ma.mail_subject("TCK0000050691", "Praktikanten") == "#TCK0000050691 - Praktikanten"


def test_signatur_aus_antworten():
    sig = ma.signature_class_id({"Entity": {"SPSUserClassBase": [{"EmailSignature": "29b9", "ID": ME}]}})
    assert sig == "29b9"
    assert ma.signature_object_id([{"Id": "29b9", "ObjectId": "2a35"}], sig) == "2a35"
    assert ma.signature_class_id({}) is None and ma.signature_object_id(None, "x") is None


def test_pausieren():
    now = datetime(2026, 11, 17, 14, 30)
    until = datetime(2026, 11, 19, 14, 30)
    body = ma.pause_body(T, until, 20000, "Nacht der Ausbildung", now=now)
    assert body["ObjectIds"] == [T] and body["Reason"] == 20000 and body["NotEscalateWhilePaused"] is True
    assert body["Comments"] == "<p>Nacht der Ausbildung</p>"
    assert body["ReminderDate"].endswith(".000Z") and body["ReminderDate"].startswith("2026-11-19T")
    with pytest.raises(BookingError):
        ma.pause_body(T, now - timedelta(hours=1), 421, "x", now=now)


def test_pausengruende():
    data = {"Values": [{"Value": 427, "DisplayString": "Aufgelöst", "State": 204, "Position": 1},
                       {"Value": 20000, "DisplayString": "Termin", "State": 203, "Position": 21},
                       {"Value": 421, "DisplayString": "Warten auf Kunde", "State": 203, "Position": 5},
                       {"Value": 426, "DisplayString": "versteckt", "State": 203, "Hidden": True}]}
    assert ma.pause_reasons(data) == [(421, "Warten auf Kunde"), (20000, "Termin")]
    assert ma.pause_reasons(None) == ma.PAUSE_REASONS


def test_weiterleiten():
    body = ma.forward_body(T, "SPSActivityTypeServiceRequest", user_id=ME, text="Hier")
    assert body == {"Tickets": [{"Item1": "SPSActivityTypeServiceRequest", "Item2": T}], "RoleID": None,
                    "UserID": ME, "OlaID": None, "Comments": "<p>Hier</p>"}
    with pytest.raises(BookingError):
        ma.forward_body(T, "x")
    roles = ma.roles([{"Id": "2", "Sys-DisplayName": "SD.ITM.Team Netzwerk"}, {"Id": "1", "Name": "SD.ITM.Team M365"}])
    assert [r["id"] for r in roles] == ["1", "2"]
    q = ma.forward_user_query("kroc")
    assert q["searchFilter"] == "kroc" and q["FilterExpression"]["Path"]["viewName"] == "Forward"


def test_leser_schickt_aktionen(tmp_path, monkeypatch):
    import threading
    from m42_reader import M42Reader
    reader = M42Reader("https://m42.example/wm/", str(tmp_path / "m42.json"), str(tmp_path / "p"))
    monkeypatch.setattr(threading.Thread, "start", lambda self: None)  # Liste nicht neu lesen
    calls = []

    def fetch(method, path, body=None, content_type=None):
        calls.append((method, path.split("?")[0], body))
        if path.endswith("/userinfo"):
            return {"Id": ME, "LastName": "Kroczak", "FirstName": "Filip"}
        if "UserInfo.SPSUserClassBase" in path:
            return {"Entity": {"SPSUserClassBase": [{"EmailSignature": "29b9"}]}}
        if path.endswith("/entity/fragments"):
            return [{"Id": "29b9", "ObjectId": "2a35"}]
        return None
    reader._fetch = fetch
    got = []
    reader.ticket_task_done.connect(got.append)
    reader._ticket_task("comment", {"request": {"id": T, "ticket": "TCK1", "text": "Hallo"}})
    assert got[-1]["ok"], got[-1]
    assert calls[-1][:2] == ("POST", "/m42Services/api/Journal/Add") and calls[-1][2]["Creator"] == ME
    reader._ticket_task("mail", {"request": {"id": T, "ticket": "TCK1", "to": "a@b.de", "subject": "s",
                                             "text": "t"}})
    assert got[-1]["ok"], got[-1]
    assert calls[-1][1] == "/m42Services/api/email/SendEmail" and calls[-1][2]["Signature"] == "2a35"
    until = (datetime.now() + timedelta(days=1)).isoformat()
    reader._ticket_task("pause", {"request": {"id": T, "until": until, "reason": 421, "text": "x"}})
    assert got[-1]["ok"] and calls[-1][1] == "/m42Services/api/activity/Pause"
    reader._ticket_task("forward", {"request": {"id": T, "type": "SPSActivityTypeIncident", "role": "r1"}})
    assert got[-1]["ok"] and calls[-1][2]["RoleID"] == "r1"
    reader._ticket_task("pause", {"request": {"id": T, "until": until, "reason": 421, "text": " "}})
    assert not got[-1]["ok"] and not got[-1].get("unclear")  # Fehler vor dem Senden: sicher nichts passiert


def test_schnellwahl_wiedervorlage():
    from ticket_action_dialog import default_pause_until, quick_pause_times
    friday = datetime(2026, 11, 20, 10, 15)  # Freitag
    times = dict(quick_pause_times(friday))
    assert times["in 1 Std."] == datetime(2026, 11, 20, 11, 15) and times["heute 16:00"].hour == 16
    assert times["morgen 8:00"] == datetime(2026, 11, 23, 8, 0)  # Montag, kein Wochenende
    assert times["nächsten Montag"] == datetime(2026, 11, 23, 8, 0)
    assert "heute 16:00" not in dict(quick_pause_times(friday.replace(hour=17)))
    assert default_pause_until(friday) == datetime(2026, 11, 23, 8, 0)


def test_als_gelesen_ueber_die_vorschau(tmp_path):
    """Matrix42 setzt „Neue Information erhalten“ zurück, wenn der Bearbeiter die Vorschau öffnet."""
    import m42_tickets as mt
    from m42_reader import M42Reader
    assert mt.preview_path("SPSActivityTypeServiceRequest", T).endswith(
        "/WidgetCommon/GetData/99912400-5e96-c50f-9a1b-08d4617dc22d/" + T + "?archived=false")
    assert "e54bab9f" in mt.preview_path("", T)  # unbekannte Art: Vorschau für Tickets
    reader = M42Reader("https://m42.example/wm/", str(tmp_path / "m42.json"), str(tmp_path / "p"))
    calls = []

    def fetch(method, path, body=None, content_type=None):
        calls.append((method, path))
        if "GetTicketEntityType" in path:
            return '"SPSActivityTypeIncident"'
        return {"Entity": {}} if "GetData" in path else []
    reader._fetch = fetch
    got = []
    reader.ticket_task_done.connect(got.append)
    reader._ticket_task("mark_read", {"id": T})
    assert got[-1]["ok"], got[-1]
    assert [m for m, _p in calls] == ["GET", "GET", "GET"]  # liest nur, schickt nichts zum Speichern
    assert "3b4c23df" in calls[1][1] and "/Journal?" in calls[2][1]


def test_anhang_name_und_adresse():
    import m42_tickets as mt
    fid = "a6c2d265-8c9f-4353-83fb-f277fe4db269"
    assert mt.file_path(fid) == f"/m42Services/api/fileStorage/{fid}"
    with pytest.raises(BookingError):
        mt.file_path("../x")
    assert mt.attachment_name('attachment; filename="a.eml"', "", fid) == "a.eml"
    assert mt.attachment_name("attachment; filename*=UTF-8''3CX%20%E2%80%93%20IP.eml", "", fid) == "3CX – IP.eml"
    assert mt.attachment_name('attachment; filename="..\\\\..\\\\boese:datei.pdf"', "", fid) == "boese_datei.pdf"
    assert mt.attachment_name("", "application/pdf", fid) == fid + ".pdf"
    assert mt.is_risky("Rechnung.pdf.exe") and not mt.is_risky("a.eml")


def test_leser_laedt_anhang(tmp_path, monkeypatch):
    import base64
    import json
    import tempfile
    from m42_reader import M42Reader
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    reader = M42Reader("https://m42.example/wm/", str(tmp_path / "m42.json"), str(tmp_path / "p"))
    reader._tools = type("Tools", (), {"alive": lambda self: True})()
    seen = []

    def evaluate(js, timeout=15, retries=0):
        seen.append(js)
        return json.dumps({"state": "ok", "status": 200, "data": base64.b64encode(b"Hallo").decode(),
                           "type": "message/rfc822", "disposition": 'attachment; filename="Alarm.eml"'})
    reader._evaluate = evaluate
    got = []
    reader.ticket_task_done.connect(got.append)
    fid = "a6c2d265-8c9f-4353-83fb-f277fe4db269"
    reader._ticket_task("attachment", {"file": fid})
    assert got[-1]["ok"], got[-1]
    data = got[-1]["data"]
    assert data["name"] == "Alarm.eml" and not data["risky"]
    assert open(data["path"], "rb").read() == b"Hallo"
    assert f"/m42Services/api/fileStorage/{fid}" in seen[0]
