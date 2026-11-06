# Entscheidungen – fortlaufend

Selbst getroffene Entscheidungen, die nicht ausdrücklich beauftragt waren, je mit Rückweg.
Ältere Einträge: `ENTSCHEIDUNGEN-2026-10-26.md`, `ENTSCHEIDUNGEN-2026-11-03-tagesabschluss.md`.

Rückgängig machen einer einzelnen Zeile: `git revert <Commit>`. Nach dem Merge in main liegen
alle Commits zusammen im Merge-Commit des PR; die ganze Nacht zurücknehmen mit
`git revert -m 1 <Merge-Commit>`.

## Nächtlicher Audit 2026-11-06 (Branch `audit/nightly-2026-11-06`)

Bericht: [`AUDIT-2026-11-06.md`](AUDIT-2026-11-06.md) · Tokens und Texte: [`DESIGN-TOKENS.md`](DESIGN-TOKENS.md)

| Datum | Bereich | Befund | Entscheidung | Begründung | Verworfene Alternativen | Commit | So rückgängig machen |
|---|---|---|---|---|---|---|---|
| 2026-11-06 | Ablauf | Branch-Vorgabe der Sitzung (`claude/nifty-rubin-iy97ea`) und Auftrag (`audit/nightly-2026-11-06`) widersprechen sich | Branch aus dem Auftrag | Auftrag nennt den Namen ausdrücklich | Sitzungs-Branch | – | – |
| 2026-11-06 | Layout | Einstellungen → Datenquellen: feste 3 Kachel-Spalten laufen bei 720 px 253 px aus dem Fenster | Spaltenzahl 1–3 nach verfügbarer Breite; Startbreite 1000 → 1040 px | kleinste Änderung, die bei jeder Breite passt; bei 1000 px liefen 3 Spalten schon 14 px über | FlowLayout (größerer Umbau); Navigation schmaler (ändert Optik überall) | `0beffc5` | `git revert 0beffc5` |
| 2026-11-06 | Layout | Wert rechts in einer Einstellungszeile (Pfad) nie schmaler als sein Text | `_ElidedLabel`: kürzt mit „…“ in der Mitte auf die echte Breite, voller Text als Tooltip | vorhandene Kürzung nutzte immer 320 px | Wert unter die Beschreibung setzen (Design-Änderung) | `0beffc5` | `git revert 0beffc5` |
| 2026-11-06 | Layout | Zeilentitel („PC-Verlauf automatisch löschen“) verbreiterte die Seite | Zeilentitel brechen um | eine Zeile Code | Titel kürzen | `c766384` | `git revert c766384` |
| 2026-11-06 | Layout | Seite „Ansicht“: feste Vorschau (≈ 300 px) überdeckt bei niedrigen Fenstern die Einstellungen | Vorschau unter 600 px Fensterhöhe ausblenden | auf Full HD mit 200 % (540 px hoch) ist für Vorschau und Einstellungen kein Platz | Vorschau mitscrollen lassen (widerspricht bewusster Entscheidung „Vorschau bleibt stehen“) | `c766384` | `PREVIEW_MIN_WINDOW_HEIGHT = 0` in `settings_window.py` oder `git revert c766384` |
| 2026-11-06 | Layout | Kundenliste: Mindestgröße 980 × 680 passt nicht auf 960 × 540 | 980 × 680 nur Startgröße, Mindestgröße 860 × 480 | Inhalt braucht nur 851 × 256 | – | `c766384` | `git revert c766384` |
| 2026-11-06 | Sicherheit | Mitschnitt schwärzte SAML/WS-Fed-Anmeldebestätigungen nicht | `saml`, `wresult`, `assertion` in `SECRET_NAME` | signierte Assertion = Anmeldung | – | `a0379b2` | `git revert a0379b2` |
| 2026-11-06 | Sicherheit | PowerShell wertet ‘ ’ ‚ ‛ als Anführungszeichen; Ordnername „Peter’s Kalender“ brach das Outlook-Skript | diese Zeichen ebenfalls verdoppeln | Syntaxfehler/Einschleusung über Config | Text per Base64 übergeben (größer) | `a0379b2` | `git revert a0379b2` |
| 2026-11-06 | Sicherheit | Edge mit `--remote-allow-origins=*`: jede Webseite dürfte sich mit dem DevTools-Port der angemeldeten Profile verbinden | Schalter entfernt | eigene Clients senden keinen Origin (`suppress_origin=True`); Browser-Tests der CI prüfen es | Origin auf `http://127.0.0.1` beschränken | `a0379b2` | `git revert a0379b2` |
| 2026-11-06 | Fehler | Tätigkeit auf anderen Tag verschieben: erst Löschen, dann Speichern – scheitert das Speichern, ist sie weg | erst speichern, dann löschen | schlimmstenfalls doppelt statt verloren | Transaktion über zwei Tage (Umbau) | `716df7c` | `git revert 716df7c` |
| 2026-11-06 | Fehler | Matrix42-Buchungsdialog leerte die eigene Fehlermeldung sofort | erst prüfen, dann Fehlertext setzen | – | – | `716df7c` | `git revert 716df7c` |
| 2026-11-06 | Fehler | Kalendereintrag „10:00 - 10:00“ wurde zur 24-h-Buchung | Eintrag ohne Dauer verwerfen | verfälschte Buchungsquote | als 0-min-Buchung behalten | `716df7c` | `git revert 716df7c` |
| 2026-11-06 | Fehler | Matrix42: nach Zeitüberschreitung „Nicht gebucht“, zweiter Klick bucht doppelt | nach dem Abschicken gilt ein Fehler als „vielleicht gebucht“: Knopf gesperrt, Zeile im Tagesabschluss abgewählt, Woche neu lesen | Doppelbuchung wird abgerechnet | automatisch in Matrix42 nachsehen (mehr Code, Netz) | `546572d` | `git revert 546572d` |
| 2026-11-06 | Tempo | Tagesabschluss öffnen 727 ms (92 000 × `strptime`) | `timefmt.parse` in `tickets`, `local_sources`, `rdp_reader` | vorhandene, getestete Funktion, gleiches Ergebnis | eigenes Caching je Aufruf | `b5f263b` | `git revert b5f263b` |
| 2026-11-06 | Tempo | Icons bei jedem Aufruf neu gerendert (≈ 1,5 ms je Icon) | `lru_cache` auf das gerenderte SVG, Rückgabe als Kopie | QIcon ist implizit geteilt | Cache je Name/Farbe (zwei Stellen) | `b5f263b` | `git revert b5f263b` |
| 2026-11-06 | Tempo | wevtutil (Ereignisprotokoll, bis 20 s) lief alle 2 min im GUI-Thread | im Lade-Thread vorwärmen; GUI trifft den 60-s-Cache | kleinste Änderung ohne neuen Thread | eigener Thread für RDP (Umbau) | `b5f263b` | `git revert b5f263b` |
| 2026-11-06 | Speicher | `_prompt_asked`/`_prompt_asked_spans` wuchsen ohne Grenze | abgelaufene Einträge bei jedem Merken entfernen | zählen ohnehin nicht mehr | – | `c10b96f` | `git revert c10b96f` |
| 2026-11-06 | Tempo | Timer des (versteckt weiterlebenden) Einstellungsfensters weckte alle 3 s | Timer nur zwischen show und hide | – | – | `c10b96f` | `git revert c10b96f` |
| 2026-11-06 | UI | Abstände 0–28 px in 12 Stufen, Schrift 12/13/14/18/20 px, Radien 2–11 px | Tokens in `theme.py` (siehe DESIGN-TOKENS.md), QSS-Platzhalter `$space_*`/`$fs_*`/`$radius*`, alle Layout-Aufrufe auf Konstanten | Auftrag; feste Skala 4/8/12/16/24/32/48 | Schriftskala 12/14/16/20/24 aus dem Auftragsbeispiel: Grundschrift 13 → 14 px hätte jedes Fenster verbreitert und Mindestgrößen gesprengt | `71bfacf` | `git revert 71bfacf` |
| 2026-11-06 | UI | ~95 Layouts ohne eigene Werte nutzten Fusion 9–11 px Rand / 6 px Abstand | `AppStyle.pixelMetric`: 12 / 8 px | eine Stelle statt 95 | jedes Layout einzeln | `71bfacf` | Zeilen `PM_Layout…` in `theme.py` entfernen |
| 2026-11-06 | UI | Wochenabschluss danach 3 px höher als 540 px | Hinweisliste Mindesthöhe 90 → 80 px | Liste scrollt ohnehin | Ränder im Dialog kleiner (gegen die Skala) | `71bfacf` | Wert in `week_dialogs.py` |
| 2026-11-06 | UI | Interne Paddings der Bedienelemente (5/13 px usw.) | **bleiben**, als abgeleitete Werte dokumentiert | sie gleichen den 2-px-Fokusrand aus; Änderung verschiebt Höhen aller Felder | auf 4/12 runden | – | – |
| 2026-11-06 | UI | Timeline-Tooltip mit eigenen Farben, Radius 10, Rand 8/10 | wie QToolTip: Tokens `tip/tiptext/tipborder`, Radius 6, Rand 8/12 | gleiche Elemente gleich | – | `db6e491` | `git revert db6e491` |
| 2026-11-06 | UI | Dialogtitel per `setBold` bzw. `<h3>` | `#section_title` (14 px fett) | eine Regel im Theme | `#page_title` (20 px, zu groß für Dialoge) | `db6e491` | `git revert db6e491` |
| 2026-11-06 | Texte | Menü „Kundenliste …“ öffnet Fenster „Kunden & Erkennung“; Statuszeile „M42“ | einheitlich „Kundenliste“ und „Matrix42“ | ein Begriff je Sache (Glossar) | Menü umbenennen (längerer Begriff) | `649d369` | `git revert 649d369` |
| 2026-11-06 | Texte | fünf Erklärtexte über 240 Zeichen | gekürzt ohne Inhaltsverlust | Scannbarkeit | stärker kürzen (Information ginge verloren) | `649d369` | `git revert 649d369` |
| 2026-11-06 | Bewusst nicht | TeamViewer-Zeiten im Sommer 1 h falsch (fester Offset +1) | **nicht geändert**, Empfehlung | Fix ändert die Bedeutung von `teamviewer_timezone_correction` (Config) | – | – | – |
| 2026-11-06 | Bewusst nicht | Kerberos-Delegation an den Matrix42-Host | **nicht geändert**, Empfehlung | nur im Firmennetz testbar | – | – | – |
