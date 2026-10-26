"""
Lernen aus Korrekturen beim Dokumentieren (ohne Qt).

- Kunde geändert: customers.learn merkt den Kunden zur Spur (siehe customers.py).
- Kategorie geändert: rule_for baut daraus eine Regel für die „Zuordnung ohne KI“
  (rules.py, config["rules"]). Angelegt wird sie nur, wenn du es im Dialog anhakst.

Gelernte Regeln tragen "learned": True. Sie stehen vor den allgemeinen Standardregeln,
damit sie greifen, und schlagen beim nächsten Mal auch im Eintragen-Dialog die Kategorie
vor (learned_category). Die Standardregeln ändern den Vorschlag dort nicht.
"""

import re

import rules

_DEFAULT_NAMES = {r["name"] for r in rules.DEFAULT_RULES}
_ONLY_NUMBER = re.compile(r"[+\d\s/-]*")
_GENERIC_TV = re.compile(r"^TeamViewer(\s+\(ID:.*\)|\s+[\d ]+)$")  # Name noch unbekannt


def _subject(entry):
    """(Feld, Wert) für die Regel: Kunde/Verbindung, sonst der Typ. None = nicht lernbar."""
    if not isinstance(entry, dict) or "app" in entry:
        return None
    if any(entry.get(k) for k in ("doc", "ai", "rule", "open", "m42", "m42_gap", "work")):
        return None
    name = (entry.get("customer_name") or "").strip()
    if name and not _ONLY_NUMBER.fullmatch(name) and not _GENERIC_TV.match(name):
        return "customer", name
    kind = (entry.get("type") or "").strip()
    if kind:
        return "type", kind
    return None


def rule_for(entry, category, customer=""):
    """Regel, die einen Eintrag wie entry künftig der Kategorie category zuordnet (oder None).

    Passt genau auf den Kunden/Verbindungsnamen des Eintrags (ohne Groß/Klein), sonst auf
    den Typ. customer: Kunde, den die Regel setzt (leer = Name des Eintrags).
    """
    category = (category or "").strip()
    subject = _subject(entry)
    if not category or subject is None:
        return None
    field, value = subject
    customer = (customer or "").strip().replace("{", "(").replace("}", ")")
    if field == "customer" and customer.casefold() == value.casefold():
        customer = ""  # leer = Name des Eintrags bleibt
    if field == "type":
        # Eine Typ-Regel passt auf alle Einträge dieses Typs (jedes Telefonat, jede
        # unbenannte TeamViewer-Sitzung): nie einen Kunden setzen, nur die Kategorie
        customer = ""
    return {
        "name": f"Gelernt: {value}",
        "field": field,
        "match": f"re:^{re.escape(value)}$",
        "category": category,
        "customer": customer,
        "enabled": True,
        "learned": True,
    }


def describe_rule(rule):
    """Kurztext für die Checkbox, z. B. 'srv01 → Fernwartung'."""
    value = rule["name"].split(": ", 1)[-1]
    return f"{value} → {rule['category']}"


def add_rule(rule_list, rule):
    """Regel einsortieren: nach früher gelernten, vor der ersten Standardregel.

    Gibt (neue Liste, "added" | "updated" | "exists") zurück. Keine Duplikate: gleiche
    Bedingung (Feld + Muster) wird nicht noch einmal angelegt; eine gelernte mit anderer
    Kategorie wird angepasst.
    """
    result = [dict(r) for r in rule_list or [] if isinstance(r, dict)]
    for r in result:
        if r.get("field") == rule["field"] and r.get("match") == rule["match"]:
            same = (r.get("category") == rule["category"]
                    and (r.get("customer") or "") == (rule.get("customer") or ""))
            if same and r.get("enabled", True):
                return result, "exists"
            if r.get("learned"):
                r.update(category=rule["category"], customer=rule.get("customer", ""), enabled=True)
                return result, "updated"
    pos = next((i for i, r in enumerate(result) if r.get("name") in _DEFAULT_NAMES), len(result))
    result.insert(pos, dict(rule))
    return result, "added"


def learned_category(entry, rule_list, categories=None):
    """Kategorie aus gelernten Regeln ('' = keine passt). Standardregeln zählen hier nicht."""
    learned = [r for r in rule_list or [] if isinstance(r, dict) and r.get("learned")]
    if not learned or not isinstance(entry, dict):
        return ""
    hit = rules.match_entry(entry, rules._compile_rules(learned), is_pc="app" in entry)
    if not hit:
        return ""
    category = hit[1]["category"].strip()
    return category if categories is None or category in categories else ""


def subject_text(entry):
    """Name, zu dem eine Regel gelernt werden kann ('' = keiner)."""
    subject = _subject(entry)
    return subject[1] if subject else ""


def doc_hints(entry, config, categories, index=None):
    """Vorschläge fürs Eintragen eines erkannten Eintrags (rein, ohne Qt).

    Ergebnis: {"customer", "category", "trace", "rule_subject"}. index: customers.Index
    (sonst aus der Config gebaut). trace/rule_subject sind None, wenn nichts zu lernen ist
    oder das Lernen in den Einstellungen aus ist.
    """
    import customers as customer_list
    from journal import suggest_category, suggest_customer
    if index is None:
        index = customer_list.index(config)
    category = learned_category(entry, config.get("rules")) or suggest_category(entry, categories)
    trace = customer_list.primary_trace(entry)
    if trace and trace[0] != "tv" and not config.get("customers_learn", True):
        trace = None
    subject = subject_text(entry) if config.get("rules_learn_offer", True) else ""
    return {
        "customer": suggest_customer(entry, config.get("teamviewer_names", {}), index),
        "category": category,
        "trace": trace,
        "rule_subject": subject or None,
    }


def apply_corrections(config, entry, item, remember=False, make_rule=False):
    """Nach dem Speichern: Kunde zur Spur und/oder Regel merken. Ändert config.

    Gibt eine Liste kurzer Meldungen zurück (leer = nichts gemerkt)."""
    import customers as customer_list
    done = []
    trace = customer_list.primary_trace(entry) if entry else None
    customer = (item.get("customer") or "").strip()
    if remember and trace and customer:
        if customer_list.learn(config, trace[0], trace[1], customer):
            done.append(f"{customer_list.display(trace[0], customer_list.clean_value(*trace))} "
                        f"gehört jetzt zu „{customer}“")
    if make_rule and entry:
        rule = rule_for(entry, item.get("category"), customer)
        if rule:
            config["rules"], status = add_rule(config.get("rules"), rule)
            if status != "exists":
                done.append(f"Regel gemerkt: {describe_rule(rule)}")
    return done
