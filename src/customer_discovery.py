"""
Kundenliste aus den Matrix42-Buchungen lernen (ohne Qt).

Was du in Matrix42 gebucht hast, zeigt, zu welchem Kunden eine Spur gehört: Rufst du dieselbe
Nummer immer wieder an, während (oder kurz bevor) du auf „Creacam“ buchst, gehört die Nummer
zu Creacam. Dasselbe gilt für TeamViewer-IDs, RDM-Einträge und VPN-Verbindungen.

discover() liefert drei Arten von Vorschlägen:
- learn:  Spur ohne Kunden in der Kundenliste -> Kunde (Schreibweise wie in Matrix42).
          Sichere Vorschläge übernimmt Zeitzeuge von selbst (Einstellung customers_auto_learn).
          Dazu Stichwörter: ein Wort aus dem Matrix42-Namen („Tuxhorn“), das in Fenstertiteln
          und Betreffs steht, während du auf diesen Kunden buchst (WORD_* unten).
- suggest: Stichwörter, die passen, aber noch nicht sicher genug sind: Vorschlag in der
          Kundenliste („Neu entdeckt“), übernommen nur auf Klick.
- rename: Kunde der Liste, dessen Spuren fast immer auf einen anders geschriebenen
          Matrix42-Kunden fallen („Holger Tenbrink“ -> „H.Tenbrink Montage GmbH“).
          Das bleibt ein Vorschlag in der Kundenliste, umbenannt wird nur auf Klick.

Sicher heißt: mindestens MIN_HITS Treffer und MIN_SHARE der Treffer beim selben Kunden.
Anrufe von Kollegen zählen nie (colleagues.py).
"""
from datetime import datetime, timedelta

import customers as cl
from day_close import same_customer

TIME_FMT = "%Y-%m-%d %H:%M:%S"
SLACK_MINUTES = 20   # Buchung darf so viel vor oder nach der Spur liegen
MIN_HITS = 3
MIN_SHARE = 0.6
MIN_SECONDS = 30     # kürzere Anrufe/Verbindungen sagen nichts

# Stichwörter (Minuten Fenster/Betreff mit dem Wort, die in Buchungen des Kunden liegen)
WORD_MIN_LEN = 5
WORD_SUGGEST_MINUTES = 10   # ab hier Vorschlag
WORD_AUTO_MINUTES = 30      # ab hier von selbst, wenn auch an WORD_AUTO_DAYS Tagen
WORD_AUTO_DAYS = 2
WORD_AUTO_SHARE = 0.8
# Wörter, die in vielen Firmennamen und Fenstertiteln vorkommen
WORD_STOP = {"systems", "system", "solutions", "service", "services", "gruppe", "group",
             "technik", "technologie", "montage", "beratung", "verwaltung", "stiftung", "partner",
             "international", "deutschland", "germany", "energy", "networks", "network", "design",
             "cloud", "software", "consulting", "management", "holding", "handel", "planung",
             "projekt", "projektplan", "bauunternehmung", "elektro", "elektroanlagen",
             "wirtschaftsberatung", "pflege", "jugendhilfe", "steuerberatung", "kanzlei", "praxis",
             "autohaus", "logistik", "spedition", "immobilien", "stadtwerke", "zahntechnik"}
OUTLOOK_TYPES = ("Termin", "Teams-Besprechung", "Mail gesendet", "Mail beantwortet")


def _t(text):
    try:
        return datetime.strptime(str(text)[:19], TIME_FMT)
    except (TypeError, ValueError):
        return None


def _votes(entries, bookings, colleague=None, slack=SLACK_MINUTES):
    """(Art, Vergleichswert) -> ({Kunde: Stimmen}, Wert wie erkannt)."""
    by_day = {}
    for b in bookings or []:
        start, end, customer = _t(b.get("start")), _t(b.get("end")), (b.get("customer") or "").strip()
        if start and end and customer:
            by_day.setdefault(start.date(), []).append((start, end, customer))
    margin = timedelta(minutes=slack)
    votes = {}
    for e in entries or []:
        if e.get("colleague") or (colleague and colleague.is_colleague(e.get("phone") or "")
                                  and e.get("type") == "Telefonat"):
            continue
        start, end = _t(e.get("start")), _t(e.get("end"))
        if not start or not end:
            continue
        seconds = e.get("duration_s")
        if (seconds if isinstance(seconds, (int, float)) else (end - start).total_seconds()) < MIN_SECONDS:
            continue
        trace = cl.primary_trace(e)
        if not trace:
            continue
        if trace[0] == "vpn" and trace[1].casefold() == str(e.get("vpn_source") or "").casefold():
            continue  # eigene Aufzeichnung ohne Namen („FortiClient“): kein Kunde
        key = (trace[0], cl.normalize(*trace))
        if not key[1]:
            continue
        hits = {c for s, en, c in by_day.get(start.date(), []) if s - margin < end and en + margin > start}
        if not hits:
            continue
        counts, _value = votes.setdefault(key, ({}, trace[1]))
        for c in hits:
            counts[c] = counts.get(c, 0) + 1 / len(hits)
    return votes


def _winner(counts, min_hits=MIN_HITS, min_share=MIN_SHARE):
    """(Kunde, Treffer, gesamt) oder None, wenn nicht sicher genug."""
    total = sum(counts.values())
    if not total:
        return None
    # gleiche Kunden in anderer Schreibweise zusammenzählen
    groups = []
    for name, n in sorted(counts.items(), key=lambda x: -x[1]):
        for g in groups:
            if same_customer(g[0], name):
                g[1] += n
                break
        else:
            groups.append([name, n])
    name, hits = max(groups, key=lambda g: g[1])
    if hits < min_hits or hits / total < min_share:
        return None
    return name, round(hits, 1), round(total, 1)


def _name_words(name):
    """Kennzeichnende Wörter eines Matrix42-Kundennamens (ohne Ort nach dem Komma)."""
    from day_close import customer_key
    head = (name or "").split(",")[0]
    return {w for w in customer_key(head).split() if len(w) >= WORD_MIN_LEN and w not in WORD_STOP}


def _word_votes(entries, bookings, index):
    """Stichwort -> {Kunde: [Minuten, Tage]} aus Fenstertiteln und Betreffs."""
    import re
    names = {(b.get("customer") or "").strip() for b in bookings or []} - {""}
    words = {}
    for name in names:
        for w in _name_words(name):
            words.setdefault(w, set()).add(name)
    if not words:
        return {}
    known = {rx.pattern for rx, _n, _w in index.words}
    patterns = {w: re.compile(r"(?<![0-9a-z])" + re.escape(w)) for w in words}
    by_day = {}
    for b in bookings or []:
        start, end, customer = _t(b.get("start")), _t(b.get("end")), (b.get("customer") or "").strip()
        if start and end and customer:
            by_day.setdefault(start.date(), []).append((start, end, customer))
    votes = {}
    for e in entries or []:
        if "app" not in e and e.get("type") not in OUTLOOK_TYPES:
            continue
        start, end = _t(e.get("start")), _t(e.get("end"))
        if not start or not end or end <= start:
            continue
        text = cl.fold(e.get("customer_name") or "")
        for w, rx in patterns.items():
            if rx.pattern in known or not rx.search(text):
                continue
            for s, en, c in by_day.get(start.date(), []):
                minutes = (min(en, end) - max(s, start)).total_seconds() / 60
                if minutes > 0:
                    v = votes.setdefault(w, {}).setdefault(c, [0.0, set()])
                    v[0] += minutes
                    v[1].add(start.date())
    return {w: v for w, v in votes.items() if any(c in words[w] for c in v)}


def _keyword_items(entries, bookings, customers, index, ignored):
    """(sicher, Vorschläge) für Stichwörter."""
    sure, maybe = [], []
    for word, counts in _word_votes(entries, bookings, index).items():
        total = sum(v[0] for v in counts.values())
        name, (minutes, days) = max(counts.items(), key=lambda x: x[1][0])
        if minutes < WORD_SUGGEST_MINUTES or minutes / total < MIN_SHARE or word not in _name_words(name):
            continue
        owner = next((c["name"] for c in customers if same_customer(c["name"], name)), name)
        item = {"kind": "word", "value": word, "customer": owner,
                "hits": round(minutes), "total": round(total), "unit": "min"}
        if key(item) in ignored:
            continue
        auto = minutes >= WORD_AUTO_MINUTES and len(days) >= WORD_AUTO_DAYS and minutes / total >= WORD_AUTO_SHARE
        (sure if auto else maybe).append(item)
    return sure, maybe


def discover(entries, bookings, customers, colleague=None, ignored=()):
    """Vorschläge {"learn": [...], "rename": [...]} (siehe oben).

    entries:   Einträge mit Spuren (Telefonate, Verbindungen) aus mehreren Tagen
    bookings:  Matrix42-Buchungen derselben Tage ({start, end, customer})
    customers: Kundenliste (cl.customer_list)
    ignored:   schon entschiedene Schlüssel (key()), kommen nicht wieder
    """
    index = cl.Index(customers)
    ignored = set(ignored or ())
    learn, per_customer = [], {}
    for (kind, norm), (counts, value) in _votes(entries, bookings, colleague).items():
        owner = index.lookup(kind, value)
        if owner:  # schon zugeordnet: zählt für die Schreibweise des Kunden
            agg = per_customer.setdefault(owner, {})
            for c, n in counts.items():
                agg[c] = agg.get(c, 0) + n
            continue
        found = _winner(counts)
        if not found:
            continue
        name = next((c["name"] for c in customers if same_customer(c["name"], found[0])), found[0])
        item = {"kind": kind, "value": cl.clean_value(kind, value), "customer": name,
                "hits": found[1], "total": found[2]}
        if key(item) not in ignored:
            learn.append(item)
    words_sure, words_maybe = _keyword_items(entries, bookings, customers, index, ignored)
    learn += words_sure
    rename = []
    for owner, counts in per_customer.items():
        found = _winner(counts)
        if found and not same_customer(owner, found[0]):
            item = {"name": owner, "to": found[0], "hits": found[1], "total": found[2]}
            if key(item) not in ignored and not any(c["name"] == found[0] for c in customers):
                rename.append(item)
    learn.sort(key=lambda x: -x["hits"])
    rename.sort(key=lambda x: -x["hits"])
    words_maybe.sort(key=lambda x: -x["hits"])
    return {"learn": learn, "rename": rename, "suggest": words_maybe}


def key(item):
    """Schlüssel eines Vorschlags für „schon entschieden“."""
    if "kind" in item:
        return f"learn|{item['kind']}|{cl.normalize(item['kind'], item['value'])}"
    return f"rename|{item['name'].casefold()}|{item['to'].casefold()}"


def describe(item):
    """Kurztext, z. B. 'Telefonnummer „0251 123“ → Creacam GmbH (5 von 6 Buchungen)'."""
    share = f"{item['hits']:g} von {item['total']:g} Buchungen"
    if item.get("unit") == "min":
        share = f"{item['hits']:g} von {item['total']:g} min in Buchungen des Kunden"
    if "kind" in item:
        return f"{cl.display(item['kind'], item['value'])} → {item['customer']} ({share})"
    return f"„{item['name']}“ heißt in Matrix42 „{item['to']}“ ({share})"


def auto_apply(config, found):
    """Sichere Spuren in die Kundenliste übernehmen und als entschieden merken (ändert config).
    Gibt die übernommenen Vorschläge zurück."""
    done = config.setdefault("customers_auto", [])
    if not isinstance(done, list):
        done = config["customers_auto"] = []
    applied = []
    for item in found.get("learn", []):
        if cl.learn(config, item["kind"], item["value"], item["customer"]):
            applied.append(item)
        done.append({"key": key(item), "text": describe(item), "status": "gelernt",
                     "date": datetime.now().strftime("%Y-%m-%d")})
    return applied


def decided(config):
    """Schlüssel aller schon entschiedenen Vorschläge."""
    return {d.get("key") for d in config.get("customers_auto") or [] if isinstance(d, dict)}


def mark(config, item, status):
    """Vorschlag als entschieden merken („umbenannt“, „ignoriert“)."""
    config.setdefault("customers_auto", []).append(
        {"key": key(item), "text": describe(item), "status": status,
         "date": datetime.now().strftime("%Y-%m-%d")})


def rename_customer(config, old, new):
    """Kunden umbenennen (mit allen Spuren). Gibt es new schon, wandern die Spuren dorthin."""
    customers = cl.customer_list(config)
    source = next((c for c in customers if c["name"] == old), None)
    if source is None:
        return False
    target = next((c for c in customers if c["name"].casefold() == new.casefold()), None)
    if target is None:
        source["name"] = new
    else:
        target["traces"] += source["traces"]
        customers.remove(source)
    cl.apply_list(config, customers)
    return True
