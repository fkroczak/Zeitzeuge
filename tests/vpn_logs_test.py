"""VPN-Logs lesen: OpenVPN GUI, OpenVPN Connect, Neuverbindung, noch offene Verbindung."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from log_parsers import VpnParser  # noqa: E402


def test_openvpn_logs(tmp_path):
    folder = str(tmp_path)
    with open(os.path.join(folder, "kunde-mueller.log"), "w", encoding="utf-8") as f:
        f.write("""2026-10-22 08:10:01 OpenVPN 2.6.12 x86_64
2026-10-22 08:10:09 Initialization Sequence Completed
2026-10-22 08:55:40 SIGTERM[hard,] received, process exiting
2026-10-22 13:00:00 Initialization Sequence Completed
2026-10-22 13:20:00 SIGUSR1[soft,connection-reset] received, process restarting
2026-10-22 13:20:30 Initialization Sequence Completed
2026-10-22 14:02:00 MANAGEMENT: >STATE:1234,CONNECTED,SUCCESS
""")
    with open(os.path.join(folder, "connect.txt"), "w", encoding="utf-8") as f:
        f.write("""[Oct 22, 2026, 09:01:00] Session is starting
[Oct 22, 2026, 09:01:03] EVENT: CONNECTED user@vpn.example.com
[Oct 22, 2026, 09:40:00] EVENT: DISCONNECTED
""")
    with open(os.path.join(folder, "ignoriert.bin"), "w") as f:
        f.write("2026-10-22 10:00:00 Initialization Sequence Completed\n")

    parser = VpnParser({"vpn_paths": [folder, os.path.join(folder, "fehlt.log")],
                        "vpn_timezone_correction": 0})
    got = sorted((c["start"][11:16], c["end"][11:16], c["customer_name"]) for c in parser.parse_logs())
    want = [
        ("08:10", "08:55", "kunde-mueller"),
        ("09:01", "09:40", "connect"),
        ("13:00", "13:20", "kunde-mueller"),
        ("13:20", "14:02", "kunde-mueller"),  # noch verbunden: bis zum letzten Eintrag
    ]
    assert got == want
    assert parser.files_read == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
