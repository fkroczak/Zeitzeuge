# Eintragen: Textbausteine, letzte Texte, Ticket-Format, Ticketnummer

## README-Text

### Für die Funktionsliste (Abschnitt Tätigkeiten dokumentieren)

- **Textbausteine:** Häufige Sätze wie „Windows-Updates installiert“ fügst du beim Eintragen
  mit **Text einfügen** (Alt+E) ein. Steht der Cursor am Ende einer Zeile, kommt der Baustein
  in eine neue Zeile. Die Bausteine 1 bis 9 wählst du im Menü direkt mit der Zahl.
  Die Liste pflegst du unter Einstellungen → **Textbausteine …**.
- **Zuletzt benutzte Texte:** Im selben Menü stehen die letzten Texte zum gewählten Kunden
  (aus den letzten 60 Tagen). Wechselst du den Kunden, wechseln auch die Vorschläge.
- **Ticket-Format „- “ / „-- “:** Auf Wunsch kopiert Zeitzeuge die Dokumentation im Format der
  Ticket-Doku: erste Zeile (oder erster Satz) als Haupttätigkeit „- …“, alle weiteren als
  Untertätigkeiten „-- …“. Das gilt für STRG + C in der Ansicht „Dokumentation“ und für
  „Kopieren“ im Rechtsklick-Menü. Einschalten unter Einstellungen → Textbausteine.
  Im Eintragen-Dialog gliedert **Text einfügen → Als Ticket-Doku gliedern** den Text sofort.
- **Ticketnummer als Vorschlag:** Zeitzeuge sucht in den Fenstertiteln (PC-Verlauf) und in
  den Matrix42-Buchungen rund um die Tätigkeit (5 Minuten davor und danach) nach
  Ticketnummern wie `TCK0000049374`. Die häufigste steht im Feld **Ticket** als Vorschlag,
  z. B. „Gefunden: TCK0000049374 (Outlook, 12 min)“. Erst mit **Übernehmen** (oder Auswahl
  in der Liste) landet sie in der Tätigkeit. Das Ticket erscheint dann in der Ansicht
  „Dokumentation“ und in der kopierten Ticketzeile. Im kleinen Nachfrage-Fenster erscheint
  das Feld nur, wenn etwas gefunden wurde.

### Für die Einrichtung

Einstellungen → **Textbausteine …**:

- **Bausteine:** ein Satz je Zeile. „Standardliste einsetzen“ holt die mitgelieferten zurück.
- **Zuletzt benutzte Texte zum gewählten Kunden anbieten:** an (Standard) oder aus.
- **Beim Kopieren als Ticket-Doku gliedern:** aus (Standard). An: „- “ / „-- “.
- **Ticketnummern erkennen:** ein Muster (regulärer Ausdruck) je Zeile. Standard `TCK\d+`
  (Matrix42). Weitere Beispiele: `Ticket #(\d+)` (die Klammer ist die Nummer). Leer = keine
  Vorschläge. Ein fehlerhaftes Muster wird mit Zeilennummer gemeldet, OK ist dann gesperrt.

## Eigene Entscheidungen

1. **Ein Knopf „Text einfügen ▾“ mit Menü statt Auswahlliste.** Eine Zeile, per Tastatur
   (Alt+E, dann Zahl) erreichbar, hält das Nachfrage-Fenster klein. Bausteine und letzte
   Texte in einem Menü (Abschnitte „Textbausteine“ / „Zuletzt zu <Kunde>“), höchstens
   5 Einträge je Gruppe, letzte Texte höchstens 5. Rückgängig: `_add_text_helpers` und
   `_fill_insert_menu` in `journal_dialogs.py`.
2. **Einfügeregel:** Cursor am Ende einer nicht leeren Zeile → neue Zeile; mitten im Text →
   mit Leerzeichen abgesetzt. Rückgängig/ändern: `snippets.insert`.
3. **Standardliste** (10 Sätze, siehe `snippets.DEFAULT_SNIPPETS`), ohne Kundendaten. Sie
   steht in der Config (`snippets`), nicht in der Datenbank, weil sie keine Nutzdaten enthält.
   Eine geleerte Liste bleibt leer. Rückgängig: Config-Schlüssel `snippets` löschen.
4. **Zuletzt benutzte Texte standardmäßig an** (`snippets_recent: true`): rein additiv im
   Menü, ändert nichts am Gespeicherten. Gelesen wird erst beim Öffnen des Menüs. Aus:
   Config `snippets_recent: false` bzw. Haken im Dialog.
5. **Ticket-Format:** Config `ticket_format` (`""` = wie bisher, `"dash"`). Standard aus.
   Bei „dash“ steht der gegliederte Text unter der Kopfzeile (Zeit, Kunde, Kategorie, Ticket),
   weil „- “ / „-- “ am Zeilenanfang stehen muss. Einzeilige Texte werden an Satzenden
   geteilt (nicht nach Abkürzungen wie „z. B.“, „inkl.“, „ggf.“); vorhandene Marken „- “,
   „-- “, „•“, „*“ und eingerückte Zeilen werden übernommen. Die Formatierung steckt in
   `tickets.format_ticket_text`; `journal.ticket_line` ruft sie nur auf (neuer Parameter
   `text_style`, Standard `""`). Rückgängig: Parameter entfernen.
6. **Ticket in der Ticketzeile** als weiterer Teil nach Kunde und Kategorie
   („Kunde · Kategorie · TCK…: Text“) und in der Doku-Ansicht vor der Kategorie. Tätigkeiten
   ohne Ticket sehen aus wie bisher. Rückgängig: `ticket_line` / `Journal.entries` in `journal.py`.
7. **Ticket nur gespeichert, wenn eines da ist** (`journal.add` entfernt ein leeres `ticket`).
   Alte Daten bleiben gleich, `_valid`/`load` unverändert.
8. **Ticket-Vorschlag:** ±5 Minuten Rand (`tickets.MARGIN_MINUTES`), sortiert nach Dauer
   im Zeitraum, Quellen Fenstertitel (Programmname) und Matrix42-Buchungen (Feld `ticket`
   und `title`). Muster ohne Groß-/Kleinschreibung, nicht mitten in Wörtern. Config
   `ticket_patterns` (Standard `["TCK\\d+"]`), leere Liste = aus.
9. **Nachfrage-Fenster:** Feld „Ticket“ nur bei einem Vorschlag (sonst eine Zeile weniger);
   im Dialog „Tätigkeit nachtragen/bearbeiten“ immer. Rückgängig: `show_ticket` in
   `PromptWindow.__init__`.
10. **Einstellungen im Dialog „Textbausteine und Ticket“ gebündelt** (Bausteine, letzte
    Texte, Ticket-Format, Muster), damit im Menü nur der zugewiesene Eintrag dazukommt.
11. **Icon „edit“** für den Menüeintrag (vorhandenes Icon aus `icons.py`).
12. Export/Import (`transfer.py`) nicht geändert: Bausteine stehen in der Config, das Ticket
    in den Tätigkeiten, die schon mitgehen.

## Geänderte Dateien

- Neu: `snippets.py`, `tickets.py`, `snippets_dialogs.py`, `tests/snippets_test.py`,
  `tests/tickets_test.py`, `docs/neu/eintragen.md`.
- `journal.py`: Import `format_ticket_text`; `add` speichert `ticket`; neue Methode
  `recent_items`; `entries` zeigt das Ticket; `ticket_line(item, text_style="")`.
- `journal_dialogs.py`: `_EntryForm` neue Keyword-Parameter (`snippets`, `recent_texts`,
  `ticket`, `ticket_suggestions`, `show_ticket`), Zeilen „Text einfügen“ und „Ticket“
  direkt unter dem Textfeld, `item()` mit `ticket`; `EntryDialog` und `PromptWindow` reichen
  `**form_options` durch.
- `app_docs.py`: Imports; `ticket_line` mit `ticket_format` beim Kopieren; `add_doc`,
  `edit_doc`, `show_next_prompt` übergeben `entry_form_options`; neue Methoden
  `entry_form_options`, `ticket_suggestions`, `edit_snippets` (vor „Nachfragen“).
- `app_daylist.py`: `copy_selection` übergibt `ticket_format`.
- `app_menus.py`: Eintrag „Text&bausteine …“ nach „&Nachfragen und Erinnerungen …“.
- `config_defaults.py`: Block „Eintragen“ am Ende (`snippets`, `snippets_recent`,
  `ticket_format`, `ticket_patterns`), Imports `snippets`, `tickets`.
- `tests/ui_audit_test.py`: Dialoge „Tätigkeit mit Ticket-Vorschlag“, „Nachfrage mit
  Ticket-Vorschlag“, „Textbausteine“; Farbprüfung auch für `snippets_dialogs.py`,
  `journal_dialogs.py`.
- `tests/journal_gui_test.py`: Prüfung Ticket-Format beim Kopieren, Menü, Einfügen,
  Gliedern, Ticket übernehmen.
