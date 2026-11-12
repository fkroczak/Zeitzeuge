"""In Matrix42 buchen: eine dokumentierte Tätigkeit als Zeiterfassung am Ticket anlegen.

Rein funktional, ohne Qt und ohne Edge. Die Abfragen selbst schickt M42Reader.book
(m42_reader.py) aus dem angemeldeten Edge. Ablauf wie im Buchungs-Mitschnitt vom 02.11.2026,
in dem eine Zeiterfassung im Matrix42-Dialog angelegt wurde:

1. Ticket suchen: POST /WidgetList/GetData/<Ticketliste> mit Filter auf die Ticketnummer
   -> Id des Tickets (ticket_from_search).
2. Vorlage holen: POST /WidgetDialog/GetNewData/<Dialog>, Inhalt
   '"objectType=ITMTimeEntryType&selectedObjects=<Ticket-Id>"' -> neue ID, Kostenstelle,
   Organisationseinheit, Standort.
3. Ticketbezug holen: POST /WidgetCommon/<Dialog>/<Quelle>/custom_Target.ITMTimeEntryClassTarget
   mit [{"Name": "@id", "Value": <Ticket-Id>}] -> Target (ID) und SLA.
4. Speichern: POST /WidgetDialog/UpdateData/<Dialog>, Inhalt '<JSON>' (time_entry) ->
   Sys-Name der neuen Zeiterfassung, z. B. TE0000088403.

Gebucht wird mit Status „Neu“ (10), so wie im Dialog. Freigeben bleibt in Matrix42.
"""
import json
import re
from datetime import datetime, timezone

import billing

AVAILABLE = True
TIME_FMT = "%Y-%m-%d %H:%M:%S"
API = "/m42Services/api"

# Kennungen aus dem Mitschnitt (in der Config unter m42_booking_ids änderbar)
DEFAULT_IDS = {
    "ticket_list": "31db2d14-df00-cddd-4759-08dcbac24c70",   # Ticketsuche im Service Desk
    "dialog": "98661499-140b-ce9b-55da-08dc798f2fc8",        # Dialog „Zeiterfassung“
    "target_source": "b949cab7-a12d-a5bd-b855-d32a6a00074e",  # Datenquelle Ticketbezug
}
STATE_NEW = 10
DEFAULT_ACTIVITY_TYPE = 10  # Administration
ACTIVITY_TYPES = [(10, "Administration")]  # bis Matrix42 die ganze Liste geliefert hat
TICKET_RE = re.compile(r"\bTCK\d{6,}\b", re.I)
EMPTY_RELATIONS = ("RelatedBackupObject", "Memorandums", "RelatedDependentObject", "ShoppingCarts",
                   "Orders", "Tasks", "FormForShoppingCarts", "Representitives", "Service",
                   "WorkflowErrors", "Bookings", "Appointments", "ServiceBookings")


class BookingError(Exception):
    """Buchen ging nicht. Die Meldung ist für den Nutzer gedacht."""


def ids(config):
    """Kennungen aus dem Mitschnitt, einzelne in der Config überschreibbar."""
    custom = (config or {}).get("m42_booking_ids") or {}
    return {k: (custom.get(k) or v) for k, v in DEFAULT_IDS.items()}


def wrap(value):
    """Inhalt so, wie die Matrix42-Dialoge ihn schicken: JSON in einfachen Anführungszeichen."""
    return "'" + json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "'"


def normalize_ticket(text):
    """'tck0000049374 ' -> 'TCK0000049374', '' wenn keine Ticketnummer drin steht."""
    m = TICKET_RE.search(text or "")
    return m.group(0).upper() if m else ""


# ------------------------------------------------------------ Plan aus der Tätigkeit

def plan(item, bill=None, ticket_format=""):
    """Vorschlag für die Buchung einer Tätigkeit aus dem Journal.

    Beginn und Ende im Abrechnungstakt (billing.booking_span: Beginn bleibt, Ende = Beginn +
    abgerechnete Dauer), Text wie beim Kopieren als Ticket-Doku. -> dict
    {ticket, start, end (datetime), minutes, text, customer}"""
    from tickets import format_ticket_text  # erst hier: hält das Modul leicht

    start, end = billing.booking_span(item, bill)
    return {
        "ticket": normalize_ticket(item.get("ticket") or ""),
        "start": start, "end": end,
        "minutes": max(1, int((end - start).total_seconds() // 60)),
        "text": format_ticket_text(item.get("text", ""), ticket_format) or item.get("text", ""),
        "goodwill": bool(item.get("goodwill")), "travel": bool(item.get("travel")),
        "no_surcharge": bool(item.get("no_surcharge")),
        "customer": item.get("customer", ""),
    }


def overlaps(bookings, start, end, ticket=""):
    """Buchungen in Matrix42, die sich mit start–end überschneiden (zum Warnen vor doppeltem
    Buchen). Gleiches Ticket zuerst."""
    found = []
    for b in bookings or []:
        try:
            bs = datetime.strptime(b["start"], TIME_FMT)
            be = datetime.strptime(b["end"], TIME_FMT)
        except (KeyError, ValueError):
            continue
        if bs < end and be > start:
            found.append(b)
    return sorted(found, key=lambda b: b.get("ticket") != ticket)


# ------------------------------------------------------------ Abfragen und Antworten

def ticket_query(number):
    """Filter für die Ticketsuche (wie die Suche im Service Desk, Operator 7 = enthält)."""
    return {"Groups": [{"Groups": [], "LogicalOperator": 1,
                        "Conditions": [{"Property": "TicketNumber", "Operator": 7, "Value": [number]}]},
                       {"Groups": [], "Conditions": [], "LogicalOperator": 1}],
            "Conditions": [], "LogicalOperator": 1}


# Ticketsuche im Buchen-Fenster: je Feld eine Abfrage „enthält“, Treffer zusammengeführt.
# Felder der Ticketliste laut Mitschnitt; Kunde und Benutzer (Melder, Bearbeiter) sind
# Verweise. Geht ein Feld nicht, zählen die übrigen.
SEARCH_FIELDS = ("TicketNumber", "Subject", "Customer", "Initiator", "Recipient")
SEARCH_LIMIT = 50


def search_query(field, text):
    """Filter „field enthält text“ (wie die Suche im Service Desk)."""
    return {"Groups": [{"Groups": [], "LogicalOperator": 1,
                        "Conditions": [{"Property": field, "Operator": 7, "Value": [text]}]},
                       {"Groups": [], "Conditions": [], "LogicalOperator": 1}],
            "Conditions": [], "LogicalOperator": 1}


def _clean(text):
    return re.sub(r"\s+", " ", re.sub(r"\s*\(\d+\)\s*$", "", text or "")).strip()


def ticket_object_id(item):
    """Kennung des Tickets selbst. Die Ticketliste liefert zwei: "Id" ist ein Teil des Tickets
    (SPSActivityClassBase), "Sys-ObjectId" das Ticket. Der Buchungsdialog braucht das Ticket
    (im Mitschnitt: Id e5ee25ff…, Sys-ObjectId daee25ff…, gebucht mit daee25ff…)."""
    return item.get("Sys-ObjectId") or item.get("Id") or ""


def ticket_row(item):
    """Eintrag der Ticketliste -> dict für die Trefferliste (None ohne Nummer/Kennung)."""
    if not isinstance(item, dict):
        return None
    number = (item.get("TicketNumber") or item.get("Sys-Name") or "").upper()
    if not TICKET_RE.fullmatch(number) or not ticket_object_id(item):
        return None
    return {"ticket": number, "id": ticket_object_id(item), "subject": (item.get("Subject") or "").strip(),
            "customer": _clean(item.get("Customer")), "state": (item.get("State") or "").strip(),
            "initiator": _clean(item.get("Initiator")), "recipient": _clean(item.get("Recipient")),
            "created": item.get("CreatedDate") or ""}


# Erledigte Tickets: in der Trefferliste nach den offenen
CLOSED_STATES = ("gelöst", "geschlossen", "abgeschlossen", "storniert", "erledigt", "closed", "resolved")


def is_closed(row):
    return (row.get("state") or "").strip().lower() in CLOSED_STATES


def search_plan(text):
    """Suchtext -> (Wort für Matrix42, Felder). Matrix42 sucht „enthält“ nur nach einem Text:
    bei mehreren Wörtern nach dem längsten, die übrigen filtert matches() danach.
    Nach Ticketnummern nur suchen, wenn Ziffern dabei sind; eine ganze Nummer nur dort."""
    words = (text or "").split()
    if not words:
        return "", ()
    word = max(words, key=len)
    if TICKET_RE.fullmatch(word):
        return word, ("TicketNumber",)
    fields = SEARCH_FIELDS if any(c.isdigit() for c in word) else \
        tuple(f for f in SEARCH_FIELDS if f != "TicketNumber")
    return word, fields


def matches(row, text):
    """Enthält das Ticket (Nummer, Titel, Kunde, Melder, Bearbeiter) jedes Wort des Suchtexts?"""
    hay = " ".join(str(row.get(k) or "") for k in
                   ("ticket", "subject", "customer", "initiator", "recipient", "state")).casefold()
    return all(w.casefold() in hay for w in (text or "").split())


def merge_tickets(*lists, text=""):
    """Treffer mehrerer Abfragen zusammenführen: jedes Ticket einmal, nur die zum ganzen
    Suchtext passenden, offene vor erledigten, darin neueste zuerst."""
    seen = {}
    for items in lists:
        for row in filter(None, map(ticket_row, items or [])):
            if matches(row, text):
                seen.setdefault(row["id"], row)
    rows = sorted(seen.values(), key=lambda r: r["created"], reverse=True)
    rows.sort(key=is_closed)  # stabil: innerhalb offen/erledigt bleibt neueste zuerst
    return rows[:SEARCH_LIMIT]


# ------------------------------------------------------------ Meine Tickets

# Übersicht „Meine Tickets“: offene Tickets, bei denen du Bearbeiter (Recipient) bist.
# Matrix42 filtert „Bearbeiter enthält <Nachname>“, den Rest (ganzer Name, nicht erledigt)
# prüft Zeitzeuge selbst. So viele Seiten liest es höchstens (neueste zuerst).
MY_TICKETS_PAGE_SIZE = 100
MY_TICKETS_PAGES = 5


def own_name(text):
    """'Kroczak, Filip - Systems (3)' -> 'Kroczak, Filip' (Abteilung und Zähler weg)."""
    return _clean(re.sub(r"\s+-\s+.*$", "", _clean(text)))


def _name_words(text):
    return re.findall(r"\w+", (text or "").casefold())


def my_tickets_word(name):
    """Wort, nach dem Matrix42 im Feld Bearbeiter sucht: der Nachname (längstes Wort vor dem
    Komma), '' ohne Namen."""
    name = own_name(name)
    words = _name_words(name.split(",")[0]) or _name_words(name)
    return max(words, key=len) if words else ""


def is_mine(row, name):
    """Bin ich Bearbeiter? Alle Wörter meines Namens stehen im Feld Bearbeiter
    (Reihenfolge egal: 'Kroczak, Filip' passt auf 'Filip Kroczak - Systems')."""
    words = _name_words(own_name(name))
    have = set(_name_words(own_name(row.get("recipient"))))
    return bool(words) and all(w in have for w in words)


def my_open_tickets(items, name):
    """Antworten der Ticketliste -> offene Tickets, bei denen name Bearbeiter ist,
    jedes einmal, neueste zuerst."""
    seen = {}
    for row in filter(None, map(ticket_row, items or [])):
        if is_mine(row, name) and not is_closed(row):
            seen.setdefault(row["id"], row)
    return sorted(seen.values(), key=lambda r: r["created"], reverse=True)


def merge_tickets_rows(rows, text):
    """Schon gefundene Treffer auf einen neuen Suchtext eingrenzen (Reihenfolge bleibt)."""
    return [r for r in rows if matches(r, text)]


def ticket_date(row):
    """'2026-10-05T08:00:00Z' -> '05.10.26' ('' wenn unbekannt)"""
    c = row.get("created") or ""
    return f"{c[8:10]}.{c[5:7]}.{c[2:4]}" if len(c) >= 10 and c[4] == "-" else ""


def ticket_list_label(row):
    """Zeile der Trefferliste: wie ticket_label, dazu das Anlagedatum."""
    return " · ".join(t for t in (ticket_label(row), ticket_date(row)) if t)


def ticket_tooltip(row):
    lines = [ticket_label(row)]
    for name, key in (("Melder", "initiator"), ("Bearbeiter", "recipient")):
        if row.get(key):
            lines.append(f"{name}: {row[key]}")
    if ticket_date(row):
        lines.append(f"Angelegt: {ticket_date(row)}")
    return "\n".join(lines)


def ticket_label(row):
    """'TCK0000049374 · Praktikanten · Systems · In Bearbeitung'"""
    return " · ".join(t for t in (row["ticket"], row["subject"], row["customer"], row["state"]) if t)


def ticket_from_search(items, number):
    """Ticket mit genau dieser Nummer aus der Antwort der Ticketsuche -> dict(id, type,
    subject, customer). BookingError, wenn es nicht (eindeutig) dabei ist."""
    hits = [i for i in items or [] if isinstance(i, dict)
            and (i.get("TicketNumber") or i.get("Sys-Name") or "").upper() == number.upper()]
    if not hits:
        raise BookingError(f"Ticket {number} nicht gefunden.")
    ticket = hits[0]
    if not ticket_object_id(ticket):
        raise BookingError(f"Ticket {number}: Matrix42 liefert keine Kennung.")
    customer = re.sub(r"\s*\(\d+\)\s*$", "", ticket.get("Customer") or "").strip()
    return {"id": ticket_object_id(ticket), "type": ticket.get("Sys-Entity", ""),
            "subject": (ticket.get("Subject") or "").strip(), "customer": re.sub(r"\s+", " ", customer),
            "state": ticket.get("State", "")}


def new_data_body(ticket_id):
    """Inhalt für GetNewData: Text '"objectType=…&selectedObjects=…"' in Anführungszeichen."""
    return wrap(f"objectType=ITMTimeEntryType&selectedObjects={ticket_id}")


def target_body(ticket_id):
    return [{"Name": "@id", "Value": ticket_id, "Type": 1}]


def target_from_response(data):
    """Antwort von custom_Target -> (Target-ID, SLA). BookingError, wenn sie fehlt."""
    try:
        target = (data.get("Entity") or {}).get("ITMTimeEntryClassTarget")[0]
        return target["ID"], target.get("TargetSLA")
    except (AttributeError, IndexError, KeyError, TypeError):
        raise BookingError("Matrix42 liefert keinen Ticketbezug für die Zeiterfassung.") from None


def _utc(value):
    """Lokale Zeit -> '2026-11-02T14:50:00.000Z' (wie der Dialog)."""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


SURCHARGE_REASON = "Zuschlag ignoriert"  # Grund, wenn keiner angegeben ist


def time_entry(template, target, sla, user, start, end, minutes, text,
               activity_type=DEFAULT_ACTIVITY_TYPE, time_zone="Europe/Berlin",
               goodwill=False, travel=False, goodwill_reason="",
               no_surcharge=False, surcharge_reason=""):
    """Zeiterfassung zum Speichern, Felder wie im Mitschnitt. template: Entity aus GetNewData.

    goodwill: Kulanz, die ganze Zeit wird nicht berechnet (IsGoodwill, GoodwillAmount in Minuten,
    Grund Pflicht wie im Dialog). travel: Reise (IsTravel). no_surcharge: Zuschlag ignorieren
    (IgnoreSurcharge, mit Grund)."""
    if not isinstance(template, dict) or not template.get("ID"):
        raise BookingError("Matrix42 liefert keine Vorlage für eine neue Zeiterfassung.")
    if not user:
        raise BookingError("Dein Matrix42-Benutzer ist unbekannt. Bitte den Kalender einmal "
                           "in Zeitzeuge lesen lassen und dann noch einmal buchen.")
    if end <= start:
        raise BookingError("„Bis“ muss nach „Von“ liegen.")
    common = dict(template.get("SPSCommonClassBase") or {})
    for name in EMPTY_RELATIONS:
        common.setdefault(name, {"AddedRelations": [], "RemovedRelations": []})
    base = dict(template.get("ITMTimeEntryClassBase") or {})
    base.update({
        "ActivityType": int(activity_type), "Target": target, "IgnoreSurcharge": False,
        "Start": _utc(start), "End": _utc(end), "User": user, "IsGoodwill": False,
        "GoodwillAmountRounded": 0, "WorktimeRounded": int(minutes), "WorktimeNominal": int(minutes),
        "Description": text, "Pause": 0, "IgnoreSurchargeReason": None, "Approach": None,
        "SLA": sla, "GoodwillReason": None, "Departure": None, "Location": None,
        "IsTravel": bool(travel), "UserTimeZone": time_zone, "GoodwillAmount": None,
    })
    if goodwill:
        base.update({"IsGoodwill": True, "GoodwillAmount": int(minutes),
                     "GoodwillAmountRounded": int(minutes),
                     "GoodwillReason": (goodwill_reason or "").strip() or "Kulanz"})
    if no_surcharge:
        base.update({"IgnoreSurcharge": True,
                     "IgnoreSurchargeReason": (surcharge_reason or "").strip() or SURCHARGE_REASON})
    entity_id = template["ID"]
    return {
        "Sys-Entity": "ITMTimeEntryType", "ID": entity_id, "Sys-IsNew": True,
        "ITMTimeEntryClassSurcharge": list(template.get("ITMTimeEntryClassSurcharge") or []),
        "SPSCommonClassBase": common, "ITMTimeEntryClassBase": base,
        "ITMILVClassBase": {"State": STATE_NEW},
        "_type": "ITMTimeEntryType", "_id": entity_id, "DisplayString": "N/A",
        "_displayName": "N/A", "_name": "N/A", "IsNew": True, "SPSActivityClassUnitOfWork": [],
    }


def saved_entry(data):
    """Antwort von UpdateData -> Nummer der Zeiterfassung (TE…). BookingError ohne Nummer."""
    entity = (data or {}).get("Entity") if isinstance(data, dict) else None
    name = (entity or {}).get("Sys-Name") or ""
    if not name.startswith("TE"):
        raise BookingError("Matrix42 hat die Zeiterfassung nicht bestätigt. Bitte in Matrix42 "
                           "nachsehen, ob sie angelegt wurde.")
    return name


def activity_types(data):
    """Antwort von /entity/enumeration/ITMTimeEntryPickupActivityType -> [(Wert, Name)]."""
    values = (data or {}).get("Values") if isinstance(data, dict) else None
    result = []
    for v in values or []:
        if isinstance(v, dict) and isinstance(v.get("Value"), int) and v.get("DisplayString"):
            result.append((v["Value"], str(v["DisplayString"])))
    return result or list(ACTIVITY_TYPES)
