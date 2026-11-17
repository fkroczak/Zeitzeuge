# UI-Cookbook: Jedes Fenster gleich bauen

Stand 2026-11-17. Dieses Cookbook sagt, **welchen Baustein du für welches Element nimmst**.
Ziel: Ein Fenster sieht aus wie das andere. Wer ein Fenster kennt, kennt alle.

Was es schon gibt und hier nur verlinkt wird:

- Werte (Abstände, Schrift, Rundungen, Farben): [`DESIGN-TOKENS.md`](DESIGN-TOKENS.md)
- Prüfungen und Barrierefreiheit: [`quality-guardrails.md`](quality-guardrails.md)
- Aussehen aller Bausteine: `src/theme.py` (`STYLESHEET`)

**Grundregel:** Kein Fenster baut Kopf, Fuß, Knöpfe oder Abstände selbst. Du baust nur den
Inhalt. Den Rahmen setzt `card_dialog.modernize()`. Fehlt ein Baustein, ergänze ihn zentral
(in `card_dialog.py`, `theme.py` oder `icons.py`) und dann im Cookbook, nicht in einem einzelnen Fenster.

---

## 1. Welcher Fenstertyp?

| Du brauchst … | Typ | Baustein | Vorbild |
|---|---|---|---|
| Einstellungen für ein Thema (Formular) | **Karten-Dialog** | `QDialog` + `modernize()` | `outlook_dialogs.py` |
| Liste oder Tabelle bearbeiten | **Karten-Dialog groß** | `QDialog` + `modernize()`, Tabelle bekommt den Platz | `billing_dialogs.py`, `customers_dialogs.py` |
| Tätigkeit nachtragen/ändern | **Eintrag-Karte** | `journal_dialogs` (`entry_dialog`, `CardParts`) | „Tätigkeit nachtragen“ |
| Kurze Frage, Ja/Nein, Warnung | **Rückfrage** | `QMessageBox` mit eigenen Knopftexten | `day_close_dialog.py:427` |
| Hinweis ohne Entscheidung | **Hinweis** | `notices.py` (Karte/Leiste) oder Statuszeile | `notices.py` |
| Ein Schalter oder Wert in den Einstellungen | **Einstellungszeile** | Zeile in `settings_window.py` (`_Row`, `_switch`) | Einstellungen → Allgemein |
| Mehrere Schritte nacheinander | **Assistent** | Karten-Dialog + `QStackedWidget`, ◀ ▶ über `nav_icons()` | `day_close_dialog.py` (Blättern) |

Nicht verwenden: `QInputDialog` (sieht anders aus als alles andere, keine Karte), `QGroupBox`
(Rahmen um Gruppen widerspricht Regel 5 „Unnötiges weglassen“), eigene Kopf-/Fußleisten.

---

## 2. Rezept: Karten-Dialog

```python
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QVBoxLayout
from card_dialog import modernize
from settings_window import _guard_wheel


class BeispielDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Beispiel")          # = Titel im Kopf
        self.setMinimumWidth(560)                # Größe M, siehe Abschnitt 3
        layout = QVBoxLayout(self)

        form = QFormLayout()                     # Beschriftung kommt automatisch über das Feld
        self.minutes = QSpinBox()                # Zahl → immer QSpinBox (Abschnitt 5)
        self.minutes.setRange(1, 30)
        self.minutes.setSuffix(" min")
        self.minutes.setValue(int(config.get("x", 3)))
        _guard_wheel(self.minutes)               # Mausrad verstellt nicht beim Blättern
        form.addRow("&Dauer je Mail:", self.minutes)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        modernize(self, "Beispiel", "Ein Satz, was hier eingestellt wird.", "settings",
                  intro=False, scroll=True)
```

`modernize()` erledigt:

- **Kopf:** Icon-Kachel, Titel (`prompt_title`), Untertitel (`hint`).
- **Inhalt:** Rand 16 px, Formulare mit Beschriftung *über* dem Feld, Doppelpunkt weg.
- **Fuß:** leise Aktionen links, rechts `Abbrechen` und genau **eine** Hauptaktion (fett, Enter).
- Texte der Standardknöpfe: OK/Save → **Speichern**, Cancel → **Abbrechen**, Close → **Schließen**.

Parameter, die du brauchst (Details im Docstring von `modernize`):

| Parameter | Wofür |
|---|---|
| `scroll=True` | Formular länger als ~6 Zeilen: Inhalt blättert, Kopf und Fuß bleiben stehen |
| `primary=btn` | Hauptaktion ist nicht OK/Speichern (z. B. „Buchen“) |
| `left=(btn,)` | leise Aktion links unten (Zurücksetzen, Entfernen, Jetzt lesen) |
| `right=(btn,)` | zweite Aktion rechts neben Abbrechen |
| `head=(w,)` | Werkzeug rechts im Kopf (◀ ▶, „+ Neuer Kunde“) |
| `subtitle_label=lbl` | Untertitel, den der Dialog selbst ändert (Datum im Tagesabschluss) |

Knopf-Rollen im `QDialogButtonBox` bestimmen den Platz: `ResetRole`/`DestructiveRole` → links leise,
`AcceptRole` → Hauptaktion, `RejectRole` → Abbrechen, `ActionRole` → links.

---

## 3. Größen

| Name | Breite | Für |
|---|---|---|
| `S` | 480 px | eine Frage, 1–3 Felder (PIN, PC-Verlauf löschen) |
| `M` | 560 px | **Standard** für Formulare und Einstellungsdialoge |
| `L` | 720 px | Formular mit Tabelle oder langen Pfaden (Regeln, Ticket-Details) |
| `XL` | min. 900 × 480, Start mit `fit_screen()` | große Listen (Kundenliste, Tagesabschluss, Tickets) |

- Eintrag-Karten (Nachfrage, Tätigkeit) sind fest 600 px breit, wie die Nachfrage-Karte.
- Alles muss auf **960 × 540** passen (Full HD bei 200 %). Prüfen: `python tests/layout_check.py`.
- Höhe nie fest setzen. Lange Dialoge: `scroll=True`.

> Noch nicht als Konstanten in `theme.py`. Bis dahin die Zahlen oben verwenden;
> Vorschlag: `DIALOG_S/M/L` in `theme.py` ergänzen und überall einsetzen.

---

## 4. Kopf und Texte

- **Titel** = Aufgabe oder Thema, 1–3 Wörter: „Kundenliste“, „In Matrix42 buchen“. Gleich dem Fenstertitel und dem Menüeintrag.
- **Untertitel** = ein Satz, höchstens ~80 Zeichen. Was passiert hier? Längere Erklärung → Tooltip am Feld.
- **Icon** nur aus `icons.PATHS` (z. B. `settings`, `calendar`, `users`, `lock`, `tag`, `list`, `search`).
  Datenquellen bekommen ihr Quellen-Icon (`outlook`, `teams`, `pbx` …).
- Du-Form, kurze Sätze, Begriffe aus dem Glossar in `DESIGN-TOKENS.md`.
- Kein HTML für Hervorhebung (`<b>` in Labels). Überschriften über Objektnamen, siehe Abschnitt 6.

---

## 5. Formularelemente

Jedes Feld steht in einem `QFormLayout` mit Beschriftung `"&Text:"` (Alt-Buchstabe, eindeutig je Fenster).

| Wert | Widget | So einstellen |
|---|---|---|
| **Zahl** (Minuten, Tage, Sekunden) | `QSpinBox` | `setRange`, Einheit per `setSuffix(" min")`, ggf. `setPrefix("alle ")`, `_guard_wheel(spin)` aus `settings_window`. Pfeile ▲▼ kommen aus dem Theme, Tippen geht immer. **Nie** `QLineEdit` für Zahlen. |
| Uhrzeit | `QTimeEdit` | Format `HH:mm` |
| Datum | `QDateEdit` | `setCalendarPopup(True)` |
| Ja/Nein **im Dialog** | `QCheckBox` | Text beschreibt den An-Zustand: „Outlook &starten, wenn es nicht läuft“ |
| Ja/Nein **in Einstellungszeile/Liste** | Schalter `_switch(name)` (`QCheckBox#switch`) | Text „An“/„Aus“ |
| Unterpunkte eines Schalters | `QCheckBox` darunter | per `setEnabled` an den Hauptschalter koppeln (Muster `OutlookSettingsDialog._sync`) |
| Auswahl aus 2–3 | `QRadioButton` untereinander | |
| Auswahl aus mehr | `QComboBox` | |
| Kurzer Text | `QLineEdit` | Leer erlaubt? Platzhalter **„leer: …“** sagt, was dann gilt („leer: Standardkalender“) |
| Liste von Werten | `QPlainTextEdit` | Hinweis „Ein Eintrag je Zeile“ im Untertitel |
| Pfad/Datei | `QLineEdit` + Knopf „&Durchsuchen …“ in einer Zeile | |
| Farbe | Farbknopf (einzige erlaubte feste Farbe per `setStyleSheet`) | |

Erklärungen zum Feld: `setToolTip(...)`. Ein Satz, endet mit Punkt, nennt ein Beispiel („z. B. itm-gruppe.de“).

Fehler: Text direkt unter dem Feld (`QLabel#hint` bzw. Fehlerstil), Speichern sperren. Nie nur Farbe.

---

## 6. Inhalt gliedern

| Element | Baustein |
|---|---|
| Abschnittsüberschrift im Inhalt | `QLabel` mit `setObjectName("section_title")` |
| Grauer Hinweistext | `QLabel` mit `setObjectName("hint")`, `setWordWrap(True)` |
| Längerer Erklärtext | `QLabel` + `prose(label)` (Zeilenhöhe 1,5) |
| Hervorgehobener Kasten („Neu entdeckt“) | `QFrame#notice`, darin `QLabel#card_title` |
| Status (An/Aus/Fehler) | `QLabel#status_badge` mit Property `state` = `ok` / `warn` (ohne = aus), Muster `app_readers.py:226` |
| Link-artiger Knopf im Text | `QToolButton`/`QPushButton` mit `setObjectName("link")` |
| Leise Aktion | `QPushButton#quiet_button` (setzt `modernize` für Reset/Destructive selbst) |
| Werkzeugknopf mit Icon | `QToolButton#prompt_tool` + `setAccessibleName` |
| Chips/Filter | `QToolButton#chip` in `QWidget#chips` |
| Leerer Zustand | `hint`-Label mit Satz, was zu tun ist („Noch keine Regeln. Lege mit + die erste an.“) |

Abstände zwischen Elementen nur `SPACE_*`. Keine Leerzeilen-Labels, keine `addSpacing` mit freien Zahlen.

---

## 7. Tabellen und Listen

Jede Tabelle bekommt dieselben Grundeinstellungen:

```python
table.verticalHeader().setVisible(False)
table.setSelectionBehavior(QAbstractItemView.SelectRows)
table.setEditTriggers(QAbstractItemView.NoEditTriggers)   # Bearbeiten per Doppelklick → Dialog
table.setShowGrid(False)
table.horizontalHeader().setStretchLastSection(True)
```

- Spaltenköpfe linksbündig (setzt `AppStyle.polish`), normale Schreibung.
- Zahlen und Zeiten rechtsbündig, Text links.
- Aktionen zur Zeile: Knöpfe **über** der Tabelle (+, Bearbeiten, Entfernen) oder Rechtsklick-Menü,
  „Entfernen“ immer als leise Aktion und mit Rückfrage.
- Leere Tabelle: Hinweistext statt leerer Fläche.

> Vorschlag: `theme.standard_table(table)` mit den Zeilen oben, damit es nicht jede Datei neu schreibt.

---

## 8. Rückfragen

```python
box = QMessageBox(QMessageBox.Question, "Tagesabschluss", "Frage in einem Satz?", parent=self)
yes = box.addButton("&Buchen", QMessageBox.AcceptRole)      # Verb statt „Ja“
box.addButton("Abbrechen", QMessageBox.RejectRole)
fit_bold(yes)
box.setDefaultButton(yes)          # bei Löschen: Abbrechen als Standard
box.exec()
```

- Knopftexte sind Verben („Löschen“, „Buchen“, „Später“), nie „Ja“/„Nein“/„OK“.
- Bei Unumkehrbarem ist **Abbrechen** der Standardknopf.
- Fenstertitel = Name der Aufgabe, aus der gefragt wird.
- Reine Information nach einer Aktion: Statuszeile (`statusBar().showMessage(text, 8000)`) statt Meldungsfenster.

---

## 9. Verboten (prüft das Review)

- `QInputDialog` – stattdessen kleiner Karten-Dialog (Größe S).
- `QGroupBox` – stattdessen `section_title` plus Abstand.
- `setStyleSheet` mit Farben oder Abständen außerhalb von `theme.py` (Ausnahme: Nutzerfarben, HTML-Vorschau auf Papier).
- Feste Zahlen für Ränder (`setContentsMargins(16, 14, …)`) – nur `SPACE_*`.
- Eigene Kopf-/Fußleisten oder Knopfreihen – `modernize`/`move_to_foot`.
- `QLineEdit` für Zahlen, `setBold`/`setPointSize` für Titel, `<b>` in Labels.
- Knöpfe „OK“, „Ja“, „Nein“, „< Zurück“, „Weiter >“ – Verben bzw. ◀ ▶ mit `nav_icons`.
- Mehr als eine fette Hauptaktion je Fenster.

---

## 10. Checkliste für jedes neue oder geänderte Fenster

- [ ] Fenstertyp aus Abschnitt 1, Vorbild angesehen
- [ ] `modernize()` mit Titel, einem Satz Untertitel, Icon aus `icons.py`
- [ ] Breite S/M/L/XL, passt auf 960 × 540 (`tests/layout_check.py`)
- [ ] Jedes Feld mit Beschriftung und eindeutigem `&`-Buchstaben
- [ ] Zahlen als `QSpinBox` mit Einheit, leere Textfelder mit „leer: …“
- [ ] Genau eine Hauptaktion, Knöpfe mit Verben
- [ ] Hell **und** Dunkel angesehen
- [ ] Nur Tastatur: Tab-Reihenfolge, Enter = Hauptaktion, Esc = Abbrechen
- [ ] Neuer Dialog in `tests/card_dialogs_gui_test.py` (`builders`) eingetragen

---

## 11. Abweichungen heute (zum Angleichen)

Bestandsaufnahme 2026-11-17. Erledigte Zeilen streichen.

| Stelle | Abweichung | Angleichen an |
|---|---|---|
| `app_readers.py:220` 3CX/ITM/Matrix42 | eigener Kopf mit `section_title` + Badge, kein `modernize` | Karten-Dialog M, Badge in `head=` |
| `app_transfer.py:87` Export | eigener Aufbau, langer Erklärtext oben | Karten-Dialog M, Text kürzen → Untertitel + Tooltip |
| `app_transfer.py:215` Übernehmen | eigener Aufbau | Karten-Dialog M |
| `setup_wizard.py:227` Assistent | kein Kopf/Fuß, `QGroupBox`, `<b>`, „< Zurück“/„Weiter >“ | Karten-Dialog + `QStackedWidget`, `nav_icons` |
| `update_dialog.py:50` Update | eigener Aufbau, `setStyleSheet` am Balken | Karten-Dialog S, Balken-Stil nach `theme.py` |
| `settings_dialogs.py:105, 140, 217, 603, 649, 804` | `QGroupBox` | `section_title` |
| `app_daylist.py:201`, `app_readers.py:559`, `customers_dialogs.py:655, 872`, `settings_dialogs.py:292` | `QInputDialog` | kleiner Karten-Dialog S |
| `card_dialog.py:146`, `ticket_dialogs.py:61` | Kopfrand `16, 14` fest | `SPACE_L, SPACE_M` (eine Stelle für beide) |
| `ticket_dialogs.py:40` `_CardDialog` | zweite Kopf/Fuß-Implementierung neben `modernize` | gemeinsamen Baustein in `card_dialog.py` |
| Breiten 400, 440, 460, 520, 540, 580 | uneinheitlich | S 480 / M 560 / L 720 |
| `link`, `link_button`, `result_link` | drei Namen für Link-Knöpfe | einer: `link` |
| `tickets_dialogs.py:456`, `tickets_dialogs.py:147` | `setStyleSheet` im Dialog | Regel in `theme.py` |
| Tabellen in 6 Dateien | Grundeinstellungen je Datei verschieden | `standard_table()` (Abschnitt 7) |
