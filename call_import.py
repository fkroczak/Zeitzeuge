"""
Anrufliste von Zeitzeuge (anrufe.json).

Der 3CX-Leser (pbx_reader.py) übernimmt neue Anrufe mit merge_calls; die
Timeline holt sich die Anrufe eines Tages mit load_call_suggestions.
"""

import json
import os
import threading
from datetime import datetime, timedelta

TIME_FMT = "%Y-%m-%d %H:%M:%S"
_lock = threading.Lock()

def _key(call):
    # Gleicher Anruf = gleiche Startminute + gleiche Nummer/Name
    return f"{call['start'][:16]}|{call.get('number') or call.get('name')}"


def merge_calls(path, new_calls):
    """Neue Anrufe in die JSON-Datei übernehmen. Gibt Anzahl neuer Einträge zurück."""
    with _lock:
        calls = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    calls = {_key(c): c for c in json.load(f)}
            except Exception as e:
                print(f"anrufe.json nicht lesbar, wird neu angelegt: {e}")

        added = changed = 0
        for c in new_calls:
            try:
                datetime.strptime(c["start"], TIME_FMT)
            except (KeyError, TypeError, ValueError):
                continue
            k = _key(c)
            if k not in calls:
                added += 1
            if calls.get(k) != c:
                changed += 1
            calls[k] = c  # neuere Daten (z. B. Name aus CRM) gewinnen

        if changed:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(sorted(calls.values(), key=lambda c: c["start"]),
                          f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        return added


_file_cache = {"mtime": None, "calls": []}


def load_call_suggestions(path, date_str, ignore_missed=True, min_seconds=0):
    """Anrufe eines Tages (YYYY-MM-DD) aus anrufe.json als Timeline-Vorschläge."""
    if not os.path.exists(path):
        return []
    mtime = os.path.getmtime(path)
    if _file_cache["mtime"] != mtime:
        try:
            with open(path, "r", encoding="utf-8") as f:
                _file_cache["calls"] = json.load(f)
            _file_cache["mtime"] = mtime
        except Exception as e:
            print(f"Fehler beim Lesen von {path}: {e}")
            return []

    result = []
    for c in _file_cache["calls"]:
        if not c.get("start", "").startswith(date_str):
            continue
        seconds = int(c.get("duration_s") or 0)
        if seconds == 0 and ignore_missed:
            continue
        if seconds < min_seconds:
            continue
        start = datetime.strptime(c["start"], TIME_FMT)
        end = start + timedelta(seconds=max(seconds, 60))  # min. 1 min, damit sichtbar

        name = c.get("name") or c.get("number") or "Unbekannt"
        number = c.get("number") or ""
        customer = f"{name} ({number})" if number and number != name else name

        details = [f"{c.get('direction', 'Anruf')}, Dauer {seconds // 60}:{seconds % 60:02d}"]
        if c.get("via"):
            details.append(f"via {c['via']}")
        result.append({
            "start": start.strftime(TIME_FMT),
            "end": end.strftime(TIME_FMT),
            "type": "Telefonat",
            "direction": c.get("direction", "Anruf"),  # für die Farbe (ein/aus/verpasst)
            "customer_name": customer,
            "details": ", ".join(details),
            "is_suggestion": True,
        })
    return result
