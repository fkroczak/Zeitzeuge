"""
Kundenliste aus den Matrix42-Buchungen lernen (ohne Qt).

Was du in Matrix42 gebucht hast, zeigt, zu welchem Kunden eine Spur gehört: Rufst du dieselbe
Nummer immer wieder an, während (oder kurz bevor) du auf „Creacam“ buchst, gehört die Nummer
zu Creacam. Dasselbe gilt für TeamViewer-IDs, RDM-Einträge und VPN-Verbindungen.

discover() liefert zwei Arten von Vorschlägen:
- learn:  Spur ohne Kunden in der Kundenliste -> Kunde (Schreibweise wie in Matrix42).
          Sichere Vorschläge übernimmt Zeitzeuge von selbst (Einstellung customers_auto_learn).
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
    rename = []
    for owner, counts in per_customer.items():
        found = _winner(counts)
        if found and not same_customer(owner, found[0]):
            item = {"name": owner, "to": found[0], "hits": found[1], "total": found[2]}
            if key(item) not in ignored and not any(c["name"] == found[0] for c in customers):
                rename.append(item)
    learn.sort(key=lambda x: -x["hits"])
    rename.sort(key=lambda x: -x["hits"])
    return {"learn": learn, "rename": rename}


def key(item):
    """Schlüssel eines Vorschlags für „schon entschieden“."""
    if "kind" in item:
        return f"learn|{item['kind']}|{cl.normalize(item['kind'], item['value'])}"
    return f"rename|{item['name'].casefold()}|{item['to'].casefold()}"


def describe(item):
    """Kurztext, z. B. 'Telefonnummer „0251 123“ → Creacam GmbH (5 von 6 Buchungen)'."""
    share = f"{item['hits']:g} von {item['total']:g} Buchungen"
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
