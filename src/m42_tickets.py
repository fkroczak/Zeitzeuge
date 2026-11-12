"""Tickets in Matrix42 anlegen und schließen: rein funktional, ohne Qt und ohne Edge.

Die Abfragen schickt M42Reader.ticket_task (m42_reader.py) aus dem angemeldeten Edge. Ablauf wie
im Ticket-Mitschnitt vom 12.11.2026:

Anlegen (Dialog „Ticket“, Widget DEFAULT_IDS["ticket_dialog"]):
1. Vorlage: POST /WidgetDialog/GetNewData/<Dialog>, '"objectType=SPSActivityTypeTicket&selectedObjects="'
   -> neue ID, Standardkategorie („Ticketeingang“), InitialData.
2. Kategorie: GET /activity/category/<Id> -> Impact, Urgency.
3. SLA: GET /activity/suitableSLAsForTicket/?Category&User=<Melder>&TicketType&Priority=-1&Impact
   -> TightestItem.
4. Melder: GET /activity/UserDetails/<Id> -> Telefon (Rückruf).
5. Speichern: POST /WidgetDialog/UpdateData/<Dialog> mit dem Ticket. Die Art steht in
   InitialData.Configuration.TicketType (0 = Störung, 6 = Serviceanfrage); Matrix42 macht daraus
   SPSActivityTypeIncident bzw. SPSActivityTypeServiceRequest. Antwort: Sys-Name (TCK…).
6. Übernehmen (Bearbeiter = ich): POST /activity/TakeOver.

Schließen: POST /ticket/CloseWizardInitialData/?ticketType=<Typ> [Id] -> Kategorie, dann
POST /ticket/Close mit Lösungstext (Comments, HTML).

Melder suchen: POST /entity/fragments/forControl (Personenauswahl im Ticketdialog).
Kategorien: POST /entity/tree (ganzer Kategoriebaum).
"""
import html
from urllib.parse import urlencode

from m42_booking import API, BookingError, EMPTY_RELATIONS, wrap

# Kennungen aus dem Mitschnitt (in der Config unter m42_ticket_ids änderbar)
DEFAULT_IDS = {"ticket_dialog": "be4ceef2-aadf-ca41-a130-08d46543427a"}

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


def ticket_entity(template, ticket_type, subject, description, category, initiator, creator,
                  sla=None, impact=None, urgency=None, callback=None):
    """Ticket zum Speichern (UpdateData), Felder wie im Mitschnitt. template: Entity aus GetNewData."""
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


# ------------------------------------------------------------ Schließen

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
