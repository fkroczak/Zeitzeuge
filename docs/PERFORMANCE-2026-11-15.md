# Leistung, fünfte Runde (15.11.2026)

Auftrag: 90 % schneller ohne Funktion wegzunehmen. Ergebnis vorweg: **90 % sind mit dieser
Architektur nicht erreichbar.** Die Runden vom 10. und 11.11. haben die großen Brocken schon
entfernt (Start −86 %, Tageswechsel −84 bis −91 %). Was jetzt noch Zeit kostet, verteilt sich auf
viele Posten von je 3–30 ms: Qt zeichnet (~20 ms je Tag), Python legt je Fensterstück Objekte an,
Zeilen werden entschlüsselt und aus JSON gelesen.

## Gemessen

`python tests/heavy_bench.py 5`, alter und neuer Stand abwechselnd, je zwei Läufe. Diese Maschine
schwankt um ±20 %.

| Messung | vorher | nachher | |
|---|---:|---:|---:|
| Hin und her (heute ↔ Vortage), je Wechsel | 45–53 ms | 36–40 ms | ~−22 % |
| Tag wechseln, je Tag | 84–101 ms | 80–84 ms | ~−10 % |
| Tag zurück, je Tag | 53–56 ms | 47–49 ms | ~−12 % |
| Tagesliste füllen (heute) | 14–19 ms | 11–13 ms | ~−20 % |
| Arbeitsblöcke (`focus_blocks`) je Tag, 2500 Stücke | 35–43 ms | 28–34 ms | ~−22 % |
| Tag zeichnen (heute, warm) | 41–45 ms | 46–47 ms | im Rauschen |

## Geändert (Ergebnis bitgleich)

1. **`timefmt.seconds`**: Zeitstempel als Sekundenzahl, Tag und Uhrzeit getrennt gemerkt. Vorher
   war bei jedem neuen Tag fast jeder Zeitstempel ein Fehlgriff im Zwischenspeicher.
2. **`focus_blocks`**: rechnet intern mit Sekunden statt Zeitstempel-Text (Sprünge, Blöcke,
   Splitter aufnehmen). `_absorb` hängt sortierte Listen aneinander statt neu zu sortieren.
3. **`merge_segments`**: Sekunden statt `datetime`-Differenzen.
4. **Fensterstücke ohne Kopie lesen** (`read_segments(copy=False)`), nur in `pc_entries_for`,
   das sie nicht ändert. Vergleich mit dem Zwischenspeicher über `itemgetter`.
5. **Fenster-Gedächtnis** (`focus._known_for`): bei vollem Speicher wird die ältere Hälfte
   verworfen statt alles.
6. **Fortschrittsbalken „Erfasst“** zeichnet beim Setzen nicht mehr sofort (synchron), sondern
   mit dem nächsten Bild.
7. `heavy_bench.py`: legt Daten für heute auch am Wochenende an (vorher am Sa/So leere Messung).

Geprüft: alle Tests, `tests/fast_seconds_test.py` (neu), `focus_equiv_test.py`; Prüfsumme über
Arbeitsblöcke und zusammengefasste Fenster von 25 Tagen mit mehreren Einstellungen, alt = neu.

## Was für deutlich mehr nötig wäre

- **Ergebnisse abgeschlossener Tage auf der Platte merken** (zusammengefasste Fenster und
  Arbeitsblöcke je Tag, Schlüssel aus Regeln, Kundenliste und Fensterstücken): Tageswechsel zu
  alten Tagen etwa −40 bis −50 %. Risiko: veraltete Blöcke, wenn die Ungültigmachung eine
  Änderung übersieht.
- **Heiße Schleifen kompiliert** (Cython/Rust für `focus`, `merge_segments`): Rechnen −80 % und
  mehr, aber neuer Build-Schritt für die EXE und den Installer.
- Qt-Zeichnen (~20 ms je Tag) bleibt in jedem Fall.
