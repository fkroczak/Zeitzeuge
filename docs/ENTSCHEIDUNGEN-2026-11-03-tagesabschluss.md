# Tagesabschluss – eigene Entscheidungen vom 02./03.11.2026 und wie man sie zurücknimmt

**Auftrag (02.11.2026, sinngemäß):** Zeitzeuge soll alle Tätigkeiten erkennen, als Block je Kunde /
Zeiteintrag / Ticket mit kurzem Tickettext vorbereiten und bei Abschluss der Tätigkeit bzw. am Ende
des Tages die Tickets teilautomatisiert buchen. Die bestehende Funktion soll nicht geändert, sondern
um die Ticketbuchung ergänzt werden. Ziel: mit wenig Aufwand rund 90 % dokumentierte Zeit.
Entscheidungen durfte ich selbst treffen, sie sollen genau dokumentiert sein.

Branch: `claude/zeitzeuge-auto-ticket-booking-4gc5t4` (noch nicht in main, kein PR angelegt).

## Was neu ist (Kurzfassung)

| Datei | Inhalt |
|---|---|
| `day_close.py` (neu) | Reine Logik ohne Qt: Minutenraster, Vorrang der Spuren, Blöcke, Lücken, Ticket, Text, Kennzahlen |
| `app_day_close.py` (neu) | Mixin am Hauptfenster: Spuren einsammeln, Fenster öffnen, Text für die Feierabend-Meldung |
| `day_close_dialog.py` (neu) | Fenster „Tagesabschluss“: Tabelle, Haken, Bearbeiten, Sammelbuchung, Einzeln buchen |
| `tests/day_close_test.py` (neu) | 13 Logik-Tests |
| `tests/day_close_gui_test.py` (neu) | Oberflächentest mit nachgebautem Matrix42 (Sammelbuchung, Wiederholung, nur dokumentieren, Meldung) |
| `main_timeline.py` | Mixin `DayCloseMixin` eingehängt (1 Import, 1 Klassenname) |
| `app_menus.py` | Eintrag **Ansicht → Übersichten → Tagesabschluss …** |
| `week_dialogs.py` | Knopf **Tagesabschluss …** im Wochenabschluss (für den markierten Tag) |
| `app_docs.py` | `end_of_day_reminder`: zusätzlicher Text und Klickziel, wenn Vorschläge bereitliegen |
| `app_tray.py` | Klick auf diese Meldung öffnet den Tagesabschluss |
| `config_defaults.py` | 4 neue Schlüssel `day_close_*` |
| `icons.py` | Symbol `check` (Lucide „circle-check“) |
| `tests/settings_window_test.py` | Menü Ansicht darf 15 statt 14 Einträge haben (siehe E8) |
| `tests/ui_audit_test.py` | neue Dateien in die Prüflisten aufgenommen |
| `README.md`, `CHANGELOG.md` | Abschnitt Tagesabschluss, Config-Tabelle, Projektstruktur |

Unverändert geblieben: Nachfragen, Eintragen-Dialog, KI, Regeln, Ticketvorschlag, das Fenster
„In Matrix42 buchen“ und `book_in_m42` / `book_day_in_m42`, `m42_booking.py`, `m42_reader.py`,
Journal-Format (nur neue Werte in bestehenden Feldern, siehe E6).

## Entscheidungen

**E1 – Eigenes Fenster „Tagesabschluss“ statt Automatik ohne Rückfrage.**
Zeitzeuge bucht auch hier nie von selbst. „Teilautomatisiert“ heißt: Vorschläge sind fertig
vorbereitet und vorausgewählt, ein Klick dokumentiert und bucht alle. Grund: Buchungen in Matrix42
gehen an Kunden; eine stille Fehlbuchung kostet mehr als ein Klick.
*Rückweg:* Fenster nicht nutzen; oder komplett entfernen (siehe „Ganz zurücknehmen“).

**E2 – Vorrang der Spuren: gebucht > eigene Tätigkeit > Verbindung/Telefonat > KI > Regel > PC.**
Jede Spur bekommt nur Minuten, die noch frei sind. Verbindungen sind am verlässlichsten (Logs), KI
bringt den besten Text, PC-Aktivität ist nur Auffüllmaterial.
*Rückweg/Anpassen:* Reihenfolge in `app_day_close.day_close_evidence` (Stufenzahlen 1–4).

**E3 – Regeln und PC-Aktivität zählen nur in der Personalzeit.** Verbindungen und Telefonate zählen
immer (auch abends: Bereitschaft). Ohne ITM gilt die Arbeitszeit aus den Einstellungen.
*Rückweg:* In `day_close.build` `work_only=tier >= 3` auf `False` setzen.

**E4 – Blöcke je Kunde, kurze Lücken auffüllen.** Gleicher Kunde hintereinander ist ein Block
(ohne Kunde: gleiche Kategorie). Lücken bis 10 Minuten in der Personalzeit gehören zum Block davor
(sonst zum Block danach), Blöcke unter 5 Minuten gehen im Nachbarn auf. Größere Lücken werden
**nicht** angeknabbert, sie stehen als „nicht zugeordnet“ (ohne Haken) da.
*Anpassen:* `day_close_gap_minutes`, `day_close_min_minutes` in der Config.

**E5 – Ticket: Fenstertitel/Matrix42 rund um den Block, sonst zuletzt für den Kunden (14 Tage).**
Der zweite Weg ist neu und eine Vermutung; er wird im Hinweis als Quelle „zuletzt für den Kunden“
angezeigt und senkt die Sicherheit auf „mittel“.
*Rückweg:* in `day_close._draft` den Block `if not ticket and customer and last_ticket…` löschen,
oder `HISTORY_DAYS = 0`.

**E6 – Gespeichert wird als normale Tätigkeit mit `source: "Tagesabschluss"` und `answered`.**
Damit erscheint alles in Zeile „Doku“, Ansicht Dokumentation, Kopieren, Buchungsquote; Nachfragen zu
diesen Zeiten entfallen (gleiches Feld `answered` wie bei der Nachfrage). Gebuchte bekommen wie bisher
`m42_entry` / `m42_booked`. Kein neues Datenformat.
*Rückweg:* Tätigkeiten mit `source == "Tagesabschluss"` lassen sich gezielt finden und löschen.

**E7 – Sammelbuchung ohne Überschneidungen durch den Abrechnungstakt.** Jede Buchung nutzt wie
bisher `m42_booking.plan` (Beginn bleibt, Ende im Takt). Ragt eine Buchung dadurch in die nächste,
rückt die nächste ans Ende der vorigen (`day_close.sequence_plans`), die abgerechnete Dauer bleibt.
Der Hinweis in der Zeile sagt „verschoben“. Zeilen, die sich mit einer schon vorhandenen
Matrix42-Buchung überschneiden, werden nicht gebucht („Einzeln buchen …“).
Grund: Die Prüfung bei Feierabend meldet sonst „Buchungen überschneiden sich“.
*Rückweg:* Aufruf `dc.sequence_plans(...)` in `day_close_dialog.run` entfernen.

**E8 – Menü Ansicht: 15 statt 14 Einträge.** Der neue Eintrag steht in der Gruppe „Übersichten“
(jetzt 3 von höchstens 5, Regel aus `docs/quality-guardrails.md` eingehalten). Die Gesamtgrenze im
Test `settings_window_test.py` habe ich von 14 auf 15 angehoben.
*Rückweg:* Eintrag in `app_menus.py` löschen, Testgrenze zurück auf 14.

**E9 – Kein Tastenkürzel.** Erst F7 vorgesehen, dann verworfen: Laut README bleiben F7–F12 bewusst
frei. Zugang: Menü Ansicht, Knopf im Wochenabschluss, Klick auf die Feierabend-Meldung.

**E10 – Feierabend-Meldung nennt den Tagesabschluss (einzige Verhaltensänderung an Bestehendem).**
Liegen Vorschläge bereit, steht in der Meldung z. B. „Tagesabschluss: 5 Vorschläge bereit, danach
92 % der Personalzeit erfasst. Klick hier zum Prüfen und Buchen.“ und der Klick öffnet den
Tagesabschluss statt der Ansicht Dokumentation (der Tagesabschluss enthält das Offene ebenfalls).
Die Meldung kommt jetzt auch dann, wenn nichts „offen“ und nichts zu prüfen ist, aber Zeit ohne
Buchung mit Vorschlägen bereitliegt (weiterhin höchstens einmal am Tag, gleiche Uhrzeit-Logik).
*Rückweg ohne Code:* `"day_close_end_of_day": false` in der `zeitzeuge_config.json` – dann ist die
Meldung exakt wie vorher. *Mit Code:* die Änderungen in `app_docs.end_of_day_reminder` und
`app_tray.on_tray_message_clicked` zurücknehmen.

**E11 – Kein automatisches Buchen direkt nach jeder Nachfrage.** „Bei Abschluss der Tätigkeit“ ist
abgedeckt, weil der Tagesabschluss jederzeit (auch mittags) für die schon beendeten Tätigkeiten
geöffnet werden kann. Ein zusätzlicher Knopf „gleich buchen“ im Nachfrage-Fenster hätte das kleine
Fenster überladen und das Bestehende geändert. Vorschlag für später, siehe unten.

**E12 – Internes Ticket optional, Standard leer.** Zeit ohne Kunden (E-Mail, Excel) bleibt ohne
Haken, außer `day_close_internal` ist gesetzt. Ohne diese Einstellung sind 90 % an Tagen mit viel
interner Arbeit nicht erreichbar; mit ihr schon. Ich wollte aber kein Ticket raten.

**E13 – Tabellenfenster, Kunde/Ticket/Text direkt änderbar, Zeiten nicht.** Zeiten ändern geht über
„Einzeln buchen …“ (Von/Bis im bekannten Fenster) oder später über „Tätigkeit bearbeiten“.
Hält das Fenster einfach.

**E14 – Hauptknopf mit eigener Mindestbreite.** Das Design setzt `min-width: 80px` und den
Standardknopf fett; Qt rechnet die Breite mit normaler Schrift, der Text wurde abgeschnitten. Nur im
neuen Fenster per eigenem Stylesheet am Knopf behoben (das Problem kann es bei anderen langen
Standardknöpfen auch geben; dort nicht angefasst).

## Geprüft

- `pytest -m "not browser"`: 266 bestanden, 1 übersprungen (vorher 252 + 1; neu 13 Logik-Tests und
  1 Oberflächentest). Browser-Tests (Edge) liefen hier nicht.
- `tests/readability_check.py`: README 65, UI-Texte 63 (Grenzen 55 / 50).
- Bildschirmfoto mit Beispieldaten: `docs/screenshots/2026-11-03/tagesabschluss.png`.
- **Nicht** geprüft: echte Buchung gegen Matrix42 (nur im Firmennetz möglich). Die Sammelbuchung
  nutzt aber ausschließlich den vorhandenen, schon erprobten Weg `M42Reader.book`.

## Für die Abnahme

1. EXE aus dem Branch-Build holen (GitHub Actions, Version „4.1.x · Test …“).
2. Einen gearbeiteten Tag anzeigen, **Ansicht → Tagesabschluss …**.
3. Prüfen: Stimmen die Blöcke je Kunde? Passen Ticket und Text? Wie hoch ist „mit den angehakten
   Zeilen … %“?
4. Erst **Nur dokumentieren** testen (bucht nichts), dann an einem Tag **Dokumentieren und buchen**
   und in Matrix42 nachsehen (Status „Neu“).

## Ideen für danach (nicht umgesetzt)

- Knopf „gleich buchen“ im Nachfrage-Fenster, wenn ein Ticket erkannt wurde.
- Text optional per KI aus allen Spuren des Blocks formulieren lassen (heute: KI-Vorschläge nur,
  wenn F6 lief).
- Tätigkeitsart je Kategorie merken (heute: zuletzt benutzte Tätigkeitsart für alle).

## Ganz zurücknehmen

Alle Commits liegen auf dem Branch oben. Vor dem Merge: Branch einfach nicht mergen. Nach dem
Merge: `git revert -m 1 <Merge-Commit>`. Daten bleiben gültig: Tätigkeiten aus dem Tagesabschluss
sind normale Tätigkeiten.
