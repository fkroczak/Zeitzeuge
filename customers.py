"""
Kundenliste: Welche Spur gehört zu welchem Kunden (ohne Qt).

Ein Kunde hat einen Namen und beliebig viele Spuren. Eine Spur ist eine Art und ein Wert:

    tv     TeamViewer-ID          "1076789144" (Leerzeichen egal)
    rdm    RDM-Eintrag            Name der Verbindung in RDM (Groß/Klein egal)
    vpn    VPN-Verbindung         Name der Verbindung in Sophos Connect usw. (Groß/Klein egal)
    phone  Telefonnummer          "+49 711 123" = "0711 123" = "0711123"
    mail   E-Mail-Domain          "@kunde.de" oder "kunde.de", gilt auch für mail.kunde.de

Ablage: config["customers"] = [{"name": "Müller GmbH", "traces": [{"kind", "value"}]}].
Wie teamviewer_names sind das Nutzdaten: main_timeline.save_config legt sie verschlüsselt in
die Datenbank (Ablage "kunden"), nicht in zeitzeuge_config.json.

teamviewer_names (TeamViewer-ID -> Name) bleibt erhalten und wird gespiegelt: Jede
TeamViewer-Spur der Kundenliste steht auch dort, und jede dort benannte ID erscheint als
Spur in der Kundenliste (customer_list). So funktionieren alte Configs, der Export für
einen anderen PC und „TeamViewer-ID benennen …“ unverändert weiter.

Eine Spur gehört höchstens zu einem Kunden. learn() verschiebt sie, wenn nötig.
"""

import re

KINDS = {
    "tv": "TeamViewer-ID",
    "rdm": "RDM-Eintrag",
    "vpn": "VPN-Verbindung",
    "phone": "Telefonnummer",
    "mail": "E-Mail-Domain",
}
KIND_ORDER = ("tv", "phone", "rdm", "vpn", "mail")

# RDM schreibt "<Protokoll>-Verbindung"/"-Sitzung" und Anzeigen von Zugangsdaten
_RDM_TYPE = re.compile(r"^(RDP|SSH|FTP|Website|TeamViewer|VPN)-(Verbindung|Sitzung)$")
_RDM_CREDS = {"OTP-Anzeige", "Passwortaktion", "Benutzername angezeigt", "Eintrag angezeigt",
              "Zugangsdaten"}
_PHONE_IN_NAME = re.compile(r"\(([+\d\s/-]{3,})\)\s*$")  # "Müller (0711 123)"


# ---------------------------------------------------------------- Normalisieren

def normalize_phone(value):
    """Telefonnummer vergleichbar machen: nur Ziffern, +49/0049 -> 0, +43 -> 0043."""
    text = str(value or "").strip()
    plus = text.startswith("+")
    digits = re.sub(r"\D", "", text)
    if plus:
        digits = "00" + digits
    if digits.startswith("0049"):
        digits = "0" + digits[4:]
    return digits if len(digits) >= 3 else ""


def normalize_domain(value):
    """'Max@Kunde.de', '@kunde.de', 'kunde.de' -> 'kunde.de'."""
    text = str(value or "").strip().lower()
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    text = text.strip(" .<>")
    return text if "." in text and " " not in text else ""


def normalize(kind, value):
    """Wert einer Spur zum Vergleichen ('' = ungültig)."""
    if kind == "tv":
        text = re.sub(r"\s", "", str(value or ""))
        return text if text.isdigit() else ""
    if kind == "phone":
        return normalize_phone(value)
    if kind == "mail":
        return normalize_domain(value)
    if kind in ("rdm", "vpn"):
        return " ".join(str(value or "").split()).casefold()
    return ""


def clean_value(kind, value):
    """Wert zum Speichern (lesbar, aber ohne überflüssige Leerzeichen)."""
    if kind == "tv":
        return normalize("tv", value)
    if kind == "mail":
        return normalize_domain(value)
    return " ".join(str(value or "").split())


def display(kind, value):
    """Spur für Texte, z. B. 'TeamViewer-ID 1 076 789 144' oder 'RDM-Eintrag „srv01“'."""
    if kind == "tv":
        from grouping import format_tv_id  # grouping ist ohne Qt
        return f"{KINDS['tv']} {format_tv_id(value)}"
    if kind == "mail":
        return f"{KINDS['mail']} „@{value}“"
    return f"{KINDS.get(kind, kind)} „{value}“"


# ---------------------------------------------------------------- Spuren eines Eintrags

def traces_of(entry):
    """Spuren eines Timeline-Eintrags: [(Art, Wert wie erkannt)], wichtigste zuerst.

    Kennt die Felder der Leser: tv_id (TeamViewer), Telefonat mit phone/number oder
    "Name (Nummer)" in customer_name (3CX), VPN-Verbindung (Sophos, OpenVPN, RDM),
    RDM-Verbindungen und Zugangsdaten (Name = RDM-Eintrag), dazu optional
    email_domains / email / phone aus anderen Quellen (z. B. Outlook, Teams).
    """
    if not isinstance(entry, dict) or "app" in entry:
        return []
    if any(entry.get(k) for k in ("doc", "ai", "rule", "open", "m42", "m42_gap", "work")):
        return []
    found = []
    if entry.get("tv_id"):
        found.append(("tv", str(entry["tv_id"])))
    kind = entry.get("type") or ""
    name = (entry.get("customer_name") or "").strip()
    phone = entry.get("phone") or entry.get("number")
    if not phone and kind == "Telefonat":
        m = _PHONE_IN_NAME.search(name)
        if m:
            phone = m.group(1)
        elif re.fullmatch(r"[+\d\s/-]{3,}", name):
            phone = name
    if phone and normalize_phone(phone):
        found.append(("phone", str(phone).strip()))
    if name and not entry.get("tv_id"):
        if kind == "VPN-Verbindung":
            found.append(("vpn", name))
            if not entry.get("vpn_source"):  # auch RDM kennt VPN-Einträge
                found.append(("rdm", name))
        elif _RDM_TYPE.match(kind) or kind in _RDM_CREDS:
            found.append(("rdm", name))
    domains = entry.get("email_domains") or []
    if isinstance(domains, str):
        domains = [domains]
    if entry.get("email"):
        domains = list(domains) + [entry["email"]]
    for d in domains:
        if normalize_domain(d):
            found.append(("mail", normalize_domain(d)))
    return found


def primary_trace(entry):
    """Die Spur, unter der ein Kunde gemerkt wird ((Art, Wert) oder None)."""
    found = traces_of(entry)
    return found[0] if found else None


# ---------------------------------------------------------------- Kundenliste

def _valid_list(raw):
    result = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict) or not str(c.get("name") or "").strip():
            continue
        traces = []
        for t in c.get("traces") or []:
            if isinstance(t, dict) and t.get("kind") in KINDS and normalize(t["kind"], t.get("value")):
                traces.append({"kind": t["kind"], "value": clean_value(t["kind"], t["value"])})
        result.append({"name": str(c["name"]).strip(), "traces": traces})
    return result


def _find(customers, name):
    key = name.strip().casefold()
    return next((c for c in customers if c["name"].casefold() == key), None)


def customer_list(config):
    """Kundenliste aus der Config, abgeglichen mit teamviewer_names (ändert config).

    Benannte TeamViewer-IDs erscheinen als Spur beim Kunden mit diesem Namen. Steht eine
    ID dort unter einem anderen Namen, gilt teamviewer_names (wie bisher). Umgekehrt
    steht jede TeamViewer-Spur der Liste auch in teamviewer_names.
    """
    customers = _valid_list(config.get("customers"))
    names = config.get("teamviewer_names")
    if not isinstance(names, dict):
        names = {}
    owner = {t["value"]: c["name"] for c in customers for t in c["traces"] if t["kind"] == "tv"}
    for tv_id, name in list(names.items()):
        tv = normalize("tv", tv_id)
        if not tv or not isinstance(name, str) or not name.strip():
            continue
        if owner.get(tv) != name.strip():  # schon richtig zugeordnet: nichts tun (schnell)
            _assign(customers, "tv", tv, name.strip())
    for c in customers:
        for t in c["traces"]:
            if t["kind"] == "tv" and t["value"] not in names:
                names[t["value"]] = c["name"]
    config["customers"] = customers
    config["teamviewer_names"] = names
    return customers


def _assign(customers, kind, value, name):
    """Spur dem Kunden name geben (Kunde wird angelegt) und bei allen anderen entfernen.
    Gibt True zurück, wenn sich etwas geändert hat."""
    key = normalize(kind, value)
    changed = False
    target = _find(customers, name)
    for c in customers:
        if c is target:
            continue
        before = len(c["traces"])
        c["traces"] = [t for t in c["traces"] if not (t["kind"] == kind
                                                      and normalize(kind, t["value"]) == key)]
        changed |= len(c["traces"]) != before
    if target is None:
        target = {"name": name.strip(), "traces": []}
        customers.append(target)
        changed = True
    if not any(t["kind"] == kind and normalize(kind, t["value"]) == key for t in target["traces"]):
        target["traces"].append({"kind": kind, "value": clean_value(kind, value)})
        changed = True
    return changed


def learn(config, kind, value, name):
    """Spur dem Kunden name zuordnen (Kundenliste und bei TeamViewer auch teamviewer_names)."""
    name = (name or "").strip()
    if kind not in KINDS or not normalize(kind, value) or not name:
        return False
    customers = customer_list(config)
    changed = _assign(customers, kind, value, name)
    if kind == "tv":
        tv = normalize("tv", value)
        if config["teamviewer_names"].get(tv) != name:
            config["teamviewer_names"][tv] = name
            changed = True
    return changed


def forget(config, kind, value):
    """Spur aus der Kundenliste (und teamviewer_names) entfernen. Der Kunde bleibt."""
    customers = customer_list(config)
    key = normalize(kind, value)
    for c in customers:
        c["traces"] = [t for t in c["traces"]
                       if not (t["kind"] == kind and normalize(kind, t["value"]) == key)]
    if kind == "tv":
        config["teamviewer_names"].pop(key, None)


def apply_list(config, customers):
    """Liste aus dem Dialog übernehmen. teamviewer_names folgt genau den TeamViewer-Spuren."""
    customers = _valid_list(customers)
    seen = {}
    for c in customers:  # Spur doppelt: der erste Kunde behält sie
        c["traces"] = [t for t in c["traces"]
                       if seen.setdefault((t["kind"], normalize(t["kind"], t["value"])), c["name"]) == c["name"]]
    config["customers"] = customers
    config["teamviewer_names"] = {t["value"]: c["name"] for c in customers
                                  for t in c["traces"] if t["kind"] == "tv"}
    return customers


# ---------------------------------------------------------------- Abfrage

class Index:
    """Schnelle Abfrage Spur -> Kunde (einmal bauen, für viele Einträge nutzen)."""

    def __init__(self, customers, tv_names=None):
        self.exact = {}
        self.domains = {}
        for c in customers or []:
            for t in c.get("traces") or []:
                key = normalize(t.get("kind"), t.get("value"))
                if not key:
                    continue
                if t["kind"] == "mail":
                    self.domains.setdefault(key, c["name"])
                else:
                    self.exact.setdefault((t["kind"], key), c["name"])
        for tv_id, name in (tv_names or {}).items():  # z. B. von einem anderen PC übernommen
            key = normalize("tv", tv_id)
            if key and isinstance(name, str) and name.strip():
                self.exact.setdefault(("tv", key), name.strip())

    def lookup(self, kind, value):
        key = normalize(kind, value)
        if not key:
            return ""
        if kind != "mail":
            return self.exact.get((kind, key), "")
        parts = key.split(".")
        for i in range(len(parts) - 1):  # mail.kunde.de -> kunde.de
            name = self.domains.get(".".join(parts[i:]))
            if name:
                return name
        return ""

    def customer_for(self, entry):
        for kind, value in traces_of(entry):
            name = self.lookup(kind, value)
            if name:
                return name
        return ""


_index_cache = [None, None]  # (Schlüssel, Index): Hinweis unter der Maus fragt sehr oft


def index(config, imported_customers=None, imported_tv_names=None):
    """Index aus der eigenen Kundenliste (zuerst) und übernommenen Daten eines anderen PCs.
    Bleiben Liste, TeamViewer-Namen und übernommene Daten gleich, kommt derselbe Index."""
    key = repr((config.get("customers"), config.get("teamviewer_names"),
                imported_customers, imported_tv_names))
    if _index_cache[0] == key:
        return _index_cache[1]
    own = customer_list(config)
    result = Index(own + _valid_list(imported_customers), imported_tv_names)
    _index_cache[:] = [key, result]
    return result


def customer_for(entry, customers):
    """Kunde zu einem Eintrag ('' = unbekannt). customers: Index, Kundenliste oder Config."""
    if isinstance(customers, Index):
        return customers.customer_for(entry)
    if isinstance(customers, dict):
        return index(customers).customer_for(entry)
    return Index(customers).customer_for(entry)


def with_customer(entry, index):
    """Text für „Kunde / Verbindung“: 'Müller GmbH · srv01', wenn eine Spur zu einem Kunden
    gehört, der nicht schon im Namen steht. Sonst der Name wie bisher."""
    name = entry.get("customer_name", "") or ""
    if entry.get("tv_id"):  # TeamViewer: Name steht schon da (teamviewer_names)
        return name
    customer = index.customer_for(entry) if index else ""
    if not customer or customer.casefold() in name.casefold():
        return name
    return f"{customer} · {name}" if name else customer
