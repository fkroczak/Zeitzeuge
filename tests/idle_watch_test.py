"""Abwesenheit am PC (idle_watch.py) und Kulanz/Reise an Tätigkeit und Matrix42-Buchung."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import m42_booking as mb  # noqa: E402
from idle_watch import IdleWatch, idle_entry  # noqa: E402
from journal import Journal, ticket_line  # noqa: E402

T0 = datetime(2026, 11, 2, 10, 0, 0)


def run(watch, samples):
    """samples: [(Sekunden ab T0, Leerlauf in Sekunden)] -> erste gemeldete Abwesenheit."""
    found = []
    for secs, idle in samples:
        span = watch.update(T0 + timedelta(seconds=secs), idle)
        if span:
            found.append(span)
    return found


def test_lange_pause_wird_bei_erster_eingabe_gemeldet():
    watch = IdleWatch(15)
    samples = [(0, 0), (5, 5)] + [(s, s) for s in range(10, 20 * 60, 5)] + [(20 * 60, 1)]
    found = run(watch, samples)
    assert found == [{"start": "2026-11-02 10:00:00", "end": "2026-11-02 10:19:59"}]


def test_kurze_pause_und_aus():
    assert run(IdleWatch(15), [(0, 0), (10 * 60, 600), (10 * 60 + 5, 0)]) == []
    assert run(IdleWatch(0), [(0, 0), (30 * 60, 1800), (30 * 60 + 5, 0)]) == []


def test_ruhezustand_ohne_proben():
    """PC schlief 40 Minuten (keine Proben), danach Eingabe: Lücke aus der Uhrzeit."""
    found = run(IdleWatch(15), [(0, 0), (40 * 60, 2)])
    assert found and found[0]["start"] == "2026-11-02 10:00:00"
    assert found[0]["end"] == "2026-11-02 10:39:58"


def test_noch_abwesend_meldet_nichts():
    # Leerlauf läuft weiter, aber keine Eingabe: noch nicht fragen
    assert run(IdleWatch(15), [(0, 0), (20 * 60, 20 * 60), (25 * 60, 25 * 60)]) == []


def test_idle_entry():
    e = idle_entry({"start": "2026-11-02 10:00:00", "end": "2026-11-02 10:20:00"})
    assert e["idle"] and e["type"] == "Abwesend vom PC"


def test_kulanz_und_reise_im_journal(tmp_path):
    j = Journal(str(tmp_path))
    item = j.add({"start": "2026-11-02 10:00:00", "end": "2026-11-02 11:00:00", "customer": "Müller",
                  "text": "Server", "goodwill": True, "travel": False})
    assert item["goodwill"] is True and "travel" not in item
    assert "Kulanz" in ticket_line(item)
    changed = j.update(item, {"goodwill": False, "travel": True})
    assert "goodwill" not in changed and changed["travel"] is True
    assert "Reise" in ticket_line(changed)


def test_kulanz_und_reise_in_matrix42():
    template = {"ID": "x", "ITMTimeEntryClassBase": {}}
    start, end = datetime(2026, 11, 2, 10, 0), datetime(2026, 11, 2, 10, 30)
    plain = mb.time_entry(template, "t", "s", "u", start, end, 30, "x")["ITMTimeEntryClassBase"]
    assert plain["IsGoodwill"] is False and plain["IsTravel"] is False
    base = mb.time_entry(template, "t", "s", "u", start, end, 30, "x", goodwill=True, travel=True,
                         goodwill_reason="Nachbesserung")["ITMTimeEntryClassBase"]
    assert base["IsGoodwill"] and base["IsTravel"]
    assert base["GoodwillAmount"] == 30 and base["GoodwillReason"] == "Nachbesserung"
    p = mb.plan({"start": "2026-11-02 10:00:00", "end": "2026-11-02 10:30:00", "goodwill": True})
    assert p["goodwill"] and not p["travel"]


def test_zuschlag_ignorieren(tmp_path):
    j = Journal(str(tmp_path))
    item = j.add({"start": "2026-11-02 10:00:00", "end": "2026-11-02 11:00:00", "text": "x",
                  "no_surcharge": True})
    assert item["no_surcharge"] is True and "ohne Zuschlag" in ticket_line(item)
    assert "no_surcharge" not in j.update(item, {"no_surcharge": False})
    template = {"ID": "x", "ITMTimeEntryClassBase": {}}
    start, end = datetime(2026, 11, 2, 10, 0), datetime(2026, 11, 2, 10, 30)
    plain = mb.time_entry(template, "t", "s", "u", start, end, 30, "x")["ITMTimeEntryClassBase"]
    assert plain["IgnoreSurcharge"] is False and plain["IgnoreSurchargeReason"] is None
    base = mb.time_entry(template, "t", "s", "u", start, end, 30, "x",
                         no_surcharge=True)["ITMTimeEntryClassBase"]
    assert base["IgnoreSurcharge"] is True and base["IgnoreSurchargeReason"] == mb.SURCHARGE_REASON
    assert mb.plan({"start": "2026-11-02 10:00:00", "end": "2026-11-02 10:30:00",
                    "no_surcharge": True})["no_surcharge"]



def test_bekannte_anrufrichtung_bleibt(tmp_path):
    """Liest 3CX einen Anruf später ohne Richtung, bleibt die bekannte Richtung erhalten."""
    import call_import
    path = str(tmp_path / "anrufe.json")
    call = {"start": "2026-11-02 10:00:00", "number": "0251", "duration_s": 60, "direction": "Ausgehend"}
    call_import.merge_calls(path, [call])
    call_import.merge_calls(path, [{**call, "direction": "Anruf", "name": "Neu"}])
    stored = call_import.load_calls(path)
    assert stored[0]["direction"] == "Ausgehend" and stored[0]["name"] == "Neu"
    call_import.merge_calls(path, [{**call, "direction": "Eingehend"}])
    assert call_import.load_calls(path)[0]["direction"] == "Eingehend"
