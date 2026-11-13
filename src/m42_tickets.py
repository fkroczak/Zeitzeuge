"""Tickets in Matrix42 anlegen, bearbeiten und schließen: rein funktional, ohne Qt und ohne Edge.

Die Abfragen schickt M42Reader.ticket_task (m42_reader.py) aus dem angemeldeten Edge. Ablauf wie
im Ticket-Mitschnitt vom 12.11.2026:

Anlegen (Dialog „Ticket“, Widget DEFAULT_IDS["ticket_dialog"]):
1. Vorlage: POST /WidgetDialog/GetNewData/<Dialog>, '"objectType=SPSActivityTypeTicket&selectedObjects="'
   -> neue ID, Standardkategorie („Ticketeingang“), InitialData.
2. Kategorie: GET /activity/category/<Id> -> Impact, Urgency.
3. SLA: GET /activity/suitableSLAsForTicket/?Category&User=<Melder>&TicketType&Priority=-1&Impact
   -> TightestItem.
4. Melder: GET /activity/UserDetails/<Id> -> Telefon (Rückruf); OU, Kostenstelle und Standort des
   Melders (initiator_common), sonst aus GET /data/objects/SPSPersonType/<Id>?full=true. Die
   Vorlage aus 1. hat die eigenen (z. B. Systems); der Dialog setzt sie beim Wählen des Melders
   um. Ohne das gehört das Ticket intern zu Systems, und Zeiterfassungen darauf ebenso.
5. Speichern: POST /WidgetDialog/UpdateData/<Dialog> mit dem Ticket. Die Art steht in
   InitialData.Configuration.TicketType (0 = Störung, 6 = Serviceanfrage); Matrix42 macht daraus
   SPSActivityTypeIncident bzw. SPSActivityTypeServiceRequest. Antwort: Sys-Name (TCK…).
6. Übernehmen (Bearbeiter = ich): POST /activity/TakeOver.

Bearbeiten (Dialog des bestehenden Tickets, DEFAULT_IDS["ticket_edit_dialog"]):
1. Laden: GET /WidgetCommon/GetData/<Dialog>/<Ticket-Id>?archived=false -> ganzes Ticket mit Sys-TimeStamp.
2. Speichern: POST /WidgetDialog/UpdateData/<Dialog> mit dem geladenen Ticket, Sys-EntityState 202,
   Beziehungen leer (AddedRelations/RemovedRelations), geändert nur Betreff und Beschreibung.
   Die Beschreibung wird ergänzt (neue Absätze hinten dran), nie ersetzt: so bleiben Bilder,
   Tabellen und Formatierungen aus Matrix42 erhalten.
Art ändern (Serviceanfrage -> Störung) und Journaleinträge fehlen noch im Mitschnitt.

Schließen: POST /ticket/CloseWizardInitialData/?ticketType=<Typ> [Id] -> Kategorie, dann
POST /ticket/Close mit Lösungstext (Comments, HTML). Beim Öffnen des Fensters holt „close_info“
die Startwerte und das Ticket: ein Lösungstext von früher (Ticket wieder eröffnet) wird vorbelegt.

Melder suchen: POST /entity/fragments/forControl (Personenauswahl im Ticketdialog).
Kategorien: POST /entity/tree (ganzer Kategoriebaum).
"""
import html
import re
from urllib.parse import urlencode

from m42_booking import API, BookingError, EMPTY_RELATIONS, wrap

# Kennungen aus dem Mitschnitt (in der Config unter m42_ticket_ids änderbar)
DEFAULT_IDS = {"ticket_dialog": "be4ceef2-aadf-ca41-a130-08d46543427a",       # Neues Ticket
               "ticket_edit_dialog": "89427fc1-3c2b-c21a-f6dc-08d46550b705"}  # bestehendes Ticket

INCIDENT, SERVICE_REQUEST = 0, 6  # SPSTicketPickupType: 0 Störung, 6 Serviceanfrage (5 Ticket)
TYPES = [(INCIDENT, "Störung (Incident)"), (SERVICE_REQUEST, "Serviceanfrage (Service Request)")]
ENTITY_OF_TYPE = {INCIDENT: "SPSActivityTypeIncident", SERVICE_REQUEST: "SPSActivityTypeServiceRequest"}
CLOSE_REASON = 427  # Abschlussgrund wie im Mitschnitt
USER_STATES_EXCLUDED = [2026, 2024, 2025]  # gesperrte/gelöschte Benutzer (Filter des Dialogs)
EMPTY = {"AddedRelations": [], "RemovedRelations": []}
# Beziehungen, die der Dialog beim Anlegen leer mitschickt
TICKET_RELATIONS = ("AttachedUsers", "RequiredSkills", "GroupTicket", "SimpleServiceForms", "NotifyUsers",
                    "Services", "ParentActivities", "Announcements", "RolesBreachingServiceLevels",
                    "EffectedActivities", "CausedByTickets", "KBArticles", "ChildActivities",
                    "ConfigurationItems", "ChildMergedProblems", "AgentsBreachingServiceLevels")


def ids(config):
    custom = (config or {}).get("m42_ticket_ids") or {}
    return {k: (custom.get(k) or v) for k, v in DEFAULT_IDS.items()}


# ------------------------------------------------------------ ich selbst

def own_user(data):
    """Antwort von GET /userinfo -> {"id", "name"} ('Kroczak, Filip'), None ohne Id."""
    if not isinstance(data, dict) or not data.get("Id"):
        return None
    name = ", ".join(t for t in ((data.get("LastName") or "").strip(), (data.get("FirstName") or "").strip()) if t)
    return {"id": data["Id"], "name": name}


# ------------------------------------------------------------ Melder und Kategorien

def user_query(widget, text, top=20):
    """Personensuche wie im Feld „Melder“ des Ticketdialogs."""
    return {"FilterExpression": {"Path": {"propertyName": "filter-expression", "controlName": "object-picker1",
                                          "widgetId": widget, "viewName": "General"},
                                 "Params": [{"Name": "@stats", "Value": USER_STATES_EXCLUDED, "Type": 2}]},
            "searchFilter": text, "entityClass": "SPSUserClassBase", "top": top, "notStrictAutocomplete": True}


def users_from_fragments(data):
    """Antwort der Personensuche -> [{"id", "name"}], z. B. 'Brüning, Gerd - WiRoPa GmbH'."""
    fragments = data.get("Fragments") if isinstance(data, dict) else None
    out = []
    for f in fragments or []:
        if isinstance(f, dict) and f.get("Id"):
            out.append({"id": f["Id"], "name": " ".join((f.get("DisplayString") or "").split())})
    return out


def tree_query(widget):
    return {"entityClass": "SPSScCategoryClassBase", "parentExpression": "Parent", "includeRoot": True,
            "FilterExpression": {"Path": {"propertyName": "filter-expression", "controlName": "object-picker3",
                                          "widgetId": widget, "viewName": "General"}, "Params": []}}


def categories_from_tree(data):
    """Kategoriebaum -> [{"id", "path"}] mit Pfad 'Visaas > Server > Fileserver', nach Pfad sortiert.
    Matrix42 schreibt die Kinder als "Chidren" (sic), "Children" geht auch."""
    out = []

    def walk(nodes, parents):
        for n in nodes or []:
            if not isinstance(n, dict):
                continue
            path = parents + [(n.get("DisplayString") or "").strip()]
            if n.get("Id"):
                out.append({"id": n["Id"], "path": " > ".join(p for p in path if p)})
            walk(n.get("Chidren") or n.get("Children"), path)
    walk(data if isinstance(data, list) else [], [])
    return sorted(out, key=lambda c: c["path"].casefold())


# ------------------------------------------------------------ Anlegen

def new_ticket_body():
    return wrap("objectType=SPSActivityTypeTicket&selectedObjects=")


def sla_path(category, initiator, ticket_type, impact):
    query = urlencode({"Category": category, "User": initiator, "TicketType": int(ticket_type),
                       "Priority": -1, "Impact": impact if impact is not None else 2})
    return f"{API}/activity/suitableSLAsForTicket/?{query}"


def description_html(text):
    """Klartext -> HTML wie im Editor: jede Zeile ein Absatz."""
    lines = (text or "").strip().splitlines()
    return "".join(f"<p>{html.escape(line) or '&nbsp;'}</p>" for line in lines) or None


COMMON_FIELDS = ("OU", "CostCenter", "Location")  # Kunde, Kostenstelle, Standort


def _ref(value):
    """Verweis in einer Matrix42-Antwort -> Id ('abc' oder {"ID": 'abc'})."""
    if isinstance(value, dict):
        value = value.get("ID") or value.get("Id") or value.get("Value")
    return value if isinstance(value, str) and value.strip() else None


def initiator_common(*answers):
    """OU, Kostenstelle und Standort des Melders aus UserDetails oder dem Personenobjekt
    -> {"OU": …, "CostCenter": …, "Location": …} (nur gefundene). Erste Antwort mit OU gewinnt."""
    aliases = {"OU": ("OU", "OUId", "OrganizationalUnit", "OrganizationalUnitId"),
               "CostCenter": ("CostCenter", "CostCenterId"), "Location": ("Location", "LocationId")}
    for data in answers:
        if not isinstance(data, dict):
            continue
        for source in (data.get("SPSCommonClassBase"), data):
            if not isinstance(source, dict):
                continue
            found = {}
            for field, names in aliases.items():
                value = next((_ref(source.get(n)) for n in names if _ref(source.get(n))), None)
                if value:
                    found[field] = value
            if found.get("OU"):
                return found
    return {}


def ticket_entity(template, ticket_type, subject, description, category, initiator, creator,
                  sla=None, impact=None, urgency=None, callback=None, initiator_ou=None):
    """Ticket zum Speichern (UpdateData), Felder wie im Mitschnitt. template: Entity aus GetNewData.
    initiator_ou: initiator_common() des Melders; ersetzt OU, Kostenstelle und Standort der Vorlage."""
    if not isinstance(template, dict) or not template.get("ID"):
        raise BookingError("Matrix42 liefert keine Vorlage für ein neues Ticket.")
    if int(ticket_type) not in ENTITY_OF_TYPE:
        raise BookingError("Bitte Störung oder Serviceanfrage wählen.")
    if not (subject or "").strip():
        raise BookingError("Bitte einen Betreff eingeben.")
    if not initiator:
        raise BookingError("Bitte den Melder (Ansprechperson beim Kunden) wählen.")
    if not category:
        raise BookingError("Bitte eine Kategorie wählen.")
    if not creator:
        raise BookingError("Dein Matrix42-Benutzer ist unbekannt. Bitte bei Matrix42 anmelden.")
    entity = dict(template)
    base = dict(template.get("SPSActivityClassBase") or {})
    for name in TICKET_RELATIONS:
        base[name] = dict(EMPTY)
    base.update({"Subject": subject.strip(), "DescriptionHTML": description_html(description),
                 "Category": category, "Initiator": initiator, "Creator": creator, "SLA": sla,
                 "NewJournalEntryAdded": False, "isReadonly": False})
    if impact is not None:
        base["Impact"] = impact
    if urgency is not None:
        base["Urgency"] = urgency
    incident = dict(template.get("SPSActivityClassIncident") or {})
    incident["ChildMergedIncidents"] = dict(EMPTY)
    if callback:
        incident["Callback"] = callback
    common = dict(template.get("SPSCommonClassBase") or {})
    common.update({k: v for k, v in (initiator_ou or {}).items() if k in COMMON_FIELDS and v})
    for name in EMPTY_RELATIONS:
        common[name] = dict(EMPTY)
    initial = dict(template.get("InitialData") or {})
    initial["Configuration"] = dict(initial.get("Configuration") or {}, TicketType=int(ticket_type))
    entity.update({"SPSActivityClassBase": base, "SPSActivityClassIncident": incident,
                   "SPSCommonClassBase": common, "InitialData": initial,
                   "ITMTimeEntryClassTarget": {"ITMTimeEntryTarget": dict(EMPTY)},
                   "_type": template.get("Sys-Entity", "SPSActivityTypeTicket"), "_id": template["ID"],
                   "IsNew": True, "TicketTargetType": "", "isEdit": False})
    return entity


def created_ticket(data):
    """Antwort von UpdateData -> {"ticket": 'TCK…', "id", "type"}."""
    entity = (data or {}).get("Entity") if isinstance(data, dict) else None
    if not isinstance(entity, dict) or not entity.get("Sys-Name"):
        raise BookingError("Matrix42 hat das Ticket nicht bestätigt. Bitte in Matrix42 nachsehen.")
    return {"ticket": entity["Sys-Name"], "id": entity.get("ID", ""), "type": entity.get("Sys-Entity", "")}


def take_over_body(ticket_id, entity_type):
    return {"Objects": [{"ObjectIds": [ticket_id], "TypeName": entity_type}]}


# ------------------------------------------------------------ Bearbeiten

ENTITY_STATE_CHANGED = 202  # Sys-EntityState beim Speichern eines geänderten Tickets (Mitschnitt)


def edit_data_path(dialog, ticket_id):
    return f"{API}/WidgetCommon/GetData/{dialog}/{ticket_id}?archived=false"


def loaded_entity(data):
    """Antwort von WidgetCommon/GetData -> Ticket (mit oder ohne Hülle "Entity")."""
    entity = data.get("Entity") if isinstance(data, dict) and isinstance(data.get("Entity"), dict) else data
    if not isinstance(entity, dict) or not entity.get("ID") or not isinstance(entity.get("SPSActivityClassBase"), dict):
        raise BookingError("Matrix42 liefert das Ticket nicht. Bitte die Liste aktualisieren.")
    return entity


def html_text(value):
    """HTML der Beschreibung -> lesbarer Klartext (nur zum Anzeigen)."""
    text = re.sub(r"(?i)<br\s*/?>", "\n", value or "")
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])\s*>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ")
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def stamp(entity):
    """Versionsmarke des Tickets: ändert sich, sobald jemand speichert."""
    base = entity.get("SPSActivityClassBase") or {}
    return f"{entity.get('Sys-TimeStamp', '')}/{base.get('Sys-TimeStamp', '')}"


def ticket_view(entity):
    """Geladenes Ticket -> was das Fenster zeigt."""
    base = entity["SPSActivityClassBase"]
    return {"id": entity["ID"], "ticket": entity.get("Sys-Name", ""), "type": entity.get("Sys-Entity", ""),
            "subject": (base.get("Subject") or "").strip(), "description": html_text(base.get("DescriptionHTML")),
            "stamp": stamp(entity)}


def edited_entity(entity, subject, addition):
    """Ticket zum Speichern: Betreff neu, Beschreibung um addition ergänzt, sonst wie geladen."""
    base = dict(entity["SPSActivityClassBase"])
    subject = (subject or "").strip()
    if not subject:
        raise BookingError("Bitte einen Betreff eingeben.")
    extra = description_html(addition)
    if subject == (base.get("Subject") or "").strip() and not extra:
        raise BookingError("Nichts geändert.")
    base["Subject"] = subject
    if extra:
        base["DescriptionHTML"] = (base.get("DescriptionHTML") or "") + extra
    for name in TICKET_RELATIONS:
        base[name] = dict(EMPTY)
    base.update({"NewJournalEntryAdded": False, "isReadonly": False})
    incident = dict(entity.get("SPSActivityClassIncident") or {})
    incident["ChildMergedIncidents"] = dict(EMPTY)
    common = dict(entity.get("SPSCommonClassBase") or {})
    for name in EMPTY_RELATIONS:
        common[name] = dict(EMPTY)
    out = dict(entity)
    out.update({"SPSActivityClassBase": base, "SPSActivityClassIncident": incident, "SPSCommonClassBase": common,
                "ITMTimeEntryClassTarget": {"ITMTimeEntryTarget": dict(EMPTY)},
                "Sys-EntityState": ENTITY_STATE_CHANGED, "_type": entity.get("Sys-Entity", "SPSActivityTypeTicket"),
                "_id": entity["ID"], "IsNew": False})
    return out


def saved_ticket(data, ticket_id):
    """Antwort von UpdateData beim Bearbeiten: muss dasselbe Ticket zurückgeben."""
    entity = (data or {}).get("Entity") if isinstance(data, dict) else None
    if not isinstance(entity, dict) or entity.get("ID") != ticket_id:
        raise BookingError("Matrix42 hat das Speichern nicht bestätigt. Bitte in Matrix42 nachsehen.")
    return {"ticket": entity.get("Sys-Name", ""), "id": ticket_id, "type": entity.get("Sys-Entity", "")}


# ------------------------------------------------------------ Schließen

# Felder mit einem früheren Lösungstext: in den Startwerten des Schließen-Assistenten „Comments“
# (wie beim Schließen geschickt), im Ticket jedes Feld mit „Solution“ im Namen (z. B. SolutionHTML).
SOLUTION_FIELDS = ("Comments", "SolutionHTML", "SolutionHtml", "Solution")


def previous_solution(initial, entity=None):
    """Lösungstext, den das Ticket schon hat (z. B. vor dem Wiedereröffnen), als Klartext; sonst ""."""
    sources = [(initial, SOLUTION_FIELDS)]
    if isinstance(entity, dict):
        sources += [(entity.get(part), SOLUTION_FIELDS[1:])
                    for part in ("SPSActivityClassBase", "SPSActivityClassIncident")]
    for source, first in sources:
        if not isinstance(source, dict):
            continue
        names = [n for n in first if n in source] + sorted(
            n for n in source if "solution" in n.lower() and n not in first)
        for name in names:
            value = source[name]
            if isinstance(value, str) and html_text(value):
                return html_text(value)
    return ""


def close_body(ticket_id, solution, category, notify_initiator=True, close_related=True,
               reason=CLOSE_REASON):
    """Ticket mit Lösungstext schließen (POST /ticket/Close), Felder wie im Mitschnitt."""
    if not ticket_id:
        raise BookingError("Ticket ohne Kennung: bitte die Liste aktualisieren.")
    if not (solution or "").strip():
        raise BookingError("Bitte einen Lösungstext eingeben.")
    return {"ObjectIds": [ticket_id], "CloseRelatedIncidents": bool(close_related), "RetireAnnouncement": False,
            "AffectedAsset": None, "AffectedService": None, "CausedByTickets": None, "CreateKbArticle": False,
            "Reason": reason, "Comments": description_html(solution), "ServicesAvailability": 10,
            "AssetsAvailability": 10, "SendMailToUsers": False, "ErrorType": 0,
            "SendMailToInitiator": bool(notify_initiator), "NotifyResponsible": None, "ActivityAction": 0,
            "WorkflowInstanceId": None, "CategoryId": category, "KBArticle": None, "InformFurtherUsers": None,
            "SendMailToRelatedResponsibleUsers": False, "SkipFailIfAlreadyClosed": False,
            "ClosureAttachmentFileIDs": None}
