# Leistung, dritte Runde: Start, Umrisse, Tageswechsel (10.11.2026)

Aufbauend auf `docs/PERFORMANCE-2026-11-10.md` (PR #77). Ziel: Start und Bedienung um
mindestens 50 % schneller, ohne Funktion wegzunehmen, und schon beim Laden ein Fenster, das
nach etwas aussieht.

## Ergebnis

Gemessen auf denselben Lastdaten, alter Stand (PR #77) und neuer Stand abwechselnd, Median
aus 7 Starts bzw. 5 Durchläufen. Die Maschine schwankt um ±10–20 %.

| Messung | PR #77 | neu | |
|---|---:|---:|---:|
| **Start: erstes Bild** (Umrisse) | 3,3–3,4 s | 0,44–0,48 s | −86 % |
| **Start: Tag fertig gezeichnet** | 3,7 s | 1,18–1,19 s | −68 % |
| **Tag wechseln, je Tag** | 1022 ms | 162 ms | −84 % |
| Tag wechseln, verdichtete Tage | 1293 ms | 120 ms | −91 % |
| Tag zeichnen (heute, warm) | 115 ms | 90 ms | −21 % |
| Tagesliste füllen (heute) | 74 ms | 29 ms | −61 % |
| Neu einlesen (alle 2 Minuten) | 158 ms | 121 ms | −24 % |
| Vergangenen Tag lesen (verdichtet) | 12,7 ms | 6,4 ms | −50 % |
| Start ohne Daten (`start_bench.py`) | 0,46 s | 0,48 s | gleich |

Start: `python tests/heavy_start_bench.py 7` (neu), Vergleich mit einem anderen Stand über
`--src <Ordner>/src --data <Ordner mit Lastdaten>`. Bedienung: `python tests/heavy_bench.py 5`.

## Wichtigster Fund: Kundenliste machte alles langsam

`heavy_bench.py` legte die Kundenliste im alten Format an (`keywords`, `domains`). Das gibt es
so nicht mehr: Alle Kunden kamen ohne Spuren an, Stichwörter griffen nie. Mit der Liste im
aktuellen Format (Spuren `word` und `mail`) brauchte schon PR #77 für den Start 3,7 s und für
einen Tageswechsel 1 s. Ursache:

1. **Arbeitsblöcke (`focus.focus_blocks`) waren quadratisch.** Mit Kunden im Fenstertitel
   entstehen Tausende kurzer Blöcke. Schritt 4 (kurze Blöcke in den Nachbarn aufnehmen) suchte
   bei jedem Schritt den kürzesten in der ganzen Liste und verband danach die ganze Liste neu
   (`_join_same`), Schritt 2 (kurze Sprünge zuordnen) suchte für jeden Sprung den Rest der Liste
   ab. Neu: Heap für den kürzesten Block, verkettete Liste für die Nachbarn, Verbinden nur rund
   um den gewachsenen Block (`_absorb_short`); Sprungziele vorab (`_attach_jumps`).
   Heute (3367 Fensterstücke): 1066 → 147 ms beim ersten Mal, 94 → 36 ms danach.
   **Ergebnis bitgleich:** `tests/focus_equiv_test.py` vergleicht die alten Verfahren mit den
   neuen auf Zufallsdaten (auch mit überlappenden Zeiten und anderen Einstellungen); auf den
   Lastdaten für sechs Tage geprüft.
2. **Kundenindex wurde ständig neu gebaut.** `customers.index` merkte nur einen Index. Timeline
   (eigene Liste) und Hauptfenster (mit übernommenen Daten eines anderen PCs) fragen
   abwechselnd mit verschiedenen Schlüsseln, also wurde bei jedem Wechsel neu gebaut. Jetzt bis
   zu vier Indexe.
3. **Tätigkeit je Fenster über Aufrufe gemerkt.** `focus.activity_of` (Regeln, Stichwörter)
   wird je (Programm, Titel) gemerkt, solange Regeln und Kundenliste gleich sind (Vergleich
   über `repr(rules)` und dasselbe Index-Objekt). Dieselben Fenster kommen jeden Tag und bei
   jedem Neuzeichnen wieder.

`heavy_bench.py` legt die Kundenliste jetzt im aktuellen Format an.

## Start: Umrisse sofort, einmal zeichnen

Vorher: Fenster zeigen, dann im Fenster den ganzen Tag ohne Logs rechnen und zeichnen
(blockiert, kein Bild), danach Logs im Hintergrund lesen und den Tag ein zweites Mal zeichnen.

Neu (`TimelineView.start_first_load`):

1. **Umrisse (`src/skeleton.py`).** Bis zum ersten Zeichnen malt die Timeline graue Balken in
   Zeilen, eine Legende und die Stundenleiste; die Tagesliste zeigt Zeilen aus grauen Balken
   unter den echten Spaltenköpfen; die Kacheln „Erfasst“, „Offen“, „Vorschläge“ und „Nach
   Kunde“ einen grauen Wert. Alles pulsiert sanft (ein Zeitgeber, 60 ms, nur solange es
   Umrisse gibt, höchstens 60 s). Farben aus der Schriftfarbe, also in Hell und Dunkel passend.
   Die Ansichts-Chips bekommen ihre Breite schon beim Zeigen (vorher erst mit den Daten, das
   war vorher nie zu sehen).
2. **Erst malen, dann lesen.** Der Lese-Thread startet, sobald die Umrisse gemalt sind
   (spätestens nach 250 ms; im Infobereich gestartet sofort). Läuft er gleichzeitig, braucht
   das erste Bild ~280 statt ~105 ms: Qt ruft beim Malen viel Python auf und wartet jedes Mal
   auf den GIL. Bis zum ersten Zeichnen wechselt Python außerdem öfter zwischen den Threads
   (`sys.setswitchinterval(0.0005)`, danach wieder der alte Wert).
3. **Vorarbeit im Lese-Thread (nur beim Start):** Anrufliste und Kollegen erkennen, Spuren vom
   PC aufbereiten, die heutigen Fensterabschnitte lesen und ihnen ihre Tätigkeit zuordnen. Alles
   davon ist ohne Qt und schon threadsicher (Datenbank mit Sperre, `LocalReader` mit Sperre);
   für `read_segments` kam eine Sperre um den Zwischenspeicher dazu.
4. **Einmal zeichnen.** Sind die Logs da, zeichnet `first_show` (bevorzugter Zeitraum) den Tag
   genau einmal, gleich mit den Logs. Dauert das Lesen länger als 1,5 s (Logs auf einem
   Netzlaufwerk), wird wie bisher erst ohne Logs gezeichnet und danach nachgezogen.

`tests/startup_skeleton_test.py` prüft: Umrisse vor dem Zeichnen, genau ein Zeichnen mit Logs,
danach keine Umrisse und kein Zeitgeber mehr.

## Kleinere Stellen

| Stelle | vorher | nachher |
|---|---:|---:|
| TeamViewer-Log, 1 Jahr (Zeitzone mit Sommerzeit) | 47 ms | 26 ms |
| RDM-Log, 1 Jahr | 79 ms | 60 ms |
| Kollegen erkennen (`colleagues._short`) | 1,0 µs/Nummer | 0,5 µs/Nummer |
| Tagesliste: Spaltenbreite messen (308 Zeilen) | jede Zeile ganz aufbereitet | nur Von, Bis, Dauer, Typ |

- `log_parsers.utc_to_local` merkt den Versatz je Viertelstunde (UTC) und Zeitzone; liegt eine
  Umstellung in der Viertelstunde, wird wie bisher einzeln gerechnet. Ergebnis identisch
  (UTC und Europe/Berlin geprüft).
- RDM: Protokoll je Eintragstyp gemerkt, Zeitversatz nicht je Zeile neu angelegt.
- `DayListView.set_entries(…, fit_text)`: Die Breite der Spalten Von, Bis, Dauer und Typ wird an
  denselben Texten gemessen, ohne Kunde, Details, Hinweise und Farbpunkt jeder Zeile zu bauen.
  Der Test vergleicht `fit_text` mit den Zellen.

## Geprüft, nicht geändert

- Import (~260–300 ms): größtenteils PySide6 (~100 ms) und das Anlegen der Qt-Aufzählungen.
  `urllib`/`http.client` über `net.py` kosten ~20 ms, werden aber von vielen Modulen gebraucht.
- Mausbewegung (Hinweis): 12 ms je 50 Bewegungen in beiden Ständen (vorher gemessene 15/23 ms
  waren Schwankung).
- Verdichten vergangener Tage (läuft einmal im Hintergrund): unverändert ~4 s für 90 Tage.
