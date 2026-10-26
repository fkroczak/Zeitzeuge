# Zeitzeuge

**Zeitzeuge zeigt dir auf einer Tages-Timeline, woran du gearbeitet hast.** Das Programm liest die Spuren, die deine Werkzeuge ohnehin hinterlassen: TeamViewer-Verbindungen, Sitzungen aus dem Remote Desktop Manager, VPN-Verbindungen aus Sophos Connect und FortiClient und Telefonate aus 3CX. Dazu merkt es sich, welches Fenster gerade aktiv war. So kannst du Tickets lückenlos schreiben und musst nicht mehr raten, wann du bei welchem Kunden warst.

Gedacht ist Zeitzeuge für IT-Dienstleister und Admins, die ihre Zeiten nachträglich erfassen oder abrechnen.

![Zeitzeuge Timeline](zeitzeuge.png)

## Funktionen

- **Tages-Timeline** von 00:00 bis 24:00 mit markierter Arbeitszeit. Telefonate, VPN und TeamViewer haben je eine feste Zeile („Tel“, „VPN“, „TV“). So siehst du sofort, wann du telefoniert hast oder verbunden warst. Darunter folgen RDM und eigene Einträge; überlappen sie sich, rücken sie in die nächste Zeile. Links steht eine Legende mit Name und Farbe jeder Zeile; sie bleibt beim Blättern stehen. Alle Zeilen passen ohne senkrechte Scrollleiste ins Fenster, bei vielen Zeilen werden sie niedriger (UMSCHALT + Mausrad blättert, falls es trotzdem eng wird).
- **TeamViewer:** liest `Connections.txt` mit Sitzungs-ID, Beginn und Ende. Verbindungen unter 1 Minute werden ausgeblendet.
  - Statt der ID kannst du einen Namen vergeben: Rechtsklick auf die Verbindung (Tagesliste oder Timeline), dann **TeamViewer-ID benennen …**.
- **Remote Desktop Manager (Devolutions):** liest `Connections.log`.
  - RDP-, SSH-, VPN-, FTP- und Website-Verbindungen mit Beginn und Ende.
  - Angezeigte Passwörter, Benutzernamen und Einmal-Passwörter (OTP).
- **VPN aus Sophos Connect:** liest `scvpn.log` und `scgui.log` aus `C:\Program Files (x86)\Sophos\Connect`. Jede Verbindung erscheint mit Beginn, Ende und dem Namen, den du ihr in Sophos Connect gegeben hast (z. B. „Kunde Müller“).
  - Ist der PC eingeschlafen, endet die Verbindung beim Einschlafen.
  - Sophos überschreibt seine Logs bei Neustarts und neuen Verbindungen. Zeitzeuge liest sie deshalb alle 2 Minuten und hebt alles in der Datenbank auf, egal welcher Tag gerade angezeigt wird.
- **Eigene VPN-Aufzeichnung:** Zeitzeuge prüft alle 30 Sekunden selbst, ob ein VPN-Adapter von Sophos oder Fortinet verbunden ist, und speichert das sofort in der Datenbank. Das läuft auch, wenn das Fenster im Infobereich liegt.
  - So bleiben die Zeiten erhalten, auch wenn die Logs fehlen oder gelöscht sind. Beginn und Ende sind auf etwa 30 Sekunden genau.
  - Steht dieselbe Verbindung auch in den Logs, zeigt Zeitzeuge nur den Eintrag aus den Logs, weil er den Namen kennt.
  - Ruhezustand, Absturz oder ein Neustart von Zeitzeuge beenden den laufenden Eintrag beim letzten Blick auf den Adapter.
  - Weitere Adapter (z. B. WireGuard) trägst du in der `zeitzeuge_config.json` unter `vpn_adapters` ein: Teil der Adapterbeschreibung und Name der Quelle. Mit `vpn_monitor_enabled: false` schaltest du die Aufzeichnung ab.
- **VPN aus FortiClient:** steht ebenfalls in Sophos' `charon.log`, weil dort jede Änderung an Netzwerkadaptern landet. Zeitzeuge zeigt die Zeiten als „FortiClient“, aber ohne Namen der Verbindung. Ohne installiertes Sophos Connect gibt es diese Quelle nicht.
  - Andere Ordner trägst du in der `zeitzeuge_config.json` unter `sophos_connect_dirs` ein.
- **Telefonate aus 3CX:** Zeitzeuge liest die Anrufliste selbst aus dem 3CX-Webclient, ohne dass du die Webseite offen haben musst.
  - Alle gelesenen Anrufe landen in der Datenbank. So entsteht eine eigene Anrufliste, die auch offline bleibt.
  - Zeitzeuge scrollt die Liste so viele Tage zurück, wie du einstellst (Standard 14). Blätterst du in Zeitzeuge auf einen älteren Tag, liest es automatisch bis dorthin nach.
- **Personalzeiten aus der ITM-Zeiterfassung:** Zeitzeuge liest deine gestempelten Zeiten und hebt sie in der Timeline als Arbeitszeit hervor. Pausen sind abgedunkelt. Die Statuszeile zeigt die gewertete Zeit und die Sollzeit.
  - Offene oder fehlerhafte Buchungen meldet Zeitzeuge einmal im Infobereich, zum Beispiel „Buchung vom 21.10. 08:02 ist seit über 12 Stunden offen – Ausstempeln vergessen?“ oder „Ende liegt vor dem Start“.
  - Die letzten 45 Tage holt Zeitzeuge in einer Abfrage. Tage, die noch fehlen, sind damit auch offline da.
- **Gebuchte Zeiten aus Matrix42 (nur im Firmennetz):** Zeitzeuge liest deine Buchungen aus dem Matrix42-Kalender (Service Desk → Kalender) und gleicht sie mit dem Tag ab.
  - Einrichten: **Einstellungen → Datenquellen → Einrichten → Matrix42 …**, dort die Adresse der Kalenderseite aus der Adresszeile einfügen. Die Windows-Anmeldung klappt meist von selbst, sonst einmal **Bei Matrix42 anmelden …**.
  - Edge liest die Wochenansicht unsichtbar mit eigenem Profil (`m42_profil`): die aktuelle Woche alle 10 Minuten, die letzten 4 Wochen einmal pro Sitzung (einstellbar), ältere Wochen beim Blättern. Alles landet in der Datenbank und bleibt auch außerhalb des Firmennetzes da.
  - Außerhalb des Firmennetzes steht in der Statuszeile „M42: nicht im Firmennetz“; Zeitzeuge liest weiter, sobald du wieder im Netz oder im VPN bist.
  - **Zeile „Matrix42“** in der Timeline: graue Blöcke sind gebucht (Kunde · Betreff), rot gestrichelte Lücken sind Personalzeit (ohne ITM: Arbeitszeit) ohne Buchung. Ein Klick auf eine Lücke trägt ab dort eine Tätigkeit ein.
  - **Tagesliste → Matrix42-Abgleich:** Buchungen mit Ticketnummer, Lücken ohne Buchung und Verbindungen/Telefonate, die höchstens zur Hälfte gebucht sind („Nicht gebucht: TeamViewer“).
  - Die Statuszeile zeigt z. B. „Matrix42 gebucht 7:05 h, nicht gebucht 1:55 h, 1 Verbindung ohne Buchung“.
- **Outlook und Teams** (standardmäßig aus): Zeitzeuge liest aus dem klassischen Outlook deine Termine, Teams-Besprechungen und gesendeten Mails. Sie stehen in der eigenen Zeile „Outlook“, in der Tagesliste als „Termin“, „Teams-Besprechung“ oder „Mail gesendet“. Eine gesendete Mail ist ein kurzer Block (3 Minuten, einstellbar). Standardmäßig zählen nur Mails an andere Firmen. Teams-Anrufe stehen in der Zeile „Tel“ wie 3CX. Danach fragt Zeitzeuge genauso „Was hast du gemacht?“. Liegt ein Anruf in einer Teams-Besprechung aus dem Kalender, trägt er deren Betreff.
  - Gespeichert werden nur Betreff, Zeit, Ort und die **Domains** der Teilnehmer oder Empfänger (z. B. „kunde.de“). Keine Adressen, keine Mailtexte. Alles liegt verschlüsselt in der Datenbank und bleibt auch ohne Outlook sichtbar.
  - Regeln ohne KI kennen die neuen Einträge (Teams-Anruf → Telefonsupport, Termin → Beratung / Abstimmung, Mail → E-Mail / Kommunikation). Die KI bekommt Termine und Mails als eigenen Abschnitt.
- **Buchungsquote:** Zeitzeuge rechnet aus, wie viel deiner Personalzeit in Matrix42 gebucht ist. Ziel sind 80 % pro Tag. Unter 50 % ist die Quote rot (✗), bis unter dem Ziel gelb (!), ab dem Ziel bis 100 % grün (✓), darüber dunkelgrün (✓✓). Die Statuszeile zeigt „Quote heute 72 % · 7 Tage 81 %“. Ein Klick öffnet den Wochenabschluss. Die Anzeige erscheint nur, wenn Matrix42 Daten liefert.
- **7-Tage-Wert:** die letzten 7 gestempelten Tage bis heute. Heute zählt nur, wenn du gestempelt hast, und nur bis jetzt. Tage ohne Matrix42-Daten zählen nicht mit. Sie stehen als „Matrix42 nicht gelesen“ da, statt als 0 %.
- **Wochenabschluss** (Knopf mit dem Tacho in der Werkzeugleiste oder Klick auf die Quote in der Statuszeile): Montag bis Freitag der Woche, Samstag und Sonntag nur, wenn du da gestempelt oder gebucht hast. Je Tag: Personalzeit, gebucht, Quote, Zeit ohne Buchung und offene Tätigkeiten. Darunter Hinweise wie „Dienstag: 1:20 h nicht gebucht“ und der 7-Tage-Wert. Mit ◀ ▶ (oder Bild auf/ab) blätterst du die Wochen. Enter oder Doppelklick zeigt den Tag im Hauptfenster. Das Ziel stellst du dort unter „Ziel je Tag“ ein.
- **Prüfung bei Feierabend:** Bist du ausgestempelt und ist Feierabend, prüft Zeitzeuge den Tag einmal: mehr als 6 Stunden ohne 30 Minuten Pause (über 9 Stunden: 45 Minuten, Pausen zählen ab 15 Minuten am Stück), mehr als 6 Stunden am Stück, PC aktiv aber ausgestempelt, Buchung außerhalb der Personalzeit, Buchungen überschneiden sich, Quote unter Ziel. Die Hinweise kommen mit der Erinnerung an offene Tätigkeiten oder allein, und stehen auch im Wochenabschluss. Abschalten: Einstellungen → Nachfragen und Erinnerungen → „Bei Feierabend prüfen“.
- **In Matrix42 buchen:** kommt bald. Rechtsklick auf eine Tätigkeit und der Wochenabschluss zeigen den Befehl schon, noch ausgegraut.
- **Aktivitätsprotokoll:** Alle 5 Sekunden merkt sich Zeitzeuge das aktive Fenster, zum Beispiel eine RDP-Sitzung, einen Browser-Tab, Outlook oder PuTTY.
  - Es erscheint als farbiges Band „PC“ oben in der Timeline, eine Farbe pro Programm.
  - Mit **PC-Verlauf** (Bildschirm-Symbol) in der Werkzeugleiste stehen die Fenster auch in der Tagesliste.
  - Nach 5 Minuten ohne Maus und Tastatur oder bei gesperrtem PC wird nichts aufgezeichnet.
  - Fenster mit bestimmten Wörtern im Titel werden nur als „(ausgeblendet)“ gespeichert, zum Beispiel Passwortmanager.
  - Mit dem **Fenster-Filter** lässt du private Programme ganz weg oder zeichnest nur erlaubte Programme auf.
- **PC-Verlauf automatisch löschen:** Auf Wunsch löscht Zeitzeuge die aufgezeichneten aktiven Fenster nach einer einstellbaren Zahl von Tagen (Standard: aus, sonst 90 Tage). Das gilt auch für den Fensterverlauf, den du von einem anderen PC übernommen hast. Deine Tätigkeiten, Buchungen, KI-Vorschläge, Anrufe und Verbindungen bleiben erhalten. Einschalten unter **Einstellungen → Datenspeicher → PC-Verlauf automatisch löschen …**. Beim Einschalten zeigt Zeitzeuge, wie viele Tage betroffen sind, und fragt nach. Danach löscht es beim Start (nach einer Minute) und einmal am Tag.
- **Zuordnung ohne KI:** Feste Regeln ordnen Verbindungen, Telefonate und Fenster einer Kategorie und einem Kunden zu, zum Beispiel Outlook als „E-Mail / Kommunikation“ oder TeamViewer als „Fernwartung“. Das Ergebnis steht in der Zeile „Zuordnung o. KI“. Es läuft lokal, kostet nichts und braucht kein Internet (früher hieß das „Regeln“).
- **Tagesliste** unter der Timeline mit Von, Bis, Dauer, Typ, Kunde und Details.
  - Die Statuszeile zeigt die belegte Zeit des Tages. Überschneidungen werden nicht doppelt gezählt.
  - Markierte Zeilen kopierst du mit STRG + C, zum Beispiel für die Ticket-Dokumentation.
  - Das Auge in der Werkzeugleiste legt fest, wie die Liste aussieht:
    - **Zusammengefasst** (Standard): Verbindungen zum selben Eintrag mit weniger als 5 Minuten Pause werden eine Zeile. Passwort-, Benutzernamen- und OTP-Anzeigen aus RDM stehen als Zähler bei der Verbindung, zum Beispiel „3 Verbindungen · 2× OTP, 1× Passwort“. Ohne passende Verbindung erscheinen sie als „Zugangsdaten“.
    - **Einzeln:** jede Zeile aus den Logs, wie bisher.
    - **Arbeitsblöcke:** alles mit weniger als 10 Minuten Pause wird ein Block, zum Beispiel „01:18–02:05 · SSL VPN, EPM, OPNsense“. Praktisch fürs Ticket.
  - Die Details eines zusammengefassten Eintrags zeigen alle einzelnen Einträge.
  - Die Pausen stellst du in der `zeitzeuge_config.json` unter `merge_gap_minutes` und `block_gap_minutes` ein.
- **KI-Vorschläge (Claude von Anthropic):** Auf Knopfdruck (F6) ordnet Claude die Spuren des Tages zu Tätigkeiten.
  - Jeder Vorschlag hat Kunde, Kategorie (zum Beispiel Fernwartung oder Telefonsupport) und einen Satz fürs Ticket.
  - Die Vorschläge stehen in der Timeline in einer eigenen Zeile „KI“, lila und gepunktet.
  - Rechtsklick auf einen Vorschlag: **Als Tätigkeit eintragen …** (Text prüfen, speichern, dann durchgezogen), **Vorschlag verwerfen** oder **Kopieren**.
  - In der Tagesliste zeigt die Ansicht **KI-Vorschläge** alle Vorschläge. STRG + C kopiert sie als fertige Ticketzeilen.
- **Tätigkeiten dokumentieren:** Was du gemacht hast, trägst du direkt in Zeitzeuge ein. Es steht in einer eigenen Zeile „Doku“ ganz oben in der Timeline.
  - **Nachtragen** (Knopf in der Werkzeugleiste): Zeit, Kunde, Kategorie und ein Satz, was du gemacht hast. Ist in der Tagesliste eine Zeile markiert, sind Zeit und Kunde schon ausgefüllt.
  - Rechtsklick auf einen Eintrag: **Tätigkeit dazu eintragen …**. Rechtsklick auf eine freie Stelle der Timeline: **Tätigkeit ab hh:mm eintragen …**.
  - Timeline und Tagesliste haben dasselbe Rechtsklick-Menü. Es zeigt nur Befehle, die zum Eintrag passen.
  - **Offenes fällt auf:** Verbindungen und Telefonate ohne Dokumentation stehen gestrichelt mit „?“ in der Zeile „Doku“. Ein Klick darauf öffnet das Eintragen.
  - **Zeitzeuge fragt nach:** Endet eine TeamViewer-Sitzung, eine RDP-/SSH-/VPN-Verbindung oder ein Telefonat, erscheint unten rechts ein kleines Fenster: „Was hast du gemacht?“. Zeit, Kunde und Kategorie sind schon ausgefüllt, du schreibst nur noch einen Satz. **Später fragen** fragt in 15 Minuten wieder, **Nicht dokumentieren** fragt für diesen Eintrag nie mehr. Ab welcher Dauer gefragt wird (Standard: 1 Minute), stellst du unter **Nachfragen und Erinnerungen …** getrennt für Verbindungen, Telefonate und Regel-Blöcke ein.
  - **TeamViewer-ID zum Kunden:** Bei TeamViewer kennt Zeitzeuge oft nur die ID. Trägst du beim Dokumentieren den Kunden ein, merkt es sich den Namen für diese ID. Ab dann steht überall der Name.
  - **Erinnerung:** Nach Feierabend und beim Beenden sagt Zeitzeuge, wie viele Tätigkeiten heute noch offen sind.
  - Sind Tätigkeiten offen, steht rechts unten der blaue Knopf **2 offen – jetzt eintragen**. Ein Klick öffnet die erste offene Tätigkeit zum Eintragen. Die Statuszeile zeigt daneben „dokumentiert 3:10 h“.
  - Dokumentierte Tätigkeiten tragen in der Timeline ein ✓, offene ein ?.
  - Jede Aktion bestätigt Zeitzeuge kurz in der Statuszeile, z. B. „Tätigkeit gespeichert“ oder „Zeitzeuge fragt in 15 Minuten noch einmal“.
  - Die Ansicht **Dokumentation** in der Tagesliste zeigt alles, STRG + C kopiert es als fertige Ticketzeilen.
  - Trägst du einen KI-Vorschlag als Tätigkeit ein, steht er in der Zeile „Doku“ und gilt als übernommen.
- **Textbausteine:** Häufige Sätze wie „Windows-Updates installiert“ fügst du beim Eintragen mit **Text einfügen** (Alt+E) ein. Steht der Cursor am Ende einer Zeile, kommt der Baustein in eine neue Zeile. Die Bausteine 1 bis 9 wählst du im Menü direkt mit der Zahl. Die Liste pflegst du unter Einstellungen → **Textbausteine …**.
- **Zuletzt benutzte Texte:** Im selben Menü stehen die letzten Texte zum gewählten Kunden (aus den letzten 60 Tagen). Wechselst du den Kunden, wechseln auch die Vorschläge.
- **Ticket-Format „- “ / „-- “:** Auf Wunsch kopiert Zeitzeuge die Dokumentation im Format der Ticket-Doku: erste Zeile (oder erster Satz) als Haupttätigkeit „- …“, alle weiteren als Untertätigkeiten „-- …“. Das gilt für STRG + C in der Ansicht „Dokumentation“ und für „Kopieren“ im Rechtsklick-Menü. Einschalten unter Einstellungen → Textbausteine. Im Eintragen-Dialog gliedert **Text einfügen → Als Ticket-Doku gliedern** den Text sofort.
- **Ticketnummer als Vorschlag:** Zeitzeuge sucht in den Fenstertiteln (PC-Verlauf) und in den Matrix42-Buchungen rund um die Tätigkeit (5 Minuten davor und danach) nach Ticketnummern wie `TCK0000049374`. Die häufigste steht im Feld **Ticket** als Vorschlag, z. B. „Gefunden: TCK0000049374 (Outlook, 12 min)“. Erst mit **Übernehmen** (oder Auswahl in der Liste) landet sie in der Tätigkeit. Das Ticket erscheint dann in der Ansicht „Dokumentation“ und in der kopierten Ticketzeile. Im kleinen Nachfrage-Fenster erscheint das Feld nur, wenn etwas gefunden wurde.
- **Kundenliste: ein Kunde, alle Spuren.** Unter *Einstellungen → Kundenliste …* legst du Kunden an und ordnest ihnen ihre Spuren zu: TeamViewer-ID, RDM-Eintrag, VPN-Verbindung, Telefonnummer und E-Mail-Domain. Telefonnummern passen in jeder Schreibweise („+49 711 123456“ = „0711 123456“). Eine Domain wie „@kunde.de“ gilt auch für „mail.kunde.de“. Zeitzeuge schlägt den Kunden dann beim Eintragen und in der Nachfrage vor. In der Tagesliste steht er vor dem Namen der Verbindung („Müller GmbH · srv01“), in der Timeline im Hinweis. Eine Spur gehört immer genau einem Kunden.
- **Kunde zuordnen per Rechtsklick.** Hat eine Verbindung, ein Telefonat oder eine Mail noch keinen Kunden, wählst du im Rechtsklick-Menü *Kunde zuordnen …*. „TeamViewer-ID benennen …“ gibt es weiter, es landet in derselben Kundenliste.
- **Zeitzeuge lernt aus deinen Korrekturen.** Änderst du beim Eintragen den vorgeschlagenen Kunden, merkt Zeitzeuge ihn zur Spur („Kunde für RDM-Eintrag „srv01“ merken“ ist angehakt). Änderst du die Kategorie, bietet der Dialog „Als Regel merken: „srv01“ → Beratung“ an. Dieser Haken ist aus: Nur wenn du ihn setzt, entsteht eine Regel in der *Zuordnung ohne KI*. Sie steht vor den Standardregeln und schlägt beim nächsten Mal auch im Dialog die Kategorie vor. Doppelte Regeln legt Zeitzeuge nicht an.
- **Abrechnungstakt:** Zeitzeuge zeigt zu jeder Tätigkeit auch die abgerechnete Zeit. Standard ist der 15-Minuten-Takt: Jede angefangene Viertelstunde wird abgerechnet. Beim Kopieren stehen echte und abgerechnete Zeiten mit Beginn und Ende in der Zeile, z. B. `10:05–10:17 (12 min) → abgerechnet 10:05–10:20 (0:15 h)  Müller GmbH · Fernwartung: Drucker eingerichtet`. Der Beginn bleibt, das Ende rückt auf den Takt. Du siehst sie auch in der Ansicht „Dokumentation“, in der Statuszeile („dokumentiert 3:10 h, abgerechnet 3:30 h“) und im Eintragen-Fenster neben der Dauer. Jede Tätigkeit wird für sich gerundet. Unter **Einstellungen → Abrechnung …** stellst du den Takt (Minuten) und die Rundung ein: „Angefangener Takt zählt“, „Auf den nächsten Takt runden“ oder „Ohne Takt“ (dann ist alles wie früher). Für einzelne Kunden kannst du einen anderen Takt oder eine andere Rundung festlegen.
- **Jede Zeile der Timeline ein- und ausblenden:** PC-Aktivität, Dokumentation, Zuordnung ohne KI, KI-Vorschläge, Telefon, Outlook, VPN, TeamViewer und Remote / Weitere schaltest du einzeln unter **Einstellungen → Zeilen der Timeline**. **Alle einblenden** holt alles zurück. Die Tagesliste zeigt weiter alle Einträge.
- **Verschlüsselte Datenbank:** Alle Daten (Anrufe, Fenster, Tätigkeiten, KI-Vorschläge, Personalzeit, Matrix42, VPN, Kundennamen) liegen in einer Datei `zeitzeuge.db`, verschlüsselt mit AES-256. Auf deinem PC öffnet sie deine Windows-Anmeldung ohne Abfrage. Für einen neuen PC gibt es einen Wiederherstellungsschlüssel, den du in RDM ablegst. Siehe [Schutz der Daten](#schutz-der-daten).
- **Ladeanzeige:** Solange Zeitzeuge etwas lädt (Logs, 3CX, ITM, Matrix42 oder KI-Vorschläge), läuft oben über der Timeline ein blauer Balken mit Text, z. B. „Lädt: 3CX-Anrufe · KI-Vorschläge (Claude ordnet 25.10. ein) …“. Kurze Lesevorgänge im Hintergrund erscheinen erst nach 1,5 Sekunden, damit nichts flackert.
- **Zustand der Datenquellen in der Statusleiste:** Rechts unten stehen 3CX und ITM nebeneinander, jeweils mit Symbol:
  - grüner Haken und Uhrzeit: zuletzt erfolgreich gelesen, z. B. „3CX 17:53“
  - gelbes Dreieck mit Ausrufezeichen und Grund: es kommen keine Daten, z. B. „3CX: Anmeldung nötig“, „ITM: offline“ oder „Fehler“
  - graue Uhr: liest gerade
  - Fehlt eine TeamViewer- oder RDM-Logdatei, erscheint „Logs: TeamViewer fehlt“ mit gelbem Dreieck.
  - Ein Klick führt direkt zur Lösung: zur Anmeldung oder zu den Einstellungen. Fährst du mit der Maus darüber, steht dort der genaue Stand.
- **Zeitlinie unter der Maus:** Eine gestrichelte senkrechte Linie folgt der Maus, oben steht die genaue Uhrzeit. Der Hinweis daneben zeigt, welche Einträge gerade liefen.
- **Zeile „Personalzeit“:** Jeder gestempelte Abschnitt ist ein Block mit Beginn und Ende, z. B. „08:10 – 12:39“, Pausen sind Lücken. Bist du noch eingestempelt, steht dort „08:02 – jetzt“. Ohne ITM heißt die Zeile „Arbeitszeit“ und zeigt gestrichelt die Arbeitszeit aus den Einstellungen. Der helle Hintergrund markiert dieselben Zeiten. Blendest du die Zeile aus, steht die Personalzeit wieder im Hinweis unter der Maus.
- **Details:** Fährst du über einen Eintrag, siehst du Kunde, Zeitraum und Dauer. Ein Klick in der Timeline, ein Doppelklick oder **Enter** in der Liste öffnet die Details.
- **Immer aktuell:** Die Logs werden alle 2 Minuten geprüft. Mit F5 liest du sie sofort neu ein. Gelesen werden nur Dateien, die sich geändert haben.
- **Bedienung:**
  - Die rote Linie zeigt die aktuelle Uhrzeit, die Arbeitszeit aus den Einstellungen ist hervorgehoben.
  - Die Timeline zeigt zuerst den ganzen Tag (0–24 Uhr) ohne Scrollen.
  - Mit **Klicken und Ziehen** markierst du einen Zeitraum. Beim Loslassen wird genau dieser Zeitraum angezeigt.
  - Ein Doppelklick auf eine freie Stelle oder **Ganzer Tag** führt zurück zur Tagesansicht. **Arbeitszeit** zeigt die Arbeitszeit des Tages.
  - STRG + Mausrad zoomt an der Mausposition, das Mausrad allein blättert durch den Tag.
  - Design „Metro Klar“: eckige Formen, ruhige Werkzeugleiste ohne Rahmen, Verbindungen als volle Farbbalken, hellblaue Auswahl. Hell und dunkel (**Einstellungen → Dunkles Design**), eigene Aktivitätstypen mit frei wählbaren Farben.

### Tastenkürzel

| Kürzel | Aktion |
|---|---|
| STRG + ← / → | Vorheriger / nächster Tag |
| STRG + T | Heute |
| F5 | Logs neu einlesen |
| F6 | KI-Vorschläge für den Tag erstellen |
| STRG + `+` / `-` | Zoom |
| STRG + 0 | Ganzen Tag zeigen |
| STRG + 9 | Arbeitszeit zeigen |
| STRG + C | Markierte Zeilen der Tagesliste kopieren |
| Enter | Details zur markierten Zeile der Tagesliste |
| ALT + E | Menü Einstellungen öffnen |
| ALT + E, Q | Untermenü Datenquellen |

F7 bis F12 belegt Zeitzeuge bewusst nicht, damit sie für andere Werkzeuge frei bleiben. Nachtragen und Wochenabschluss erreichst du über die Knöpfe in der Werkzeugleiste.

## Voraussetzungen

- Windows 10 oder 11
- Python 3.10 oder neuer, wenn du das Programm aus dem Quellcode startest
- PySide6 (Qt 6)

## Installation

```bash
git clone https://github.com/fkroczak/Zeitzeuge.git
cd zeitzeuge
pip install -r requirements.txt
python main_timeline.py
```

### EXE herunterladen

GitHub baut die EXE bei jeder Änderung automatisch:

- **Neuester Stand:** Öffne im Repository den Reiter **Actions**, dann den obersten Lauf „EXE bauen“. Unter **Artifacts** liegt die `ZeitZeuge.exe` als ZIP.
- **Feste Version:** Bei einem Tag wie `v4.0.0` entsteht ein Eintrag unter **Releases**, mit der EXE als Download.
- **Ordner-Variante** (`ZeitZeuge-Ordner.zip`, ebenfalls unter Artifacts bzw. Releases): ZIP entpacken und `ZeitZeuge.exe` im Ordner starten. Sie entpackt beim Start nichts nach `%TEMP%` und ist für Rechner mit EDR wie Cortex XDR gedacht (z. B. die PAW). Selbst bauen: `set ZEITZEUGE_ONEDIR=1` und dann `pyinstaller ZeitZeuge.spec`.

### EXE selbst bauen

Doppelklick auf `build.bat`. Alternativ in der Kommandozeile:

```bash
pip install -r requirements.txt
pyinstaller --noconfirm --clean ZeitZeuge.spec
```

Die fertige `ZeitZeuge.exe` liegt danach in `dist/`. Die Versionsnummer steht nur in `version.py`; sie erscheint unter **Info** und in den Dateieigenschaften der EXE. Ein Tag `v…` muss dazu passen, sonst bricht der Build ab.

**Signieren:** Unsignierte EXE-Dateien melden Virenscanner und Windows SmartScreen öfter als verdächtig. Hinterlegst du im Repository unter **Settings → Secrets and variables → Actions** ein Code-Signing-Zertifikat als `SIGN_PFX_BASE64` (PFX-Datei Base64-kodiert) und `SIGN_PFX_PASSWORD`, signiert GitHub die EXE automatisch. Ohne Zertifikat bleibt sie unsigniert.

### Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest                     # alles (Qt- und Browser-Tests laufen je in eigenem Prozess)
pytest -m "not skript"     # nur die schnellen Logik-Tests
```

Browser-Tests (3CX, ITM, Mitschnitt) brauchen Edge oder Chrome; ohne Browser werden sie lokal übersprungen. Die Einstellungsdatei `zeitzeuge_config.json` legt Zeitzeuge beim ersten Start unter `Dokumente\Zeitzeuge` an.

## Einrichtung

Die Werkzeugleiste ist so aufgeteilt:

- **Links:** vorheriger Tag, Datum, nächster Tag und Heute.
- **Daneben:** Aktualisieren, Ansicht der Tagesliste (Auge), PC-Verlauf (Bildschirm), KI-Vorschläge (Stern), Lupen, Ganzer Tag und Arbeitszeit.
- **Rechts:** **Einstellungen** (☰).

Fährst du über einen Knopf, erklärt ein Hinweis, was er tut. Im schmalen Fenster zeigen „Ganzer Tag“ und „Arbeitszeit“ nur noch ihr Symbol, danach rutschen Werkzeuge in den Überlauf (»). Tag und Einstellungen bleiben immer sichtbar.

### Datenquellen ein- und ausschalten

Unter **Einstellungen → Datenquellen** schaltest du jede Quelle mit einem Klick ein oder aus:

| Gruppe | Quellen |
|---|---|
| Fernwartung | TeamViewer, RDM |
| VPN | Sophos Connect, FortiClient, weitere VPN-Logs (OpenVPN …) |
| Telefon und Zeiten | 3CX-Anrufe, ITM-Personalzeiten |

Pfade, Zeitzonen und Anmeldungen stellst du unter **Einstellungen → Datenquellen → Einrichten** ein. Das Aufzeichnen der aktiven Fenster schaltest du direkt im Menü **Einstellungen** oder unten rechts in der Statuszeile.

### TeamViewer und RDM

Unter **Einstellungen → Datenquellen → Einrichten → TeamViewer-Logs …** bzw. **RDM-Logs …** stellst du ein:
- wo die Logdateien liegen,
- eine Zeitzonenkorrektur, weil TeamViewer seine Zeiten in UTC speichert.

Standardpfade:

| Quelle | Pfad |
|---|---|
| TeamViewer | `%APPDATA%\TeamViewer\Connections.txt` |
| RDM | `%LOCALAPPDATA%\Devolutions\RemoteDesktopManager\Connections.log` |

### VPN-Verbindungen

Sophos Connect und FortiClient erkennt Zeitzeuge von selbst. Es liest ihre Logs und prüft alle 30 Sekunden, ob ihr VPN-Adapter verbunden ist. Beide schaltest du unter **Einstellungen → Datenquellen** einzeln ein oder aus.

Für andere VPN-Clients legst du unter **Einstellungen → Datenquellen → Einrichten → VPN-Logs …** fest, wo ihre Logs liegen. Du kannst einzelne Dateien oder ganze Ordner eintragen. Bei einem Ordner liest Zeitzeuge alle `.log`- und `.txt`-Dateien darin. Der Dateiname wird zum Namen der Verbindung, bei OpenVPN ist das der Profilname.

| VPN-Client | Standardpfad |
|---|---|
| OpenVPN GUI | `%USERPROFILE%\OpenVPN\log` |
| OpenVPN Connect | `%APPDATA%\OpenVPN Connect\logs` |
| Sophos SSL VPN Client | `%PROGRAMFILES(X86)%\Sophos\Sophos SSL VPN Client\log` |

Erkannt werden Zeilen mit Zeitstempel und „Initialization Sequence Completed“ oder „CONNECTED“ als Beginn und „process exiting“, „restarting“ oder „DISCONNECTED“ als Ende. Ist die Verbindung noch offen, endet der Eintrag beim letzten Logeintrag. Hinweis: OpenVPN GUI überschreibt sein Log bei jeder neuen Verbindung, ältere Tage fehlen dann.

### Telefonate aus 3CX

Zeitzeuge öffnet den 3CX-Webclient unsichtbar mit dem installierten Microsoft Edge und liest jede Minute die Anrufliste. Alle 5 Minuten lädt es die Seite neu, weil 3CX neue Anrufe im Hintergrund sonst nicht nachträgt. Gibt es kein Edge, nimmt es Chrome. Edge läuft dabei mit einem eigenen Profil, getrennt von deinem normalen Browser. Es ist egal, ob du sonst den 3CX-Client, die Webseite oder das Tischtelefon benutzt.

1. **Einstellungen → Datenquellen → Einrichten → 3CX …** öffnen.
2. 3CX-Adresse prüfen und **Bei 3CX anmelden …** klicken.
3. Im Edge-Fenster ganz normal bei 3CX anmelden. Sobald die Anrufliste erscheint, schließt Zeitzeuge das Fenster selbst und liest danach unsichtbar im Hintergrund weiter. Das Fenster muss also nicht offen bleiben.

Die Anmeldung bleibt gespeichert (`%LOCALAPPDATA%\Zeitzeuge\3cx_profil`). Läuft sie ab, meldet sich Zeitzeuge im Infobereich. Ein Klick auf die Meldung öffnet die Anmeldung. Ton, Mikrofon und Benachrichtigungen sind gesperrt, dort klingelt also nichts. Für 3CX zählt Zeitzeuge aber als zusätzlich angemeldeter Webclient.

Zeitzeuge scrollt die Anrufliste so viele Tage zurück, wie unter **Anrufe zurück lesen** im Dialog eingestellt ist (Standard 14, Schlüssel `calls_days_back`). Erhöhst du die Zahl, liest es die fehlenden Tage nach. Bis zu welchem Tag die Anrufe vollständig sind, merkt es sich in der Datenbank. Zeigst du einen älteren Tag an, scrollt Zeitzeuge im Hintergrund bis dorthin weiter. Das geht nur so weit zurück, wie 3CX die Anrufe selbst noch anzeigt.

**Direkt-Abfrage prüfen:** Im 3CX-Dialog holt **Direkt-Abfrage prüfen** die Anrufe ohne Webseite direkt vom 3CX-Server und vergleicht sie mit deiner gespeicherten Anrufliste. Den Bericht `3cx_pruefung_….json` legt Zeitzeuge in den Datenordner, Namen und Nummern nur maskiert. Damit lässt sich festlegen, welche Felder Dauer und Richtung tragen. Danach kann Zeitzeuge 3CX ganz ohne Edge lesen.

Die Einstellungen für Telefonate stehen in `zeitzeuge_config.json`:

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `calls_ignore_missed` | `true` | Verpasste Anrufe ausblenden |
| `calls_min_duration` | `0` | Kürzere Anrufe ausblenden (in Sekunden) |
| `call_colors` | blau / grün / rot | Farben für eingehende, ausgehende und verpasste Anrufe, z. B. `{"Eingehend": "#3D8BFD"}` |
| `calls_3cx_url` | `https://voice.visaas.de:5001` | Adresse des 3CX-Webclients |
| `pbx_reader_enabled` | `false` | Zeitzeuge liest 3CX selbst |
| `calls_days_back` | `14` | So viele Tage liest Zeitzeuge zurück |

### Personalzeiten aus der ITM-Zeiterfassung

Zeitzeuge fragt deine Personalzeiten direkt bei der Schnittstelle der ITM-Zeiterfassung ab, ohne die Webseite offen zu halten. Heute liest es alle 5 Minuten, andere Tage einmal, sobald du sie anzeigst. Klappt die Direkt-Abfrage nicht, liest Zeitzeuge wie früher über die Webseite.

**Anmelden mit Passwort (ohne Edge):**

1. **Einstellungen → Datenquellen → Einrichten → ITM-Personalzeiten …** öffnen.
2. Benutzername und Mandant eintragen, dann **Bei ITM anmelden …** klicken.
3. Passwort eingeben. Zeitzeuge speichert es nicht.

**Anmelden im Edge-Fenster:** Benutzername leer lassen und **Bei ITM anmelden …** klicken. Im Edge-Fenster anmelden. Sobald die Tagesübersicht geladen ist, schließt Zeitzeuge das Fenster selbst.

Auf beiden Wegen erneuert Zeitzeuge die Anmeldung danach selbst, ohne Edge zu starten. Dafür merkt es sich das Erneuerungs-Token der ITM-Anmeldung. Es gilt 7 Tage und verlängert sich bei jeder Abfrage. Solange Zeitzeuge mindestens einmal pro Woche läuft, musst du dich nicht neu anmelden. Nimmt die Tagesübersicht dieses Token nicht an, startet Edge wie früher kurz und unsichtbar.

Lässt der Mandant Anmeldungen nur aus dem Firmennetz zu, klappt die Anmeldung mit Passwort nur dort oder über VPN. **Anmeldung löschen** im selben Dialog entfernt das gespeicherte Token.

Die Anmeldung liegt in `%LOCALAPPDATA%\Zeitzeuge\itm_anmeldung.json` (unter Windows verschlüsselt, nur für deinen Windows-Benutzer lesbar) und, bei Anmeldung über Edge, in `itm_profil` daneben. Die gelesenen Tage liegen in der Datenbank. Die Timeline zeigt dann deine gestempelte Zeit hell und alles andere, auch die Pausen, abgedunkelt. Ohne Personalzeiten gilt wie bisher die Arbeitszeit aus den Einstellungen.

### Outlook und Teams

Einstellungen → Datenquellen → „Outlook (Termine, Mails)“ und
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

### Abfragen mitschneiden (3CX und ITM)

Mit einem Mitschnitt lässt sich prüfen, ob Zeitzeuge die Daten später direkt beim Server abfragen kann, ohne die Seite dauerhaft in Edge offen zu halten. Das spart viel Arbeitsspeicher.

1. **Einstellungen → Datenquellen → Einrichten → 3CX …** oder **ITM-Personalzeiten …** öffnen.
2. **Abfragen mitschneiden …** klicken. Ein Edge-Fenster öffnet sich.
3. Falls nötig anmelden. Bei 3CX die Anrufliste ein Stück nach unten scrollen, bei ITM zwei oder drei andere Tage aufrufen.
4. Das Fenster schließen. Zeitzeuge speichert `mitschnitt_pbx_….json` oder `mitschnitt_itm_….json` im Datenordner.

Aufgezeichnet werden nur Datenabfragen, keine Bilder oder Skripte. Passwörter, Token und Cookie-Werte sind geschwärzt. Von Token und Cookies bleiben Name, Länge und Ablaufzeit, damit man sieht, wie lange eine Anmeldung hält. Antworten sind gekürzt (die ersten drei Einträge einer Liste). Darin können trotzdem Namen und Telefonnummern stehen, schau die Datei also vor dem Weitergeben durch.

### KI-Vorschläge

Du brauchst einen API-Schlüssel von Anthropic (console.anthropic.com).

1. **Einstellungen → KI-Vorschläge …** öffnen.
2. Schlüssel eintragen (beginnt mit `sk-ant-`) und Modell wählen.
3. Tag anzeigen und den Stern (**KI-Vorschläge**) klicken oder F6 drücken.

Der Schlüssel liegt nur auf deinem PC unter `%LOCALAPPDATA%\Zeitzeuge\anthropic_key.txt`, nicht im Datenordner. Alternativ liest Zeitzeuge die Umgebungsvariable `ANTHROPIC_API_KEY`.

**Kosten:** Gesendet wird nur, wenn du es anstößt. Haben sich die Einträge des Tages nicht geändert, fragt Zeitzeuge vorher nach. Ein normaler Arbeitstag kostet mit Opus 5.5 meist 5 bis 15 Cent, mit Haiku 5.5 deutlich unter 1 Cent. Bei 100 $ Guthaben reicht das für viele Monate. Was bisher ausgegeben wurde, steht im Dialog.

Die Vorschläge liegen pro Tag in der Datenbank.

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `ai_model` | `claude-opus-5-5` | Modell: `claude-opus-5-5`, `claude-sonnet-5-5` oder `claude-haiku-5-5` |
| `ai_effort` | `low` | Wie gründlich Claude nachdenkt: `low`, `medium` oder `high` (höher = teurer) |
| `ai_send_window_titles` | `true` | Fenstertitel aus dem Aktivitätsprotokoll mitsenden |
| `ai_auto` | `false` | Vergangene Tage ohne Vorschläge beim Anzeigen automatisch einordnen |
| `ai_categories` | Fernwartung, Telefonsupport, … | Kategorien, aus denen Claude wählt |

### Nachfragen und Erinnerungen

Unter **Einstellungen → Nachfragen und Erinnerungen …** legst du fest, wann Zeitzeuge nachfragt. Deine Tätigkeiten liegen pro Tag in der Datenbank.

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `prompt_mode` | `window` | `window`: kleines Fenster unten rechts, `tray`: nur Meldung im Infobereich, `off`: nicht fragen |
| `prompt_sources` | `["connections", "calls"]` | Wonach gefragt wird: Verbindungen, Telefonate, `rules` (Blöcke aus den Regeln) |
| `prompt_thresholds` | `{"connections": 1, "calls": 1, "rules": 1}` | Erst ab dieser Dauer (Minuten) nachfragen, je Art: Verbindungen, Telefonate, Regel-Blöcke. 0 = immer. Einstellbar unter *Nachfragen und Erinnerungen …* |
| `prompt_snooze_minutes` | `15` | „Später fragen“ fragt nach so vielen Minuten wieder |
| `prompt_end_of_day` | `true` | Nach Feierabend einmal an Offenes erinnern |
| `prompt_on_quit` | `true` | Beim Beenden an Offenes erinnern |
| `m42_url` | ITM-Kalenderseite (support.itm-gruppe.com) | Adresse der Matrix42-Kalenderseite |
| `m42_reader_enabled` | `false` | Gebuchte Zeiten aus Matrix42 lesen |
| `m42_weeks_back` | `4` | So viele Wochen zurück einmal pro Sitzung lesen |
| `m42_gap_minutes` | `5` | Kürzere Lücken ohne Buchung zählen nicht |
| `timeline_rows` | alle an | Sichtbare Zeilen der Timeline: `pc`, `work` (Personalzeit), `doc`, `m42`, `rule` (Zuordnung ohne KI), `ai`, `call`, `vpn`, `tv`, `other` (Remote / Weitere) |

Gefragt wird nur nach Tätigkeiten, die gerade erst geendet haben. Ältere offene Einträge stehen gestrichelt in der Zeile „Doku“, damit nichts verloren geht. Als dokumentiert gilt ein Eintrag, wenn mindestens die Hälfte seiner Zeit in deinen Tätigkeiten steckt.

### Textbausteine und Ticket

Unter **Einstellungen → Textbausteine …** stellst du ein:

- **Bausteine:** ein Satz je Zeile. „Standardliste einsetzen“ holt die mitgelieferten zurück.
- **Zuletzt benutzte Texte zum gewählten Kunden anbieten:** an (Standard) oder aus.
- **Beim Kopieren als Ticket-Doku gliedern:** aus (Standard). An: „- “ / „-- “.
- **Ticketnummern erkennen:** ein Muster (regulärer Ausdruck) je Zeile. Standard `TCK\d+`
  (Matrix42). Weitere Beispiele: `Ticket #(\d+)` (die Klammer ist die Nummer). Leer = keine
  Vorschläge. Ein fehlerhaftes Muster wird mit Zeilennummer gemeldet, OK ist dann gesperrt.

### Zuordnung ohne KI (Regeln)

Ohne KI und ohne Internet ordnet Zeitzeuge den Tag mit festen Regeln ein. Das kostet nichts, und kein Eintrag verlässt den PC.

Eine Regel sagt: Wenn ein Feld dieses Muster enthält, gehört der Eintrag zu dieser Kategorie und diesem Kunden. Ein Beispiel: Programm enthält `outlook`, also Kategorie „E-Mail / Kommunikation“.

- Du bearbeitest die Regeln unter **Einstellungen → Zuordnung ohne KI (Regeln) …**.
- Die Felder sind Programm, Fenstertitel, Kunde, Typ, Details oder alle zusammen.
- Ein Muster ist ein Textteil, groß und klein ist egal. Mit `re:` davor ist es ein regulärer Ausdruck.
- Ist das Feld **Kunde** leer, gilt der Kunde vom Eintrag, bei Telefonaten der Anrufer. `{1}` setzt die erste Klammer aus dem regulären Ausdruck ein. So holst du den Kunden aus einem Fenstertitel wie „Ticket #123 – Müller GmbH“.
- Die Reihenfolge zählt: Die erste passende Regel gewinnt. Mit **Nach oben** und **Nach unten** änderst du sie.
- Verbindungen und Telefonate gehen immer vor PC-Fenstern. Ein Fenster während einer TeamViewer-Sitzung gehört also zur Sitzung.
- Treffer mit gleicher Kategorie und gleichem Kunden werden ein Block, wenn die Pause kürzer als 5 Minuten ist. Blöcke unter 5 Minuten fallen weg, damit die Zeile ruhig bleibt. Blöcke überschneiden sich nie.
- Eine ungültige Regel zeigt der Dialog als Fehler an. Speichern geht erst, wenn sie korrigiert ist.
- **Standardregeln wiederherstellen** holt die mitgelieferten Regeln zurück: Fernwartung (TeamViewer, RDP, SSH, VPN, Remotedesktop-Fenster), Telefonsupport, Zugangsdaten, E-Mail, Microsoft 365 / Azure und Teams. Die Regel fürs Ticketsystem ist ein Muster zum Anpassen und erst einmal aus.

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `rules` | Standardregeln | Liste der Regeln, oberste zuerst. Felder: `name`, `field` (`any`, `app`, `title`, `customer`, `type`, `details`), `match`, `category`, `customer`, `enabled` |
| `rules_gap_minutes` | `5` | Kürzere Pausen werden im Block überbrückt |
| `rules_min_minutes` | `5` | Kürzere Blöcke fallen weg |

Die Kategorien sind dieselben wie bei den KI-Vorschlägen (`ai_categories`).

### Abrechnung und PC-Verlauf

Unter **Einstellungen → Abrechnung …** stellst du Takt und Rundung ein, auch je Kunde. Den PC-Verlauf löschst du unter **Einstellungen → Datenspeicher → PC-Verlauf automatisch löschen …**. In der `zeitzeuge_config.json` stehen dazu:

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `billing_step_minutes` | `15` | Abrechnungstakt in Minuten |
| `billing_mode` | `"up"` | `"up"` angefangener Takt zählt, `"nearest"` nächster Takt, `"off"` ohne Takt |
| `billing_customers` | `{}` | Ausnahmen: `{"Müller GmbH": {"step": 30, "mode": "nearest"}}` |
| `pc_history_purge` | `false` | PC-Verlauf automatisch löschen |
| `pc_history_days` | `90` | so viele Tage behalten (7 bis 3650) |

### Wenn etwas schiefgeht

Zeitzeuge soll nie Daten verlieren und nie dauerhaft hängen. Das passiert bei Problemen:

- **Kein Internet:** Zeitzeuge prüft kurz, ob der 3CX- oder ITM-Server erreichbar ist. Wenn nicht, startet es kein Edge. Die Statuszeile zeigt dann zum Beispiel „3CX: offline, nächster Versuch 10:42“. Nach jedem Fehlversuch wartet Zeitzeuge länger: 20 Sekunden, 40 Sekunden, 80 Sekunden und so weiter, höchstens 10 Minuten. Ist das Netz wieder da, liest es sofort weiter. Klappt es fünfmal hintereinander nicht, meldet sich Zeitzeuge einmal im Infobereich.
- **Edge abgestürzt oder beendet:** Hast du Edge im Task-Manager beendet oder ist er abgestürzt, merkt Zeitzeuge das. Es räumt auf und startet Edge beim nächsten Durchlauf neu. Hängt ein Durchlauf länger als 15 Minuten, beendet Zeitzeuge Edge hart und fängt neu an. Jede Minute prüft ein Wächter, ob die Leser für 3CX und ITM noch laufen, und startet sie bei Bedarf neu.
- **Anmeldefenster:** Meldest du dich 10 Minuten lang nicht an, schließt sich das Fenster von selbst. In der Statuszeile steht dann „Anmeldung abgebrochen (Zeitüberschreitung)“. Über die Meldung im Infobereich öffnest du es wieder. Schaltest du 3CX oder ITM unter **Datenquellen** aus, gehen auch ihr Edge und ihr Anmeldefenster zu.
- **Edge-Reste:** Beim Start und beim Beenden schließt Zeitzeuge alle Edge-Fenster mit seinen eigenen Profilen (`3cx_profil`, `itm_profil`, `m42_profil`). Dein normaler Edge bleibt immer offen.
- **Daten gesperrt:** Öffnet deine Windows-Anmeldung die Datenbank nicht (neuer PC, anderes Konto), fragt Zeitzeuge nach dem Wiederherstellungsschlüssel aus RDM. Brichst du ab, beendet sich Zeitzeuge und ändert nichts. Es legt nie eine neue, leere Datenbank über die alte.
- **Absturz beim Schreiben:** Die Datenbank schreibt jede Änderung als Ganzes oder gar nicht (SQLite mit WAL). Bricht der Strom mitten im Schreiben weg, fehlt höchstens die letzte Änderung.
- **Kaputte Dateien:** Ist eine Datei wie `zeitzeuge_config.json` oder eine alte `anrufe.json` beschädigt, überschreibt Zeitzeuge sie nicht. Es benennt sie um in `<Name>.defekt-<Datum>-<Uhrzeit>` und sagt dir das nach dem Start. Danach macht es mit Standardwerten weiter. Deine alten Daten stecken in der umbenannten Datei. Einzelne kaputte Einträge in einer sonst guten Datei überspringt Zeitzeuge einfach.
- **Gesperrte Dateien:** Hält OneDrive oder ein Virenscanner eine Datei kurz fest, versucht Zeitzeuge es gleich noch einmal. Ist die Datenbank gerade gesperrt, behält Zeitzeuge neue Fensterabschnitte im Speicher und schreibt sie beim nächsten Mal. Eine gesperrte alte Datei übernimmt es später.
- **Sehr große Logs:** Von Logdateien über 100 MB liest Zeitzeuge nur die letzten 20 MB und sagt dir das einmal. Logs in UTF-16 erkennt es von selbst. Kaputte Zeilen werden übersprungen.
- **KI ohne Internet:** Statt einer langen Fehlermeldung steht dort „Keine Internetverbindung“.
- **fehler.log:** Alle Fehler stehen mit Uhrzeit in `fehler.log` im Datenordner. Interne Fehler beenden Zeitzeuge nicht. Die Statuszeile zeigt höchstens einmal pro Minute einen Hinweis.
- **Nur einmal starten:** Zeitzeuge läuft immer nur einmal. Startest du es ein zweites Mal, kommt ein kurzer Hinweis. Mit `--minimized` beendet sich der zweite Start still. Zwei Zeitzeugen würden sich sonst gegenseitig die Dateien überschreiben.
- **Fenster hängt:** Reagiert das Fenster länger als 2 Sekunden nicht, schreibt Zeitzeuge in `haenger.log` im Datenordner, an welcher Stelle im Programm es gerade hing. Diese Datei hilft, die Ursache zu finden. Sie enthält nur Programmzeilen, keine Daten aus deinen Logs.

### Speicherort

| Was | Wo |
|---|---|
| Einstellungen (`zeitzeuge_config.json`), `fehler.log`, `haenger.log` | Datenordner, Standard **Dokumente\Zeitzeuge** |
| Datenbank `zeitzeuge.db` (alle Daten, verschlüsselt) | lokal unter `%LOCALAPPDATA%\Zeitzeuge` |
| Sicherung `zeitzeuge-sicherung.db` (genauso verschlüsselt) | Datenordner, alle 2 Stunden und beim Beenden |
| Anmeldungen (`3cx_profil`, `itm_profil`, `m42_profil`, `itm_anmeldung.json`) | lokal unter `%LOCALAPPDATA%\Zeitzeuge` |

Warum die Datenbank lokal liegt: „Dokumente“ wird oft mit OneDrive synchronisiert. OneDrive lädt eine SQLite-Datei sonst mitten im Schreiben hoch oder ihre Hilfsdateien (`-wal`, `-shm`) getrennt. Das kann die Kopie in der Cloud beschädigen. Die Sicherung im Datenordner ist dagegen eine fertige Datei, die Zeitzeuge in einem Schritt ersetzt. Fehlt die lokale Datenbank (neuer PC, Profil neu), macht Zeitzeuge mit der Sicherung weiter.

- **Einstellungen → Datenspeicher → Speicherort ändern …** wählt einen anderen Datenordner. Einstellungen und Sicherung ziehen mit um, danach startet Zeitzeuge neu.
- **Einstellungen → Datenspeicher → Datenordner öffnen** zeigt den Ordner im Explorer (auch im Menü des Infobereichs).
- **Erster Start nach dem Update:** Zeitzeuge übernimmt die alten Dateien (`anrufe.json`, `aktivitaet/`, `taetigkeiten/`, `ki_vorschlaege/`, `personalzeiten.json`, `m42_buchungen.json`, `vpn_verbindungen.json`, `uebernommen.json`, Kundennamen aus der Config) in die Datenbank. Jede Datei prüft es danach gegen (gleicher Inhalt, gleiche Anzahl je Tag) und verschiebt sie erst dann nach `alt-<Datum>\`. Gelöscht wird nichts. Wenn alles passt, kannst du `alt-<Datum>` selbst löschen. Bricht der Start mittendrin ab, macht Zeitzeuge beim nächsten Start dort weiter, ohne etwas doppelt einzulesen.
- Daten aus sehr alten Versionen, die noch neben der EXE liegen, verschiebt Zeitzeuge beim Start in den Datenordner.

### Schutz der Daten

Zeitzeuge verschlüsselt alle Inhalte mit einem zufälligen Schlüssel (AES-256-GCM). Lesbar sind in der Datei nur technische Angaben: welcher Tag und welche Art von Daten. Kunden, Titel, Texte und Nummern stehen nirgends im Klartext. Personal, Kollegen, OneDrive, Backups, eine kopierte Festplatte oder ein anderes Windows-Konto sehen damit nichts.

Den Schlüssel selbst speichert Zeitzeuge nur verpackt, in zwei „Schlüsselfächern“:

1. **Windows-Anmeldung:** Standard. Zeitzeuge startet ohne Abfrage, nur dein Windows-Konto kann das Fach öffnen (DPAPI).
2. **Windows-Anmeldung und PIN** (wahlweise, siehe unten): Dann fragt Zeitzeuge beim Start nach der PIN.
3. **Wiederherstellungsschlüssel:** 48 Ziffern in 8 Blöcken, wie bei BitLocker. Zeitzeuge zeigt ihn einmal beim Einrichten. Leg ihn in RDM ab (Eintrag „Zeitzeuge Wiederherstellung“). Damit öffnest du die Daten auf einem neuen PC oder mit einem anderen Windows-Konto; danach startet Zeitzeuge dort wieder ohne Abfrage. Jeder Block ist durch 11 teilbar, so meldet Zeitzeuge einen Tippfehler direkt mit dem Block.

**Einstellungen → Datenspeicher → Schutz …** zeigt den Stand und hat diese Knöpfe:

- **PIN beim Start → Einschalten …:** Ab dann reicht die Windows-Anmeldung allein nicht mehr. Zeitzeuge löscht alle Fächer ohne PIN, auch die anderer PCs und Konten. Geht nur, wenn es schon einen Wiederherstellungsschlüssel gibt. **Ändern …** setzt eine neue PIN für dieses Windows-Konto, **Ausschalten** geht zurück zur Windows-Anmeldung allein.
- **Neu erzeugen …:** neuer Wiederherstellungsschlüssel, der alte wird ungültig. Ersetze dann den Eintrag in RDM.
- **Prüfen …:** prüft, ob der Schlüssel aus RDM passt. Dabei ändert sich nichts.
- **Ändern …** beim Übertragungsschlüssel: neu erzeugen oder vom anderen PC eingeben (siehe [Zwei PCs](#zwei-pcs-arbeits-pc-und-paw)).

Fehlt der Wiederherstellungsschlüssel noch, steht rechts unten der blaue Knopf **Wiederherstellungsschlüssel einrichten**.

Schlüssel gehören nie in eine Befehlszeile oder Verknüpfung: Virenscanner wie Cortex XDR speichern Befehlszeilen zentral. Zeitzeuge hat darum keinen Startparameter für einen Schlüssel.

**PIN beim Start:** Domänen-Admins können die Windows-Anmeldung (DPAPI) mit dem Sicherungsschlüssel der Domäne umgehen. Mit PIN hilft ihnen das nicht: Der Datenschlüssel ist zusätzlich mit der PIN verpackt (Argon2id, etwa 0,3 Sekunden und 128 MB je Versuch).

- Beim Start fragt Zeitzeuge nach der PIN. **PIN vergessen …** führt zum Wiederherstellungsschlüssel; danach legst du eine neue PIN fest.
- Nach 3 Fehlversuchen wartet Zeitzeuge: 30 Sekunden, dann doppelt so lange, höchstens 15 Minuten.
- Auf einem neuen PC oder mit einem neuen Windows-Konto öffnest du einmal mit dem Wiederherstellungsschlüssel und legst dort eine PIN fest.
- Leg die PIN **nicht** in RDM ab, sonst kommt ein Admin über RDM daran. Den Wiederherstellungsschlüssel schon: Er öffnet die Daten ohne PIN, also schütze den RDM-Eintrag entsprechend.

Grenzen: Die Wartezeit nach Fehlversuchen bremst nur in Zeitzeuge. Wer eine Kopie der Datei und Admin-Rechte hat, kann eine kurze PIN in Stunden bis Tagen durchprobieren. Nimm darum 10 Zeichen oder mehr, z. B. einen kurzen Satz. Wer Zeitzeuge oder deinen PC beobachtet, während die Daten offen sind (z. B. mit Admin-Rechten auf den laufenden Prozess), kommt trotzdem heran. Windows Hello statt PIN gibt es noch nicht: Dafür bräuchte Zeitzeuge ein weiteres Paket (Windows-Laufzeit), das auf der PAW neu geprüft werden müsste.

### Aktivitätsprotokoll

Ein- und ausschalten geht an drei Stellen, alle zeigen denselben Zustand:

- Knopf **Aufzeichnung aktiv / pausiert** rechts unten in der Statuszeile (ein Klick schaltet um),
- Menü im Infobereich → **Aufzeichnung pausieren / fortsetzen**,
- **Einstellungen → Aktive Fenster aufzeichnen**.

Im Infobereich zeigt das Logo den Zustand: blauer Ring mit rotem „Jetzt“-Punkt, solange aufgezeichnet wird; grauer Ring mit Pause-Zeichen statt Punkt, wenn die Aufzeichnung pausiert ist. Die Statuszeile zeigt denselben roten bzw. grauen Punkt. Der Zustand bleibt nach einem Neustart erhalten. Bereits Aufgezeichnetes bleibt auch bei Pause in der Timeline sichtbar.

Die Fensterabschnitte liegen verschlüsselt in der Datenbank (siehe [Schutz der Daten](#schutz-der-daten)).

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `tracking_enabled` | `true` | Aufzeichnung an oder aus |
| `tracking_idle_minutes` | `5` | Ab so vielen Minuten ohne Eingabe gilt der PC als verlassen |
| `tracking_ignore` | `["KeePass", "Bitwarden", …]` | Fenster mit diesen Wörtern werden nur als „(ausgeblendet)“ gespeichert |
| `tracking_skip` | `[]` | Fenster mit diesen Wörtern werden gar nicht aufgezeichnet |
| `tracking_mode` | `"blacklist"` | `blacklist`: alles außer der Sperrliste. `whitelist`: nur Fenster aus `tracking_allow` |
| `tracking_allow` | `[]` | Erlaubt-Liste für den Whitelist-Modus |
| `tracking_whitelist_other` | `"mask"` | Whitelist: andere Fenster als „(andere)“ zählen (`mask`) oder gar nicht aufzeichnen (`skip`) |

#### Fenster-Filter: Sperrliste und Erlaubt-Liste

Unter **Einstellungen → Fenster-Filter …** legst du fest, was aufgezeichnet wird.

- **Alles, außer der Sperrliste** (Standard): Die Sperrliste hat zwei Stufen.
  - **Titel ausblenden:** Das Programm und die Zeit bleiben, der Titel heißt „(ausgeblendet)“. Gut für Passwortmanager.
  - **Gar nicht aufzeichnen:** Die Zeit bleibt leer, als wärst du nicht am PC. Gut für private Programme oder Spiele.
- **Nur Erlaubtes:** Nur Fenster aus der Erlaubt-Liste werden mit Titel aufgezeichnet. Andere zählen als „(andere)“ ohne Titel, damit die Zeit am PC sichtbar bleibt. Du kannst sie auch ganz weglassen. Die Sperrliste gilt hier weiter.
- Ein Eintrag pro Zeile. Er passt auf den Programmnamen (`chrome.exe` oder `chrome`) oder auf einen Teil des Fenstertitels. Groß und klein ist egal.
- Mit `re:` davor ist der Eintrag ein regulärer Ausdruck, zum Beispiel `re:^Spiel`. Einen ungültigen Ausdruck zeigt der Dialog als Fehler.
- Unten im Dialog stehen die Programme, die in den letzten 7 Tagen am längsten liefen. Ein Klick auf einen Knopf übernimmt das gewählte Programm in eine Liste.
- Neue Filter gelten sofort, auch für das gerade aktive Fenster.

### Im Hintergrund laufen

Aufgezeichnet wird nur, solange Zeitzeuge läuft. Schließt du das Fenster, läuft Zeitzeuge im Infobereich weiter (Symbol neben der Uhr). Richtig beenden geht über Rechtsklick auf das Symbol → **Beenden** oder **Einstellungen → Zeitzeuge beenden**.

Das Menü im Infobereich enthält: **Zeitzeuge öffnen** (auch per Klick auf das Symbol), den Zustand der Aufzeichnung mit **pausieren / fortsetzen**, **Logs neu einlesen**, **Datenquellen**, **Datenordner öffnen** und **Beenden**.

Damit Zeitzeuge mit Windows startet:

1. Drück `Win + R`, gib `shell:startup` ein und drück Enter.
2. Leg in dem Ordner eine Verknüpfung zu `ZeitZeuge.exe` an.
3. Häng in den Eigenschaften der Verknüpfung unter **Ziel** ` --minimized` an. Dann startet Zeitzeuge direkt im Infobereich.

### Zwei PCs: Arbeits-PC und PAW

Auf einer PAW (Privileged Access Workstation) laufen oft nur RDM-Verbindungen, ohne 3CX, ITM, Matrix42 und ohne Laufwerksfreigabe zum Arbeits-PC. So kommt trotzdem alles an einer Stelle zusammen:

1. **Auf der PAW einmal einrichten:** **Einstellungen → Datenspeicher → Dieser PC ist eine PAW (nur RDM sammeln)**. Zeitzeuge sammelt dort nur die RDM-Verbindungen. TeamViewer, VPN, 3CX, ITM, Matrix42, Fensteraufzeichnung und Nachfragen sind aus.
2. **Auf dem Arbeits-PC exportieren:** **Einstellungen → Datenspeicher → Daten exportieren …**, Zeitraum wählen (Standard 31 Tage). **Als Datei speichern** erzeugt eine einzige Datei `Zeitzeuge-Export_<PC>_<Datum>.zeitzeuge`. Darf keine Datei auf die PAW, nimm **In Zwischenablage kopieren**: Der Export wird Text, der auch über eine RDP-Zwischenablage passt, die nur Text erlaubt. Beim ersten Export erzeugst du einen **Übertragungsschlüssel** (oder gibst einen vorhandenen ein) und legst ihn in RDM ab („Zeitzeuge Übertragung“).
3. **Auf der PAW übernehmen:** **Daten übernehmen …** → **Datei wählen** oder **Aus Zwischenablage**. Beim ersten Mal fragt Zeitzeuge nach dem Übertragungsschlüssel aus RDM und merkt ihn sich. Die PAW zeigt dann ihre RDM-Verbindungen zusammen mit Anrufen, Personalzeit, Matrix42-Abgleich, VPN, TeamViewer, Fenstern, Tätigkeiten und den schon erstellten KI-Vorschlägen vom Arbeits-PC.

- Übernommenes steht in der Datenbank der PAW und ist mit „von <PC>“ gekennzeichnet. Ein neuerer Export ersetzt die Tage des älteren; ein älterer überschreibt nichts Neueres.
- KI-Vorschläge vom Arbeits-PC erscheinen in der Zeile „KI“ (die PAW erreicht Claude meist nicht). **Als Tätigkeit eintragen** geht auch auf der PAW; verwerfen nur auf dem Arbeits-PC. Verworfene Vorschläge kommen nicht mit.
- Übernommene Tätigkeiten lassen sich auf der PAW nur ansehen und kopieren; ändern geht auf dem Arbeits-PC. Was dort dokumentiert ist, gilt auch auf der PAW als dokumentiert.
- Der Export enthält Kundennamen, Telefonate und Fenstertitel. Er ist mit dem Übertragungsschlüssel verschlüsselt (AES-256-GCM). Ohne den Schlüssel ist er wertlos; lösche ihn trotzdem nach dem Übernehmen.
- Exporte älterer Versionen (unverschlüsselt) nimmt Zeitzeuge weiter an und weist darauf hin.
- Ein Export geht nur auf einen anderen PC; auf demselben PC lehnt Zeitzeuge ihn ab.

**Virenscanner / EDR (z. B. Cortex XDR):** Im PAW-Modus startet Zeitzeuge nie Edge im Hintergrund, liest keine Cookies, durchsucht und beendet keine Prozesse und lädt die Edge-Steuerung gar nicht erst. Übrig bleibt: RDM-Log lesen, Fenster anzeigen, Dateien im Datenordner schreiben. Nimm auf der PAW am besten die **Ordner-Variante** (`ZeitZeuge-Ordner.zip`): Die einzelne `ZeitZeuge.exe` entpackt sich bei jedem Start nach `%TEMP%` und lädt von dort DLLs, was EDR-Produkte gern als verdächtig werten. Ist ein Zertifikat hinterlegt, sind beide Varianten signiert. Sicher ausschließen lässt sich ein Fehlalarm nur, wenn die IT die EXE (Signatur oder Hash) freigibt.

### RDM im Rechenzentrum

Läuft RDM auf einem Server, kann Zeitzeuge dessen Log auch über das Netzwerk lesen. Trag unter **Einstellungen → Datenquellen → Einrichten → RDM-Logs …** den Netzwerkpfad ein, zum Beispiel `\\server\c$\Users\<name>\AppData\Local\Devolutions\RemoteDesktopManager\Connections.log`. Weicht die Zeitzone des Servers ab, gleichst du das dort mit der Zeitzonenkorrektur aus.

### Weitere Einstellungen

| Schlüssel | Bedeutung |
|---|---|
| `work_days` | Arbeitszeit pro Wochentag, z. B. `"Fr": "08:00-13:00"`, leer = frei. Einstellbar unter **Einstellungen → Arbeitszeiten …** |
| `dark_mode` | Dunkles Design |
| `activity_types`, `type_colors` | Aktivitätstypen und ihre Farben |
| ~~`teamviewer_names`~~ | Kundennamen zu TeamViewer-IDs stehen nicht mehr in der Config, sondern verschlüsselt in der Datenbank. Alte Einträge übernimmt Zeitzeuge beim ersten Start. |

Für Tests und Hilfsskripte gibt es zwei Umgebungsvariablen: `ZEITZEUGE_DATA` setzt den Datenordner (die Datenbank liegt dann ebenfalls dort, ohne Sicherung), `ZEITZEUGE_DB` den Pfad der Datenbank.

## Projektstruktur

| Datei | Inhalt |
|---|---|
| `main_timeline.py` | Start, Config laden/speichern, Hauptfenster (setzt sich aus den `app_*.py` zusammen) |
| `app_menus.py` | Werkzeugleiste, Menü „Einstellungen“, Dialoge dazu |
| `app_daylist.py` | Tagesliste, Statuszeile, Tageswechsel |
| `app_docs.py` | Tätigkeiten dokumentieren, Nachfragen, KI-Vorschläge |
| `app_readers.py` | 3CX- und ITM-Leser im Hauptfenster |
| `app_tray.py` | Infobereich, Fensteraufzeichnung, Beenden |
| `theme.py` | Design: Farben (hell/dunkel), Stylesheet, Qt-Stil, deutsche Dialogknöpfe |
| `config_defaults.py` | Standardwerte der Einstellungen |
| `version.py` | Versionsnummer |
| `timeline_only.py` | Zeichnen der Timeline, Tooltips, Zoom, Logs im Hintergrund lesen |
| `icons.py` | Linien-Icons (Lucide, ISC-Lizenz) und Zustandspunkt der Aufzeichnung |
| `log_parsers.py` | Einlesen der TeamViewer- und RDM-Logs |
| `call_import.py` | Empfang der 3CX-Anrufe, Auslieferung des Browser-Skripts |
| `activity_tracker.py` | Aktivitätsprotokoll (aktives Fenster, Leerlauf) |
| `pbx_reader.py` | Edge im Hintergrund steuern (DevTools-Protokoll), 3CX direkt auslesen |
| `itm_reader.py` | Personalzeiten aus der ITM-Zeiterfassung lesen |
| `itm_auth.py` | ITM-Anmeldung ohne Edge, eigene Buchungen aus dem alten Backend, fehlerhafte Buchungen |
| `request_recorder.py` | Mitschnitt der Abfragen einer Seite, mit Schwärzen von Geheimnissen |
| `ai_classifier.py` | KI-Vorschläge über die Anthropic-API |
| `journal.py` | Eigene Tätigkeiten speichern, offene erkennen |
| `journal_dialogs.py` | Dialoge zum Nachtragen, Nachfrage-Fenster, Einstellungen dazu |
| `m42_reader.py` | Matrix42: Kalender im unsichtbaren Edge lesen (Wochenansicht, Blättern, Anmeldung) |
| `m42_data.py` | Matrix42: Einträge umwandeln, Abgleich gebucht / nicht gebucht (ohne Qt) |
| `busy_bar.py` | Ladeanzeige oben im Fenster |
| `transfer.py` | Export/Import zwischen zwei PCs (Arbeits-PC → PAW), übernommene Daten (ohne Qt) |
| `app_transfer.py` | Hauptfenster: Export- und Import-Dialog, PAW-Modus |
| `rules.py` | Klassifizierung ohne KI: Regeln, Blöcke bilden, Vorrang (ohne Qt) |
| `storage.py` | Speicherort: Datenordner, Datenbank, Sicherung, Umziehen |
| `datastore.py` | Verschlüsselte SQLite-Datenbank: Ablagen je Tag, Zeilen, Schlüsselfächer, Migration der alten Dateien, Sicherung (ohne Qt) |
| `datakey.py` | Schlüssel: AES-256-GCM, Ziffernschlüssel (Wiederherstellung, Übertragung), Windows-Anmeldung (DPAPI), PIN (Argon2id) (ohne Qt) |
| `app_protect.py` | Hauptfenster: Dialog „Schutz …“, Wiederherstellungs- und Übertragungsschlüssel, Sicherung alle 2 Stunden |
| `protect_dialogs.py` | Dialoge: Schlüssel einmal zeigen, Schlüssel oder PIN eingeben, PIN festlegen, „Daten sind gesperrt“ |
| `safe_io.py` | Dateien sicher lesen und schreiben, kaputte Dateien beiseitelegen, große Logs nur am Ende lesen, `fehler.log` |
| `net.py` | Prüfen, ob ein Server erreichbar ist, und Wartezeit nach Fehlern |
| `tests/` | Tests (pytest), laufen bei jedem Build: Start, Bedienbarkeit, Infobereich, Log-Parser, VPN-Logs, 3CX und ITM mit nachgebauten Seiten, KI-Vorschläge mit nachgebauter API, Fensterabfrage, Anrufliste. Dazu `start_bench.py` (Startzeit messen) und `screenshots.sh` (Bildschirmfotos mit Demodaten) |
| `settings_dialogs.py` | Dialoge für Logpfade, Aktivitätstypen, Arbeitszeiten, KI, Fenster-Filter und Regeln |
| `zeitzeuge_anrufe.user.js` | Liest die Anrufliste aus der 3CX-Webseite (für das Lesen über Edge) |
| `pbx_direct.py` | 3CX direkt abfragen (Anmeldung, Protobuf) |
| `ZeitZeuge.spec` | Build-Datei für PyInstaller |
| `build.bat` | EXE auf dem eigenen PC bauen |
| `.github/workflows/build.yml` | Automatischer EXE-Build auf GitHub |

## Datenschutz

Zeitzeuge arbeitet nur auf deinem eigenen Rechner. Es liest lokale Logdateien und nimmt Anrufe nur über `127.0.0.1` entgegen. Es werden keine Daten an fremde Server gesendet. Die einzige Ausnahme sind die KI-Vorschläge, und nur wenn du sie einrichtest und anstößt.

**KI-Vorschläge:** Dabei gehen die Einträge des Tages an Anthropic: Uhrzeiten, Kunden- und Verbindungsnamen, Anrufer und, wenn eingeschaltet, die Fenstertitel. Passwörter selbst stehen nicht in den Logs und werden nicht gesendet. Fenster aus `tracking_ignore` gehen nur als „(ausgeblendet)“ mit. Prüfe vorher, ob das zu deinen Verträgen mit Kunden passt. Wenn nicht: Fenstertitel ausschalten oder die Funktion nicht nutzen.

**Was wo liegt:** Fenstertitel, Kundennamen, Telefonate, Tätigkeiten und alle anderen Daten stehen verschlüsselt in `zeitzeuge.db` (siehe [Schutz der Daten](#schutz-der-daten)). In den Ordnern `3cx_profil`, `itm_profil` und `m42_profil` und in `itm_anmeldung.json` liegen deine Anmeldungen bei 3CX, ITM und Matrix42. Sie sind zu schützen wie ein Browserprofil. `itm_anmeldung.json` ist unter Windows mit deiner Windows-Anmeldung verschlüsselt.

**Logs:** `fehler.log` und `haenger.log` enthalten nur Uhrzeiten, Dateinamen, Programmzeilen und Fehlerarten. Bei internen Fehlern schreibt Zeitzeuge die Art und die Stelle im Programm, aber nicht den Text der Ausnahme, weil darin Daten stehen könnten. Ausnahme: Mitschnitte (`mitschnitt_*.json`) und der 3CX-Prüfbericht, die du nur selbst anstößt. Darin sind Geheimnisse geschwärzt (im Prüfbericht auch Namen und Nummern), ein Mitschnitt kann aber Daten der Seite enthalten. Lösche ihn nach der Auswertung.

**Alte Dateien:** Nach dem Update liegen die alten, unverschlüsselten Dateien in `alt-<Datum>\` im Datenordner. Lösche den Ordner, sobald du in Zeitzeuge alles siehst.

Datenbank, Sicherung, Exporte und alle alten Dateien stehen in `.gitignore`, genauso wie die persönliche `zeitzeuge_config.json`.

## Lizenz

MIT, siehe [LICENSE](LICENSE).
