"""SessionMGMT: sessions.log lesen, Doppelte mit mstsc/PuTTY/VPN abgleichen, Kunde aus dem Tresor."""
import os
from datetime import datetime, timedelta, timezone

import customers
import sessionmgmt_reader as sm

# Wie SessionMGMT es schreibt (Storage/SessionLog.cs)
LOG = r'''2026-11-11T08:18:53.616Z [INFO] launch session=3f9a1c host=192.168.1.26:3389 user=administrator type=1 vault="Müller GmbH" entry="DC01" platform=win32 method=embedded
2026-11-11T08:30:00.000Z [INFO] launch session=aa000001 host=fw.mueller.de:22 user=root type=77 vault="Müller GmbH" entry="Firewall \"alt\"" platform=win32 method=putty
2026-11-11T08:40:00.000Z [INFO] launch session=bb000002 host=portal.example.de:443 user= type=5 vault="Kunde Weber" entry="Portal" platform=win32 method=browser
2026-11-11T08:45:00.000Z [INFO] launch session=cc000003 host=10.0.0.9:3389 user=admin type=1 vault="Kunde Weber" entry="TS01" platform=win32 method=embedded
2026-11-11T08:45:20.000Z [INFO] end session=cc000003 host=10.0.0.9:3389 user=admin type=1 vault="Kunde Weber" entry="TS01" platform=win32 method=embedded start=2026-11-11T08:45:00.000Z duration=00:00:20 reason=failed
2026-11-11T08:50:00.000Z [INFO] end session=aa000001 host=fw.mueller.de:22 user=root type=77 vault="Müller GmbH" entry="Firewall \"alt\"" platform=win32 method=putty start=2026-11-11T08:30:00.000Z duration=00:20:00 reason=exited
2026-11-11T09:01:12.004Z [INFO] end session=3f9a1c host=192.168.1.26:3389 user=administrator type=1 vault="Müller GmbH" entry="DC01" platform=win32 method=embedded start=2026-11-11T08:18:53.616Z duration=00:42:18 reason=closed
2026-11-11T10:00:00.000Z [INFO] end session=dd000004 host=Kunde-Nord user=vpnuser type=20 vault="Kunde Nord" entry="VPN Nord" platform=win32 method=sccli start=2026-11-11T09:00:00.000Z duration=01:00:00 reason=disconnected
2026-11-11T11:00:00.000Z [INFO] launch session=ee000005 host=srv02:3389 user=admin type=1 vault="Kunde Weber" entry="SRV02" platform=win32 method=rdpfile
Unsinn ohne Zeit
'''.splitlines()


def local(h, mi, s=0):
    return datetime(2026, 11, 11, h, mi, s, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def fmt(when):
    return when.strftime("%Y-%m-%d %H:%M:%S")


def test_sitzungen_aus_dem_log():
    conns = sm.SessionMgmtParser().parse_file(LOG, 0)
    rows = [(c["start"], c["end"], c["type"], c["customer_name"], c.get("vault")) for c in conns]
    assert rows == [
        (fmt(local(8, 18, 53)), fmt(local(9, 1, 12)), "RDP-Verbindung", "DC01", "Müller GmbH"),
        (fmt(local(8, 30)), fmt(local(8, 50)), "SSH-Verbindung", 'Firewall "alt"', "Müller GmbH"),
        (fmt(local(8, 40)), fmt(local(8, 41)), "Website-Verbindung", "Portal", "Kunde Weber"),
        # fehlgeschlagene Verbindung (TS01) fehlt; VPN nur mit end-Zeile (Anfang abgeschnitten)
        (fmt(local(9, 0)), fmt(local(10, 0)), "VPN-Verbindung", "VPN Nord", "Kunde Nord"),
        (fmt(local(11, 0)), fmt(local(11, 1)), "RDP-Verbindung", "SRV02", "Kunde Weber"),
    ]
    assert "Kunde Müller GmbH" in conns[0]["details"] and "192.168.1.26" in conns[0]["details"]
    assert "eingebettet" in conns[0]["details"]
    assert "Ende unbekannt" in conns[-1]["details"]
    assert conns[0]["sm_host"] == "192.168.1.26"


def test_pfade_und_datenordner(tmp_path, monkeypatch):
    log = tmp_path / "sessions.log"
    log.write_text("\n".join(LOG[:1] + LOG[6:7]) + "\n", encoding="utf-8")
    monkeypatch.setattr(sm, "configured_log", lambda: None)
    parser = sm.SessionMgmtParser({"sessionmgmt_paths": [str(log), str(tmp_path / "fehlt.log")]})
    assert [c["customer_name"] for c in parser.parse_logs()] == ["DC01"]
    assert parser.files_read == 1

    # Datenordner aus SessionMGMT.json (Installer) kommt dazu
    install = tmp_path / "prog"
    install.mkdir()
    data = tmp_path / "daten"
    data.mkdir()
    (data / "sessions.log").write_text(LOG[1] + "\n" + LOG[5] + "\n", encoding="utf-8")
    (install / "SessionMGMT.json").write_text('{ "DataDir": "%s" }' % str(data).replace("\\", "\\\\"),
                                              encoding="utf-8")
    monkeypatch.undo()  # configured_log wieder echt
    monkeypatch.setattr(sm, "CONFIG_DIRS", (str(install),))
    assert sm.configured_log() == os.path.join(str(data), "sessions.log")
    names = sorted(c["customer_name"] for c in parser.parse_logs())
    assert names == ["DC01", 'Firewall "alt"']


def _conn(start, end, kind, name, **extra):
    return {"start": fmt(start), "end": fmt(end), "type": kind, "customer_name": name, **extra}


def test_doppelte_entfernen():
    conns = sm.SessionMgmtParser().parse_file(LOG, 0)
    mstsc = _conn(local(8, 19), local(9, 1), "RDP-Verbindung", "192.168.1.26", rdp_source="mstsc")
    putty = _conn(local(8, 30, 5), local(8, 49, 50), "SSH-Verbindung", "fw.mueller.de")
    other = _conn(local(8, 20), local(8, 25), "RDP-Verbindung", "anderer-host")
    sophos = _conn(local(9, 0, 30), local(9, 45), "VPN-Verbindung", "Kunde-Nord", vpn_source="sophos")
    srv02 = _conn(local(11, 0, 10), local(11, 30), "RDP-Verbindung", "srv02", rdp_source="mstsc")
    keep_sm, keep_other = sm.merge(conns, [mstsc, putty, other, sophos, srv02])

    assert [c["customer_name"] for c in keep_sm] == ["DC01", 'Firewall "alt"', "Portal"]
    # mstsc/PuTTY derselben Sitzung fallen weg; VPN aus Sophos bleibt (echte Tunnelzeiten),
    # SRV02 ohne Ende: die mstsc-Aufzeichnung bleibt und bekommt den Kunden
    assert keep_other == [other, sophos, srv02]
    assert sophos["vault"] == "Kunde Nord" and srv02["vault"] == "Kunde Weber"
    assert sm.merge([], [mstsc]) == ([], [mstsc])


def test_kunde_aus_dem_tresor():
    conns = sm.SessionMgmtParser().parse_file(LOG, 0)
    index = customers.Index([{"name": "Müller GmbH", "traces": []},
                             {"name": "Weber", "traces": [{"kind": "word", "value": "Weber"}]}])
    assert index.customer_for(conns[0]) == "Müller GmbH"   # Tresor = Kundenname
    assert index.match(conns[0])[1] == "vault"
    assert index.customer_for(conns[2]) == "Weber"          # Stichwort im Tresornamen
    assert index.customer_for(conns[3]) == ""
    assert customers.with_customer(conns[0], index) == "Müller GmbH · DC01"
    # Gemerkte Spur (RDM-Eintrag) geht vor
    index = customers.Index([{"name": "Müller GmbH", "traces": []},
                             {"name": "Anders", "traces": [{"kind": "rdm", "value": "DC01"}]}])
    assert index.customer_for(conns[0]) == "Anders"
