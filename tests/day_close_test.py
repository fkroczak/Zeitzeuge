"""Tagesabschluss (day_close.py): Vorschläge aus Spuren, Lücken, Tickets, Kennzahlen."""
from datetime import datetime, timedelta

import day_close as dc

D = "2026-11-02"
DAY = datetime(2026, 11, 2)


def t(hm):
    return f"{D} {hm}:00"


def work(*spans):
    return [(DAY + timedelta(hours=int(a[:2]), minutes=int(a[3:])),
             DAY + timedelta(hours=int(b[:2]), minutes=int(b[3:]))) for a, b in spans]


def conn(a, b, name, kind="RDP-Sitzung", **kw):
    return dict({"start": t(a), "end": t(b), "type": kind, "customer_name": name}, **kw)


def hint(e):
    name = e.get("customer_name", "")
    return (name.split(" - ")[0] if not e.get("pc_block") else name), e.get("category", "Fernwartung")


def test_full_day_reaches_high_coverage_with_blocks_per_customer():
    evidence = [
        (1, conn("08:00", "09:10", "Kanzlei Schmidt - DC01")),
        (1, conn("09:15", "09:40", "Kanzlei Schmidt - SRV02")),  # 5 min Lücke: gleicher Block
        (1, conn("10:00", "10:45", "Müller GmbH", kind="TeamViewer")),
        (4, {"start": t("10:45"), "end": t("12:00"), "type": "PC: E-Mail", "pc_block": True,
             "customer_name": "", "category": "E-Mail / Kommunikation", "label": "E-Mail"}),
    ]
    plan = dc.build(D, work(("08:00", "12:00")), evidence=evidence, hint=hint)
    rows = [(r["kind"], r["start"][11:16], r["end"][11:16], r["customer"]) for r in plan["rows"]]
    assert rows == [("draft", "08:00", "09:40", "Kanzlei Schmidt"),  # 5 min Lücke überbrückt
                    ("gap", "09:40", "10:00", ""),                    # 20 min: zu lang zum Füllen
                    ("draft", "10:00", "10:45", "Müller GmbH"),
                    ("draft", "10:45", "12:00", "")]                  # PC ohne Kunde
    drafts = [r for r in plan["rows"] if r["kind"] == dc.KIND_DRAFT]
    assert drafts[1]["text"] == "Fernwartung: TeamViewer"  # Kunde steht nicht doppelt im Text
    assert drafts[0]["customer"] == "Kanzlei Schmidt"
    assert drafts[0]["start"].endswith("08:00:00")
    assert drafts[-1]["customer"] == "" and not drafts[-1]["checked"]
    # angehakt sind nur die Blöcke mit Kunde
    assert plan["percent_now"] == 0
    assert plan["percent_after"] == 60  # 08:00–09:40 + 10:00–10:45 von 4 h


def test_gap_between_blocks_is_absorbed_and_big_gap_is_shown():
    evidence = [(1, conn("08:00", "09:00", "A - x")), (1, conn("09:08", "10:00", "B - y")),
                (1, conn("11:00", "11:30", "A - z"))]
    plan = dc.build(D, work(("08:00", "12:00")), evidence=evidence, hint=hint)
    rows = [(r["kind"], r["start"][11:16], r["end"][11:16], r["customer"]) for r in plan["rows"]]
    assert ("draft", "08:00", "09:08", "A") in rows          # 8 min Lücke -> Block davor
    assert ("draft", "09:08", "10:00", "B") in rows
    assert ("gap", "10:00", "11:00", "") in rows              # 60 min ohne Spur
    assert ("draft", "11:00", "11:30", "A") in rows
    assert ("gap", "11:30", "12:00", "") in rows              # 30 min frei: nicht angeknabbert


def test_booked_and_documented_time_is_not_proposed_again():
    bookings = [{"start": t("08:00"), "end": t("09:00"), "ticket": "TCK0000000001"}]
    docs = [{"id": "a", "start": t("09:00"), "end": t("09:30"), "customer": "A", "text": "x"},
            {"id": "b", "start": t("09:30"), "end": t("10:00"), "customer": "B", "text": "y",
             "m42_entry": "TE1"}]
    evidence = [(1, conn("08:00", "11:00", "C - srv"))]
    plan = dc.build(D, work(("08:00", "11:00")), docs=docs, evidence=evidence, bookings=bookings,
                    hint=hint)
    kinds = [(r["kind"], r["start"][11:16], r["end"][11:16]) for r in plan["rows"]]
    assert kinds == [("doc", "09:00", "09:30"), ("draft", "10:00", "11:00")]
    assert plan["booked"] == 90  # 08:00–09:00 Matrix42 + 09:30–10:00 schon gebuchte Tätigkeit
    assert plan["percent_now"] == 50
    assert plan["percent_after"] == 100


def test_doc_already_booked_by_hand_is_unchecked():
    bookings = [{"start": t("09:00"), "end": t("09:30")}]
    docs = [{"id": "a", "start": t("09:00"), "end": t("09:30"), "customer": "A", "text": "x"}]
    plan = dc.build(D, work(("09:00", "10:00")), docs=docs, bookings=bookings)
    row = plan["rows"][0]
    assert row["kind"] == "doc" and not row["checked"] and "schon gebucht" in row["note"]


def test_pc_blocks_only_count_in_work_time_connections_always():
    evidence = [(4, {"start": t("18:00"), "end": t("19:00"), "pc_block": True, "category": "Excel",
                     "customer_name": "", "type": "PC: Excel"}),
                (1, conn("19:00", "19:30", "A - fw"))]
    plan = dc.build(D, work(("08:00", "17:00")), evidence=evidence, hint=hint)
    drafts = [r for r in plan["rows"] if r["kind"] == "draft"]
    assert [(r["start"][11:16], r["customer"]) for r in drafts] == [("19:00", "A")]


def test_ticket_from_windows_then_from_history():
    evidence = [(1, conn("08:00", "09:00", "A - x")), (1, conn("10:00", "11:00", "B - y"))]
    recent = [{"start": "2026-10-30 10:00:00", "end": "2026-10-30 11:00:00", "customer": "B",
               "ticket": "TCK0000000022"}]

    def ticket_for(start, end):
        return ("TCK0000000011", "Outlook") if start.hour == 8 else ("", "")

    plan = dc.build(D, work(("08:00", "11:00")), evidence=evidence, hint=hint,
                    ticket_for=ticket_for, recent=recent)
    drafts = {r["customer"]: r for r in plan["rows"] if r["kind"] == "draft"}
    assert drafts["A"]["ticket"] == "TCK0000000011" and drafts["A"]["confidence"] == "hoch"
    assert drafts["B"]["ticket"] == "TCK0000000022"
    assert drafts["B"]["ticket_source"] == "zuletzt für den Kunden"
    assert drafts["B"]["confidence"] == "mittel"


def test_history_ignores_old_and_future_items():
    recent = [{"start": "2026-10-01 10:00:00", "customer": "B", "ticket": "TCK1"},
              {"start": "2026-11-05 10:00:00", "customer": "B", "ticket": "TCK2"}]
    assert dc.last_tickets(recent, before=DAY) == {}


def test_text_prefers_ai_then_rule_then_composed():
    ai = {"start": t("08:00"), "end": t("09:00"), "ai": True, "description": "Drucker eingerichtet"}
    rule = {"start": t("08:00"), "end": t("09:00"), "rule": True, "description": "Fernwartung bei A"}
    rdp = conn("08:00", "09:00", "A - DC01")
    call = {"start": t("08:00"), "end": t("08:10"), "type": "3CX-Anruf", "direction": "Eingehend",
            "customer_name": "A"}
    assert dc.compose_text("Fernwartung", [(rdp, 50), (ai, 10)]) == "Drucker eingerichtet"
    assert dc.compose_text("Fernwartung", [(rdp, 50), (rule, 10)]) == "Fernwartung bei A"
    assert dc.compose_text("Fernwartung", [(rdp, 50), (call, 10)]) == "Fernwartung: RDP DC01, Telefonat"


def test_small_splinters_join_neighbour():
    evidence = [(1, conn("08:00", "09:00", "A - x")), (1, conn("09:00", "09:03", "B - y")),
                (1, conn("09:03", "10:00", "A - z"))]
    plan = dc.build(D, work(("08:00", "10:00")), evidence=evidence, hint=hint)
    drafts = [r for r in plan["rows"] if r["kind"] == "draft"]
    assert len(drafts) == 1 and drafts[0]["customer"] == "A"
    assert (drafts[0]["start"][11:16], drafts[0]["end"][11:16]) == ("08:00", "10:00")


def test_internal_customer_fills_customerless_blocks():
    evidence = [(4, {"start": t("08:00"), "end": t("09:00"), "pc_block": True,
                     "category": "E-Mail / Kommunikation", "customer_name": "", "type": "PC: E-Mail"})]
    internal = {"customer": "ITM intern", "ticket": "TCK0000000999", "category": "Intern"}
    plan = dc.build(D, work(("08:00", "10:00")), evidence=evidence, internal=internal)
    draft, gap = plan["rows"]
    assert draft["customer"] == "ITM intern" and draft["ticket"] == "TCK0000000999" and draft["checked"]
    assert gap["kind"] == "gap" and gap["customer"] == "ITM intern" and not gap["checked"]


def test_sequence_plans_removes_overlaps_from_rounding():
    a = {"start": DAY.replace(hour=10), "end": DAY.replace(hour=10, minute=15), "minutes": 15}
    b = {"start": DAY.replace(hour=10, minute=7), "end": DAY.replace(hour=10, minute=37), "minutes": 30}
    dc.sequence_plans([b, a])
    assert b["start"] == DAY.replace(hour=10, minute=15) and b["end"] == DAY.replace(hour=10, minute=45)
    assert b.get("shifted") and not a.get("shifted")


def test_to_item_and_summary_follow_checks():
    plan = dc.build(D, work(("08:00", "09:00")), evidence=[(1, conn("08:00", "09:00", "A - x"))],
                    hint=hint)
    row = plan["rows"][0]
    assert dc.to_item(row)["customer"] == "A" and "ticket" not in dc.to_item(row)
    row["checked"] = False
    again = dc.summarize(D, work(("08:00", "09:00")), plan["rows"])
    assert again["percent_after"] == 0


def test_empty_day():
    plan = dc.build(D, [], evidence=[])
    assert plan["rows"] == [] and plan["percent_after"] is None
