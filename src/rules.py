"""
Klassifizierung ohne KI: feste Regeln ordnen die Einträge eines Tages ein.

Jede Regel prüft ein Feld eines Eintrags (Programm, Fenstertitel, Kunde, Typ,
Details oder alles) auf einen Text oder einen regulären Ausdruck ("re:…"). Weitere
Bedingungen stehen unter "and" ([{"field", "match"}]); dann müssen alle passen, z. B.
Programm „Code“ und Fenstertitel „zeiterfassung“.
Die erste passende Regel gewinnt. Treffer mit gleicher Kategorie und gleichem
Kunden werden zu Blöcken zusammengefasst. Blöcke überschneiden sich nie:
Verbindungen und Telefonate gehen vor PC-Fenstern, danach zählt die
Reihenfolge der Regeln.

Rein funktional, ohne Qt. Auch von activity_tracker.py für die Fenster-Filter
benutzt (compile_pattern, pattern_error).
"""

import copy
import heapq
import re
from datetime import datetime

TIME_FMT = "%Y-%m-%d %H:%M:%S"
RESULT_TYPE = "Klassifizierung"
SKIP_TYPES = {RESULT_TYPE, "KI-Vorschlag"}

# Feld -> Anzeigename im Dialog
FIELDS = {
    "any": "Alle Felder",
    "app": "Programm",
    "title": "Fenstertitel",
    "customer": "Kunde",
    "type": "Typ",
    "details": "Details",
}
FIELD_ORDER = ("app", "title", "customer", "type", "details")

DEFAULT_RULES = [
    {"name": "Fernwartung (TeamViewer, RDP, SSH, RDM)", "field": "type",
     "match": r"re:^(TeamViewer|RDP|SSH|FTP|Website)", "category": "Fernwartung",
     "customer": "", "enabled": True},
    {"name": "Telefonat", "field": "type", "match": "re:^Telefonat",
     "category": "Telefonsupport", "customer": "", "enabled": True},
    {"name": "VPN", "field": "type", "match": "re:^VPN",
     "category": "Fernwartung", "customer": "", "enabled": True},
    {"name": "Zugangsdaten (Passwort, OTP)", "field": "type",
     "match": "re:passwort|otp|benutzername|zugangsdaten|eintrag angezeigt",
     "category": "Zugangsdaten / Sicherheit", "customer": "", "enabled": True},
    {"name": "Remotedesktop-Fenster mit Servername", "field": "title",
     "match": r"re:^(.+?) - (?:Remotedesktopverbindung|Remote Desktop Connection)",
     "category": "Fernwartung", "customer": "{1}", "enabled": True},
    {"name": "Remotedesktop (mstsc)", "field": "app", "match": "mstsc",
     "category": "Fernwartung", "customer": "", "enabled": True},
    {"name": "Ticketsystem (Muster anpassen)", "field": "title",
     "match": r"re:Ticket\s*#?\d+\s*[–-]\s*(.+?)(?:\s+[–|-]\s|$)",
     "category": "Dokumentation / Ticket", "customer": "{1}", "enabled": False},
    {"name": "Microsoft 365 / Azure", "field": "title",
     "match": r"re:admin\.microsoft\.com|Microsoft 365 admin|Exchange admin|\bEntra\b"
              r"|\bIntune\b|portal\.azure|Microsoft Azure",
     "category": "Cloud-/M365-Administration", "customer": "", "enabled": True},
    {"name": "E-Mail (Outlook, Thunderbird)", "field": "app",
     "match": r"re:^(outlook|olk|thunderbird)(\.exe)?$",
     "category": "E-Mail / Kommunikation", "customer": "", "enabled": True},
    {"name": "Teams", "field": "app", "match": r"re:^(ms-)?teams(\.exe)?$",
     "category": "Beratung / Abstimmung", "customer": "", "enabled": True},
    {"name": "Devolutions Password Manager", "field": "app",
     "match": r"re:^devolutions(\.exe)?$",
     "category": "Zugangsdaten / Sicherheit", "customer": "", "enabled": True},
    # Outlook und Teams (nur, wenn die Datenquelle eingeschaltet ist, gibt es solche Einträge)
    {"name": "Teams-Anruf", "field": "type", "match": "re:^Teams-Anruf",
     "category": "Telefonsupport", "customer": "", "enabled": True},
    {"name": "Termin / Teams-Besprechung (Outlook)", "field": "type",
     "match": "re:^(Termin|Teams-Besprechung)$",
     "category": "Beratung / Abstimmung", "customer": "", "enabled": True},
    {"name": "Gesendete Mail (Outlook)", "field": "type", "match": "re:^Mail (gesendet|beantwortet)$",
     "category": "E-Mail / Kommunikation", "customer": "", "enabled": True},
    {"name": "Fahrt (vermutet)", "field": "type", "match": "re:^Fahrt",
     "category": "Fahrt / Reise", "customer": "", "enabled": True},
    {"name": "Teams-Chat", "field": "type", "match": "re:^Teams-Chat$",
     "category": "E-Mail / Kommunikation", "customer": "", "enabled": True},
]


def default_rules():
    """Frische Kopie der Standardregeln (für Config und Dialog)."""
    return copy.deepcopy(DEFAULT_RULES)


def categories(config):
    """Kategorien wie bei den KI-Vorschlägen (Config `ai_categories`)."""
    cats = config.get("ai_categories") if config else None
    if cats:
        return list(cats)
    try:
        from ai_classifier import DEFAULT_CATEGORIES  # erst hier: zieht Qt mit
        return list(DEFAULT_CATEGORIES)
    except Exception:
        return ["Fernwartung", "Telefonsupport", "Server-/Netzwerkadministration",
                "Cloud-/M365-Administration", "Zugangsdaten / Sicherheit",
                "E-Mail / Kommunikation", "Dokumentation / Ticket",
                "Beratung / Abstimmung", "Vor-Ort-Einsatz", "Fahrt / Reise",
                "Interne Tätigkeit", "Pause / Privat"]


# ---------------------------------------------------------------- Muster

def compile_pattern(text):
    """Muster in eine Regex ohne Groß/Klein übersetzen.

    "re:…" ist ein regulärer Ausdruck, alles andere ein Textteil.
    Wirft ValueError mit verständlicher Meldung, wenn die Regex ungültig ist.
    """
    text = (text or "").strip()
    if text[:3].lower() == "re:":
        expr = text[3:].strip()
        if not expr:
            raise ValueError("Nach „re:“ fehlt der Ausdruck")
        try:
            return re.compile(expr, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Ungültiger regulärer Ausdruck: {e}") from None
    if not text:
        raise ValueError("Muster ist leer")
    return re.compile(re.escape(text), re.IGNORECASE)


def pattern_error(text):
    """Fehlermeldung zum Muster oder None, wenn es in Ordnung ist."""
    try:
        compile_pattern(text)
        return None
    except ValueError as e:
        return str(e)


def conditions(rule):
    """Alle Bedingungen einer Regel: [(Feld, Muster)], die erste zuerst."""
    found = [(rule.get("field", "any"), rule.get("match", ""))]
    for c in rule.get("and") or []:
        if isinstance(c, dict):
            found.append((c.get("field", "any"), c.get("match", "")))
    return found


def rule_errors(rules):
    """[(Index, Meldung)] für Regeln mit ungültigem Muster oder Feld."""
    result = []
    for i, rule in enumerate(rules or []):
        err = None
        for n, (field, match) in enumerate(conditions(rule)):
            err = pattern_error(match)
            if err is None and field not in FIELDS:
                err = f"Unbekanntes Feld „{field}“"
            if err:
                err = f"Bedingung {n + 1}: {err}" if n else err
                break
        if err is None and not (rule.get("category") or "").strip():
            err = "Kategorie fehlt"
        if err:
            result.append((i, err))
    return result


_PLACEHOLDER = re.compile(r"\{(\d)\}")


def fill_customer(template, match):
    """Platzhalter {0}…{9} mit den Gruppen des Treffers füllen."""
    def group(m):
        n = int(m.group(1))
        try:
            return match.group(n) or ""
        except (IndexError, re.error):
            return ""
    return _PLACEHOLDER.sub(group, template).strip(" -–|:")


# ---------------------------------------------------------------- Einordnen

def _compile_rules(rules, only_enabled=True):
    """[(Index, Regel, Regex, Felder, weitere Bedingungen [(Regex, Felder)])]."""
    compiled = []
    for i, rule in enumerate(rules or []):
        if only_enabled and (not rule.get("enabled", True) or not (rule.get("category") or "").strip()):
            continue
        parts = []
        try:
            for field, match in conditions(rule):
                if field not in FIELDS:
                    raise ValueError(field)
                parts.append((compile_pattern(match), FIELD_ORDER if field == "any" else (field,)))
        except ValueError:
            continue  # ungültige Regel: der Dialog zeigt den Fehler, hier überspringen
        (regex, fields), extra = parts[0], parts[1:]
        compiled.append((i, rule, regex, fields, extra))
    return compiled


def drop_impossible(compiled, constants):
    """Regeln weglassen, die bei diesen festen Feldwerten nie passen können: Alle Felder einer
    Bedingung stehen fest und keins passt. Beispiel: Fenster der PC-Aktivität haben immer den
    Typ „PC“ und keinen Kunden, Regeln nur auf den Typ „Telefonat“ greifen dort nie.
    Reihenfolge und Ergebnis von match_entry bleiben gleich, es wird nur weniger geprüft."""
    def never(regex, fields):
        return all(f in constants for f in fields) and not any(regex.search(constants[f]) for f in fields)
    return [c for c in compiled
            if not never(c[2], c[3]) and not any(never(rx, fs) for rx, fs in (c[4] if len(c) > 4 else ()))]


def _fields(entry, is_pc):
    customer = entry.get("customer_name") or ""
    return {
        "app": (entry.get("app") or "") if is_pc else "",
        "title": customer if is_pc else "",
        "customer": "" if is_pc else customer,
        "type": entry.get("type") or "",
        "details": entry.get("details") or "",
    }


def keyword_customer(entry, keywords, is_pc=False):
    """Kunde über ein Stichwort der Kundenliste (customers.Index.keyword) oder ''."""
    if keywords is None or entry.get("colleague"):
        return ""
    text = entry.get("customer_name") or ""
    if is_pc and entry.get("app"):
        text = f"{text} {entry.get('app')}"
    return keywords.keyword(text)


def _first_match(values, regex, fields):
    for f in fields:
        m = regex.search(values[f])
        if m:
            return m
    return None


def match_entry(entry, compiled, is_pc=False, keywords=None):
    """(Regelindex, Regel, Kunde) der ersten passenden Regel oder None.

    keywords: customers.Index; setzt die Regel keinen Kunden, kommt er aus einem Stichwort
    der Kundenliste im Fenstertitel oder Namen („Tuxhorn“ im Titel -> Tuxhorn GmbH)."""
    values = _fields(entry, is_pc)
    for index, rule, regex, fields, *rest in compiled:
        # wie _first_match, aber ohne Funktionsaufruf je Regel (läuft je Fenster und Regel)
        for f in fields:
            m = regex.search(values[f])
            if m:
                break
        else:
            continue
        if rest and rest[0] and not all(_first_match(values, rx, fs) for rx, fs in rest[0]):
            continue
        template = rule.get("customer") or ""
        if template:
            customer = fill_customer(template, m)
        elif entry.get("type") == "Telefonat":
            # Anrufer ist eine Person (Kollege oder Ansprechpartner), kein Kunde
            customer = ""
        else:
            customer = values["customer"]
        if not customer:
            customer = keyword_customer(entry, keywords, is_pc)
        return index, rule, customer
    return None


def hit_counts(rules, entries, pc_entries, keywords=None):
    """Treffer je Regel (Liste wie rules): wie oft war sie die erste passende Regel?
    Für die Spalte „7 Tage“ im Regel-Dialog. Ausgeschaltete Regeln zählen mit 0."""
    counts = [0] * len(rules or [])
    compiled = _compile_rules(rules)
    for tier, source in ((0, entries or []), (1, pc_entries or [])):
        for e in source:
            if isinstance(e, dict) and e.get("type") not in SKIP_TYPES:
                hit = match_entry(e, compiled, is_pc=tier == 1)
                if hit:
                    counts[hit[0]] += 1
    return counts


def preview(rule, entries, pc_entries, limit=3):
    """Worauf passt eine Regel für sich allein (ohne Vorrang)? -> (Anzahl, Beispiele)."""
    compiled = _compile_rules([dict(rule, enabled=True, category=rule.get("category") or "?")])
    if not compiled:
        return 0, []
    count, examples = 0, []
    for tier, source in ((0, entries or []), (1, pc_entries or [])):
        for e in source:
            if not isinstance(e, dict) or e.get("type") in SKIP_TYPES:
                continue
            if match_entry(e, compiled, is_pc=tier == 1):
                count += 1
                label = e.get("customer_name") or e.get("type") or ""
                if tier == 1 and e.get("app"):
                    label = f"{e['app']}: {label}"
                if label and label not in examples and len(examples) < limit:
                    examples.append(label)
    return count, examples


def _parse(text):
    try:
        return datetime.fromisoformat(str(text)[:19])
    except (TypeError, ValueError):
        return None


class _Piece:
    __slots__ = ("start", "end", "key", "tier", "prio", "items")

    def __init__(self, start, end, key, tier, prio, items):
        self.start, self.end, self.key = start, end, key
        self.tier, self.prio, self.items = tier, prio, items


def _resolve(items):
    """Überlappende Treffer auflösen: je Zeitpunkt gewinnt der mit der besten Priorität.

    items: Liste (start, end, prio, key, tier, entry). Ergebnis: Stücke ohne Überlappung.
    """
    events = sorted({t for it in items for t in (it[0], it[1])})
    by_start = sorted(range(len(items)), key=lambda i: items[i][0])
    heap, pieces, nxt = [], [], 0
    for t0, t1 in zip(events, events[1:]):
        while nxt < len(by_start) and items[by_start[nxt]][0] <= t0:
            i = by_start[nxt]
            heapq.heappush(heap, (items[i][2], i))
            nxt += 1
        while heap and items[heap[0][1]][1] <= t0:
            heapq.heappop(heap)  # schon zu Ende
        if not heap:
            continue
        prio, i = heap[0]
        start, end, _, key, tier, entry = items[i]
        last = pieces[-1] if pieces else None
        if last and last.end == t0 and last.key == key and last.tier == tier:
            last.end = t1
            last.prio = min(last.prio, prio)
            if last.items[-1] is not entry:
                last.items.append(entry)
        else:
            pieces.append(_Piece(t0, t1, key, tier, prio, [entry]))
    return pieces


def _merge(pieces, gap_seconds):
    """Stücke mit gleicher Kategorie+Kunde und kurzer Lücke verbinden.

    Verbindungen/Telefonate (Stufe 0) schlucken dabei kurze PC-Stücke (Stufe 1)
    dazwischen: ein Fenster während einer Sitzung gehört zur Sitzung.
    """
    out = []
    for p in pieces:
        if out and out[-1].key == p.key and (p.start - out[-1].end).total_seconds() <= gap_seconds:
            _extend(out[-1], p)
            continue
        if p.tier == 0:
            j = len(out) - 1
            while j >= 0 and out[j].tier > 0:
                j -= 1
            if (0 <= j < len(out) - 1 and out[j].key == p.key
                    and (p.start - out[j].end).total_seconds() <= gap_seconds):
                del out[j + 1:]
                _extend(out[j], p)
                continue
        out.append(p)
    return out


def _extend(block, piece):
    block.end = max(block.end, piece.end)
    block.prio = min(block.prio, piece.prio)
    block.tier = min(block.tier, piece.tier)
    seen = {id(e) for e in block.items}
    block.items.extend(e for e in piece.items if id(e) not in seen)


def _fmt_minutes(seconds):
    m = int(round(seconds / 60))
    return f"{m // 60}:{m % 60:02d} h" if m >= 60 else f"{m} min"


def _describe(category, customer, items):
    counts = {}
    for e in items:
        kind = e.get("type") or "Eintrag"
        counts[kind] = counts.get(kind, 0) + 1
    parts = []
    for kind, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        if kind.startswith("PC: "):
            parts.append(f"{kind[4:]} ({n} Fenster)" if n > 1 else kind[4:])
        else:
            parts.append(f"{n}× {kind}" if n > 1 else kind)
    head = f"{category}: {customer}" if customer else category
    return f"{head} – {', '.join(parts[:4])}" if parts else head


def _details(items):
    names = []
    for e in items:
        name = (e.get("customer_name") or "").strip()
        if name and name not in names:
            names.append(name)
    text = "; ".join(names[:6])
    if len(names) > 6:
        text += f" (+{len(names) - 6} weitere)"
    return text


def classify(entries, pc_entries, rules, gap_minutes=5, min_minutes=2, keywords=None):
    """Einträge eines Tages per Regel zu Tätigkeitsblöcken einordnen.

    entries:    Verbindungen, Telefonate, Zugangsdaten … (Timeline-Format,
                "start"/"end" als 'JJJJ-MM-TT hh:mm:ss', "type", "customer_name", "details")
    pc_entries: aktive Fenster (wie TimelineView.pc_entries_for: "app", Titel in "customer_name")
    rules:      Liste von Regeln (siehe DEFAULT_RULES), Reihenfolge = Priorität
    gap_minutes: Lücken bis zu dieser Länge werden innerhalb eines Blocks überbrückt
    min_minutes: kürzere Blöcke fallen weg
    keywords:   customers.Index für Stichwörter der Kundenliste (siehe match_entry)

    Ergebnis: Blöcke im Timeline-Format, nach Start sortiert, ohne Überschneidungen.
    """
    compiled = _compile_rules(rules)
    if not compiled:
        return []

    items = []  # (start, end, prio, key, tier, entry)
    cache = {}
    for tier, source in ((0, entries or []), (1, pc_entries or [])):
        for e in source:
            if not isinstance(e, dict) or e.get("type") in SKIP_TYPES:
                continue
            start, end = _parse(e.get("start")), _parse(e.get("end"))
            if start is None or end is None or end <= start:
                continue
            ck = (tier, e.get("app"), e.get("customer_name"), e.get("type"), e.get("details"))
            hit = cache.get(ck, False)
            if hit is False:
                hit = cache[ck] = match_entry(e, compiled, is_pc=tier == 1, keywords=keywords)
            if hit is None:
                continue
            index, rule, customer = hit
            key = (rule["category"].strip(), customer)
            items.append((start, end, (tier, index, start), key, tier, e))
    if not items:
        return []

    gap = max(0, gap_minutes) * 60
    minimum = max(0, min_minutes) * 60
    pieces = _merge(_resolve(items), gap)
    pieces = [p for p in pieces if (p.end - p.start).total_seconds() >= minimum]
    pieces = _merge(pieces, gap)  # nach dem Weglassen kurzer Stücke erneut verbinden

    result = []
    for p in pieces:
        category, customer = p.key
        srcs = sorted(p.items, key=lambda e: str(e.get("start")))
        result.append({
            "start": p.start.strftime(TIME_FMT),
            "end": p.end.strftime(TIME_FMT),
            "type": RESULT_TYPE,
            "category": category,
            "customer_name": customer,
            "description": _describe(category, customer, srcs),
            "details": _details(srcs),
            "duration": _fmt_minutes((p.end - p.start).total_seconds()),
            "is_suggestion": True,
            "rule": True,
            "sources": [{"start": e.get("start"), "end": e.get("end"), "type": e.get("type"),
                         "customer_name": e.get("customer_name", "")} for e in srcs[:50]],
        })
    return result
