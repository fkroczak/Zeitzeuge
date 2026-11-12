"""Was die Quellen zu einem Zeitraum sagen (ohne Qt), für „Zeitraum nachtragen“.

Wie in „Companion“: Markierst du in der Timeline einen Zeitraum, zeigt der Dialog, was in
dieser Zeit los war, nach Quelle getrennt:

    Rechner   Excel 25 min · Outlook 10 min · DC01 – Remotedesktop 5 min
    Kalender  Workshop Anforderungen (10:00–11:00)
    Anrufe    Kanzlei Schmidt (0251 123456) 4 min
    Verbindungen  RDP Müller GmbH - TS01 35 min

suggestion() liefert dazu einen Vorschlag (Kunde, Text), wenn ein Termin oder Anruf den
Zeitraum überwiegend füllt.

estimate() wiegt alle Spuren gegeneinander ab und schätzt, für welchen Kunden und in welcher
Kategorie du vermutlich gearbeitet hast, jeweils mit Wahrscheinlichkeit in Prozent:

    Kunde (vermutet)      Jugendhilfe Olsberg 70 % (Anruf Joerg Spiekermann 24 min)
    Kategorie (vermutet)  Zugangsdaten / Sicherheit 45 % · Telefonsupport 25 %

Sobald du etwas in „Tätigkeit“ schreibst, zählt auch dein Text: feste Stichwörter
(„Drucker“, „Kennwort“, „Exchange“) und die Wörter, die du bisher bei einer Kategorie
geschrieben hast (aus dem Journal gelernt).
"""
import re
from datetime import datetime
from urllib.parse import unquote

import rules as rule_engine

TIME_FMT = "%Y-%m-%d %H:%M:%S"
CALENDAR_TYPES = {"Termin", "Teams-Besprechung"}
SKIP_TYPES = {"Mail gesendet", "Mail beantwortet"}
FILE_TYPES = {"Datei geöffnet"}
WEB_TYPES = {"Browser"}
NET_TYPES = {"WLAN", "Netzwerk"}
LABEL_MAX = 40  # längere Namen (Pfade, Fenstertitel) sprengen sonst die Karte


def _short(text, limit=LABEL_MAX):
    """Text auf limit Zeichen kürzen, mit „…“ statt mitten im Wort abgeschnitten."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(" -–·,") + "…"


def _file_name(path):
    """Nur der Dateiname, auch aus Links wie ms-screensketch:edit?filePath=C%3A%5C…"""
    text = unquote(str(path or ""))
    if "filePath=" in text:
        text = text.split("filePath=", 1)[1].split("&", 1)[0]
    name = re.split(r"[\\/]", text.rstrip("\\/"))[-1]
    return _short(name or text)


def _t(text):
    return datetime.strptime(text, TIME_FMT)


def _overlap(entry, start, end):
    """Sekunden, die entry im Zeitraum liegt."""
    try:
        s, e = _t(entry["start"]), _t(entry["end"])
    except (KeyError, ValueError):
        return 0.0
    return max(0.0, (min(e, end) - max(s, start)).total_seconds())


def _min(seconds):
    m = int(round(seconds / 60))
    return f"{m} min" if m < 60 else f"{m // 60}:{m % 60:02d} h"


def _source(entry):
    kind = entry.get("type") or ""
    if "app" in entry or kind.startswith("PC:"):
        return "Rechner"
    if kind in FILE_TYPES:
        return "Dateien"
    if kind in WEB_TYPES:
        return "Web"
    if kind in NET_TYPES:
        return "Netzwerk"
    if kind in CALENDAR_TYPES:
        return "Kalender"
    if entry.get("direction") or "Telefonat" in kind or "Anruf" in kind:
        return "Anrufe"
    return "Verbindungen"


def context(start, end, activities, pc_entries, limit=3):
    """[(Quelle, Text)] für den Zeitraum start–end (datetime), wichtigste Quelle zuerst."""
    if end <= start:
        return []
    groups = {}
    for e in list(pc_entries or ()) + list(activities or ()):
        if e.get("type") in SKIP_TYPES or e.get("doc") or e.get("open") or e.get("work"):
            continue
        sec = _overlap(e, start, end)
        if sec < 30:
            continue
        src = _source(e)
        if src == "Rechner":
            label = (e.get("type") or "PC: ?")[4:].strip() or e.get("app", "")
        elif src == "Kalender":
            label = f"{e.get('customer_name') or 'Termin'} ({e['start'][11:16]}–{e['end'][11:16]})"
        elif src == "Dateien":
            label = _file_name(e.get("customer_name"))
        else:
            label = (f"{e.get('type', '')} " if src == "Verbindungen" else "") + (e.get("customer_name") or "")
        label = _short(label)
        bucket = groups.setdefault(src, {})
        bucket[label.strip()] = bucket.get(label.strip(), 0) + sec
    result = []
    for src in ("Rechner", "Kalender", "Anrufe", "Verbindungen", "Dateien", "Web", "Netzwerk"):
        items = sorted(groups.get(src, {}).items(), key=lambda x: -x[1])
        if not items:
            continue
        # Dateien: Dauer ist nur ein fester Platzhalter, also nur die Namen
        parts = [label if src in ("Kalender", "Dateien") else f"{label} {_min(sec)}"
                 for label, sec in items[:limit]]
        if len(items) > limit:
            parts.append(f"+{len(items) - limit} weitere")
        result.append((src, " · ".join(parts)))
    return result


def suggestion(start, end, activities, index=None):
    """(Kunde, Text) aus einem Termin oder Anruf, der mindestens die Hälfte füllt, sonst None."""
    total = (end - start).total_seconds()
    if total <= 0:
        return None
    best, best_sec = None, 0.0
    for e in activities or ():
        if _source(e) not in ("Kalender", "Anrufe"):
            continue
        sec = _overlap(e, start, end)
        if sec > best_sec:
            best, best_sec = e, sec
    if best is None or best_sec < total / 2:
        return None
    customer = index.customer_for(best) if index else ""
    if _source(best) == "Kalender":
        return customer, best.get("customer_name") or "Termin"
    return customer, "Telefonat"


# ---------------------------------------------------------------- Schätzung

# Wie stark eine Spur auf den Kunden zeigt: Anruf mit bekannter Nummer am stärksten, das
# Netzwerk (oft nur das eigene Büro) am schwächsten
CUSTOMER_WEIGHT = {"Anrufe": 3.0, "Kalender": 2.0, "Verbindungen": 2.0, "Rechner": 1.0}
NET_TYPES = {"Netzwerk", "WLAN"}
NET_WEIGHT = 0.5
# Anteil der Zeit ohne Kundenspur, der gegen jeden Kunden spricht: eine einzelne kurze Spur
# soll nicht gleich 100 % ergeben
UNKNOWN_SHARE = 0.3

# Worte in Fenstertitel, Dateiname oder Verbindung, die sagen, WAS gemacht wurde
# (zählen mehr als das Programm oder die Art des Kontakts)
CATEGORY_WORDS = [
    ("Zugangsdaten / Sicherheit",
     r"kennw[oö]rt|passw[oö]rt|password|fehlversuch|anmeldelog|anmeldeprotokoll|sign-?in-?log"
     r"|\bmfa\b|\b2fa\b|\botp\b|gesperrt|lockout|berechtigung|zugangsdaten|sicherheit"),
    ("Cloud-/M365-Administration",
     r"\bm365\b|microsoft 365|office 365|\bo365\b|\bentra\b|\bazure\b|\bintune\b"
     r"|exchange online|sharepoint|admin\.microsoft|\btenant\b"),
    ("Server-/Netzwerkadministration",
     r"firewall|sophos|fortigate|\bswitch\b|\bdhcp\b|\bdns\b|active directory|\bgpo\b"
     r"|gruppenrichtlinie|hyper-v|vmware|vcenter|veeam|backup|domänencontroller|\bdc0?\d\b"
     r"|drucker|printer|telefonanlage|\brouter\b|\bnas\b|\bwlan\b|access ?point"),
    ("Dokumentation / Ticket", r"dokumentation|\bdoku\b|\bticket|\bmatrix42\b|\bconfluence\b"),
]
WORD_WEIGHT = 3.0
LEARNED_WEIGHT = 3.0
OWN_RULE_WEIGHT = 2.0
DEFAULT_WEIGHT = 1.0
# Standardregeln, die nur sagen WIE (Telefon, Mail, Termin), nicht WAS gemacht wurde
CONTACT_CATEGORIES = {"Telefonsupport", "E-Mail / Kommunikation", "Beratung / Abstimmung"}
CONTACT_WEIGHT = 0.5
HISTORY_SHARE = 0.3  # so viel vom Zeitraum zählt die bisherige Kategorie zum Kunden
# Dein eigener Text sagt am deutlichsten, was du gemacht hast: so viel vom Zeitraum zählt er
TEXT_SHARE = 1.5
# Wörter wie „Kunde“ oder „Tests“ stehen bei jeder Kategorie und sagen nichts
STOP_WORDS = {"und", "oder", "der", "die", "das", "den", "dem", "des", "mit", "für", "auf", "von",
              "bei", "nach", "zum", "zur", "ein", "eine", "einer", "einen", "neu", "neue", "kunde",
              "kunden", "diverse", "test", "tests", "beim", "über", "sowie", "wurde", "wurden"}


def _pct(score, total):
    return int(round(100 * score / total)) if total > 0 else 0


def _pick_category(name, categories):
    """Kategorie aus der eigenen Liste zu name (gleich oder Wortanfang), sonst ''."""
    if categories is None:
        return name
    if name in categories:
        return name
    head = re.split(r"[ /-]", name.casefold(), maxsplit=1)[0]
    return next((c for c in categories if c.casefold().startswith(head)), "")


def _entries(start, end, activities, pc_entries):
    """[(Eintrag, ist PC, Sekunden im Zeitraum)] wie in context()."""
    found = []
    for is_pc, source in ((True, pc_entries or ()), (False, activities or ())):
        for e in source:
            if not isinstance(e, dict) or e.get("type") in SKIP_TYPES:
                continue
            if e.get("doc") or e.get("open") or e.get("work"):
                continue
            sec = _overlap(e, start, end)
            if sec >= 30:
                found.append((e, is_pc or "app" in e, sec))
    return found


def _customer_scores(found, index):
    scores, reasons = {}, {}
    if index is None:
        return scores, reasons
    for e, is_pc, sec in found:
        if e.get("colleague"):
            continue  # Kollege am Telefon sagt nichts über den Kunden
        if is_pc:
            name = index.keyword(f"{e.get('customer_name') or ''} {e.get('app') or ''}")
            src = "Rechner"
        else:
            name = index.customer_for(e)
            src = _source(e)
        if not name:
            continue
        weight = NET_WEIGHT if e.get("type") in NET_TYPES else CUSTOMER_WEIGHT[src]
        score = sec * weight
        scores[name] = scores.get(name, 0.0) + score
        what = {"Anrufe": "Anruf", "Kalender": "Termin", "Rechner": "Fenster"}.get(src, e.get("type") or src)
        label = f"{what} {(e.get('customer_name') or '').strip()}".strip()
        if score > reasons.get(name, ("", 0.0))[1]:
            reasons[name] = (f"{label} {_min(sec)}", score)
    return scores, {k: v[0] for k, v in reasons.items()}


def _category_scores(found, categories, rule_list):
    compiled = rule_engine._compile_rules(rule_list if rule_list is not None
                                          else rule_engine.default_rules())
    defaults = {r["name"] for r in rule_engine.DEFAULT_RULES}
    words = [(re.compile(rx, re.IGNORECASE), cat) for cat, rx in CATEGORY_WORDS]
    scores, reasons = {}, {}

    def add(category, score, why):
        category = _pick_category(category, categories)
        if not category or score <= 0:
            return
        scores[category] = scores.get(category, 0.0) + score
        if score > reasons.get(category, ("", 0.0))[1]:
            reasons[category] = (why, score)

    for e, is_pc, sec in found:
        text = " ".join(str(e.get(k) or "") for k in ("type", "customer_name", "details"))
        name = (e.get("customer_name") or e.get("type") or "").strip()
        hit = next(((rx.search(text), cat) for rx, cat in words if rx.search(text)), None)
        if hit:
            add(hit[1], sec * WORD_WEIGHT, f"„{hit[0].group(0)}“ in {_short(name)}")
        match = rule_engine.match_entry(e, compiled, is_pc=is_pc)
        if not match:
            continue
        rule = match[1]
        category = (rule.get("category") or "").strip()
        if rule.get("learned"):
            weight = LEARNED_WEIGHT
        elif rule.get("name") not in defaults:
            weight = OWN_RULE_WEIGHT
        else:
            weight = CONTACT_WEIGHT if category in CONTACT_CATEGORIES else DEFAULT_WEIGHT
        add(category, sec * weight, f"Regel „{rule.get('name', '')}“")
    return scores, {k: v[0] for k, v in reasons.items()}


def _history_scores(customer, history, categories, total):
    """Kategorien, die du bei diesem Kunden bisher gebucht hast (nach Dauer gewichtet)."""
    if not customer or not history:
        return {}
    seconds = {}
    for item in history:
        if not isinstance(item, dict) or item.get("customer") != customer or not item.get("category"):
            continue
        cat = _pick_category(item["category"], categories)
        if not cat:
            continue
        try:
            sec = (_t(item["end"]) - _t(item["start"])).total_seconds()
        except (KeyError, ValueError):
            continue
        seconds[cat] = seconds.get(cat, 0.0) + max(sec, 60.0)
    all_sec = sum(seconds.values())
    return {cat: total * HISTORY_SHARE * sec / all_sec for cat, sec in seconds.items()} if all_sec else {}


def _words(text):
    return {w for w in re.findall(r"[0-9a-zäöüß]{3,}", (text or "").casefold()) if w not in STOP_WORDS}


def _text_scores(text, categories, history):
    """{Kategorie: Anteil 0..1} aus deinem Text: Stichwörter und gelernte Wörter."""
    words = _words(text)
    if not words:
        return {}, {}
    scores, reasons = {}, {}
    for cat, rx in CATEGORY_WORDS:
        m = re.search(rx, text, re.IGNORECASE)
        cat = _pick_category(cat, categories)
        if m and cat:
            scores[cat] = scores.get(cat, 0.0) + 1.0
            reasons[cat] = f"„{m.group(0)}“ in deinem Text"
    # Gelernt: wie oft stand ein Wort bisher bei welcher Kategorie?
    seen = {}
    for item in history or ():
        if not isinstance(item, dict) or not item.get("category"):
            continue
        cat = _pick_category(item["category"], categories)
        if not cat:
            continue
        for w in _words(item.get("text")) & words:
            seen.setdefault(w, {}).setdefault(cat, 0)
            seen[w][cat] += 1
    for w, per_cat in seen.items():
        n = sum(per_cat.values())
        if n < 2:
            continue  # einmal ist Zufall
        for cat, k in per_cat.items():
            share = k / n
            if share >= 0.5:
                scores[cat] = scores.get(cat, 0.0) + share
                reasons.setdefault(cat, f"„{w}“ schreibst du sonst bei {cat}")
    all_ = sum(scores.values())
    return ({c: v / all_ for c, v in scores.items()} if all_ else {}), reasons


def estimate(start, end, activities, pc_entries, index=None, categories=None, rule_list=None,
             history=None, limit=2, text=""):
    """Vermuteter Kunde und vermutete Kategorie für start–end.

    Ergebnis: {"customers": [(Kunde, Prozent, Grund)], "categories": [(Kategorie, Prozent, Grund)]},
    wahrscheinlichste zuerst. index: customers.Index; categories: eigene Kategorien (nur diese
    werden vorgeschlagen); rule_list: Regeln aus der Config (Standard: Standardregeln);
    history: bisherige Tätigkeiten (Journal.recent_items) für die übliche Kategorie je Kunde
    und die Wörter, die du bei einer Kategorie schreibst; text: was du gerade schreibst.
    """
    total = (end - start).total_seconds()
    result = {"customers": [], "categories": []}
    if total <= 0:
        return result
    found = _entries(start, end, activities, pc_entries)

    scores, reasons = _customer_scores(found, index)
    base = sum(scores.values()) + UNKNOWN_SHARE * total
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    result["customers"] = [(name, _pct(score, base), reasons[name]) for name, score in ranked[:limit]]

    cat_scores, cat_reasons = _category_scores(found, categories, rule_list)
    top = result["customers"][0][0] if result["customers"] and result["customers"][0][1] >= 40 else ""
    for cat, score in _history_scores(top, history, categories, total).items():
        cat_scores[cat] = cat_scores.get(cat, 0.0) + score
        cat_reasons.setdefault(cat, f"bisher bei {top}")
    shares, text_reasons = _text_scores(text, categories, history)
    for cat, share in shares.items():
        cat_scores[cat] = cat_scores.get(cat, 0.0) + share * TEXT_SHARE * total
        cat_reasons[cat] = text_reasons[cat]  # dein Text erklärt es am besten
    all_cat = sum(cat_scores.values())
    ranked = sorted(cat_scores.items(), key=lambda x: -x[1])
    result["categories"] = [(cat, _pct(score, all_cat), cat_reasons[cat]) for cat, score in ranked[:limit]]
    return result


def estimate_rows(found):
    """Zeilen für die Karte „Was die Quellen sagen“ aus estimate()."""
    rows = []
    if found.get("customers"):
        name, pct, why = found["customers"][0]
        text = f"{name} {pct} % ({why})"
        text += "".join(f" · {n} {p} %" for n, p, _w in found["customers"][1:])
        rows.append(("Kunde (vermutet)", text))
    if found.get("categories"):
        name, pct, why = found["categories"][0]
        text = f"{name} {pct} % ({why})"
        text += "".join(f" · {n} {p} %" for n, p, _w in found["categories"][1:])
        rows.append(("Kategorie (vermutet)", text))
    return rows
