"""TeamViewer- und RDM-Logs einlesen (log_parsers.py) und Zeitformat prüfen."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from log_parsers import RdmParser, TeamViewerParser  # noqa: E402
from timeline_only import parse_time  # noqa: E402


@pytest.fixture
def config(tmp_path):
    folder = str(tmp_path)
    tv_path = os.path.join(folder, "Connections.txt")
    rdm_path = os.path.join(folder, "Connections.log")
    with open(tv_path, "w", encoding="utf-8") as f:
        f.write("1076789144\t21-10-2026 07:12:00\t21-10-2026 07:47:30\tdemo\tRemoteControl\t{x}\n"
                "1123456789\t21-10-2026 08:00:00\t21-10-2026 08:00:40\tzu kurz\n"
                "1123456789\t32-13-2026 08:00:00\t21-10-2026 09:00:00\tungültiges Datum\n"
                "Kopfzeile ohne Daten\n")
    with open(rdm_path, "w", encoding="utf-8") as f:
        f.write("[21.10.2026 09:02:00] Verbinden - 'Kanzlei - DC01' (RDP (Microsoft Remote Desktop))\n"
                "[21.10.2026 09:03:20] Passwort angezeigt - 'Kanzlei - DC01' (RDP (Microsoft Remote Desktop))\n"
                "[21.10.2026 09:58:00] Getrennt - 'Kanzlei - DC01' (RDP (Microsoft Remote Desktop))\n"
                "[21.10.2026 10:20:00] Verbinden - 'Firewall' (SSH Shell)\n"
                "[99.10.2026 10:20:00] Verbinden - 'kaputt' (SSH Shell)\n")
    return {"teamviewer_paths": [tv_path], "teamviewer_timezone_correction": 1,
            "rdm_paths": [rdm_path, os.path.join(folder, "fehlt.log")], "rdm_timezone_correction": 0}


def test_teamviewer(config):
    tv = TeamViewerParser(config)
    rows = tv.parse_logs()
    assert [(r["start"], r["end"], r["tv_id"]) for r in rows] == [
        ("2026-10-21 08:12:00", "2026-10-21 08:47:30", "1076789144")], rows  # +1 h, kurze/ungültige weg
    assert tv.files_read == 1
    assert tv.parse_logs() is not rows and tv.parse_logs() == rows  # zweites Mal aus dem Cache


def test_rdm(config):
    rdm = RdmParser(config)
    rows = rdm.parse_logs()
    summary = [(r["start"][11:], r["end"][11:], r["type"], r["customer_name"]) for r in rows]
    assert summary == [
        ("09:03:20", "09:03:30", "Passwortaktion", "Kanzlei - DC01"),
        ("09:02:00", "09:58:00", "RDP-Verbindung", "Kanzlei - DC01"),
        ("10:20:00", "10:21:00", "SSH-Sitzung", "Firewall"),  # nie getrennt: 1 Minute
    ], summary
    assert rdm.files_read == 1  # fehlende Datei zählt nicht

    # Zeitzonenkorrektur aus der Config wirkt sofort (neuer Cache-Schlüssel)
    config["rdm_timezone_correction"] = 2
    assert rdm.parse_logs()[1]["start"] == "2026-10-21 11:02:00"


def test_zeitformat():
    assert str(parse_time("2026-10-21 08:12:00")) == "2026-10-21 08:12:00"


@pytest.mark.parametrize("bad", ["2026-10-21", "2026-10-21T08:12:00", "21.10.2026 08:12:00",
                                 "2026-13-21 08:12:00"])
def test_zeitformat_ungueltig(bad):
    with pytest.raises(ValueError):
        parse_time(bad)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
