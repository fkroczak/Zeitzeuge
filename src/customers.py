r"""
Kundenliste: Welche Spur gehört zu welchem Kunden (ohne Qt).

Ein Kunde hat einen Namen und beliebig viele Spuren. Eine Spur ist eine Art und ein Wert:

    tv     TeamViewer-ID          "1076789144" (Leerzeichen egal)
    rdm    RDM-Eintrag            Name der Verbindung in RDM (Groß/Klein egal)
    vpn    VPN-Verbindung         Name der Verbindung in Sophos Connect usw. (Groß/Klein egal)
    phone  Telefonnummer          "+49 711 123" = "0711 123" = "0711123"
    mail   E-Mail-Domain          "@kunde.de" oder "kunde.de", gilt auch für mail.kunde.de
    net    Netzwerk / WLAN        Name des Netzwerks beim Kunden, z. B. "Mueller-Gast"
    word   Stichwort              Text in Fenstertitel, Betreff oder Name, z. B. "Nordhafen"
                                  oder "SWN-" (Groß/Klein und Umlaute egal). Greift nur, wenn
                                  keine genauere Spur passt; längere Stichwörter gehen vor.
    path   Ordner / Dateipfad     "E:\Kundenprojekte\Avangard": steht der Pfad oder sein letzter
                                  Teil („Avangard“) im Fenstertitel (Explorer, Word, VS Code …)
    host   Rechnername / Host     "srv01", "*.kunde.local" oder "fw-??": Name einer Verbindung
                                  (RDP, SSH, RDM) oder im Fenstertitel; * und ? als Platzhalter
    ip     IP-Adresse / -Bereich  "10.20.0.0/16" oder "192.168.5.10" (CIDR), in Verbindungen
                                  und Fenstertiteln

Wie Stichwörter greifen Pfad, Host und IP nur, wenn keine genauere Spur passt (Reihenfolge:
IP, Host, Pfad, Stichwort).

Ablage: config["customers"] = [{"name": "Müller GmbH", "number": "K-10234",
"calendar": True, "address": "Hauptstr. 5, 70173 Stuttgart", "travel_minutes": 25,
"traces": [{"kind", "value"}]}]. number (Kundennummer), calendar (Termine über die
Mail-Domains zuordnen, Standard an), address und travel_minutes (Fahrzeit vom Büro, von
Hand oder über OpenStreetMap berechnet, siehe route.py) sind optional.
Wie teamviewer_names sind das Nutzdaten: main_timeline.save_config legt sie verschlüsselt in
die Datenbank (Ablage "kunden"), nicht in zeitzeuge_config.json.

teamviewer_names (TeamViewer-ID -> Name) bleibt erhalten und wird gespiegelt: Jede
TeamViewer-Spur der Kundenliste steht auch dort, und jede dort benannte ID erscheint als
Spur in der Kundenliste (customer_list). So funktionieren alte Configs, der Export für
einen anderen PC und „TeamViewer-ID benennen …“ unverändert weiter.

Eine Spur gehört höchstens zu einem Kunden. learn() verschiebt sie, wenn nötig.
"""

import fnmatch
import ipaddress
import re

KINDS = {
    "tv": "TeamViewer-ID",
    "rdm": "RDM-Eintrag",
    "vpn": "VPN-Verbindung",
    "phone": "Telefonnummer",
    "mail": "E-Mail-Domain",
    "net": "Netzwerk",
    "word": "Stichwort",
    "path": "Ordner / Dateipfad",
    "host": "Rechnername / Host",
    "ip": "IP-Adresse / -Bereich",
}
KIND_ORDER = ("tv", "phone", "rdm", "vpn", "mail", "net", "word", "path", "host", "ip")
# Arten, die im Text (Fenstertitel, Betreff, Name einer Verbindung) gesucht werden
TEXT_KINDS = ("ip", "host", "path", "word")
# Termine und Teams-Besprechungen: Kunde über Mail-Domain nur, wenn „Kalendertermine“ an ist
CALENDAR_TYPES = {"Termin", "Teams-Besprechung"}
WORD_MIN = 3  # kürzere Stichwörter träfen zu viel

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
    if kind in ("rdm", "vpn", "net"):
        return " ".join(str(value or "").split()).casefold()
    if kind == "word":
        text = fold(value)
        return text if len(text) >= WORD_MIN else ""
    if kind == "path":
        text = fold(value).replace("/", "\\").rstrip("\\ ")
        return text if len(text) >= WORD_MIN else ""
    if kind == "host":
        text = str(value or "").strip().casefold()
        return text if re.fullmatch(r"[a-z0-9*?][a-z0-9.*?_-]*", text) and text.strip("*?.") else ""
    if kind == "ip":
        try:
            return str(ipaddress.ip_network(str(value or "").strip(), strict=False))
        except ValueError:
            return ""
    return ""


_UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def fold(text):
    """Text zum Stichwort-Vergleich: klein, Umlaute ausgeschrieben, Leerzeichen einfach."""
    text = str(text or "").casefold()
    if not text.isascii():  # Umlaute gibt es nur außerhalb von ASCII (translate ist langsam)
        text = text.translate(_UMLAUT)
    return " ".join(text.split())


def clean_value(kind, value):
    """Wert zum Speichern (lesbar, aber ohne überflüssige Leerzeichen)."""
    if kind == "tv":
        return normalize("tv", value)
    if kind in ("mail", "ip", "host"):
        return normalize(kind, value)
    return " ".join(str(value or "").split())


def display(kind, value):
    """Spur für Texte, z. B. 'TeamViewer-ID 1 076 789 144' oder 'RDM-Eintrag „srv01“'."""
    if kind == "tv":
        from grouping import format_tv_id  # grouping ist ohne Qt
        return f"{KINDS['tv']} {format_tv_id(value)}"
    if kind == "mail":
        return f"{KINDS['mail']} „@{value}“"
    if kind == "word":
        return f"{KINDS['word']} „{value}“ (Fenstertitel, Betreff)"
    if kind == "ip":
        return f"IP „{value}“"
    if kind == "host":
        return f"Host „{value}“"
    if kind == "path":
        return f"Ordner „{value}“"
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
        elif kind in ("Netzwerk", "WLAN"):
            found.append(("net", name))
        elif kind == "Browser" and normalize_domain(name.split()[0]):  # Domain aus dem Verlauf
            found.append(("mail", normalize_domain(name.split()[0])))
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
        item = {"name": str(c["name"]).strip(), "traces": traces}
        number = str(c.get("number") or "").strip()
        if number:
            item["number"] = number
        if c.get("calendar") is False:
            item["calendar"] = False
        address = " ".join(str(c.get("address") or "").split())
        if address:
            item["address"] = address
        minutes = travel_minutes(c)
        if minutes is not None:
            item["travel_minutes"] = minutes
        result.append(item)
    return result


def travel_minutes(customer):
    """Fahrzeit zum Kunden in Minuten (eingetragen oder berechnet) oder None."""
    value = customer.get("travel_minutes") if isinstance(customer, dict) else None
    if value is None or value == "":
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


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

_IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
_HOST_TOKEN = re.compile(r"[a-z0-9][a-z0-9._-]*")


def _word_rx(word):
    """Beginnt das Wort mit Buchstabe/Ziffer, passt es nur am Wortanfang
    („Huber“ passt auf „Huber-Server“, nicht auf „Schuber“)."""
    return re.compile((r"(?<![0-9a-z])" if word[0].isalnum() else "") + re.escape(word))


class Index:
    """Schnelle Abfrage Spur -> Kunde (einmal bauen, für viele Einträge nutzen)."""

    def __init__(self, customers, tv_names=None):
        self.exact = {}
        self.domains = {}
        self.no_calendar = set()
        words, paths, hosts, nets = {}, {}, {}, []
        for c in customers or []:
            if c.get("calendar") is False:
                self.no_calendar.add(c["name"])
            for t in c.get("traces") or []:
                key = normalize(t.get("kind"), t.get("value"))
                if not key:
                    continue
                kind = t["kind"]
                if kind == "mail":
                    self.domains.setdefault(key, c["name"])
                elif kind == "word":
                    words.setdefault(key, c["name"])
                elif kind == "path":
                    paths.setdefault(key, c["name"])
                elif kind == "host":
                    hosts.setdefault(key, c["name"])
                elif kind == "ip":
                    nets.append((ipaddress.ip_network(key), key, c["name"]))
                else:
                    self.exact.setdefault((kind, key), c["name"])
        # Längere (genauere) Werte zuerst
        self.words = [(_word_rx(w), name, w) for w, name in sorted(words.items(), key=lambda x: -len(x[0]))]
        self.paths = []
        for p, name in sorted(paths.items(), key=lambda x: -len(x[0])):
            last = p.rsplit("\\", 1)[-1]
            self.paths.append((p, last, _word_rx(last) if len(last) >= 4 and last != p else None, name))
        self.hosts = [(h, name) for h, name in sorted(hosts.items(), key=lambda x: (-len(x[0].strip("*?")), x[0]))]
        self.nets = sorted(nets, key=lambda x: -x[0].prefixlen)  # engster Bereich zuerst
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

    def match(self, entry):
        """(Kunde, Art, Wert) der Spur, über die der Eintrag zum Kunden gehört, oder None."""
        calendar = isinstance(entry, dict) and entry.get("type") in CALENDAR_TYPES
        for kind, value in traces_of(entry):
            name = self.lookup(kind, value)
            if name and not (calendar and kind == "mail" and name in self.no_calendar):
                return name, kind, normalize(kind, value)
        if (isinstance(entry, dict) and not entry.get("colleague")
                and not any(entry.get(k) for k in ("doc", "ai", "rule", "m42", "m42_gap", "work"))):
            return self.text_match(entry.get("customer_name") or "")
        return None

    def customer_for(self, entry):
        found = self.match(entry)
        return found[0] if found else ""

    def text_match(self, text):
        """(Kunde, Art, Wert) für IP, Host, Ordner oder Stichwort im Text, sonst None."""
        if not text or not (self.words or self.paths or self.hosts or self.nets):
            return None
        if self.nets:
            for ip in _IPV4.findall(text):
                try:
                    addr = ipaddress.ip_address(ip)
                except ValueError:
                    continue
                for net, key, name in self.nets:
                    if addr in net:
                        return name, "ip", key
        low = text.casefold()
        if self.hosts:
            tokens = _HOST_TOKEN.findall(low)
            for pattern, name in self.hosts:
                wild = "*" in pattern or "?" in pattern
                for tok in tokens:
                    tok = tok.rstrip(".")
                    if (fnmatch.fnmatchcase(tok, pattern) if wild
                            else tok == pattern or tok.startswith(pattern + ".")):
                        return name, "host", pattern
        folded = fold(text)
        slashed = folded.replace("/", "\\") if self.paths else folded
        for path, last, last_rx, name in self.paths:
            if path in slashed or (last_rx and last in folded and last_rx.search(folded)):
                return name, "path", path
        for rx, name, word in self.words:
            # Das Muster ist das Wort selbst (dazu höchstens „Wortanfang“): kommt es gar nicht
            # vor, kann es nicht passen. „in“ ist viel schneller als eine Regex-Suche.
            if word in folded and rx.search(folded):
                return name, "word", word
        return None

    def keyword(self, text):
        """Kunde, dessen Stichwort, Ordner, Host oder IP im Text steht ('' = keiner)."""
        found = self.text_match(text)
        return found[0] if found else ""


def count_hits(index, entries, pc_entries=()):
    """Wie oft jede Spur gegriffen hat: {(Art, normalisierter Wert): Anzahl}.

    entries: Verbindungen, Telefonate, Mails; pc_entries: Fenster der PC-Aktivität
    (Titel und Programm wie in rules.keyword_customer)."""
    hits = {}
    for e in entries or ():
        found = index.match(e)
        if found:
            hits[found[1:]] = hits.get(found[1:], 0) + 1
    for p in pc_entries or ():
        found = index.text_match(f"{p.get('customer_name') or ''} {p.get('app') or ''}")
        if found:
            hits[found[1:]] = hits.get(found[1:], 0) + 1
    return hits


# Schlüssel -> Index: Hinweis unter der Maus fragt sehr oft. Mehrere Plätze, weil Timeline
# (nur eigene Liste) und Hauptfenster (mit übernommenen Daten) abwechselnd fragen; mit nur
# einem Platz wurde der Index dann bei jedem Wechsel neu gebaut.
_index_cache = {}
INDEX_CACHE_SIZE = 4


def index(config, imported_customers=None, imported_tv_names=None):
    """Index aus der eigenen Kundenliste (zuerst) und übernommenen Daten eines anderen PCs.
    Bleiben Liste, TeamViewer-Namen und übernommene Daten gleich, kommt derselbe Index."""
    key = repr((config.get("customers"), config.get("teamviewer_names"),
                imported_customers, imported_tv_names))
    hit = _index_cache.get(key)
    if hit is not None:
        return hit
    own = customer_list(config)
    result = Index(own + _valid_list(imported_customers), imported_tv_names)
    while len(_index_cache) >= INDEX_CACHE_SIZE:
        _index_cache.pop(next(iter(_index_cache)), None)
    _index_cache[key] = result
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
