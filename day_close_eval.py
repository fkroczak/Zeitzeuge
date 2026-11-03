"""Wie gut erkennt der Tagesabschluss deine Tätigkeiten? Messung an deinen echten Buchungen (ohne Qt).

Grundgedanke: Was du in Matrix42 gebucht hast, ist die richtige Antwort. Für einen vergangenen Tag
rechnet Zeitzeuge die Vorschläge so, als wäre noch nichts gebucht und nichts eingetragen
(„Nachspielen“), und vergleicht sie Minute für Minute mit den echten Buchungen:

- **Erkannt (Zeit):** Anteil der gebuchten Zeit, zu der es einen Vorschlag mit Kunde gibt.
- **Kunde richtig:** davon der Anteil, bei dem der Kunde stimmt (Schreibweise egal, same_customer).
- **Erkennungsgrad:** gebuchte Zeit mit richtigem Kunden ÷ gebuchte Zeit. Das ist die Kennzahl
  für „wie viel hätte der Tagesabschluss richtig vorbereitet“. Ziel 70–90 %.
- **Ticket richtig:** Anteil der Vorschlagszeit mit sicherem Ticket (Fenstertitel, internes
  Ticket), bei der das Ticket stimmt.
- **Falsches Ticket:** Anteil der Vorschlagszeit mit sicherem Ticket, bei der ein anderes Ticket
  gebucht wurde. Nur diese Tickets bucht der Tagesabschluss ohne Rückfrage; das ist das Risiko
  einer Fehlbuchung und soll klein bleiben (Ziel unter 10 %).
- **Vermutetes Ticket richtig:** Trefferquote der Tickets „zuletzt für den Kunden benutzt“. Sie
  werden nur nach ausdrücklicher Bestätigung gebucht.

Minuten mit mehreren echten Buchungen zählen einmal (die längste Buchung gilt). Tage ohne
Matrix42-Daten zählen nicht.
"""
from datetime import datetime

import day_close as dc

TARGET_LOW, TARGET_HIGH = 70, 90   # Erkennungsgrad: Zielbereich in Prozent
WRONG_TICKET_MAX = 10              # Falsches Ticket: höchstens so viel Prozent
MIN_SAMPLE_MINUTES = 8 * 60        # weniger gebuchte Zeit: Aussage noch unsicher


def _ticket(text):
    return (text or "").strip().upper()


def _truth_minutes(day, truth):
    """Minute -> echte Buchung (bei Überschneidung die längere)."""
    spans = [(dc._span(day, b), b) for b in truth or []]
    owner = {}
    for span, b in sorted((x for x in spans if x[0]), key=lambda x: x[0][0] - x[0][1]):
        for m in range(*span):
            owner.setdefault(m, b)
    return owner


def evaluate_day(date_str, rows, truth):
    """Vorschläge eines nachgespielten Tages gegen die echten Buchungen -> Zähler in Minuten."""
    day = datetime.strptime(date_str, "%Y-%m-%d")
    owner = _truth_minutes(day, truth)
    proposal = {}
    for r in rows or []:
        if r.get("kind") == dc.KIND_GAP or not r.get("customer"):
            continue
        span = dc._span(day, r)
        if span:
            for m in range(*span):
                proposal.setdefault(m, r)
    counts = {"truth": len(owner), "covered": 0, "customer_ok": 0, "with_ticket": 0,
              "ticket_ok": 0, "ticket_wrong": 0, "guessed": 0, "guessed_ok": 0,
              "proposed": len(proposal), "extra": 0}
    for m, r in proposal.items():
        b = owner.get(m)
        if b is None:
            counts["extra"] += 1  # Vorschlag, wo nichts gebucht wurde (Pause, intern, nicht gebucht)
            continue
        counts["covered"] += 1
        if dc.same_customer(r.get("customer", ""), b.get("customer", "")) or (
                _ticket(r.get("ticket")) and _ticket(r.get("ticket")) == _ticket(b.get("ticket"))):
            counts["customer_ok"] += 1
        if _ticket(r.get("ticket")) and r.get("ticket_guessed"):
            # vermutet: wird nur nach Bestätigung gebucht, zählt getrennt
            counts["guessed"] += 1
            counts["guessed_ok"] += _ticket(r.get("ticket")) == _ticket(b.get("ticket"))
        elif _ticket(r.get("ticket")):
            counts["with_ticket"] += 1
            if _ticket(r.get("ticket")) == _ticket(b.get("ticket")):
                counts["ticket_ok"] += 1
            else:
                counts["ticket_wrong"] += 1
    return counts


def add(total, counts):
    for k, v in counts.items():
        total[k] = total.get(k, 0) + v
    return total


def rates(counts):
    """Zähler -> Kennzahlen in Prozent (None, wenn es nichts zu messen gab)."""
    def pct(a, b):
        return None if not b else round(100 * a / b)
    return {
        "recognized": pct(counts.get("customer_ok", 0), counts.get("truth", 0)),  # Erkennungsgrad
        "covered": pct(counts.get("covered", 0), counts.get("truth", 0)),
        "customer": pct(counts.get("customer_ok", 0), counts.get("covered", 0)),
        "ticket": pct(counts.get("ticket_ok", 0), counts.get("with_ticket", 0)),
        "ticket_wrong": pct(counts.get("ticket_wrong", 0), counts.get("with_ticket", 0)),
        # sicheres Ticket (wird ohne Rückfrage gebucht) für so viel der gebuchten Zeit
        "ticket_auto": pct(counts.get("ticket_ok", 0), counts.get("truth", 0)),
        "guessed": pct(counts.get("guessed_ok", 0), counts.get("guessed", 0)),
        "truth_minutes": counts.get("truth", 0),
    }


def verdict(r):
    """Kurzurteil für die Anzeige: (Stufe, Text). Stufe 'ok' | 'warn' | 'bad' | 'none'."""
    if r["recognized"] is None:
        return "none", "Noch keine Matrix42-Buchungen zum Vergleichen."
    sample = "" if r["truth_minutes"] >= MIN_SAMPLE_MINUTES else " (noch wenig gebuchte Zeit, Wert schwankt)"
    wrong = r["ticket_wrong"] or 0
    if wrong > WRONG_TICKET_MAX:
        return "bad", (f"Falsches Ticket bei {wrong} % der Vorschlagszeit – vor dem Buchen jedes Ticket "
                       f"prüfen{sample}.")
    if r["recognized"] >= TARGET_LOW:
        return "ok", f"Erkennungsgrad {r['recognized']} % – im Ziel ({TARGET_LOW}–{TARGET_HIGH} %){sample}."
    return "warn", (f"Erkennungsgrad {r['recognized']} % – unter dem Ziel von {TARGET_LOW} %. Mehr Kunden "
                    f"in der Kundenliste (Spuren) und KI-Vorschläge (F6) heben ihn{sample}.")


def summary_text(r):
    """'Erkennungsgrad 84 % · Kunde richtig 95 % · Ticket richtig 81 % · falsches Ticket 4 %'"""
    def p(v):
        return "–" if v is None else f"{v} %"
    return (f"Erkennungsgrad {p(r['recognized'])} · erkannt {p(r['covered'])} · Kunde richtig "
            f"{p(r['customer'])} · sicheres Ticket richtig {p(r['ticket'])} · falsches Ticket "
            f"{p(r['ticket_wrong'])} · vermutetes Ticket richtig {p(r.get('guessed'))}")
