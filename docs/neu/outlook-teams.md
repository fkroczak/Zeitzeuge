# Outlook und Teams als Datenquellen

## README-Text

### Funktionsliste (neuer Punkt)

- **Outlook und Teams** (standardmäßig aus): Zeitzeuge liest aus dem klassischen Outlook
  deine Termine, Teams-Besprechungen und gesendeten Mails. Sie stehen in der eigenen Zeile
  „Outlook“, in der Tagesliste als „Termin“, „Teams-Besprechung“ oder „Mail gesendet“.
  Eine gesendete Mail ist ein kurzer Block (3 Minuten, einstellbar). Standardmäßig zählen
  nur Mails an andere Firmen. Teams-Anrufe stehen in der Zeile „Tel“ wie 3CX. Danach fragt
  Zeitzeuge genauso „Was hast du gemacht?“. Liegt ein Anruf in einer Teams-Besprechung aus
  dem Kalender, trägt er deren Betreff.
- Gespeichert werden nur Betreff, Zeit, Ort und die **Domains** der Teilnehmer oder
  Empfänger (z. B. „kunde.de“). Keine Adressen, keine Mailtexte. Alles liegt verschlüsselt
  in der Datenbank und bleibt auch ohne Outlook sichtbar.
- Regeln ohne KI kennen die neuen Einträge (Teams-Anruf → Telefonsupport,
  Termin → Beratung / Abstimmung, Mail → E-Mail / Kommunikation). Die KI bekommt Termine
  und Mails als eigenen Abschnitt.

### Einrichtung (neuer Abschnitt)

**Outlook und Teams:** Einstellungen → Datenquellen → „Outlook (Termine, Mails)“ und
„Teams-Anrufe“ einschalten. Unter Datenquellen → Einrichten → „Outlook und Teams …“
stellst du ein:

- Termine und gesendete Mails einzeln an oder aus, nur Mails an andere Firmen.
- Domains deiner Firma (leer: Zeitzeuge erkennt sie aus Outlook).
- Dauer je Mail in der Timeline, wie viele Tage zurück und wie oft Zeitzeuge liest.
- Anderer Kalender oder Ordner, z. B. `\\name@firma.de\Kalender`.
- Ob Zeitzeuge Outlook starten darf. Sonst liest es nur, während Outlook offen ist.
- Ab welcher Dauer ein Teams-Anruf zählt (Standard 30 Sekunden).

Gut zu wissen:

- Es geht nur mit dem **klassischen Outlook**. Das neue Outlook hat keine Schnittstelle
  dafür. Zeitzeuge sagt das in der Statuszeile.
- Zeitzeuge fragt Outlook über PowerShell im Hintergrund, ohne Fenster. Admin-Rechte
  braucht es nicht. Meldet Outlook „Ein Programm versucht, auf E-Mail-Adressen
  zuzugreifen“, ist der Virenschutz nicht aktuell gemeldet. Dann „Verweigern“ wählen
  und die Quelle ausschalten oder die IT fragen.
- Teams-Anrufe erkennt Zeitzeuge daran, dass Teams das Mikrofon benutzt (das merkt sich
  Windows). Das gilt auch für Besprechungen. Die Richtung (ein- oder ausgehend) und das
  Gegenüber kennt Teams hier nicht.
- Auf der PAW bleiben Outlook und Teams aus.

## Eigene Entscheidungen

1. **Teams-Anrufe über die Mikrofon-Nutzung (Registry) statt nur über Teams-Logs.**
   Windows hält unter `HKCU\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone\MSTeams_8wekyb3d8bbwe`
   (klassisch: `…\NonPackaged\…#Teams.exe`) `LastUsedTimeStart`/`LastUsedTimeStop` fest.
   Das ist ohne Admin lesbar, dokumentiertes Windows-Verhalten (Datenschutz-Anzeige)
   und hängt nicht vom Logformat von Teams ab. Zeitzeuge schaut alle 30 Sekunden nach.
   Nachteil: Windows kennt nur die letzte Nutzung je App. Zwei Anrufe innerhalb von
   30 Sekunden oder Anrufe, während Zeitzeuge aus war (außer dem letzten), fehlen.
   Besprechungen zählen auch. Rückgängig: `teams_calls_enabled` aus;
   Funktion `teams_calls.mic_readings`.
2. **Teams-Logs als Ergänzung, Format unsicher.** Der Parser (`teams_calls.parse_log`)
   sucht in `MSTeams_*.log` des neuen Teams nach `desktop_call_state_change_send` mit
   `isOngoing: true/false`. So zeigen Community-Werkzeuge (Busylight-Skripte) Anrufe an.
   Microsoft dokumentiert das nicht. Ich konnte es nicht an einem echten Rechner prüfen.
   Die Testdaten in `tests/teams_calls_test.py` sind nachgebaut. Passt das Format nicht,
   findet der Parser nichts, und es bleibt bei der Mikrofon-Erkennung.
   Rückgängig: `teams_logs_enabled: false`.
3. **Teams-Anrufe in der Zeile „Tel“** mit Typ „Teams-Anruf“ und `direction: "Anruf"`.
   So gelten sie überall als Telefonat (`row_kind == "call"`, Nachfrage, Kategorie-Vorschlag
   Telefonsupport, Mindestdauer „Telefonate“). Farbe eigener Typ „Teams-Anruf“ (#464EB8).
   Liegt ein Anruf zur Hälfte in einer Teams-Besprechung, übernimmt er Betreff und
   Teilnehmer-Domains (`teams_meeting: true`). Rückgängig: `teams_calls.call_entries`.
4. **Zeile „Outlook“ nur, wenn die Quelle an ist** (oder übernommene Outlook-Einträge
   da sind). Sonst hätten alle Nutzer eine leere Zeile mehr. `timeline_only.draw_timeline`
   (`has_outlook`). Zeile sitzt direkt unter „Tel“. Menütext „Telefon (3CX)“ heißt jetzt
   „Telefon (3CX, Teams)“. `timeline_rows` hat den Schlüssel `outlook` (Standard an).
5. **Keine Nachfrage für Termine und Mails** und sie zählen nicht als „Verbindungen ohne
   Buchung“ im Matrix42-Abgleich: Ein Kalendereintrag beweist nicht, dass du daran
   gearbeitet hast, und jede Mail würde nachgefragt. `app_docs.doc_candidates` und
   `m42_unbooked` (`row_kind(e) != "outlook"`). Rückgängig: die beiden Bedingungen löschen.
6. **Nur das klassische Outlook, nur wenn es läuft.** `GetActiveObject` statt Outlook zu
   starten (`outlook_start_if_closed: false`): Zeitzeuge soll Outlook nicht ungefragt
   öffnen. Fehlt Outlook ganz (Registry `HKCR\Outlook.Application`), startet Zeitzeuge
   PowerShell gar nicht. Rückgängig: Einstellung „Outlook starten“.
7. **Datensparsamkeit im PowerShell-Skript:** Das Skript gibt nur Domains aus, nie
   Adressen. Mailtexte werden nicht ausgegeben. Der Text einer Einladung wird nur nach
   dem Teams-Link durchsucht, wenn Ort und Teams-Eigenschaft nichts sagen
   (`outlook_check_body`). Private Termine heißen „Privater Termin“, ohne Ort und Domains.
8. **Was nicht gezeigt wird:** ganztägige und abgesagte Termine (sie würden den Tag
   füllen); interne Mails (`outlook_mails_external_only: true`). Als „frei“ eingetragene
   Termine erscheinen mit Hinweis. `outlook_data.appointment_entry`, `mail_entry`.
9. **Ablage:** `outlook` (je Tag `{termine, mails, gelesen, eigene_domain}`) und
   `teams_anrufe` (je Tag Liste). Jeder Outlook-Lauf ersetzt die gelesenen Tage ganz,
   damit verschobene Termine verschwinden. Schlägt ein Ordner fehl, bleibt sein Teil.
   Gelesen werden 14 Tage zurück bis Tagesende, alle 10 Minuten; ältere Tage beim
   Blättern einmal je Sitzung. Eigene Domains: Einstellung, sonst aus Outlook erkannt
   (Exchange-Benutzer bzw. erstes Konto). Gespeichert werden alle Domains, gefiltert wird
   beim Anzeigen (so wirkt eine geänderte Einstellung auch rückwirkend).
10. **Regeln ohne KI:** drei neue Standardregeln am Ende von `rules.DEFAULT_RULES`
    (Teams-Anruf → Telefonsupport, Termin/Teams-Besprechung → Beratung / Abstimmung,
    Mail gesendet → E-Mail / Kommunikation). Bestehende Nutzer haben ihre Regeln in der
    Config und bekommen sie nicht automatisch. Am Ende, damit Indizes bestehender Regeln
    gleich bleiben. Rückgängig: die drei Einträge in `rules.py` löschen.
11. **KI-Eingabe:** Termine und Mails stehen in `ai_classifier.build_day_text` als eigener
    Abschnitt „Termine und gesendete Mails aus Outlook“, nur wenn es welche gibt. Ohne
    Outlook bleibt der Text gleich. `email_domains` hängen als „Domains: …“ an, wenn sie
    nicht schon in den Details stehen. Der Systemprompt ist unverändert.
12. **PowerShell statt pywin32:** keine neue Abhängigkeit. `powershell.exe -NoProfile
    -NonInteractive -ExecutionPolicy Bypass -EncodedCommand`, `CREATE_NO_WINDOW`,
    Zeitlimit 90 s, Ausgabe JSON in UTF-8. Läuft im eigenen Thread (`outlook_reader.py`).
    Datumsfilter für `Items.Restrict` im Format der Windows-Region (`ToString('g')`),
    wie Microsoft es verlangt.
13. **Statuszeile:** kein eigener Knopf in `source_buttons` (hätte `app_daylist.py`
    verändert). Probleme kommen einmal als Meldung in die Statuszeile, nach 5 Fehlern in
    Folge in den Infobereich (wie bei den anderen Lesern). Status im Dialog.
14. **PAW:** `outlook_enabled` und `teams_calls_enabled` stehen in `app_transfer.PAW_OFF`.
    Auf der PAW startet der Leser nie (`app_outlook.apply_outlook_reader`).
15. **Standardfarben:** Termin #0F6CBD, Teams-Besprechung #5B5FC7, Mail gesendet #1F7A8C,
    Teams-Anruf #464EB8 (`main_timeline.load_config_with_defaults`), alle mit Kontrast
    ≥ 4,5 : 1 (Bedienbarkeitstest).

## Offene Punkte / Risiken

- Das PowerShell-Skript ist in CI nur ohne Outlook geprüft
  (`tests/outlook_test.py::test_skript_laeuft_in_powershell`, nur Windows: Syntax und
  JSON-Ausgabe). Mit echtem Outlook bitte einmal von Hand testen (Serientermine,
  Exchange-Empfänger, deutsches Datumsformat).
- Outlook-Sicherheitsabfrage (Object Model Guard) bei veraltetem Virenschutz.
- Format der Teams-Logs (siehe Entscheidung 2).

## Geänderte Dateien

Neu:
- `outlook_data.py` – PowerShell-Skript, Ausgabe prüfen, Einträge bilden, Ablage `outlook`.
- `teams_calls.py` – Mikrofon-Nutzung, Teams-Log-Parser, Zusammenführen, Ablage `teams_anrufe`.
- `outlook_reader.py` – Hintergrund-Leser (Thread, Schnittstelle wie die anderen Leser).
- `outlook_dialogs.py` – Dialog „Outlook und Teams“.
- `app_outlook.py` – Mixin fürs Hauptfenster (Starten/Stoppen, Einträge je Tag, Dialog).
- `tests/outlook_test.py`, `tests/teams_calls_test.py` (Logik), `tests/outlook_gui_test.py` (Skript).

Geändert (klein):
- `main_timeline.py` – Mixin `OutlookMixin`, Pfade `OUTLOOK_FILE`/`TEAMS_CALLS_FILE`,
  `_init_outlook()` nach den anderen Lesern, vier Typfarben.
- `timeline_only.py` – `FIXED_ROWS`/`LEGEND_FIXED`/`TIMELINE_ROWS`/`ROW_NAMES` um
  „outlook“, `OUTLOOK_TYPES`, `row_kind`, `outlook_entries` in `activities_for`,
  Outlook-Zeile nur bei Bedarf.
- `app_menus.py` – `SOURCES` dritte Gruppe +2, Einrichten „Outlook und Teams …“, `toggle_source`.
- `app_readers.py` – `all_readers` nimmt `outlook_reader` mit.
- `app_docs.py` – Termine/Mails nicht nachfragen, nicht als „ohne Buchung“.
- `app_transfer.py` – `PAW_OFF` +2.
- `rules.py` – drei Standardregeln am Ende.
- `ai_classifier.py` – `build_day_text` mit Outlook-Abschnitt.
- `config_defaults.py` – Block „Outlook und Teams“ am Ende, `timeline_rows.outlook`.
- `datastore.py` – Kommentar mit den neuen Ablagenamen.
- `tests/ui_audit_test.py` – Dialog „Outlook und Teams“.
