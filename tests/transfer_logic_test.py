"""Export/Import zwischen zwei PCs (transfer.py): Format, Zwischenablage, Ersetzen, Fehler."""
import os
import sys
import tempfile
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import transfer  # noqa: E402

D = "2026-10-20"
DAY = {
    "verbindungen": [{"start": f"{D} 09:00:00", "end": f"{D} 09:30:00", "type": "Telefonat",
                      "customer_name": "Müller"}],
    "pc": [{"start": f"{D} 09:00:00", "end": f"{D} 09:05:00", "app": "outlook.exe", "title": "Posteingang"}],
    "personalzeit": {"zeiten": [{"start": f"{D} 08:00:00", "end": f"{D} 16:00:00"}]},
    "m42": [],
    "taetigkeiten": {"items": [{"id": "a1", "start": f"{D} 09:00:00", "end": f"{D} 09:30:00",
                                "customer": "Müller", "text": "Drucker"}], "ignored": ["k"]},
}


def export(created="2026-10-21 08:00:00", days=None):
    return transfer.make_export(days if days is not None else {D: DAY, "2026-10-19": {}},
                                {"123": "Kunde"}, pc="ARBEITS-PC",
                                now=datetime.fromisoformat(created))


def test_roundtrip_file_and_clipboard():
    e = export()
    assert e["von"] == "2026-10-19" and e["bis"] == D and "2026-10-19" not in e["tage"]
    assert e["tage"][D]["m42"] == []  # gelesen, nichts gebucht: bleibt erhalten
    assert transfer.parse(transfer.to_bytes(e)) == e
    text = transfer.to_clipboard_text(e)
    wrapped = "\n".join(text[i:i + 76] for i in range(0, len(text), 76))  # Umbrüche beim Kopieren
    assert transfer.parse(wrapped) == e
    assert "1 Verbindungen" in transfer.summary(e) and "1 Tätigkeiten" in transfer.summary(e)


@pytest.mark.parametrize("bad", [b"", b"kaputt", "Hallo", "ZEITZEUGE-EXPORT:1:@@@",
                                 b'{"format": "anders"}'])
def test_rejects_garbage(bad):
    with pytest.raises(transfer.TransferError):
        transfer.parse(bad)


def test_store_merge_replace_and_own_pc():
    path = os.path.join(tempfile.mkdtemp(), "uebernommen.json")
    store = transfer.ImportStore(path)
    assert not store and store.m42(D) is None
    assert store.add(export()) == 1  # Tage ohne Daten zählen nicht
    store = transfer.ImportStore(path)  # aus der Datei
    conns = store.connections(D)
    assert conns[0]["source_pc"] == "ARBEITS-PC" and conns[0]["customer_name"] == "Müller"
    assert store.segments(D)[0]["app"] == "outlook.exe"
    assert store.personal(D)["zeiten"][0]["start"].endswith("08:00:00")
    assert store.m42(D) == [] and store.m42("2026-10-19") is None
    j = store.journal(D)
    assert j["items"][0]["von_pc"] == "ARBEITS-PC" and j["ignored"] == ["k"]
    assert store.teamviewer_names() == {"123": "Kunde"}

    # Älterer Export überschreibt nichts Neueres
    store.add(export("2026-10-20 08:00:00", {D: {"verbindungen": []}}))
    assert len(store.connections(D)) == 1
    # Neuerer Export ohne Daten für den Tag leert ihn
    store.add(export("2026-10-22 08:00:00", {D: {}, "2026-10-21": {"pc": DAY["pc"]}}))
    assert store.connections(D) == [] and store.segments("2026-10-21")

    with pytest.raises(transfer.TransferError):
        store.add(export(), own_pc="arbeits-pc")
    store.clear()
    assert not store and not os.path.exists(path)
