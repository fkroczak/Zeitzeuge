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
OU_KOCH, CC_GLOBAL, LOC_GLOBAL = ("11111111-2222-3333-4444-555555555555", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                                  "99999999-8888-7777-6666-555555555555")
# GET /activity/UserDetails wie im Log vom 13.11.2026 (Feldnamen echt, Werte erfunden)
USER_DETAILS = {"Accounts": [], "Phone": "02542 1", "Email": "m@kunde.de",
                "OrgUnit": "Dr. Koch Beratung und Coaching", "OrgUnitId": OU_KOCH,
                "CostCenter": "Global", "CostCenterId": CC_GLOBAL, "Location": "Global", "LocationId": LOC_GLOBAL}
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


def test_frueherer_loesungstext():
    # Startwerte des Schließen-Assistenten haben Vorrang, HTML wird Klartext
    assert mt.previous_solution({"Comments": "<p>Treiber neu</p><p>getestet</p>"}) == "Treiber neu\ngetestet"
    # sonst aus dem Ticket (auch unbekannte Feldnamen mit „Solution“), leere Felder zählen nicht
    entity = {"SPSActivityClassBase": {"SolutionHTML": "<p>&nbsp;</p>", "ClosureSolutionText": "Lizenz erneuert"}}
    assert mt.previous_solution({"Comments": None}, entity) == "Lizenz erneuert"
    assert mt.previous_solution({}, {"SPSActivityClassBase": {"Comments": "kein Lösungsfeld"}}) == ""
    assert mt.previous_solution(None) == ""


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
           "suitableSLAs": {"TightestItem": SLA}, "UserDetails": USER_DETAILS,
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
    common = saved["SPSCommonClassBase"]  # Kunde des Melders, nicht die eigene OU (Systems)
    assert (common["OU"], common["CostCenter"], common["Location"]) == (OU_KOCH, CC_GLOBAL, LOC_GLOBAL)
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


def test_leser_loesungstext_vor_dem_schliessen(tmp_path):
    entity = {"ID": "ticket-1", "SPSActivityClassBase": {"Subject": "x", "SolutionHTML": "<p>Gelöst</p>"}}
    reader, calls, got = _reader(tmp_path, dict(ANSWERS, GetData=entity))
    reader._ticket_task("close_info", {"id": "ticket-1", "type": "SPSActivityTypeIncident"})
    assert got[-1]["ok"] and got[-1]["data"] == {"solution": "Gelöst"}, got[-1]
    assert calls[0][2] == ["ticket-1"] and "GetData" in calls[1][1]

    # Startwerte haben ihn schon: Ticket nicht extra laden
    answers = dict(ANSWERS, CloseWizardInitialData={"TicketCategory": CAT, "Comments": "<p>Alt</p>"})
    reader, calls, got = _reader(tmp_path, answers)
    reader._ticket_task("close_info", {"id": "ticket-1", "type": ""})
    assert got[-1]["data"] == {"solution": "Alt"} and len(calls) == 1


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


# ---------------------------------------------------------------- Bearbeiten (Mitschnitt 16:27:10)

EDIT_DIALOG = mt.DEFAULT_IDS["ticket_edit_dialog"]
LOADED = {"Sys-Entity": "SPSActivityTypeServiceRequest", "ID": "ticket-1", "Sys-IsNew": False,
          "Sys-TimeStamp": "00000000DC09AE2F", "Sys-Name": "TCK0000050866",
          "SPSActivityClassBase": {"Sys-TimeStamp": "00000000DC09AEE9", "ID": "base-1", "Subject": "Rückmeldung",
                                   "DescriptionHTML": "<p>- Anpassungen an ZRO&nbsp;Ordnern</p><table><tr><td>x</td>"
                                                      "</tr></table>", "Category": CAT, "Initiator": MELDER,
                                   "AttachedUsers": [{"Id": "u"}]},
          "SPSActivityClassIncident": {"Callback": "02542 1", "ChildMergedIncidents": []},
          "SPSCommonClassBase": {"State": 200, "Memorandums": []},
          "InitialData": {"Configuration": {"TicketType": 6}}}


def test_ticket_bearbeiten_felder():
    view = mt.ticket_view(mt.loaded_entity({"Entity": LOADED}))
    assert view == {"id": "ticket-1", "ticket": "TCK0000050866", "type": "SPSActivityTypeServiceRequest",
                    "subject": "Rückmeldung", "description": "- Anpassungen an ZRO Ordnern\nx",
                    "category": CAT, "rich": True, "stamp": "00000000DC09AE2F/00000000DC09AEE9"}
    assert mt.loaded_entity(LOADED) is LOADED  # auch ohne Hülle
    with pytest.raises(BookingError):
        mt.loaded_entity({"Entity": {"ID": "x"}})

    # nur hinten ergänzt: alte Beschreibung bleibt Zeichen für Zeichen, Ergänzung hinten dran
    e = mt.edited_entity(LOADED, " Rückmeldung ZRO ", view["description"] + "\nNeu: <Ordner>\nZeile 2")
    base = e["SPSActivityClassBase"]
    assert base["DescriptionHTML"] == LOADED["SPSActivityClassBase"]["DescriptionHTML"] + \
        "<p>Neu: &lt;Ordner&gt;</p><p>Zeile 2</p>"
    assert base["Subject"] == "Rückmeldung ZRO" and base["Category"] == CAT and base["Initiator"] == MELDER
    assert base["AttachedUsers"] == mt.EMPTY and base["Sys-TimeStamp"] == "00000000DC09AEE9"
    assert e["SPSActivityClassIncident"] == {"Callback": "02542 1", "ChildMergedIncidents": mt.EMPTY}
    assert e["SPSCommonClassBase"]["State"] == 200 and e["SPSCommonClassBase"]["Memorandums"] == mt.EMPTY
    assert (e["Sys-EntityState"], e["_id"], e["_type"], e["IsNew"]) == \
        (202, "ticket-1", "SPSActivityTypeServiceRequest", False)
    assert (e["Sys-Entity"], e["Sys-TimeStamp"], e["InitialData"]) == \
        ("SPSActivityTypeServiceRequest", "00000000DC09AE2F", LOADED["InitialData"])
    assert LOADED["SPSActivityClassBase"]["Subject"] == "Rückmeldung"  # Vorlage unverändert

    # Beschreibung umgeschrieben: Klartext ersetzt sie
    e = mt.edited_entity(LOADED, "Rückmeldung", "Ganz neu\n\nzweiter Absatz")
    assert e["SPSActivityClassBase"]["DescriptionHTML"] == "<p>Ganz neu</p><p>&nbsp;</p><p>zweiter Absatz</p>"
    # nur Betreff: Beschreibung unverändert (gleicher Text oder None)
    for same in (view["description"] + "  \n", None):
        assert mt.edited_entity(LOADED, "Anders", same)["SPSActivityClassBase"]["DescriptionHTML"] == \
            LOADED["SPSActivityClassBase"]["DescriptionHTML"]
    with pytest.raises(BookingError, match="Nichts"):
        mt.edited_entity(LOADED, "Rückmeldung", view["description"], CAT)
    with pytest.raises(BookingError, match="Betreff"):
        mt.edited_entity(LOADED, " ", "mehr")

    # Kategorie: neue Kategorie mit neuem SLA, gleiche Kategorie ändert nichts
    e = mt.edited_entity(LOADED, "Rückmeldung", None, "cat-neu", "sla-neu")
    assert (e["SPSActivityClassBase"]["Category"], e["SPSActivityClassBase"]["SLA"]) == ("cat-neu", "sla-neu")
    assert mt.category_sla_path(LOADED, CAT) is None and mt.category_sla_path(LOADED, None) is None
    path = mt.category_sla_path(LOADED, "cat-neu")
    assert "Category=cat-neu" in path and f"User={MELDER}" in path and "TicketType=6" in path

    assert mt.saved_ticket({"Entity": {"ID": "ticket-1", "Sys-Name": "TCK1"}}, "ticket-1")["ticket"] == "TCK1"
    with pytest.raises(BookingError):
        mt.saved_ticket({"Entity": {"ID": "anderes"}}, "ticket-1")


def test_leser_ticket_bearbeiten(tmp_path):
    answers = {"WidgetCommon/GetData": {"Entity": LOADED},
               "UpdateData": {"Entity": {"ID": "ticket-1", "Sys-Name": "TCK0000050866",
                                         "Sys-Entity": "SPSActivityTypeServiceRequest"}}}
    reader, calls, got = _reader(tmp_path, answers)
    reader._ticket_task("load", {"id": "ticket-1"})
    assert got[-1]["ok"] and got[-1]["data"]["description"].startswith("- Anpassungen")
    assert calls[-1][:2] == ("GET", f"/m42Services/api/WidgetCommon/GetData/{EDIT_DIALOG}/ticket-1")

    req = {"id": "ticket-1", "ticket": "TCK0000050866", "stamp": got[-1]["data"]["stamp"],
           "subject": "Rückmeldung", "description": got[-1]["data"]["description"] + "\nOrdner angelegt",
           "category": CAT}
    calls.clear()
    reader._ticket_task("edit", {"request": req})
    assert got[-1]["ok"], got[-1]
    assert got[-1]["data"]["subject"] == "Rückmeldung"
    assert [(m, p.split("/api/")[1]) for m, p, _b in calls] == [
        ("GET", f"WidgetCommon/GetData/{EDIT_DIALOG}/ticket-1"), ("POST", f"WidgetDialog/UpdateData/{EDIT_DIALOG}")]
    saved = json.loads(calls[1][2][1:-1])
    assert saved["SPSActivityClassBase"]["DescriptionHTML"].endswith("<p>Ordner angelegt</p>")

    # neue Kategorie: SLA wie im Dialog neu holen (Mitschnitt 13.11.2026)
    reader, calls, got = _reader(tmp_path, dict(answers, suitableSLAsForTicket={"TightestItem": "sla-neu"}))
    reader._ticket_task("edit", {"request": dict(req, category="cat-neu")})
    assert got[-1]["ok"], got[-1]
    assert [p.split("/api/")[1] for _m, p, _b in calls] == [
        f"WidgetCommon/GetData/{EDIT_DIALOG}/ticket-1", "activity/suitableSLAsForTicket/",
        f"WidgetDialog/UpdateData/{EDIT_DIALOG}"]
    base = json.loads(calls[2][2][1:-1])["SPSActivityClassBase"]
    assert (base["Category"], base["SLA"]) == ("cat-neu", "sla-neu")

    # inzwischen von jemand anderem gespeichert: nichts schicken
    reader, calls, got = _reader(tmp_path, answers)
    reader._ticket_task("edit", {"request": dict(req, stamp="alt/alt")})
    assert not got[-1]["ok"] and not got[-1].get("unclear") and "inzwischen" in got[-1]["error"]
    assert not any("UpdateData" in p for _m, p, _b in calls)

    # Speichern läuft in Zeitüberschreitung: unklar
    reader, calls, got = _reader(tmp_path, answers, fail="UpdateData")
    reader._ticket_task("edit", {"request": req})
    assert not got[-1]["ok"] and got[-1]["unclear"]


def test_kunde_des_melders():
    assert mt.initiator_common({"Phone": "1"}) == {}
    # echte UserDetails: Ids nehmen, nie die Anzeigenamen daneben
    assert mt.initiator_common(USER_DETAILS) == {"OU": OU_KOCH, "CostCenter": CC_GLOBAL, "Location": LOC_GLOBAL}
    assert mt.initiator_common({"OrgUnit": "Systems", "OrgUnitId": None}) == {}
    assert mt.initiator_common({"OrgUnit": {"ObjectId": OU_KOCH, "DisplayString": "Koch"}}) == {"OU": OU_KOCH}
    assert mt.field_overview({"Phone": "1", "OU": {"ID": "x"}}) == {"Phone": "str", "OU": {"ID": "str"}}
    e = mt.ticket_entity(TEMPLATE, mt.INCIDENT, "x", "", CAT, MELDER, ME, initiator_ou={"OU": OU_KOCH})
    assert (e["SPSCommonClassBase"]["OU"], e["SPSCommonClassBase"]["CostCenter"]) == (OU_KOCH, None)
    # ohne Kunde des Melders: null wie im Dialog (Mitschnitt 13.11.2026), nie die eigene OU der Vorlage
    common = mt.ticket_entity(TEMPLATE, mt.INCIDENT, "x", "", CAT, MELDER, ME)["SPSCommonClassBase"]
    assert (common["OU"], common["CostCenter"], common["Location"]) == (None, None, None)


def test_leser_ticket_anlegen_ohne_kunde(tmp_path):
    # UserDetails ohne OrgUnitId: OU null, Matrix42 setzt sie vom Melder; Personenobjekt nicht lesen (403)
    reader, calls, got = _reader(tmp_path, dict(ANSWERS, UserDetails={"Phone": "1", "OrgUnit": "Systems"}))
    reader._ticket_task("create", {"request": REQUEST})
    assert got[-1]["ok"] and got[-1]["data"]["warning"] == "", got[-1]
    saved = next(json.loads(b[1:-1]) for _m, p, b in calls if "UpdateData" in p)
    assert saved["SPSCommonClassBase"]["OU"] is None
    assert not any("data/objects" in p for _m, p, _b in calls)


def test_load_error_macht_object_is_deleted_lesbar():
    raw = mt.BookingError('Matrix42 antwortet mit Fehler 500: {"Key": "Matrix42.Pandora.BizLogic.'
                          'ContentWidget.ObjectIsDeleted", "Message": "The object you try to open is deleted"}')
    err = mt.load_error(raw, "SPSActivityTypeIncident")
    assert "Störung" in str(err) and "{" not in str(err)
    other = mt.BookingError("Matrix42 antwortet mit Fehler 500")
    assert mt.load_error(other) is other


def test_html_text_liest_outlook_html_mail():
    mail = ('<html><head><meta charset="utf-8"><style><!-- p.MsoNormal {margin:0cm} --></style>'
            '<!--[if gte mso 9]><xml><o:shapedefaults/></xml><![endif]--></head><body>'
            '<p class="MsoNormal">Hallo zusammen,<o:p></o:p></p><p><o:p>&nbsp;</o:p></p>'
            '<p>kann es sein?<br>Gr&uuml;&szlig;e</p><table><tr><td>Name</td><td>M&uuml;ller</td></tr></table>'
            '</body></html>')
    assert mt.html_text(mail) == "Hallo zusammen,\n\nkann es sein?\nGrüße\nName\tMüller"
