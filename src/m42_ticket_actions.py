"""Aktionen an einem Ticket: kommentieren, E-Mail senden, pausieren, weiterleiten. Rein funktional.

Abfragen wie im Mitschnitt „Ticket ansehen“ vom 17.11.2026 (Matrix42-Weboberfläche):

Kommentar: POST /Journal/Add {ObjectId, Comments (HTML), Publish, EntryType 0, Creator (ich),
  FileIds [], IsFromEditDialog false} -> {"JournalId"}. Publish = für den Melder sichtbar.

E-Mail: POST /email/SendEmail (Antwort 204). Empfänger je Feld als Benutzer-Ids (Users) und als
  Adressen (Emails, mit „;“ getrennt). Signatur: die Objekt-Id der eigenen Signatur. Der Dialog holt
  sie über POST /WidgetCommon/<Mail-Dialog>/<Quelle>/UserInfo.SPSUserClassBase (@id = ich)
  -> EmailSignature, dann POST /entity/fragments (SVMEmailSignatureClassBase) -> ObjectId.
  Absender: support@itm-gruppe.com (DefaultSenderTickets der Systemeinstellungen).
  Betreff wie vom Dialog vorbelegt: „#TCK… - Betreff“.

Pausieren: POST /activity/Pause {ObjectIds, ReminderDate (UTC), Comments, Reason,
  NotEscalateWhilePaused} (204). Gründe: GET /entity/enumeration/SPSCommonPickupObjectStateReason,
  die mit State 203 (angehalten), z. B. 421 „Warten auf Kunde“, 20000 „Termin“.

Weiterleiten: POST /activity/Forward {Tickets [{Item1: Art, Item2: Id}], RoleID, UserID, OlaID,
  Comments} (204). Personen: POST /entity/fragments/forControl (Dialog „Forward“, object-picker2),
  Teams (Rollen): POST /dataQuery/relationItems (SPSScRoleClassBase, object-picker1).
"""
import re
from datetime import datetime, timezone

from m42_booking import API, BookingError
from m42_tickets import description_html

MAIL_DIALOG = "40221732-81ec-c499-2ec5-08d384807f48"          # „E-Mail senden“
MAIL_USER_SOURCE = "2cddcb67-3d9c-44d0-f907-e902ad2d812b"     # UserInfo.SPSUserClassBase (Signatur)
FORWARD_DIALOG = "9a3f6e77-ba97-c276-ac89-08d33aafa4da"       # „Weiterleiten“
MAIL_SENDER = "support@itm-gruppe.com"
PAUSED_STATE = 203
# Falls die Liste aus Matrix42 nicht kommt (Stand Mitschnitt 17.11.2026)
PAUSE_REASONS = [(421, "Warten auf Kunde"), (422, "Warten auf Lieferant"),
                 (424, "Warten auf übergeordnetes Ticket"), (420, "Bekannter Fehler"), (20000, "Termin"),
                 (423, "Sonstige"), (425, "RFC erstellt")]
PAUSE_REASONS_PATH = f"{API}/entity/enumeration/SPSCommonPickupObjectStateReason"
_MAIL = re.compile(r"[^@\s;,<>]+@[^@\s;,<>]+\.[^@\s;,<>]+")


def _need(ticket_id):
    if not ticket_id:
        raise BookingError("Ticket ohne Kennung: bitte die Liste aktualisieren.")


def _text(text, what):
    body = description_html(text)
    if not body:
        raise BookingError(f"Bitte {what} eingeben.")
    return body


# ------------------------------------------------------------ Kommentar

def comment_body(ticket_id, text, creator, public=True):
    _need(ticket_id)
    return {"ObjectId": ticket_id, "Comments": _text(text, "einen Kommentar"), "Publish": bool(public),
            "EntryType": 0, "Creator": creator or None, "FileIds": [], "IsFromEditDialog": False}


# ------------------------------------------------------------ E-Mail

def mail_addresses(text):
    """„a@x.de; B <b@y.de>, c@z.de“ -> ["a@x.de", "b@y.de", "c@z.de"] (jede einmal)."""
    out = []
    for m in _MAIL.findall(text or ""):
        if m.casefold() not in (o.casefold() for o in out):
            out.append(m)
    return out


def _recipients(addresses, users=()):
    return {"Users": list(users), "BusinessPartners": [], "BusinessContacts": [], "Roles": [],
            "Emails": ";".join(addresses)}


def mail_subject(ticket, subject):
    """Betreff wie der Dialog: „#TCK0000050691 - Praktikanten …“."""
    return " - ".join(t for t in (f"#{ticket}" if ticket else "", (subject or "").strip()) if t)


def mail_body(ticket_id, to, subject, text, cc="", signature=None, known_users=None, sender=MAIL_SENDER):
    """to/cc: Adressen als Text. known_users: {Adresse (klein): Benutzer-Id}, z. B. der Melder;
    die gehen wie im Dialog zusätzlich als Benutzer mit."""
    _need(ticket_id)
    to_list, cc_list = mail_addresses(to), mail_addresses(cc)
    if not to_list:
        raise BookingError("Bitte mindestens eine E-Mail-Adresse bei „An“ eingeben.")
    if not (subject or "").strip():
        raise BookingError("Bitte einen Betreff eingeben.")
    known = {k.casefold(): v for k, v in (known_users or {}).items() if k and v}

    def users(addresses):
        return [known[a.casefold()] for a in addresses if a.casefold() in known]

    return {"IncidentId": ticket_id, "AddRecipientsToAttachedUsers": False,
            "To": _recipients(to_list, users(to_list)), "CC": _recipients(cc_list, users(cc_list)),
            "IsActiveCC": bool(cc_list), "BCC": _recipients([]), "IsActiveBCC": False,
            "Signature": signature or None, "Subject": subject.strip(), "SendersEmailAddress": sender,
            "Text": _text(text, "einen Text"), "ReplyText": "", "Attachments": None}


def signature_path():
    return f"{API}/WidgetCommon/{MAIL_DIALOG}/{MAIL_USER_SOURCE}/UserInfo.SPSUserClassBase"


def signature_query(user_id):
    return [{"Name": "@id", "Value": user_id, "Type": 1}]


def signature_class_id(data):
    """Antwort von UserInfo.SPSUserClassBase -> Id der Signatur (Klasse) oder None."""
    rows = ((data or {}).get("Entity") or {}).get("SPSUserClassBase") if isinstance(data, dict) else None
    for row in rows or []:
        if isinstance(row, dict) and row.get("EmailSignature"):
            return row["EmailSignature"]
    return None


def signature_fragment_query(signature_id):
    return [{"entityClass": "SVMEmailSignatureClassBase", "ids": [signature_id],
             "dataQueryName": "Email signatures"}]


def signature_object_id(data, signature_id):
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and item.get("Id") == signature_id and item.get("ObjectId"):
            return item["ObjectId"]
    return None


# ------------------------------------------------------------ Pausieren

def pause_reasons(data):
    """Antwort der Aufzählung -> [(Wert, Text)] der Gründe fürs Anhalten, sichtbare zuerst nach Position."""
    values = data.get("Values") if isinstance(data, dict) else None
    out = [(v["Value"], v.get("DisplayString") or str(v["Value"]))
           for v in sorted((v for v in values or [] if isinstance(v, dict)), key=lambda v: v.get("Position") or 0)
           if v.get("State") == PAUSED_STATE and not v.get("Hidden") and isinstance(v.get("Value"), int)]
    return out or list(PAUSE_REASONS)


def _utc(when):
    if when.tzinfo is None:
        when = when.astimezone()  # lokale Zeit
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def pause_body(ticket_id, until, reason, text, no_escalation=True, now=None):
    """until: datetime (lokal), bis wann das Ticket ruht (Erinnerung)."""
    _need(ticket_id)
    if not isinstance(until, datetime):
        raise BookingError("Bitte angeben, bis wann das Ticket pausiert.")
    if until <= (now or datetime.now()):
        raise BookingError("Die Wiedervorlage muss in der Zukunft liegen.")
    if not reason:
        raise BookingError("Bitte einen Grund wählen.")
    return {"ObjectIds": [ticket_id], "ReminderDate": _utc(until), "Comments": _text(text, "einen Kommentar"),
            "Reason": int(reason), "NotEscalateWhilePaused": bool(no_escalation)}


# ------------------------------------------------------------ Weiterleiten

def forward_user_query(text, role_id=None, top=8):
    return {"FilterExpression": {"Path": {"propertyName": "filter-expression", "controlName": "object-picker2",
                                          "widgetId": FORWARD_DIALOG, "viewName": "Forward"},
                                 "Params": [{"Name": "@showAll", "Value": 0, "Type": 2},
                                            {"Name": "@roleID", "Value": role_id, "Type": 1}]},
            "searchFilter": text, "entityClass": "SPSUserClassBase", "top": top, "objectId": None,
            "notStrictAutocomplete": True, "displayString": None}


def roles_query(page_size=200):
    return {"ClientTimeOffset": 0, "EntityClassName": "SPSScRoleClassBase", "EntityTypeName": "SPSSecurityTypeRole",
            "AddedRelations": "", "RemovedRelations": "",
            "AdditionalFilter": {"Conditions": [], "Groups": [{"Conditions": [], "Groups": [], "LogicalOperator": 1},
                                                              {"Conditions": [], "Groups": [], "LogicalOperator": 1}],
                                 "LogicalOperator": 1},
            "Filters": "", "PageSize": page_size, "Page": 0, "Search": "", "OrderBy": "", "Columns": "Name,Description",
            "LookupFor": "", "ResetFilter": False, "SubFilters": "",
            "FilterExpression": {"Path": {"propertyName": "filter-expression", "controlName": "object-picker1",
                                          "widgetId": FORWARD_DIALOG, "viewName": "Forward"},
                                 "Params": [{"Name": "@showAll", "Value": 0, "Type": 2},
                                            {"Name": "@userID", "Value": None, "Type": 1}]}}


def roles(data):
    """Antwort von relationItems -> [{"id", "name"}] nach Namen."""
    out = [{"id": r["Id"], "name": r.get("Sys-DisplayName") or r.get("Name") or ""}
           for r in data if isinstance(r, dict) and r.get("Id")] if isinstance(data, list) else []
    return sorted(out, key=lambda r: r["name"].casefold())


def forward_body(ticket_id, entity_type, user_id=None, role_id=None, text=""):
    _need(ticket_id)
    if not (user_id or role_id):
        raise BookingError("Bitte ein Team oder eine Person wählen.")
    return {"Tickets": [{"Item1": entity_type or "SPSActivityTypeTicket", "Item2": ticket_id}],
            "RoleID": role_id or None, "UserID": user_id or None, "OlaID": None,
            "Comments": description_html(text) or ""}
