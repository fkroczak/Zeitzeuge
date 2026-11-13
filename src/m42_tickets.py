"""Tickets in Matrix42 anlegen, bearbeiten und schließen: rein funktional, ohne Qt und ohne Edge.

Die Abfragen schickt M42Reader.ticket_task (m42_reader.py) aus dem angemeldeten Edge. Ablauf wie
im Ticket-Mitschnitt vom 12.11.2026:

Anlegen (Dialog „Ticket“, Widget DEFAULT_IDS["ticket_dialog"]):
1. Vorlage: POST /WidgetDialog/GetNewData/<Dialog>, '"objectType=SPSActivityTypeTicket&selectedObjects="'
   -> neue ID, Standardkategorie („Ticketeingang“), InitialData.
2. Kategorie: GET /activity/category/<Id> -> Impact, Urgency.
3. SLA: GET /activity/suitableSLAsForTicket/?Category&User=<Melder>&TicketType&Priority=-1&Impact
   -> TightestItem.
4. Melder: GET /activity/UserDetails/<Id> -> Telefon (Rückruf), OrgUnitId, CostCenterId, LocationId.
   Kunde (OU), Kostenstelle und Standort: Die Vorlage aus 1. hat die eigenen vorbelegt (Systems).
   Der Dialog schickt beim Speichern null, und Matrix42 setzt sie vom Melder (Mitschnitt vom
   13.11.2026: danach OU = OrgUnitId aus UserDetails). Zeitzeuge schickt die Werte aus UserDetails,
   sonst null wie der Dialog, nie die der Vorlage: sonst gehört das Ticket intern zu Systems.
5. Speichern: POST /WidgetDialog/UpdateData/<Dialog> mit dem Ticket. Die Art steht in
   InitialData.Configuration.TicketType (0 = Störung, 6 = Serviceanfrage); Matrix42 macht daraus
   SPSActivityTypeIncident bzw. SPSActivityTypeServiceRequest. Antwort: Sys-Name (TCK…).
6. Übernehmen (Bearbeiter = ich): POST /activity/TakeOver.

Bearbeiten (Dialog des bestehenden Tickets, DEFAULT_IDS["ticket_edit_dialog"]):
1. Laden: GET /WidgetCommon/GetData/<Dialog>/<Ticket-Id>?archived=false -> ganzes Ticket mit Sys-TimeStamp.
2. Speichern: POST /WidgetDialog/UpdateData/<Dialog> mit dem geladenen Ticket, Sys-EntityState 202,
   Beziehungen leer (AddedRelations/RemovedRelations), geändert nur Betreff, Beschreibung und
   Kategorie (Mitschnitt vom 13.11.2026: Betreff geändert, Rest Zeichen für Zeichen wie geladen).
   Beschreibung: Kommt nur Text hinten dazu, wird er als neue Absätze angehängt (Bilder, Tabellen
   und Formatierungen aus Matrix42 bleiben). Sonst ersetzt der Klartext die Beschreibung.
   Kategorie: Der Dialog fragt dazu /activity/suitableSLAsForTicket (wie beim Anlegen) und nimmt
   TightestItem als SLA (ServiceDesk-Einstellung AutoApplyingTightestSLA = 1).
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


GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _ref(value):
    """Verweis in einer Matrix42-Antwort -> Id (GUID als Text oder {"ID": GUID}), sonst None.
    Nur GUIDs: UserDetails liefert neben OrgUnitId auch OrgUnit mit dem Anzeigenamen."""
    if isinstance(value, dict):
        value = (value.get("ID") or value.get("Id") or value.get("ObjectId") or value.get("Sys-ObjectId")
                 or value.get("Value"))
    return value.strip() if isinstance(value, str) and GUID.fullmatch(value.strip()) else None


# Feldnamen je Ziel, die Id-Felder zuerst. UserDetails (Log vom 13.11.2026): OrgUnit/OrgUnitId,
# CostCenter/CostCenterId, Location/LocationId; die Felder ohne Id sind dort Anzeigenamen.
COMMON_ALIASES = {"OU": ("OrgUnitId", "OUId", "OrganizationalUnitId", "OrgUnit", "OU", "OrganizationalUnit"),
                  "CostCenter": ("CostCenterId", "CostCenter"), "Location": ("LocationId", "Location")}


def initiator_common(*answers):
    """OU (Kunde), Kostenstelle und Standort des Melders aus GET /activity/UserDetails
    -> {"OU": …, "CostCenter": …, "Location": …} (nur gefundene). Erste Antwort mit OU gewinnt."""
    for data in answers:
        if not isinstance(data, dict):
            continue
        for source in (data.get("SPSCommonClassBase"), data):
            if not isinstance(source, dict):
                continue
            found = {}
            for field, names in COMMON_ALIASES.items():
                value = next((_ref(source.get(n)) for n in names if _ref(source.get(n))), None)
                if value:
                    found[field] = value
            if found.get("OU"):
                return found
    return {}


def field_overview(data, depth=1):
    """Felder einer Antwort fürs Log, ohne Inhalte: {'Phone': 'str', 'SPSCommonClassBase': {...}}."""
    if isinstance(data, dict):
        if depth < 0:
            return "dict"
        return {k: field_overview(v, depth - 1) for k, v in list(data.items())[:60]}
    if isinstance(data, list):
        return f"list[{len(data)}]"
    return type(data).__name__


def ticket_entity(template, ticket_type, subject, description, category, initiator, creator,
                  sla=None, impact=None, urgency=None, callback=None, initiator_ou=None):
    """Ticket zum Speichern (UpdateData), Felder wie im Mitschnitt. template: Entity aus GetNewData.
    initiator_ou: initiator_common() des Melders. OU, Kostenstelle und Standort kommen von dort, sonst
    null wie im Dialog (Matrix42 setzt sie dann vom Melder), nie aus der Vorlage (eigene OU)."""
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
    common.update({k: (initiator_ou or {}).get(k) or None for k in COMMON_FIELDS})
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


def load_error(error, kind=""):
    """Fehler beim Laden über den Dialog des bestehenden Tickets lesbar machen. Matrix42 meldet
    ObjectIsDeleted („The object you try to open is deleted“), wenn das Ticket gelöscht oder
    archiviert ist oder der Dialog die Art des Tickets nicht öffnen kann."""
    if "ObjectIsDeleted" not in str(error):
        return error
    art = {"SPSActivityTypeIncident": "Störung", "SPSActivityTypeServiceRequest": "Serviceanfrage",
           "SPSActivityTypeTicket": "Ticket"}.get(kind, kind.replace("SPSActivityType", ""))
    return BookingError("Matrix42 kann dieses Ticket hier nicht öffnen (meldet es als gelöscht"
                        + (f", Art: {art}" if art else "") + "). Bitte in Matrix42 bearbeiten.")


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


RICH_HTML = re.compile(r"(?i)<(img|table|ul|ol|a|b|strong|i|em|u|span|font|h[1-6])\b")


def ticket_view(entity):
    """Geladenes Ticket -> was das Fenster zeigt. rich: Beschreibung hat Bilder, Tabellen o. Ä.,
    die beim Ersetzen durch Klartext verloren gingen."""
    base = entity["SPSActivityClassBase"]
    description = base.get("DescriptionHTML") or ""
    return {"id": entity["ID"], "ticket": entity.get("Sys-Name", ""), "type": entity.get("Sys-Entity", ""),
            "subject": (base.get("Subject") or "").strip(), "description": html_text(description),
            "category": base.get("Category"), "rich": bool(RICH_HTML.search(description)),
            "stamp": stamp(entity)}


def ticket_kind(entity):
    """Art des geladenen Tickets für die SLA-Abfrage (0 Störung, 6 Serviceanfrage)."""
    config = ((entity.get("InitialData") or {}).get("Configuration") or {})
    if config.get("TicketType") is not None:
        return int(config["TicketType"])
    return SERVICE_REQUEST if entity.get("Sys-Entity") == ENTITY_OF_TYPE[SERVICE_REQUEST] else INCIDENT


def category_sla_path(entity, category):
    """SLA-Abfrage für eine neue Kategorie des geladenen Tickets; None, wenn sie gleich bleibt."""
    base = entity["SPSActivityClassBase"]
    if not category or category == base.get("Category"):
        return None
    return sla_path(category, base.get("Initiator"), ticket_kind(entity), base.get("Impact"))


def _new_description(old_html, text):
    """Neue DescriptionHTML oder None (unverändert). Nur hinten ergänzt: alte HTML bleibt."""
    old_text, text = html_text(old_html), (text or "").strip()
    if text == old_text:
        return None
    if old_text and text.startswith(old_text):
        return (old_html or "") + (description_html(text[len(old_text):]) or "")
    return description_html(text) or ""


def edited_entity(entity, subject, description, category=None, sla=None):
    """Ticket zum Speichern: Betreff, Beschreibung (ganzer Klartext) und Kategorie neu, sonst wie geladen.
    description None: Beschreibung bleibt. sla: SLA zur neuen Kategorie (TightestItem)."""
    base = dict(entity["SPSActivityClassBase"])
    subject = (subject or "").strip()
    if not subject:
        raise BookingError("Bitte einen Betreff eingeben.")
    new_html = None if description is None else _new_description(base.get("DescriptionHTML"), description)
    new_category = category if category and category != base.get("Category") else None
    if subject == (base.get("Subject") or "").strip() and new_html is None and not new_category:
        raise BookingError("Nichts geändert.")
    base["Subject"] = subject
    if new_html is not None:
        base["DescriptionHTML"] = new_html
    if new_category:
        base["Category"] = new_category
        if sla:
            base["SLA"] = sla
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
                "ITMTimeEntryClassTarget": dict(entity.get("ITMTimeEntryClassTarget") or {},
                                                ITMTimeEntryTarget=dict(EMPTY)),
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
