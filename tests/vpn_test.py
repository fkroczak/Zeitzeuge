"""VPN-Zeiten aus Sophos Connect (scvpn.log, scgui.log) und FortiClient (charon.log)."""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from vpn_reader import VpnReader, adapters_up, parse_fortinet, parse_sophos  # noqa: E402

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


@pytest.fixture
def same(check):
    """Vergleich wie im alten Skript: alle Vergleiche laufen, Fehler werden gesammelt."""
    return lambda label, got, want: check(got == want, f"{label}: {got!r} statt {want!r}")


def test_sophos_und_forticlient(same):
    names = {}
    rows = [(c["start"], c["end"], c["customer_name"], c["running"])
            for c in parse_sophos(SCVPN, SCGUI, names, now=NOW)]
    same("Sophos", rows, [
        ("2026-10-19 14:20:33", "2026-10-19 16:37:04", "Kunde Nord", False),  # Fehlversuch davor fehlt
        ("2026-10-21 11:00:00", "2026-10-21 21:21:38", "198.51.100.30", False),  # Ende = Schlafbeginn
        ("2026-10-22 09:25:59", "2026-10-22 10:00:00", "Kunde Süd", True),  # läuft noch
    ])
    same("Namen gelernt", names, {"203.0.113.20": "Kunde Nord", "198.51.100.30": "Kunde Süd"})

    rows = [(c["start"][11:], c["end"][11:], c["customer_name"]) for c in parse_fortinet(CHARON, now=NOW)]
    same("FortiClient", rows, [("08:25:27", "08:28:16", "FortiClient"), ("15:36:12", "15:51:02", "FortiClient")])


def test_archiv_bleibt_erhalten(same):
    """Archiv: bleibt erhalten, auch wenn die Logs überschrieben werden."""
    with tempfile.TemporaryDirectory() as tmp:
        logs = os.path.join(tmp, "Connect")
        os.makedirs(logs)
        for name, lines in [("scvpn.log", SCVPN[:6]), ("scgui.log", SCGUI), ("charon.log.old", CHARON)]:
            with open(os.path.join(logs, name), "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        archive = os.path.join(tmp, "vpn_verbindungen.json")
        same("erstes Lesen", len(VpnReader(archive, [logs]).connections()), 3)
        for name in os.listdir(logs):
            os.remove(os.path.join(logs, name))
        same("nach Überschreiben", len(VpnReader(archive, [logs]).connections()), 3)
        with open(archive, encoding="utf-8") as f:
            same("Archiv-Namen", json.load(f)["names"], {"203.0.113.20": "Kunde Nord"})


def test_eigene_aufzeichnung(same):
    """Eigene Aufzeichnung: Adapter alle 30 s prüfen, ohne Logs."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "vpn_verbindungen.json")
        up = []
        reader = VpnReader(archive, [os.path.join(tmp, "fehlt")], adapter_func=lambda: list(up))
        t = datetime(2026, 10, 23, 9, 0, 0)

        def tick(seconds=30):
            nonlocal t
            t += timedelta(seconds=seconds)
            reader.sample(now=t)

        tick()                                   # 09:00:30 nichts verbunden
        up[:] = ["Fortinet Virtual Ethernet Adapter (NDIS 6.30) (Ethernet 3)", "Intel Wi-Fi"]
        for _ in range(10):
            tick()                               # 09:01:00 – 09:05:30 verbunden
        up[:] = []
        tick()                                   # 09:06:00 getrennt
        up[:] = ["Sophos TAP Adapter (Sophos-TAP)"]
        tick()                                   # 09:06:30 Sophos verbunden
        tick()                                   # 09:07:00
        tick(3600)                               # Ruhezustand: Ende bleibt 09:07:00, neuer Eintrag ab 10:07:00
        tick()                                   # 10:07:30

        # Zeitzeuge wird neu gestartet (z. B. nach Absturz): Archiv bleibt, offener Eintrag wird geschlossen
        reader2 = VpnReader(archive, [os.path.join(tmp, "fehlt")], adapter_func=lambda: [])
        reader2.sample(now=t + timedelta(seconds=30))
        rows = [(c["start"][11:], c["end"][11:], c["customer_name"], c["running"]) for c in reader2.connections()]
        same("eigene Aufzeichnung", rows, [
            ("09:01:00", "09:05:30", "FortiClient", False),
            ("09:06:30", "09:07:00", "Sophos Connect", False),
            ("10:07:00", "10:07:30", "Sophos Connect", False),
        ])

        # Logs mit Namen haben Vorrang: überlappende eigene Aufzeichnung fällt weg
        logs = os.path.join(tmp, "Connect")
        os.makedirs(logs)
        with open(os.path.join(logs, "scvpn.log"), "w", encoding="utf-8") as f:
            f.write("2026-10-23 09:06:40AM [1] dbg 198.51.100.30 VPN state changed to connected\n"
                    "2026-10-23 09:06:55AM [1] dbg 198.51.100.30 VPN state changed to disconnected\n")
        with open(os.path.join(logs, "scgui.log"), "w", encoding="utf-8") as f:
            f.write("2026-10-23 09:06:41AM [1] inf Verbindung Kunde Süd hergestellt\n")
        rows = [(c["start"][11:], c["customer_name"]) for c in VpnReader(archive, [logs], adapter_func=lambda: []).connections()]
        same("Logs vor eigener Aufzeichnung", rows, [
            ("09:01:00", "FortiClient"), ("09:06:40", "Kunde Süd"), ("10:07:00", "Sophos Connect")])


def test_echte_adapterabfrage():
    """Echte Adapterabfrage (unter Windows über GetAdaptersAddresses)."""
    found = adapters_up()
    print("Verbundene Adapter:", found)
    assert found and all(isinstance(a, str) and a.strip() for a in found), \
        f"Adapterabfrage liefert nichts Brauchbares: {found!r}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
