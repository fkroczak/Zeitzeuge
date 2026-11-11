# Leistung, vierte Runde: Audit nach #79–#83, Hin- und Herspringen, Dopplungen (11.11.2026)

Aufbauend auf `docs/PERFORMANCE-2026-11-10-start.md`. Auftrag: nach den vielen Änderungen
prüfen, ob Zeitzeuge langsamer geworden ist, dann ohne Einschränkung der Funktion so weit wie
möglich beschleunigen (Ziel 50 %) und doppelten Code zusammenfassen.

## 1. Audit: keine Verlangsamung durch #79–#83

Stand nach der dritten Runde (#78, `2a7c0cb`) gegen `main` mit #83 (`577e4c0`), gleiche
Lastdaten (`tests/heavy_bench.py`, `tests/heavy_start_bench.py`), abwechselnd gemessen:

| Messung | #78 | #83 |
|---|---:|---:|
| Tag zeichnen (heute, warm) | 45 ms | 38 ms |
| Tag wechseln, je Tag | 82 ms | 82 ms |
| Neu einlesen (alle 2 Min.) | 63 ms | 67 ms |
| Start: Daten da | 635–666 ms | 631–657 ms |

Alles im Rauschen (±10–20 %). Die neuen Teile wurden einzeln geprüft:

- Nachfrage-Karte (`prompt_card.py`): Zeitgeber laufen nur, solange die Karte sichtbar ist.
- Tray-Menü: der blinkende Punkt läuft nur bei offenem Menü.
- Zeitraum-Kontext (`range_context.py`): rechnet nur im Nachtragen-Dialog, Tippen wird mit
  400 ms gebündelt.
- Fahrzeit zur Termin-Adresse (#81): fragt OpenStreetMap im Hintergrund und merkt das Ergebnis.

## 2. Ergebnis der Optimierung

Median aus je zwei Läufen mit 5 Durchgängen, alter und neuer Stand abwechselnd auf derselben
Maschine:

| Messung | vorher (#83) | nachher | |
|---|---:|---:|---:|
| **Tag zurück, je Tag** (Tag kurz ansehen, dann zurück) | 125–129 ms | 44 ms | **−65 %** |
| **Hin und her** (heute ↔ Vortage), je Wechsel | 78–80 ms | 42–46 ms | **−45 %** |
| Tagesliste füllen (heute) | 16–20 ms | 12–13 ms | −30 % |
| Vergangenen Tag lesen (3000 Zeilen) | 12–17 ms | 9–10 ms | −35 % |
| Tag zeichnen, Zwischenspeicher leer | 77–81 ms | 63–72 ms | −15 % |
| Tag zeichnen (heute, warm) | 41–42 ms | 35–36 ms | −14 % |
| Neu einlesen (alle 2 Min.) | 63–69 ms | 57–59 ms | −12 % |
| Tag wechseln, neuer Tag ohne Pause | 82–84 ms | 73–74 ms | −12 % |
| Start mit Lastdaten: Daten da | 640–690 ms | 600–635 ms | −7 % |
| Start: Lese-Thread (Logs, Vorarbeit) | 266 ms | 199 ms | −25 % |
| TeamViewer-Log, 1 Jahr | 35 ms | 19 ms | −45 % |

Die 50 % werden dort erreicht, wo man im Alltag am meisten wartet: beim Durchblättern der Tage
(Nachtragen, Tagesabschluss) und beim Hin- und Herspringen. Ein ganz neuer Tag ohne Pause
davor und der Start sind 7–15 % schneller. Nach drei Runden sind dort nur noch viele kleine
Posten von je 1–5 ms übrig (Fensterstücke entschlüsseln, zusammenfassen, Blöcke bilden, Qt
zeichnen). Mehr ginge nur mit Umbauten, die Risiko bringen (Logs auf der Platte
zwischenspeichern, siehe unten).

Messen: `python tests/heavy_bench.py 5` (neu: „Hin und her“ und „Tag zurück, je Tag“).

## 3. Was geändert wurde

Alle Änderungen liefern dasselbe Ergebnis wie vorher. Geprüft mit Tests und Gegenproben
(Prüfsumme über die Arbeitsblöcke von 14 Tagen, alte gegen neue Stichwortsuche,
Zeitzonen-Umrechnung über zwei Jahre in sieben Zeitzonen, Bildschirmfoto alt gegen neu).

1. **Vortag im Hintergrund vorbereiten** (`TimelineView._schedule_prefetch`, `_prefetch`).
   400 ms nach dem Zeichnen rechnet ein Thread Fensterstücke und Arbeitsblöcke des Vortags in
   die Zwischenspeicher, nur reine Python-Teile wie beim Start (`_warm_up`). Ein Klick auf
   „Tag zurück“ trifft dann die Zwischenspeicher. Wechselt man genau zu diesem Tag, während
   der Thread noch rechnet, wartet das Zeichnen auf ihn, statt alles doppelt zu rechnen. Nicht
   bei übernommenen Daten eines anderen PCs und nicht ohne Arbeitsblöcke.
2. **Zwischenspeicher für 8 Tage statt für einen.** Arbeitsblöcke (`pc_blocks_for`) wurden
   nur für einen Tag gemerkt: Zwischen heute und gestern wurde jedes Mal alles neu gerechnet.
   Jetzt für die letzten 8 Tage, die Fensterstücke ebenso (vorher 6 Einträge, also 2–3 Tage).
   Der Schlüssel enthält die Regeln über ihren Inhalt (`repr`) statt ihrer `id`, der
   Kundenindex wird mit gemerkt. So kann keine wiederverwendete `id` alte Blöcke liefern.
   Beide Speicher haben jetzt eine Sperre (der Thread aus 1. schreibt mit).
3. **Nur einmal rendern statt bis zu zweimal.** `_render` setzte die Höhengrenzen der Timeline
   erst nach dem Berechnen der Zeilenhöhe. Der Splitter stellte die Höhe dann sofort um, und
   `_apply_resize` renderte alles ein zweites Mal (bei 6 von 9 Wechseln mit anderer
   Zeilenzahl). Jetzt erst Grenzen setzen, dann mit der neuen Höhe rendern. Einziger
   Unterschied im Bildschirmfoto: die Bildlaufposition kann um 1 Pixel abweichen.
4. **Stichwortsuche der Kundenliste** (`customers.Index.text_match`): Vor jeder Regex wird
   geprüft, ob das Wort überhaupt im Text steht (`in`, das Muster ist das Wort selbst).
   14–27 → 3–4 µs je Fenstertitel. `fold` übersetzt Umlaute nur, wenn der Text nicht ASCII ist.
   Ein Versuch mit allen Wörtern in einer Regex war dreimal langsamer (Pythons Regex kann
   lange Alternativen schlecht) und wurde verworfen.
5. **Regeln vorab filtern** (`rules.drop_impossible`): Fenster haben immer den Typ „PC“, keinen
   Kunden und keine Details. Regeln, die nur auf diese Felder schauen und dort nicht passen,
   greifen nie (10 der 16 Standardregeln) und werden in `focus_blocks` einmal weggelassen.
   Dazu prüft `match_entry` die Felder ohne Funktionsaufruf je Regel.
6. **Tagesliste:** Textbreiten werden je Schrift gemerkt (`DayListView.fit_widths`), Zeiten mit
   `f"{h:02d}:{m:02d}"` statt `strftime` formatiert (viermal schneller).
7. **Offene Tätigkeiten** (`Journal.open_items`): die dokumentierten Tätigkeiten des Tages werden
   einmal gelesen, nicht für jeden erkannten Eintrag neu (525 Mal je 9 Tageswechsel).
8. **`timeline_only.parse_time` gemerkt** (wie `timefmt.parse`): beim Zeichnen, in der Liste und
   im Hinweis kommen dieselben Zeiten immer wieder.
9. **Datenbank-Zeilen schneller lesen** (`datastore._loads`): JSON aus `_dumps` ist immer UTF-8,
   die Erkennung der Kodierung je Zeile fällt weg.
10. **TeamViewer-Log:** Die Umrechnung UTC → Ortszeit merkte den Versatz je Viertelstunde, aber
    fast jede Sitzung liegt in einer anderen Viertelstunde (6.000 Fehlgriffe auf 10.000
    Zeiten). Jetzt je Tag, wenn der Versatz am Anfang und Ende des Tages gleich ist; an Tagen
    mit Umstellung wird jede Zeit einzeln gerechnet. Über zwei Jahre in sieben Zeitzonen (auch
    Lord Howe mit 30-Minuten-Umstellung, Chatham, Indien) gleich wie die exakte Rechnung.

Neue Tests: `tests/draw_cache_test.py` (Arbeitsblöcke für mehrere Tage, Vortag vorbereiten =
selbst gerechnet), `tests/perf_cache_test.py` (Regel-Vorfilter, Stichwortsuche gegen das alte
Verfahren, Zeitzonen je Tag).

## 4. Code-Dopplungen zusammengefasst

Gesucht mit einem AST-Vergleich aller Funktionen (auch mit umbenannten Variablen) und einem
Vergleich von Zeilenblöcken. Zusammengefasst, ohne das Verhalten zu ändern:

| Doppelt | jetzt |
|---|---|
| `local_sources._utc_to_local` = `rdp_reader._event_time` (Windows-Ereigniszeit) | `timefmt.event_time` |
| `customer_discovery._t` = `outlook_data._time` (Zeit lesen oder `None`) | `timefmt.parse_or_none` |
| `_valid` in `local_sources`, `rdp_reader`, `vpn_reader` (Beginn und Ende lesbar) | `timefmt.has_times` |
| `prune` in `RdpReader` und `VpnReader` | `retention.prune_archive` |
| Ticketsuche und Trefferliste in `BookingDialog` und `TicketSearchDialog` | Basis `_TicketSearch` |
| JavaScript für Anmeldung/Token/Köpfe in `API_JS` und `FETCH_JS` (Matrix42) | `_JS_HELPERS` |

Die alten Namen bleiben als Verweise (Tests und andere Module nutzen sie). Dazu fünf
ungenutzte Importe entfernt (`pyflakes`).

Bewusst nicht zusammengefasst:

- `prompt_card.py` (Karte und Leiste haben gleiche `showEvent`/`resizeEvent`): #84 baut dort
  gerade um, das gäbe nur Konflikte.
- PowerShell-Skript für Outlook (Gesendet und Teams-Chats lesen ähnlich): hier nicht testbar.
- `m42_data.covered_seconds` und `Journal.covered_seconds`: ähnlicher Name, andere Rechnung.
- Die vielen zweizeiligen `_t(text)` je Modul: rufen schon alle `timefmt.parse`.

## 5. Geprüft, nicht geändert

- **Logs zwischen zwei Starts auf der Platte merken:** würde den Start um ~60 ms verkürzen,
  aber RDM- und TeamViewer-Log ändern sich mit jeder Verbindung. Beim morgendlichen Start
  wäre der Zwischenspeicher meist veraltet; Weiterlesen ab der letzten Stelle bräuchte den
  Zustand offener Sitzungen. Nutzen zu klein für das Risiko.
- **Gemeinsame Sekundenrechnung für `focus` und `activity_tracker`:** beim ersten Lesen eines
  Tages langsamer (leerer Zwischenspeicher), zurückgenommen.
- **Alle Stichwörter in einer Regex:** dreimal langsamer, zurückgenommen.
- `hang_watch.py`: `pyflakes` meldet einen undefinierten Namen, der Wert wird aber immer vorher
  gesetzt. Kein Fehler.
- `heavy_start_bench.py` zeigt beim Bauen des Fensters +10 ms, wenn der Stand aus einem
  Git-Checkout läuft (`version.py` fragt `git`). In der gebauten EXE gibt es das nicht.
