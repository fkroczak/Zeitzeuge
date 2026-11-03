"""Tagesabschluss: aus allen Spuren eines Tages fertige Buchungsvorschläge machen (ohne Qt).

Ziel: mit wenig Aufwand rund 90 % der Personalzeit dokumentiert und gebucht. Zeitzeuge legt
dafür alles, was es über den Tag weiß, auf ein Minutenraster und füllt die Personalzeit:

1. Schon in Matrix42 gebucht (Buchungen und Tätigkeiten mit m42_entry): bleibt, wie es ist.
2. Deine eigenen Tätigkeiten (Journal), noch nicht gebucht: fertig, nur noch buchen.
3. Erkannte Spuren in dieser Reihenfolge, jede bekommt nur noch freie Minuten:
   Stufe 1 Verbindungen, Telefonate, Besprechungen, Mails (Themen wie bei den Nachfragen),
   Stufe 2 KI-Vorschläge (bringen einen fertigen Satz mit),
   Stufe 3 Blöcke der Zuordnung ohne KI, Stufe 4 Arbeitsblöcke am PC.
   Stufe 3 und 4 zählen nur in der Personalzeit (PC am Abend ist nicht automatisch Arbeit).
4. Aufeinanderfolgende Minuten mit demselben Kunden (bzw. ohne Kunde: derselben Kategorie)
   werden ein Block. Kurze Lücken (bis gap_minutes) in der Personalzeit gehören zum Block
   davor, sonst zum Block danach. Splitter unter min_minutes gehen im Nachbarn auf.
5. Je Block: Kunde und Kategorie (hint), Ticket (ticket_for: Fenstertitel / Matrix42 rund um
   den Block, sonst das zuletzt für den Kunden benutzte Ticket), kurzer Tickettext
   (KI-Satz > Regeltext > aus den Spuren zusammengesetzt).
6. Was in der Personalzeit dann noch frei ist (ab min_minutes), steht als „Nicht zugeordnet“
   da: ohne Haken, du kannst Kunde, Ticket und Text direkt eintragen.

Das Ergebnis sind nur Vorschläge. Gespeichert und gebucht wird erst im Fenster
(day_close_dialog.py), wenn du es bestätigst.

Zeiten als Text "JJJJ-MM-TT hh:mm:ss" wie überall, intern als Minuten des Tages.
"""
import re
from datetime import datetime, timedelta

TIME_FMT = "%Y-%m-%d %H:%M:%S"
DAY_MINUTES = 24 * 60
GAP_MINUTES = 10   # kürzere Lücken in der Personalzeit gehören zum Nachbarblock
MIN_MINUTES = 5    # kürzere Blöcke gehen im Nachbarn auf, kürzere freie Zeit fällt weg
HISTORY_DAYS = 14  # so weit zurück zählt „zuletzt für den Kunden benutzt“ (Ticket)
TEXT_LIMIT = 120   # zusammengesetzte Tickettexte höchstens so lang

GUESSED = "zuletzt für den Kunden"  # Quelle eines vermuteten Tickets
KIND_DOC = "doc"      # eigene Tätigkeit, noch nicht gebucht
KIND_DRAFT = "draft"  # aus Spuren vorbereitet
KIND_GAP = "gap"      # Personalzeit ohne Spur

TIER_NAMES = {1: "Verbindung/Telefonat", 2: "KI-Vorschlag", 3: "Zuordnung ohne KI", 4: "PC-Aktivität"}


def _t(text):
    return datetime.strptime(str(text)[:19], TIME_FMT)


def _minute(day, value):
    """datetime -> Minute des Tages (0 … 1440), vor/nach dem Tag abgeschnitten."""
    if value <= day:
        return 0
    if value >= day + timedelta(days=1):
        return DAY_MINUTES
    return int((value - day).total_seconds() // 60)


def _minute_up(day, value):
    """Wie _minute, aber angefangene Minuten zählen (Ende einer Spur)."""
    m = _minute(day, value)
    if m < DAY_MINUTES and (value - day).total_seconds() % 60:
        m += 1
    return m


def _span(day, entry):
    try:
        return _minute(day, _t(entry["start"])), _minute_up(day, _t(entry["end"]))
    except (KeyError, TypeError, ValueError):
        return None


def _text(day, minute):
    return (day + timedelta(minutes=minute)).strftime(TIME_FMT)


def _norm(name):
    return " ".join((name or "").split()).casefold()


def hm(minutes):
    """90 -> '1:30 h'"""
    minutes = max(0, int(round(minutes)))
    return f"{minutes // 60}:{minutes % 60:02d} h"


def percent(part, whole):
    return None if whole <= 0 else round(100 * part / whole)


# ------------------------------------------------------------ Texte

def evidence_label(entry, customer=""):
    """Kurzer Name einer Spur für den zusammengesetzten Tickettext (ohne den Kunden selbst)."""
    if entry.get("pc_block"):
        return entry.get("label") or entry.get("category") or entry.get("app") or "Arbeit am PC"
    kind = entry.get("type") or ""
    if entry.get("direction") or "anruf" in kind.lower() or "telefon" in kind.lower():
        return "Telefonat"
    if kind == "Mail gesendet":
        return "E-Mail"
    if kind in ("Termin", "Teams-Besprechung"):
        subject = (entry.get("description") or entry.get("subject") or "").strip()
        return f"Besprechung {subject}".strip() if subject else "Besprechung"
    name = (entry.get("customer_name") or "").strip()
    # „Kanzlei Schmidt - DC01“ -> „DC01“: der Kunde steht schon in der Buchung
    if " - " in name:
        name = name.split(" - ", 1)[1].strip()
    if customer and _norm(name) == _norm(customer):
        name = ""
    short = {"TeamViewer": "TeamViewer", "RDP-Sitzung": "RDP", "RDP-Verbindung": "RDP",
             "SSH-Sitzung": "SSH", "SSH": "SSH", "VPN-Sitzung": "VPN", "VPN": "VPN"}.get(kind, kind)
    if name and name != kind and not name.replace(" ", "").isdigit() and not name.startswith(kind):
        return f"{short} {name}".strip()
    return short or "Tätigkeit"


def compose_text(category, evidence, customer=""):
    """Kurzer Tickettext aus den Spuren eines Blocks: KI-Satz > Regeltext > Zusammenfassung.

    evidence: [(Spur, Minuten im Block)], längste zuerst."""
    for entry, _m in evidence:
        if entry.get("ai") and (entry.get("description") or "").strip():
            return entry["description"].strip()
    for entry, _m in evidence:
        if entry.get("rule") and (entry.get("description") or "").strip():
            return entry["description"].strip()
    labels = []
    for entry, _m in evidence:
        for part in [entry] + [p for p in entry.get("parts") or [] if p is not entry]:
            label = evidence_label(part, customer)
            if label and label not in labels and label != category:
                labels.append(label)
    text = ", ".join(labels[:4])
    if category and text:
        text = f"{category}: {text}"
    text = text or category or "Tätigkeit"
    return text if len(text) <= TEXT_LIMIT else text[:TEXT_LIMIT - 1].rstrip(" ,") + "…"


# ------------------------------------------------------------ Kunden vergleichen, Verlauf

_LEGAL = re.compile(r"\b(gmbh|mbh|ag|kg|ohg|gbr|ug|e\.?\s?k|e\.?\s?v|co|inc|ltd|haftungsbeschränkt|und|&)\b\.?")
_UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def customer_key(name):
    """Vergleichsform eines Kundennamens: ohne Rechtsform, Umlaute, Satzzeichen, Kundennummer.
    'Müller GmbH & Co. KG (10023)' -> 'mueller'"""
    text = re.sub(r"\s*\(\d+\)\s*$", "", name or "").casefold()
    text = _LEGAL.sub(" ", text).translate(_UMLAUT)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def same_customer(a, b):
    """Gleicher Kunde trotz anderer Schreibweise? Gleich, einer im anderen enthalten oder alle
    Wörter des kürzeren Namens stecken im längeren."""
    ka, kb = customer_key(a), customer_key(b)
    if not ka or not kb:
        return False
    if ka == kb or (min(len(ka), len(kb)) >= 4 and (ka in kb or kb in ka)):
        return True
    wa = {w for w in ka.split() if len(w) >= 3}
    wb = {w for w in kb.split() if len(w) >= 3}
    short, long_ = sorted((wa, wb), key=len)
    # alle Wörter des kürzeren Namens im längeren: „Kanzlei Schmidt“ = „Schmidt & Partner
    # Kanzlei“, aber nie „Auto Huber“ = „Bäckerei Huber“ (falsches Ticket wäre teurer)
    return bool(short) and short <= long_ and any(len(w) >= 4 for w in short)


class History:
    """Was du früher gebucht oder eingetragen hast (vor dem Tag, höchstens days Tage zurück).

    ticket(Kunde): zuletzt benutztes Ticket des Kunden (Schreibweise egal).
    customer(Ticket): Kunde, für den das Ticket zuletzt benutzt wurde.
    items: Tätigkeiten aus dem Journal und Matrix42-Buchungen ({start, customer, ticket})."""

    def __init__(self, items=(), before=None, days=HISTORY_DAYS):
        self.by_customer = {}  # Vergleichsform -> (Beginn, Ticket)
        self.by_ticket = {}    # Ticket (groß) -> (Beginn, Kunde)
        limit = (before - timedelta(days=days)).strftime(TIME_FMT) if before else ""
        upper = before.strftime(TIME_FMT) if before else "9999"
        for item in items or []:
            if not isinstance(item, dict):
                continue
            start, ticket = str(item.get("start", "")), (item.get("ticket") or "").strip()
            customer = (item.get("customer") or "").strip()
            if not ticket or (limit and start < limit) or start >= upper:
                continue
            key = customer_key(customer)
            if key and start >= self.by_customer.get(key, ("", ""))[0]:
                self.by_customer[key] = (start, ticket)
            if customer and start >= self.by_ticket.get(ticket.upper(), ("", ""))[0]:
                self.by_ticket[ticket.upper()] = (start, customer)

    def ticket(self, customer):
        key = customer_key(customer)
        if not key:
            return ""
        if key in self.by_customer:
            return self.by_customer[key][1]
        hits = [k for k in self.by_customer if same_customer(k, key)]
        # mehrdeutig (z. B. „Huber“: Auto Huber und Bäckerei Huber): lieber kein Ticket als ein falsches
        return self.by_customer[hits[0]][1] if len(hits) == 1 else ""

    def customer(self, ticket):
        return self.by_ticket.get((ticket or "").strip().upper(), ("", ""))[1]


def last_tickets(recent_items, before=None, days=HISTORY_DAYS):
    """Kunde (Vergleichsform) -> zuletzt benutzte Ticketnummer (siehe History)."""
    return {k: v[1] for k, v in History(recent_items, before, days).by_customer.items()}


# ------------------------------------------------------------ Vorschläge bauen

def build(date_str, work_spans, docs=(), evidence=(), bookings=(), hint=None, ticket_for=None,
          recent=(), gap_minutes=GAP_MINUTES, min_minutes=MIN_MINUTES, internal=None,
          history_bookings=()):
    """Buchungsvorschläge eines Tages.

    work_spans: [(datetime, datetime)] Personalzeit (sonst Arbeitszeit aus den Einstellungen).
    docs: eigene Tätigkeiten des Tages (Journal). evidence: [(Stufe 1–4, Eintrag)].
    bookings: Matrix42-Buchungen des Tages. hint(Eintrag) -> (Kunde, Kategorie).
    ticket_for(start, end) -> (Ticket, Quelle) oder ("", ""). recent: Tätigkeiten der letzten
    Tage, history_bookings: Matrix42-Buchungen der letzten Tage (beides für Ticket je Kunde und
    Kunde je Ticket, nur was vor dem Tag liegt). internal: {"customer", "ticket",
    "category"} für Blöcke ohne Kunde (z. B. internes Ticket), sonst None.

    -> {"rows": [...], "work", "booked", "documented", "proposed" (Minuten in der Personalzeit),
        "percent_now", "percent_after"}
    """
    day = datetime.strptime(date_str, "%Y-%m-%d")
    hint = hint or (lambda e: (e.get("customer_name", ""), e.get("category", "")))
    gap_minutes, min_minutes = max(0, int(gap_minutes)), max(1, int(min_minutes))

    work = [False] * DAY_MINUTES
    for a, b in work_spans or []:
        for m in range(_minute(day, a), _minute(day, b)):
            work[m] = True

    owner = [None] * DAY_MINUTES  # None | "booked" | ("doc", i) | ("ev", i)

    def claim(span, value, work_only=False):
        if not span:
            return 0
        got = 0
        for m in range(*span):
            if owner[m] is None and (work[m] or not work_only):
                owner[m] = value
                got += 1
        return got

    for b in bookings or []:
        claim(_span(day, b), "booked")

    rows = []
    docs = sorted((d for d in docs or [] if isinstance(d, dict) and not d.get("von_pc")),
                  key=lambda d: str(d.get("start", "")))
    for d in docs:
        if str(d.get("start", ""))[:10] != date_str:
            continue
        span = _span(day, d)
        if d.get("m42_entry"):
            claim(span, "booked")
            continue
        if not span or span[1] <= span[0]:
            continue
        length = span[1] - span[0]
        already = sum(1 for m in range(*span) if owner[m] == "booked")
        claim(span, ("doc", len(rows)))
        likely_booked = already >= 0.5 * length  # in Matrix42 schon von Hand gebucht?
        rows.append({
            "kind": KIND_DOC, "start": d["start"], "end": d["end"],
            "customer": d.get("customer", ""), "category": d.get("category", ""),
            "ticket": d.get("ticket", ""), "ticket_source": "Tätigkeit" if d.get("ticket") else "",
            "text": d.get("text", ""), "sources": ["deine Tätigkeit"],
            "confidence": "hoch", "doc_item": d,
            "checked": not likely_booked,
            "note": "zur Zeit ist in Matrix42 schon gebucht" if likely_booked else "",
        })

    history = History(list(recent or []) + list(history_bookings or []), before=day)

    # Spuren: Stufe für Stufe, jede nur auf noch freie Minuten
    ev = []
    for tier, entry in sorted(evidence or [], key=lambda te: (te[0], str(te[1].get("start", "")))):
        span = _span(day, entry)
        if not span or span[1] <= span[0]:
            continue
        customer, category = hint(entry)
        e = {"tier": tier, "entry": entry, "customer": (customer or "").strip(),
             "category": (category or "").strip(), "ticket": "", "customer_source": ""}
        if not e["customer"] and ticket_for:
            # Ohne Kunde (z. B. Ticketarbeit am PC): Ticket aus dem Fenstertitel trennt die Blöcke,
            # und der Verlauf sagt, zu welchem Kunden das Ticket gehört
            e["ticket"] = _ticket_for(ticket_for, _text(day, span[0]), _text(day, span[1]))[0]
            if e["ticket"] and history.customer(e["ticket"]):
                e["customer"], e["customer_source"] = history.customer(e["ticket"]), "aus dem Ticket"
        ev.append(e)
        if not claim(span, ("ev", len(ev) - 1), work_only=tier >= 3):
            ev.pop()  # nichts mehr frei: Spur bringt nichts Neues

    def key_of(value):
        if isinstance(value, tuple) and value[0] == "ev":
            e = ev[value[1]]
            if e["customer"]:
                return ("c", customer_key(e["customer"]) or _norm(e["customer"]))
            return ("k", _norm(e["category"]), e["ticket"].upper())
        return None

    # Läufe bilden: gleiche Kunden-/Kategorie-Schlüssel hintereinander
    runs = []  # {"key", "start", "end", "minutes": {ev-index: Minuten}}
    for m in range(DAY_MINUTES):
        key = key_of(owner[m])
        if key is None:
            continue
        last = runs[-1] if runs else None
        if last and last["key"] == key and _bridgeable(owner, work, last["end"], m, gap_minutes):
            last["end"] = m + 1
        else:
            last = {"key": key, "start": m, "end": m + 1, "minutes": {}}
            runs.append(last)
        last["minutes"][owner[m][1]] = last["minutes"].get(owner[m][1], 0) + 1

    runs = _absorb_small(runs, min_minutes, gap_minutes)
    _fill_gaps(runs, owner, work, gap_minutes)

    for run in runs:
        rows.append(_draft(day, run, ev, ticket_for, history, internal))

    # Personalzeit, die noch frei ist (nicht in einem Lauf aufgegangen)
    taken = [False] * DAY_MINUTES
    for run in runs:
        for m in range(run["start"], run["end"]):
            taken[m] = True
    m = 0
    while m < DAY_MINUTES:
        if work[m] and owner[m] is None and not taken[m]:
            start = m
            while m < DAY_MINUTES and work[m] and owner[m] is None and not taken[m]:
                m += 1
            if m - start >= min_minutes:
                row = {"kind": KIND_GAP, "start": _text(day, start), "end": _text(day, m),
                       "customer": "", "category": "", "ticket": "", "ticket_source": "",
                       "text": "", "sources": [], "confidence": "niedrig", "checked": False,
                       "note": "keine Spur – bei Bedarf ausfüllen"}
                if internal and internal.get("customer"):
                    row.update(customer=internal["customer"], ticket=internal.get("ticket", ""),
                               category=internal.get("category", ""), ticket_source="intern",
                               note="intern (keine Spur)")
                rows.append(row)
        else:
            m += 1

    rows.sort(key=lambda r: (r["start"], r["end"]))
    return summarize(date_str, work_spans, rows, bookings, docs)


def _bridgeable(owner, work, end, m, gap_minutes):
    """Minuten end … m-1 dürfen überbrückt werden: kurz, frei und in der Personalzeit."""
    if m == end:
        return True
    if m - end > gap_minutes:
        return False
    return all(owner[i] is None and work[i] for i in range(end, m))


def _absorb_small(runs, min_minutes, gap_minutes):
    """Läufe unter min_minutes gehen im Nachbarn auf (vorher, sonst nachher), wenn er nah ist."""
    changed = True
    while changed:
        changed = False
        for i, run in enumerate(runs):
            if run["end"] - run["start"] >= min_minutes:
                continue
            prev = runs[i - 1] if i > 0 else None
            nxt = runs[i + 1] if i + 1 < len(runs) else None
            target = None
            if prev and run["start"] - prev["end"] <= gap_minutes:
                target = prev
            elif nxt and nxt["start"] - run["end"] <= gap_minutes:
                target = nxt
            if target is None:
                runs.pop(i)  # allein und winzig: fällt weg
                changed = True
                break
            target["start"], target["end"] = min(target["start"], run["start"]), max(target["end"], run["end"])
            for k, v in run["minutes"].items():
                target["minutes"][k] = target["minutes"].get(k, 0) + v
            runs.pop(i)
            changed = True
            break
    # Nachbarn mit gleichem Schlüssel, die jetzt aneinanderstoßen: zusammenlegen
    merged = []
    for run in runs:
        if merged and merged[-1]["key"] == run["key"] and run["start"] - merged[-1]["end"] <= gap_minutes:
            last = merged[-1]
            last["end"] = max(last["end"], run["end"])
            for k, v in run["minutes"].items():
                last["minutes"][k] = last["minutes"].get(k, 0) + v
        else:
            merged.append(run)
    runs[:] = merged
    return runs


def _fill_gaps(runs, owner, work, gap_minutes):
    """Kurze freie Personalzeit direkt nach einem Lauf gehört zu ihm, direkt davor zum nächsten."""
    for i, run in enumerate(runs):
        m = run["end"]
        nxt_start = runs[i + 1]["start"] if i + 1 < len(runs) else DAY_MINUTES
        n = m
        while n < nxt_start and n < DAY_MINUTES and owner[n] is None and work[n]:
            n += 1
        if n > m and n - m <= gap_minutes and (n == nxt_start or not work[n] or owner[n] is not None):
            run["end"] = n
    for i, run in enumerate(runs):
        m = run["start"]
        prev_end = runs[i - 1]["end"] if i > 0 else 0
        n = m
        while n > prev_end and owner[n - 1] is None and work[n - 1]:
            n -= 1
        if n < m and m - n <= gap_minutes and (n == prev_end or not work[n - 1] or owner[n - 1] is not None):
            run["start"] = n


def _internal_fits(internal, category):
    """Internes Ticket für diesen Block? Mit "categories" nur für diese Kategorien (z. B. E-Mail)."""
    if not internal or not internal.get("customer"):
        return False
    wanted = [c for c in internal.get("categories") or [] if c]
    return not wanted or category in wanted


def _ticket_for(ticket_for, start_text, end_text):
    try:
        return ticket_for(_t(start_text), _t(end_text)) or ("", "")
    except (TypeError, ValueError):
        return "", ""


def _draft(day, run, ev, ticket_for, history, internal):
    used = sorted(((ev[i], mins) for i, mins in run["minutes"].items()), key=lambda x: -x[1])
    customers, categories = {}, {}
    for e, mins in used:
        if e["customer"]:
            customers[e["customer"]] = customers.get(e["customer"], 0) + mins
        if e["category"]:
            categories[e["category"]] = categories.get(e["category"], 0) + mins
    customer = max(customers, key=customers.get) if customers else ""
    category = max(categories, key=categories.get) if categories else ""
    start_text, end_text = _text(day, run["start"]), _text(day, run["end"])
    ticket, source = _ticket_for(ticket_for, start_text, end_text) if ticket_for else ("", "")
    customer_source = next((e["customer_source"] for e, _m in used
                            if e["customer_source"] and same_customer(e["customer"], customer)), "")
    owner = history.customer(ticket) if ticket else ""
    if ticket and customer and owner and not same_customer(customer, owner):
        # Gegenprobe: das Ticket gehört laut Verlauf einem anderen Kunden -> nicht vorschlagen
        ticket, source = "", ""
    if ticket and not customer and owner:
        # Ticket im Fenstertitel, Kunde unbekannt: Kunde, für den das Ticket gebucht wurde
        customer, customer_source = history.customer(ticket), "aus dem Ticket"
    if not ticket and customer and history.ticket(customer):
        ticket, source = history.ticket(customer), GUESSED
    note = ""
    if not customer and _internal_fits(internal, category):
        customer = internal["customer"]
        category = category or internal.get("category", "")
        if not ticket:
            ticket, source = internal.get("ticket", ""), "intern"
        note = "intern"
    best_tier = min((e["tier"] for e, _m in used), default=4)
    if (customer and ticket and best_tier <= 2 and not customer_source
            and source not in (GUESSED, "intern")):
        confidence = "hoch"
    elif customer and ticket:
        confidence = "mittel"
    else:
        confidence = "niedrig"
    if not customer:
        note = "Kunde fehlt"
    elif not ticket:
        note = "Ticket fehlt – wird nur dokumentiert"
    elif source == GUESSED:
        note = "Ticket vermutet – bitte prüfen"
    tiers = []
    for e, _m in used:
        name = TIER_NAMES.get(e["tier"], "")
        if name and name not in tiers:
            tiers.append(name)
    return {
        "kind": KIND_DRAFT, "start": start_text, "end": end_text,
        "customer": customer, "category": category, "ticket": ticket, "ticket_source": source,
        "text": compose_text(category, [(e["entry"], m) for e, m in used], customer),
        "sources": tiers, "confidence": confidence, "checked": bool(customer),
        "customer_source": customer_source,
        # vermutet (zuletzt für den Kunden benutzt): wird nur nach ausdrücklicher Bestätigung gebucht
        "ticket_guessed": source == GUESSED,
        "note": note, "evidence": [e["entry"] for e, _m in used],
    }


# ------------------------------------------------------------ Kennzahlen

def _merged_minutes(day, spans, work):
    mark = [False] * DAY_MINUTES
    for a, b in spans:
        for m in range(max(0, a), min(DAY_MINUTES, b)):
            mark[m] = True
    return sum(1 for m in range(DAY_MINUTES) if mark[m] and work[m])


def summarize(date_str, work_spans, rows, bookings=(), docs=()):
    """Kennzahlen zu den Vorschlägen: Personalzeit, schon gebucht, mit den angehakten Zeilen."""
    day = datetime.strptime(date_str, "%Y-%m-%d")
    work = [False] * DAY_MINUTES
    for a, b in work_spans or []:
        for m in range(_minute(day, a), _minute(day, b)):
            work[m] = True
    work_total = sum(work)
    booked = [s for s in (_span(day, b) for b in bookings or []) if s]
    booked += [s for s in (_span(day, d) for d in docs or [] if d.get("m42_entry")) if s]
    documented = [s for s in (_span(day, d) for d in docs or [] if not d.get("m42_entry")) if s]
    chosen = [s for s in (_span(day, r) for r in rows if r.get("checked")) if s]
    booked_m = _merged_minutes(day, booked, work)
    after_m = _merged_minutes(day, booked + chosen, work)
    return {
        "rows": rows, "work": work_total, "booked": booked_m,
        "documented": _merged_minutes(day, booked + documented, work),
        "proposed": after_m,
        "percent_now": percent(booked_m, work_total),
        "percent_after": percent(after_m, work_total),
    }


def to_item(row, source="Tagesabschluss"):
    """Vorschlag -> Tätigkeit fürs Journal (nur für Entwürfe und freie Zeit)."""
    item = {"start": row["start"], "end": row["end"], "customer": row.get("customer", ""),
            "category": row.get("category", ""), "text": row.get("text", ""), "source": source}
    if row.get("ticket"):
        item["ticket"] = row["ticket"]
    return item


def sequence_plans(plans):
    """Buchungen eines Abschlusses ohne Überschneidung: Durch den Abrechnungstakt kann eine
    Buchung über den Beginn der nächsten hinausreichen (10:00–10:07 wird 10:00–10:15, die
    nächste beginnt 10:07). Dann rückt die nächste ans Ende der vorigen; die abgerechnete Dauer
    bleibt gleich. plans: [{start, end, minutes, …}] (datetime), nach Beginn sortiert.
    Ändert die Pläne und gibt sie zurück."""
    previous_end = None
    for p in sorted(plans, key=lambda p: p["start"]):
        if previous_end and p["start"] < previous_end:
            length = p["end"] - p["start"]
            p["start"] = previous_end
            p["end"] = previous_end + length
            p["shifted"] = True
        previous_end = p["end"]
    return plans
