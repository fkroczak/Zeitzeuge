# Bewertung: WebView, asynccron, Multithreading – und Leistungsmessung (04.11.2026)

## Kurz

| Frage | Ergebnis | Empfehlung |
|---|---|---|
| WebView-Komponente | Möglich: Qt 6.12 bringt `QtWebView` mit WebView2-Backend (Edge-Laufzeit von Windows, ~0,4 MB). | Nicht als Ersatz für das unsichtbare Edge der Leser. Höchstens später für das Anmeldefenster. |
| asynccron | Ein Paket „asynccron“ gibt es nicht. Nächste Kandidaten: `async-cron` (letzte Version 2020) und `aiocron` 2.1. | Nicht einbauen: kein Gewinn, viel Umbau. |
| Multithreading | Ist schon da: jeder Leser hat seinen eigenen Thread, Logs werden im Hintergrund gelesen. | Kein Umbau. Die Bremsen lagen im Fenster-Thread und sind behoben (siehe Messung). |
| Leistung | Start 1,6 s → 0,4 s, Zeichnen „heute“ 115 → 34 ms, Tageswechsel 48 → 23 ms. | Umgesetzt in diesem Branch. |

## WebView

**Was es gibt:**
- `PySide6.QtWebView.QWebView` (in `PySide6-Addons`, Qt 6.12). Unter Windows nutzt es WebView2,
  also die Edge-Laufzeit, die in Windows 10/11 schon installiert ist und sich selbst aktualisiert.
  Die EXE wird nur um etwa 0,4 MB größer (`Qt6WebView.dll`, `qtwebview_webview2.dll`).
- `QtWebEngine` (eigenes Chromium, Paket `PySide6-WebEngine`): 132 MB Download, die EXE würde
  um weit über 100 MB größer. Weil Zeitzeuge eine einzelne EXE ist, müsste das bei jedem Start
  entpackt werden. Der Start würde dadurch deutlich langsamer. **Nicht geeignet.**
- `pywebview`: braucht eine eigene Ereignisschleife im Hauptthread und verträgt sich nicht mit Qt.
  **Nicht geeignet.**

**Warum QtWebView die Edge-Steuerung nicht ersetzen kann.** Die Leser (3CX, Matrix42, ITM)
steuern Edge über das DevTools-Protokoll. Davon brauchen sie mehr, als `QWebView` anbietet:

| Wird gebraucht | Edge über DevTools (heute) | QWebView |
|---|---|---|
| eigenes Profil je Quelle (`3cx_profil`, `m42_profil`) | ja | nein, nur ein Datenordner pro Programm |
| Ton, Mikrofon und Benachrichtigungen sperren | ja | nein |
| Mitschnitt der Abfragen (Buchungs-Mitschnitt, `request_recorder.py`) | ja (Network-Events) | nein |
| unsichtbar im Hintergrund lesen | ja (eigener Prozess) | nur als Fenster im Fenster-Thread |
| blockierende Aufrufe aus dem Lese-Thread | ja | nein, nur Rückrufe im Fenster-Thread |
| JavaScript ausführen, Cookies | ja | ja |

Ein Umbau würde alle drei Leser neu schreiben, aus dem eigenen Thread in den Fenster-Thread
holen und Mitschnitt und Profiltrennung verlieren. Die PAW-Regel („kein Edge im Hintergrund“)
gilt für WebView2 genauso, denn es startet ebenfalls `msedgewebview2.exe`.

**Wo es sinnvoll wäre:** das **Anmeldefenster** (3CX, Matrix42, ITM) im Zeitzeuge-Fenster
statt eines eigenen Edge-Fensters. Dafür müsste die Anmeldung im WebView2-Datenordner landen und
von dort an das Profil des Lesers kommen. Das geht nicht ohne Weiteres, weil die Profile getrennt
sind. Vorher wäre auf einem Windows-PC zu prüfen, ob die Windows-Anmeldung (SSO) bei Matrix42
in WebView2 über Qt klappt. Auf dem Linux-Prüfstand geht das nicht.

## asynccron

- `asynccron` gibt es auf PyPI nicht. `async-cron` 1.6.2 ist seit Januar 2020 unverändert,
  `aiocron` 2.1 (Februar 2025) ist gepflegt.
- Beide brauchen eine asyncio-Ereignisschleife. Zeitzeuge läuft in der Qt-Schleife. Man bräuchte
  eine Brücke (z. B. `qasync`) oder einen eigenen Thread für asyncio.
- Zeitzeuge plant keine festen Uhrzeiten, sondern Abstände mit Backoff, Netzprüfung und
  „sofort lesen“ (`_wake`): 30 s, 2, 5 und 10 Minuten. Cron-Ausdrücke passen dazu nicht.
- Die eigentliche Arbeit blockiert (psutil, Outlook-COM, websocket-client, SQLite). Sie bräuchte
  also auch mit asyncio weiter Threads.

Ergebnis: Man gewinnt nichts, bekommt aber eine neue Abhängigkeit und muss alle Leser umbauen.
Feste Uhrzeiten (z. B. „Tagesabschluss um 16:30“) gehen mit `QTimer` genauso.

## Multithreading

Diese Arbeit läuft schon in eigenen Threads:

| Thread | Datei |
|---|---|
| Leser 3CX, Matrix42, ITM (je einer, mit Backoff) | `pbx_reader.py` (`BrowserReader._loop`), `m42_reader.py`, `itm_reader.py` |
| Leser Outlook / Teams | `outlook_reader.py` |
| Logs von TeamViewer, RDM und VPN einlesen | `timeline_only.py` (`refresh`) |
| langsame Spuren vom PC (Browser-Verlauf, Dateien) | `local_sources.py` |
| KI-Vorschläge, Matrix42 buchen und Tickets suchen | `ai_classifier.py`, `m42_reader.py` |
| Hänger-Wächter | `hang_watch.py` |

Python hat eine globale Sperre (GIL), PySide6 läuft noch nicht ohne sie. Mehr Threads machen
Rechenarbeit also nicht schneller, sie helfen nur beim Warten (Netz, Dateien). Zeichnen muss in
Qt im Fenster-Thread bleiben. Die Messung zeigt: Langsam war Rechenarbeit im Fenster-Thread, die
**doppelt** gemacht wurde. Die wird jetzt vermieden, statt sie zu verteilen.

Noch im Fenster-Thread: die 30-Sekunden-Abfragen `vpn_sample`, `mstsc_sample` und `local_sample`
(`app_daylist.py`). Sie fragen Windows nach Prozessen und Adaptern. Ob sie auf echten PCs bremsen,
kann ich hier unter Linux nicht messen. Meldet `haenger.log` dort Stellen, wäre das der nächste
Kandidat für einen eigenen Thread.

## Leistungsmessung

Prüfstand: Linux-Container ohne Bildschirm (`QT_QPA_PLATFORM=offscreen`), Python 3.13,
PySide6 6.12. Die Werte sind Mediane. Absolute Zeiten auf Windows weichen ab, das Verhältnis
vorher/nachher gilt aber.

`python tests/start_bench.py 7` (leere Daten, je Lauf ein frischer Prozess):

| Messung | vorher | nachher |
|---|---|---|
| Import | 1462 ms | 227 ms |
| Fenster bauen | 104 ms | 108 ms |
| Fenster sichtbar | 1600 ms | 382 ms |
| Daten gezeichnet | 1615 ms | 398 ms |

`python tests/perf_bench.py 5` (neu: 1 Jahr TeamViewer- und RDM-Logs, 1000 Fensterwechsel heute):

| Messung | vorher | nachher |
|---|---|---|
| Import | 1390 ms | 309 ms |
| Logs einlesen (ohne Cache) | 97 ms | 88 ms |
| Fenster bis Daten gezeichnet | 698 ms | 383 ms |
| Neu einlesen, Logs unverändert (alle 2 min) | 170 ms | 39 ms |
| Timeline zeichnen (heute) | 115 ms | 34 ms |
| Tag wechseln (je Tag) | 48 ms | 23 ms |

Die Testsuite läuft dadurch auch schneller: 69 s → 40 s.

### Was gebremst hat und was geändert ist

1. **Paket `anthropic` beim Start** (1,26 s von 1,44 s Import): `ai_classifier.py` lädt es jetzt
   erst bei der ersten KI-Anfrage. `available()` prüft nur, ob es installiert ist
   (`importlib.util.find_spec`). PyInstaller packt es weiter mit ein.
2. **`datetime.strptime`** beim Zeichnen: bis zu 485 000 Aufrufe je 30 Tageswechsel
   (`prompt_topics._t`, `journal._t`, `activity_tracker.merge_segments`). Das neue `timefmt.parse`
   liefert dasselbe Ergebnis und denselben Fehler bei anderem Format, ist aber etwa zehnmal
   schneller und merkt sich Zeitstempel.
3. **Fensterwechsel 6× je Zeichnen aus der Datenbank** (Timeline, Tagesliste, Dokumentation,
   Status): `read_segments` merkt sich die letzten 8 gelesenen Tage. Sobald die Datenbank sich
   ändert, liest es neu. Das erkennt `Store.version()` am Schreibzähler und an
   `PRAGMA data_version` (auch Schreiben aus einem anderen Prozess). Aufrufer bekommen Kopien.

Abgesichert durch `tests/perf_cache_test.py`: gleiches Ergebnis wie `strptime`, auch bei
fehlerhaften Zeitstempeln, und neu lesen nach eigenem und fremdem Schreiben.
