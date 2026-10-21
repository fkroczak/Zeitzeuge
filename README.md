# Zeitzeuge

**Zeitzeuge zeigt dir auf einer Tages-Timeline, woran du gearbeitet hast.** Das Programm liest die Spuren, die deine Werkzeuge ohnehin hinterlassen: TeamViewer-Verbindungen, Sitzungen aus dem Remote Desktop Manager und Telefonate aus 3CX. Dazu merkt es sich, welches Fenster gerade aktiv war. So kannst du Tickets lückenlos schreiben und musst nicht mehr raten, wann du bei welchem Kunden warst.

Gedacht ist Zeitzeuge für IT-Dienstleister und Admins, die ihre Zeiten nachträglich erfassen oder abrechnen.

![Zeitzeuge Timeline](zeitzeuge.png)

## Funktionen

- **Tages-Timeline** von 00:00 bis 24:00 mit markierter Arbeitszeit. Überlappende Einträge werden in eigenen Zeilen gezeigt.
- **TeamViewer:** liest `Connections.txt` mit Sitzungs-ID, Beginn und Ende. Verbindungen unter 1 Minute werden ausgeblendet.
- **Remote Desktop Manager (Devolutions):** liest `Connections.log`.
  - RDP-, SSH-, VPN-, FTP- und Website-Verbindungen mit Beginn und Ende.
  - Angezeigte Passwörter, Benutzernamen und Einmal-Passwörter (OTP).
- **Telefonate aus 3CX:** Ein Browser-Skript überträgt die Anrufliste aus dem 3CX-Webclient, ohne dass eine API nötig ist. Ein Assistent richtet es mit wenigen Klicks ein (siehe unten).
- **Aktivitätsprotokoll:** Alle 5 Sekunden merkt sich Zeitzeuge das aktive Fenster, zum Beispiel eine RDP-Sitzung, einen Browser-Tab, Outlook oder PuTTY.
  - Es erscheint als farbiges Band „PC“ oben in der Timeline, eine Farbe pro Programm.
  - Mit **PC-Verlauf in Liste** stehen die Fenster auch in der Tagesliste.
  - Nach 5 Minuten ohne Maus und Tastatur oder bei gesperrtem PC wird nichts aufgezeichnet.
  - Fenster mit bestimmten Wörtern im Titel werden nur als „(ausgeblendet)“ gespeichert, zum Beispiel Passwortmanager.
- **Tagesliste** unter der Timeline mit Von, Bis, Dauer, Typ, Kunde und Details.
  - Die Statuszeile zeigt die belegte Zeit des Tages. Überschneidungen werden nicht doppelt gezählt.
  - Markierte Zeilen kopierst du mit STRG + C, zum Beispiel für die Ticket-Dokumentation.
- **Details per Maus:** Fährst du über einen Eintrag, siehst du Kunde, Zeitraum und Dauer. Ein Klick oder ein Doppelklick in der Liste öffnet die Details.
- **Immer aktuell:** Die Logs werden alle 2 Minuten geprüft. Mit F5 liest du sie sofort neu ein. Gelesen werden nur Dateien, die sich geändert haben.
- **Bedienung:**
  - Die rote Linie zeigt die aktuelle Uhrzeit, die Arbeitszeit aus den Einstellungen ist hervorgehoben.
  - Zoom nur in der Breite, mit STRG + Mausrad an der Mausposition. Das Mausrad allein blättert durch den Tag.
  - Dunkles und helles Design, eigene Aktivitätstypen mit frei wählbaren Farben.

### Tastenkürzel

| Kürzel | Aktion |
|---|---|
| STRG + ← / → | Vorheriger / nächster Tag |
| STRG + T | Heute |
| F5 | Logs neu einlesen |
| STRG + `+` / `-` | Zoom |
| STRG + 0 | Zoom zurücksetzen, Arbeitszeit zeigen |
| STRG + C | Markierte Zeilen der Tagesliste kopieren |

## Voraussetzungen

- Windows 10 oder 11
- Python 3.9 oder neuer, wenn du das Programm aus dem Quellcode startest
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

Die fertige `ZeitZeuge.exe` liegt danach in `dist/`. Die Einstellungsdatei `zeitzeuge_config.json` legt Zeitzeuge beim ersten Start neben der EXE an.

## Einrichtung

### TeamViewer und RDM

Über die Knöpfe **TeamViewer** und **RDM** in der Werkzeugleiste stellst du ein:
- wo die Logdateien liegen,
- eine Zeitzonenkorrektur, weil TeamViewer seine Zeiten in UTC speichert.

Standardpfade:

| Quelle | Pfad |
|---|---|
| TeamViewer | `%APPDATA%\TeamViewer\Connections.txt` |
| RDM | `%LOCALAPPDATA%\Devolutions\RemoteDesktopManager\Connections.log` |

### Telefonate aus 3CX

Am einfachsten über **Einstellungen ▾ → Browser-Anbindung (3CX) einrichten …**. Der Assistent öffnet nacheinander die richtigen Seiten in Chrome, und du bestätigst jeweils mit einem Klick:

1. Tampermonkey im Chrome Web Store hinzufügen.
2. Bei Tampermonkey den Schalter „Nutzerskripte zulassen“ einschalten (ab Chrome 138 nötig).
3. 3CX-Adresse eintragen, **Skript installieren** klicken und in Tampermonkey bestätigen.
4. Anrufliste öffnen. Sobald sich das Skript meldet, zeigt der Assistent einen Haken.

Eine vollautomatische Installation ohne Klick lässt Chrome aus Sicherheitsgründen nicht zu. Updates des Skripts holt sich Tampermonkey danach selbst von Zeitzeuge.

So läuft die Übertragung:

```
3CX-Webclient (Browser) ──Tampermonkey-Skript──▶ Zeitzeuge (127.0.0.1:8765) ──▶ anrufe.json ──▶ Timeline
```

Wenn Tampermonkey beim ersten Senden fragt, erlaube den Zugriff auf `127.0.0.1` mit „Immer erlauben“.

Solange die Anrufliste offen ist, wird sie jede Minute übertragen. Unten rechts auf der Seite gibt es außerdem den Knopf **„→ Zeitzeuge“** zum Senden von Hand. Der Server nimmt nur Verbindungen vom eigenen Rechner an, und doppelte Anrufe werden aussortiert.

Die Einstellungen für Telefonate stehen in `zeitzeuge_config.json`:

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `calls_enabled` | `true` | Anrufe empfangen ein oder aus |
| `calls_port` | `8765` | Port, er muss zum Skript passen |
| `calls_ignore_missed` | `true` | Verpasste Anrufe ausblenden |
| `calls_min_duration` | `0` | Kürzere Anrufe ausblenden (in Sekunden) |
| `calls_3cx_url` | `https://voice.visaas.de:5001` | Adresse des 3CX-Webclients |

### Aktivitätsprotokoll

Ein- und ausschalten über **Einstellungen ▾ → Aktive Fenster aufzeichnen**. Die Daten liegen pro Tag in `aktivitaet/JJJJ-MM-TT.jsonl` neben der EXE.

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `tracking_enabled` | `true` | Aufzeichnung an oder aus |
| `tracking_idle_minutes` | `5` | Ab so vielen Minuten ohne Eingabe gilt der PC als verlassen |
| `tracking_ignore` | `["KeePass", "Bitwarden", …]` | Fenster mit diesen Wörtern werden nur als „(ausgeblendet)“ gespeichert |

### Im Hintergrund laufen

Aufgezeichnet wird nur, solange Zeitzeuge läuft. Schließt du das Fenster, läuft Zeitzeuge im Infobereich weiter (Symbol neben der Uhr). Richtig beenden geht über Rechtsklick auf das Symbol → **Beenden**.

Damit Zeitzeuge mit Windows startet:

1. Drück `Win + R`, gib `shell:startup` ein und drück Enter.
2. Leg in dem Ordner eine Verknüpfung zu `ZeitZeuge.exe` an.
3. Häng in den Eigenschaften der Verknüpfung unter **Ziel** ` --minimized` an. Dann startet Zeitzeuge direkt im Infobereich.

### RDM im Rechenzentrum

Läuft RDM auf einem Server, kann Zeitzeuge dessen Log auch über das Netzwerk lesen. Trag unter **Einstellungen ▾ → RDM-Logs …** den Netzwerkpfad ein, zum Beispiel `\\server\c$\Users\<name>\AppData\Local\Devolutions\RemoteDesktopManager\Connections.log`. Weicht die Zeitzone des Servers ab, gleichst du das dort mit der Zeitzonenkorrektur aus.

### Weitere Einstellungen

| Schlüssel | Bedeutung |
|---|---|
| `work_start`, `work_end` | Arbeitszeit, z. B. `"08:00"` und `"17:00"` |
| `dark_mode` | Dunkles Design |
| `activity_types`, `type_colors` | Aktivitätstypen und ihre Farben |

## Projektstruktur

| Datei | Inhalt |
|---|---|
| `main_timeline.py` | Hauptfenster, Werkzeugleiste, Einstellungen, Design |
| `timeline_only.py` | Zeichnen der Timeline, Tooltips, Zoom |
| `log_parsers.py` | Einlesen der TeamViewer- und RDM-Logs |
| `call_import.py` | Empfang der 3CX-Anrufe, Auslieferung des Browser-Skripts |
| `activity_tracker.py` | Aktivitätsprotokoll (aktives Fenster, Leerlauf) |
| `browser_setup.py` | Einrichtungsassistent für Tampermonkey |
| `tests/smoke_test.py` | Schnelltest, läuft bei jedem Build |
| `settings_dialogs.py` | Dialoge für Logpfade und Aktivitätstypen |
| `zeitzeuge_anrufe.user.js` | Tampermonkey-Skript für den 3CX-Webclient |
| `ZeitZeuge.spec` | Build-Datei für PyInstaller |
| `build.bat` | EXE auf dem eigenen PC bauen |
| `.github/workflows/build.yml` | Automatischer EXE-Build auf GitHub |

## Datenschutz

Zeitzeuge arbeitet nur auf deinem eigenen Rechner. Es liest lokale Logdateien und nimmt Anrufe nur über `127.0.0.1` entgegen. Es werden keine Daten an fremde Server gesendet.

Das Aktivitätsprotokoll speichert Fenstertitel. Darin können Kundennamen, Betreffzeilen von Mails oder Dateinamen stehen. Die Dateien in `aktivitaet/` gehören deshalb nur auf deinen PC. Sie stehen in `.gitignore`, genauso wie `anrufe.json` und die persönliche `zeitzeuge_config.json`.


## Lizenz

MIT, siehe [LICENSE](LICENSE).
