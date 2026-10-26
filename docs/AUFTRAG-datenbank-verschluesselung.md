# Auftrag: Eine verschlüsselte Datenbank statt vieler Dateien

Prompt für den nächsten Agenten (Claude Code). Komplett kopieren und als erste Nachricht senden.

---

Du arbeitest am Repository **fkroczak/Zeitzeuge** (Python 3.11, PySide6, Windows-Desktop-App,
Build per PyInstaller auf GitHub Actions, Tests mit pytest unter `tests/`). Lies zuerst
`README.md` (Funktionen, Projektstruktur, Datenschutz), `docs/quality-guardrails.md` und
`config_defaults.py`. Alle Texte in der Oberfläche und in Commits sind Deutsch, Du-Form, kurz.

## Ziel

1. **Weniger Dateien:** Statt vieler JSON-Dateien und Tagesordner liegen alle Nutzdaten in
   **einer** SQLite-Datei `zeitzeuge.db` im Datenordner. Danach bleiben dort nur noch
   `zeitzeuge.db`, `zeitzeuge_config.json` (nur Einstellungen) und `fehler.log`.
2. **Verschlüsselt:** Wer die Dateien liest (Personal, Kollegen, OneDrive, Backups, kopierte
   Festplatte, anderes Windows-Konto), sieht nichts. Bedienung so einfach wie möglich, und
   der Nutzer kommt auch bei vergessener PIN / neuem PC wieder an die Daten.

## Heutige Ablage (alles zu übernehmen)

Pfade stehen in `main_timeline.py` (Konstanten `*_FILE`, `*_DIR`), umziehbar über `storage.py`
(`DATA_ITEMS`). Ablagen und ihre Module:

| Daten | Heute | Modul |
|---|---|---|
| Anrufe (3CX) | `anrufe.json`, `anrufe_stand.json` | `call_import.py`, `pbx_reader.py` (merge_calls) |
| VPN-Aufzeichnung | `vpn_verbindungen.json` | `vpn_reader.py` |
| ITM-Personalzeiten | `personalzeiten.json` | `itm_reader.py` (`load_days`, `_save`) |
| Matrix42-Buchungen | `m42_buchungen.json` | `m42_data.py` (`load_store`), `m42_reader.py` (`_save`) |
| Aktive Fenster | `aktivitaet/JJJJ-MM-TT.jsonl` (alle 5 s Anhängen!) | `activity_tracker.py` |
| Eigene Tätigkeiten | `taetigkeiten/JJJJ-MM-TT.json` | `journal.py` |
| KI-Vorschläge | `ki_vorschlaege/JJJJ-MM-TT.json` | `ai_classifier.py` (`AiStore`) |
| Übernommen (PAW) | `uebernommen.json` | `transfer.py` (`ImportStore`) |
| Kundennamen | `teamviewer_names` in der Config | `config_defaults.py` |

Nicht in die Datenbank: Edge-Profile (`3cx_profil`, `itm_profil`, `m42_profil` unter
`%LOCALAPPDATA%\Zeitzeuge`), `itm_anmeldung.json` (schon per DPAPI geschützt, siehe
`itm_auth.py`), `fehler.log`, `haenger.log`. Prüfe, dass in den Logs keine Nutzdaten
(Fenstertitel, Kundennamen) landen.

## Vorgaben Datenbank

- Eine Schicht `datastore.py` (ohne Qt) mit klarer API; die bisherigen Klassen behalten ihre
  Schnittstellen (`Journal`, `AiStore`, `ImportStore`, `load_call_suggestions`,
  `read_segments`, `ItmReader.day`, `M42Reader.day` …), speichern aber über die Schicht.
  So bleiben Oberfläche und die meisten Tests unverändert.
- Mehrere Threads schreiben (Fensteraufzeichnung alle 5 s, 3CX/ITM/Matrix42-Leser,
  VPN-Monitor alle 30 s): WAL-Modus, eine Verbindung je Thread oder ein Schreib-Lock,
  kurze Transaktionen, `busy_timeout`. Absturz mitten im Schreiben darf nichts zerstören.
- Datenordner liegt oft in OneDrive-synchronisierten „Dokumenten“: WAL-/SHM-Dateien und
  gesperrte Dateien abfangen (vgl. `safe_io.py`, `FileLocked`). Wenn nötig, die DB unter
  `%LOCALAPPDATA%` und im Datenordner nur eine Sicherung — begründen und mit dem Nutzer klären.
- **Migration** beim ersten Start: alte Dateien einlesen, in die DB schreiben, Gegenprobe
  (Anzahl je Tag), alte Dateien nach `alt-<Datum>/` verschieben (nicht löschen). Abbruch
  mittendrin muss beim nächsten Start sauber weiterlaufen. `storage.move_data` /
  „Speicherort ändern“ anpassen.
- Tempo: Tagesliste und Timeline dürfen nicht langsamer werden (`tests/list_speed_test.py`,
  `tests/start_bench.py`).

## Vorgaben Verschlüsselung

- Zufälliger Datenschlüssel (256 Bit). Nutzdaten mit **AES-256-GCM** aus dem Paket
  `cryptography` (in `requirements.txt` mit fester Version). Unverschlüsselt dürfen nur
  technische Spalten bleiben (Tag, Zeitstempel für die Suche); Inhalte (Kunden, Titel,
  Texte, Nummern) nur verschlüsselt. Alternativ SQLCipher — nur wenn Wheels für Windows
  sauber und ohne Zusatz-DLLs von zweifelhafter Herkunft verfügbar sind (die PAW hat
  Cortex XDR, siehe README „Zwei PCs“).
- Der Datenschlüssel liegt nur verpackt in **Schlüsselfächern** (Tabelle `key_slots`):
  1. **Windows-Anmeldung (DPAPI, CurrentUser)** — Standard, Start ohne Abfrage.
     Vorbild: `itm_auth.py` (CryptProtectData über ctypes).
  2. **Wiederherstellungsschlüssel** — lange Zeichenfolge in Blöcken (wie BitLocker), wird
     bei der Einrichtung einmal gezeigt (kopierbar), der Nutzer legt ihn als Eintrag in
     **RDM** ab. Öffnet die Daten auf neuem PC / neuem Konto; danach neues DPAPI-Fach anlegen.
  3. **Optional (Schritt 3, erst nach Rückfrage):** Windows Hello oder eigene PIN als
     zusätzliche Abfrage beim Start (PIN: Argon2id/scrypt, Fehlversuche bremsen). Nötig nur,
     wenn auch Domänen-Admins nicht herankommen sollen (DPAPI ist mit dem Domänen-Backup-Key
     umgehbar).
- **Kein Start über RDM mit Schlüssel in der Befehlszeile:** Cortex XDR protokolliert
  Befehlszeilen zentral.
- **PAW-Export verschlüsseln** (`transfer.py`): mit einem Übertragungsschlüssel, den der
  Nutzer ebenfalls in RDM ablegt (auf PC und PAW gleich). Altes, unverschlüsseltes Format
  beim Import weiter annehmen, aber mit Hinweis.
- Menü **Einstellungen → Datenspeicher → Schutz …**: Stand anzeigen, Wiederherstellungsschlüssel
  neu erzeugen (alter wird ungültig), mit Wiederherstellungsschlüssel öffnen, optional
  PIN/Hello an/aus. Klare, kurze Texte; Bedienbarkeit nach `docs/quality-guardrails.md`.
- Ohne passendes Fach: verständlicher Dialog („Daten sind gesperrt – Wiederherstellungsschlüssel
  aus RDM eingeben“), niemals die Daten überschreiben oder neu anlegen.

## Offene Entscheidungen (vor Schritt 3 den Nutzer fragen)

1. Reicht Schutz vor Personal/Dritten (DPAPI + Wiederherstellungsschlüssel), oder sollen auch
   Domänen-Admins nicht herankommen (dann Hello/PIN beim Start)?
2. Ist der Nutzer einverstanden, Wiederherstellungs- und Übertragungsschlüssel in RDM abzulegen?
3. DB im Datenordner (OneDrive) oder lokal unter `%LOCALAPPDATA%`?

## Vorgehen

1. Plan kurz vorlegen (Schema, API von `datastore.py`, Migration), dann umsetzen.
2. Schritt 1 (DB + Migration) und Schritt 2 (Verschlüsselung DPAPI + Wiederherstellungsschlüssel
   + verschlüsselter Export) zusammen; Schritt 3 nur nach Antwort auf Frage 1.
3. Tests: neue reine Logik-Tests (`*_test.py` mit `test_`-Funktionen) für Schema, Migration
   (inkl. Abbruch und doppeltem Start), Ver-/Entschlüsselung, Schlüsselfächer, falscher
   Schlüssel, gesperrte Datei; bestehende Tests müssen grün bleiben
   (`QT_QPA_PLATFORM=offscreen python -m pytest -q`). Browser-Tests laufen lokal mit
   `ZEITZEUGE_BROWSER=<chromium>` und `ZEITZEUGE_BROWSER_ARGS=--no-sandbox`.
4. README (Funktionen, Speicherort, Datenschutz, Projektstruktur, Config-Tabelle) aktualisieren.
5. Auf einem eigenen Branch arbeiten, PR mit der Vorlage `.github/pull_request_template.md`.

## Zuletzt erledigt (Kontext)

Ladeanzeige, ausblendbare Timeline-Zeilen, „Zuordnung ohne KI“, Matrix42-Leser und -Abgleich,
Export/Import Arbeits-PC → PAW inkl. KI-Vorschlägen, PAW-Modus ohne Edge (Cortex XDR),
Ordner-Build, Personalzeit als eigene Zeile. Details: `git log`, README.
