"""Tickets in Matrix42 anlegen und schließen: Logik ohne Browser (Felder wie im Ticket-Mitschnitt
vom 12.11.2026). Den Ablauf im Leser prüft test_leser_* mit einem nachgebauten _fetch."""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import m42_tickets as mt  # noqa: E402
from m42_booking import BookingError  # noqa: E402

ME, MELDER, CAT, SLA = "me-1", "melder-1", "cat-fileserver", "sla-sr"
TEMPLATE = {"Sys-Entity": "SPSActivityTypeTicket", "ID": "ticket-1", "Sys-IsNew": True,
            "SPSActivityClassBase": {"NotifyResponsible": True, "Subject": None, "Category": "cat-default",
                                     "Initiator": None, "Recipient": None, "Urgency": 2, "Impact": 2,
                                     "AttachedUsers": {"AddedRelations": [], "ReferenceTo": "SPSUserClassBase"}},
            "SPSActivityClassIncident": {"EntryBy": 0, "Callback": None},
            "SPSCommonClassBase": {"CostCenter": "cc", "OU": "ou", "Location": "loc", "State": None},
            "InitialData": {"Sla": {"TightestItem": "x"}, "Configuration": {"TicketType": 6, "UsePrefillAsset": True}}}
# Felder, die der Dialog im Mitschnitt beim Anlegen geschickt hat (Auswahl)
RECORDED_TOP = {"Sys-Entity", "ID", "Sys-IsNew", "SPSActivityClassBase", "SPSActivityClassIncident",
                "ITMTimeEntryClassTarget", "SPSCommonClassBase", "InitialData", "_type", "_id", "IsNew",
                "TicketTargetType", "isEdit"}
# POST /ticket/Close im Mitschnitt: genau diese Felder
RECORDED_CLOSE = {"ObjectIds", "CloseRelatedIncidents", "RetireAnnouncement", "AffectedAsset", "AffectedService",
                  "CausedByTickets", "CreateKbArticle", "Reason", "Comments", "ServicesAvailability",
                  "AssetsAvailability", "SendMailToUsers", "ErrorType", "SendMailToInitiator", "NotifyResponsible",
                  "ActivityAction", "WorkflowInstanceId", "CategoryId", "KBArticle", "InformFurtherUsers",
                  "SendMailToRelatedResponsibleUsers", "SkipFailIfAlreadyClosed", "ClosureAttachmentFileIDs"}


def test_ticket_anlegen_felder():
    e = mt.ticket_entity(TEMPLATE, mt.INCIDENT, " Rückmeldung ", "Zeile 1\n<b>2</b>", CAT, MELDER, ME,
                         SLA, impact=3, urgency=1, callback="02542 1")
    assert RECORDED_TOP <= set(e)
    base = e["SPSActivityClassBase"]
    assert (base["Subject"], base["Category"], base["Initiator"], base["Creator"], base["SLA"]) == \
        ("Rückmeldung", CAT, MELDER, ME, SLA)
    assert base["DescriptionHTML"] == "<p>Zeile 1</p><p>&lt;b&gt;2&lt;/b&gt;</p>"
    assert (base["Impact"], base["Urgency"]) == (3, 1)
    assert base["AttachedUsers"] == {"AddedRelations": [], "RemovedRelations": []}
    assert e["SPSActivityClassIncident"]["Callback"] == "02542 1"
    assert e["InitialData"]["Configuration"] == {"TicketType": 0, "UsePrefillAsset": True}
    assert e["SPSCommonClassBase"]["Bookings"] == {"AddedRelations": [], "RemovedRelations": []}
    assert TEMPLATE["InitialData"]["Configuration"]["TicketType"] == 6  # Vorlage unverändert
    assert json.loads(mt.wrap(e)[1:-1])["ID"] == "ticket-1"
    sr = mt.ticket_entity(TEMPLATE, mt.SERVICE_REQUEST, "x", "", CAT, MELDER, ME)
    assert sr["InitialData"]["Configuration"]["TicketType"] == 6 and sr["SPSActivityClassBase"]["DescriptionHTML"] is None


@pytest.mark.parametrize("args, msg", [
    (dict(subject=" "), "Betreff"), (dict(initiator=None), "Melder"), (dict(category=""), "Kategorie"),
    (dict(creator=""), "Benutzer"), (dict(ticket_type=5), "Störung"), (dict(template={}), "Vorlage")])
def test_ticket_anlegen_pflichtfelder(args, msg):
    kw = dict(template=TEMPLATE, ticket_type=0, subject="x", description="", category=CAT,
              initiator=MELDER, creator=ME)
    kw.update(args)
    with pytest.raises(BookingError, match=msg):
        mt.ticket_entity(**kw)


def test_schliessen_felder():
    body = mt.close_body("ticket-1", "Erledigt nach Kundenwunsch", CAT)
    assert set(body) == RECORDED_CLOSE
    assert body["Comments"] == "<p>Erledigt nach Kundenwunsch</p>" and body["Reason"] == 427
    assert body["ObjectIds"] == ["ticket-1"] and body["SendMailToInitiator"] is True
    assert mt.close_body("t", "x", CAT, notify_initiator=False)["SendMailToInitiator"] is False
    with pytest.raises(BookingError, match="Lösungstext"):
        mt.close_body("ticket-1", "  ", CAT)


def test_antworten_lesen():
    assert mt.own_user({"Id": ME, "FirstName": "Filip", "LastName": "Kroczak"}) == {"id": ME, "name": "Kroczak, Filip"}
    assert mt.own_user({}) is None
    users = mt.users_from_fragments({"Fragments": [
        {"Id": MELDER, "DisplayString": "Brüning, Gerd - WiRoPa GmbH "}, {"DisplayString": "ohne Id"}]})
    assert users == [{"id": MELDER, "name": "Brüning, Gerd - WiRoPa GmbH"}]
    assert mt.users_from_fragments(None) == []
    tree = [{"Id": "a", "DisplayString": "Visaas", "Chidren": [
        {"Id": "b", "DisplayString": "Server", "Chidren": [{"Id": CAT, "DisplayString": "Fileserver"}]}]},
        {"Id": "c", "DisplayString": "Cloud Funktionsabweichung"}]
    assert [c["path"] for c in mt.categories_from_tree(tree)] == [
        "Cloud Funktionsabweichung", "Visaas", "Visaas > Server", "Visaas > Server > Fileserver"]
    assert mt.created_ticket({"Entity": {"Sys-Name": "TCK0000050866", "ID": "ticket-1",
                                         "Sys-Entity": "SPSActivityTypeServiceRequest"}}) == \
        {"ticket": "TCK0000050866", "id": "ticket-1", "type": "SPSActivityTypeServiceRequest"}
    with pytest.raises(BookingError):
        mt.created_ticket({"Entity": {}})
    assert "TicketType=0" in mt.sla_path(CAT, MELDER, 0, 2) and "Priority=-1" in mt.sla_path(CAT, MELDER, 0, None)


def _reader(tmp_path, answers, fail=None):
    from m42_reader import M42Reader
    reader = M42Reader("https://m42.example/wm/", str(tmp_path / "m42.json"), str(tmp_path / "p"))
    reader.load_my_tickets = lambda: None
    calls = []

    def fetch(method, path, body=None, content_type=None):
        calls.append((method, path.split("?")[0], body))
        if fail and re.search(re.escape(fail) + r"(/|$)", path.split("?")[0]):
            raise BookingError("Zeitüberschreitung")
        return next((v for k, v in answers.items() if k in path), None)
    reader._fetch = fetch
    got = []
    reader.ticket_task_done.connect(got.append)
    return reader, calls, got


ANSWERS = {"/userinfo": {"Id": ME, "FirstName": "Filip", "LastName": "Kroczak"},
           "GetNewData": {"Entity": TEMPLATE}, "/activity/category/": {"Impact": 2, "Urgency": 2},
           "suitableSLAs": {"TightestItem": SLA}, "UserDetails": {"Phone": "02542 1"},
           "UpdateData": {"Entity": {"Sys-Name": "TCK0000050866", "ID": "ticket-1",
                                     "Sys-Entity": "SPSActivityTypeServiceRequest"}},
           "CloseWizardInitialData": {"TicketCategory": CAT, "CloseRelatedIncidents": True}}
REQUEST = {"type": mt.SERVICE_REQUEST, "initiator": MELDER, "category": CAT, "subject": "Test",
           "description": "", "take_over": True}


def test_leser_ticket_anlegen(tmp_path):
    reader, calls, got = _reader(tmp_path, ANSWERS)
    reader._ticket_task("create", {"request": REQUEST})
    assert got[-1]["ok"], got[-1]
    assert got[-1]["data"] == {"ticket": "TCK0000050866", "id": "ticket-1", "type": "SPSActivityTypeServiceRequest",
                               "taken_over": True, "warning": ""}
    paths = [p.split("/api/")[1] for _m, p, _b in calls]
    assert paths == ["userinfo", f"WidgetDialog/GetNewData/{mt.DEFAULT_IDS['ticket_dialog']}",
                     f"activity/category/{CAT}/", "activity/suitableSLAsForTicket/",
                     f"activity/UserDetails/{MELDER}/", f"WidgetDialog/UpdateData/{mt.DEFAULT_IDS['ticket_dialog']}",
                     "activity/TakeOver"], paths
    saved = json.loads(calls[5][2][1:-1])
    assert saved["SPSActivityClassBase"]["Creator"] == ME and saved["SPSActivityClassBase"]["SLA"] == SLA
    assert calls[6][2] == {"Objects": [{"ObjectIds": ["ticket-1"], "TypeName": "SPSActivityTypeServiceRequest"}]}

    # Störung gewählt, Matrix42 macht etwas anderes daraus: Hinweis; ohne Übernehmen kein TakeOver
    reader, calls, got = _reader(tmp_path, ANSWERS)
    reader._ticket_task("create", {"request": dict(REQUEST, type=mt.INCIDENT, take_over=False)})
    assert got[-1]["ok"] and "ServiceRequest" in got[-1]["data"]["warning"]
    assert not any("TakeOver" in p for _m, p, _b in calls)


def test_leser_anlegen_unklar_und_uebernehmen_fehlt(tmp_path):
    reader, calls, got = _reader(tmp_path, ANSWERS, fail="UpdateData")
    reader._ticket_task("create", {"request": REQUEST})
    assert not got[-1]["ok"] and got[-1]["unclear"] and "nachsehen" in got[-1]["error"]

    reader, calls, got = _reader(tmp_path, ANSWERS, fail="TakeOver")
    reader._ticket_task("create", {"request": REQUEST})
    assert got[-1]["ok"] and not got[-1]["data"]["taken_over"] and "Übernehmen" in got[-1]["data"]["warning"]

    reader, calls, got = _reader(tmp_path, ANSWERS, fail="GetNewData")  # vor dem Speichern: klar gescheitert
    reader._ticket_task("create", {"request": REQUEST})
    assert not got[-1]["ok"] and not got[-1].get("unclear")


def test_leser_ticket_schliessen(tmp_path):
    reader, calls, got = _reader(tmp_path, ANSWERS)
    req = {"id": "ticket-1", "type": "SPSActivityTypeIncident", "ticket": "TCK1", "solution": "Gelöst", "notify": False}
    reader._ticket_task("close", {"request": req})
    assert got[-1]["ok"], got[-1]
    assert [p for _m, p, _b in calls] == ["/m42Services/api/ticket/CloseWizardInitialData/",
                                         "/m42Services/api/ticket/Close"]
    assert calls[0][2] == ["ticket-1"]
    assert calls[1][2]["CategoryId"] == CAT and calls[1][2]["SendMailToInitiator"] is False

    reader, calls, got = _reader(tmp_path, ANSWERS, fail="/ticket/Close")
    reader._ticket_task("close", {"request": req})
    assert got[-1]["unclear"]


def test_leser_melder_und_kategorien(tmp_path):
    answers = {"forControl": {"Fragments": [{"Id": MELDER, "DisplayString": "Brüning, Gerd - WiRoPa GmbH"}]},
               "entity/tree": [{"Id": CAT, "DisplayString": "Ticketeingang"}]}
    reader, calls, got = _reader(tmp_path, answers)
    reader._ticket_task("users", {"text": "brün"})
    assert got[-1]["data"] == [{"id": MELDER, "name": "Brüning, Gerd - WiRoPa GmbH"}]
    assert calls[0][2]["searchFilter"] == "brün"
    reader._ticket_task("categories", {})
    assert got[-1]["data"] == [{"id": CAT, "path": "Ticketeingang"}]


def test_meine_tickets_mit_kennung(tmp_path):
    reader, calls, got = _reader(tmp_path, {"/userinfo": {"Id": ME, "FirstName": "Filip", "LastName": "Kroczak"},
                                            "GetData": [
        {"TicketNumber": "TCK0000000001", "Sys-ObjectId": "1", "State": "Neu", "Recipient": "Kroczak, Filip - Systems",
         "Recipient_Value": ME, "Sys-Entity": "SPSActivityTypeIncident", "CreatedDate": "2026-11-01"},
        {"TicketNumber": "TCK0000000002", "Sys-ObjectId": "2", "State": "Neu", "Recipient": "Kroczak, Filip - Systems",
         "Recipient_Value": "anderer", "CreatedDate": "2026-11-02"}]})
    loaded = []
    reader.my_tickets_loaded.connect(loaded.append)
    reader._read_my_tickets()
    rows = loaded[-1]["rows"]
    assert [r["ticket"] for r in rows] == ["TCK0000000001"] and rows[0]["type"] == "SPSActivityTypeIncident"
    assert reader.user_name == "Kroczak, Filip" and reader.user_id == ME
