"""Schnelltest für den Build (läuft auf GitHub unter Windows)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import activity_tracker
import json

from call_import import load_call_suggestions, merge_calls

# Windows-API-Aufrufe dürfen nicht abstürzen
print("Aktives Fenster:", activity_tracker.foreground_window())
print("Leerlauf (s):", activity_tracker.idle_seconds())
tracker = activity_tracker.ActivityTracker(tempfile.mkdtemp())
tracker.sample()
tracker.stop()

# Anrufe zusammenführen: keine Doppelten, später erkannter Name wird gespeichert
calls_file = os.path.join(tempfile.mkdtemp(), "anrufe.json")
call = {"start": "2026-10-20 09:15:00", "duration_s": 120, "name": "0251123", "number": "0251123"}
assert merge_calls(calls_file, [call]) == 1
assert merge_calls(calls_file, [call]) == 0
assert merge_calls(calls_file, [dict(call, name="ABC GmbH")]) == 0
saved = json.load(open(calls_file, encoding="utf-8"))
assert [c["name"] for c in saved] == ["ABC GmbH"], saved
assert len(load_call_suggestions(calls_file, "2026-10-20")) == 1
assert load_call_suggestions(calls_file, "2026-10-21") == []

print("Smoke-Test ok")
