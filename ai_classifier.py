"""
KI-Vorschläge: Tätigkeiten des Tages mit Claude (Anthropic) einordnen.

Zeitzeuge schickt die Einträge eines Tages (Verbindungen, Telefonate,
Zugangsdaten und auf Wunsch die aktiven Fenster) als kurze Textliste an die
Anthropic-API. Zurück kommen Tätigkeitsblöcke mit Kunde, Kategorie und einem
Satz fürs Ticket. Sie erscheinen in der Timeline als eigene Zeile "KI".

- Läuft nur, wenn du es anstößt (Knopf "KI-Vorschläge" oder F6), oder auf
  Wunsch automatisch für vergangene Tage.
- Ergebnisse liegen pro Tag in ki_vorschlaege/JJJJ-MM-TT.json. Ändern sich
  die Einträge des Tages nicht, wird nichts erneut gesendet.
- Der API-Schlüssel liegt lokal unter %LOCALAPPDATA%\\Zeitzeuge\\anthropic_key.txt
  (nicht im oft mit OneDrive synchronisierten Datenordner) oder in der
  Umgebungsvariable ANTHROPIC_API_KEY.
"""

import hashlib
import json
import os
import threading
from datetime import datetime

from PySide6.QtCore import QObject, Signal

import net
import datastore
import safe_io
import storage

try:
    import anthropic
except ImportError:  # Paket fehlt: Funktion bleibt aus
    anthropic = None

TIME_FMT = "%Y-%m-%d %H:%M:%S"
AI_TYPE = "KI-Vorschlag"
KEY_FILE = "anthropic_key.txt"

# Modelle zur Auswahl (ID, Anzeigename, Preis Eingabe / Ausgabe in $ pro 1 Mio. Token)
MODELS = [
    ("claude-opus-5-5", "Claude Opus 5.5 (beste Qualität)", 4.00, 20.00),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5 (günstiger)", 2.00, 10.00),
    ("claude-haiku-5-5", "Claude Haiku 5.5 (am günstigsten)", 0.10, 0.50),
]
DEFAULT_MODEL = MODELS[0][0]
OFFLINE_TEXT = "Keine Internetverbindung. Die KI-Vorschläge gehen erst wieder mit Internet."


def api_url():
    """Adresse der API (ANTHROPIC_BASE_URL wie im anthropic-Paket, z. B. für Tests)."""
    return os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"

DEFAULT_CATEGORIES = [
    "Fernwartung",
    "Telefonsupport",
    "Server-/Netzwerkadministration",
    "Cloud-/M365-Administration",
    "Zugangsdaten / Sicherheit",
    "E-Mail / Kommunikation",
    "Dokumentation / Ticket",
    "Beratung / Abstimmung",
    "Interne Tätigkeit",
    "Pause / Privat",
]

SYSTEM_PROMPT = """Du hilfst einem IT-Dienstleister, seinen Arbeitstag für Tickets und \
Abrechnung zu erfassen. Du bekommst die Spuren eines Tages: Fernwartungs-Verbindungen \
(TeamViewer, RDP, SSH, VPN aus dem Remote Desktop Manager), angezeigte Zugangsdaten, \
Telefonate und die aktiven Fenster am PC.

Fasse zusammengehörige Spuren zu Tätigkeitsblöcken zusammen und ordne jeden Block ein:
- kunde: der Kunde oder das System, um das es geht. Leite ihn aus Verbindungs-, \
Anrufer- und Fensternamen ab. Unbekannt oder intern: leerer Text.
- kategorie: genau eine aus der vorgegebenen Liste.
- beschreibung: ein kurzer Satz auf Deutsch, wie ihn ein Techniker ins Ticket schreibt, \
z. B. "Fernwartung Server, Updates eingespielt" oder "Rückruf wegen Druckerproblem". \
Erfinde keine Details, die nicht aus den Spuren hervorgehen.
- sicherheit: wie sicher die Zuordnung ist, von 0 bis 1.

Regeln:
- Blöcke überschneiden sich nicht und liegen zeitlich sortiert. Ein Block beginnt \
und endet zu Uhrzeiten aus den Spuren.
- Kurze Unterbrechungen (wenige Minuten) gehören zum laufenden Block, wenn es \
um denselben Kunden geht. Ein Telefonat zu einem anderen Thema ist ein eigener Block.
- Zeiten ohne Spuren lässt du aus. Fasse nicht den ganzen Tag zu einem Block zusammen.
- Fenstertitel wie "(ausgeblendet)" sind private oder geschützte Fenster."""


def api_key():
    """API-Schlüssel aus der Umgebung oder der lokalen Datei, sonst ''."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"].strip()
    try:
        with open(os.path.join(storage.local_dir(), KEY_FILE), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def key_from_env():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def save_api_key(key):
    path = os.path.join(storage.local_dir(), KEY_FILE)
    if not key:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(key.strip())


def model_price(model):
    for mid, _name, price_in, price_out in MODELS:
        if mid == model:
            return price_in, price_out
    return MODELS[0][2], MODELS[0][3]


def cost_usd(model, usage):
    """Ungefähre Kosten eines Aufrufs in US-Dollar."""
    price_in, price_out = model_price(model)
    tokens_in = (usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
                 + usage.get("cache_read_input_tokens", 0) * 0.1)
    return (tokens_in * price_in + usage.get("output_tokens", 0) * price_out) / 1_000_000


# ---------------------------------------------------------------- Eingabe

def _hm(text):
    return text[11:16]


OUTLOOK_TYPES = ("Termin", "Teams-Besprechung", "Mail gesendet")  # wie timeline_only.OUTLOOK_TYPES


def build_day_text(entries, pc_entries=None):
    """Einträge des Tages als kompakte Textliste (eine Zeile pro Eintrag)."""
    lines, outlook = [], []
    for e in sorted(entries, key=lambda e: e["start"]):
        if e.get("type") == AI_TYPE:
            continue
        kind = e.get("type", "")
        if e.get("direction") and not (kind == "Teams-Anruf" and e["direction"] == "Anruf"):
            kind = f"{kind} {e['direction'].lower()}"
        parts = [f"{_hm(e['start'])}-{_hm(e['end'])}", kind, e.get("customer_name", "")]
        if e.get("details"):
            parts.append(e["details"])
        if e.get("email_domains") and not any(d in (e.get("details") or "") for d in e["email_domains"]):
            parts.append("Domains: " + ", ".join(e["email_domains"]))
        (outlook if kind in OUTLOOK_TYPES else lines).append(" | ".join(p for p in parts if p))
    pc_lines = []
    for p in sorted(pc_entries or [], key=lambda e: e["start"]):
        pc_lines.append(f"{_hm(p['start'])}-{_hm(p['end'])} | {p.get('app', '')} | "
                        f"{p.get('customer_name', '')}")
    text = "Verbindungen, Zugangsdaten und Telefonate:\n" + ("\n".join(lines) or "(keine)")
    if outlook:  # nur mit eingeschalteter Datenquelle Outlook
        text += ("\n\nTermine und gesendete Mails aus Outlook (Kalender zeigt Geplantes, "
                 "eine Mail steht für wenige Minuten):\n" + "\n".join(outlook))
    if pc_entries is not None:
        text += "\n\nAktive Fenster am PC (Programm | Fenstertitel):\n" + ("\n".join(pc_lines) or "(keine)")
    return text


def _schema(categories):
    return {
        "type": "object",
        "properties": {
            "taetigkeiten": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "von": {"type": "string", "description": "HH:MM"},
                        "bis": {"type": "string", "description": "HH:MM"},
                        "kunde": {"type": "string"},
                        "kategorie": {"type": "string", "enum": list(categories)},
                        "beschreibung": {"type": "string"},
                        "sicherheit": {"type": "number"},
                    },
                    "required": ["von", "bis", "kunde", "kategorie", "beschreibung", "sicherheit"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["taetigkeiten"],
        "additionalProperties": False,
    }


def _valid_hm(text):
    try:
        datetime.strptime(text, "%H:%M")
        return True
    except (TypeError, ValueError):
        return False


def to_entries(date_str, items):
    """Antwort der KI in Timeline-Einträge umwandeln (ungültige Zeilen fallen weg)."""
    result = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue  # kaputter Eintrag in der Datei
        von, bis = item.get("von", ""), item.get("bis", "")
        if not (_valid_hm(von) and _valid_hm(bis)) or bis <= von:
            continue
        result.append({
            "start": f"{date_str} {von}:00",
            "end": f"{date_str} {bis}:00",
            "type": AI_TYPE,
            "customer_name": item.get("kunde", "").strip(),
            "category": item.get("kategorie", ""),
            "details": f"{item.get('kategorie', '')}: {item.get('beschreibung', '').strip()}",
            "description": item.get("beschreibung", "").strip(),
            "confidence": item.get("sicherheit", 0),
            "is_suggestion": True,
            "ai": True,
            "ai_id": i,
            "status": item.get("status", ""),
        })
    result.sort(key=lambda e: e["start"])
    return result


# ---------------------------------------------------------------- Ablage

class AiStore:
    """Vorschläge pro Tag (Ablage "ki_vorschlaege" in der Datenbank)."""

    def __init__(self, folder):
        self.folder = folder
        self._cache = {}

    def _db(self):
        return datastore.locate(self.folder, "day_files")

    def load(self, date_str):
        if date_str not in self._cache:
            try:
                store, name = self._db()
                data = store.get(name, date_str)
            except (datastore.Busy, datastore.Locked):
                return None  # gerade nicht lesbar: nicht merken
            if not isinstance(data, dict):
                data = None
            elif not isinstance(data.get("items", []), list):
                data["items"] = []
            self._cache[date_str] = data
        return self._cache[date_str]

    def save(self, date_str, data):
        try:
            store, name = self._db()
            store.put(name, date_str, data)
        except (datastore.Busy, datastore.Locked) as e:
            safe_io.report(f"KI-Vorschläge: Speichern fehlgeschlagen ({e})")
        self._cache[date_str] = data

    def entries(self, date_str):
        """Vorschläge des Tages als Timeline-Einträge, ohne verworfene."""
        data = self.load(date_str)
        if not data:
            return []
        return [e for e in to_entries(date_str, data.get("items", []))
                if e["status"] != "verworfen"]

    def set_status(self, date_str, ai_id, status):
        data = self.load(date_str)
        if not data or not 0 <= ai_id < len(data.get("items", [])):
            return
        data["items"][ai_id]["status"] = status
        self.save(date_str, data)

    def is_current(self, date_str, input_hash):
        data = self.load(date_str)
        return bool(data) and data.get("input_hash") == input_hash


# ---------------------------------------------------------------- Aufruf

def classify(text, categories, model, key, effort="low"):
    """Ein Aufruf der Messages-API. Gibt (Liste der Tätigkeiten, usage-dict) zurück."""
    client = anthropic.Anthropic(api_key=key, timeout=180.0, max_retries=2)
    request = dict(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT + "\n\nKategorien: " + ", ".join(categories),
        messages=[{"role": "user", "content": text}],
        output_config={"effort": effort,
                       "format": {"type": "json_schema", "schema": _schema(categories)}},
    )
    if model.startswith("claude-haiku"):
        response = client.messages.create(**request)
    else:
        # Lehnt das Modell ab (Sicherheitsfilter), springt die API selbst auf ein passendes um
        response = client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request)

    if response.stop_reason == "refusal":
        raise RuntimeError("Claude hat die Anfrage abgelehnt.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Die Antwort war zu lang und wurde abgeschnitten.")
    text_out = next((b.text for b in response.content if b.type == "text"), "")
    items = json.loads(text_out).get("taetigkeiten", [])
    u = response.usage
    usage = {
        "input_tokens": u.input_tokens or 0,
        "output_tokens": u.output_tokens or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
    }
    return items, usage


def error_text(exc):
    """Verständliche Meldung zu einem Fehler beim Aufruf (nie ein Stacktrace)."""
    if anthropic is not None:
        if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
            if not net.reachable(api_url()):
                return OFFLINE_TEXT
            return "Keine Verbindung zu Anthropic. Internet oder Proxy prüfen."
        if isinstance(exc, anthropic.AuthenticationError):
            return "API-Schlüssel ungültig. Bitte unter Einstellungen ▾ → KI-Vorschläge prüfen."
        if isinstance(exc, anthropic.PermissionDeniedError):
            return "Der API-Schlüssel darf dieses Modell nicht nutzen."
        if isinstance(exc, anthropic.RateLimitError):
            return "Zu viele Anfragen oder Guthaben aufgebraucht. Bitte später noch einmal."
        if isinstance(exc, anthropic.APIConnectionError):
            return "Keine Verbindung zu Anthropic. Internet oder Proxy prüfen."
        if isinstance(exc, anthropic.APIStatusError):
            return f"Fehler von Anthropic ({exc.status_code}): {str(getattr(exc, 'message', exc))[:200]}"
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return OFFLINE_TEXT if not net.reachable(api_url()) else f"Netzwerkfehler: {str(exc)[:200]}"
    if isinstance(exc, ValueError):
        return "Die Antwort von Claude war nicht lesbar. Bitte noch einmal versuchen."
    return (str(exc) or type(exc).__name__)[:200]


class AiClassifier(QObject):
    """Startet Aufrufe im Hintergrund und meldet das Ergebnis per Signal."""

    finished = Signal(str, int, float)  # Tag, Zahl der Vorschläge, Kosten in $
    failed = Signal(str, str)           # Tag, Fehlermeldung

    def __init__(self, store, config, parent=None):
        super().__init__(parent)
        self.store = store
        self.config = config
        self.running = set()

    @staticmethod
    def available():
        return anthropic is not None

    def input_text(self, entries, pc_entries):
        send_pc = self.config.get("ai_send_window_titles", True)
        return build_day_text(entries, pc_entries if send_pc else None)

    def input_hash(self, text):
        payload = json.dumps([text, self.categories(), self.model()], ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def categories(self):
        return self.config.get("ai_categories") or DEFAULT_CATEGORIES

    def model(self):
        return self.config.get("ai_model") or DEFAULT_MODEL

    def start(self, date_str, entries, pc_entries, force=False):
        """Tag klassifizieren. False, wenn nichts zu tun ist (läuft schon, aktuell, leer)."""
        if date_str in self.running:
            return False
        text = self.input_text(entries, pc_entries)
        digest = self.input_hash(text)
        if not force and self.store.is_current(date_str, digest):
            return False
        if not entries and not pc_entries:
            self.failed.emit(date_str, "An diesem Tag gibt es keine Einträge.")
            return False
        key = api_key()
        if not key:
            self.failed.emit(date_str, "Kein API-Schlüssel hinterlegt (Einstellungen ▾ → KI-Vorschläge).")
            return False
        if anthropic is None:
            self.failed.emit(date_str, "Das Paket 'anthropic' ist nicht installiert.")
            return False
        self.running.add(date_str)
        model, categories = self.model(), self.categories()
        effort = self.config.get("ai_effort", "low")
        threading.Thread(target=self._run, daemon=True,
                         args=(date_str, text, digest, model, categories, key, effort)).start()
        return True

    def _run(self, date_str, text, digest, model, categories, key, effort):
        try:
            if not net.reachable(api_url()):  # ohne Netz gleich klar melden statt nach Minuten
                self.failed.emit(date_str, OFFLINE_TEXT)
                return
            items, usage = classify(text, categories, model, key, effort)
            old = self.store.load(date_str) or {}
            # Übernommene Vorschläge bleiben übernommen, wenn sie gleich wiederkommen
            kept = {(i.get("von"), i.get("bis"), i.get("kunde")): i.get("status")
                    for i in old.get("items", []) if i.get("status")}
            for item in items:
                status = kept.get((item.get("von"), item.get("bis"), item.get("kunde")))
                if status:
                    item["status"] = status
            cost = cost_usd(model, usage)
            self.store.save(date_str, {
                "input_hash": digest, "model": model,
                "created": datetime.now().strftime(TIME_FMT),
                "usage": usage, "cost_usd": round(cost, 5), "items": items,
                # Kosten früherer Läufe für diesen Tag (für "Bisher ausgegeben")
                "earlier_cost_usd": round(old.get("cost_usd", 0) + old.get("earlier_cost_usd", 0), 5),
            })
            self.finished.emit(date_str, len(items), cost)
        except Exception as exc:  # Netzwerk, API, ungültiges JSON
            safe_io.log(f"KI-Vorschläge {date_str}: {exc!r}")
            self.failed.emit(date_str, error_text(exc))
        finally:
            self.running.discard(date_str)
