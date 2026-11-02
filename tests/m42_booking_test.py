"""In Matrix42 buchen: Logik ohne Browser (Felder wie im Buchungs-Mitschnitt vom 02.11.2026)."""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import m42_booking as mb  # noqa: E402
from billing import Billing  # noqa: E402

TEMPLATE = {"Sys-Entity": "ITMTimeEntryType", "ID": "a13b6f29-2d6f-cdc4-5b00-08df38f4dabd",
            "Sys-IsNew": True, "ITMTimeEntryClassSurcharge": [],
            "SPSCommonClassBase": {"CostCenter": "cc", "OU": "ou", "Location": "loc"},
            "ITMTimeEntryClassBase": {"ActivityType": None, "Target": None, "Pause": 0, "Approach": 0},
            "ITMILVClassBase": {"State": None}}
# Felder der gespeicherten Zeiterfassung im Mitschnitt (UpdateData)
RECORDED_BASE = {"ActivityType", "Target", "IgnoreSurcharge", "Start", "User", "IsGoodwill",
                 "GoodwillAmountRounded", "WorktimeRounded", "Description", "Pause",
                 "IgnoreSurchargeReason", "Approach", "SLA", "GoodwillReason", "Departure", "End",
                 "Location", "IsTravel", "UserTimeZone", "GoodwillAmount", "WorktimeNominal"}


def test_plan_im_takt_mit_ticket_und_text():
    item = {"start": "2026-11-02 15:50:12", "end": "2026-11-02 16:07:40", "customer": "Systems",
            "ticket": "tck0000049374", "text": "Praktikantenbetreuung. Utilman-Methode gezeigt."}
    p = mb.plan(item, Billing())
    assert p["ticket"] == "TCK0000049374"
    assert (p["start"], p["end"]) == (datetime(2026, 11, 2, 15, 50), datetime(2026, 11, 2, 16, 20))
    assert p["minutes"] == 30 and p["customer"] == "Systems"
    assert mb.plan(item, Billing(mode="off"))["end"] == datetime(2026, 11, 2, 16, 7)
    assert mb.plan(item, None, "dash")["text"].startswith("- Praktikantenbetreuung")
    assert mb.plan({**item, "ticket": "", "text": "x"})["ticket"] == ""


def test_ticket_aus_der_suche():
    items = [{"TicketNumber": "TCK0000049375", "Id": "falsch"},
             {"Sys-Entity": "SPSActivityTypeServiceRequest", "TicketNumber": "TCK0000049374",
              "Id": "daee25ff-87cd-f111-0dbd-0050569e2f05", "Subject": "Praktikanten",
              "Customer": "Systems  (999830)", "State": "In Bearbeitung"}]
    t = mb.ticket_from_search(items, "TCK0000049374")
    assert t["id"] == "daee25ff-87cd-f111-0dbd-0050569e2f05" and t["customer"] == "Systems"
    with pytest.raises(mb.BookingError, match="nicht gefunden"):
        mb.ticket_from_search(items, "TCK0000000001")
    q = mb.ticket_query("TCK0000049374")
    assert q["Groups"][0]["Conditions"][0] == {"Property": "TicketNumber", "Operator": 7,
                                               "Value": ["TCK0000049374"]}


def test_abfragen_wie_im_mitschnitt():
    assert mb.new_data_body("abc") == "'\"objectType=ITMTimeEntryType&selectedObjects=abc\"'"
    assert mb.target_body("abc") == [{"Name": "@id", "Value": "abc", "Type": 1}]
    resp = {"Entity": {"ITMTimeEntryClassTarget": [{"ID": "e7ee", "TargetSLA": "df3d", "TargetOU": "fa01"}]}}
    assert mb.target_from_response(resp) == ("e7ee", "df3d")
    with pytest.raises(mb.BookingError):
        mb.target_from_response({"Entity": {}})


def test_zeiterfassung_wie_im_mitschnitt():
    start, end = datetime(2026, 11, 2, 15, 50), datetime(2026, 11, 2, 16, 20)
    e = mb.time_entry(TEMPLATE, "e7ee", "df3d", "edc4", start, end, 30, "- Text", 10)
    base = e["ITMTimeEntryClassBase"]
    assert set(base) == RECORDED_BASE
    assert base["Start"] == start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    assert base["End"].endswith(".000Z") and base["WorktimeRounded"] == base["WorktimeNominal"] == 30
    assert (base["Target"], base["SLA"], base["User"], base["ActivityType"]) == ("e7ee", "df3d", "edc4", 10)
    assert e["ID"] == e["_id"] == TEMPLATE["ID"] and e["Sys-IsNew"] and e["IsNew"]
    assert e["ITMILVClassBase"] == {"State": 10}  # Status „Neu“
    common = e["SPSCommonClassBase"]
    assert common["CostCenter"] == "cc" and common["Bookings"] == {"AddedRelations": [], "RemovedRelations": []}
    body = mb.wrap(e)
    assert body.startswith("'{") and body.endswith("}'") and json.loads(body[1:-1]) == e
    with pytest.raises(mb.BookingError, match="Benutzer"):
        mb.time_entry(TEMPLATE, "e7ee", "df3d", "", start, end, 30, "x")
    with pytest.raises(mb.BookingError):
        mb.time_entry(TEMPLATE, "e7ee", "df3d", "edc4", end, start, 30, "x")


def test_antworten():
    assert mb.saved_entry({"Entity": {"Sys-Name": "TE0000088403"}}) == "TE0000088403"
    with pytest.raises(mb.BookingError):
        mb.saved_entry({"Entity": {"Sys-Name": ""}})
    types = mb.activity_types({"Values": [{"Value": 10, "DisplayString": "Administration"},
                                          {"Value": 30, "DisplayString": "Consulting"}, "kaputt"]})
    assert types == [(10, "Administration"), (30, "Consulting")]
    assert mb.activity_types(None) == mb.ACTIVITY_TYPES


def test_ueberschneidungen_und_kennungen():
    bookings = [{"start": "2026-11-02 15:00:00", "end": "2026-11-02 16:00:00", "ticket": "TCK2"},
                {"start": "2026-11-02 15:45:00", "end": "2026-11-02 16:15:00", "ticket": "TCK1"},
                {"start": "2026-11-02 17:00:00", "end": "2026-11-02 18:00:00", "ticket": "TCK1"}]
    found = mb.overlaps(bookings, datetime(2026, 11, 2, 15, 50), datetime(2026, 11, 2, 16, 20), "TCK1")
    assert [b["ticket"] for b in found] == ["TCK1", "TCK2"]
    assert mb.ids({"m42_booking_ids": {"dialog": "neu"}})["dialog"] == "neu"
    assert mb.ids({})["ticket_list"] == mb.DEFAULT_IDS["ticket_list"]


def test_ticketsuche_zusammenfuehren():
    q = mb.search_query("Customer", "systems")
    assert q["Groups"][0]["Conditions"][0] == {"Property": "Customer", "Operator": 7, "Value": ["systems"]}
    a = [{"TicketNumber": "TCK0000000001", "Id": "1", "Subject": "Alt", "Customer": "Müller  (1)",
          "CreatedDate": "2026-10-01T08:00:00Z"},
         {"TicketNumber": "kein Ticket", "Id": "x"}, "kaputt"]
    b = [{"TicketNumber": "TCK0000000002", "Id": "2", "Subject": "Neu", "Customer": "Müller  (1)",
          "Recipient": "Kroczak, Filip", "CreatedDate": "2026-10-05T08:00:00Z"},
         {"TicketNumber": "TCK0000000001", "Id": "1", "CreatedDate": "2026-10-01T08:00:00Z"}]
    rows = mb.merge_tickets(a, b, None)
    assert [r["ticket"] for r in rows] == ["TCK0000000002", "TCK0000000001"]  # neueste zuerst, je einmal
    assert rows[1]["customer"] == "Müller" and rows[0]["recipient"] == "Kroczak, Filip"
    assert mb.ticket_label(rows[1]) == "TCK0000000001 · Alt · Müller"
