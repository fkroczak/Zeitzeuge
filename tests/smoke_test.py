"""Schnelltest für den Build (läuft auf GitHub unter Windows)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import activity_tracker  # noqa: E402
from call_import import load_call_suggestions, load_calls, merge_calls  # noqa: E402


def test_fensterabfrage(tmp_path):
    """Windows-API-Aufrufe dürfen nicht abstürzen."""
    print("Aktives Fenster:", activity_tracker.foreground_window())
    print("Leerlauf (s):", activity_tracker.idle_seconds())
    tracker = activity_tracker.ActivityTracker(str(tmp_path))
    tracker.sample()
    tracker.stop()


def test_anrufe_zusammenfuehren(tmp_path):
    """Anrufe zusammenführen: keine Doppelten, später erkannter Name wird gespeichert."""
    calls_file = os.path.join(str(tmp_path), "anrufe.json")
    call = {"start": "2026-10-20 09:15:00", "duration_s": 120, "name": "0251123", "number": "0251123"}
    assert merge_calls(calls_file, [call]) == 1
    assert merge_calls(calls_file, [call]) == 0
    assert merge_calls(calls_file, [dict(call, name="ABC GmbH")]) == 0
    saved = load_calls(calls_file)
    assert [c["name"] for c in saved] == ["ABC GmbH"], saved
    assert len(load_call_suggestions(calls_file, "2026-10-20")) == 1
    assert load_call_suggestions(calls_file, "2026-10-21") == []


def test_versuch_und_gespraech_in_derselben_minute(tmp_path):
    """Nicht angenommener Versuch darf das Gespräch derselben Minute nicht überschreiben."""
    calls_file = os.path.join(str(tmp_path), "anrufe.json")
    talk = {"start": "2026-10-23 10:58:00", "duration_s": 360, "name": "M B", "number": "0492"}
    attempt = dict(talk, duration_s=0, direction="Verpasst")
    assert merge_calls(calls_file, [talk, attempt]) == 2  # 3CX: neuester zuerst
    assert merge_calls(calls_file, [talk, attempt]) == 0
    suggestions = load_call_suggestions(calls_file, "2026-10-23")
    assert len(suggestions) == 1 and "Dauer 6:00" in suggestions[0]["details"], suggestions


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
