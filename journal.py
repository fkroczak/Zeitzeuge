"""
Tätigkeiten, die du selbst einträgst (nachträglich oder auf Nachfrage von Zeitzeuge).

Pro Tag eine Datei taetigkeiten/JJJJ-MM-TT.json:
    {"items": [{"id", "start", "end", "customer", "category", "text",
                "source", "created", "updated"}],
     "ignored": ["<Schlüssel eines Eintrags, nach dem nicht mehr gefragt wird>"]}

Dazu die Logik, welche erkannten Tätigkeiten noch nicht dokumentiert sind
(open_items). Daraus entstehen die Nachfrage-Fenster und die Zeile "Doku".
"""

import os
import re
import uuid
from datetime import datetime, timedelta

import safe_io

TIME_FMT = "%Y-%m-%d %H:%M:%S"
DOC_TYPE = "Dokumentiert"
OPEN_TYPE = "Undokumentiert"


def _t(text):
    return datetime.strptime(text, TIME_FMT)


def entry_key(entry):
    """Fester Schlüssel eines erkannten Eintrags (zum Ignorieren/Zurückstellen)."""
    who = entry.get("tv_id") or entry.get("customer_name") or ""
    return f"{entry.get('type', '')}|{who}|{entry.get('start', '')[:16]}"


def duration_text(seconds):
    minutes = int(round(seconds / 60))
    if minutes < 60:
        return f"{max(minutes, 1)} min"
    return f"{minutes // 60}:{minutes % 60:02d} h"


class Journal:
    def __init__(self, folder):
        self.folder = folder
        self._cache = {}

    # ------------------------------------------------------------ Ablage

    def _path(self, date_str):
        return os.path.join(self.folder, f"{date_str}.json")

    def load(self, date_str):
        if date_str not in self._cache:
            data = safe_io.read_json(self._path(date_str), None, expect=dict) or {}
            items = [i for i in data.get("items", []) if self._valid(i)]
            self._cache[date_str] = {"items": items, "ignored": list(data.get("ignored", []))}
        return self._cache[date_str]

    @staticmethod
    def _valid(item):
        try:
            return isinstance(item, dict) and _t(item["start"]) < _t(item["end"])
        except (KeyError, TypeError, ValueError):
            return False

    def _save(self, date_str):
        return safe_io.write_json(self._path(date_str), self._cache[date_str], indent=1)

    def items(self, date_str):
        return sorted(self.load(date_str)["items"], key=lambda i: i["start"])

    def add(self, item):
        """Neue Tätigkeit speichern. item braucht start, end; Rest optional."""
        item = dict(item)
        item.setdefault("id", uuid.uuid4().hex[:12])
        now = datetime.now().strftime(TIME_FMT)
        item.setdefault("created", now)
        item["updated"] = now
        for key in ("customer", "category", "text"):
            item[key] = (item.get(key) or "").strip()
        if not self._valid(item):
            raise ValueError("Ende muss nach dem Beginn liegen")
        date_str = item["start"][:10]
        data = self.load(date_str)
        data["items"] = [i for i in data["items"] if i.get("id") != item["id"]]
        data["items"].append(item)
        if not self._save(date_str):
            raise OSError("Tätigkeit konnte nicht gespeichert werden (Details in fehler.log)")
        return item

    def update(self, old_item, new_item):
        """Tätigkeit ändern (auch auf einen anderen Tag verschieben)."""
        new_item = {**old_item, **new_item}
        if old_item["start"][:10] != new_item["start"][:10]:
            self.delete(old_item)
        return self.add(new_item)

    def delete(self, item):
        date_str = item["start"][:10]
        data = self.load(date_str)
        data["items"] = [i for i in data["items"] if i.get("id") != item.get("id")]
        self._save(date_str)

    def ignore(self, entry):
        date_str = entry["start"][:10]
        data = self.load(date_str)
        key = entry_key(entry)
        if key not in data["ignored"]:
            data["ignored"].append(key)
            self._save(date_str)

    def is_ignored(self, entry):
        return entry_key(entry) in self.load(entry["start"][:10])["ignored"]

    def customers(self, days=60, today=None):
        """Kunden der letzten Tage, häufigste zuerst (für die Auswahl im Dialog)."""
        today = today or datetime.now()
        counts = {}
        for i in range(days):
            date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            if not os.path.exists(self._path(date_str)) and date_str not in self._cache:
                continue
            for item in self.load(date_str)["items"]:
                if item.get("customer"):
                    counts[item["customer"]] = counts.get(item["customer"], 0) + 1
        return sorted(counts, key=lambda c: (-counts[c], c.lower()))

    # ------------------------------------------------------------ Anzeige

    def entries(self, date_str):
        """Tätigkeiten als Timeline-Einträge."""
        result = []
        for item in self.items(date_str):
            label = " · ".join(t for t in (item.get("category"), item.get("text")) if t)
            result.append({
                "start": item["start"], "end": item["end"],
                "type": DOC_TYPE,
                "customer_name": item.get("customer", ""),
                "category": item.get("category", ""),
                "description": item.get("text", ""),
                "details": label,
                "is_suggestion": False,
                "doc": True,
                "doc_item": item,
            })
        return result

    def covered_seconds(self, date_str, start, end):
        """Wie viele Sekunden von [start, end) schon dokumentiert sind."""
        spans = sorted((max(_t(i["start"]), start), min(_t(i["end"]), end))
                       for i in self.items(date_str))
        total, cur_end = 0.0, start
        for s, e in spans:
            s = max(s, cur_end)
            if e > s:
                total += (e - s).total_seconds()
                cur_end = e
        return total

    def open_items(self, entries, date_str, min_minutes=5, now=None, min_share=0.5):
        """Erkannte Tätigkeiten des Tages, die noch nicht (zur Hälfte) dokumentiert sind.

        entries: zusammengefasste Einträge des Tages (Verbindungen, Telefonate, Regel-Blöcke).
        Laufende (Ende nahe jetzt) zählen noch nicht, ignorierte nie.
        """
        now = now or datetime.now()
        result = []
        for e in entries:
            if e.get("doc") or e.get("ai") or e.get("open") or "app" in e:
                continue
            try:
                start, end = _t(e["start"]), _t(e["end"])
            except (KeyError, ValueError):
                continue
            if start.strftime("%Y-%m-%d") != date_str:
                continue
            seconds = (end - start).total_seconds()
            # Läuft noch (VPN offen, Ende = letzter Blick): erst nach dem Ende fragen
            running = e.get("running") or any(p.get("running") for p in e.get("parts", []))
            if seconds < min_minutes * 60 or running or end > now - timedelta(minutes=3):
                continue
            if self.is_ignored(e):
                continue
            if self.covered_seconds(date_str, start, end) >= seconds * min_share:
                continue
            result.append(e)
        return result


def open_entry(entry):
    """Undokumentierten Eintrag für die Zeile "Doku" (gestrichelt, Klick = eintragen)."""
    return {
        "start": entry["start"], "end": entry["end"],
        "type": OPEN_TYPE,
        "customer_name": entry.get("customer_name", ""),
        "details": f"Noch nicht dokumentiert: {describe(entry)}",
        "is_suggestion": True,
        "open": True,
        "source_entry": entry,
    }


def describe(entry):
    """Kurze Beschreibung eines erkannten Eintrags für die Nachfrage."""
    start, end = _t(entry["start"]), _t(entry["end"])
    what = entry.get("category") if entry.get("rule") else entry.get("type", "Tätigkeit")
    if entry.get("direction") and entry.get("direction") != "Anruf":
        what = f"{entry.get('type', '')} {entry['direction'].lower()}"
    who = entry.get("customer_name") or ""
    return (f"{what}{' ' + who if who else ''}, {start:%H:%M}–{end:%H:%M} "
            f"({duration_text((end - start).total_seconds())})")


def suggest_category(entry, categories):
    """Passende Kategorie für einen erkannten Eintrag (ohne KI)."""
    if entry.get("category") and entry["category"] in categories:
        return entry["category"]
    kind = (entry.get("type") or "").lower()
    wanted = []
    if entry.get("direction") or "telefon" in kind:
        wanted = ["telefon"]
    elif any(w in kind for w in ("teamviewer", "rdp", "ssh", "vpn", "verbindung")):
        wanted = ["fernwartung"]
    elif any(w in kind for w in ("passwort", "otp", "zugang", "benutzername")):
        wanted = ["zugang", "sicherheit"]
    for w in wanted:
        for c in categories:
            if w in c.lower():
                return c
    return ""


def suggest_customer(entry, tv_names=None):
    """Kunde aus einem erkannten Eintrag (ohne Nummern in Klammern, ohne reine IDs)."""
    if entry.get("tv_id"):
        return (tv_names or {}).get(entry["tv_id"], "")
    name = entry.get("customer_name") or ""
    name = re.sub(r"\s*\([+\d\s/-]+\)$", "", name)  # "Müller (0711 123)" -> "Müller"
    return "" if re.fullmatch(r"[+\d\s/-]*", name) else name


def ticket_line(item):
    """Tätigkeit als Zeile fürs Ticket."""
    start, end = _t(item["start"]), _t(item["end"])
    head = f"{start:%H:%M}–{end:%H:%M} ({duration_text((end - start).total_seconds())})"
    parts = [p for p in (item.get("customer"), item.get("category")) if p]
    text = item.get("text", "")
    return f"{head}  {' · '.join(parts)}{': ' if parts and text else ''}{text}".rstrip()
