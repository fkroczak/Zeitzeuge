# Buchungsquote, Wochenabschluss, Prüfung bei Feierabend (Agent D)

## README-Text

### Funktionsliste (nach „Matrix42“ einfügen)

- **Buchungsquote:** Zeitzeuge rechnet aus, wie viel deiner Personalzeit in Matrix42 gebucht ist.
  Ziel sind 80 % pro Tag. Unter 50 % ist die Quote rot (✗), bis unter dem Ziel gelb (!), ab dem
  Ziel bis 100 % grün (✓), darüber dunkelgrün (✓✓). Die Statuszeile zeigt „Quote heute 72 % ·
  7 Tage 81 %“. Ein Klick öffnet den Wochenabschluss. Die Anzeige erscheint nur, wenn Matrix42
  Daten liefert.
- **7-Tage-Wert:** die letzten 7 gestempelten Tage bis heute. Heute zählt nur, wenn du gestempelt
  hast, und nur bis jetzt. Tage ohne Matrix42-Daten zählen nicht mit. Sie stehen als
  „Matrix42 nicht gelesen“ da, statt als 0 %.
- **Wochenabschluss (F8):** Montag bis Freitag der Woche, Samstag und Sonntag nur, wenn du da
  gestempelt oder gebucht hast. Je Tag: Personalzeit, gebucht, Quote, Zeit ohne Buchung und offene
  Tätigkeiten. Darunter Hinweise wie „Dienstag: 1:20 h nicht gebucht“ und der 7-Tage-Wert.
  Mit ◀ ▶ (oder Bild auf/ab) blätterst du die Wochen. Enter oder Doppelklick zeigt den Tag im
  Hauptfenster. Das Ziel stellst du dort unter „Ziel je Tag“ ein.
- **Prüfung bei Feierabend:** Bist du ausgestempelt und ist Feierabend, prüft Zeitzeuge den Tag
  einmal: mehr als 6 Stunden ohne 30 Minuten Pause (über 9 Stunden: 45 Minuten, Pausen zählen ab
  15 Minuten am Stück), mehr als 6 Stunden am Stück, PC aktiv aber ausgestempelt, Buchung außerhalb
  der Personalzeit, Buchungen überschneiden sich, Quote unter Ziel. Die Hinweise kommen mit der
  Erinnerung an offene Tätigkeiten oder allein, und stehen auch im Wochenabschluss. Abschalten:
  Einstellungen → Nachfragen und Erinnerungen → „Bei Feierabend prüfen“.
- **In Matrix42 buchen:** kommt bald. Rechtsklick auf eine Tätigkeit und der Wochenabschluss
  zeigen den Befehl schon, noch ausgegraut.

### Tastenkürzel (Tabelle ergänzen)

| F8 | Wochenabschluss: Buchungsquote, Lücken und Offenes der Woche |

## Eigene Entscheidungen

1. **Personalzeit = ITM „gewertet“, solange du ausgestempelt bist.** Das ist die Zeit, die ITM nach
   Abzug der Pause wertet. Bist du noch eingestempelt (heute), zählen die gestempelten Abschnitte
   bis jetzt, weil „gewertet“ dann veraltet ist. Ohne „gewertet“ (z. B. Tage aus dem alten ITM-Backend)
   zählen ebenfalls die Abschnitte. Rückgängig: `booking_rate.personal_seconds` immer
   `seconds(spans)` zurückgeben lassen.
2. **Ohne ITM:** Personalzeit ist die Arbeitszeit aus den Einstellungen, überall als
   „Arbeitszeit (lt. Einstellungen)“ gekennzeichnet. Ein solcher Tag zählt für den 7-Tage-Wert nur,
   wenn es an dem Tag Buchungen gibt, sonst wäre jeder Urlaubstag 0 %. Die Prüfungen von Pausen,
   PC-Aktivität und Buchungen außerhalb entfallen ohne ITM (die geplante Arbeitszeit ist keine
   Stempelung). Rückgängig: `DayRate.stamped` in `booking_rate.py`, `check_day(from_itm=…)` in
   `day_checks.py`.
3. **ITM-Tag ohne Zeiten** (gelesen, aber nicht gestempelt, z. B. Urlaub) gilt als Tag ohne
   Personalzeit, nicht als Arbeitszeit aus den Einstellungen. Rückgängig: `week_dialogs.day_inputs`
   (Bedingung `itm_day is not None` → `itm_day and itm_day.get("zeiten")`).
4. **7-Tage-Wert und fehlende Matrix42-Daten:** Der Zeitraum sind die letzten 7 gestempelten Tage
   (gesucht bis 31 Tage zurück). Tage darin ohne Matrix42-Daten zählen weder bei gebucht noch bei
   Personalzeit und werden mit Datum genannt. Es wird nicht weiter zurückgesucht, damit der Wert
   wirklich „die letzten 7 Tage“ bleibt. Rückgängig: `booking_rate.seven_days`, `LOOKBACK_DAYS`.
5. **Buchungen zählen ganz**, auch außerhalb der Personalzeit (Quote kann so über 100 % gehen).
   Überschneidungen zählen nur einmal. Zeit außerhalb meldet die Prüfung bei Feierabend.
   Buchungen von heute zählen nur bis jetzt. Keine Rundung (der Abrechnungstakt von Agent E gilt
   nicht für die Quote).
6. **Farbe der Statuszeile** richtet sich nach dem 7-Tage-Wert (ohne ihn nach heute). Das Symbol am
   Ende (✗ ! ✓ ✓✓) zeigt dieselbe Stufe, der Hinweis beim Darüberfahren beide Werte in Worten.
   Rückgängig: `week_dialogs.status_text`. Ausblenden: Config `"booking_rate_status": false`.
7. **Tastenkürzel F8** statt STRG+W: F5–F7 sind schon Befehle der Werkzeugleiste, STRG+W heißt in
   Windows meist „Fenster schließen“. Rückgängig: `app_menus._build_toolbar` (`self.week_action`).
8. **Feierabend mit ITM** (Fehlerbehebung, betrifft auch die bisherige Erinnerung an offene
   Tätigkeiten): Bisher kam die Erinnerung, sobald das letzte Ende der Personalzeit vorbei war. Weil
   ein offener Abschnitt bis „jetzt“ reicht, kam sie schon eingestempelt, und ausgestempelt in der
   Mittagspause. Jetzt: nur ausgestempelt und ab dem geplanten Ende aus den Einstellungen (später
   ausgestempelt: gleich danach), ohne geplantes Ende eine Stunde nach dem Ausstempeln. Ohne ITM
   bleibt alles wie bisher. Rückgängig: `app_docs.end_of_day_reminder`, `day_checks.after_hours`.
9. **Feierabend-Meldung:** Mit offenen Tätigkeiten bleiben Titel und erster Satz wie bisher, dazu
   „Außerdem:“ und bis zu 4 Befunde. Ohne offene Tätigkeiten kommt einmal „Feierabend: bitte prüfen“;
   ein Klick darauf öffnet den Wochenabschluss. Die Meldung braucht wie bisher den Infobereich und
   „Nach Feierabend an Offenes erinnern“ und kommt nicht bei „Nachfragen: Aus“ (die Prüfung läuft in
   `check_prompts`). Abschalten nur der Befunde: Config `"day_checks_enabled": false`.
10. **Schwellen:** PC aktiv aber ausgestempelt ab 10 Minuten (Lücken unter 5 Minuten zwischen
    Fenstern werden überbrückt), Config `"day_checks_pc_minutes"`. Buchung außerhalb ab 5 Minuten
    (dieselbe Toleranz wie Lücken ohne Buchung, `"m42_gap_minutes"`). Überschneidung ab 1 Minute.
    Konstanten oben in `day_checks.py`.
11. **Pausenprüfung:** Zählt die Lücken zwischen gestempelten Abschnitten (ab 15 Minuten). Fehlt
    insgesamt Pause, kommt nur dieser Hinweis, sonst auch „mehr als 6 Stunden am Stück“. Eine von
    ITM automatisch abgezogene Pause gilt nicht als gestempelt. Fehler der Stempelungen selbst
    (offen seit 12 Stunden, Ende vor Start) meldet weiter nur der ITM-Leser (`itm_auth.booking_issues`).
12. **Quote-Zelle im Wochenabschluss** ist ein `QLabel` mit Objektname `rate_<stufe>`, weil das
    Stylesheet (`QTableWidget::item`) die Hintergrundfarbe von Tabellenzellen überdeckt. Der Text
    steht zusätzlich in der Zelle selbst (Screenreader, Tests).
13. **Ziel** stellst du direkt im Wochenabschluss ein (Feld „Ziel je Tag“, 1–200 %), kein eigener
    Eintrag im Menü Einstellungen. Config `"booking_target_percent"`.
14. **„In Matrix42 buchen“** im Rechtsklick-Menü als deaktivierter Eintrag ohne `&`-Buchstaben
    (Regel: reine Anzeigen brauchen keinen). `entry_menu_items` kann dafür einen dritten Wert
    `False` (= deaktiviert) liefern. Rückgängig: Eintrag `"m42_book"` in `timeline_only.entry_menu_items`.

## Geänderte Dateien

Neu:
- `booking_rate.py` – Quote, Stufen, 7-Tage-Wert (ohne Qt)
- `day_checks.py` – Prüfung bei Feierabend (ohne Qt)
- `week_dialogs.py` – Wochenabschluss-Dialog, Daten sammeln, Knopf in der Statuszeile
- `m42_booking.py` – Platzhalter „In Matrix42 buchen – kommt bald“
- `tests/booking_rate_test.py`, `tests/day_checks_test.py` (pytest, ohne Qt)
- `tests/week_gui_test.py` (Skript: Dialog, Statuszeile, Feierabend-Meldung, Menü, Einstellung)

Geändert (klein):
- `app_docs.py` – `end_of_day_reminder` erweitert, neue Methode `show_week`, Importe
- `app_menus.py` – Knopf „Wochenabschluss“ (F8, Icon „gauge“) nach „Nachtragen“
- `app_daylist.py` – `update_status_text` ruft `week_dialogs.update_rate_button`
- `app_tray.py` – Klick auf „Feierabend: bitte prüfen“ öffnet den Wochenabschluss
- `main_timeline.py` – `self.rate_button` in der Statuszeile (vor „… offen – jetzt eintragen“)
- `journal_dialogs.py` – `DocPromptDialog`: Häkchen „Bei Feierabend prüfen“
- `timeline_only.py` – deaktivierter Menüeintrag `m42_book`, `exec_entry_menu` kann deaktivieren
- `theme.py` – Farbpaare `rate_low/mid/ok/over` (+ `_text`) hell und dunkel, Stylesheet-Regeln
- `icons.py` – Icon „gauge“
- `config_defaults.py` – Block „Buchungsquote und Prüfung bei Feierabend“ am Ende
- `tests/ui_audit_test.py` – Dialog „Wochenabschluss“, Kontrast der neuen Farbpaare, `week_dialogs.py`
  in der Prüfung auf graue Texte
