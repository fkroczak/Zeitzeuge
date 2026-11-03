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


# Aus einer echten FortiVPN_1.log (FortiClient 7), gekürzt
FORTIVPN = """\
[2026-10-12 17:21:19.3224544 UTC+02:00] [11544:11532] [FortiVPN  2204    info] fortivpn::StateMachine::HandleTunnelConnected "av" is connected.
[2026-10-12 17:30:00.0000000 UTC+02:00] [11544:11840] [FortiVPN  1    info] fortivpn::IFortiVPN_Impl::Handle_PowerBroadcastMsg() Unhandled Power Event: 0x12
[2026-10-12 18:12:48.5048035 UTC+02:00] [11544:11532] [FortiVPN  2331    info] fortivpn::StateMachine::HandleTunnelDisconnectRequest() "av" is going to be disconnected.
[2026-10-12 18:12:54.1352009 UTC+02:00] [11544:11532] [FortiVPN  2370    info] fortivpn::StateMachine::HandleTunnelDisconnected "av" is disconnected.
[2026-10-12 18:12:55.4286733 UTC+02:00] [11544:11532] [FortiVPN  2370    info] fortivpn::StateMachine::HandleTunnelDisconnected "av" is disconnected.
[2026-10-13 08:34:22.1478512 UTC+02:00] [11544:11532] [FortiVPN  2370    info] fortivpn::StateMachine::HandleTunnelDisconnected "A.S.I." is disconnected.
[2026-10-13 08:49:05.5787346 UTC+02:00] [11544:11532] [FortiVPN  2204    info] fortivpn::StateMachine::HandleTunnelConnected "A.S.I." is connected.
[2026-10-13 12:01:59.9952371 UTC+02:00] [11544:11840] [FortiVPN  749    info] Sleep while machine is running, will suspend myself.
[2026-10-13 13:42:03.9977917 UTC+02:00] [11544:11840] [FortiVPN  743    info] wakeup after sleep, will resume.
[2026-11-03 21:07:02.0000000 UTC+02:00] [19768:5760] [FortiVPN  2204    info] fortivpn::StateMachine::HandleTunnelConnected "kreimer" is connected.
""".splitlines()


def test_fortivpn_log(same):
    rows = [(c["start"], c["end"], c["customer_name"], c["running"])
            for c in parse_forti_trace(FORTIVPN, now=datetime(2026, 11, 3, 21, 30))]
    same("FortiVPN_1.log", rows, [
        ("2026-10-12 17:21:19", "2026-10-12 18:12:54", "av", False),
        ("2026-10-13 08:49:05", "2026-10-13 12:01:59", "A.S.I.", False),   # Ruhezustand beendet
        ("2026-11-03 21:07:02", "2026-11-03 21:30:00", "kreimer", True),   # noch verbunden
    ])
    with temp_dir() as tmp:
        for name in ("FortiVPN_1.log", "FortiVPN_1_error.log"):
            with open(os.path.join(tmp, name), "w", encoding="cp1252") as f:
                f.write("\n".join(FORTIVPN[:5] if name == "FortiVPN_1.log" else ["[x] Fehler"]) + "\n")
        reader = VpnReader(os.path.join(tmp, "vpn.json"), [os.path.join(tmp, "fehlt")], adapter_func=lambda: [])
        reader.forti_paths = [os.path.join(tmp, "FortiVPN_*.log")]
        same("mit *", [c["customer_name"] for c in reader.connections()], ["av"])


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


def _rdp_event(when, number, activity, pid, value=""):
    """Ein Ereignis wie von wevtutil /f:xml (SystemTime in UTC)."""
    utc = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.1234567Z")
    return ('<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System>'
            '<Provider Name="Microsoft-Windows-TerminalServices-ClientActiveXCore"/>'
            f'<EventID>{number}</EventID><TimeCreated SystemTime="{utc}"/>'
            f'<Correlation ActivityID="{activity}"/><Execution ProcessID="{pid}" ThreadID="1"/>'
            f'</System><EventData><Data Name="Name">x</Data><Data Name="Value">{value}</Data>'
            '</EventData></Event>')


def test_mstsc_aus_ereignisprotokoll(same):
    from rdp_reader import parse_rdp_events
    fmt = "%Y-%m-%d %H:%M:%S"
    a, b, c = "{AAAA}", "{BBBB}", "{CCCC}"
    xml = "".join([  # neueste zuerst, wie wevtutil /rd:true
        _rdp_event(datetime(2026, 11, 3, 15, 0, 0), 1024, c, 300, "SRV-OFFEN"),
        _rdp_event(datetime(2026, 11, 3, 13, 0, 10), 1026, b, 200, "2"),
        _rdp_event(datetime(2026, 11, 3, 13, 0, 5), 1024, b, 200, "FEHLVERSUCH"),
        _rdp_event(datetime(2026, 11, 3, 11, 45, 0), 1026, a, 100, "1"),
        _rdp_event(datetime(2026, 11, 3, 10, 0, 3), 1102, a, 100, "10.0.0.5"),
        _rdp_event(datetime(2026, 11, 3, 10, 0, 2), 1027, a, 100, "DOMAIN"),
        _rdp_event(datetime(2026, 11, 3, 10, 0, 0), 1024, a, 100, "DC01.kunde.local:3389"),
    ])
    rows = [(s["start"].strftime(fmt)[11:], s["end"].strftime(fmt)[11:] if s["end"] else None, s["host"])
            for s in parse_rdp_events(xml)]
    same("Ereignisse", rows, [("10:00:00", "11:45:00", "DC01.kunde.local"),
                              ("13:00:05", "13:00:10", "FEHLVERSUCH"), ("15:00:00", None, "SRV-OFFEN")])
    same("kaputtes XML", parse_rdp_events("<Event"), [])

    with temp_dir() as tmp:
        reader = RdpReader({}, os.path.join(tmp, "rdp.json"), proc_func=lambda: [], event_func=lambda: xml)
        rows = [(c["start"][11:], c["end"][11:], c["customer_name"], c["rdp_source"])
                for c in reader.connections()]
        same("Timeline", rows, [("10:00:00", "11:45:00", "DC01.kunde.local", "mstsc"),
                                ("15:00:00", "15:01:00", "SRV-OFFEN", "mstsc")])
        assert "Ereignisprotokoll" in reader.connections()[0]["details"]

        # Selbst aufgezeichnet (Zeitzeuge kam erst 10:30 dazu): eine Sitzung, Beginn aus dem Protokoll
        procs = [(7, datetime(2026, 11, 3, 10, 30, 0).timestamp(), ["mstsc.exe", "/v:DC01.kunde.local"])]
        reader2 = RdpReader({}, os.path.join(tmp, "rdp2.json"), proc_func=lambda: list(procs),
                            title_func=lambda: {}, event_func=lambda: xml)
        t = datetime(2026, 11, 3, 10, 30, 0)
        while t < datetime(2026, 11, 3, 11, 44, 0):
            reader2.sample(now=t)
            t += timedelta(seconds=30)
        procs.clear()
        reader2.sample(now=t)
        rows = [(c["start"][11:], c["end"][11:], c["customer_name"]) for c in reader2.connections()]
        same("zusammengeführt", rows, [("10:00:00", "11:45:00", "DC01.kunde.local"),
                                       ("15:00:00", "15:01:00", "SRV-OFFEN")])

        off = RdpReader({"mstsc_events_enabled": False}, os.path.join(tmp, "rdp3.json"),
                        proc_func=lambda: [], event_func=lambda: xml)
        same("Ereignisprotokoll aus", off.connections(), [])
