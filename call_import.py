"""
Anrufliste von Zeitzeuge (Ablage "anrufe" in der Datenbank, je Tag ein Eintrag).

Der 3CX-Leser (pbx_reader.py) übernimmt neue Anrufe mit merge_calls; die
Timeline holt sich die Anrufe eines Tages mit load_call_suggestions.
"""

import os
import threading
from datetime import datetime, timedelta

import datastore
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


def _store(path):
    return datastore.locate(path, "calls")


def load_calls(path, raise_locked=False):
    """Alle gespeicherten Anrufe (aus der Datenbank, je Tag ein Eintrag).
    Einzelne kaputte Einträge werden übersprungen statt alles zu verwerfen."""
    try:
        store, name = _store(path)
        days = store.all(name)
    except datastore.Busy as e:
        if raise_locked:
            raise safe_io.FileLocked(str(e)) from e
        return []
    data = [c for day in days.values() if isinstance(day, list) for c in day]
    calls = [c for c in data if isinstance(c, dict) and _valid(c)]
    if len(calls) != len(data):
        safe_io.log(f"{os.path.basename(path)}: {len(data) - len(calls)} unlesbare Einträge übersprungen")
    return sorted(calls, key=lambda c: c["start"])


def _load_day(store, name, day):
    data = store.get(name, day) or []
    return [c for c in data if isinstance(c, dict) and _valid(c)]


def merge_calls(path, new_calls):
    """Neue Anrufe übernehmen. Gibt Anzahl neuer Einträge zurück."""
    with _lock:
        try:
            store, name = _store(path)
            by_day = {}
            for c in new_calls:
                if isinstance(c, dict) and _valid(c):
                    by_day.setdefault(c["start"][:10], []).append(c)
            added = 0
            changed = {}
            for day, items in by_day.items():
                calls = {_key(c): c for c in _load_day(store, name, day)}
                dirty = False
                for c in items:
                    k = _key(c)
                    if k not in calls:
                        added += 1
                    if calls.get(k) != c:
                        dirty = True
                    calls[k] = c  # neuere Daten (z. B. Name aus CRM) gewinnen
                if dirty:
                    changed[day] = sorted(calls.values(), key=lambda c: c["start"])
            if changed:
                store.put_many(name, changed)
            return added
        except datastore.Busy as e:
            # Beim nächsten Lesen kommen die Anrufe wieder
            safe_io.report(f"Anrufe konnten nicht gespeichert werden: {e}")
            return 0


def load_call_suggestions(path, date_str, ignore_missed=True, min_seconds=0):
    """Anrufe eines Tages (YYYY-MM-DD) als Timeline-Vorschläge."""
    try:
        store, name = _store(path)
        calls = _load_day(store, name, date_str)
    except (datastore.Busy, datastore.Locked):
        return []

    result = []
    for c in calls:
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
