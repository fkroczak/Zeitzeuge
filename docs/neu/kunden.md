# Kunden: Kundenliste und Lernen aus Korrekturen (Agent A)

## README-Text

### Funktionsliste

- **Kundenliste: ein Kunde, alle Spuren.** Unter *Einstellungen → Kundenliste …* legst du
  Kunden an und ordnest ihnen ihre Spuren zu: TeamViewer-ID, RDM-Eintrag, VPN-Verbindung,
  Telefonnummer und E-Mail-Domain. Telefonnummern passen in jeder Schreibweise
  („+49 711 123456“ = „0711 123456“). Eine Domain wie „@kunde.de“ gilt auch für
  „mail.kunde.de“. Zeitzeuge schlägt den Kunden dann beim Eintragen und in der Nachfrage vor.
  In der Tagesliste steht er vor dem Namen der Verbindung („Müller GmbH · srv01“), in der
  Timeline im Hinweis. Eine Spur gehört immer genau einem Kunden.
- **Kunde zuordnen per Rechtsklick.** Hat eine Verbindung, ein Telefonat oder eine Mail noch
  keinen Kunden, wählst du im Rechtsklick-Menü *Kunde zuordnen …*. „TeamViewer-ID
  benennen …“ gibt es weiter, es landet in derselben Kundenliste.
- **Zeitzeuge lernt aus deinen Korrekturen.** Änderst du beim Eintragen den vorgeschlagenen
  Kunden, merkt Zeitzeuge ihn zur Spur („Kunde für RDM-Eintrag „srv01“ merken“ ist
  angehakt). Änderst du die Kategorie, bietet der Dialog „Als Regel merken: „srv01“ →
  Beratung“ an. Dieser Haken ist aus: Nur wenn du ihn setzt, entsteht eine Regel in der
  *Zuordnung ohne KI*. Sie steht vor den Standardregeln und schlägt beim nächsten Mal auch
  im Dialog die Kategorie vor. Doppelte Regeln legt Zeitzeuge nicht an.

### Datenschutz / Ablage (für den Abschnitt zur Datenbank)

Die Kundenliste ist Nutzdaten wie die TeamViewer-Namen: Sie steht verschlüsselt in der
Datenbank (Ablage „kunden“), nicht in `zeitzeuge_config.json`. Beim Export für einen
anderen PC (z. B. die PAW) geht sie mit; dort wird sie wie die TeamViewer-Namen nur gelesen.

## Eigene Entscheidungen

1. **Ablage in der Datenbank (Ablage „kunden“), im Speicher als `config["customers"]`.**
   Kundenzuordnungen sind Konfiguration, aber auch Nutzdaten (Kundennamen, Nummern). Seit der
   Datenbank liegen schon die TeamViewer-Namen verschlüsselt dort; die Kundenliste folgt
   demselben Weg (`load_config_with_defaults` / `save_config` in main_timeline.py,
   `CUSTOMERS_DOC = "kunden"`). Stand vorher eine Liste in der Config-Datei, wird sie
   einmal übernommen. Rückgängig: in main_timeline.py die beiden Blöcke „Kundenliste“ entfernen;
   dann stünde `customers` wieder in der Datei.
2. **`teamviewer_names` bleibt und wird gespiegelt statt migriert.** Jede TeamViewer-Spur der
   Liste steht auch in `teamviewer_names`, jede dort benannte ID erscheint in der Liste
   (`customers.customer_list`). Bei Widerspruch gilt `teamviewer_names` (das schreibt auch
   eine ältere Zeitzeuge-Version). So laufen alte Configs, Export/Import, die Timeline-Namen
   und „TeamViewer-ID benennen …“ unverändert. Rückgängig: `customer_list` ohne den Abgleich;
   `teamviewer_names` bleibt ohnehin unberührt.
3. **Eine Spur gehört genau einem Kunden.** Ordnest du sie neu zu, wird sie beim alten Kunden
   entfernt (`customers._assign`, Hinweis im Dialog). Sonst wäre der Vorschlag zufällig.
4. **Welche Felder eine Spur sind** (`customers.traces_of`): `tv_id`; `phone`/`number` oder
   „Name (Nummer)“ bei Telefonaten; `VPN-Verbindung` = VPN-Name (ohne `vpn_source` auch
   RDM-Eintrag, weil RDM VPN-Einträge kennt); RDM-Typen `<Protokoll>-Verbindung/-Sitzung` und
   Zugangsdaten = RDM-Eintrag; `email_domains`/`email` für neue Quellen (Agent C). Reihenfolge:
   TeamViewer, Telefon, RDM, VPN, Mail. Eigene Tätigkeiten, KI, Regeln und PC-Fenster haben
   keine Spur.
5. **3CX-Einträge bekommen ein Feld `phone`** (call_import.py, rein additiv). Alte Einträge
   ohne Feld gehen über „Name (Nummer)“.
6. **Anzeige in der Tagesliste „Müller GmbH · srv01“ statt `customer_name` zu ersetzen.**
   `customer_name` bleibt unverändert, weil `entry_key` (Ignorieren/Später fragen), die
   Regeln und der Export ihn nutzen. Nur die Spalte „Kunde / Verbindung“ und der
   Timeline-Hinweis („Kunde: …“) zeigen den Kunden. TeamViewer bleibt wie bisher (Name statt ID).
   Rückgängig: in app_daylist.py `customers.with_customer(a, index)` wieder durch
   `a.get("customer_name", "")` ersetzen; in timeline_only.py `_customer_line` entfernen.
7. **„Kunde merken“ bei anderen Spuren nur sichtbar, wenn du den Kunden änderst**, dann
   angehakt (wie bei TeamViewer). TeamViewer: wie bisher immer sichtbar. Abschaltbar mit
   `customers_learn: false` (dann nur TeamViewer wie bisher).
8. **Regel aus geänderter Kategorie als Checkbox im Dialog, standardmäßig aus**, nur sichtbar,
   wenn die Kategorie vom Vorschlag abweicht. Keine Meldung nach dem Speichern, weil die
   Nachfrage sich selbst schließt und dann nichts mehr blockieren soll. Abschaltbar mit
   `rules_learn_offer: false`.
9. **Form der gelernten Regel** (`learning.rule_for`): Feld „Kunde“ mit genauem Muster
   `re:^<Name>$` (ohne Groß/Klein), bei reinen Nummern oder unbenannter TeamViewer-ID das Feld
   „Typ“. Name „Gelernt: <Name>“, Merkmal `"learned": true`. Eingefügt nach früher gelernten
   und eigenen Regeln, vor der ersten Standardregel (`learning.add_rule`). Gleiche Bedingung:
   nichts Neues; gelernte mit anderer Kategorie wird angepasst.
10. **Gelernte Regeln schlagen im Dialog die Kategorie vor** (`learning.learned_category`),
    die Standardregeln nicht. Sonst würde sich der Vorschlag für alle ungefragt ändern.
    Rückgängig: in `learning.doc_hints` nur `suggest_category` nutzen.
11. **Export nimmt die Kundenliste mit** (`transfer.make_export(..., customers=)`, Schlüssel
    `kunden`, `ImportStore.customers()`); ein neuerer Export ersetzt die Liste des PCs. Alte
    Exporte ohne `kunden` gehen weiter. Rückgängig: Argument in app_transfer.py weglassen.
12. **CustomersMixin hängt an DocsMixin** (`class DocsMixin(CustomersMixin)`), damit die
    Klassenzeile in main_timeline.py nicht geändert werden muss (weniger Merge-Konflikte).
13. **Neues Icon „users“** (Lucide) in icons.py für „Kundenliste …“.
14. **Rechtsklick „Kunde &zuordnen …“** nur, wenn eine Spur erkennbar ist und noch kein Kunde
    passt (`entry_menu_items(entry, customer_known)`). Bei TeamViewer bleibt „TeamViewer-ID
    &benennen …“; beide schreiben in dieselbe Liste. Ändern eines bekannten Kunden geht über
    die Kundenliste.

## Geänderte Dateien

Neu:
- `customers.py` – Datenmodell, Normalisierung, Spuren eines Eintrags, Index, `customer_for`.
- `learning.py` – Regel aus Korrektur bauen/einsortieren, Vorschläge fürs Eintragen,
  Korrekturen anwenden.
- `customers_dialogs.py` – Dialog „Kundenliste“, `CustomersMixin` (Menü, Rechtsklick, Index).
- `tests/customers_test.py` (11 Tests, ohne Qt), `tests/customers_gui_test.py` (Skript mit
  Oberfläche), `docs/neu/kunden.md`.

Geändert (klein und lokal):
- `app_docs.py` – Importe, `DocsMixin(CustomersMixin)`, `known_customers` + Kundenliste,
  Befehl `assign_customer`, `add_doc`/`show_next_prompt` nutzen `learning.doc_hints`,
  `_save_doc(..., rule=)` mit `learning.apply_corrections`, `on_prompt_answered` reicht
  `wants_rule()` durch.
- `journal_dialogs.py` – nur Bereich Kunde/Kategorie in `_EntryForm`: Parameter `trace`,
  `rule_subject`, Checkbox „Kunde … merken“ verallgemeinert (Attribut heißt weiter
  `remember_tv`), neue Checkbox „Als Regel merken“, Methoden `remember_customer`/`wants_rule`;
  `EntryDialog`/`PromptWindow` mit optionalen Parametern (`customer`, `category`, `trace`,
  `rule_subject`) und `wants_rule()`.
- `journal.py` – `suggest_customer(entry, tv_names=None, customers=None)`.
- `app_daylist.py` – Spalte „Kunde / Verbindung“ mit Kunde; „TeamViewer-ID benennen“ über
  `customers.learn/forget`.
- `timeline_only.py` – `entry_menu_items(entry, customer_known=False)` mit „Kunde zuordnen …“,
  `exec_entry_menu` prüft die Kundenliste, Hinweis „Kunde: …“ (`_customer_line`).
- `app_menus.py` – „Kunden&liste …“ in der Gruppe Arbeitszeiten/Aktivitätstypen/KI (jetzt 4).
- `main_timeline.py` – `CUSTOMERS_DOC`, Laden/Speichern der Kundenliste in der Datenbank.
- `config_defaults.py` – Block „Kunden“ am Ende: `customers`, `customers_learn`,
  `rules_learn_offer`.
- `call_import.py` – Feld `phone` an Anruf-Einträgen.
- `transfer.py`, `app_transfer.py` – Kundenliste im Export, `ImportStore.customers()`.
- `icons.py` – Icon „users“.
- `tests/ui_audit_test.py` – Dialoge „Kundenliste“ und „Tätigkeit mit Lernen“.
