"""Zusammenfassen der Tagesliste (grouping.py) mit nachgebauten RDM/TeamViewer-Einträgen."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grouping import format_tv_id, group_entries, work_blocks

D = "2025-12-18 "


def e(start, end, kind, name, **extra):
    return {"start": D + start, "end": D + end, "type": kind, "customer_name": name,
            "details": "", "is_suggestion": True, **extra}


entries = [
    # VPN bricht ab und wird neu aufgebaut, dazwischen OTP/Passwort
    e("01:18:31", "01:21:00", "VPN-Verbindung", "Kunde - SSL VPN"),
    e("01:18:34", "01:18:44", "OTP-Anzeige", "Kunde - SSL VPN"),
    e("01:19:00", "01:19:10", "Passwortaktion", "Kunde - SSL VPN"),
    e("01:22:00", "01:25:00", "VPN-Verbindung", "Kunde - SSL VPN"),
    e("01:26:00", "01:42:00", "VPN-Verbindung", "Kunde - SSL VPN"),
    # nach langer Pause: neue Zeile
    e("03:00:00", "03:10:00", "VPN-Verbindung", "Kunde - SSL VPN"),
    # Zugangsdaten ohne Verbindung
    e("01:38:00", "01:38:10", "Passwortaktion", "server - root"),
    e("01:38:20", "01:38:30", "Passwortaktion", "server - root"),
    # Telefonate nie zusammenfassen
    e("01:30:00", "01:32:00", "Telefonat", "Max", direction="Eingehend"),
    e("01:33:00", "01:34:00", "Telefonat", "Max", direction="Eingehend"),
    # TeamViewer: gleiche ID mit kurzer Pause
    e("05:00:00", "05:20:00", "TeamViewer", "Müller", tv_id="1076789144"),
    e("05:23:00", "05:40:00", "TeamViewer", "Müller", tv_id="1076789144"),
]

grouped = group_entries(entries, gap_minutes=5)
rows = [(g["start"][11:16], g["end"][11:16], g["type"], g["customer_name"]) for g in grouped]
for r in rows:
    print(r)

vpn = [g for g in grouped if g["type"] == "VPN-Verbindung"]
assert [(g["start"][11:16], g["end"][11:16]) for g in vpn] == [("01:18", "01:42"), ("03:00", "03:10")], vpn
assert vpn[0]["details"] == "3 Verbindungen · 1× OTP, 1× Passwort", vpn[0]["details"]
assert len(vpn[0]["parts"]) == 5
creds = [g for g in grouped if g["type"] == "Zugangsdaten"]
assert len(creds) == 1 and creds[0]["details"] == "2× Passwort", creds
assert sum(1 for g in grouped if g["type"] == "Telefonat") == 2
tv = [g for g in grouped if g["type"] == "TeamViewer"]
assert len(tv) == 1 and tv[0]["end"].endswith("05:40:00") and tv[0]["tv_id"] == "1076789144"
assert len(grouped) == 6, len(grouped)
# Keine Minute geht verloren: alle Originale stecken in genau einer Zeile
assert sum(len(g.get("parts", [g])) for g in grouped) == len(entries)

blocks = work_blocks(grouped, gap_minutes=10)
assert [(b["start"][11:16], b["end"][11:16]) for b in blocks] == \
    [("01:18", "01:42"), ("03:00", "03:10"), ("05:00", "05:40")], blocks
assert blocks[0]["customer_name"].startswith("Kunde - SSL VPN")
assert blocks[0]["details"].endswith("· 9 Einträge"), blocks[0]["details"]

assert format_tv_id("1076789144") == "1 076 789 144"
print("Zusammenfassen ok")

# Doppelte Backslashes in alten Standardpfaden werden bereinigt
from main_timeline import clean_path  # noqa: E402
assert clean_path(r"C:\Users\x\AppData\Local\\Devolutions\\RDM\\Connections.log") == \
    r"C:\Users\x\AppData\Local\Devolutions\RDM\Connections.log"
assert clean_path(r"\\server\share\\x.log") == r"\\server\share\x.log"
print("Pfade ok")
