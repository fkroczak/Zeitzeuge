"""
Anrufliste von Zeitzeuge (anrufe.json).

Der 3CX-Leser (pbx_reader.py) übernimmt neue Anrufe mit merge_calls; die
Timeline holt sich die Anrufe eines Tages mit load_call_suggestions.
"""

import os
import threading
from datetime import datetime, timedelta

import safe_io

TIME_FMT = "%Y-%m-%d %H:%M:%S"
_lock = threading.Lock()

def _key(call):
    # Gleicher Anruf = gleiche Startminute + gleiche Nummer/Name + angenommen ja/nein.
    # 3CX listet oft einen nicht angenommenen Versuch und das eigentliche Gespräch in
    # derselben Minute; ohne "angenommen" überschrieb der Versuch das Gespräch.
    try:
        talked = int(call.get("duration_s") or 0) > 0
    except (TypeError, ValueError):
        talked = False
    return f"{call['start'][:16]}|{call.get('number') or call.get('name')}|{int(talked)}"


def _valid(call):
    try:
        datetime.strptime(call["start"], TIME_FMT)
        return True
    except (KeyError, TypeError, ValueError):
        return False


def load_calls(path, raise_locked=False):
    """Alle gespeicherten Anrufe. Eine kaputte Datei wird beiseitegelegt (safe_io),
    einzelne kaputte Einträge werden übersprungen statt alles zu verwerfen."""
    data = safe_io.read_json(path, [], expect=list, raise_locked=raise_locked)
    calls = [c for c in data if isinstance(c, dict) and _valid(c)]
    if len(calls) != len(data):
        safe_io.log(f"{os.path.basename(path)}: {len(data) - len(calls)} unlesbare Einträge übersprungen")
    return calls


def merge_calls(path, new_calls):
    """Neue Anrufe in die JSON-Datei übernehmen. Gibt Anzahl neuer Einträge zurück."""
    with _lock:
        try:
            calls = {_key(c): c for c in load_calls(path, raise_locked=True)}
        except safe_io.FileLocked:
            # Nicht mit nur den neuen Anrufen überschreiben: beim nächsten Lesen kommen sie wieder
            return 0

        added = changed = 0
        for c in new_calls:
            if not isinstance(c, dict) or not _valid(c):
                continue
            k = _key(c)
            if k not in calls:
                added += 1
            if calls.get(k) != c:
                changed += 1
            calls[k] = c  # neuere Daten (z. B. Name aus CRM) gewinnen

        if changed and not safe_io.write_json(path, sorted(calls.values(), key=lambda c: c["start"])):
            return 0
        return added


_file_cache = {"mtime": None, "calls": []}


def load_call_suggestions(path, date_str, ignore_missed=True, min_seconds=0):
    """Anrufe eines Tages (YYYY-MM-DD) aus anrufe.json als Timeline-Vorschläge."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    if _file_cache["mtime"] != mtime:
        try:
            with _lock:  # nicht mitten in merge_calls lesen
                _file_cache["calls"] = load_calls(path, raise_locked=True)
            _file_cache["mtime"] = mtime
        except safe_io.FileLocked:
            pass  # gesperrt: bisherigen Stand zeigen, beim nächsten Mal neu lesen

    result = []
    for c in _file_cache["calls"]:
        if not c.get("start", "").startswith(date_str):
            continue
        try:
            seconds = int(c.get("duration_s") or 0)
        except (TypeError, ValueError):
            seconds = 0
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
            "duration_s": seconds,  # echte Dauer (der Balken ist min. 1 min breit)
            "direction": c.get("direction", "Anruf"),  # für die Farbe (ein/aus/verpasst)
            "customer_name": customer,
            "details": ", ".join(details),
            "is_suggestion": True,
        })
    return result
