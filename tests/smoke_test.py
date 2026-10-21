"""Schnelltest für den Build (läuft auf GitHub unter Windows)."""
import os
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import activity_tracker
from browser_setup import build_userscript
from call_import import start_call_server, status

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
print("Smoke-Test ok")
