# Qualitäts-Guardrails: Bedienbarkeit und Barrierefreiheit

Zeitzeuge ist eine Windows-Desktop-App (PyQt5), keine Webseite. Lighthouse und WAVE
passen deshalb nicht. Die gleichen Ziele (WCAG 2.2 AA, gute UX) prüfen wir mit
Qt-eigenen Mitteln.

## Was automatisch geprüft wird

| Prüfung | Datei | In CI | Wirkung |
|---|---|---|---|
| Bedienbarkeit (siehe unten) | `tests/ui_audit_test.py` | Schritt „Bedienbarkeit“ | **blockiert** den Build |
| Lesbarkeit README und UI-Texte | `tests/readability_check.py` | Schritt „Lesbarkeit“ | warnt nur |
| Tagesliste zusammenfassen (keine Einträge gehen verloren) | `tests/grouping_test.py` | Schritt „Tagesliste zusammenfassen“ | blockiert |
| Start des Hauptfensters | `tests/start_test.py` | Schritt „Starttest“ | blockiert |
| Infobereich: Menü, Aufzeichnung pausieren/fortsetzen, Zustand überall gleich | `tests/tray_test.py` | Schritt „Infobereich …“ | blockiert |
| TeamViewer-/RDM-Logs einlesen, Zeitformat streng | `tests/parser_test.py` | Schritt „Logs einlesen …“ | blockiert |
| Startzeit (Fenster sichtbar, Daten gezeichnet) | `tests/start_bench.py` | nein, von Hand | Messwert |

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
- Farben nur aus `THEMES` in `main_timeline.py`. Neue Farbpaare in den Kontrasttest aufnehmen.
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

## Ausnahmen

Keine.

## Nicht automatisch prüfbar (Checkliste im PR-Template)

- Test mit Windows-Sprachausgabe (Narrator, STRG + WIN + Eingabe) oder NVDA.
- Bedienung nur mit Tastatur: Tab-Reihenfolge, Fokus nicht verloren nach Dialogen.
- Darstellung bei 150 % und 200 % Windows-Anzeige.
- Verständlichkeit neuer Texte, Zahl der gleichzeitigen Entscheidungen (Hick).
