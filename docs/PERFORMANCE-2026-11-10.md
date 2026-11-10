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

## Empfehlungen für später (größerer Umbau)

1. **mstsc-/VPN-Aufzeichnung löst ein komplettes Neueinlesen aus.** Solange eine RDP-Sitzung oder ein
   VPN-Tunnel offen ist, meldet die 30-Sekunden-Aufzeichnung jedes Mal eine Änderung und
   `refresh()` liest alle Logs und zeichnet neu (jetzt ~75–110 ms alle 30 Sekunden). Besser: nur
   die geänderte Quelle neu aufbereiten. Achtung: Dafür muss das Windows-Ereignisprotokoll
   (`rdp_reader.event_sessions`, wevtutil) weiter im Hintergrund gelesen werden, sonst hängt
   die Oberfläche bis zu Sekunden. Deshalb hier bewusst nicht umgebaut.
2. **Spuren vom PC liegen als ein Dokument für alle Tage in der Datenbank.** Jede Änderung
   verschlüsselt und schreibt das ganze Archiv (12 ms bei 90 Tagen, wächst mit der Aufbewahrung).
   Je Tag ablegen wie Anrufe und Outlook.
3. **Abgeschlossene Tage der Fensteraufzeichnung verdichten.** Ein vergangener Tag wird beim
   ersten Anzeigen Zeile für Zeile entschlüsselt (3000 Zeilen ≈ 15 ms). Nach Tagesende als ein
   Dokument (oder gleich als Arbeitsblöcke) speichern.
4. **Tagesliste als Modell (`QAbstractTableModel`) statt `QTableWidget`.** Bei vollem PC-Verlauf in
   der Liste (Tausende Zeilen) entfällt das Anlegen von sechs Objekten je Zeile.
