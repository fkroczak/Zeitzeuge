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

## Tests und Build (CI)

Gemessen auf GitHub Actions, gleiche Tests (499, keiner übersprungen; vorher 495 + 4 neue).

| | vorher (main, 13.11.) | nachher (Branch, 15.11.) |
|---|---:|---:|
| **Ganzer Lauf (Tests + EXE + Setup)** | 9:20 min | **2:41 min** |
| Tests Windows (Job) | 9:06 min | 2:03 min |
| davon pytest | 8:15 min | 1:33 min |
| EXE / Ordner+Setup | 4:40 min nacheinander | 2:33 / 2:36 min gleichzeitig |
| Tests Linux (Branch-Push) | ~2 min | ~1 min |

Was es gebracht hat:

- **Browser-Tests warteten fest.** 3CX: nach jedem Browserstart 10 s „Seite laden lassen“
  (`PbxReader.LOAD_WAIT`, im Test 3 s); Matrix42: die Seiten-Skripte warten bis zu 30 s auf
  Anmeldung/Kalender (`M42Reader.JS_TIME_SCALE`, im Test 0,1). In der App unverändert 10 s
  bzw. Faktor 1. pbx 171 → 82 s, m42 153 → 45 s.
- **Parallel** mit pytest-xdist (`pytest.ini`: `-n auto --dist worksteal`; auf dem
  2-Kern-Windows-Runner 4 Worker, die Browser-Tests warten meist). Einzeln/Debuggen: `pytest -n 0`
  (`-p no:xdist` geht wegen `addopts` nicht mehr).
- **Langsame Tests zuerst, auf die Worker verteilt** (`tests/conftest.py`): worksteal gibt jedem
  Worker anfangs einen zusammenhängenden Block; ohne Verteilung liefen alle Browser-Tests
  nacheinander auf einem Worker.
- **Build in zwei gleichzeitigen Jobs** (Einzel-EXE; Ordner + Setup) statt nacheinander.
  Installierte Pakete im Cache statt `pip install`.
- **Release:** ein kleiner Job legt auf main/Tag den Entwurf an, beide Builds laden direkt hinein
  (nicht über den Artefakt-Speicher), veröffentlicht wird nur, wenn Tests und Builds grün sind.
  Der Weg über main ist erst mit dem nächsten Merge echt geprüft.

Gefunden vom Tester (separater Agent) und behoben:

- `recorder_test` flackerte parallel (2 von 12 Läufen): Die nachgebaute Seite meldete sich sofort
  beim Laden an, unter Last genau während Chromium für die neue Adresse den Renderer wechselt und
  der Mitschnitt sich neu anhängt. Der Nachbau meldet sich jetzt 1 s nach dem Laden an (wie ein
  Mensch). Unter Volllast 10 von 10 grün. In der App betrifft das höchstens Abfragen, die eine
  Seite in den ersten Millisekunden selbst schickt.
- Umsortieren brach bei Teilmengen mit `StopIteration` ab (z. B. nur vier langsame Tests mit
  `-n 2`).
- `focus_blocks` wich bei ungewöhnlich geschriebenen Zeitstempeln (z. B. „7:00:00“ statt
  „07:00:00“) ab; jetzt auch dort gleich wie vorher (12008 Vergleiche, 0 Abweichungen).

Untere Grenze: Ein Windows-Job braucht ~35 s zum Einrichten, PyInstaller für die Einzel-EXE
~1:40 min. Unter ~2:30 min für den ganzen Lauf geht es nur mit größeren (kostenpflichtigen)
Runnern oder ohne eine der beiden EXE-Varianten.
