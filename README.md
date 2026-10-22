# Zeitzeuge

**Zeitzeuge zeigt dir auf einer Tages-Timeline, woran du gearbeitet hast.** Das Programm liest die Spuren, die deine Werkzeuge ohnehin hinterlassen: TeamViewer-Verbindungen, Sitzungen aus dem Remote Desktop Manager, VPN-Verbindungen aus Sophos Connect und FortiClient und Telefonate aus 3CX. Dazu merkt es sich, welches Fenster gerade aktiv war. So kannst du Tickets lückenlos schreiben und musst nicht mehr raten, wann du bei welchem Kunden warst.

Gedacht ist Zeitzeuge für IT-Dienstleister und Admins, die ihre Zeiten nachträglich erfassen oder abrechnen.

![Zeitzeuge Timeline](zeitzeuge.png)

## Funktionen

- **Tages-Timeline** von 00:00 bis 24:00 mit markierter Arbeitszeit. Telefonate, VPN und TeamViewer haben je eine feste Zeile („Tel“, „VPN“, „TV“). So siehst du sofort, wann du telefoniert hast oder verbunden warst. Darunter folgen RDM und eigene Einträge; überlappen sie sich, rücken sie in die nächste Zeile.
- **TeamViewer:** liest `Connections.txt` mit Sitzungs-ID, Beginn und Ende. Verbindungen unter 1 Minute werden ausgeblendet.
  - Statt der ID kannst du einen Namen vergeben: Rechtsklick auf die Zeile in der Tagesliste, dann **TeamViewer-ID benennen …**.
- **Remote Desktop Manager (Devolutions):** liest `Connections.log`.
  - RDP-, SSH-, VPN-, FTP- und Website-Verbindungen mit Beginn und Ende.
  - Angezeigte Passwörter, Benutzernamen und Einmal-Passwörter (OTP).
- **VPN aus Sophos Connect:** liest `scvpn.log` und `scgui.log` aus `C:\Program Files (x86)\Sophos\Connect`. Jede Verbindung erscheint mit Beginn, Ende und dem Namen, den du ihr in Sophos Connect gegeben hast (z. B. „Kunde Müller“).
  - Ist der PC eingeschlafen, endet die Verbindung beim Einschlafen.
  - Sophos überschreibt seine Logs bei Neustarts und neuen Verbindungen. Zeitzeuge liest sie deshalb alle 2 Minuten und hebt alles in `vpn_verbindungen.json` auf, egal welcher Tag gerade angezeigt wird.
- **Eigene VPN-Aufzeichnung:** Zeitzeuge prüft alle 30 Sekunden selbst, ob ein VPN-Adapter von Sophos oder Fortinet verbunden ist, und speichert das sofort in `vpn_verbindungen.json`. Das läuft auch, wenn das Fenster im Infobereich liegt.
  - So bleiben die Zeiten erhalten, auch wenn die Logs fehlen oder gelöscht sind. Beginn und Ende sind auf etwa 30 Sekunden genau.
  - Steht dieselbe Verbindung auch in den Logs, zeigt Zeitzeuge nur den Eintrag aus den Logs, weil er den Namen kennt.
  - Ruhezustand, Absturz oder ein Neustart von Zeitzeuge beenden den laufenden Eintrag beim letzten Blick auf den Adapter.
  - Weitere Adapter (z. B. WireGuard) trägst du in der `zeitzeuge_config.json` unter `vpn_adapters` ein: Teil der Adapterbeschreibung und Name der Quelle. Mit `vpn_monitor_enabled: false` schaltest du die Aufzeichnung ab.
- **VPN aus FortiClient:** steht ebenfalls in Sophos' `charon.log`, weil dort jede Änderung an Netzwerkadaptern landet. Zeitzeuge zeigt die Zeiten als „FortiClient“, aber ohne Namen der Verbindung. Ohne installiertes Sophos Connect gibt es diese Quelle nicht.
  - Andere Ordner trägst du in der `zeitzeuge_config.json` unter `sophos_connect_dirs` ein.
- **Telefonate aus 3CX:** Zeitzeuge liest die Anrufliste selbst aus dem 3CX-Webclient, ohne dass du die Webseite offen haben musst.
  - Alle gelesenen Anrufe landen in `anrufe.json`. So entsteht eine eigene Anrufliste, die auch offline bleibt.
  - Zeitzeuge scrollt die Liste so viele Tage zurück, wie du einstellst (Standard 14). Blätterst du in Zeitzeuge auf einen älteren Tag, liest es automatisch bis dorthin nach.
- **Personalzeiten aus der ITM-Zeiterfassung:** Zeitzeuge liest deine gestempelten Zeiten und hebt sie in der Timeline als Arbeitszeit hervor. Pausen sind abgedunkelt. Die Statuszeile zeigt die gewertete Zeit und die Sollzeit.
- **Aktivitätsprotokoll:** Alle 5 Sekunden merkt sich Zeitzeuge das aktive Fenster, zum Beispiel eine RDP-Sitzung, einen Browser-Tab, Outlook oder PuTTY.
  - Es erscheint als farbiges Band „PC“ oben in der Timeline, eine Farbe pro Programm.
  - Mit **PC-Verlauf** in der Werkzeugleiste stehen die Fenster auch in der Tagesliste.
  - Nach 5 Minuten ohne Maus und Tastatur oder bei gesperrtem PC wird nichts aufgezeichnet.
  - Fenster mit bestimmten Wörtern im Titel werden nur als „(ausgeblendet)“ gespeichert, zum Beispiel Passwortmanager.
  - Mit dem **Fenster-Filter** lässt du private Programme ganz weg oder zeichnest nur erlaubte Programme auf.
- **Klassifizierung ohne KI:** Feste Regeln ordnen Verbindungen, Telefonate und Fenster einer Kategorie und einem Kunden zu, zum Beispiel Outlook als „E-Mail / Kommunikation“.
- **Tagesliste** unter der Timeline mit Von, Bis, Dauer, Typ, Kunde und Details.
  - Die Statuszeile zeigt die belegte Zeit des Tages. Überschneidungen werden nicht doppelt gezählt.
  - Markierte Zeilen kopierst du mit STRG + C, zum Beispiel für die Ticket-Dokumentation.
  - Die Auswahl rechts in der Werkzeugleiste legt fest, wie die Liste aussieht:
    - **Zusammengefasst** (Standard): Verbindungen zum selben Eintrag mit weniger als 5 Minuten Pause werden eine Zeile. Passwort-, Benutzernamen- und OTP-Anzeigen aus RDM stehen als Zähler bei der Verbindung, zum Beispiel „3 Verbindungen · 2× OTP, 1× Passwort“. Ohne passende Verbindung erscheinen sie als „Zugangsdaten“.
    - **Einzeln:** jede Zeile aus den Logs, wie bisher.
    - **Arbeitsblöcke:** alles mit weniger als 10 Minuten Pause wird ein Block, zum Beispiel „01:18–02:05 · SSL VPN, EPM, OPNsense“. Praktisch fürs Ticket.
  - Die Details eines zusammengefassten Eintrags zeigen alle einzelnen Einträge.
  - Die Pausen stellst du in der `zeitzeuge_config.json` unter `merge_gap_minutes` und `block_gap_minutes` ein.
- **KI-Vorschläge (Claude von Anthropic):** Auf Knopfdruck (F6) ordnet Claude die Spuren des Tages zu Tätigkeiten.
  - Jeder Vorschlag hat Kunde, Kategorie (zum Beispiel Fernwartung oder Telefonsupport) und einen Satz fürs Ticket.
  - Die Vorschläge stehen in der Timeline in einer eigenen Zeile „KI“, lila und gepunktet.
  - Rechtsklick auf einen Vorschlag: **übernehmen** (dann durchgezogen), **verwerfen** oder **Text kopieren**.
  - In der Tagesliste zeigt die Ansicht **KI-Vorschläge** alle Vorschläge. STRG + C kopiert sie als fertige Ticketzeilen.
- **Zeitlinie unter der Maus:** Eine gestrichelte senkrechte Linie folgt der Maus, oben steht die genaue Uhrzeit. Der Hinweis daneben zeigt, ob du zu dieser Minute eingestempelt warst (Personalzeit oder Pause) und welche Einträge gerade liefen. Der grüne Streifen unter der Stundenleiste und der helle Hintergrund markieren die Personalzeit (ohne ITM die Arbeitszeit aus den Einstellungen).
- **Details:** Fährst du über einen Eintrag, siehst du Kunde, Zeitraum und Dauer. Ein Klick in der Timeline, ein Doppelklick oder **Enter** in der Liste öffnet die Details.
- **Immer aktuell:** Die Logs werden alle 2 Minuten geprüft. Mit F5 liest du sie sofort neu ein. Gelesen werden nur Dateien, die sich geändert haben.
- **Bedienung:**
  - Die rote Linie zeigt die aktuelle Uhrzeit, die Arbeitszeit aus den Einstellungen ist hervorgehoben.
  - Die Timeline zeigt zuerst den ganzen Tag (0–24 Uhr) ohne Scrollen.
  - Mit **Klicken und Ziehen** markierst du einen Zeitraum. Beim Loslassen wird genau dieser Zeitraum angezeigt.
  - Ein Doppelklick auf eine freie Stelle oder **Ganzer Tag** führt zurück zur Tagesansicht. **Arbeitszeit** zeigt die Arbeitszeit des Tages.
  - STRG + Mausrad zoomt an der Mausposition, das Mausrad allein blättert durch den Tag.
  - Dunkles und helles Design (**Einstellungen → Dunkles Design**), eigene Aktivitätstypen mit frei wählbaren Farben.

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

## Voraussetzungen

- Windows 10 oder 11
- Python 3.10 oder neuer, wenn du das Programm aus dem Quellcode startest
- PyQt5

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
- **Feste Version:** Bei einem Tag wie `v3.3` entsteht ein Eintrag unter **Releases**, mit der EXE als Download.

### EXE selbst bauen

Doppelklick auf `build.bat`. Alternativ in der Kommandozeile:

```bash
pip install -r requirements.txt
pyinstaller --noconfirm --clean ZeitZeuge.spec
```

Die fertige `ZeitZeuge.exe` liegt danach in `dist/`. Die Einstellungsdatei `zeitzeuge_config.json` legt Zeitzeuge beim ersten Start unter `Dokumente\Zeitzeuge` an.

## Einrichtung

Der Knopf **Einstellungen** steht ganz links in der Werkzeugleiste. So bleibt er auch im schmalen Fenster sichtbar.

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

Zeitzeuge scrollt die Anrufliste so viele Tage zurück, wie unter **Anrufe zurück lesen** im Dialog eingestellt ist (Standard 14, Schlüssel `calls_days_back`). Erhöhst du die Zahl, liest es die fehlenden Tage nach. Bis zu welchem Tag die Anrufe vollständig sind, merkt es sich in `anrufe_stand.json`. Zeigst du einen älteren Tag an, scrollt Zeitzeuge im Hintergrund bis dorthin weiter. Das geht nur so weit zurück, wie 3CX die Anrufe selbst noch anzeigt.

**Direkt-Abfrage prüfen:** Im 3CX-Dialog holt **Direkt-Abfrage prüfen** die Anrufe ohne Webseite direkt vom 3CX-Server und vergleicht sie mit deiner `anrufe.json`. Den Bericht `3cx_pruefung_….json` legt Zeitzeuge in den Datenordner, Namen und Nummern nur maskiert. Damit lässt sich festlegen, welche Felder Dauer und Richtung tragen. Danach kann Zeitzeuge 3CX ganz ohne Edge lesen.

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

Zeitzeuge fragt deine Personalzeiten direkt bei der Schnittstelle der ITM-Zeiterfassung ab, ohne die Webseite offen zu halten. Heute liest es alle 5 Minuten, andere Tage einmal, sobald du sie anzeigst. Edge startet nur kurz und unsichtbar, wenn die Anmeldung erneuert werden muss (etwa einmal pro Stunde), und schließt sich danach wieder. Klappt die Direkt-Abfrage nicht, liest Zeitzeuge wie früher über die Webseite.

1. **Einstellungen → Datenquellen → Einrichten → ITM-Personalzeiten …** öffnen.
2. Adresse prüfen (`https://app.itm-gruppe.com`) und **Bei ITM anmelden …** klicken.
3. Im Edge-Fenster anmelden. Sobald die Tagesübersicht geladen ist, schließt Zeitzeuge das Fenster selbst.

Die Anmeldung liegt in `%LOCALAPPDATA%\Zeitzeuge\itm_profil`, die gelesenen Tage in `personalzeiten.json` im Datenordner. Die Timeline zeigt dann deine gestempelte Zeit hell und alles andere, auch die Pausen, abgedunkelt. Ohne Personalzeiten gilt wie bisher die Arbeitszeit aus den Einstellungen.

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
3. Tag anzeigen und **KI-Vorschläge** klicken oder F6 drücken.

Der Schlüssel liegt nur auf deinem PC unter `%LOCALAPPDATA%\Zeitzeuge\anthropic_key.txt`, nicht im Datenordner. Alternativ liest Zeitzeuge die Umgebungsvariable `ANTHROPIC_API_KEY`.

**Kosten:** Gesendet wird nur, wenn du es anstößt. Haben sich die Einträge des Tages nicht geändert, fragt Zeitzeuge vorher nach. Ein normaler Arbeitstag kostet mit Opus 5.5 meist 5 bis 15 Cent, mit Haiku 5.5 deutlich unter 1 Cent. Bei 100 $ Guthaben reicht das für viele Monate. Was bisher ausgegeben wurde, steht im Dialog.

Die Vorschläge liegen pro Tag in `ki_vorschlaege/JJJJ-MM-TT.json` im Datenordner.

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `ai_model` | `claude-opus-5-5` | Modell: `claude-opus-5-5`, `claude-sonnet-5-5` oder `claude-haiku-5-5` |
| `ai_effort` | `low` | Wie gründlich Claude nachdenkt: `low`, `medium` oder `high` (höher = teurer) |
| `ai_send_window_titles` | `true` | Fenstertitel aus dem Aktivitätsprotokoll mitsenden |
| `ai_auto` | `false` | Vergangene Tage ohne Vorschläge beim Anzeigen automatisch einordnen |
| `ai_categories` | Fernwartung, Telefonsupport, … | Kategorien, aus denen Claude wählt |

### Klassifizierung ohne KI (Regeln)

Ohne KI und ohne Internet ordnet Zeitzeuge den Tag mit festen Regeln ein. Das kostet nichts, und kein Eintrag verlässt den PC.

Eine Regel sagt: Wenn ein Feld dieses Muster enthält, gehört der Eintrag zu dieser Kategorie und diesem Kunden. Ein Beispiel: Programm enthält `outlook`, also Kategorie „E-Mail / Kommunikation“.

- Du bearbeitest die Regeln unter **Einstellungen → Regeln (ohne KI) …**.
- Die Felder sind Programm, Fenstertitel, Kunde, Typ, Details oder alle zusammen.
- Ein Muster ist ein Textteil, groß und klein ist egal. Mit `re:` davor ist es ein regulärer Ausdruck.
- Ist das Feld **Kunde** leer, gilt der Kunde vom Eintrag, bei Telefonaten der Anrufer. `{1}` setzt die erste Klammer aus dem regulären Ausdruck ein. So holst du den Kunden aus einem Fenstertitel wie „Ticket #123 – Müller GmbH“.
- Die Reihenfolge zählt: Die erste passende Regel gewinnt. Mit **Nach oben** und **Nach unten** änderst du sie.
- Verbindungen und Telefonate gehen immer vor PC-Fenstern. Ein Fenster während einer TeamViewer-Sitzung gehört also zur Sitzung.
- Treffer mit gleicher Kategorie und gleichem Kunden werden ein Block, wenn die Pause kürzer als 5 Minuten ist. Blöcke unter 2 Minuten fallen weg. Blöcke überschneiden sich nie.
- Eine ungültige Regel zeigt der Dialog als Fehler an. Speichern geht erst, wenn sie korrigiert ist.
- **Standardregeln wiederherstellen** holt die mitgelieferten Regeln zurück: Fernwartung (TeamViewer, RDP, SSH, VPN, Remotedesktop-Fenster), Telefonsupport, Zugangsdaten, E-Mail, Microsoft 365 / Azure und Teams. Die Regel fürs Ticketsystem ist ein Muster zum Anpassen und erst einmal aus.

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `rules` | Standardregeln | Liste der Regeln, oberste zuerst. Felder: `name`, `field` (`any`, `app`, `title`, `customer`, `type`, `details`), `match`, `category`, `customer`, `enabled` |
| `rules_gap_minutes` | `5` | Kürzere Pausen werden im Block überbrückt |
| `rules_min_minutes` | `2` | Kürzere Blöcke fallen weg |

Die Kategorien sind dieselben wie bei den KI-Vorschlägen (`ai_categories`).

### Wenn Zeitzeuge hängt

Reagiert das Fenster länger als 2 Sekunden nicht, schreibt Zeitzeuge in `haenger.log` im Datenordner, an welcher Stelle im Programm es gerade hing. Diese Datei hilft, die Ursache zu finden. Sie enthält nur Programmzeilen, keine Daten aus deinen Logs.

### Speicherort

Zeitzeuge speichert Config, Anrufe und Aktivitätsprotokoll unter **Dokumente\Zeitzeuge**.

- **Einstellungen → Datenspeicher → Speicherort ändern …** wählt einen anderen Ordner. Die Daten ziehen mit um, danach startet Zeitzeuge neu.
- **Einstellungen → Datenspeicher → Datenordner öffnen** zeigt den Ordner im Explorer (auch im Menü des Infobereichs).
- Daten aus älteren Versionen, die noch neben der EXE liegen, verschiebt Zeitzeuge beim ersten Start automatisch.
- Die 3CX-Anmeldung liegt immer lokal unter `%LOCALAPPDATA%\Zeitzeuge`. Der Ordner „Dokumente“ wird oft mit OneDrive synchronisiert, und eine Browser-Anmeldung gehört nicht in die Cloud.

### Aktivitätsprotokoll

Ein- und ausschalten geht an drei Stellen, alle zeigen denselben Zustand:

- Knopf **Aufzeichnung aktiv / pausiert** rechts unten in der Statuszeile (ein Klick schaltet um),
- Menü im Infobereich → **Aufzeichnung pausieren / fortsetzen**,
- **Einstellungen → Aktive Fenster aufzeichnen**.

Im Infobereich zeigt das Logo den Zustand: blauer Ring mit rotem „Jetzt“-Punkt, solange aufgezeichnet wird; grauer Ring mit Pause-Zeichen statt Punkt, wenn die Aufzeichnung pausiert ist. Die Statuszeile zeigt denselben roten bzw. grauen Punkt. Der Zustand bleibt nach einem Neustart erhalten. Bereits Aufgezeichnetes bleibt auch bei Pause in der Timeline sichtbar.

 Die Daten liegen pro Tag in `aktivitaet/JJJJ-MM-TT.jsonl` im Datenordner.

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

### RDM im Rechenzentrum

Läuft RDM auf einem Server, kann Zeitzeuge dessen Log auch über das Netzwerk lesen. Trag unter **Einstellungen → Datenquellen → Einrichten → RDM-Logs …** den Netzwerkpfad ein, zum Beispiel `\\server\c$\Users\<name>\AppData\Local\Devolutions\RemoteDesktopManager\Connections.log`. Weicht die Zeitzone des Servers ab, gleichst du das dort mit der Zeitzonenkorrektur aus.

### Weitere Einstellungen

| Schlüssel | Bedeutung |
|---|---|
| `work_days` | Arbeitszeit pro Wochentag, z. B. `"Fr": "08:00-13:00"`, leer = frei. Einstellbar unter **Einstellungen → Arbeitszeiten …** |
| `dark_mode` | Dunkles Design |
| `activity_types`, `type_colors` | Aktivitätstypen und ihre Farben |

## Projektstruktur

| Datei | Inhalt |
|---|---|
| `main_timeline.py` | Hauptfenster, Werkzeugleiste, Einstellungen, Design |
| `timeline_only.py` | Zeichnen der Timeline, Tooltips, Zoom, Logs im Hintergrund lesen |
| `icons.py` | Linien-Icons (Lucide, ISC-Lizenz) und Zustandspunkt der Aufzeichnung |
| `log_parsers.py` | Einlesen der TeamViewer- und RDM-Logs |
| `call_import.py` | Empfang der 3CX-Anrufe, Auslieferung des Browser-Skripts |
| `activity_tracker.py` | Aktivitätsprotokoll (aktives Fenster, Leerlauf) |
| `pbx_reader.py` | Edge im Hintergrund steuern (DevTools-Protokoll), 3CX direkt auslesen |
| `itm_reader.py` | Personalzeiten aus der ITM-Zeiterfassung lesen |
| `request_recorder.py` | Mitschnitt der Abfragen einer Seite, mit Schwärzen von Geheimnissen |
| `ai_classifier.py` | KI-Vorschläge über die Anthropic-API |
| `rules.py` | Klassifizierung ohne KI: Regeln, Blöcke bilden, Vorrang (ohne Qt) |
| `storage.py` | Speicherort der Daten |
| `tests/` | Tests, laufen bei jedem Build: Start, Bedienbarkeit, Infobereich, Log-Parser, VPN-Logs, 3CX und ITM mit nachgebauten Seiten, KI-Vorschläge mit nachgebauter API, Fensterabfrage, Anrufliste. Dazu `start_bench.py` (Startzeit messen) und `screenshots.sh` (Bildschirmfotos mit Demodaten) |
| `settings_dialogs.py` | Dialoge für Logpfade, Aktivitätstypen, Arbeitszeiten, KI, Fenster-Filter und Regeln |
| `zeitzeuge_anrufe.user.js` | Liest die Anrufliste aus der 3CX-Webseite (für das Lesen über Edge) |
| `pbx_direct.py` | 3CX direkt abfragen (Anmeldung, Protobuf) |
| `ZeitZeuge.spec` | Build-Datei für PyInstaller |
| `build.bat` | EXE auf dem eigenen PC bauen |
| `.github/workflows/build.yml` | Automatischer EXE-Build auf GitHub |

## Datenschutz

Zeitzeuge arbeitet nur auf deinem eigenen Rechner. Es liest lokale Logdateien und nimmt Anrufe nur über `127.0.0.1` entgegen. Es werden keine Daten an fremde Server gesendet. Die einzige Ausnahme sind die KI-Vorschläge, und nur wenn du sie einrichtest und anstößt.

**KI-Vorschläge:** Dabei gehen die Einträge des Tages an Anthropic: Uhrzeiten, Kunden- und Verbindungsnamen, Anrufer und, wenn eingeschaltet, die Fenstertitel. Passwörter selbst stehen nicht in den Logs und werden nicht gesendet. Fenster aus `tracking_ignore` gehen nur als „(ausgeblendet)“ mit. Prüfe vorher, ob das zu deinen Verträgen mit Kunden passt. Wenn nicht: Fenstertitel ausschalten oder die Funktion nicht nutzen.

Das Aktivitätsprotokoll speichert Fenstertitel. Darin können Kundennamen, Betreffzeilen von Mails oder Dateinamen stehen. Die Dateien in `aktivitaet/` gehören deshalb nur auf deinen PC. In den Ordnern `3cx_profil` und `itm_profil` liegen deine Anmeldungen bei 3CX und ITM. Sie sind zu schützen wie ein Browserprofil. Alle diese Dateien stehen in `.gitignore`, genauso wie `anrufe.json`, `personalzeiten.json`, `ki_vorschlaege/`, `mitschnitt_*.json` und die persönliche `zeitzeuge_config.json`.


## Lizenz

MIT, siehe [LICENSE](LICENSE).
