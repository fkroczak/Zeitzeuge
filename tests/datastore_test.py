"""Verschlüsselte Datenbank (datastore.py, datakey.py): Schema, Schlüssel, Migration, Sperren."""
import glob
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import datakey  # noqa: E402
import datastore  # noqa: E402
import safe_io  # noqa: E402

D = "2026-10-20"
SECRET = "Müller Kundenname GmbH"


def new_store(folder=None):
    folder = folder or tempfile.mkdtemp()
    return datastore.Store(os.path.join(folder, "zeitzeuge.db"), folder).unlock()


def file_bytes(path):
    data = b""
    for p in glob.glob(path + "*"):  # auch -wal und -shm
        with open(p, "rb") as f:
            data += f.read()
    return data


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---------------------------------------------------------------- Schlüssel und Format

def test_ziffernschluessel_format_und_tippfehler():
    code = datakey.new_code()
    blocks = code.split("-")
    assert len(blocks) == 8 and all(len(b) == 6 and int(b) % 11 == 0 for b in blocks)
    assert datakey.normalize_code(" " + code.replace("-", " ") + "\n") == code
    wrong = blocks[:]
    wrong[2] = f"{(int(wrong[2]) + 1) % 1000000:06d}"
    with pytest.raises(datakey.BadCode, match="Block 3"):
        datakey.normalize_code("-".join(wrong))
    with pytest.raises(datakey.BadCode, match="48 Ziffern"):
        datakey.normalize_code(code[:-3])
    with pytest.raises(datakey.BadCode):
        datakey.normalize_code(code + "x")
    assert len({datakey.new_code() for _ in range(50)}) == 50


def test_verschluesselung_bindet_an_den_platz():
    c = datakey.Cipher(datakey.new_key())
    for size in (10, 5000):  # klein ungepackt, groß gepackt
        data = os.urandom(size // 2).hex().encode()[:size]
        blob = c.encrypt(data, b"docs|anrufe|" + D.encode())
        assert c.decrypt(blob, b"docs|anrufe|" + D.encode()) == data
        with pytest.raises(datakey.WrongKey):  # anderer Tag
            c.decrypt(blob, b"docs|anrufe|2026-10-21")
        broken = bytearray(blob)
        broken[-1] ^= 1
        with pytest.raises(datakey.WrongKey):
            c.decrypt(bytes(broken), b"docs|anrufe|" + D.encode())
    with pytest.raises(datakey.WrongKey):
        datakey.Cipher(datakey.new_key()).decrypt(c.encrypt(b"x"), b"")


def test_schema_und_nichts_im_klartext():
    store = new_store()
    store.put("anrufe", D, [{"start": f"{D} 09:00:00", "name": SECRET, "number": "0301 4711"}])
    store.append("aktivitaet", D, {"start": f"{D} 09:00:00", "end": f"{D} 09:05:00",
                                   "app": "outlook.exe", "title": f"Mail von {SECRET}"})
    store.put("teamviewer_names", "", {"123456789": SECRET})
    raw = file_bytes(store.path)
    for text in (SECRET, "0301 4711", "outlook.exe", "123456789"):
        assert text.encode("utf-8") not in raw, f"{text} steht im Klartext in der Datei"
    con = sqlite3.connect(store.path)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"docs", "rows", "meta", "key_slots"} <= tables
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert con.execute("SELECT name, day FROM docs WHERE name = 'anrufe'").fetchall() == [("anrufe", D)]
    con.close()
    assert store.get("anrufe", D)[0]["name"] == SECRET
    assert store.rows("aktivitaet", D)[0]["title"].endswith(SECRET)


def test_vertauschte_zeilen_werden_erkannt():
    store = new_store()
    store.put("taetigkeiten", D, {"items": [1]})
    store.put("taetigkeiten", "2026-10-21", {"items": [2]})
    con = sqlite3.connect(store.path)
    blob = con.execute("SELECT data FROM docs WHERE day = ?", (D,)).fetchone()[0]
    con.execute("UPDATE docs SET data = ? WHERE day = '2026-10-21'", (blob,))
    con.commit()
    con.close()
    safe_io.take_problems()
    assert store.get("taetigkeiten", "2026-10-21") is None  # nicht der Inhalt eines anderen Tages
    assert any("beschädigt" in p for p in safe_io.take_problems())


# ---------------------------------------------------------------- Schlüsselfächer

def test_faecher_wiederherstellung_und_neuer_benutzer(monkeypatch):
    store = new_store()
    store.put("anrufe", D, [{"name": SECRET}])
    assert not store.has_recovery()
    code = store.new_recovery_code()
    assert store.has_recovery()
    store.close()

    # Gleicher Benutzer: öffnet ohne Abfrage
    again = datastore.Store(store.path).unlock()
    assert again.get("anrufe", D)[0]["name"] == SECRET
    again.close()

    # Anderer Windows-Benutzer / neuer PC: kein Fach passt
    real_unwrap = datakey.auto_unwrap

    def other_user(kind, blob):
        raise datakey.WrongKey("anderer Benutzer")
    monkeypatch.setattr(datakey, "auto_unwrap", other_user)
    before = sha(store.path)
    locked = datastore.Store(store.path)
    with pytest.raises(datastore.Locked):
        locked.unlock()
    with pytest.raises(datastore.Locked):
        locked.get("anrufe", D)
    with pytest.raises(datakey.WrongKey):
        locked.unlock_with_code(datakey.new_code())
    with pytest.raises(datakey.BadCode):
        locked.unlock_with_code(code[:-1] + ("1" if code[-1] != "1" else "2"))
    locked.close()
    assert sha(store.path) == before, "gesperrt: Datei darf sich nicht ändern"

    opened = datastore.Store(store.path).unlock_with_code(code.replace("-", " "))
    assert opened.get("anrufe", D)[0]["name"] == SECRET
    slots = opened.protection()["auto"]
    assert len(slots) == 2, "neues Fach für diesen Benutzer angelegt"
    opened.close()

    # Neues Fach wirkt beim nächsten Start (hier: das zuletzt angelegte passt)
    calls = {"n": 0}

    def newest_only(kind, blob):
        calls["n"] += 1
        if calls["n"] == 1:
            raise datakey.WrongKey("altes Fach")
        return real_unwrap(kind, blob)
    monkeypatch.setattr(datakey, "auto_unwrap", newest_only)
    assert datastore.Store(store.path).unlock().get("anrufe", D)


def test_neuer_wiederherstellungsschluessel_macht_alten_ungueltig(monkeypatch):
    store = new_store()
    old = store.new_recovery_code()
    new = store.new_recovery_code()
    assert old != new and len(store.protection()["auto"]) == 1
    store.close()
    monkeypatch.setattr(datakey, "auto_unwrap", lambda k, b: (_ for _ in ()).throw(datakey.WrongKey("x")))
    with pytest.raises(datakey.WrongKey):
        datastore.Store(store.path).unlock_with_code(old)
    assert datastore.Store(store.path).unlock_with_code(new).unlocked


def test_ohne_faecher_nie_neu_anlegen():
    store = new_store()
    store.put("anrufe", D, [{"name": SECRET}])
    store._write_tx(lambda c: c.execute("DELETE FROM key_slots"))
    store.close()
    with pytest.raises(datastore.Locked):
        datastore.Store(store.path).unlock()
    con = sqlite3.connect(store.path)
    assert con.execute("SELECT COUNT(*) FROM docs").fetchone()[0] == 1, "Daten noch da"
    assert con.execute("SELECT COUNT(*) FROM key_slots").fetchone()[0] == 0, "kein neues Fach"
    con.close()


def test_kaputte_datei_bleibt_unveraendert():
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "zeitzeuge.db")
    with open(path, "wb") as f:
        f.write(b"das ist keine Datenbank" * 100)
    before = sha(path)
    with pytest.raises(datastore.Busy):
        datastore.Store(path).unlock()
    assert sha(path) == before


# ---------------------------------------------------------------- Threads, Sicherung

def test_mehrere_threads_schreiben():
    store = new_store()
    errors = []

    def writer(n):
        try:
            for i in range(100):
                store.append("aktivitaet", D, {"t": n, "i": i})
                if i % 10 == 0:
                    store.put("vpn_verbindungen", "", {"n": n, "i": i})
                    store.get("vpn_verbindungen")
        except Exception as e:  # pragma: no cover - nur bei Fehler
            errors.append(e)
    threads = [threading.Thread(target=writer, args=(n,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    rows = store.rows("aktivitaet", D)
    assert len(rows) == 500 and len({(r["t"], r["i"]) for r in rows}) == 500


def test_sicherung_ist_vollstaendig_und_verschluesselt():
    store = new_store()
    store.put("anrufe", D, [{"name": SECRET}])
    store.append("aktivitaet", D, {"title": SECRET})
    target = os.path.join(tempfile.mkdtemp(), "zeitzeuge-sicherung.db")
    assert store.backup(target)
    assert not os.path.exists(target + "-wal") and not os.path.exists(target + ".tmp")
    assert SECRET.encode() not in file_bytes(target)
    copy = datastore.Store(target).unlock()  # gleicher Benutzer: öffnet ohne Abfrage
    assert copy.get("anrufe", D)[0]["name"] == SECRET and copy.rows("aktivitaet", D)


def test_busy_wird_gemeldet_statt_absturz():
    store = new_store()
    other = sqlite3.connect(store.path, timeout=0)
    other.execute("BEGIN EXCLUSIVE")  # anderer Prozess hält die Datei
    old = datastore.RETRIES, datastore.RETRY_WAIT
    datastore.RETRIES, datastore.RETRY_WAIT = 1, 0.01
    store._conn.execute("PRAGMA busy_timeout = 50")
    try:
        with pytest.raises(datastore.Busy):
            store.put("anrufe", D, [])
    finally:
        datastore.RETRIES, datastore.RETRY_WAIT = old
        other.execute("ROLLBACK")
        other.close()
    store.put("anrufe", D, [{"ok": 1}])
    assert store.get("anrufe", D) == [{"ok": 1}]


# ---------------------------------------------------------------- Migration

def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if path.endswith(".jsonl"):
            f.writelines(json.dumps(line, ensure_ascii=False) + "\n" for line in data)
        else:
            json.dump(data, f, ensure_ascii=False)


def legacy_folder():
    """Datenordner wie vor der Datenbank, alle Ablagen."""
    folder = tempfile.mkdtemp()
    j = lambda *p: os.path.join(folder, *p)  # noqa: E731
    write(j("anrufe.json"), [{"start": f"{D} 09:00:00", "number": "0301", "name": SECRET, "duration_s": 60},
                             {"start": f"{D} 10:00:00", "number": "0302", "duration_s": 30},
                             {"start": "2026-10-21 08:00:00", "number": "0303", "duration_s": 90}])
    write(j("anrufe_stand.json"), {"vollstaendig_ab": "2026-10-01", "version": 2})
    write(j("vpn_verbindungen.json"), {"connections": [], "adapter": [], "names": {"1": SECRET}})
    write(j("personalzeiten.json"), {D: {"zeiten": [{"start": f"{D} 08:00:00", "end": f"{D} 16:00:00"}]}})
    write(j("m42_buchungen.json"), {"tage": {D: [{"start": f"{D} 09:00:00", "end": f"{D} 10:00:00",
                                                  "customer": SECRET}], "2026-10-21": []},
                                    "gelesen": {D: "2026-10-21 07:00"}})
    write(j("uebernommen.json"), {"pcs": {"ARBEITS-PC": {"tage": {D: {"pc": []}}, "erstellt": {}}}})
    write(j("aktivitaet", f"{D}.jsonl"), [{"start": f"{D} 09:00:00", "end": f"{D} 09:05:00",
                                           "app": "outlook.exe", "title": SECRET}] * 3)
    write(j("aktivitaet", "2026-10-21.jsonl"), [{"start": "2026-10-21 09:00:00", "end": "2026-10-21 09:05:00",
                                                  "app": "excel.exe", "title": "x"}])
    write(j("taetigkeiten", f"{D}.json"), {"items": [{"id": "a", "start": f"{D} 09:00:00",
                                                      "end": f"{D} 09:30:00", "customer": SECRET}],
                                           "ignored": ["k"]})
    write(j("ki_vorschlaege", f"{D}.json"), {"items": [{"von": "09:00", "bis": "09:30"}], "input_hash": "h"})
    return folder


def check_migrated(folder):
    """Alles über die bisherigen Schnittstellen lesbar, alte Dateien in alt-<Datum>/."""
    from activity_tracker import read_segments
    from ai_classifier import AiStore
    from call_import import load_call_suggestions, load_calls
    from journal import Journal
    from m42_data import load_store
    from transfer import ImportStore
    from vpn_reader import VpnReader
    import itm_reader

    j = lambda *p: os.path.join(folder, *p)  # noqa: E731
    assert len(load_calls(j("anrufe.json"))) == 3
    assert [c["customer_name"] for c in load_call_suggestions(j("anrufe.json"), D)][0].startswith(SECRET)
    assert len(read_segments(j("aktivitaet"), D)) == 3 and len(read_segments(j("aktivitaet"), "2026-10-21")) == 1
    assert Journal(j("taetigkeiten")).load(D)["items"][0]["customer"] == SECRET
    assert AiStore(j("ki_vorschlaege")).is_current(D, "h")
    assert itm_reader.load_days(j("personalzeiten.json"))[D]["zeiten"]
    days, read = load_store(j("m42_buchungen.json"))
    assert days[D][0]["customer"] == SECRET and days["2026-10-21"] == [] and read[D] == "2026-10-21 07:00"
    assert ImportStore(j("uebernommen.json")).pcs["ARBEITS-PC"]["tage"][D] == {"pc": []}
    assert VpnReader(j("vpn_verbindungen.json"), [j("fehlt")])._archive()["names"] == {"1": SECRET}
    store = datastore.store_for_dir(folder)
    assert store.get("anrufe_stand")["vollstaendig_ab"] == "2026-10-01"
    left = sorted(n for n in os.listdir(folder) if not n.startswith("zeitzeuge.db"))
    assert left == [f"alt-{date.today().isoformat()}"], f"übrig im Datenordner: {left}"
    alt = j(left[0])
    assert os.path.exists(os.path.join(alt, "anrufe.json"))
    assert os.path.exists(os.path.join(alt, "aktivitaet", f"{D}.jsonl"))


def test_migration_aller_ablagen():
    folder = legacy_folder()
    store = datastore.register(new_store(folder))
    try:
        total = datastore.migrate_all(store)
        assert total >= 3 + 4 + 1 + 1, total
        check_migrated(folder)
        stats = store.stats()
        assert stats["docs"]["anrufe"] == 2 and stats["rows"]["aktivitaet"] == 4
        # Doppelter Start: nichts doppelt
        assert datastore.migrate_all(store) == 0
        assert store.stats() == stats
    finally:
        datastore.unregister(folder)


def test_migration_abbruch_vor_dem_verschieben():
    """Absturz nach dem Speichern, bevor die Datei verschoben ist: kein doppeltes Einlesen."""
    folder = legacy_folder()
    store = new_store(folder)

    def crash(path):
        raise SystemExit("Absturz")
    store._move_old = crash
    with pytest.raises(SystemExit):
        datastore.migrate_all(store)
    store.close()
    store = datastore.register(new_store(folder))  # nächster Start
    try:
        datastore.migrate_all(store)
        check_migrated(folder)
        assert store.stats()["docs"]["anrufe"] == 2
    finally:
        datastore.unregister(folder)


def test_migration_abbruch_mitten_in_der_transaktion():
    """Absturz beim Schreiben: Transaktion fällt weg, nichts halb, nächster Start übernimmt alles."""
    folder = legacy_folder()
    store = new_store(folder)
    real = store._enc
    count = {"n": 0}

    def enc(*args):
        count["n"] += 1
        if count["n"] == 5:
            raise SystemExit("Absturz")
        return real(*args)
    store._enc = enc
    with pytest.raises(SystemExit):
        datastore.migrate_all(store)
    store.close()
    store = datastore.register(new_store(folder))
    try:
        datastore.migrate_all(store)
        check_migrated(folder)
        assert store.stats()["rows"]["aktivitaet"] == 4
    finally:
        datastore.unregister(folder)


def test_migration_gesperrte_datei(monkeypatch):
    """Gesperrte alte Datei (OneDrive) bleibt liegen, der Rest wird übernommen, später sie auch."""
    folder = legacy_folder()
    real = safe_io.read_json

    def locked(path, *a, **k):
        if path.endswith("personalzeiten.json"):
            raise safe_io.FileLocked("gesperrt")
        return real(path, *a, **k)
    monkeypatch.setattr(safe_io, "read_json", locked)
    store = datastore.register(new_store(folder))
    try:
        datastore.migrate_all(store)
        assert os.path.exists(os.path.join(folder, "personalzeiten.json"))
        assert not os.path.exists(os.path.join(folder, "anrufe.json"))
        monkeypatch.setattr(safe_io, "read_json", real)
        datastore.migrate_all(store)
        check_migrated(folder)
    finally:
        datastore.unregister(folder)


def test_migration_neuere_daten_in_der_db_bleiben():
    folder = tempfile.mkdtemp()
    store = datastore.register(new_store(folder))
    try:
        store.put("taetigkeiten", D, {"items": ["neu"], "ignored": []})
        write(os.path.join(folder, "taetigkeiten", f"{D}.json"), {"items": ["alt"], "ignored": []})
        datastore.migrate_all(store)
        assert store.get("taetigkeiten", D)["items"] == ["neu"]
        assert glob.glob(os.path.join(folder, "alt-*", "taetigkeiten", f"{D}.json")), "alte Datei aufgehoben"
    finally:
        datastore.unregister(folder)


def test_kaputte_alte_datei_wird_beiseitegelegt():
    folder = tempfile.mkdtemp()
    with open(os.path.join(folder, "anrufe.json"), "w", encoding="utf-8") as f:
        f.write('[{"start": "2026-10')
    store = datastore.register(new_store(folder))
    try:
        datastore.migrate_all(store)
        assert glob.glob(os.path.join(folder, "anrufe.json.defekt-*"))
        assert store.days("anrufe") == []
    finally:
        datastore.unregister(folder)


# ---------------------------------------------------------------- PIN beim Start (Schritt 3)

PIN = "Grüne Wiese 42"


def test_pin_noetig_auch_mit_windows_anmeldung(monkeypatch):
    """Mit PIN reicht die Windows-Anmeldung (DPAPI, auch der Domänen-Sicherungsschlüssel) nicht."""
    store = new_store()
    store.put("anrufe", D, [{"name": SECRET}])
    with pytest.raises(ValueError, match="Wiederherstellungsschlüssel"):
        store.enable_pin(PIN)  # ohne Wiederherstellungsschlüssel wäre eine vergessene PIN das Ende
    code = store.new_recovery_code()
    with pytest.raises(datakey.BadPin):
        store.enable_pin("123")
    store.enable_pin(PIN)
    kinds = [k for k, _l, _c in store.protection()["auto"]]
    assert kinds == [datakey.pin_kind()], "kein Fach ohne PIN mehr übrig"
    store.close()

    # „Admin“: kann jedes DPAPI-Fach öffnen, kennt aber die PIN nicht
    s = datastore.Store(store.path)
    with pytest.raises(datastore.NeedPin):
        s.unlock()
    with pytest.raises(datakey.WrongKey):
        s.unlock_with_pin("falsche PIN 1")
    assert not s.unlocked
    assert s.unlock_with_pin(PIN).get("anrufe", D)[0]["name"] == SECRET
    s.close()

    # Wiederherstellungsschlüssel geht weiter; mit PIN legt er kein Fach ohne PIN an
    s = datastore.Store(store.path).unlock_with_code(code)
    assert [k for k, _l, _c in s.protection()["auto"]] == [datakey.pin_kind()]
    s.set_pin("Neue PIN 2026")
    s.close()
    with pytest.raises(datakey.WrongKey):
        datastore.Store(store.path).unlock_with_pin(PIN)
    assert datastore.Store(store.path).unlock_with_pin("Neue PIN 2026").unlocked


def test_pin_fehlversuche_bremsen(monkeypatch):
    store = new_store()
    store.new_recovery_code()
    store.enable_pin(PIN)
    store.close()
    s = datastore.Store(store.path)
    for _ in range(store.PIN_FREE_TRIES - 1):
        with pytest.raises(datakey.WrongKey, match="stimmt nicht"):
            s.unlock_with_pin("falsch falsch")
    assert s.pin_wait() == 0
    with pytest.raises(datakey.WrongKey, match="Sekunden"):
        s.unlock_with_pin("falsch falsch")
    assert s.pin_wait() > 0
    with pytest.raises(datakey.WrongKey, match="warte"):
        s.unlock_with_pin(PIN)  # auch die richtige PIN erst nach der Wartezeit
    real = datastore.time.time
    monkeypatch.setattr(datastore.time, "time", lambda: real() + 3600)
    assert s.unlock_with_pin(PIN).unlocked
    assert s.pin_wait() == 0, "nach Erfolg keine Wartezeit mehr"


def test_pin_anderes_konto_braucht_wiederherstellung(monkeypatch):
    store = new_store()
    code = store.new_recovery_code()
    store.enable_pin(PIN)
    store.close()
    monkeypatch.setattr(datakey, "auto_unwrap",
                        lambda k, b: (_ for _ in ()).throw(datakey.WrongKey("anderes Konto")))
    s = datastore.Store(store.path)
    with pytest.raises(datastore.NeedPin):
        s.unlock()
    with pytest.raises(datastore.Locked) as info:
        s.unlock_with_pin(PIN)
    assert not isinstance(info.value, datastore.NeedPin) and "keine PIN" in str(info.value)
    assert s.unlock_with_code(code).unlocked


def test_pin_ausschalten():
    store = new_store()
    store.new_recovery_code()
    store.enable_pin(PIN)
    store.disable_pin()
    assert not store.pin_required()
    store.close()
    assert datastore.Store(store.path).unlock().unlocked, "wieder ohne Abfrage"
