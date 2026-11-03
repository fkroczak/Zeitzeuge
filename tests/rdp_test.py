"""Remotedesktop: RDM Better (launcher.log), mstsc-Aufzeichnung, FortiClient-Trace-Logs, Pausen."""
import contextlib
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pytest  # noqa: E402

import datastore  # noqa: E402
from rdp_reader import RdpReader, host_from_cmdline, host_from_title, parse_launcher  # noqa: E402
from vpn_reader import VpnReader, parse_forti_trace  # noqa: E402

# Aus einer echten launcher.log (RDM Better), gekürzt
LAUNCHER = """\
2026-08-28T13:18:36.377Z [INFO] launch host=192.168.0.50:3389 user=itm-admin type=1 platform=win32 method=rdpfile
2026-10-08T14:48:20.477Z [INFO] launch host=autohaus.example.de:3389 user=10 type=5 platform=win32 method=rdpfile
2026-11-03T10:11:53.181Z [INFO] launch host=10.10.80.35:3389 user=Administrator type=1 platform=win32 method=rdpfile
2026-11-03T14:23:34.485Z [INFO] launch host=10.70.9.90:3389 user=Administrator type=1 platform=win32 method=rdpfile
irgendwas anderes
""".splitlines()


@pytest.fixture
def same(check):
    return lambda label, got, want: check(got == want, f"{label}: {got!r} statt {want!r}")


def local(y, mo, d, h, mi, s):
    """UTC -> Ortszeit dieses Rechners (wie im Programm)."""
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


@contextlib.contextmanager
def temp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            yield tmp
        finally:
            datastore.unregister(tmp)


def test_launcher_log(same):
    rows = [(l["time"], l["host"], l["user"]) for l in parse_launcher(LAUNCHER)]
    same("Starts", rows, [
        (local(2026, 8, 28, 13, 18, 36), "192.168.0.50", "itm-admin"),
        (local(2026, 10, 8, 14, 48, 20), "autohaus.example.de", "10"),
        (local(2026, 11, 3, 10, 11, 53), "10.10.80.35", "Administrator"),
        (local(2026, 11, 3, 14, 23, 34), "10.70.9.90", "Administrator"),
    ])


def test_ziel_aus_mstsc(same):
    with temp_dir() as tmp:
        rdp = os.path.join(tmp, "verbindung.rdp")
        with open(rdp, "w", encoding="utf-16") as f:
            f.write("screen mode id:i:2\r\nfull address:s:dc01.kunde.local:3389\r\nusername:s:admin\r\n")
        same("rdp-Datei", host_from_cmdline(["mstsc.exe", rdp]), "dc01.kunde.local")
    same("/v:", host_from_cmdline(["mstsc.exe", "/v:10.0.0.5:3390", "/f"]), "10.0.0.5:3390")
    same("ohne Ziel", host_from_cmdline(["mstsc.exe"]), "")
    same("Titel", host_from_title("DC01 - Remotedesktopverbindung"), "DC01")
    same("Titel englisch", host_from_title("ts01.kunde.de - Remote Desktop Connection"), "ts01.kunde.de")
    same("anderer Titel", host_from_title("Remotedesktopverbindung"), "")


def test_mstsc_und_rdm_better(same):
    with temp_dir() as tmp:
        start = local(2026, 11, 3, 10, 11, 53)
        log = os.path.join(tmp, "launcher.log")
        with open(log, "w", encoding="utf-8") as f:
            f.write("\n".join(LAUNCHER) + "\n")
        config = {"rdmbetter_paths": [log]}
        procs = []
        reader = RdpReader(config, os.path.join(tmp, "rdp_sitzungen.json"),
                           proc_func=lambda: list(procs), title_func=lambda: {7: ["10.10.80.35 - Remotedesktopverbindung"]})
        t = start - timedelta(seconds=5)
        reader.sample(now=t)                      # noch nichts offen
        procs[:] = [(7, (start + timedelta(seconds=4)).timestamp(), ["mstsc.exe", r"C:\fehlt\tmp.rdp"])]
        for _ in range(20):                       # 10 Minuten offen
            t += timedelta(seconds=30)
            reader.sample(now=t)
        procs[:] = []
        t += timedelta(seconds=30)
        reader.sample(now=t)                      # geschlossen

        rows = [(c["start"], c["end"], c["customer_name"], c["rdp_source"])
                for c in reader.connections() if c["start"].startswith("2026-11-03")]
        fmt = "%Y-%m-%d %H:%M:%S"
        same("Sitzungen", rows, [
            ((start + timedelta(seconds=4)).strftime(fmt), (start + timedelta(seconds=595)).strftime(fmt),
             "10.10.80.35", "RDM Better"),
            (local(2026, 11, 3, 14, 23, 34).strftime(fmt),
             (local(2026, 11, 3, 14, 23, 34) + timedelta(minutes=1)).strftime(fmt), "10.70.9.90", "RDM Better"),
        ])
        same("Typ wie RDM", {c["type"] for c in reader.connections()}, {"RDP-Verbindung"})

        # Archiv bleibt, auch ohne launcher.log; dann zählt die Sitzung als mstsc
        os.remove(log)
        again = RdpReader(config, os.path.join(tmp, "rdp_sitzungen.json"), proc_func=lambda: [])
        same("aus dem Archiv", [(c["customer_name"], c["rdp_source"]) for c in again.connections()],
             [("10.10.80.35", "mstsc")])
        config["mstsc_enabled"] = False
        same("mstsc aus", again.connections(), [])


FORTI = """\
[2026-11-03 08:01:10] info  connecting to vpn.kunde.de
[2026-11-03 08:01:14] info  connection name: Kunde Nord
[2026-11-03 08:01:15] info  tunnel is up, status=connected
[2026-11-03 09:30:02] info  disconnected, reason: user request
[2026-11-03 11:00:00] error not connected: authentication failed
""".splitlines()


def test_forticlient_trace(same):
    rows = [(c["start"][11:], c["end"][11:], c["customer_name"])
            for c in parse_forti_trace(FORTI, now=datetime(2026, 11, 3, 12, 0))]
    same("FortiClient", rows, [("08:01:15", "09:30:02", "Kunde Nord")])

    with temp_dir() as tmp:
        trace = os.path.join(tmp, "FortiVPN_1.log")
        with open(trace, "w", encoding="utf-8") as f:
            f.write("\n".join(FORTI) + "\n")
        reader = VpnReader(os.path.join(tmp, "vpn.json"), [os.path.join(tmp, "fehlt")], adapter_func=lambda: [])
        reader.forti_paths = [trace]
        same("im Archiv", [c["customer_name"] for c in reader.connections()], ["Kunde Nord"])


def test_pause_in_arbeitszeit(same):
    from timeline_only import work_spans
    config = {"work_days": {"Mo": "08:00-17:00", "Di": "08:00-12:00", "Sa": ""},
              "work_breaks": {"Mo": "12:00-12:30", "Di": "13:00-13:30", "Sa": "12:00-12:30"}}
    same("Montag", work_spans(config, 0), [(480, 720), (750, 1020)])
    same("Pause außerhalb", work_spans(config, 1), [(480, 720)])
    same("frei", work_spans(config, 5), [])
    same("ohne Pausen", work_spans({"work_days": {"Mo": "08:00-17:00"}}, 0), [(480, 1020)])
