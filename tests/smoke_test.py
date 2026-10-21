"""Schnelltest für den Build (läuft auf GitHub unter Windows)."""
import os
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import activity_tracker
from browser_setup import build_userscript
import json

from call_import import load_call_suggestions, merge_calls, start_call_server, status

# Windows-API-Aufrufe dürfen nicht abstürzen
print("Aktives Fenster:", activity_tracker.foreground_window())
print("Leerlauf (s):", activity_tracker.idle_seconds())
tracker = activity_tracker.ActivityTracker(tempfile.mkdtemp())
tracker.sample()
tracker.stop()

# Server liefert das Skript aus und nimmt Meldungen an
template = open("zeitzeuge_anrufe.user.js", encoding="utf-8").read()
start_call_server(os.path.join(tempfile.mkdtemp(), "anrufe.json"), port=8799,
                  script_provider=lambda: build_userscript(template, "https://pbx.test:5001", 8799))
script = urllib.request.urlopen("http://127.0.0.1:8799/zeitzeuge_anrufe.user.js").read().decode()
assert "// @include      https://pbx.test:5001/*" in script
urllib.request.urlopen("http://127.0.0.1:8799/ping?v=test").read()
assert status["script_version"] == "test"
# Fremde Seiten dürfen keine Anrufe einschleusen (kein JSON -> abgelehnt)
fake = urllib.request.Request("http://127.0.0.1:8799/anrufe", data=b"[]",
                              headers={"Content-Type": "text/plain"})
try:
    urllib.request.urlopen(fake)
    raise AssertionError("Anfrage ohne JSON wurde angenommen")
except urllib.error.HTTPError as e:
    assert e.code == 415, e.code

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
