"""Prüfstand Tagesabschluss: Erkennungsgrad an 40 nachgebauten Arbeitstagen mit bekannter Wahrheit.

Jeder Tag besteht aus Aufgaben (Kunde, Ticket, Dauer), die als Matrix42-Buchung die richtige
Antwort sind. Daraus entstehen Spuren mit den Störungen echter Tage:
- Verbindungen beginnen etwas später und enden früher als die Arbeit,
- 15 % der TeamViewer-Sitzungen haben nur eine unbekannte ID,
- 30 % der Anrufer sind nur eine Nummer (nicht in der Kundenliste),
- Ticketarbeit am PC: nur in 60 % steht die Ticketnummer im Fenstertitel, nie der Kunde,
- interne E-Mail-Zeit (gebucht auf ein internes Ticket, ohne Spur zum Kunden),
- kurze Splitter (Teams, Explorer) mitten in der Arbeit, Kunden mit anderer Schreibweise.

Zwei Profile: „schlecht eingerichtet“ (Werte oben) und „gut eingerichtet“ (Kundenliste gepflegt:
3 % unbekannte IDs, 95 % bekannte Anrufer, 85 % Ticketnummer im Fenstertitel). Der Test schlägt
fehl, wenn eine Änderung die Erkennung unter diese Grenzen drückt: gut eingerichtet ≥ 80 %,
schlecht eingerichtet mit internem Ticket ≥ 70 %, ohne ≥ 55 %; immer Kunde richtig ≥ 95 % und
falsches Ticket (ohne Rückfrage gebucht) ≤ 3 %. Die Werte gelten für diese Annahmen, nicht automatisch für jeden echten
Tag. Echte Tage misst „Erkennung messen …“ im Fenster Tagesabschluss (day_close_eval.py).
"""
import random
from datetime import datetime, timedelta

import day_close as dc
import day_close_eval as ev

CUSTOMERS = [  # (Name in Matrix42, Name in den Spuren, Telefon bekannt?)
    ("Müller GmbH", "Mueller", True), ("Kanzlei Schmidt & Partner", "Kanzlei Schmidt", True),
    ("Bäckerei Huber e.K.", "Baeckerei Huber", False), ("Auto Huber GmbH", "Auto Huber", True),
    ("Stadtwerke Nord", "Stadtwerke Nord", True), ("Praxis Dr. Weber", "Praxis Weber", True),
    ("Logistik Kraus AG", "Kraus Logistik", False), ("Hotel Seeblick", "Hotel Seeblick", True),
    ("Elektro Brandt", "Elektro Brandt", True), ("Steuerbüro Lang", "Steuerbuero Lang", True),
]
INTERNAL = {"customer": "ITM intern", "ticket": "TCK0000099999", "category": "Intern",
            "categories": ["E-Mail / Kommunikation", "Teams"]}
T = "%Y-%m-%d %H:%M:%S"


def _ticket(rng):
    return f"TCK{rng.randrange(10 ** 9, 10 ** 10):010d}"


HARSH = {"unknown_tv": 0.15, "phone_known": 0.7, "title_ticket": 0.6}   # schlecht eingerichtet
GOOD = {"unknown_tv": 0.03, "phone_known": 0.95, "title_ticket": 0.85}  # Kundenliste gepflegt


def simulate(days=40, seed=7, profile=None):
    """-> [(Tag, Personalzeit, Spuren, Wahrheit)]. profile: Anteil unbekannter TeamViewer-IDs,
    Anteil bekannter Anrufer, Anteil Ticketnummer im Fenstertitel (HARSH oder GOOD)."""
    profile = profile or HARSH
    rng = random.Random(seed)
    tickets = {c[0]: _ticket(rng) for c in CUSTOMERS}
    out = []
    day = datetime(2026, 9, 1)
    while len(out) < days:
        day += timedelta(days=1)
        if day.weekday() >= 5:
            continue
        for c in CUSTOMERS:  # ab und zu ein neues Ticket je Kunde
            if rng.random() < 0.1:
                tickets[c[0]] = _ticket(rng)
        work = [(day.replace(hour=8), day.replace(hour=12)), (day.replace(hour=12, minute=30),
                                                               day.replace(hour=16, minute=30))]
        evidence, truth = [], []
        for a, b in work:
            t = a
            while t < b - timedelta(minutes=10):
                length = timedelta(minutes=rng.choice([15, 20, 30, 30, 45, 60, 75, 90]))
                end = min(t + length, b)
                kind = rng.choices(["remote", "phone", "ticket", "meeting", "mail"],
                                   [35, 15, 25, 10, 15])[0]
                name, trace, phone = rng.choice(CUSTOMERS)
                s, e = t.strftime(T), end.strftime(T)
                if kind == "mail":
                    truth.append({"start": s, "end": e, "customer": INTERNAL["customer"],
                                  "ticket": INTERNAL["ticket"]})
                    evidence.append((4, {"start": s, "end": e, "pc_block": True, "type": "PC: E-Mail",
                                         "category": "E-Mail / Kommunikation", "customer_name": "",
                                         "label": "E-Mail", "title": "Posteingang - Outlook"}))
                else:
                    truth.append({"start": s, "end": e, "customer": name, "ticket": tickets[name]})
                if kind == "remote":
                    late, early = rng.randint(0, 4), rng.randint(0, 5)
                    tv = rng.random() < 0.5
                    unknown = tv and rng.random() < profile["unknown_tv"]
                    label = "TeamViewer 1 234 567" if unknown else (
                        trace if tv else f"{trace} - SRV{rng.randint(1, 9):02d}")
                    evidence.append((1, {"start": (t + timedelta(minutes=late)).strftime(T),
                                         "end": (end - timedelta(minutes=early)).strftime(T),
                                         "type": "TeamViewer" if tv else "RDP-Sitzung",
                                         "customer_name": label}))
                elif kind == "phone":
                    talk = max(3, int((end - t).total_seconds() / 60 * rng.uniform(0.6, 1.0)))
                    who = trace if (phone or profile is GOOD) and rng.random() < profile["phone_known"] else "0711 5550123"
                    evidence.append((1, {"start": s, "end": (t + timedelta(minutes=talk)).strftime(T),
                                         "type": "3CX-Anruf", "direction": "Eingehend", "customer_name": who}))
                elif kind == "ticket":
                    title = (f"{tickets[name]} - Störung - Matrix42" if rng.random() < profile["title_ticket"]
                             else "Service Desk - Matrix42")
                    evidence.append((4, {"start": s, "end": e, "pc_block": True, "type": "PC: Ticketsystem",
                                         "category": "Ticketsystem", "customer_name": "",
                                         "label": "Ticketsystem", "title": title}))
                elif kind == "meeting":
                    evidence.append((1, {"start": s, "end": e, "type": "Teams-Besprechung",
                                         "customer_name": trace, "description": f"Abstimmung {trace}"}))
                # kurzer Splitter mitten drin (zählt in der Wahrheit zur Aufgabe)
                if rng.random() < 0.3 and end - t > timedelta(minutes=20):
                    mid = t + (end - t) / 2
                    evidence.append((4, {"start": mid.strftime(T), "end": (mid + timedelta(minutes=2)).strftime(T),
                                         "pc_block": True, "type": "PC: Teams", "category": "Teams",
                                         "customer_name": "", "label": "Teams", "title": "Chat"}))
                t = end + timedelta(minutes=rng.choice([0, 0, 0, 2, 5]))
        out.append((day.strftime("%Y-%m-%d"), work, evidence, truth))
    return out


def hint(entry):
    """Wie learning.doc_hints mit Kundenliste: Spur -> Kunde (Matrix42-Schreibweise teils anders)."""
    if entry.get("pc_block"):
        return "", entry.get("category", "")
    name = (entry.get("customer_name") or "").split(" - ")[0]
    known = {c[1]: c[1] for c in CUSTOMERS}
    return known.get(name, ""), "Fernwartung"


def ticket_for_day(evidence):
    """Wie tickets.suggest über die Fenstertitel: längstes Ticket im Block."""
    def ticket_for(start, end):
        found = {}
        for _tier, e in evidence:
            if not e.get("pc_block"):
                continue
            a, b = max(start, dc._t(e["start"])), min(end, dc._t(e["end"]))
            if b > a and e.get("title", "").startswith("TCK"):
                tk = e["title"].split()[0]
                found[tk] = found.get(tk, 0) + (b - a).total_seconds()
        return (max(found, key=found.get), "Matrix42") if found else ("", "")
    return ticket_for


def run(internal=None, days=40, profile=None):
    sim = simulate(days, profile=profile)
    total, history = {}, []
    for date_str, work, evidence, truth in sim:
        plan = dc.build(date_str, work, evidence=evidence, hint=hint, ticket_for=ticket_for_day(evidence),
                        history_bookings=history, internal=internal)
        ev.add(total, ev.evaluate_day(date_str, plan["rows"], truth))
        history += truth  # danach gebucht: Verlauf für die nächsten Tage
    return ev.rates(total)


def check_safety(r):
    """Gilt in jedem Profil: Kunde fast immer richtig, ohne Rückfrage gebuchte Tickets fast nie falsch."""
    assert r["customer"] >= 95, r
    assert r["ticket_wrong"] <= 3, r


def test_good_setup_reaches_target():
    """Gut eingerichtet (Kundenliste gepflegt, Ticketnummern im Fenstertitel, internes Ticket für
    E-Mail): Erkennungsgrad im Ziel 70–90 % (Untergrenze mit Puffer: 80 %)."""
    r = run(internal=INTERNAL, profile=GOOD)
    print("gut eingerichtet:", ev.summary_text(r))
    assert r["recognized"] >= 80, r
    check_safety(r)


def test_harsh_setup_with_internal_ticket():
    r = run(internal=INTERNAL)
    print("schlecht eingerichtet, internes Ticket:", ev.summary_text(r))
    assert r["recognized"] >= 70, r
    check_safety(r)


def test_harsh_setup_floor():
    """Schlecht eingerichtet und ohne internes Ticket: Untergrenze, unter die es nie fallen darf."""
    r = run()
    print("schlecht eingerichtet, ohne internes Ticket:", ev.summary_text(r))
    assert r["recognized"] >= 55, r
    check_safety(r)


def test_benchmark_sees_errors():
    """Der Prüfstand muss Verschlechterungen sehen: ohne PC-Spuren und Verlauf fällt die Erkennung."""
    total = {}
    for date_str, work, evidence, truth in simulate(40):
        plan = dc.build(date_str, work, evidence=[x for x in evidence if x[0] != 4], hint=hint)
        ev.add(total, ev.evaluate_day(date_str, plan["rows"], truth))
    assert ev.rates(total)["recognized"] < run()["recognized"] - 5
