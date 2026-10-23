"""Klassifizierung ohne KI (rules.py): Regeln, Verschmelzen, Vorrang, Regex-Gruppen, Tempo."""
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import rules  # noqa: E402

D = "2026-10-22 "

def e(start, end, kind, name, **extra):
    return {"start": D + start, "end": D + end, "type": kind, "customer_name": name,
            "details": extra.pop("details", ""), "is_suggestion": True, **extra}


def pc(start, end, app, title):
    return {"start": D + start, "end": D + end, "type": f"PC: {app}", "customer_name": title,
            "details": app, "app": app, "is_suggestion": True}


def no_overlap(blocks):
    for a, b in zip(blocks, blocks[1:]):
        if a["end"] > b["start"]:
            return False
    return all(b["start"] < b["end"] for b in blocks)


R = rules.default_rules()


def test_muster_und_ungueltige_regeln(check):
    """1. Muster: Text, Regex, ungültige Regex."""
    check(rules.pattern_error("chrome") is None, "Textmuster gilt als Fehler")
    check(rules.pattern_error("re:^(a|b)$") is None, "gültige Regex gilt als Fehler")
    check(rules.pattern_error("re:(") is not None, "ungültige Regex nicht erkannt")
    check(rules.pattern_error("re:") is not None, "leere Regex nicht erkannt")
    check(rules.pattern_error("") is not None, "leeres Muster nicht erkannt")
    check(rules.compile_pattern("CHROME").search("chrome.exe"), "Groß/Klein wird beachtet")
    check(rules.compile_pattern("a.b").search("axb") is None, "Textmuster wird als Regex gelesen")
    check(rules.rule_errors(R) == [], f"Standardregeln fehlerhaft: {rules.rule_errors(R)}")
    bad = R + [{"name": "kaputt", "field": "title", "match": "re:[", "category": "X", "enabled": True}]
    check([i for i, _ in rules.rule_errors(bad)] == [len(R)], "Fehler in Regel nicht gemeldet")
    # ungültige Regel stürzt nicht ab, die anderen gelten weiter
    out = rules.classify([e("09:00:00", "09:30:00", "TeamViewer", "Müller GmbH")], [], bad)
    check(len(out) == 1 and out[0]["category"] == "Fernwartung", f"ungültige Regel stört: {out}")


def test_standardregeln_ordnen_ein(check):
    """2. Standardregeln ordnen ein."""
    entries = [
        e("09:00:00", "09:20:00", "TeamViewer", "Müller GmbH"),
        e("09:22:00", "09:40:00", "TeamViewer", "Müller GmbH"),   # Lücke 2 min -> ein Block
        e("09:45:00", "09:50:00", "TeamViewer", "Müller GmbH"),   # Lücke 5 min -> noch derselbe
        e("11:00:00", "11:05:00", "Telefonat", "Max Muster (0123)"),
        e("12:00:00", "12:30:00", "VPN-Verbindung", "Kunde - SSL VPN"),
        e("12:05:00", "12:05:10", "OTP-Anzeige", "Kunde - SSL VPN"),
        e("14:00:00", "14:00:10", "Passwortaktion", "server - root"),  # zu kurz
    ]
    pcs = [
        pc("09:10:00", "09:15:00", "outlook.exe", "Posteingang"),       # während TeamViewer
        pc("10:00:00", "10:30:00", "OUTLOOK.EXE", "Posteingang - Outlook"),
        pc("13:00:00", "13:20:00", "mstsc.exe", "srv-dc01 - Remotedesktopverbindung"),
        pc("13:20:00", "13:30:00", "chrome.exe", "Microsoft 365 admin center - Google Chrome"),
        pc("13:30:00", "13:31:00", "notepad.exe", "Unbenannt"),          # keine Regel
        pc("15:00:00", "15:10:00", "ms-teams.exe", "Chat | Microsoft Teams"),
    ]
    out = rules.classify(entries, pcs, R)
    summary = [(b["start"][11:16], b["end"][11:16], b["category"], b["customer_name"]) for b in out]
    print("Blöcke:", *summary, sep="\n  ")
    expected = [
        ("09:00", "09:50", "Fernwartung", "Müller GmbH"),
        ("10:00", "10:30", "E-Mail / Kommunikation", ""),
        ("11:00", "11:05", "Telefonsupport", "Max Muster (0123)"),
        ("12:00", "12:30", "Fernwartung", "Kunde - SSL VPN"),
        ("13:00", "13:20", "Fernwartung", "srv-dc01"),
        ("13:20", "13:30", "Cloud-/M365-Administration", ""),
        ("15:00", "15:10", "Beratung / Abstimmung", ""),
    ]
    check(summary == expected, f"Standardregeln falsch eingeordnet:\n{summary}\nerwartet\n{expected}")
    check(no_overlap(out), "Blöcke überschneiden sich")
    first = out[0]
    check(first["type"] == "Klassifizierung" and first["is_suggestion"] and first["rule"],
          f"Format falsch: {first}")
    check(len(first["sources"]) == 3 and all(s["type"] == "TeamViewer" for s in first["sources"]),
          f"Quellen des TeamViewer-Blocks falsch: {first['sources']}")
    check("3× TeamViewer" in first["description"] and "Müller GmbH" in first["description"],
          f"Beschreibung: {first['description']}")
    for key in ("start", "end", "type", "category", "customer_name", "description", "details",
                "is_suggestion", "rule", "sources"):
        check(key in first, f"Schlüssel {key} fehlt")


def test_vorrang_und_verschmelzen(check):
    """3. Vorrang: Verbindung schlägt PC-Fenster, Rest wird gekürzt (auch geteilt)."""
    out = rules.classify([e("10:20:00", "10:40:00", "RDP-Verbindung", "srv01")],
                         [pc("10:00:00", "11:00:00", "outlook.exe", "Posteingang")], R)
    summary = [(b["start"][11:16], b["end"][11:16], b["category"]) for b in out]
    check(summary == [("10:00", "10:20", "E-Mail / Kommunikation"), ("10:20", "10:40", "Fernwartung"),
                      ("10:40", "11:00", "E-Mail / Kommunikation")], f"Vorrang falsch: {summary}")
    check(no_overlap(out), "Vorrang: Überschneidung")

    # Kurzes Fenster in der Lücke zwischen zwei Sitzungen gehört zur Sitzung
    out = rules.classify([e("09:00:00", "09:30:00", "TeamViewer", "A"),
                          e("09:33:00", "10:00:00", "TeamViewer", "A")],
                         [pc("09:30:00", "09:33:00", "outlook.exe", "Posteingang")], R)
    check([(b["start"][11:16], b["end"][11:16]) for b in out] == [("09:00", "10:00")],
          f"Sitzungslücke nicht überbrückt: {out}")

    # Telefonat mitten in VPN: Regelreihenfolge entscheidet, VPN wird geteilt
    out = rules.classify([e("12:00:00", "13:00:00", "VPN-Verbindung", "K"),
                          e("12:20:00", "12:30:00", "Telefonat", "Max")], [], R)
    summary = [(b["start"][11:16], b["end"][11:16], b["category"]) for b in out]
    check(summary == [("12:00", "12:20", "Fernwartung"), ("12:20", "12:30", "Telefonsupport"),
                      ("12:30", "13:00", "Fernwartung")], f"Telefonat in VPN: {summary}")

    # Reihenfolge ändern: VPN vor Telefonat -> VPN gewinnt ganz
    swapped = [R[2], R[1]] + [r for i, r in enumerate(R) if i not in (1, 2)]
    out = rules.classify([e("12:00:00", "13:00:00", "VPN-Verbindung", "K"),
                          e("12:20:00", "12:30:00", "Telefonat", "Max")], [], swapped)
    check([(b["start"][11:16], b["end"][11:16]) for b in out] == [("12:00", "13:00")],
          f"Priorität per Reihenfolge wirkt nicht: {out}")

    # Kurzer Wechsel (unter min_minutes) teilt den Block nicht
    out = rules.classify([], [pc("10:00:00", "10:10:00", "outlook.exe", "Posteingang"),
                              pc("10:10:00", "10:11:00", "ms-teams.exe", "Chat"),
                              pc("10:11:00", "10:20:00", "outlook.exe", "Posteingang")], R)
    check([(b["start"][11:16], b["end"][11:16], b["category"]) for b in out]
          == [("10:00", "10:20", "E-Mail / Kommunikation")], f"kurzer Wechsel teilt: {out}")

    # Lücke größer als gap_minutes -> zwei Blöcke; min_minutes filtert
    out = rules.classify([e("09:00:00", "09:10:00", "TeamViewer", "A"),
                          e("09:20:00", "09:30:00", "TeamViewer", "A")], [], R, gap_minutes=5)
    check(len(out) == 2, f"große Lücke verbunden: {out}")
    out = rules.classify([e("09:00:00", "09:10:00", "TeamViewer", "A"),
                          e("09:20:00", "09:30:00", "TeamViewer", "A")], [], R, gap_minutes=15)
    check(len(out) == 1, f"gap_minutes wirkt nicht: {out}")
    out = rules.classify([e("09:00:00", "09:01:30", "TeamViewer", "A")], [], R, min_minutes=2)
    check(out == [], f"zu kurzer Block bleibt: {out}")
    # Verschiedene Kunden werden nie verbunden
    out = rules.classify([e("09:00:00", "09:10:00", "TeamViewer", "A"),
                          e("09:10:00", "09:20:00", "TeamViewer", "B")], [], R)
    check([b["customer_name"] for b in out] == ["A", "B"], f"Kunden vermischt: {out}")


def test_regex_gruppen_kunden_felder(check):
    """4. Regex-Gruppen als Kunde, feste Kunden, Felder."""
    ticket = dict(R[6], enabled=True)
    out = rules.classify([], [pc("09:00:00", "09:30:00", "chrome.exe",
                                 "Ticket #123 – Müller GmbH - Google Chrome")], [ticket])
    check(out and out[0]["customer_name"] == "Müller GmbH", f"Regex-Gruppe als Kunde: {out}")
    custom = [{"name": "Projekt", "field": "any", "match": r"re:Projekt (\w+)", "category": "Interne Tätigkeit",
               "customer": "Intern {1}", "enabled": True},
              {"name": "fest", "field": "details", "match": "Wartungsvertrag", "category": "Fernwartung",
               "customer": "Stammkunde AG", "enabled": True},
              {"name": "aus", "field": "type", "match": "TeamViewer", "category": "X", "enabled": False}]
    out = rules.classify([e("09:00:00", "09:30:00", "Notiz", "Projekt Alpha"),
                          e("10:00:00", "10:30:00", "TeamViewer", "Kunde", details="Wartungsvertrag 7"),
                          e("11:00:00", "11:30:00", "TeamViewer", "Kunde")], [], custom)
    check([(b["category"], b["customer_name"]) for b in out]
          == [("Interne Tätigkeit", "Intern Alpha"), ("Fernwartung", "Stammkunde AG")],
          f"Felder/Kunden/abgeschaltet: {[(b['category'], b['customer_name']) for b in out]}")
    check(rules.fill_customer("{2}", rules.compile_pattern("re:(a)").search("a")) == "",
          "fehlende Gruppe gibt keinen leeren Text")
    # Feld "title" passt nicht auf Verbindungen, "customer" nicht auf PC-Fenster
    out = rules.classify([e("09:00:00", "09:30:00", "TeamViewer", "Posteingang")],
                         [pc("10:00:00", "10:30:00", "x.exe", "Müller")],
                         [{"field": "title", "match": "Posteingang", "category": "A", "enabled": True},
                          {"field": "customer", "match": "Müller", "category": "B", "enabled": True}])
    check(out == [], f"Felder vermischt: {out}")


def test_kaputte_eintraege_und_leere_regeln(check):
    """5. Kaputte Einträge, eigene Ergebnisse und leere Regeln."""
    out = rules.classify([{"start": "kaputt", "end": D + "10:00:00", "type": "TeamViewer"},
                          {"type": "TeamViewer"}, "keinDict",
                          e("10:00:00", "09:00:00", "TeamViewer", "rückwärts"),
                          e("09:00:00", "10:00:00", "Klassifizierung", "alt")], [], R)
    check(out == [], f"kaputte Einträge: {out}")
    check(rules.classify([e("09:00:00", "10:00:00", "TeamViewer", "A")], [], []) == [], "ohne Regeln")


def test_tempo(check):
    """6. Tempo: ein Tag mit 5.000 PC-Abschnitten und 200 Verbindungen unter 200 ms."""
    start = datetime(2026, 10, 22, 6, 0, 0)
    apps = [("outlook.exe", "Posteingang"), ("chrome.exe", "Microsoft 365 admin center"),
            ("ms-teams.exe", "Chat"), ("notepad.exe", "Notiz"), ("mstsc.exe", "srv - Remotedesktopverbindung"),
            ("chrome.exe", "Zeitung")]
    big_pc, t = [], start
    for i in range(5000):
        a, title = apps[(i * 7) % len(apps)]
        t2 = t + timedelta(seconds=8 + (i % 5) * 3)
        big_pc.append({"start": t.strftime(rules.TIME_FMT), "end": t2.strftime(rules.TIME_FMT),
                       "type": f"PC: {a}", "customer_name": f"{title} {i % 40}", "app": a, "details": a})
        t = t2
    big = []
    for i in range(200):
        s = start + timedelta(minutes=i * 3)
        big.append({"start": s.strftime(rules.TIME_FMT),
                    "end": (s + timedelta(minutes=2)).strftime(rules.TIME_FMT),
                    "type": ["TeamViewer", "RDP-Verbindung", "Telefonat", "VPN-Verbindung"][i % 4],
                    "customer_name": f"Kunde {i % 7}", "details": ""})
    t0 = time.perf_counter()
    out = rules.classify(big, big_pc, R)
    ms = (time.perf_counter() - t0) * 1000
    print(f"Tempo: {len(big_pc)} PC-Abschnitte + {len(big)} Verbindungen -> {len(out)} Blöcke in {ms:.0f} ms")
    check(ms < 200, f"zu langsam: {ms:.0f} ms")
    check(no_overlap(out), "Tempo-Tag: Überschneidung")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
