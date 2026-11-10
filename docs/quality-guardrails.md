# Qualitäts-Guardrails: Bedienbarkeit und Barrierefreiheit

Zeitzeuge ist eine Windows-Desktop-App (PySide6, Qt 6), keine Webseite. Lighthouse und WAVE
passen deshalb nicht. Die gleichen Ziele (WCAG 2.2 AA, gute UX) prüfen wir mit
Qt-eigenen Mitteln.

## Was automatisch geprüft wird

| Prüfung | Datei | In CI | Wirkung |
|---|---|---|---|
| Bedienbarkeit (siehe unten) | `tests/ui_audit_test.py` | Schritt „Tests (pytest)“ | **blockiert** den Build |
| Lesbarkeit README und UI-Texte | `tests/readability_check.py` | Schritt „Lesbarkeit“ | warnt nur |
| Tagesliste zusammenfassen (keine Einträge gehen verloren) | `tests/grouping_test.py` | Schritt „Tests (pytest)“ | blockiert |
| Start des Hauptfensters | `tests/start_test.py` | Schritt „Tests (pytest)“ | blockiert |
| Infobereich: Menü, Aufzeichnung pausieren/fortsetzen, Zustand überall gleich | `tests/tray_test.py` | Schritt „Tests (pytest)“ | blockiert |
| TeamViewer-/RDM-Logs einlesen, Zeitformat streng | `tests/parser_test.py` | Schritt „Tests (pytest)“ | blockiert |
| Klassifizierung ohne KI: Regeln, Vorrang, keine Überschneidung, Tempo | `tests/rules_test.py` | Schritt „Tests (pytest)“ | blockiert |
| Fenster-Filter (Black-/Whitelist), Schreibfehler im Aktivitätsprotokoll | `tests/tracking_filter_test.py` | Schritt „Tests (pytest)“ | blockiert |
| Robustheit: kaputte Dateien, große/UTF-16-Logs, offline, Leser-Absturz, Anmelde-Timeout, Fehler in Slots, eine Instanz | `tests/robustness_test.py` | Schritt „Tests (pytest)“ | blockiert |
| Datenbank: nichts im Klartext, Schlüsselfächer, falscher Schlüssel, Migration mit Abbruch und doppeltem Start, gesperrte Dateien, Threads | `tests/datastore_test.py`, `tests/protect_start_test.py` | Schritt „Tests (pytest)“ | blockiert |
| Export für die PAW verschlüsselt, alter Export weiter lesbar | `tests/transfer_logic_test.py` | Schritt „Tests (pytest)“ | blockiert |
| Startzeit (Fenster sichtbar, Daten gezeichnet) | `tests/start_bench.py` | nein, von Hand | Messwert |
| Zeichnen und Tageswechsel mit einem Jahr Logs und 1000 Fensterwechseln | `tests/perf_bench.py` | nein, von Hand | Messwert |
| Zeichnen, Tagesliste, Tageswechsel mit allen Quellen voll (196.000 Fensterwechsel, Anrufe, Outlook, Spuren) | `tests/heavy_bench.py` | nein, von Hand | Messwert (siehe docs/PERFORMANCE-2026-11-10.md) |
| Kleines Fenster und 100/150/200 %: abgeschnittene Texte, waagerechte Scrollleisten, passt auf 960 × 540 (Full HD bei 200 %); Screenshots | `tests/layout_check.py` | nein, von Hand | Befundliste |
| Abstände, Schrift, Rundungen nur aus Tokens | `docs/DESIGN-TOKENS.md`, `src/theme.py` | Review | Regel |

„Blockiert“ heißt: Der Lauf wird rot und es entsteht kein Release. Die Tests laufen parallel zum
Bau der EXE (Job „Tests“, aufgeteilt in 3CX, M42 und Rest); Testversionen aus Branches stehen
deshalb auch bei roten Tests zum Download bereit, nur das Release auf main wartet auf alle Tests.

`tests/ui_audit_test.py` öffnet Hauptfenster und alle Einstellungsdialoge ohne Bildschirm
und prüft:

1. **Namen für Screenreader** (WCAG 4.1.2): Jedes Bedienelement hat einen Namen, der nicht nur
   aus Symbolen besteht (`◀`, `+`). Felder bekommen ihn über `QFormLayout.addRow("Text:", feld)`,
   `label.setBuddy(feld)` oder `setAccessibleName()`.
2. **Kontrast** (WCAG 1.4.3): Alle Textfarben beider Designs und die Beschriftung auf
   Timeline-Balken mindestens 4,5 : 1. Fest eingetragene graue Texte (`color: gray`) sind verboten,
   stattdessen `setObjectName("hint")`.
3. **Sichtbarer Fokus** (WCAG 2.4.7): Das Stylesheet hat `:focus`-Regeln für Knöpfe und Felder.
4. **Tastatur** (WCAG 2.1.1): Enter in der Tagesliste öffnet die Details.
5. **Überschaubare Menüs** (Hick'sches Gesetz): höchstens 5 Einträge pro Gruppe, jeder Eintrag
   im Einstellungsmenü hat einen Alt-Buchstaben (`&`).
6. **Skalierung** (WCAG 1.4.4): Hi-DPI-Skalierung ist an, die Oberfläche wächst mit der
   Windows-Anzeigegröße.
7. **Schmales Fenster** (WCAG 1.4.10): Bei 640 px Breite ist der Knopf „»“ für ausgeblendete
   Befehle sichtbar und groß genug.
8. **Fehler in Formularen** (WCAG 3.3.1): Arbeitszeit mit Ende vor Beginn wird neben dem Tag
   als Fehler gezeigt, OK ist gesperrt.
9. **UI-Regeln** (siehe unten): Rahmen von Feldern, Knöpfen, Scrollbalken und jeder
   Timeline-Balken mindestens 3 : 1 zum Grund (WCAG 1.4.11), höchstens ein Hauptknopf je Dialog,
   und im Quelltext: keine Großbuchstaben per `.upper()`, nur `normal` und `bold`, kein reines
   Schwarz, keine fest eingetragene Schrift, Text linksbündig, Fließtext mit Zeilenhöhe 1,5.

## 16 kleine UI-Design-Regeln

Nach „16 kleine UI-Design-Regeln, die große Wirkung erzielen“ (Tech-Beat, nach Adham Dannaway).
So setzt Zeitzeuge sie um:

| # | Regel | Umsetzung in Zeitzeuge |
|---|---|---|
| 1 | Abstand gruppiert Zusammengehöriges | Beschriftung direkt am Feld (`QFormLayout`), Gruppen durch Abstand und fette Überschrift statt Rahmen. |
| 2 | Einheitlich bleiben | Farben nur aus `THEMES`, Symbole nur aus `icons.py`, eine Schrift (`theme.FONT_FAMILIES`) auch in der Timeline. |
| 3 | Was gleich aussieht, funktioniert gleich | Akzentfarbe nur für Bedienbares und Auswahl. Werte in den Einstellungen (`row_value`) in Textfarbe, weil sie nicht anklickbar sind. |
| 4 | Klare Hierarchie | Seitentitel 20 px fett, Abschnittsköpfe fett, Hinweise grau (`hint`). Ein Hauptknopf je Dialog (Test). |
| 5 | Unnötiges weglassen | Gruppen ohne Rahmen, Tabellenkopf mit 1-px-Linie, Werkzeugleiste ohne Rahmen. |
| 6 | Farbe mit Absicht | Violett = bedienbar/Fokus/Vorschlag, Hauptknopf in Textfarbe, Rot = Fehler/Jetzt, Ampelfarben nur für die Buchungsquote. |
| 7 | Bedienelemente mind. 3 : 1 | Token `control` für Rahmen von Feldern und Knöpfen, `handle` für Scrollbalken; Timeline-Farben in beiden Designs ≥ 3 : 1 zum Grund. |
| 8 | Text mind. 4,5 : 1 | Alle Textfarben beider Designs und die Schrift auf Balken (Test). |
| 9 | Nicht nur Farbe | Zustände mit Zeichen oder Text (Pause-Zeichen, „frei“/Fehlertext, Prozent der Buchungsquote, gestrichelte Lücken). |
| 10 | Eine serifenlose Schrift | Segoe UI überall, `theme.ui_font()` für selbst gezeichnete Teile. Feste Breite nur für Schlüssel und Beispiele. |
| 11 | Keine Großbuchstaben | Spaltenköpfe, Menü-Überschriften und Bereichsnamen in normaler Schreibung, dafür fett. |
| 12 | Zwei Schriftschnitte | Nur `normal` und `bold` (kein 600/700/DemiBold gemischt). |
| 13 | Kein reines Schwarz | Dunkle Schrift ist `#18181B`/`#14181D` (`readable_on`), nie `#000000`. |
| 14 | Linksbündig | Text und Felder links, auch der Wiederherstellungsschlüssel. Ausnahme: kurze Wochenüberschrift zwischen ◀ ▶. |
| 15 | Zeilenhöhe 1,5 für Fließtext | `theme.prose(label)` für Einleitungen und Erklärungen in Dialogen. |
| 16 | Zeilen nicht zu lang | Dialoge mit fester, schmaler Breite (480–560 px, etwa 70–80 Zeichen). Keine Begrenzung am Label selbst: `setMaximumWidth` setzt Text mittig oder schneidet ihn ab, ein Ereignisfilter stürzt unter Windows beim Beenden ab. |

## Lokal ausführen

```bash
pip install -r requirements.txt
set QT_QPA_PLATFORM=offscreen        # PowerShell: $env:QT_QPA_PLATFORM="offscreen"
python tests/ui_audit_test.py        # Exit-Code 1 bei Befunden
python tests/readability_check.py
```

## Regeln für neue Oberflächen

- Felder immer mit sichtbarer Beschriftung über `QFormLayout.addRow` oder `setBuddy`.
  Die Beschriftung steht direkt neben ihrem Feld, nie näher am nächsten Feld (Gesetz der Nähe).
- Knöpfe mit Symbolen bekommen `setAccessibleName("…")` mit dem ausgeschriebenen Zweck.
- Fehler neben dem Feld als Text zeigen (nicht nur farbig) und das Speichern sperren, bis sie
  behoben sind. Kein stilles Verwerfen.
- Farben nur aus `THEMES` in `theme.py`. Neue Farbpaare in den Kontrasttest aufnehmen.
- Längere Erklärtexte mit `prose(label)` aus `theme.py` (Zeilenhöhe 1,5).
- Selbst gezeichnete Schrift mit `ui_font()`, fett nur über `bold`, nie 600/700 oder DemiBold.
- Alles, was nur per Maus geht (Timeline), braucht einen Tastaturweg (Tagesliste, Tastenkürzel).
- Menügruppen mit Trennlinien, höchstens 5 Einträge pro Gruppe, mit `&` für Alt-Buchstaben.
  Reine Anzeigen im Menü (deaktiviert, z. B. „Aufzeichnung aktiv“) brauchen keinen.
- Menü nach Aufgaben: Häufiges oben und direkt, Einmaliges (Datenquellen, Speicherort) im Untermenü.
- Icons nur aus `icons.py` (eine Strichstärke, Textfarbe des Designs). Zustände nie nur über
  Farbe zeigen (z. B. grauer Punkt **mit** Pause-Zeichen).
- Ein Zustand, eine Aktion: Menü, Infobereich und Statuszeile nutzen dieselbe `QAction`.
- Texte in der Du-Form, kurze Sätze, Fachbegriffe der Zielgruppe (RDP, Log) sind in Ordnung.

## Ratchet: Werte dürfen nur besser werden

- `tests/ui_audit_test.py` erlaubt **0 Befunde**. Eine Ausnahme braucht eine Begründung als
  Kommentar im Test und einen Eintrag unten.
- Untergrenzen der Lesbarkeit stehen in `MIN_FLESCH` in `tests/readability_check.py`.
  Sie werden nur angehoben, nie gesenkt.

## Baseline und Verlauf

| Datum | Bedienbarkeits-Befunde | Flesch-Amstad README / UI |
|---|---|---|
| 21.10.2026 vorher | 45 | 61 / 55 |
| 21.10.2026 nachher | 0 | 61 / 55 |
| 22.10.2026 Überarbeitung | 0 | 60 / 60 |
| 02.11.2026 16 UI-Regeln | 0 | 60 / 60 |

## Ausnahmen

Keine.

## Nicht automatisch prüfbar (Checkliste im PR-Template)

- Test mit Windows-Sprachausgabe (Narrator, STRG + WIN + Eingabe) oder NVDA.
- Bedienung nur mit Tastatur: Tab-Reihenfolge, Fokus nicht verloren nach Dialogen.
- Darstellung bei 150 % und 200 % Windows-Anzeige.
- Verständlichkeit neuer Texte, Zahl der gleichzeitigen Entscheidungen (Hick).
