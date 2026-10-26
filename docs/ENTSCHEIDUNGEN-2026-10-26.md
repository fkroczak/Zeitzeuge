# Eigene Entscheidungen vom 26.10.2026 – und wie man sie zurücknimmt

Umgesetzt wurden die Wünsche aus dem Gespräch vom 26.10.2026: Kundenliste, Lernen aus
Korrekturen, Textbausteine, Outlook/Teams, Prüfung bei Feierabend, 15-Minuten-Takt,
PC-Verlauf löschen (Standard aus), Ticketnummer als Vorschlag, Buchungsquote mit
Wochenabschluss und „In Matrix42 buchen (kommt bald)“.

Diese Datei listet alles, was **nicht** ausdrücklich gewünscht war, sondern selbst
entschieden wurde. Die ausführliche Liste je Thema steht in `docs/neu/`:
`kunden.md`, `eintragen.md`, `outlook-teams.md`, `buchungsquote.md`,
`abrechnung-datenschutz.md` (jeweils Abschnitt „Eigene Entscheidungen“ mit Rückweg).

## Ganze Funktion zurücknehmen

Jede Funktion steckt in genau einem Merge-Commit. Zurücknehmen mit
`git revert -m 1 <Commit>` (spätere Commits können kleine Konflikte bringen, siehe unten):

| Funktion | Merge-Commit |
|---|---|
| Textbausteine, letzte Texte, Ticket-Format, Ticketnummer-Vorschlag | `b695885` |
| 15-Minuten-Takt, PC-Verlauf löschen | `a49e005` |
| Kundenliste, Lernen aus Korrekturen | `7c39462` |
| Buchungsquote, Wochenabschluss, Prüfung bei Feierabend, Matrix42 „kommt bald“ | `fc01e39` |
| Outlook und Teams | `a261857` |

Danach kamen: `47da963` (Fehlerbehebung Eintragen-Dialog), `9874c4a` (README),
`0472c00` (Befunde aus der Prüfung). Wer eine Funktion zurücknimmt, sollte die
passenden Teile dieser Commits mit prüfen.

Fast alles lässt sich auch ohne Code abschalten, über die Einstellungen oder einen
Schlüssel in `zeitzeuge_config.json` (siehe unten).

## Die wichtigsten eigenen Entscheidungen

### Verhalten, das sich für bestehende Nutzer ändert

1. **15-Minuten-Takt ist sofort an** (`billing_mode: "up"`). Grund: ausdrücklicher Wunsch
   („15-Min-Takt wird abgerechnet“). Folge: Kopierte Ticketzeilen zeigen echte und
   abgerechnete Zeiten, z. B. „10:05–10:17 (12 min) → abgerechnet 10:05–10:20 (0:15 h)“
   (Format auf Wunsch so festgelegt; Beginn bleibt, Ende im Takt). Die Statuszeile zeigt
   „abgerechnet …“. Gerundet wird **je Tätigkeit**, die
   angefangene Viertelstunde zählt. Zurück: Einstellungen → Abrechnung → „Ohne Takt“
   (`billing_mode: "off"`), dann ist alles wie früher.
2. **Feierabend-Erinnerung mit ITM-Stempelung:** Ist man ausgestempelt, kommt die
   Erinnerung erst ab dem geplanten Ende, ohne Plan eine Stunde nach dem Ausstempeln.
   Früher kam sie manchmal schon in der Mittagspause. Ohne Stempelung, noch eingestempelt
   oder ohne ITM bleibt es wie früher. Zurück: `app_docs.end_of_day_reminder`.
3. **Prüfung bei Feierabend ist an** (`day_checks_enabled: true`). Sie meldet sich auch,
   wenn Nachfragen aus sind, aber nur einmal am Tag und nur bei einem Befund.
   Zurück: Einstellungen → Nachfragen und Erinnerungen → „Bei Feierabend prüfen“.
4. **Tagesliste zeigt den Kunden zur Spur**, z. B. „Müller GmbH · srv01“, sobald er in der
   Kundenliste steht. Der gespeicherte Name des Eintrags bleibt unverändert.
   Zurück: `app_daylist.py`, `customers.with_customer(...)` durch `a.get("customer_name", "")`
   ersetzen.
5. **Statuszeile zeigt die Buchungsquote** („Quote heute 72 % · 7 Tage 81 %“), nur wenn
   Matrix42 Daten liefert. Aus: `booking_rate_status: false`.
6. **Wochenabschluss nur über die Oberfläche** (Knopf in der Werkzeugleiste, Klick auf die
   Quote in der Statuszeile). Auf Wunsch kein Tastenkürzel; auch F7 (Nachtragen) ist
   entfernt, damit F7–F12 für andere Werkzeuge frei bleiben.

### Datenschutz und Ablage

7. **Kundenliste, gelernte Regeln und Kunden-Ausnahmen des Abrechnungstakts stehen
   verschlüsselt in der Datenbank**, nicht in `zeitzeuge_config.json`. Das ist derselbe
   Weg wie bei den TeamViewer-Namen. Die Datei enthält die Regeln ohne die gelernten.
   Ändert jemand die Regeln in der Datei von Hand, gilt die Datei, und die gelernten Regeln
   werden wieder einsortiert. Zurück: in `main_timeline.py` `DB_KEYS`, `RULES_DOC`,
   `_file_config` und `_merge_learned_rules`.
8. **Ist die Datenbank beim Start gesperrt**, überschreibt Zeitzeuge die Kundenliste usw.
   beim Speichern nicht (`UNREAD_KEYS` in `main_timeline.py`).
9. **PC-Verlauf löschen:** Behalten werden heute und die letzten N Tage (Standard 90).
   Es läuft kein VACUUM (zu langsam, sperrt alles). Gelöschte Zeilen werden vorher mit
   Nullen überschrieben und `secure_delete` ist beim Löschen an. Reste verschlüsselter Daten
   können trotzdem in ungenutztem Platz einzelner Seiten bleiben, bis SQLite ihn neu
   beschreibt (unter Windows im Test gesehen). Ganz sicher entfernt sie nur ein VACUUM. Die alten Ordner `alt-<Datum>/` bleiben unangetastet.
10. **Outlook:** Gespeichert werden nur Betreff, Zeit, Ort und Domains, keine Adressen und
    keine Mailtexte. Zeitzeuge liest nur, wenn Outlook schon läuft
    (`outlook_start_if_closed: false`). Ganztägige und abgesagte Termine fallen weg.

### Lernen und Vorschläge

11. **„Als Regel merken“ ist standardmäßig nicht angehakt.** Regeln entstehen nur, wenn
    du das willst. „Kunde merken“ ist angehakt, wie bisher bei TeamViewer.
    Aus: `rules_learn_offer: false`, `customers_learn: false`.
12. **Hat ein Eintrag keinen brauchbaren Namen** (z. B. nur eine Telefonnummer), lernt die
    Regel auf den Typ („Telefonat“). Eine solche Regel setzt nur die Kategorie, nie einen
    Kunden, sonst bekämen alle Telefonate denselben Kunden.
13. **Gelernte Regeln stehen vor den Standardregeln** und schlagen im Dialog die Kategorie
    vor. Die Standardregeln ändern den Vorschlag im Dialog nicht.
14. **Ticketnummer:** Das Muster ist `TCK\d+`. Gesucht wird 5 Minuten vor und nach der
    Tätigkeit, im PC-Verlauf und in Matrix42-Buchungen. Die Nummer wird nur vorgeschlagen,
    erst „Übernehmen“ setzt sie. Muster ändern: Einstellungen → Textbausteine.
15. **Textbausteine:** Es gibt 10 Standardsätze. „Zuletzt benutzte Texte“ ist an
    (`snippets_recent`). Das Ticket-Format „- “/„-- “ ist aus (`ticket_format: ""`).

### Buchungsquote

16. **Personalzeit** ist der ITM-Wert „gewertet“, solange man ausgestempelt ist; sonst
    zählen die gestempelten Abschnitte bis jetzt. Ohne ITM gilt die Arbeitszeit aus den
    Einstellungen. Sie ist so gekennzeichnet und zählt für den 7-Tage-Wert nur an Tagen
    mit Buchungen.
17. **Tage ohne gelesene Matrix42-Daten** zählen im 7-Tage-Wert nicht als 0 %. Sie werden
    als „Matrix42 nicht gelesen“ genannt.
18. **Buchungen außerhalb der Personalzeit zählen mit.** Die Quote kann deshalb über 100 %
    liegen. Die Prüfung bei Feierabend meldet solche Buchungen.

### Outlook und Teams

19. **Teams-Anrufe** werden vor allem daran erkannt, dass Teams das Mikrofon benutzt
    (Registry, ohne Admin). Die Teams-Logs dienen nur als Ergänzung. Ihr Format ist nicht
    dokumentiert und **nicht an einem echten Rechner geprüft**. Besprechungen zählen mit.
20. **Teams-Anrufe stehen in der Zeile „Tel“** und werden nachgefragt wie 3CX. Termine und
    Mails werden nicht nachgefragt und zählen nicht als „ohne Buchung“.
21. **Drei neue Standardregeln** für Teams-Anruf, Termin und Mail. Bestehende Nutzer
    bekommen sie nicht automatisch, weil ihre Regeln schon in der Config stehen.

### Beim Zusammenführen und Prüfen behoben

- Im Eintragen-Dialog stand bei TeamViewer und RDM die Beschriftung „… merken“ im Textfeld
  (`47da963`).
- Mehrere Befunde aus der Prüfung des gesamten neuen Codes (`0472c00`).

## Noch offen

- **In Matrix42 buchen:** wartet auf deine Angaben. Vorbereitet sind `m42_booking.py`
  (Platzhalter) und `billing.booking_span` (Ende auf den Takt gerundet).
- **Outlook und Teams mit echtem Outlook und Teams von Hand testen:** Serientermine,
  deutsches Datumsformat beim Filtern, Sicherheitsabfrage von Outlook, Teams-Mikrofon.
