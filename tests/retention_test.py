"""PC-Verlauf automatisch löschen (retention.py, datastore.delete_rows_before, ImportStore)."""
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config_defaults  # noqa: E402
import datastore  # noqa: E402
import retention  # noqa: E402
import transfer  # noqa: E402

TODAY = date(2026, 10, 26)


def new_store():
    folder = tempfile.mkdtemp()
    return datastore.Store(os.path.join(folder, "zeitzeuge.db"), folder).unlock()


def seg(day, n=0):
    return {"start": f"{day} 09:{n:02d}:00", "end": f"{day} 09:{n:02d}:30", "app": "outlook.exe",
            "title": f"Posteingang {n}"}


def fill(store):
    for day, count in (("2026-06-01", 3), ("2026-07-27", 2), ("2026-07-28", 2), ("2026-10-26", 1)):
        store.append_many("aktivitaet", [(day, seg(day, i)) for i in range(count)])
    store.append_many("andere", [("2026-01-01", {"x": 1})])
    store.put("taetigkeiten", "2026-06-01", {"items": [{"id": "a"}], "ignored": []})


def test_standard_aus_und_grenzen():
    config = config_defaults.default_config()
    assert retention.settings(config) == (False, 90)
    assert retention.settings({"pc_history_purge": True, "pc_history_days": 1}) == (True, 7)
    assert retention.settings({"pc_history_days": "x"}) == (False, 90)
    assert retention.settings({"pc_history_days": True}) == (False, 90)
    assert retention.cutoff(90, TODAY) == "2026-07-28"


def test_zeilen_vor_einem_tag_loeschen():
    store = new_store()
    fill(store)
    assert store.rows_before("aktivitaet", "2026-07-28") == (2, 5)
    assert store.delete_rows_before("aktivitaet", "2026-07-28") == 5
    assert store.row_days("aktivitaet") == ["2026-07-28", "2026-10-26"]
    assert store.rows("aktivitaet", "2026-07-28")[1]["title"] == "Posteingang 1"
    # Andere Ablagen und Dokumente bleiben
    assert store.row_count("andere") == 1
    assert store.get("taetigkeiten", "2026-06-01")["items"][0]["id"] == "a"
    assert store.delete_rows_before("aktivitaet", "2026-07-28") == 0
    store.close()


def test_in_schritten_aelteste_zuerst():
    store = new_store()
    fill(store)
    assert store.delete_rows_before("aktivitaet", "2026-07-28", limit=2) == 2
    assert store.row_count("aktivitaet", "2026-06-01") == 1  # die ältesten zuerst
    assert store.row_count("aktivitaet", "2026-07-27") == 2
    deleted, done = retention.purge_step(store, "aktivitaet", "2026-07-28", chunk=2)
    assert (deleted, done) == (2, False)
    deleted, done = retention.purge_step(store, "aktivitaet", "2026-07-28", chunk=2)
    assert (deleted, done) == (1, True)
    assert store.row_days("aktivitaet") == ["2026-07-28", "2026-10-26"]
    store.close()


def test_geloeschte_inhalte_ueberschrieben():
    """secure_delete: gelöschte Zeilen stehen danach nicht mehr (verschlüsselt) in der Datei."""
    store = new_store()
    store.append_many("aktivitaet", [("2026-01-01", seg("2026-01-01", i)) for i in range(50)])
    with store._lock:
        blobs = [b for (b,) in store._conn.execute("SELECT data FROM rows")]
    store.delete_rows_before("aktivitaet", "2026-02-01")
    store.close()  # Checkpoint: WAL in die Datei
    with open(store.path, "rb") as f:
        raw = f.read()
    left = [raw.find(b[:24]) for b in blobs if b[:24] in raw]
    if left:  # Angaben zur Ursache (nur bei Fehler)
        import sqlite3
        conn = sqlite3.connect(store.path)
        info = {p: conn.execute(f"PRAGMA {p}").fetchone()[0]
                for p in ("journal_mode", "page_size", "page_count", "freelist_count")}
        info["sqlite"] = sqlite3.sqlite_version
        info["wal"] = os.path.exists(store.path + "-wal")
        conn.close()
        raise AssertionError(f"{len(left)} von {len(blobs)} gelöschten Zeilen noch in der Datei, "
                             f"Seiten {sorted({o // info['page_size'] for o in left})}, {info}")


def test_uebernommener_pc_verlauf():
    path = os.path.join(tempfile.mkdtemp(), "uebernommen.json")
    imported = transfer.ImportStore(path)
    days = {"2026-06-01": {"pc": [seg("2026-06-01")],
                           "verbindungen": [{"start": "2026-06-01 09:00:00", "end": "2026-06-01 09:30:00",
                                             "type": "Telefonat"}]},
            "2026-10-20": {"pc": [seg("2026-10-20")]}}
    imported.add(transfer.make_export(days, pc="ARBEITS-PC"))
    assert imported.pc_days_before("2026-07-28") == ["2026-06-01"]
    assert imported.drop_pc_before("2026-07-28") == 1
    again = transfer.ImportStore(path)  # gespeichert
    assert again.segments("2026-06-01") == [] and len(again.connections("2026-06-01")) == 1
    assert again.segments("2026-10-20")
    assert again.drop_pc_before("2026-07-28") == 0


def test_vorschau_und_loeschen_gesamt():
    store = new_store()
    fill(store)
    datastore.register(store)  # ImportStore findet so dieselbe Datenbank
    path = os.path.join(store.data_dir, "uebernommen.json")
    imported = transfer.ImportStore(path)
    imported.add(transfer.make_export({"2026-05-01": {"pc": [seg("2026-05-01")]}}, pc="PAW"))
    before = retention.cutoff(90, TODAY)
    info = retention.affected(store, "aktivitaet", imported, before)
    assert info == {"days": ["2026-05-01", "2026-06-01", "2026-07-27"], "rows": 5, "imported_days": 1}
    text = retention.summary(info, before)
    assert text.startswith("3 Tage PC-Verlauf vor dem 28.07.2026 (ab 01.05.2026, 5 Fensterabschnitte")
    assert retention.purge(store, "aktivitaet", imported, before, chunk=2) == (5, 1)
    assert retention.affected(store, "aktivitaet", imported, before)["days"] == []
    assert retention.summary({"days": [], "rows": 0, "imported_days": 0}, before) == \
        "Vor dem 28.07.2026 liegt kein PC-Verlauf."
    datastore.unregister(store.data_dir)
    store.close()
