"""Spuren vom PC: Ereignisprotokoll, Sperren, SSH/PowerShell, Dateien, Browser, WLAN."""
import contextlib
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pytest  # noqa: E402

import datastore  # noqa: E402
import local_sources as ls  # noqa: E402


@pytest.fixture
def same(check):
    return lambda label, got, want: check(got == want, f"{label}: {got!r} statt {want!r}")


@contextlib.contextmanager
def temp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            yield tmp
        finally:
            datastore.unregister(tmp)


def local(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


EVENT = ('<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System>'
         '<Provider Name="Microsoft-Windows-{p}"/><EventID>{i}</EventID>'
         '<TimeCreated SystemTime="{t}"/></System></Event>')


def test_ereignisprotokoll(same):
    xml = "<Events>" + "".join(EVENT.format(p=p, i=i, t=t) for p, i, t in [
        ("Kernel-Power", 42, "2026-11-03T11:30:00.1234Z"),        # Ruhezustand
        ("Power-Troubleshooter", 1, "2026-11-03T12:15:00.000Z"),  # aufgewacht
        ("Kernel-General", 13, "2026-11-03T16:00:00.000Z"),       # heruntergefahren
        ("Kernel-General", 12, "2026-11-04T06:50:00.000Z"),       # gestartet
        ("Winlogon", 7002, "2026-11-04T09:00:00.000Z"),           # abgemeldet
        ("Winlogon", 7001, "2026-11-04T09:05:00.000Z"),           # angemeldet
        ("Kernel-Power", 41, "2026-11-04T10:00:00.000Z"),         # zählt nicht
    ]) + "</Events>"
    events = ls.parse_events(xml)
    same("Anzahl", len(events), 6)
    spans = ls.event_spans(events)
    same("Zeiten", spans, [
        (local(2026, 11, 3, 11, 30), local(2026, 11, 3, 12, 15), ls.SLEEP),
        (local(2026, 11, 3, 16, 0), local(2026, 11, 4, 6, 50), ls.OFF),
        (local(2026, 11, 4, 9, 0), local(2026, 11, 4, 9, 5), ls.LOGGED_OFF),
    ])
    same("kaputtes XML", ls.parse_events("<Events><x"), [])


def test_sitzungsziele(same):
    same("ssh", ls.session_target("ssh.exe", ["ssh", "-p", "2222", "-i", "key", "root@fw01.kunde.de"]),
         ("SSH-Verbindung", "fw01.kunde.de"))
    same("ssh ohne Ziel", ls.session_target("ssh.exe", ["ssh", "-V"]), None)
    same("putty -load", ls.session_target("putty.exe", ["putty.exe", "-load", "Kunde Nord DC"]),
         ("SSH-Verbindung", "Kunde Nord DC"))
    same("putty Titel", ls.session_target("putty.exe", ["putty.exe"], ["admin@nas01: ~ - PuTTY"]),
         ("SSH-Verbindung", "nas01"))
    same("winscp", ls.session_target("winscp.exe", ["WinSCP.exe", "sftp://u@files.kunde.de/"]),
         ("FTP-Verbindung", "files.kunde.de"))
    same("PSSession", ls.session_target("pwsh.exe", ["pwsh", "-c", "Enter-PSSession -ComputerName DC01"]),
         ("PowerShell-Sitzung", "DC01"))
    same("lokale PowerShell", ls.session_target("powershell.exe", ["powershell.exe"]), None)


def test_wlan_netsh(same):
    de = "    Name                   : WLAN\n    Status                 : Verbunden\n    SSID                   : Kunde-Gast\n    BSSID                  : aa:bb\n"
    en = "    State                  : disconnected\n"
    same("deutsch", ls.parse_netsh(de), "Kunde-Gast")
    same("getrennt", ls.parse_netsh(en), "")


def test_dateien_und_browser(same):
    with temp_dir() as tmp:
        recent = os.path.join(tmp, "Recent")
        os.makedirs(recent)
        for name, minute in (("Angebot Müller.docx.lnk", 5), ("Projekte.lnk", 6), ("desktop.ini", 7)):
            path = os.path.join(recent, name)
            open(path, "w").close()
            stamp = datetime(2026, 11, 3, 9, minute).timestamp()
            os.utime(path, (stamp, stamp))
        same("Dateien", ls.recent_files(recent), [(datetime(2026, 11, 3, 9, 5), "Angebot Müller.docx")])

        history = os.path.join(tmp, "History")
        con = sqlite3.connect(history)
        con.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT)")
        con.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)")

        def webkit(dt):
            utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return int((utc - datetime(1601, 1, 1)).total_seconds() * 1_000_000)

        rows = [(1, "https://portal.kunde.de/ticket?id=TCK0000012345&secret=1", "Ticket TCK0000012345", 10, 0),
                (2, "https://www.kunde.de/kontakt", "Kontakt", 10, 3),
                (3, "https://www.google.com/search?q=geheim", "geheim", 10, 4),
                (4, "https://kunde.de/x", "x", 10, 30)]
        for uid, url, title, h, m in rows:
            con.execute("INSERT INTO urls VALUES (?, ?, ?)", (uid, url, title))
            con.execute("INSERT INTO visits (url, visit_time) VALUES (?, ?)", (uid, webkit(datetime(2026, 11, 3, h, m))))
        con.commit()
        con.close()
        visits = ls.read_history(history, datetime(2026, 11, 1))
        same("Aufrufe", len(visits), 4)
        blocks = ls.browser_blocks(visits, ls.DEFAULT_BROWSER_IGNORE)
        same("Blöcke", [(b["start"].strftime("%H:%M"), b["end"].strftime("%H:%M"), b["domain"], b["tickets"])
                        for b in blocks], [
            ("10:00", "10:01", "portal.kunde.de", ["TCK0000012345"]),
            ("10:03", "10:04", "kunde.de", []),
            ("10:30", "10:31", "kunde.de", []),
        ])
        same("keine Adressen", any("secret" in str(b) or "geheim" in str(b) for b in blocks), False)


def test_leser(same):
    with temp_dir() as tmp:
        state = {"locked": False, "procs": [], "wlan": "Kunde-Gast"}
        reader = ls.LocalReader({"recent_files_dirs": [os.path.join(tmp, "fehlt")], "browser_paths": []},
                                os.path.join(tmp, "lokal_spuren.json"), funcs={
            "locked": lambda: state["locked"], "processes": lambda: list(state["procs"]),
            "titles": lambda: {}, "events": lambda: [], "wlan": lambda: state["wlan"],
            "history": lambda path, since: [], "threaded": False})
        t = datetime(2026, 11, 3, 9, 0, 0)

        def tick(seconds=30):
            nonlocal t
            t += timedelta(seconds=seconds)
            reader.sample(now=t)

        tick()
        state["locked"] = True
        for _ in range(4):
            tick()                                   # 2 Minuten gesperrt
        state["locked"] = False
        state["procs"] = [(9, (t + timedelta(seconds=5)).timestamp(), "ssh.exe", ["ssh", "admin@fw01"])]
        for _ in range(4):
            tick()
        state["procs"] = []
        tick()
        rows = [(e["type"], e["customer_name"]) for e in reader.entries()]
        same("Einträge", sorted(rows), sorted([("PC gesperrt", "gesperrt"), ("SSH-Verbindung", "fw01"),
                                               ("Netzwerk", "Kunde-Gast")]))
        # Neu gestartet: alles kommt aus dem Archiv
        again = ls.LocalReader({}, os.path.join(tmp, "lokal_spuren.json"), funcs={"threaded": False})
        same("Archiv", len(again.entries()), 3)
        again.config["wlan_enabled"] = False
        same("Netzwerk aus", [e["type"] for e in again.entries() if e["type"] == "Netzwerk"], [])


def test_keine_nachfrage_fuer_spuren(same):
    from timeline_only import row_kind
    same("Zeilen", [row_kind({"type": t}) for t in (ls.LOCKED, ls.WLAN_TYPE, ls.FILE_TYPE, ls.BROWSER_TYPE)],
         ["pcstate", "wlan", "files", "files"])
    same("SSH bleibt Verbindung", row_kind({"type": "SSH-Verbindung"}), None)


def test_netzwerkprofile(same):
    text = "ITM.local\tEthernet 2\tDomainAuthenticated\r\nKunde-Gast\tWLAN\tPublic\r\nfirma.vpn\tFortinet SSL VPN\t1\r\n"
    nets = ls.parse_profiles(text)
    same("Profile", [(n["name"], n["wireless"], n["category"]) for n in nets],
         [("ITM.local", False, "Domäne"), ("Kunde-Gast", True, "öffentlich"), ("firma.vpn", False, "privat")])
    same("ohne VPN", [n["name"] for n in ls.location_networks(nets, ls.DEFAULT_NETWORK_IGNORE)],
         ["ITM.local", "Kunde-Gast"])
    import customers
    config = {"customers": [{"name": "Müller GmbH", "traces": [{"kind": "net", "value": "kunde-gast"}]}]}
    same("Kunde zum Netz", customers.customer_for({"type": "Netzwerk", "customer_name": "Kunde-Gast"}, config),
         "Müller GmbH")
