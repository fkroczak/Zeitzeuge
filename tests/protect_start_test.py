"""Start mit der Datenbank (main_timeline.open_store): Sicherung, gesperrte Daten, Kundennamen."""
import hashlib
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import datakey  # noqa: E402
import datastore  # noqa: E402
import main_timeline as mt  # noqa: E402

D = "2026-10-20"


@pytest.fixture
def paths(monkeypatch):
    """Datenordner (wie OneDrive-Dokumente) und lokaler Ordner getrennt, wie unter Windows."""
    data, local = tempfile.mkdtemp(), tempfile.mkdtemp()
    monkeypatch.setattr(mt, "DATA_DIR", data)
    monkeypatch.setattr(mt, "DB_FILE", os.path.join(local, "zeitzeuge.db"))
    monkeypatch.setattr(mt, "BACKUP_FILE", os.path.join(data, "zeitzeuge-sicherung.db"))
    monkeypatch.setattr(mt, "CONFIG_FILE", os.path.join(data, "zeitzeuge_config.json"))
    yield data, local
    datastore.unregister(data)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_sicherung_und_wiederherstellung(paths):
    data, local = paths
    store = mt.open_store()
    store.put("anrufe", D, [{"name": "Müller"}])
    assert mt.backup_store() and os.path.exists(mt.BACKUP_FILE)
    assert not mt.backup_store(), "ohne Änderung keine neue Sicherung"
    datastore.unregister(data)
    os.remove(mt.DB_FILE)  # neuer PC / lokale Daten weg
    for ext in ("-wal", "-shm"):
        if os.path.exists(mt.DB_FILE + ext):
            os.remove(mt.DB_FILE + ext)
    store = mt.open_store()
    assert store.get("anrufe", D) == [{"name": "Müller"}], "aus der Sicherung im Datenordner"
    assert sorted(os.listdir(data)) == ["zeitzeuge-sicherung.db"], "keine WAL-Dateien im Datenordner"


def test_gesperrt_nie_ueberschreiben(paths, monkeypatch):
    data, _local = paths
    store = mt.open_store()
    store.put("anrufe", D, [{"name": "Müller"}])
    code = store.new_recovery_code()
    datastore.unregister(data)
    before = sha(mt.DB_FILE)
    monkeypatch.setattr(datakey, "auto_unwrap",
                        lambda k, b: (_ for _ in ()).throw(datakey.WrongKey("anderes Konto")))
    asked = []
    with pytest.raises(mt.StoreLocked):
        mt.open_store(ask=lambda s: asked.append(s) or False)  # Abbrechen im Dialog
    assert asked and sha(mt.DB_FILE) == before and not datastore.registered(data)
    store = mt.open_store(ask=lambda s: bool(s.unlock_with_code(code)))
    assert store.get("anrufe", D) == [{"name": "Müller"}]


def test_kundennamen_wandern_aus_der_config(paths):
    data, _local = paths
    with open(mt.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"teamviewer_names": {"123456789": "Müller GmbH"}, "dark_mode": True}, f)
    store = mt.open_store()
    cfg = mt.load_config_with_defaults()
    assert cfg["teamviewer_names"] == {"123456789": "Müller GmbH"} and cfg["dark_mode"]
    with open(mt.CONFIG_FILE, encoding="utf-8") as f:
        text = f.read()
    assert "Müller" not in text and "123456789" not in text, "Kundennamen nicht mehr in der Config"
    cfg["teamviewer_names"]["987"] = "Meier"
    mt.save_config(cfg)
    assert store.get("teamviewer_names") == {"123456789": "Müller GmbH", "987": "Meier"}
    with open(mt.CONFIG_FILE, encoding="utf-8") as f:
        assert "Meier" not in f.read()


def test_start_mit_pin(paths, monkeypatch):
    """Start mit PIN: ohne PIN bleibt alles zu, mit PIN geht es auf."""
    data, _local = paths
    store = mt.open_store()
    store.put("anrufe", D, [{"name": "Müller"}])
    store.new_recovery_code()
    store.enable_pin("Grüne Wiese 42")
    datastore.unregister(data)
    before = sha(mt.DB_FILE)
    with pytest.raises(mt.StoreLocked):
        mt.open_store(ask=lambda s: False)
    assert sha(mt.DB_FILE) == before
    seen = []
    store = mt.open_store(ask=lambda s: seen.append(type(s.unlock_with_pin("Grüne Wiese 42"))) or True)
    assert seen and store.get("anrufe", D) == [{"name": "Müller"}]
