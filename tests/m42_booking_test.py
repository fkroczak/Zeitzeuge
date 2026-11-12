"""In Matrix42 buchen: Logik ohne Browser (Felder wie im Buchungs-Mitschnitt vom 02.11.2026)."""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

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
              "Id": "e5ee25ff-87cd-f111-0dbd-0050569e2f05", "Sys-ObjectId": "daee25ff-87cd-f111-0dbd-0050569e2f05",
              "Subject": "Praktikanten",
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


def test_search_plan_and_matches():
    assert mb.search_plan("wiro drucker") == ("drucker", ("Subject", "Customer", "Initiator", "Recipient"))
    assert mb.search_plan("TCK0000050699") == ("TCK0000050699", ("TicketNumber",))
    assert mb.search_plan("50699")[1] == mb.SEARCH_FIELDS
    row = {"ticket": "TCK0000050428", "subject": "Drucker Austausch", "customer": "wiro GmbH"}
    assert mb.matches(row, "WIRO drucker") and not mb.matches(row, "wiro login")


def test_merge_tickets_open_first_and_filtered():
    items = [{"TicketNumber": "TCK0000000003", "Id": "3", "Subject": "Login", "Customer": "WiRoPa",
              "State": "Gelöst", "CreatedDate": "2026-11-10T08:00:00Z"},
             {"TicketNumber": "TCK0000000002", "Id": "2", "Subject": "Login", "Customer": "WiRoPa",
              "State": "In Bearbeitung", "CreatedDate": "2026-11-01T08:00:00Z"},
             {"TicketNumber": "TCK0000000001", "Id": "1", "Subject": "Drucker", "Customer": "WiRoPa",
              "State": "Neu", "CreatedDate": "2026-11-11T08:00:00Z"}]
    rows = mb.merge_tickets(items, text="wiro login")
    assert [r["ticket"] for r in rows] == ["TCK0000000002", "TCK0000000003"]
    assert mb.ticket_list_label(rows[0]).endswith("· 01.11.26")
    assert [r["ticket"] for r in mb.merge_tickets_rows(rows, "bearbeitung")] == ["TCK0000000002"]


def test_meine_tickets_filter():
    assert mb.own_name("Kroczak, Filip - Systems (3)") == "Kroczak, Filip"
    assert mb.my_tickets_word("Kroczak, Filip") == "kroczak"
    assert mb.my_tickets_word("") == ""
    items = [
        {"TicketNumber": "TCK0000000001", "Id": "1", "State": "In Bearbeitung",
         "Recipient": "Kroczak, Filip - Systems", "CreatedDate": "2026-10-01T08:00:00Z"},
        {"TicketNumber": "TCK0000000002", "Id": "2", "State": "Neu",
         "Recipient": "Filip Kroczak", "CreatedDate": "2026-10-05T08:00:00Z"},
        {"TicketNumber": "TCK0000000003", "Id": "3", "State": "Geschlossen",
         "Recipient": "Kroczak, Filip - Systems", "CreatedDate": "2026-10-06T08:00:00Z"},
        {"TicketNumber": "TCK0000000004", "Id": "4", "State": "Neu",  # anderer Kroczak
         "Recipient": "Kroczak, Anna", "CreatedDate": "2026-10-07T08:00:00Z"},
        {"TicketNumber": "TCK0000000001", "Id": "1", "State": "In Bearbeitung",  # doppelt
         "Recipient": "Kroczak, Filip - Systems", "CreatedDate": "2026-10-01T08:00:00Z"},
    ]
    rows = mb.my_open_tickets(items, "Kroczak, Filip")
    assert [r["ticket"] for r in rows] == ["TCK0000000002", "TCK0000000001"]
    assert mb.my_open_tickets(items, "") == []


def test_meine_tickets_lesen(tmp_path):
    from m42_reader import M42Reader
    reader = M42Reader("https://m42.example/wm/", str(tmp_path / "m42.json"), str(tmp_path / "p"))
    calls, got = [], []
    page = [{"TicketNumber": f"TCK{n:010d}", "Id": str(n), "State": "Neu", "Recipient": "Kroczak, Filip",
             "CreatedDate": f"2026-10-{n % 28 + 1:02d}T08:00:00Z"} for n in range(mb.MY_TICKETS_PAGE_SIZE)]

    def fetch(method, path, body=None, content_type=None):
        if path.endswith("/userinfo"):  # eigener Benutzer: hier unbekannt
            return None
        calls.append((path, body))
        return page if "page=0" in path else page[:3]
    reader._fetch = fetch
    reader.my_tickets_loaded.connect(got.append)

    reader._read_my_tickets()  # Name unbekannt: nichts abfragen, Hinweis
    assert not calls and got[-1]["rows"] is None and "Name" in got[-1]["error"]

    reader.user_name = "Kroczak, Filip"
    reader._read_my_tickets()
    assert len(calls) == 2 and "page=1" in calls[1][0]  # volle erste Seite: zweite nachlesen
    assert calls[0][1]["Groups"][0]["Conditions"][0] == {"Property": "Recipient", "Operator": 7,
                                                        "Value": ["kroczak"]}
    assert len(got[-1]["rows"]) == mb.MY_TICKETS_PAGE_SIZE and not got[-1]["error"]

    def broken(*_a, **_k):
        raise mb.BookingError("Matrix42 antwortet mit Fehler 500")
    reader._fetch = broken
    reader._read_my_tickets()  # Fehler: alte Liste bleibt, Fehler steht dabei
    assert len(got[-1]["rows"]) == mb.MY_TICKETS_PAGE_SIZE and "500" in got[-1]["error"]


def test_kulanz_mit_zeit_und_grund():
    item = {"start": "2026-11-02 10:00:00", "end": "2026-11-02 11:00:00", "goodwill": True,
            "goodwill_minutes": 20, "goodwill_reason": "Nacharbeit"}
    p = mb.plan(item, Billing())
    assert p["goodwill_minutes"] == 20 and p["goodwill_reason"] == "Nacharbeit"
    start, end = datetime(2026, 11, 2, 10, 0), datetime(2026, 11, 2, 11, 0)
    base = mb.time_entry(TEMPLATE, "t", "s", "u", start, end, 60, "x", goodwill=True,
                         goodwill_reason="Nacharbeit", goodwill_minutes=20)["ITMTimeEntryClassBase"]
    assert base["IsGoodwill"] and base["GoodwillAmount"] == 20 and base["GoodwillReason"] == "Nacharbeit"
    # ohne Angabe oder mehr als die Zeit: die ganze Zeit
    base = mb.time_entry(TEMPLATE, "t", "s", "u", start, end, 60, "x", goodwill=True)["ITMTimeEntryClassBase"]
    assert base["GoodwillAmount"] == 60
    base = mb.time_entry(TEMPLATE, "t", "s", "u", start, end, 60, "x", goodwill=True,
                         goodwill_minutes=90)["ITMTimeEntryClassBase"]
    assert base["GoodwillAmount"] == 60
    assert mb.plan({"start": item["start"], "end": item["end"], "goodwill_minutes": 20}, Billing())[
        "goodwill_minutes"] == 0, "ohne Kulanz keine Kulanzzeit"


def test_reise_mit_kilometern():
    item = {"start": "2026-11-02 10:00:00", "end": "2026-11-02 11:00:00", "travel": True,
            "travel_km_there": 42, "travel_km_back": 40}
    p = mb.plan(item, Billing())
    assert (p["travel_km_there"], p["travel_km_back"]) == (42, 40)
    start, end = datetime(2026, 11, 2, 10, 0), datetime(2026, 11, 2, 11, 0)
    base = mb.time_entry(TEMPLATE, "t", "s", "u", start, end, 60, "x", travel=True,
                         km_there=42, km_back=40)["ITMTimeEntryClassBase"]
    assert base["IsTravel"] and base["Approach"] == 42 and base["Departure"] == 40
    base = mb.time_entry(TEMPLATE, "t", "s", "u", start, end, 60, "x", travel=True)["ITMTimeEntryClassBase"]
    assert base["Approach"] is None and base["Departure"] is None, "ohne Kilometer wie bisher"
