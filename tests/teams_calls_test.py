"""Teams-Anrufe: Mikrofon-Nutzung (Registry), Teams-Logs, Zusammenführen, Ablage."""
import contextlib
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import datastore  # noqa: E402
import teams_calls as tc  # noqa: E402

TF = tc.TIME_FMT
PLUS1 = timezone(timedelta(hours=1))


def local(*args, tz=PLUS1):
    """Zeit in einer Zeitzone -> lokale Zeit dieses Rechners (wie im Parser)."""
    return datetime(*args, tzinfo=tz).astimezone().replace(tzinfo=None)


def filetime(dt_utc):
    return int((dt_utc - datetime(1601, 1, 1, tzinfo=timezone.utc)).total_seconds() * 10_000_000)


@contextlib.contextmanager
def temp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            yield tmp
        finally:
            datastore.unregister(tmp)


# Auszug aus MSTeams_*.log (neues Teams), Inhalte erfunden. Zwei Schreibweisen,
# wie sie in verschiedenen Versionen vorkommen.
LOG = """\
2026-10-26T09:14:58.123456+01:00 0x00002a10 <INFO> native_modules::PowerManagementModule: Display on
2026-10-26T09:15:02.483001+01:00 0x00002a10 <INFO> TelemetryService: Telemetry: {"name":"desktop_call_state_change_send","isOngoing":true,"callType":"oneToOne"}
2026-10-26T09:20:00.000000+01:00 0x00002a10 <INFO> TelemetryService: Telemetry: {"name":"desktop_call_state_change_send","isOngoing":true}
2026-10-26T09:27:40.001000+01:00 0x00002a10 <INFO> TelemetryService: Telemetry: {"name":"desktop_call_state_change_send","isOngoing":false}
kaputte Zeile desktop_call_state_change_send isOngoing: true
2026-10-26T10:05:10Z 0x00002a10 <INFO> Received Action: name: desktop_call_state_change_send, isOngoing: true
2026-10-26T10:06:00Z 0x00002a10 <INFO> Received Action: name: desktop_call_state_change_send, isOngoing: false
2026-10-26 11:00:00.5 0x1 <INFO> desktop_call_state_change_send isOngoing=false
2026-10-26T11:30:00.000+01:00 0x1 <INFO> desktop_call_state_change_send "isOngoing": true
""".splitlines()


def test_filetime():
    when = datetime(2026, 10, 26, 8, 0, 5, tzinfo=timezone.utc)
    assert tc.filetime_to_local(filetime(when)) == when.astimezone().replace(tzinfo=None)
    assert tc.filetime_to_local(0) is None and tc.filetime_to_local("x") is None


def test_teams_schluessel():
    assert tc.is_teams_key("MSTeams_8wekyb3d8bbwe")
    assert tc.is_teams_key(r"C:#Users#max#AppData#Local#Microsoft#Teams#current#Teams.exe")
    assert not tc.is_teams_key("Microsoft.WindowsSoundRecorder_8wekyb3d8bbwe")
    assert not tc.is_teams_key(r"C:#Program Files#Zoom#Zoom.exe")
    assert tc.app_label(r"C:#x#Teams.exe") == "Teams (klassisch)"
    if sys.platform != "win32":
        assert tc.mic_readings() == []
    else:
        assert isinstance(tc.mic_readings(), list)  # ohne Teams: leer, nie ein Fehler


def test_mikrofon_nutzungen():
    now = datetime(2026, 10, 26, 12, 0)
    readings = [
        ("MSTeams_8wekyb3d8bbwe", datetime(2026, 10, 26, 11, 0), datetime(2026, 10, 26, 11, 20)),
        ("C:#x#Teams.exe", datetime(2026, 10, 26, 11, 50), None),          # läuft noch
        ("MSTeams_alt", datetime(2026, 10, 25, 8, 0), None),                 # unplausibel lange
        ("MSTeams_neu", None, datetime(2026, 10, 26, 9, 0)),                 # ohne Beginn
        ("MSTeams_x", datetime(2026, 10, 26, 10, 0), datetime(2026, 10, 26, 9, 0)),  # Stop alt: läuft
    ]
    s = tc.sessions_from_readings(readings, now)
    assert [(x["start"][11:16], x["end"][11:16], x["running"], x["app"]) for x in s] == [
        ("11:00", "11:20", False, "Teams"), ("11:50", "12:00", True, "Teams (klassisch)"),
        ("10:00", "12:00", True, "Teams")]


def test_log_parser():
    now = local(2026, 10, 26, 11, 45)
    calls = tc.parse_log(LOG, now=now)
    got = [(c["start"], c["end"], c["running"]) for c in calls]
    assert got == [
        (local(2026, 10, 26, 9, 15, 2).strftime(TF), local(2026, 10, 26, 9, 27, 40).strftime(TF), False),
        (local(2026, 10, 26, 10, 5, 10, tz=timezone.utc).strftime(TF),
         local(2026, 10, 26, 10, 6, tz=timezone.utc).strftime(TF), False),
        (local(2026, 10, 26, 11, 30).strftime(TF), now.strftime(TF), True),
    ]
    assert all(c["source"] == "log" for c in calls)
    assert tc.parse_log(["nichts", ""]) == []


def test_logdateien():
    with tempfile.TemporaryDirectory() as tmp:
        for name, lines in (("MSTeams_2026-10-26_09-00-00.00.log", LOG[:2]),
                            ("MSTeams_2026-10-26_09-20-00.01.log", LOG[2:4])):
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        os.utime(os.path.join(tmp, "MSTeams_2026-10-26_09-00-00.00.log"), (1, 1))  # sehr alt
        files = tc.log_files([os.path.join(tmp, "MSTeams_*.log")])
        assert [os.path.basename(f) for f in files] == ["MSTeams_2026-10-26_09-20-00.01.log"]
        now = datetime.now()
        os.utime(files[0], None)
        both = tc.log_files([os.path.join(tmp, "MSTeams_*.log")], days=100000)
        # Anruf beginnt in der einen und endet in der anderen Datei
        calls = tc.read_logs(both, now=now)
        assert len(calls) == 1 and not calls[0]["running"]


def test_eintraege_und_besprechung():
    sessions = [
        {"start": "2026-10-26 09:00:00", "end": "2026-10-26 09:10:00", "source": "mikrofon", "app": "Teams"},
        {"start": "2026-10-26 09:09:30", "end": "2026-10-26 09:12:00", "source": "log", "app": "Teams"},
        {"start": "2026-10-26 09:12:40", "end": "2026-10-26 09:15:00", "source": "mikrofon", "app": "Teams"},
        {"start": "2026-10-26 10:00:00", "end": "2026-10-26 10:00:10", "source": "mikrofon", "app": "Teams"},
        {"start": "2026-10-26 14:00:00", "end": "2026-10-26 14:50:00", "source": "mikrofon", "app": "Teams"},
    ]
    meetings = [{"start": "2026-10-26 14:00:00", "end": "2026-10-26 15:00:00", "type": "Teams-Besprechung",
                 "customer_name": "Jour fixe Kunde Nord", "email_domains": ["kunde-nord.de"]}]
    entries = tc.call_entries(sessions, meetings)
    assert [(e["start"][11:16], e["duration_s"], e["customer_name"]) for e in entries] == [
        ("09:00", 900, ""), ("14:00", 3000, "Jour fixe Kunde Nord")]  # 10 s Gerätetest fehlt
    call, meeting = entries
    assert call["type"] == "Teams-Anruf" and call["direction"] == "Anruf"
    assert "Mikrofon und Teams-Log" in call["details"] and call["details"].startswith("Dauer 15:00")
    assert meeting["email_domains"] == ["kunde-nord.de"] and meeting["teams_meeting"]
    # Kurze Anrufe zeigen, wenn gewünscht
    assert len(tc.call_entries(sessions, min_seconds=0)) == 3


def test_ablage_und_tracker():
    with temp_dir() as tmp:
        path = os.path.join(tmp, "teams_anrufe.json")
        state = {"readings": []}
        tracker = tc.TeamsCallTracker(path, mic_func=lambda: state["readings"], use_logs=False)
        t0 = datetime(2026, 10, 26, 9, 0)
        assert tracker.sample(t0) == []

        # Anruf beginnt: läuft, Ende = jetzt
        state["readings"] = [("MSTeams_8wekyb3d8bbwe", t0, None)]
        assert tracker.sample(t0 + timedelta(minutes=1)) == ["2026-10-26"]
        day = tc.load_day(path, "2026-10-26")
        assert len(day) == 1 and day[0]["running"] and day[0]["end"] == "2026-10-26 09:01:00"
        # Anruf endet
        state["readings"] = [("MSTeams_8wekyb3d8bbwe", t0, t0 + timedelta(minutes=7))]
        tracker.sample(t0 + timedelta(minutes=8))
        day = tc.load_day(path, "2026-10-26")
        assert len(day) == 1 and not day[0]["running"] and day[0]["end"] == "2026-10-26 09:07:00"
        assert tracker.sample(t0 + timedelta(minutes=9)) == []  # nichts Neues

        # Zeitzeuge war während des nächsten Anrufs aus: Windows kennt nur noch einen neueren
        t1 = t0 + timedelta(hours=1)
        state["readings"] = [("MSTeams_8wekyb3d8bbwe", t1, None)]
        tracker.sample(t1 + timedelta(minutes=2))
        t2 = t0 + timedelta(hours=2)
        state["readings"] = [("MSTeams_8wekyb3d8bbwe", t2, t2 + timedelta(minutes=3))]
        tracker.sample(t2 + timedelta(minutes=5))
        day = tc.load_day(path, "2026-10-26")
        assert [(s["start"][11:16], s["end"][11:16], s["running"]) for s in day] == [
            ("09:00", "09:07", False), ("10:00", "10:02", False), ("11:00", "11:03", False)]

        # Mikrofon nicht lesbar: kein Absturz
        def broken():
            raise OSError("Registry gesperrt")
        tc.TeamsCallTracker(path, mic_func=broken, use_logs=False).sample(t2)

        # verschlüsselt in der Datenbank
        datastore.unregister(tmp)
        with open(os.path.join(tmp, datastore.DB_NAME), "rb") as f:
            assert b"mikrofon" not in f.read()


def test_tracker_mit_logs():
    with temp_dir() as tmp, tempfile.TemporaryDirectory() as logs:
        with open(os.path.join(logs, "MSTeams_1.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(LOG[1:4]) + "\n")
        path = os.path.join(tmp, "teams_anrufe.json")
        tracker = tc.TeamsCallTracker(path, mic_func=lambda: [],
                                      log_globs=[os.path.join(logs, "MSTeams_*.log")])
        changed = tracker.sample(datetime.now())
        assert len(changed) == 1
        assert tracker.sample(datetime.now()) == []  # Logs unverändert: nicht neu lesen
        assert tc.load_day(path, changed[0])[0]["source"] == "log"
