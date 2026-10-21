# Zeitzeuge

**Zeitzeuge zeigt dir auf einer Tages-Timeline, woran du gearbeitet hast.** Das Programm liest die Spuren, die deine Werkzeuge ohnehin hinterlassen: TeamViewer-Verbindungen, Sitzungen aus dem Remote Desktop Manager und Telefonate aus 3CX. So musst du am Ende des Tages nicht mehr raten, wann du bei welchem Kunden warst.

Gedacht ist Zeitzeuge für IT-Dienstleister und Admins, die ihre Zeiten nachträglich erfassen oder abrechnen.

![Zeitzeuge Timeline](zeitzeuge.png)

## Funktionen

- **Tages-Timeline** von 00:00 bis 24:00 mit markierter Arbeitszeit. Überlappende Einträge werden in eigenen Zeilen gezeigt.
- **TeamViewer:** liest `Connections.txt` mit Sitzungs-ID, Beginn und Ende. Verbindungen unter 1 Minute werden ausgeblendet.
- **Remote Desktop Manager (Devolutions):** liest `Connections.log`.
  - RDP-, SSH-, VPN-, FTP- und Website-Verbindungen mit Beginn und Ende.
  - Angezeigte Passwörter, Benutzernamen und Einmal-Passwörter (OTP).
- **Telefonate aus 3CX:** Ein Browser-Skript überträgt die Anrufliste aus dem 3CX-Webclient, ohne dass eine API nötig ist (siehe unten).
- **Details per Maus:** Fährst du über einen Eintrag, siehst du Typ, Kunde, Zeitraum und Dauer. Ein Klick öffnet die Details.
- **Bedienung:**
  - Tag wechseln mit ◀ ▶, Kalender und „Heute“.
  - Zoom per Knopf oder mit STRG + Mausrad.
  - Dunkles und helles Design.
  - Eigene Aktivitätstypen mit frei wählbaren Farben.
- **Schnell:** Logdateien werden nur neu gelesen, wenn sie sich geändert haben.

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

```
3CX-Webclient (Browser) ──Tampermonkey-Skript──▶ Zeitzeuge (127.0.0.1:8765) ──▶ anrufe.json ──▶ Timeline
```

1. Installiere in Chrome die Erweiterung [Tampermonkey](https://www.tampermonkey.net/).
2. Lege dort ein neues Skript an und füge den Inhalt von `zeitzeuge_anrufe.user.js` ein.
3. Trag in der Zeile `@match` die Adresse deiner 3CX-Anlage ein.
4. Starte Zeitzeuge und öffne im Browser die Anrufliste.
5. Wenn Tampermonkey fragt, erlaube den Zugriff auf `127.0.0.1` mit „Immer erlauben“.

Solange die Anrufliste offen ist, wird sie jede Minute übertragen. Unten rechts auf der Seite gibt es außerdem den Knopf **„→ Zeitzeuge“** zum Senden von Hand. Der Server nimmt nur Verbindungen vom eigenen Rechner an, und doppelte Anrufe werden aussortiert.

Die Einstellungen für Telefonate stehen in `zeitzeuge_config.json`:

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `calls_enabled` | `true` | Anrufe empfangen ein oder aus |
| `calls_port` | `8765` | Port, er muss zum Skript passen |
| `calls_ignore_missed` | `true` | Verpasste Anrufe ausblenden |
| `calls_min_duration` | `0` | Kürzere Anrufe ausblenden (in Sekunden) |

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
| `call_import.py` | Empfang und Speicherung der 3CX-Anrufe |
| `settings_dialogs.py` | Dialoge für Logpfade und Aktivitätstypen |
| `zeitzeuge_anrufe.user.js` | Tampermonkey-Skript für den 3CX-Webclient |
| `ZeitZeuge.spec` | Build-Datei für PyInstaller |
| `build.bat` | EXE auf dem eigenen PC bauen |
| `.github/workflows/build.yml` | Automatischer EXE-Build auf GitHub |

## Datenschutz

Zeitzeuge arbeitet nur auf deinem eigenen Rechner. Es liest lokale Logdateien und nimmt Anrufe nur über `127.0.0.1` entgegen. Es werden keine Daten an fremde Server gesendet. Die Datei `anrufe.json` enthält Namen und Telefonnummern. Sie steht deshalb in `.gitignore`, genauso wie die persönliche `zeitzeuge_config.json`.


## Lizenz

MIT, siehe [LICENSE](LICENSE).
