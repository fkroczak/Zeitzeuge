# Abrechnungstakt und PC-Verlauf automatisch löschen (Agent E)

## README-Text

### Funktionsliste

- **Abrechnungstakt:** Zeitzeuge zeigt zu jeder Tätigkeit auch die abgerechnete Zeit.
  Standard ist der 15-Minuten-Takt: Jede angefangene Viertelstunde wird abgerechnet.
  Beim Kopieren steht sie mit in der Zeile, z. B.
  `10:05–10:17 (12 min → abgerechnet 0:15 h)  Müller GmbH · Fernwartung: Drucker eingerichtet`.
  Du siehst sie auch in der Ansicht „Dokumentation“, in der Statuszeile
  („dokumentiert 3:10 h, abgerechnet 3:30 h“) und im Eintragen-Fenster neben der Dauer.
  Jede Tätigkeit wird für sich gerundet. Unter **Einstellungen → Abrechnung …** stellst du
  den Takt (Minuten) und die Rundung ein: „Angefangener Takt zählt“, „Auf den nächsten Takt
  runden“ oder „Ohne Takt“ (dann ist alles wie früher). Für einzelne Kunden kannst du
  einen anderen Takt oder eine andere Rundung festlegen.
- **PC-Verlauf automatisch löschen:** Auf Wunsch löscht Zeitzeuge die aufgezeichneten
  aktiven Fenster nach einer einstellbaren Zahl von Tagen (Standard: aus, sonst 90 Tage).
  Das gilt auch für den Fensterverlauf, den du von einem anderen PC übernommen hast.
  Deine Tätigkeiten, Buchungen, KI-Vorschläge, Anrufe und Verbindungen bleiben erhalten.
  Einschalten unter **Einstellungen → Datenspeicher → PC-Verlauf automatisch löschen …**.
  Beim Einschalten zeigt Zeitzeuge, wie viele Tage betroffen sind, und fragt nach.
  Danach löscht es beim Start (nach einer Minute) und einmal am Tag.

### Einrichtung (Abschnitt Einstellungen/Config)

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `billing_step_minutes` | `15` | Abrechnungstakt in Minuten |
| `billing_mode` | `"up"` | `"up"` angefangener Takt zählt, `"nearest"` nächster Takt, `"off"` ohne Takt |
| `billing_customers` | `{}` | Ausnahmen: `{"Müller GmbH": {"step": 30, "mode": "nearest"}}` |
| `pc_history_purge` | `false` | PC-Verlauf automatisch löschen |
| `pc_history_days` | `90` | so viele Tage behalten (7 bis 3650) |

## Eigene Entscheidungen

1. **Je Tätigkeit runden** (nicht die Summe je Tag/Kunde). Jede Zeile im Ticket steht für
   sich, und die Summe in der Statuszeile passt zu den Zeilen. Ein Ticket-Feld gibt es noch
   nicht (Agent B). Rückgängig/anders: `Billing.total_minutes` in `billing.py` (z. B. erst
   je Kunde summieren, dann `billed_minutes`).
2. **Gerechnet wird in ganzen Minuten**, Sekunden kaufmännisch gerundet (wie die Anzeige
   der Dauer). Sonst würde 15:20 min wegen 20 Sekunden zu 0:30 h. Rückgängig:
   `billing._minutes` durch `math.ceil(seconds / 60)` ersetzen.
3. **Mindesttakt:** Jede Tätigkeit > 0 zählt mindestens einen Takt, auch bei „nächster Takt“
   (5 min → 0:15 h). Im Modus „aus“ mindestens 1 min (wie bisher in der Anzeige).
   Ort: `billed_minutes` in `billing.py`.
4. **„Nächster Takt“ rundet bei genau halb auf** (7,5 → 15 bei 15-min-Takt; ganze Minuten:
   8 min → 15, 22 min → 15, 23 min → 30). Ort: `billed_minutes`.
5. **Kundennamen vergleichen ohne Groß/klein und doppelte Leerzeichen.** Ort: `billing._norm`.
6. **Format der Kopie:** `(12 min → abgerechnet 0:15 h)` im Kopf der Ticketzeile; abgerechnete
   Zeit immer als `H:MM h`. Im Modus „aus“ steht nichts dabei (Zeile wie bisher).
   `journal.ticket_line(item, billing=None)` ohne `billing` ist unverändert, z. B. beim
   Löschen-Dialog. Rückgängig: `billing=` in `app_daylist.copy_selection` und
   `app_docs.on_entry_action` weglassen oder `billing_mode: "off"`.
7. **Statuszeile:** „abgerechnet …“ erscheint nur, wenn mindestens eine Regel aktiv ist
   (`Billing.any_active`). Dokumentiert ist die zusammengeführte Zeit (wie bisher),
   abgerechnet die Summe je Tätigkeit. Ort: `app_daylist.update_status_text`.
8. **Für Matrix42 (später):** `billing.booking_span(item, billing)` / `booking_item` – Beginn
   bleibt (auf die Minute), Ende = Beginn + abgerechnete Dauer. Überschneidungen mit der
   nächsten Tätigkeit prüft die Funktion nicht – das muss der Buchungs-Code entscheiden.
9. **Icon „tag“** für den Menüeintrag „Abre&chnung …“ (Preisschild). Ort: `app_menus.py`.
10. **Einstellung PC-Verlauf in einem eigenen kleinen Dialog** (`retention_dialogs.py`) statt im
    Dialog „Fenster-Filter“: Der ist schon 820 px hoch, und settings_dialogs.py bleibt so
    unberührt. Menü: Untermenü „Daten&speicher“, erste Gruppe (jetzt 4 Einträge),
    „PC-&Verlauf automatisch löschen …“.
11. **Behalten werden heute und die letzten N Tage**, gelöscht wird alles mit Tag
    < heute − N (`retention.cutoff`). Erlaubt 7 bis 3650 Tage (`retention.MIN_DAYS/MAX_DAYS`).
12. **Rückfrage** auch, wenn bei eingeschaltetem Löschen die Frist verkürzt wird; nur, wenn
    tatsächlich etwas betroffen ist. Ort: `RetentionRunner.edit`.
13. **Ausführung:** eine Minute nach dem Start, danach stündliche Prüfung, ob heute schon
    gelöscht wurde. Gelöscht wird in Schritten von 5000 Zeilen (`retention.CHUNK`) über
    `QTimer` im Hauptthread – die Datenbank hat eine Verbindung mit Lock, ein eigener Thread
    würde die Fensteraufzeichnung genauso blockieren. Jeder Schritt ist eine eigene
    Transaktion (`Store.delete_rows_before(..., limit=)`); bricht es ab, ist nichts halb.
14. **Kein VACUUM.** Ein VACUUM kopiert die ganze Datei (Sekunden bei großer Datenbank, braucht
    doppelten Platz, sperrt alles). Der frei gewordene Platz wird für neue Zeilen
    wiederverwendet, die Datei wächst also nicht weiter. Stattdessen **`PRAGMA secure_delete`**
    während des Löschens: Gelöschte Seiten werden mit Nullen überschrieben, die (ohnehin
    verschlüsselten) Inhalte stehen danach nicht mehr in der Datei (Test
    `test_geloeschte_inhalte_ueberschrieben`). Rückgängig: Zeilen mit `secure_delete` in
    `datastore.delete_rows_before` entfernen.
15. **Übernommener PC-Verlauf** (Export/Import, `uebernommen`): Nur der Schlüssel `"pc"` der
    alten Tage wird entfernt (`ImportStore.drop_pc_before`), Verbindungen, Tätigkeiten,
    Buchungen und KI-Vorschläge des anderen PCs bleiben.
16. **Nicht angefasst:** Die alten Klartext-Dateien in `alt-<Datum>/` (aus der Migration) und
    die Sicherung der Datenbank im Datenordner. Die Sicherung wird beim nächsten Sichern
    überschrieben (Löschen zählt als Änderung). `alt-<Datum>/` sind Dateien, die der Nutzer
    bewusst behalten hat.

## Geänderte Dateien

Neu:
- `billing.py` – Logik Abrechnungstakt (ohne Qt), inkl. `booking_span`/`booking_item`.
- `billing_dialogs.py` – Dialog „Abrechnung“ (Takt, Rundung, Ausnahmen je Kunde).
- `retention.py` – Logik PC-Verlauf löschen (ohne Qt).
- `retention_dialogs.py` – Dialog „PC-Verlauf automatisch löschen“ und `RetentionRunner`.
- `tests/billing_test.py`, `tests/retention_test.py`.
- `docs/neu/abrechnung-datenschutz.md` (diese Datei).

Geändert (klein und lokal):
- `config_defaults.py` – Block „Abrechnung und Datenschutz“ am Ende des Dicts.
- `journal.py` – `ticket_line(item, billing=None)`: nur der Kopf mit Zeit/Dauer.
- `journal_dialogs.py` – `_EntryForm`: `billing`-Attribut, `set_billing()`, Kundenwechsel ruft
  `validate`, in `validate` „, abgerechnet 0:15 h“ hinter der Dauer; Import `hours_text`.
- `app_docs.py` – `billing()`; Kopieren mit Takt; `set_billing` an Eintragen-, Bearbeiten-
  und Nachfrage-Fenster.
- `app_daylist.py` – Spalte Dauer in der Ansicht „Dokumentation“, `copy_selection`, Statuszeile.
- `app_menus.py` – Eintrag „Abre&chnung …“ in der Gruppe Arbeitszeiten/Aktivitätstypen/KI,
  `edit_billing()`; im Untermenü „Datenspeicher“ „PC-&Verlauf automatisch löschen …“.
- `main_timeline.py` – Import und `self.retention = RetentionRunner(...)` am Ende von `__init__`.
- `datastore.py` – `Store.rows_before()`, `Store.delete_rows_before()`.
- `transfer.py` – `ImportStore.pc_days_before()`, `ImportStore.drop_pc_before()`.
- `tests/ui_audit_test.py` – Dialoge „Abrechnung“ und „PC-Verlauf löschen“, neue Dateien in
  der Prüfung auf graue Farben.
- `tests/journal_gui_test.py` – Prüfungen für Takt (Kopie, Liste, Statuszeile, Nachfrage,
  abschaltbar) und PC-Verlauf löschen (aus = nichts gelöscht).
