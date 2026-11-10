# Leistung: Zeichnen, Daten lesen, Daten bereitstellen (10.11.2026)

## Kurz

Mit realistisch vollen Daten war Zeitzeuge deutlich langsamer, als `perf_bench.py` zeigte
(der Benchmark kannte nur TeamViewer, RDM und 1000 Fensterwechsel). Mit dem neuen
`tests/heavy_bench.py` und cProfile wurden die teuersten Stellen gefunden und behoben:

| Messung (heavy_bench, Median) | vorher | nachher |
|---|---:|---:|
| Tag wechseln, je Tag | 240 ms | 100–110 ms |
| Tag zeichnen (heute) | 159 ms | 73 ms |
| Tag zeichnen, Zwischenspeicher leer | 230 ms | 105–110 ms |
| Neu einlesen (alle 2 Minuten) | 248 ms | 118 ms |
| Tagesliste füllen | 57 ms | 34 ms |
| Nur anordnen (Zoom, Fenstergröße) | 14 ms | 9 ms |

Start (`start_bench.py`) und `perf_bench.py` sind unverändert oder etwas schneller. Alle Tests grün.

## Testdaten (`python tests/heavy_bench.py [Durchläufe] [--profile]`)

- aktive Fenster: heute 4000 Wechsel, dazu 90 Arbeitstage mit je 3000 (196.000 Zeilen in der Datenbank)
- 40 Anrufe je Arbeitstag über ein Jahr (10.480)
- 90 Tage Outlook (6 Termine, 60 Mails je Tag), Tätigkeiten (12 je Tag) und Spuren vom PC
  (60 Browser-Blöcke, 60 Dateien, Netzwerk, Sperren je Tag)
- ein Jahr TeamViewer- und RDM-Logs, 40 Kunden in der Kundenliste

`--profile` druckt je Messung die 25 teuersten Funktionen.

## Gefunden und behoben

1. **Langsames Zeit-Parsen im Zeichenpfad.** `focus.py` (Arbeitsblöcke), `travel.py`, `billing.py`,
   `booking_rate.py`, `day_summary.py` und `call_import.py` nutzten noch `datetime.strptime`.
   Beim Tageswechsel waren das rund 15.000 Aufrufe je Tag. Jetzt `timefmt.parse` (fromisoformat,
   gemerkt). Neu: `timefmt.fmt` statt `strftime` zum Schreiben (Spuren vom PC, Anrufe,
   Zusammenfassen), etwa fünfmal schneller.
2. **Dieselben Daten mehrmals je Zeichnen.** Timeline, Tagesliste, Zeile „Doku“ und Statuszeile
   riefen `activities_for` 3–4×, `pc_entries_for` rund 10× und `doc_candidates` 2× für denselben
   Tag auf. Neu: `TimelineView.memo` merkt Ergebnisse nur während eines `draw_timeline`
   (danach wieder leer, nichts kann veralten). Aufrufer bekommen Kopien.
3. **Fensterstücke zusammenfassen.** `pc_entries_for` merkt sich je Tag das Ergebnis, solange die
   Fensterstücke gleich sind (Vergleich über alle Stücke, also exakt).
4. **Arbeitsblöcke (`focus.focus_blocks`).** Regeln wurden für jedes Fensterstück neu geprüft,
   jetzt einmal je (Programm, Titel). Beim Suchen der Rückkehr nach einem kurzen Sprung wurde
   jedes Mal der Rest der Liste kopiert (`pieces[i + 1:]`, quadratisch). `app_label` ist gemerkt.
   Ergebnis bitgleich (geprüft mit Prüfsumme über 3000 Stücke).
5. **Spuren vom PC alle 2 Minuten neu aufbereitet.** `LocalReader.entries` baut die Einträge nur
   neu, wenn sich das Archiv oder ein Schalter geändert hat.
6. **Spuren-Aufzeichnung zeichnete auch andere Tage neu.** Solange eine SSH-Sitzung lief oder der
   Bildschirm gesperrt war, startete alle 30 Sekunden ein komplettes Neueinlesen, auch wenn ein
   anderer Tag angezeigt wurde. Jetzt wie bei mstsc und VPN nur, wenn heute angezeigt wird;
   sonst wird nur der Zwischenspeicher verworfen.
7. **Tagesliste malte je Zeile einen Farbpunkt.** Jetzt einmal je Farbe.

Neue Tests: `tests/draw_cache_test.py` (Zwischenspeicher beim Zeichnen, nie veraltet) und
Ergänzungen in `tests/perf_cache_test.py` (Zeitformat, Arbeitsblöcke, Spuren vom PC).

## Geprüft, im Rahmen (nicht geändert)

| Stelle | Dauer (Lastdaten) |
|---|---:|
| Fensterstücke eines Tages entschlüsseln (3000 Zeilen, erster Aufruf je Tag) | 15 ms |
| Alle Anrufe laden (1 Jahr) | 15 ms |
| Kollegen erkennen (nur nach neuem Anruf) | 29 ms |
| Spuren vom PC speichern (90 Tage, ganzes Archiv) | 12 ms |
| Neuen Anruf speichern | 0,2 ms |
| Hinweis bei Mausbewegung | 0,2 ms |

Datenbank: WAL und `synchronous=NORMAL`, passt.

## Zweite Runde: die vier größeren Umbauten (umgesetzt)

Gemessen mit CPU-Zeit, je bestes von 6 Durchgängen, alt und neu abwechselnd (die Maschine
schwankt sonst um ±20 %):

| Messung | vor der 2. Runde | nachher |
|---|---:|---:|
| Tag wechseln, je Tag | 122–129 ms | 106–118 ms |
| Timeline zeichnen (heute) | 98–108 ms | 75–95 ms |
| Tagesliste mit 4200 Zeilen (jedes Fenster einzeln) | 445 ms | 119 ms |
| Vergangenen Tag lesen (3000 Fensterabschnitte) | 16,7 ms | 5,8 ms (verdichtet) |
| Spuren vom PC speichern (eine Änderung, 90 Tage Archiv) | 12,6 ms | 1,3 ms |

1. **mstsc, VPN und Spuren vom PC bereiten nur ihre eigene Quelle neu auf.** Bisher löste jede
   Änderung (bei offener RDP-Sitzung oder VPN alle 30 Sekunden) `refresh()` aus: alle Logs neu
   lesen, alle Quellen neu aufbereiten, zeichnen. Jetzt `TimelineView.reload_source("rdp" |
   "vpn" | "local")`: nur der Index dieser Quelle wird verworfen, mehrere Meldungen kurz
   hintereinander ergeben ein Zeichnen. Für mstsc liest ein Hintergrund-Thread vorher das
   Windows-Ereignisprotokoll (wevtutil), die Oberfläche wartet nie darauf. Läuft gerade ein
   Neueinlesen, passiert nichts (es bringt die Änderung ohnehin mit).
2. **Spuren vom PC je Tag gespeichert.** Ablage `lokal_spuren` hat jetzt ein Dokument je Tag (Tag =
   Beginn des Eintrags). Eine Änderung schreibt nur ihren Tag (`LocalReader._touch` merkt ihn
   vor). Das frühere eine Dokument (Tag "") wird beim ersten Lesen auf Tage verteilt und
   gelöscht. Kürzen nach Aufbewahrung löscht leere Tage.
3. **Vergangene Tage der Fensteraufzeichnung verdichtet.** `activity_tracker.compact_days` fasst die
   Zeilen jedes abgeschlossenen Tags zu einem Dokument (Ablage `aktivitaet`, gleicher Tag)
   zusammen, einmal am Tag im Hintergrund (`RetentionRunner.compact`, eine Minute nach dem Start,
   danach stündlich geprüft). `Store.compact_rows` liest, schreibt und löscht unter der Sperre;
   eine Zeile, die gerade dazukommt, bleibt als Zeile und kommt beim nächsten Mal dazu. Wie beim
   Löschen werden die alten Zeilen erst mit Nullen überschrieben. `read_segments` liest Dokument
   und Zeilen. Das automatische Löschen nach Aufbewahrung zählt und löscht verdichtete Tage mit.
   Der erste Lauf nach dem Update braucht für 90 volle Tage etwa 3 Sekunden (im Hintergrund).
4. **Tagesliste als Modell (`src/day_list_view.py`).** Statt sechs `QTableWidgetItem` je Zeile
   bekommt die Liste nur die Einträge; eine Zeile wird erst aufbereitet, wenn Qt sie zeigt.
   Zwei Fallen, die dabei auffielen:
   - Mit „an Inhalt anpassen“ fragt Qt beim Messen jede Zelle nach vielen Rollen ab, jede
     Abfrage ein Sprung nach Python (148.000 Aufrufe für 20 Tage) – das war langsamer als
     vorher. Jetzt sucht `fit_widths` je Spalte die breiteste Zeile in Python und lässt Qt nur
     diese eine Zelle messen (1.300 Aufrufe).
   - Das Stylesheet galt nur für `QTableWidget`. Die Liste heißt jetzt `QTableView#day_list` und
     ist in `theme.py` bei denselben Regeln eingetragen (Abstände, Auswahl, blaue Kante).
   Für bestehenden Code und Tests hat `DayListView` weiter `rowCount()`, `item(r, c).text()`,
   `toolTip()`, `currentRow()` und `cellDoubleClicked`.

Tests: `tests/perf_cache_test.py` (Verdichten mit nachträglicher Zeile, Löschen verdichteter Tage,
Spuren je Tag samt Umzug aus dem alten Format, nur geänderter Tag wird geschrieben),
`tests/draw_cache_test.py` (`reload_source`: nur die Quelle, ein Zeichnen für mehrere Meldungen).
