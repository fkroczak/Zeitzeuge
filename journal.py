"""
Tätigkeiten, die du selbst einträgst (nachträglich oder auf Nachfrage von Zeitzeuge).

Pro Tag ein Eintrag in der Datenbank (Ablage "taetigkeiten", früher
taetigkeiten/JJJJ-MM-TT.json):
    {"items": [{"id", "start", "end", "customer", "category", "text",
                "source", "created", "updated", "ticket" (optional)}],
     "ignored": ["<Schlüssel eines Eintrags, nach dem nicht mehr gefragt wird>"]}

Dazu die Logik, welche erkannten Tätigkeiten noch nicht dokumentiert sind
(open_items). Daraus entstehen die Nachfrage-Fenster und die Zeile "Doku".
"""

import re
import uuid
from datetime import datetime, timedelta

import datastore
import safe_io
from tickets import format_ticket_text

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
        # Tätigkeiten anderer PCs (übernommen, nur lesen): Funktion Tag -> {"items", "ignored"}
        self.extra = None

    def _extra(self, date_str):
        if not self.extra:
            return {"items": [], "ignored": []}
        try:
            return self.extra(date_str) or {"items": [], "ignored": []}
        except Exception:  # übernommene Daten dürfen die eigenen nie stören
            return {"items": [], "ignored": []}

    # ------------------------------------------------------------ Ablage

    def _db(self):
        return datastore.locate(self.folder, "day_files")

    def load(self, date_str):
        if date_str not in self._cache:
            try:
                store, name = self._db()
                data = store.get(name, date_str) or {}
            except (datastore.Busy, datastore.Locked):
                # Gerade nicht lesbar: nichts merken, sonst überschriebe das nächste Speichern
                # den Tag mit nur dem neuen Eintrag
                return {"items": [], "ignored": [], "locked": True}
            if not isinstance(data, dict):
                data = {}
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
        try:
            store, name = self._db()
            store.put(name, date_str, self._cache[date_str])
            return True
        except (datastore.Busy, datastore.Locked) as e:
            safe_io.report(f"Tätigkeiten: Speichern fehlgeschlagen ({e})")
            self._cache.pop(date_str, None)  # beim nächsten Lesen wieder den gespeicherten Stand
            return False

    def items(self, date_str):
        """Eigene Tätigkeiten und (nur lesen) die von anderen PCs übernommenen."""
        extra = [i for i in self._extra(date_str)["items"] if self._valid(i)]
        return sorted(self.load(date_str)["items"] + extra, key=lambda i: i["start"])

    def add(self, item):
        """Neue Tätigkeit speichern. item braucht start, end; Rest optional."""
        item = dict(item)
        item.setdefault("id", uuid.uuid4().hex[:12])
        now = datetime.now().strftime(TIME_FMT)
        item.setdefault("created", now)
        item["updated"] = now
        for key in ("customer", "category", "text"):
            item[key] = (item.get(key) or "").strip()
        if "ticket" in item:  # Ticketnummer, nur gespeichert, wenn eine da ist
            item["ticket"] = (item.get("ticket") or "").strip()
            if not item["ticket"]:
                del item["ticket"]
        if not self._valid(item):
            raise ValueError("Ende muss nach dem Beginn liegen")
        date_str = item["start"][:10]
        data = self.load(date_str)
        if data.get("locked"):
            raise OSError("Die Datenbank ist gerade gesperrt. Bitte gleich noch einmal speichern.")
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
        if data.get("locked"):
            raise OSError("Die Datenbank ist gerade gesperrt. Bitte gleich noch einmal versuchen.")
        data["items"] = [i for i in data["items"] if i.get("id") != item.get("id")]
        self._save(date_str)

    def ignore(self, entry):
        date_str = entry["start"][:10]
        data = self.load(date_str)
        key = entry_key(entry)
        if key not in data["ignored"] and not data.get("locked"):
            data["ignored"].append(key)
            self._save(date_str)

    def is_ignored(self, entry):
        date_str = entry["start"][:10]
        key = entry_key(entry)
        return key in self.load(date_str)["ignored"] or key in self._extra(date_str)["ignored"]

    def customers(self, days=60, today=None):
        """Kunden der letzten Tage, häufigste zuerst (für die Auswahl im Dialog)."""
        today = today or datetime.now()
        counts = {}
        try:
            store, name = self._db()
            stored = set(store.days(name))
        except (datastore.Busy, datastore.Locked):
            stored = set()
        for i in range(days):
            date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            if date_str not in stored and date_str not in self._cache:
                continue
            for item in self.load(date_str)["items"]:
                if item.get("customer"):
                    counts[item["customer"]] = counts.get(item["customer"], 0) + 1
        return sorted(counts, key=lambda c: (-counts[c], c.lower()))

    def recent_items(self, days=60, today=None):
        """Eigene Tätigkeiten der letzten Tage (für zuletzt benutzte Texte je Kunde)."""
        today = today or datetime.now()
        try:
            store, name = self._db()
            stored = set(store.days(name))
        except (datastore.Busy, datastore.Locked):
            stored = set()
        result = []
        for i in range(days):
            date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            if date_str in stored or date_str in self._cache:
                result += self.load(date_str)["items"]
        return result

    # ------------------------------------------------------------ Anzeige

    def entries(self, date_str):
        """Tätigkeiten als Timeline-Einträge."""
        result = []
        for item in self.items(date_str):
            label = " · ".join(t for t in (item.get("ticket"), item.get("category"), item.get("text"))
                               if t)
            if item.get("von_pc"):
                label += f" (von {item['von_pc']})"
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
        min_minutes: Mindestdauer, als Zahl oder Funktion (Eintrag -> Minuten).
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
            # Telefonate werden mindestens 1 min breit gezeichnet: echte Dauer nehmen
            length = e.get("duration_s", seconds)
            limit = min_minutes(e) if callable(min_minutes) else min_minutes
            # Läuft noch (VPN offen, Ende = letzter Blick): erst nach dem Ende fragen
            running = e.get("running") or any(p.get("running") for p in e.get("parts", []))
            if length < limit * 60 or running or end > now - timedelta(minutes=3):
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
    if who.startswith(what or "\0"):  # "TeamViewer 1 123 …" nicht als "TeamViewer TeamViewer 1 123 …"
        what = ""
    return (f"{what}{' ' if what and who else ''}{who}, {start:%H:%M}–{end:%H:%M} "
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


def suggest_customer(entry, tv_names=None, customers=None):
    """Kunde aus einem erkannten Eintrag (ohne Nummern in Klammern, ohne reine IDs).

    customers: Kundenliste oder customers.Index. Passt eine Spur (TeamViewer-ID, Nummer,
    RDM-/VPN-Name, E-Mail-Domain), gewinnt der Kunde aus der Liste."""
    if customers is not None:
        import customers as customer_list  # ohne Qt
        found = customer_list.customer_for(entry, customers)
        if found:
            return found
    if entry.get("tv_id"):
        return (tv_names or {}).get(entry["tv_id"], "")
    name = entry.get("customer_name") or ""
    name = re.sub(r"\s*\([+\d\s/-]+\)$", "", name)  # "Müller (0711 123)" -> "Müller"
    return "" if re.fullmatch(r"[+\d\s/-]*", name) else name


def ticket_line(item, text_style="", billing=None):
    """Tätigkeit als Zeile fürs Ticket. text_style "dash": Text als "- " / "-- " darunter.
    billing (billing.Billing): abgerechnete Dauer dazu, z. B. "10:05–10:17 (12 min → abgerechnet 0:15 h)"."""
    start, end = _t(item["start"]), _t(item["end"])
    seconds = (end - start).total_seconds()
    note = billing.note(seconds, item.get("customer", "")) if billing else ""
    head = f"{start:%H:%M}–{end:%H:%M} ({duration_text(seconds)}{note})"
    parts = [p for p in (item.get("customer"), item.get("category"), item.get("ticket")) if p]
    text = format_ticket_text(item.get("text", ""), text_style)
    if text_style == "dash" and text:  # Kopfzeile, darunter die gegliederte Tätigkeit
        return f"{head}  {' · '.join(parts)}{':' if parts else ''}".rstrip() + "\n" + text
    return f"{head}  {' · '.join(parts)}{': ' if parts and text else ''}{text}".rstrip()
