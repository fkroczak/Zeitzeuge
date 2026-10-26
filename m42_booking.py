"""In Matrix42 buchen – kommt bald.

Hier entsteht später das direkte Buchen einer dokumentierten Tätigkeit in Matrix42
(Service Desk, Zeitbuchung am Ticket). Die nötigen Angaben (Schnittstelle, Felder,
Anmeldung) liefert der Nutzer noch. Bis dahin zeigen das Rechtsklick-Menü einer
Tätigkeit ("m42_book") und der Wochenabschluss einen deaktivierten Eintrag.

Geplant:
- book(item): Tätigkeit aus dem Journal ({start, end, customer, category, text}) als
  Zeitbuchung am Ticket anlegen (Ticketnummer aus dem Text, z. B. TCK0000049374).
- Danach den Tag neu lesen (m42_reader.want), damit Zeile "Matrix42" und Buchungsquote
  die neue Buchung zeigen.
- Keine Rundung hier: gebucht wird die echte Zeit (oder der Abrechnungstakt, wenn der
  Nutzer das so einstellt).
"""

AVAILABLE = False
COMING_SOON = "Kommt bald: Tätigkeiten direkt in Matrix42 buchen"


def book(item):
    """Tätigkeit in Matrix42 buchen. Noch nicht verfügbar."""
    raise NotImplementedError(COMING_SOON)
