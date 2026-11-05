# Tagesabschluss: Womit die Erkennungsleistung gewährleistet wird

Stand 03.11.2026, Branch `claude/zeitzeuge-auto-ticket-booking-4gc5t4`.

## Kurzfassung

| Frage | Antwort |
|---|---|
| Wie hoch ist der Erkennungsgrad? | Im Prüfstand **85–91 %** bei gut eingerichtetem Zeitzeuge, **72–78 %** bei lückenhafter Kundenliste mit internem Ticket, **54–64 %** ohne beides (je 10 Durchläufe à 40 Arbeitstage). |
| Wie oft stimmt der Kunde? | **97–99 %** der vorgeschlagenen Zeit, in jedem Profil. |
| Wie oft würde ohne Rückfrage ein falsches Ticket gebucht? | **1–2 %** der Zeit mit sicherem Ticket. Vorher (ohne die neuen Sicherungen) waren es 22 %. |
| Wie gut ist es an meinen echten Tagen? | Das misst **Tagesabschluss → Erkennung messen …** an deinen eigenen Ticketsystem-Buchungen der letzten 20 Tage. |
| Kann es von selbst falsch buchen? | Nein. Gebucht wird nur nach deinem Klick, ohne Rückfrage nur mit sicherem Ticket. |

**Ehrlich gesagt:** 70–90 % lassen sich nicht für jeden denkbaren Tag versprechen. Was Zeitzeuge
nicht sieht (Arbeit ohne PC-Spur, unbekannte Anrufer, Ticketarbeit ohne Ticketnummer im
Fenstertitel), kann es nicht zuordnen. Gewährleistet ist dreierlei:
1. Der Prüfstand hält bei jedem Build Mindestwerte fest.
2. Die Messung zeigt dir jederzeit den echten Wert auf deinen Daten.
3. Die Sicherungen sorgen dafür, dass eine Lücke in der Erkennung zu einer leeren Zeile führt, nicht zu einer falschen Buchung.

## 1. Was „Erkennungsgrad“ heißt

Die richtige Antwort ist, was du im Ticketsystem gebucht hast. Gemessen wird Minute für Minute:

- **Erkennungsgrad** = gebuchte Zeit, für die der Tagesabschluss den richtigen Kunden vorgeschlagen
  hätte ÷ gebuchte Zeit. Ziel 70–90 %.
- **Kunde richtig** = Anteil der vorgeschlagenen Zeit mit dem richtigen Kunden.
- **Falsches Ticket** = Anteil der Zeit mit *sicherem* Ticket, bei der ein anderes Ticket gebucht
  wurde. Nur solche Tickets bucht der Tagesabschluss ohne Rückfrage. Ziel unter 10 %, erreicht 1–2 %.
- **Vermutetes Ticket richtig** = Trefferquote der Tickets „zuletzt für den Kunden“ (rund 78 %).
  Deshalb werden sie nur nach Bestätigung gebucht.

## 2. Drei Säulen der Gewährleistung

### a) Messung an deinen echten Daten (`day_close_eval.py`)

Knopf **Erkennung messen …** im Fenster Tagesabschluss:

- Für jeden der letzten 20 Tage mit Ticketsystem-Buchungen rechnet Zeitzeuge die Vorschläge so, als wäre
  nichts eingetragen und nichts gebucht. Ticketnummern aus den Buchungen des Tages selbst zählen dabei
  nicht.
- Die Vorschläge vergleicht es mit deinen echten Buchungen.
- Das Ergebnis zeigt Erkennungsgrad, Kunde richtig, Ticket richtig, falsches Ticket und je Tag
  den Erkennungsgrad, dazu ein Urteil: im Ziel, unter dem Ziel (mit Tipp) oder Warnung bei zu vielen
  falschen Tickets.

### b) Prüfstand bei jedem Build (`tests/day_close_benchmark_test.py`)

40 nachgebaute Arbeitstage mit bekannter Wahrheit und den Störungen echter Tage:

- Verbindungen beginnen bis 4 Minuten später und enden bis 5 Minuten früher.
- Unbekannte TeamViewer-IDs, Anrufer nur als Nummer.
- Ticketarbeit am PC ohne Kundennamen, nur teils mit Ticketnummer im Fenstertitel.
- Interne E-Mail-Zeit, kurze Splitter (Teams) mitten in der Arbeit.
- Kunden heißen im Ticketsystem anders als in den Spuren („Müller GmbH“ / „Mueller“).
- Tickets wechseln (neue Anliegen).

Der Build schlägt fehl, wenn eine spätere Änderung unter diese Grenzen fällt:

| Profil | Erkennungsgrad mindestens | gemessen (10 Durchläufe) |
|---|---|---|
| gut eingerichtet (Kundenliste gepflegt, internes Ticket für E-Mail) | 80 % | 85–91 % |
| lückenhafte Kundenliste, internes Ticket | 70 % | 72–78 % |
| lückenhafte Kundenliste, ohne internes Ticket | 55 % | 54–64 % |
| immer | Kunde richtig ≥ 95 %, falsches Ticket ≤ 3 % | 97–99 % / 1–2 % |

Ein Gegentest stellt sicher, dass der Prüfstand Verschlechterungen überhaupt bemerkt.

### c) Sicherungen gegen Fehlbuchungen

1. **Gebucht wird nur auf Klick.** Zeitzeuge bucht nie von selbst.
2. **Ohne Rückfrage nur sichere Tickets:** Ticketnummer im Fenstertitel, von Hand eingetragen oder
   das eingestellte interne Ticket. Vermutete Tickets bucht es nur nach **Vermutete mitbuchen**.
   Der Standardknopf der Rückfrage ist **Nur sichere buchen**.
3. **Gegenprobe Ticket ↔ Kunde:** Gehört ein Ticket laut Verlauf einem anderen Kunden, wird es
   verworfen.
4. **Strenger Kundenvergleich:** andere Schreibweise ja, ähnliche Firmen nie („Auto Huber“ ≠
   „Bäckerei Huber“). Mehrdeutig heißt: kein Ticket.
5. **Kein fremdes Ticket über den Rand:** Tickets kommen nur aus dem eigenen Block, nicht aus
   angrenzenden Buchungen.
6. **Keine Doppelbuchung:** Schon Gebuchtes wird ausgespart. Zeilen, die eine vorhandene
   Ticketsystem-Buchung überschneiden, werden nicht gebucht. Gebuchte Tätigkeiten merken sich die Nummer
   der Zeiterfassung. Schließt du das Fenster mitten im Buchen, wird die laufende Buchung noch
   vermerkt.
7. **Keine Überschneidung durch den Abrechnungstakt:** Folgebuchungen rücken nach.
8. **Status „Neu“:** Jede Buchung lässt sich im Ticketsystem vor dem Freigeben prüfen.

## 3. Was die Erkennung verbessert hat

| Maßnahme | Wirkung im Prüfstand |
|---|---|
| Vermutete Tickets getrennt, nur mit Bestätigung | falsches Ticket 22 % → 1 % |
| Ticketarbeit am PC je Ticket getrennt | falsche Kunden durch verschmolzene Blöcke fast weg (Kunde richtig 93 % → 99 %) |
| Kunde zum Ticket aus dem Verlauf (14 Tage Ticketsystem + Tätigkeiten) | Ticketarbeit ohne Kundennamen wird zugeordnet |
| Kunde zu neuen Tickets über die Ticketsuche des Ticketsystems (im Fenster) | neue Tickets werden zugeordnet (im Prüfstand nicht mitgezählt, also zusätzlich) |
| Unscharfer Kundenvergleich | „Müller GmbH“ im Ticketsystem = „Mueller“ in der Kundenliste |
| Internes Ticket je Kategorie | E-Mail-Zeit +14 Prozentpunkte, ohne Ticketarbeit falsch zuzuordnen |

## 4. So erreichst du 70–90 % im Alltag

Der Erkennungsgrad hängt davon ab, was Zeitzeuge sehen kann. In dieser Reihenfolge lohnt es sich:

1. **Internes Ticket einstellen** (`day_close_internal` mit `categories`, z. B. E-Mail und Teams).
   Bringt im Prüfstand am meisten (+14 Punkte).
2. **Kundenliste pflegen:** TeamViewer-IDs, Telefonnummern, RDM- und VPN-Namen. Am einfachsten beim
   Eintragen „Kunde … merken“ angehakt lassen.
3. **Ticket im Browser offen haben**, während du daran arbeitest. Dann steht die Ticketnummer im
   Fenstertitel, und Zeitzeuge findet Ticket und Kunden.
4. **KI-Vorschläge (F6)** vor dem Abschluss: bessere Texte, zusätzliche Zuordnung.
5. **Erkennung messen …** nach ein, zwei Wochen ansehen. Liegt der Wert unter 70 %, sagt das Urteil,
   woran es liegt.

## 5. Grenzen

- Der Prüfstand bildet typische Tage nach, nicht deine. Maßgeblich ist die Messung an deinen
  Buchungen.
- Gemessen werden kann nur, was im Ticketsystem gebucht ist. Tage ohne Ticketsystem-Daten zählen nicht.
- Gelernte Regeln aus späteren Korrekturen fließen beim Nachspielen alter Tage schon mit ein. Die
  Messung kann dadurch etwas zu gut ausfallen.
- Eine echte Buchung gegen das Ticketsystem ist in dieser Umgebung nicht prüfbar (nur im Firmennetz). Die
  Sammelbuchung nutzt den vorhandenen, schon erprobten Buchungsweg.
