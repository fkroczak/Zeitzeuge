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

Bearbeiten (Dialog des bestehenden Tickets je Art, edit_dialog()): Matrix42 hat je Ticketart einen
eigenen Dialog (WidgetCommon/GetWidgets, Purpose 2): Störung „Incident Dialog“, Serviceanfrage
„Service Request Dialog“, Ticket „ITM.SD.EditTicket Dialog“. Lädt man eine Störung über den Dialog
der Serviceanfrage, meldet Matrix42 ObjectIsDeleted (Mitschnitt „Ticket ansehen“, TCK0000050902,
13.11.2026). Ist die Art unbekannt, fragt Zeitzeuge sie wie Matrix42 ab:
GET /ticket/GetTicketEntityType/<Id> -> "SPSActivityTypeIncident".
1. Laden: GET /WidgetCommon/GetData/<Dialog>/<Ticket-Id>?archived=false -> ganzes Ticket mit Sys-TimeStamp.
2. Speichern: POST /WidgetDialog/UpdateData/<Dialog> mit dem geladenen Ticket, Sys-EntityState 202,
   Beziehungen leer (AddedRelations/RemovedRelations), geändert nur Betreff, Beschreibung und
   Kategorie (Mitschnitt vom 13.11.2026: Betreff geändert, Rest Zeichen für Zeichen wie geladen).
   Beschreibung: Kommt nur Text hinten dazu, wird er als neue Absätze angehängt (Bilder, Tabellen
   und Formatierungen aus Matrix42 bleiben). Sonst ersetzt der Klartext die Beschreibung.
   Kategorie: Der Dialog fragt dazu /activity/suitableSLAsForTicket (wie beim Anlegen) und nimmt
   TightestItem als SLA (ServiceDesk-Einstellung AutoApplyingTightestSLA = 1).
Art ändern (Serviceanfrage -> Störung) fehlt noch im Mitschnitt.

Verlauf (Journal, Mitschnitt „Ticket ansehen“ vom 17.11.2026): GET /Journal?objectId=<Ticket-Id>
&start=<n>&count=6&objectLinkTemplate=…&timeOffset=<min>, neueste zuerst. Matrix42 blättert in
Fünferschritten und fragt je einen mehr ab (sechster = erster der nächsten Seite). Einträge:
Id, CreatedDate (UTC), Header („E-Mail empfangen von …“, „Kommentiert von …“, „Angehalten von …“),
Text (HTML, E-Mails mit eingebetteten Bildern, Anhänge als Links), Creator.

Schließen: POST /ticket/CloseWizardInitialData/?ticketType=<Typ> [Id] -> Kategorie, dann
POST /ticket/Close mit Lösungstext (Comments, HTML). Beim Öffnen des Fensters holt „close_info“
die Startwerte und das Ticket: ein Lösungstext von früher (Ticket wieder eröffnet) wird vorbelegt.

Verwalter des Kunden (Mitschnitt „Ticket ansehen“ vom 18.11.2026, Klick auf den Kunden im Ticket):
1. Ticket: SPSCommonClassBase.OU = Id des Kunden (Fragment-Id, wie UserDetails.OrgUnitId).
2. POST /entity/fragments [{"entityClass": "SPSOrgUnitClassBase", "ids": [OU]}] -> ObjectId, Anzeigename.
3. GET /WidgetCommon/GetData/<Kundendialog>/<ObjectId>?archived=false -> SPSOrgUnitClassBase.Manager
   („Verwalter“) und SubManager („Delegierte Verwalter“), je eine Benutzer-Id oder null.
4. POST /entity/fragments [{"entityClass": "SPSUserClassBase", "ids": [Id]}, …] -> Namen
   („Spiekermann, Jörg - Kropff-Federath'sche Stiftung …“), dann /activity/UserDetails für Telefon/E-Mail.

Melder suchen: POST /entity/fragments/forControl (Personenauswahl im Ticketdialog).
Kategorien: POST /entity/tree (ganzer Kategoriebaum).
"""
import html
import re
from html.parser import HTMLParser
from datetime import datetime
from urllib.parse import urlencode

from m42_booking import API, BookingError, EMPTY_RELATIONS, wrap

# Kennungen aus dem Mitschnitt (in der Config unter m42_ticket_ids änderbar)
DEFAULT_IDS = {"ticket_dialog": "be4ceef2-aadf-ca41-a130-08d46543427a",            # Neues Ticket
               "ticket_edit_dialog": "89427fc1-3c2b-c21a-f6dc-08d46550b705",       # Serviceanfrage
               "incident_edit_dialog": "44823b12-332d-c3fb-7d47-08d2f40c5bfe",     # Störung
               "ticket_type_edit_dialog": "2725327a-bc66-ef11-debc-0050569e2f05",  # Ticket
               "org_unit_dialog": "be4a3af4-b45d-ca53-2e23-08d383179037"}          # Kunde (OU)

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


def _same(text):
    return " ".join((text or "").split()).casefold()


def melder_search_text(name):
    """Suchtext für die Personensuche aus dem Melder der Ticketliste:
    'Muster, Erika - Praxis Beispiel …' -> 'Muster, Erika'."""
    return (name or "").split(" - ")[0].strip()


def match_user(users, name):
    """Melder aus der Ticketliste (nur Name, keine Id) in den Treffern der Personensuche finden.
    Genau gleicher Anzeigename zuerst, sonst der einzige Treffer mit gleichem Namen ohne Firma.
    None, wenn es nicht eindeutig ist (dann lieber keine falsche Telefonnummer zeigen)."""
    want = _same(name)
    if not want:
        return None
    exact = [u for u in users if _same(u.get("name")) == want]
    if exact:
        return exact[0] if len({u["id"] for u in exact}) == 1 else None
    short = _same(melder_search_text(name))
    same = [u for u in users if _same(melder_search_text(u.get("name"))) == short]
    return same[0] if len(same) == 1 else None


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


def edit_dialog(ids, kind):
    """Dialog, mit dem Matrix42 ein bestehendes Ticket dieser Art öffnet und speichert."""
    return {"SPSActivityTypeIncident": ids.get("incident_edit_dialog"),
            "SPSActivityTypeTicket": ids.get("ticket_type_edit_dialog")}.get(kind) or ids["ticket_edit_dialog"]


def entity_type(data):
    """Antwort von GET /ticket/GetTicketEntityType/<Id> -> 'SPSActivityTypeIncident' ('' wenn unklar)."""
    text = data.strip().strip('"') if isinstance(data, str) else ""
    return text if text.startswith("SPSActivityType") else ""


# „Preview for Agent“ je Ticketart (WidgetCommon/GetWidgets). Öffnet der Bearbeiter ein Ticket darin,
# setzt Matrix42 „Neue Information erhalten“ selbst zurück, ohne eigene Abfrage zum Speichern
# (Mitschnitt vom 17.11.2026, 14:54: GetData mit NewInformationReceived 1, zwanzig Sekunden später 0)
PREVIEW_WIDGETS = {"SPSActivityTypeIncident": "3b4c23df-08e7-c3bd-be7c-08d33f5dcbe1",
                   "SPSActivityTypeServiceRequest": "99912400-5e96-c50f-9a1b-08d4617dc22d",
                   "SPSActivityTypeTicket": "e54bab9f-0a7b-ce2a-ca48-08d46175796f"}


def preview_path(kind, ticket_id):
    """Ticket in der Vorschau öffnen wie Matrix42 (Kennzeichen „neue Information“ geht dann weg)."""
    widget = PREVIEW_WIDGETS.get(kind or "", PREVIEW_WIDGETS["SPSActivityTypeTicket"])
    return edit_data_path(widget, ticket_id)


def edit_data_path(dialog, ticket_id):
    return f"{API}/WidgetCommon/GetData/{dialog}/{ticket_id}?archived=false"


def load_error(error, kind=""):
    """Fehler beim Laden eines bestehenden Tickets lesbar machen. Matrix42 meldet ObjectIsDeleted
    („The object you try to open is deleted“), wenn das Ticket über den Dialog einer anderen Ticketart
    geladen wird (z. B. Störung über den Dialog der Serviceanfrage, siehe edit_dialog) oder es
    wirklich gelöscht ist."""
    if "ObjectIsDeleted" not in str(error):
        return error
    art = {"SPSActivityTypeIncident": "Störung", "SPSActivityTypeServiceRequest": "Serviceanfrage",
           "SPSActivityTypeTicket": "Ticket"}.get(kind, kind.replace("SPSActivityType", ""))
    return BookingError("Matrix42 kann dieses Ticket nicht laden" + (f" ({art})" if art else "")
                        + ". Es ist gelöscht oder hat eine andere Art als in der Liste. "
                          "Bitte die Liste aktualisieren.")


def loaded_entity(data):
    """Antwort von WidgetCommon/GetData -> Ticket (mit oder ohne Hülle "Entity")."""
    entity = data.get("Entity") if isinstance(data, dict) and isinstance(data.get("Entity"), dict) else data
    if not isinstance(entity, dict) or not entity.get("ID") or not isinstance(entity.get("SPSActivityClassBase"), dict):
        raise BookingError("Matrix42 liefert das Ticket nicht. Bitte die Liste aktualisieren.")
    return entity


class _TextParser(HTMLParser):
    """HTML (auch ganze HTML-E-Mails aus Outlook) -> Klartext. Kopf, CSS, Skripte und
    Kommentare fallen weg, Absätze und Zeilenumbrüche bleiben, Entities werden aufgelöst."""
    SKIP = {"head", "style", "script", "title", "xml", "o:p"}
    BLOCK = {"p", "div", "li", "tr", "table", "blockquote", "pre", "hr",
             "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "img" and not self.skip:
            self.parts.append("[Bild]")  # wie Matrix42 im Klartext der E-Mail
        elif tag in self.BLOCK and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")  # neuer Block beginnt in einer neuen Zeile
        elif tag in ("td", "th"):
            self.parts.append("\t")

    def handle_startendtag(self, tag, attrs):
        if tag == "img":
            self.handle_starttag(tag, attrs)
        elif tag == "br" or tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(re.sub(r"[ \t\r\n\f]+", " ", data))


def html_text(value):
    """HTML der Beschreibung -> lesbarer Klartext (nur zum Anzeigen)."""
    parser = _TextParser()
    try:
        parser.feed(value or "")
        parser.close()
    except Exception:  # kaputtes HTML: lieber grob als gar nicht
        return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()
    text = "".join(parser.parts).replace("\xa0", " ").replace("\u200b", "")
    lines = [re.sub(r" {2,}", " ", line).strip(" ") for line in text.split("\n")]
    text = "\n".join(line.replace("\t ", "\t").strip("\t") for line in lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def stamp(entity):
    """Versionsmarke des Tickets: ändert sich, sobald jemand speichert."""
    base = entity.get("SPSActivityClassBase") or {}
    return f"{entity.get('Sys-TimeStamp', '')}/{base.get('Sys-TimeStamp', '')}"


# Für die Anzeige im Fenster „Ticket ansehen“ (QTextBrowser: führt nichts aus, lädt nichts aus dem Netz)
_DROP_BLOCKS = re.compile(r"(?is)<(script|iframe|object|embed|form|title)\b.*?</\1\s*>")
_DROP_TAGS = re.compile(r"(?i)</?(script|iframe|object|embed|form|input|button|meta|link|base)\b[^>]*>")
_IMG = re.compile(r"(?is)<img\b[^>]*>")
_IMG_SIZE = re.compile(r"""(?is)\s(width|height)\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""")
_IMG_STYLE = re.compile(r"""(?is)\sstyle\s*=\s*("[^"]*"|'[^']*')""")


def view_html(value):
    """Beschreibung als HTML zum Ansehen (mit eingebetteten Bildern): Skripte, Formulare und
    Rahmen fallen weg, Bilder ohne feste Größe (das Fenster verkleinert sie auf seine Breite)."""
    text = _DROP_TAGS.sub("", _DROP_BLOCKS.sub("", value or ""))
    return _IMG.sub(lambda m: _IMG_STYLE.sub("", _IMG_SIZE.sub("", m.group(0))), text)


RICH_HTML = re.compile(r"(?i)<(img|table|ul|ol|a|b|strong|i|em|u|span|font|h[1-6])\b")


def ticket_view(entity):
    """Geladenes Ticket -> was das Fenster zeigt. rich: Beschreibung hat Bilder, Tabellen o. Ä.,
    die beim Ersetzen durch Klartext verloren gingen."""
    base = entity["SPSActivityClassBase"]
    description = base.get("DescriptionHTML") or ""
    return {"id": entity["ID"], "ticket": entity.get("Sys-Name", ""), "type": entity.get("Sys-Entity", ""),
            "subject": (base.get("Subject") or "").strip(), "description": html_text(description),
            "category": base.get("Category"), "rich": bool(RICH_HTML.search(description)),
            "html": view_html(description) if RICH_HTML.search(description) else "",
            "stamp": stamp(entity), "initiator": base.get("Initiator") or "",
            "ou": (entity.get("SPSCommonClassBase") or {}).get("OU") or "",
            "callback": ((entity.get("SPSActivityClassIncident") or {}).get("Callback") or "").strip(),
            # Kontakt des Melders kommt mit dem Ticket (Telefon, E-Mail, Firma), dann ohne Extra-Abfrage
            "contact": _user_details(entity)}


def _user_details(entity):
    details = (entity.get("InitialData") or {}).get("UserDetails") if isinstance(entity.get("InitialData"), dict) else None
    return details if isinstance(details, dict) else {}


def contact_rows(details, name="", callback=""):
    """Kontakt des Melders aus GET /activity/UserDetails -> [(Name, Wert, Link)], Link "" ohne.
    Telefon als tel:, E-Mail als mailto:. Die Rückrufnummer des Tickets nur, wenn sie anders ist."""
    d = details if isinstance(details, dict) else {}

    def text(key):
        value = d.get(key)
        if isinstance(value, dict):
            value = value.get("DisplayString") or value.get("Name") or ""
        return value.strip() if isinstance(value, str) else ""

    def tel(number):
        return "tel:" + re.sub(r"[^\d+]", "", number) if re.search(r"\d", number) else ""

    rows = [("Name", name.strip(), ""), ("Firma", text("OrgUnit"), "")]
    phone, mobile, mail = text("Phone"), text("MobilePhone") or text("Mobile"), text("Email")
    rows += [("Telefon", phone, tel(phone)), ("Mobil", mobile, tel(mobile)),
             ("E-Mail", mail, f"mailto:{mail}" if "@" in mail else "")]
    if callback and re.sub(r"\D", "", callback) not in {re.sub(r"\D", "", phone), re.sub(r"\D", "", mobile)}:
        rows.append(("Rückruf", callback, tel(callback)))
    location = text("Location")
    if location and location.lower() != "global":
        rows.append(("Standort", location, ""))
    return [r for r in rows if r[1]]


MANAGER_ROLES = (("Manager", "Verwalter"), ("SubManager", "Delegierter Verwalter"))


def fragments_query(entity_class, ids):
    """POST /entity/fragments: Anzeigenamen (und ObjectId) zu Ids, je Id ein Eintrag."""
    return [{"entityClass": entity_class, "ids": [i]} for i in ids if i]


def fragments_by_id(data):
    """Antwort von /entity/fragments -> {Id: {"object": ObjectId, "name": Anzeigename}}."""
    return {f["Id"]: {"object": f.get("ObjectId") or "", "name": (f.get("DisplayString") or "").strip()}
            for f in (data if isinstance(data, list) else []) if isinstance(f, dict) and f.get("Id")}


def org_unit_managers(data):
    """Kunde aus WidgetCommon/GetData -> [(Rolle, Benutzer-Id)] für Verwalter und Delegierten Verwalter,
    nur die hinterlegten."""
    entity = data.get("Entity", data) if isinstance(data, dict) else {}
    base = (entity or {}).get("SPSOrgUnitClassBase") or {}
    return [(role, base[key]) for key, role in MANAGER_ROLES if base.get(key)]


def person_name(display):
    """„Spiekermann, Jörg - Kropff-Federath'sche Stiftung …“ -> „Spiekermann, Jörg“."""
    return (display or "").split(" - ", 1)[0].strip()


def manager_rows(people, initiator=""):
    """Verwalter des Kunden -> [(Rolle, HTML)] fürs Fenster: Name, Telefon und E-Mail als Links.
    Ist der Verwalter selbst Melder, steht „(Melder)“ dahinter."""
    rows = []
    for p in people or []:
        details = p.get("details") or {}
        parts = [html.escape(p.get("name") or "?") + (" (Melder)" if initiator and p.get("id") == initiator else "")]
        for number in (details.get("Phone"), details.get("MobilePhone") or details.get("Mobile")):
            if isinstance(number, str) and re.search(r"\d", number):
                digits = re.sub(r"[^\d+]", "", number)
                parts.append(f'<a href="tel:{digits}">{html.escape(number.strip())}</a>')
        mail = details.get("Email")
        if isinstance(mail, str) and "@" in mail:
            parts.append(f'<a href="mailto:{html.escape(mail.strip(), quote=True)}">{html.escape(mail.strip())}</a>')
        rows.append((p.get("role") or "", " · ".join(parts)))
    return rows


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


def edited_entity(entity, subject, description, category=None, sla=None, initiator=None, details=None):
    """Ticket zum Speichern: Betreff, Beschreibung (ganzer Klartext), Kategorie und Melder neu, sonst wie
    geladen. description None: Beschreibung bleibt. sla: SLA zur neuen Kategorie (TightestItem).
    initiator: neuer Melder; details: seine UserDetails. Wie beim Anlegen kommen Kunde (OU),
    Kostenstelle, Standort und Rückrufnummer dann vom Melder (nur gefundene Werte)."""
    base = dict(entity["SPSActivityClassBase"])
    subject = (subject or "").strip()
    if not subject:
        raise BookingError("Bitte einen Betreff eingeben.")
    new_html = None if description is None else _new_description(base.get("DescriptionHTML"), description)
    new_category = category if category and category != base.get("Category") else None
    new_initiator = initiator if initiator and initiator != base.get("Initiator") else None
    if subject == (base.get("Subject") or "").strip() and new_html is None and not new_category \
            and not new_initiator:
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
    if new_initiator:
        base["Initiator"] = new_initiator
        common.update(initiator_common(details))
        phone = (details or {}).get("Phone") if isinstance(details, dict) else None
        if phone and "Callback" in incident:
            incident["Callback"] = phone
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


# ------------------------------------------------------------------ Verlauf (Journal)

JOURNAL_PAGE = 5      # Matrix42 blättert in Fünferschritten (count 6: einer mehr zum Erkennen)
JOURNAL_MAX_PAGES = 40  # höchstens 200 Einträge
JOURNAL_LINK = '<a href="#" class="mx-object-journal--link {0} {1}">{2}</a>'  # wie Matrix42
# Nachrichten: E-Mails, Kommentare und das Anlegen aus einer E-Mail; alles andere sind Änderungen
_MESSAGE_HEADERS = ("e-mail", "kommentiert", "kommentar", "das ticket wurde aus der e-mail")


def journal_path(ticket_id, start, offset_minutes=0):
    query = urlencode({"objectId": ticket_id, "start": start, "count": JOURNAL_PAGE + 1,
                       "objectLinkTemplate": JOURNAL_LINK, "timeOffset": offset_minutes})
    return f"{API}/Journal?{query}"


def journal_entries(pages):
    """Antworten der Journal-Seiten -> Einträge (jeder einmal, neueste zuerst):
    {"id", "time" (datetime lokal oder None), "header", "html", "creator", "message"}."""
    out, seen = [], set()
    for page in pages:
        for item in page if isinstance(page, list) else []:
            if not isinstance(item, dict) or item.get("Id") in seen:
                continue
            seen.add(item.get("Id"))
            header = (item.get("Header") or "").strip()
            out.append({"id": item.get("Id") or "", "time": _utc_local(item.get("CreatedDate")),
                        "header": header, "html": item.get("Text") or "", "creator": item.get("Creator") or "",
                        "message": header.casefold().startswith(_MESSAGE_HEADERS)})
    out.sort(key=lambda e: e["time"] or datetime.min, reverse=True)
    return out


def _utc_local(value):
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    except ValueError:
        return None


_DOCUMENT_TAGS = re.compile(r"(?is)<head\b.*?</head\s*>|<style\b.*?</style\s*>|<!--.*?-->|</?(html|body)\b[^>]*>")
_HREF = re.compile(r"""(?i)(\shref\s*=\s*["'])(/[^/"'][^"']*)""")


WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember")
# Art eines Eintrags -> (Zeichen, Farbe des Kästchens)
JOURNAL_KINDS = {"mail_in": ("✉", "#2563EB"), "mail_out": ("↗", "#16A34A"), "comment": ("✎", "#CA8A04"),
                 "alert": ("!", "#DC2626"), "change": ("•", "#9CA3AF")}
PREVIEW_CHARS = 180
_MAIL_META = re.compile(r"(?i)^(an|cc|bcc|von|from|to|betreff|subject)\s*:")
_MAIL_INTRO = re.compile(r"(?i)^die folgende (nachricht|e-mail) wurde")
_ATTACHMENT = re.compile(r"(?i)mx-journal-attachment-link")
# Anhang-Link der Mail im Verlauf: /SPS/Forms/AttachmentDownload.aspx?FileID=…&ObjectID=… gibt es auf
# dem Server nicht (404). Die Weboberfläche lädt Anhänge über GET /fileStorage/<FileID> (FileID =
# UniqueFileId aus /commonStorage/files). Das Fenster bekommt „zz:attachment:<FileID>“ und lädt selbst.
_ATTACHMENT_HREF = re.compile(r"""(?i)(\shref\s*=\s*["'])[^"']*AttachmentDownload\.aspx\?[^"']*?FileID=([0-9a-f-]+)[^"']*""")


def _kind(entry):
    head = entry["header"].casefold()
    if head.startswith("e-mail gesendet"):
        return "mail_out"
    if head.startswith(("e-mail", "das ticket wurde aus der e-mail")):
        return "mail_in"
    if head.startswith(("kommentiert", "kommentar")):
        return "comment"
    return "alert" if "eskaliert" in head else "change"


def _title_who(header):
    """„Angehalten von Kroczak, Filip - Systems“ -> („Angehalten“, „Kroczak, Filip“)."""
    title, sep, who = header.partition(" von ")
    if not sep or header.casefold().startswith("das ticket wurde aus"):
        return header, ""
    return title.strip(), who.split(" - ")[0].split(" (")[0].strip()


def _plain_lines(body):
    return [line.strip() for line in html_text(body).split("\n") if line.strip()]


def _preview(entry, kind):
    """Erste Zeilen des eigentlichen Inhalts (bei E-Mails ohne Einleitung, An/CC, Betreff)."""
    lines = _plain_lines(entry["html"])
    if kind in ("mail_in", "mail_out"):
        if lines and _MAIL_INTRO.match(lines[0]):
            lines = lines[1:]
        meta = [i for i, line in enumerate(lines[:6]) if _MAIL_META.match(line)]
        if meta:
            subject_after = kind == "mail_out"  # gesendet: Betreff nach Bcc, empfangen: davor
            lines = lines[meta[-1] + 1 + subject_after:]
    elif lines and lines[0].rstrip().endswith(":") and len(lines) > 1:
        lines = lines[1:]  # „Das Ticket wurde mit folgendem Kommentar … angehalten:“ -> der Kommentar
    text = " ".join(lines)
    return text if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS].rsplit(" ", 1)[0] + " …"


def journal_rows(entries):
    """Einträge -> Tage [(datum, [Zeile, …])], neueste zuerst. Aufeinanderfolgende Änderungen
    derselben Person in derselben Minute werden eine Zeile („3 Änderungen“)."""
    days = []
    for e in entries:
        kind = _kind(e)
        title, who = _title_who(e["header"])
        when = e["time"]
        row = {"id": e["id"], "kind": kind, "title": title, "who": who, "time": when,
               "preview": _preview(e, kind), "html": e["html"], "items": [(title, e)]}
        day = when.date() if when else None
        if not days or days[-1][0] != day:
            days.append((day, []))
        rows = days[-1][1]
        last = rows[-1] if rows else None
        if (kind == "change" and last and last["kind"] == "change" and last["who"] == who
                and (last["time"] and when and last["time"].strftime("%H%M") == when.strftime("%H%M"))):
            last["items"].append((title, e))
            continue
        rows.append(row)
    return days


def _day_title(day):
    if day is None:
        return "Ohne Datum"
    return f"{WEEKDAYS[day.weekday()]}, {day.day}. {MONTHS[day.month - 1]} {day.year}"


def file_path(file_id):
    """Anhang herunterladen wie die Weboberfläche (Links vom 17.11.2026)."""
    if not GUID.fullmatch(file_id or ""):
        raise BookingError("Unbekannter Anhang.")
    return f"{API}/fileStorage/{file_id}"


# Diese Dateien öffnet Zeitzeuge nicht selbst (könnten Programme starten), sondern zeigt den Ordner
RISKY_EXTENSIONS = {".exe", ".com", ".bat", ".cmd", ".msi", ".msp", ".scr", ".pif", ".lnk", ".js", ".jse",
                    ".vbs", ".vbe", ".wsf", ".wsh", ".ps1", ".psm1", ".hta", ".cpl", ".jar", ".reg", ".application"}
_TYPE_EXT = {"application/pdf": ".pdf", "message/rfc822": ".eml", "image/png": ".png", "image/jpeg": ".jpg",
             "text/plain": ".txt", "application/zip": ".zip"}


def attachment_name(disposition, content_type, file_id):
    """Dateiname aus Content-Disposition (auch filename*=UTF-8''…), sonst Id plus Endung nach Typ.
    Ohne Pfad und ohne Zeichen, die Windows nicht mag."""
    from urllib.parse import unquote
    name = ""
    m = re.search(r"(?i)filename\*\s*=\s*([^']*)'[^']*'([^;]+)", disposition or "")
    if m:
        name = unquote(m.group(2).strip().strip('"'), encoding=m.group(1) or "utf-8", errors="replace")
    else:
        m = re.search(r'(?i)filename\s*=\s*"?([^";]+)"?', disposition or "")
        name = m.group(1).strip() if m else ""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name.replace("\\", "/").split("/")[-1]).strip(" .")
    if not name:
        name = file_id + _TYPE_EXT.get((content_type or "").split(";")[0].strip().lower(), "")
    return name[:150]


def is_risky(name):
    import os
    return os.path.splitext(name or "")[1].lower() in RISKY_EXTENSIONS


def journal_html(entries, expanded=(), origin=""):
    """Verlauf als Zeitstrahl, nach Tagen gruppiert: runde Punkte je Art auf einer Linie
    (Bilder „zz:dot:<Art>“ und „zz:line“, das Fenster zeichnet sie), E-Mails und Kommentare mit
    Vorschau (auf-/zuklappen über Links „zz:toggle:<id>“), Änderungen einzeilig und grau.
    origin („https://host“) macht Anhang-Links von Matrix42 klickbar."""
    parts = []
    for day, rows in journal_rows(entries):
        parts.append(f'<p style="margin:14px 0 6px 0; color:{GREY}; font-size:small;">'
                     f'<b>{html.escape(_day_title(day).upper())}</b></p>'
                     '<table width="100%" cellspacing="0" cellpadding="0">')
        for i, row in enumerate(rows):
            line = ' background="zz:line"' if i < len(rows) - 1 else ""
            parts.append(f'<tr><td width="30" valign="top"{line}><img src="zz:dot:{row["kind"]}"></td>'
                         f'<td valign="top" style="padding-bottom:10px;">'
                         f'{_row_html(row, row["id"] in expanded, origin)}</td></tr>')
        parts.append("</table>")
    return "".join(parts)


GREY = "#62626B"
LINK = "color:#005FB8; text-decoration:none; font-size:small;"


def _body_html(raw, origin):
    body = _ATTACHMENT_HREF.sub(lambda m: m.group(1) + "zz:attachment:" + m.group(2), _DOCUMENT_TAGS.sub("", raw))
    if origin:
        body = _HREF.sub(lambda m: m.group(1) + origin.rstrip("/") + m.group(2), body)
    return view_html(body)


def _row_html(row, open_, origin):
    when = row["time"].strftime("%H:%M") if row["time"] else ""
    toggle = f'zz:toggle:{html.escape(row["id"], quote=True)}'
    if row["kind"] in ("change", "alert"):  # eine graue Zeile
        if len(row["items"]) > 1:
            text = f'{len(row["items"])} Änderungen: ' + " · ".join(dict.fromkeys(t for t, _e in row["items"]))
        else:
            text = row["title"] + (f' – {row["preview"]}' if row["preview"] else "")
        who = f' · {row["who"]}' if row["who"] else ""
        out = f'<span style="color:{GREY};">{html.escape(text)}<small>{html.escape(who)} · {when}</small></span>'
        if open_:
            out += "".join(f'<div style="color:{GREY};">{_body_html(e["html"], origin)}</div>'
                           for _t, e in row["items"])
            out += f'<a href="{toggle}" style="{LINK}">▴ zuklappen</a>'
        elif len(row["items"]) > 1 or row["preview"].endswith(" …"):
            out += f' <a href="{toggle}" style="{LINK}">▸ mehr</a>'
        return out
    label = "Kommentar von" if row["kind"] == "comment" else "E-Mail von"
    title = f'{label} {row["who"]}' if row["who"] else row["title"]
    if row["title"].casefold().startswith("das ticket wurde aus"):
        title = "Ticket aus E-Mail erstellt"
    out = f'<b>{html.escape(title)}</b> <span style="color:{GREY};">· {when}</span>'
    images = len(_IMG.findall(row["html"]))
    files = len(_ATTACHMENT.findall(row["html"]))
    extra = "".join(f" · {n} {w}" for n, w in ((images, "Bild" if images == 1 else "Bilder"),
                                                   (files, "Anhang" if files == 1 else "Anhänge")) if n)
    if open_:
        return out + f'<div>{_body_html(row["html"], origin)}</div><a href="{toggle}" style="{LINK}">▴ zuklappen</a>'
    out += f'<br><span style="color:{GREY};">{html.escape(row["preview"])}</span>'
    return out + f'<br><a href="{toggle}" style="{LINK}">▸ aufklappen{extra}</a>'
