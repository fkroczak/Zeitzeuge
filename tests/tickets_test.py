"""Ticketnummern vorschlagen, Ticket-Format "- " / "-- " und Ticket in der Ablage (ohne Oberfläche)."""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tickets  # noqa: E402
from journal import Journal, ticket_line  # noqa: E402
from tickets import format_ticket_text, suggest  # noqa: E402

D = "2026-10-20"
START, END = datetime(2026, 10, 20, 10, 0), datetime(2026, 10, 20, 10, 30)


def seg(a, b, title, app="Outlook"):
    return {"start": f"{D} {a}:00", "end": f"{D} {b}:00", "title": title, "app": app}


def test_find_tickets():
    compiled, errors = tickets.compile_patterns(tickets.DEFAULT_PATTERNS)
    assert not errors
    assert tickets.find_tickets("Systems - TCK0000049374 - Praktikanten", compiled) == ["TCK0000049374"]
    assert tickets.find_tickets("tck0000049374 und TCK0000049374", compiled) == ["TCK0000049374"]
    assert tickets.find_tickets("XTCK123 ist keins", compiled) == []
    compiled, _ = tickets.compile_patterns([r"Ticket #(\d+)"])
    assert tickets.find_tickets("Re: Ticket #1234 Drucker", compiled) == ["1234"]
    _, errors = tickets.compile_patterns(["TCK\\d+", "", "(kaputt"])
    assert [no for no, _msg in errors] == [3]


def test_vorschlaege_nach_dauer():
    segments = [
        seg("09:50", "10:12", "TCK0000000001 - Drucker - Outlook"),  # ab 09:55 (Rand) 17 min
        seg("10:12", "10:15", "Matrix42 - TCK0000000002", "Edge"),    # 3 min
        seg("10:15", "10:20", "TCK0000000002 - Mail", "Outlook"),     # 5 min
        seg("12:00", "12:30", "TCK0000000003 - weit weg"),            # außerhalb
        seg("10:20", "10:25", "Ohne Ticket"),
    ]
    found = suggest(START, END, segments, margin_minutes=5)
    assert [f["ticket"] for f in found] == ["TCK0000000001", "TCK0000000002"]
    assert found[0]["seconds"] == 17 * 60
    assert found[0]["label"] == "TCK0000000001 (Outlook, 17 min)"
    assert found[1]["sources"] == ["Outlook", "Edge"]


def test_vorschlaege_aus_matrix42():
    bookings = [{"start": f"{D} 10:00:00", "end": f"{D} 10:30:00", "ticket": "TCK0000049374",
                 "customer": "Systems"},
                {"start": f"{D} 14:00:00", "end": f"{D} 15:00:00", "ticket": "TCK0000000009"}]
    found = suggest(START, END, [], bookings)
    assert [(f["ticket"], f["sources"]) for f in found] == [("TCK0000049374", ["Matrix42"])]


def test_vorschlaege_aus():
    segments = [seg("10:00", "10:30", "TCK0000000001")]
    assert suggest(START, END, segments, patterns=[]) == []
    assert suggest(START, END, [{"start": "kaputt"}, {}], patterns=None) == []


def test_format_ticket_text():
    assert format_ticket_text("Drucker\nTreiber", "") == "Drucker\nTreiber"  # aus: unverändert
    assert format_ticket_text("PVS-Stand mit Lexware Update\nBackup geprüft\nLexware aktualisiert",
                              "dash") == ("- PVS-Stand mit Lexware Update\n-- Backup geprüft\n"
                                          "-- Lexware aktualisiert")
    # Ein Satz je Teil, Abkürzungen trennen nicht
    assert format_ticket_text("Drucker eingerichtet. Treiber z. B. von HP aktualisiert.",
                              "dash") == "- Drucker eingerichtet.\n-- Treiber z. B. von HP aktualisiert."
    # Vorhandene Marken bleiben, doppelt wird nichts
    text = "- Haupt\n-- Unter\n- Zweite Haupt\n  eingerückt"
    once = format_ticket_text(text, "dash")
    assert once == "- Haupt\n-- Unter\n- Zweite Haupt\n-- eingerückt"
    assert format_ticket_text(once, "dash") == once
    assert format_ticket_text("", "dash") == ""
    assert format_ticket_text("• Punkt\n* Stern", "dash") == "- Punkt\n-- Stern"


def test_ticket_line_und_ablage(tmp_path):
    j = Journal(str(tmp_path))
    item = j.add({"start": f"{D} 10:00:00", "end": f"{D} 10:30:00", "customer": "Müller",
                  "category": "Fernwartung", "text": "Drucker\nTreiber", "ticket": " TCK0000000001 "})
    assert item["ticket"] == "TCK0000000001"
    # Ohne Ticket: kein leeres Feld gespeichert, Zeile wie bisher
    plain = j.add({"start": f"{D} 11:00:00", "end": f"{D} 11:30:00", "customer": "Müller",
                   "text": "Updates", "ticket": ""})
    assert "ticket" not in plain
    assert ticket_line(plain) == "11:00–11:30 (30 min)  Müller: Updates"
    assert ticket_line(item) == ("10:00–10:30 (30 min)  Müller · Fernwartung · TCK0000000001: "
                                 "Drucker\nTreiber")
    assert ticket_line(item, "dash") == ("10:00–10:30 (30 min)  Müller · Fernwartung · TCK0000000001:\n"
                                         "- Drucker\n-- Treiber")
    assert ticket_line({"start": f"{D} 11:00:00", "end": f"{D} 11:30:00", "text": "A"},
                       "dash") == "11:00–11:30 (30 min)\n- A"
    # Neu laden, Doku-Ansicht zeigt das Ticket, Ticket wieder entfernen
    j2 = Journal(str(tmp_path))
    stored = [i for i in j2.items(D) if i["id"] == item["id"]][0]
    assert stored["ticket"] == "TCK0000000001"
    entry = [e for e in j2.entries(D) if e["doc_item"]["id"] == item["id"]][0]
    assert "TCK0000000001" in entry["details"]
    changed = j2.update(stored, {"ticket": ""})
    assert "ticket" not in changed
