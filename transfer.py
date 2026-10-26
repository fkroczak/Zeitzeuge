"""
Daten von einem PC auf einen anderen übertragen (z. B. vom Arbeits-PC auf die PAW).

Auf der PAW gibt es kein 3CX, kein ITM, kein Matrix42 und keine Laufwerksfreigabe.
Darum: Auf dem Arbeits-PC alles Nötige in EINE Datei exportieren (oder als Text in die
Zwischenablage), von Hand auf die PAW bringen und dort übernehmen. Die PAW zeigt dann
ihre eigenen RDM-Verbindungen zusammen mit allem vom Arbeits-PC an einer Stelle.

Format: JSON, mit gzip gepackt und mit dem Übertragungsschlüssel verschlüsselt
(AES-256-GCM, Schlüssel per scrypt aus dem Ziffernschlüssel, siehe datakey.py):
    b"ZZEXP2\n" + Salz + Nonce + Chiffrat
In der Zwischenablage als Text "ZEITZEUGE-EXPORT:2:" + Base64 (geht auch, wo nur Text
über RDP kopiert werden darf). Das alte, unverschlüsselte Format 1 ("ZEITZEUGE-EXPORT:1:",
reines gzip) wird beim Übernehmen weiter angenommen, mit Hinweis.

    {"format": "zeitzeuge-export", "version": 1, "pc": "PC-123",
     "erstellt": "2026-10-26 08:00:00", "von": "2026-09-26", "bis": "2026-10-26",
     "teamviewer_names": {...},
     "tage": {"2026-10-20": {"verbindungen": [...], "pc": [...], "personalzeit": {...},
                             "m42": [...], "taetigkeiten": {"items": [...], "ignored": [...]},
                             "ki": {"items": [...], "model": ..., "created": ...}}}}

Übernommene Daten liegen auf dem Ziel-PC in EINER Datei (uebernommen.json), je
Herkunfts-PC getrennt. Ein neuerer Export desselben PCs ersetzt dessen Tage.

Rein funktional, ohne Qt.
"""

import base64
import binascii
import gzip
import json
import os
import socket
from datetime import datetime

import datakey
import datastore
import safe_io

FORMAT = "zeitzeuge-export"
VERSION = 1
CLIP_PREFIX = "ZEITZEUGE-EXPORT:2:"   # verschlüsselt
CLIP_PREFIX_PLAIN = "ZEITZEUGE-EXPORT:1:"  # alt, unverschlüsselt
MAGIC = b"ZZEXP2\n"
PURPOSE = b"export"
TIME_FMT = "%Y-%m-%d %H:%M:%S"
DAY_KEYS = ("verbindungen", "pc", "personalzeit", "m42", "taetigkeiten", "ki")


class TransferError(ValueError):
    """Datei oder Text ist kein Zeitzeuge-Export (oder beschädigt)."""


class WrongTransferKey(TransferError):
    """Übertragungsschlüssel passt nicht zum Export."""


class NeedKey(TransferError):
    """Export ist verschlüsselt, aber es wurde kein Übertragungsschlüssel angegeben."""


def pc_name():
    return os.environ.get("COMPUTERNAME") or socket.gethostname() or "PC"


def make_export(days, teamviewer_names=None, pc=None, now=None):
    """days: {Tag: {verbindungen, pc, personalzeit, m42, taetigkeiten}} -> Export-dict."""
    now = now or datetime.now()
    # None = nichts bekannt; leere Listen bleiben (bei Matrix42: gelesen, nichts gebucht)
    clean = {d: {k: v for k, v in day.items() if k in DAY_KEYS and v is not None}
             for d, day in days.items()}
    clean = {d: v for d, v in clean.items() if any(v.values()) or v.get("m42") == []}
    return {
        "format": FORMAT, "version": VERSION, "pc": pc or pc_name(),
        "erstellt": now.strftime(TIME_FMT),
        "von": min(days) if days else "", "bis": max(days) if days else "",
        "teamviewer_names": dict(teamviewer_names or {}),
        "tage": clean,
    }


def to_bytes(export, code=None):
    """Export als Dateiinhalt. Mit code (Übertragungsschlüssel) verschlüsselt, ohne nur
    gepackt (nur noch für Tests und zum Lesen alter Exporte)."""
    raw = json.dumps(export, ensure_ascii=False, separators=(",", ":"), default=str)
    packed = gzip.compress(raw.encode("utf-8"), compresslevel=9)
    if code is None:
        return packed
    return MAGIC + datakey.wrap_with_code(packed, code, PURPOSE)


def to_clipboard_text(export, code=None):
    prefix = CLIP_PREFIX if code is not None else CLIP_PREFIX_PLAIN
    return prefix + base64.b64encode(to_bytes(export, code)).decode("ascii")


def _raw(data):
    """Zwischenablage-Text oder Dateiinhalt -> bytes."""
    if isinstance(data, str):
        text = "".join(data.split())  # Zeilenumbrüche beim Kopieren stören nicht
        for prefix in (CLIP_PREFIX, CLIP_PREFIX_PLAIN):
            if text.startswith(prefix):
                try:
                    return base64.b64decode(text[len(prefix):], validate=True)
                except (ValueError, binascii.Error) as e:
                    raise TransferError(f"Der Text ist unvollständig oder beschädigt ({e}).") from e
        raise TransferError("In der Zwischenablage steht kein Zeitzeuge-Export.")
    return data


def is_encrypted(data):
    """Steckt ein verschlüsselter Export in data (bytes oder Zwischenablage-Text)?"""
    try:
        return _raw(data).startswith(MAGIC)
    except TransferError:
        return False


def parse(data, code=None):
    """Export aus Dateiinhalt (bytes) oder Zwischenablage (str). TransferError bei Unsinn,
    NeedKey, wenn er verschlüsselt ist und code fehlt. Unverschlüsselte (alte) Exporte
    tragen danach "unverschluesselt": True."""
    data = _raw(data)
    plain = not data.startswith(MAGIC)
    if not plain:
        if not code:
            raise NeedKey("Der Export ist verschlüsselt. Dafür brauchst du den Übertragungsschlüssel.")
        try:
            data = datakey.unwrap_with_code(data[len(MAGIC):], code, PURPOSE)
        except datakey.BadCode as e:
            raise TransferError(str(e)) from e
        except datakey.WrongKey as e:
            raise WrongTransferKey("Der Übertragungsschlüssel passt nicht zu diesem Export. "
                                "Er muss auf beiden PCs gleich sein.") from e
    try:
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        export = json.loads(data.decode("utf-8"))
    except TransferError:
        raise
    except (ValueError, OSError, EOFError, UnicodeDecodeError) as e:
        raise TransferError(f"Die Daten sind kein Zeitzeuge-Export oder beschädigt ({e}).") from e
    if not isinstance(export, dict) or export.get("format") != FORMAT:
        raise TransferError("Das ist kein Zeitzeuge-Export.")
    if export.get("version", 0) > VERSION:
        raise TransferError("Der Export stammt aus einer neueren Zeitzeuge-Version. Bitte hier aktualisieren.")
    if not isinstance(export.get("tage"), dict):
        raise TransferError("Der Export enthält keine Tage.")
    if plain:
        export["unverschluesselt"] = True
    return export


def summary(export):
    """Kurzer Text: was steckt im Export?"""
    days = export.get("tage", {})
    count = {k: 0 for k in ("verbindungen", "pc", "m42", "taetigkeiten", "ki")}
    personal = 0
    for day in days.values():
        for k in ("verbindungen", "pc", "m42"):
            count[k] += len(day.get(k) or [])
        count["taetigkeiten"] += len((day.get("taetigkeiten") or {}).get("items") or [])
        count["ki"] += len([i for i in (day.get("ki") or {}).get("items") or []
                            if isinstance(i, dict) and i.get("status") != "verworfen"])
        personal += bool(day.get("personalzeit"))

    def de(d):
        return f"{d[8:10]}.{d[5:7]}.{d[:4]}" if len(d) == 10 else d
    lines = [f"Von {export.get('pc', '?')}, erstellt {export.get('erstellt', '?')}",
             f"Zeitraum {de(export.get('von', ''))} – {de(export.get('bis', ''))} ({len(days)} Tage mit Daten)",
             f"{count['verbindungen']} Verbindungen und Telefonate, {count['pc']} Fensterabschnitte, "
             f"{personal} Tage Personalzeit, {count['m42']} Matrix42-Buchungen, "
             f"{count['taetigkeiten']} Tätigkeiten, {count['ki']} KI-Vorschläge"]
    return "\n".join(lines)


class ImportStore:
    """Übernommene Daten anderer PCs (Ablage "uebernommen" in der Datenbank)."""

    def __init__(self, path):
        self.path = path
        try:
            store, name = datastore.locate(path, "single")
            data = store.get(name, "", {})
        except (datastore.Busy, datastore.Locked) as e:
            safe_io.report(f"Übernommene Daten gerade nicht lesbar: {e}")
            data = {}
        data = data if isinstance(data, dict) else {}
        pcs = data.get("pcs") if isinstance(data.get("pcs"), dict) else {}
        self.pcs = {k: v for k, v in pcs.items() if isinstance(v, dict) and isinstance(v.get("tage"), dict)}

    def add(self, export, own_pc=None):
        """Export übernehmen. Tage desselben PCs werden ersetzt, wenn der Export neuer ist.
        Gibt die Zahl der übernommenen Tage zurück."""
        pc = export.get("pc") or "PC"
        if own_pc and pc.lower() == own_pc.lower():
            raise TransferError(f"Der Export stammt von diesem PC ({pc}). Er gehört auf den anderen PC.")
        entry = self.pcs.setdefault(pc, {"tage": {}, "erstellt": {}})
        created = export.get("erstellt", "")
        stamps = entry.setdefault("erstellt", {})
        if not isinstance(stamps, dict):
            stamps = entry["erstellt"] = {}
        taken = 0
        # Alle Tage des Zeitraums gelten als bekannt: ein Tag ohne Daten löscht alte Daten
        days = dict(export["tage"])
        if export.get("von") and export.get("bis"):
            for d in list(entry["tage"]):
                if export["von"] <= d <= export["bis"] and d not in days:
                    days[d] = {}
        for d, day in days.items():
            if not isinstance(day, dict) or stamps.get(d, "") > created:
                continue  # älterer Export überschreibt nichts Neueres
            if day:
                entry["tage"][d] = day
            else:
                entry["tage"].pop(d, None)
            stamps[d] = created
            taken += 1
        entry["teamviewer_names"] = {**entry.get("teamviewer_names", {}),
                                     **(export.get("teamviewer_names") or {})}
        entry["zuletzt"] = created
        try:
            store, name = datastore.locate(self.path, "single")
            store.put(name, "", {"pcs": self.pcs})
        except (datastore.Busy, datastore.Locked) as e:
            raise OSError(f"Übernommene Daten konnten nicht gespeichert werden ({e})") from e
        return taken

    def clear(self):
        self.pcs = {}
        store, name = datastore.locate(self.path, "single")
        store.delete(name, "")

    def pc_days_before(self, day):
        """Tage vor day, an denen übernommener PC-Verlauf (aktive Fenster) liegt."""
        return sorted({d for entry in self.pcs.values() for d, data in entry["tage"].items()
                       if d < day and isinstance(data, dict) and data.get("pc")})

    def drop_pc_before(self, day):
        """Übernommenen PC-Verlauf vor day entfernen. Alles andere (Verbindungen,
        Tätigkeiten, Buchungen …) bleibt. Gibt die Zahl der betroffenen Tage zurück."""
        dropped = 0
        for entry in self.pcs.values():
            for d, data in entry["tage"].items():
                if d < day and isinstance(data, dict) and data.get("pc"):
                    data.pop("pc")
                    dropped += 1
        if dropped:
            try:
                store, name = datastore.locate(self.path, "single")
                store.put(name, "", {"pcs": self.pcs})
            except (datastore.Busy, datastore.Locked) as e:
                raise OSError(f"Übernommene Daten konnten nicht gespeichert werden ({e})") from e
        return dropped

    def __bool__(self):
        return bool(self.pcs)

    def _days(self, date_str):
        for pc, entry in self.pcs.items():
            day = entry["tage"].get(date_str)
            if isinstance(day, dict):
                yield pc, day

    def connections(self, date_str):
        """Verbindungen und Telefonate anderer PCs, gekennzeichnet mit dem Herkunfts-PC."""
        result = []
        for pc, day in self._days(date_str):
            for e in day.get("verbindungen") or []:
                if isinstance(e, dict) and "start" in e and "end" in e:
                    result.append(dict(e, source_pc=pc))
        return result

    def segments(self, date_str):
        result = []
        for _pc, day in self._days(date_str):
            result += [s for s in day.get("pc") or [] if isinstance(s, dict)
                       and all(isinstance(s.get(k), str) for k in ("start", "end", "app", "title"))]
        return result

    def personal(self, date_str):
        for _pc, day in self._days(date_str):
            if isinstance(day.get("personalzeit"), dict):
                return day["personalzeit"]
        return None

    def m42(self, date_str):
        """Buchungen (None = für diesen Tag nichts übernommen)."""
        found = None
        for _pc, day in self._days(date_str):
            if isinstance(day.get("m42"), list):
                found = (found or []) + day["m42"]
        return found

    def journal(self, date_str):
        """Tätigkeiten anderer PCs: {"items": [...], "ignored": [...]}, Einträge mit von_pc."""
        items, ignored = [], []
        for pc, day in self._days(date_str):
            data = day.get("taetigkeiten") or {}
            items += [dict(i, von_pc=pc) for i in data.get("items") or [] if isinstance(i, dict)]
            ignored += [k for k in data.get("ignored") or [] if isinstance(k, str)]
        return {"items": items, "ignored": ignored}

    def ai(self, date_str):
        """KI-Vorschläge anderer PCs: [(PC, Liste der Vorschläge wie in ki_vorschlaege)]."""
        result = []
        for pc, day in self._days(date_str):
            items = (day.get("ki") or {}).get("items")
            if isinstance(items, list) and items:
                result.append((pc, items))
        return result

    def teamviewer_names(self):
        names = {}
        for entry in self.pcs.values():
            names.update(entry.get("teamviewer_names") or {})
        return names

    def describe(self):
        """Je Herkunfts-PC: Name, Zeitraum, Stand."""
        lines = []
        for pc, entry in sorted(self.pcs.items()):
            days = sorted(entry["tage"])
            span = f"{days[0]} bis {days[-1]}" if days else "keine Tage"
            lines.append(f"{pc}: {span}, Stand {entry.get('zuletzt', '?')}")
        return "\n".join(lines)
