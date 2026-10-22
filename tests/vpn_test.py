"""VPN-Zeiten aus Sophos Connect (scvpn.log, scgui.log) und FortiClient (charon.log)."""
import json
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vpn_reader import VpnReader, parse_fortinet, parse_sophos

SCVPN = """\
2026-10-19 02:16:57PM [12400] dbg 203.0.113.10 VPN state changed to connecting
2026-10-19 02:17:25PM [3680] dbg 203.0.113.10 VPN state changed to disconnecting
2026-10-19 02:20:20PM [31512] dbg 203.0.113.20 VPN state changed to connecting
2026-10-19 02:20:33PM [19752] dbg 203.0.113.20 VPN state changed to connected
2026-10-19 04:37:04PM [7792] dbg 203.0.113.20 VPN state changed to disconnecting
2026-10-19 04:37:08PM [15388] dbg 203.0.113.20 VPN state changed to disconnected
2026-10-21 11:00:00AM [8752] dbg 198.51.100.30 VPN state changed to connected
2026-10-21 09:21:38PM [5956] inf System is going to sleep
2026-10-22 08:08:53AM [5956] dbg 198.51.100.30 VPN state changed to disconnecting
2026-10-22 09:25:59AM [8752] dbg 198.51.100.30 VPN state changed to connected
""".splitlines()

SCGUI = """\
2026-10-19 02:20:20PM [7792] inf Verbindung Kunde Nord wird hergestellt
2026-10-19 02:20:34PM [7792] inf Verbindung Kunde Nord hergestellt
2026-10-22 09:26:00AM [6800] inf Verbindung Kunde Süd hergestellt
""".splitlines()

CHARON = """\
2026-10-20 08:25:27AM 18[KNL] interface 20 'Fortinet Virtual Ethernet Adapter (NDIS 6.30)' changed state from Down to Up
2026-10-20 08:28:16AM 19[KNL] interface 20 'Fortinet Virtual Ethernet Adapter (NDIS 6.30)' changed state from Up to Down
2026-10-20 03:36:12PM 29[KNL] interface 20 'Fortinet Virtual Ethernet Adapter (NDIS 6.30)' changed state from Down to Up
2026-10-20 03:51:02PM 31[KNL] interface 20 'Fortinet Virtual Ethernet Adapter (NDIS 6.30)' changed state from Up to Down
2026-10-22 09:25:54AM 22[KNL] interface 7 'Sophos TAP Adapter' changed state from Down to Up
2026-10-22 10:16:22AM 23[KNL] interface 7 'Sophos TAP Adapter' changed state from Up to Down
""".splitlines()

NOW = datetime(2026, 10, 22, 10, 0, 0)
errors = []


def check(label, got, want):
    if got != want:
        errors.append(f"{label}: {got!r} statt {want!r}")


names = {}
rows = [(c["start"], c["end"], c["customer_name"], c["running"])
        for c in parse_sophos(SCVPN, SCGUI, names, now=NOW)]
check("Sophos", rows, [
    ("2026-10-19 14:20:33", "2026-10-19 16:37:04", "Kunde Nord", False),  # Fehlversuch davor fehlt
    ("2026-10-21 11:00:00", "2026-10-21 21:21:38", "198.51.100.30", False),  # Ende = Schlafbeginn
    ("2026-10-22 09:25:59", "2026-10-22 10:00:00", "Kunde Süd", True),  # läuft noch
])
check("Namen gelernt", names, {"203.0.113.20": "Kunde Nord", "198.51.100.30": "Kunde Süd"})

rows = [(c["start"][11:], c["end"][11:], c["customer_name"]) for c in parse_fortinet(CHARON, now=NOW)]
check("FortiClient", rows, [("08:25:27", "08:28:16", "FortiClient"), ("15:36:12", "15:51:02", "FortiClient")])

# Archiv: bleibt erhalten, auch wenn die Logs überschrieben werden
with tempfile.TemporaryDirectory() as tmp:
    logs = os.path.join(tmp, "Connect")
    os.makedirs(logs)
    for name, lines in [("scvpn.log", SCVPN[:6]), ("scgui.log", SCGUI), ("charon.log.old", CHARON)]:
        with open(os.path.join(logs, name), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    archive = os.path.join(tmp, "vpn_verbindungen.json")
    check("erstes Lesen", len(VpnReader(archive, [logs]).connections()), 3)
    for name in os.listdir(logs):
        os.remove(os.path.join(logs, name))
    check("nach Überschreiben", len(VpnReader(archive, [logs]).connections()), 3)
    with open(archive, encoding="utf-8") as f:
        check("Archiv-Namen", json.load(f)["names"], {"203.0.113.20": "Kunde Nord"})

if errors:
    print("\n".join(errors))
    sys.exit(1)
print("VPN-Test ok")
