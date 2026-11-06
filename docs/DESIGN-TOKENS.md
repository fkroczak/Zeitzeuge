# Design-Tokens, Glossar und gekürzte Texte

Stand 2026-11-06. Alle Werte stehen in `src/theme.py`. Qt kennt keine CSS-Variablen: Python
nutzt die Konstanten, das Stylesheet die Platzhalter (`$space_m`, `$fs_sm`, `$radius_card` …),
die beim Import ersetzt werden (`SIZE_TOKENS`). Farben bleiben je Design in `THEMES`
(`$text`, `$surface` …, ersetzt in `apply_style`). Entscheidungen: [`ENTSCHEIDUNGEN.md`](ENTSCHEIDUNGEN.md).

## Festgelegte Tokens

### Abstände (px, feste Skala)

| Konstante | QSS | px | Wofür |
|---|---|---|---|
| `SPACE_XS` | `$space_xs` | 4 | Titel → Beschreibung, eng Zusammengehöriges |
| `SPACE_S` | `$space_s` | 8 | Elemente einer Gruppe; **Standard-Abstand** aller Layouts |
| `SPACE_M` | `$space_m` | 12 | Gruppen; **Standard-Rand** aller Layouts; kleine Karten innen |
| `SPACE_L` | `$space_l` | 16 | Dialoge und Karten innen |
| `SPACE_XL` | `$space_xl` | 24 | zwischen Bereichen, Seitenrand oben/unten |
| `SPACE_2XL` | `$space_2xl` | 32 | Seitenrand links/rechts (Einstellungen) |
| `SPACE_3XL` | `$space_3xl` | 48 | leere Zustände (noch ungenutzt) |

Layouts ohne eigene Werte bekommen Rand `SPACE_M` und Abstand `SPACE_S` über
`AppStyle.pixelMetric` (bisher Fusion: 9–11 / 6 px).

**Abgeleitete Werte (bleiben bewusst):** Innenabstände von Bedienelementen im QSS
(`padding: 5px 8px` Felder, `6px 14px` Knöpfe, `2px 10px` Chips) und ihre Fokus-Ausgleiche
(`5px 13px`, `3px 5px`, `1px 9px`, `1px 3px`): Der Fokusrand ist 2 px statt 1 px, das Padding
wird um 1 px kleiner, damit nichts springt. Eine Rundung auf die Skala würde die Höhe aller
Felder und Knöpfe ändern.

### Schrift (px)

| Konstante | QSS | px | Wofür |
|---|---|---|---|
| `FONT_SM` | `$fs_sm` | 12 | Spaltenköpfe, Kennzahl-Beschriftung, Zähler, Menü-Überschriften, Beispiele |
| `FONT_BASE` | `$fs_base` | 13 | Grundschrift |
| `FONT_LG` | `$fs_lg` | 14 | Abschnitts- und Dialogtitel (`#section_title`) |
| `FONT_XL` | `$fs_xl` | 20 | Seitentitel (`#page_title`), große Kennzahlen (`#kpi_value`, `#rate_value_*`) |

Gewichte nur `normal` und `bold`. Zeilenhöhe Fließtext 1,5 (`PROSE_LINE_HEIGHT`, `theme.prose`).
Ausnahme Grafik: Die Timeline zeichnet mit `ui_font(8)` (8 pt ≈ 11 px) – Zeichengeometrie, kein Layout.

Warum nicht 12/14/16/20/24 wie im Auftragsbeispiel: Die Grundschrift 13 → 14 px hätte jedes
Fenster verbreitert, Mindestgrößen gesprengt (960 × 540) und die Optik spürbar verändert.
Vier Größen erfüllen „höchstens 4–5“.

### Rundungen (px)

| Konstante | QSS | px | Wofür |
|---|---|---|---|
| `RADIUS_SM` | `$radius_sm` | 4 | Häkchen, Menüzeilen |
| `RADIUS` | `$radius` | 6 | Felder, Knöpfe, Listeneinträge, Tooltips |
| `RADIUS_CARD` | `$radius_card` | 10 | Karten, Kacheln, Tabellen, Timeline, Menüs, Avatar |
| `RADIUS_CHIP` | `$radius_chip` | 11 | Chips (Pille bei 22 px Höhe) |

Komponenten-intern bleiben 3 px (Scrollbalken, 6 px breit) und 2 px (Fortschrittsbalken).

### Rahmen, Schatten

Rahmen 1 px (`$border` für Flächen, `$control` für Bedienelemente, mind. 3 : 1), Fokus 2 px
`$accent`, Navigation 3 px Akzentkante. Schatten: keine (bewusst, flaches Design).

### Farben

Unverändert in `THEMES` (Hell und Dunkel, je 45 Tokens). Neu: `tip`, `tiptext`, `tipborder`
für Hinweise (QToolTip und Timeline-Tooltip, in beiden Designs dunkel, Kontrast ≈ 17 : 1).
Kontrast aller Textfarben ≥ 4,5 : 1 prüft `tests/ui_audit_test.py`.

## Glossar der UI-Begriffe

| Begriff | So schreiben | Nicht |
|---|---|---|
| Matrix42 | Matrix42 | M42, Ticketsystem (nur in Beispielen für fremde Systeme) |
| Kundenliste | Kundenliste (Menü, Fenster) | Kunden & Erkennung |
| Tätigkeit | eine dokumentierte Arbeit | Eintrag (= Zeile der Tagesliste) |
| Eintrag | Zeile der Tagesliste / Timeline | Tätigkeit |
| Datenquelle | TeamViewer, RDM, VPN, 3CX … | Quelle allein nur im Kontext |
| Logdatei | Logdatei, Logdateien | Log-Datei |
| Aufzeichnung | Mitschreiben der aktiven Fenster | Mitschnitt (= Mitschnitt von Webanfragen für die Fehlersuche) |
| Infobereich | Infobereich | Taskleiste, Tray |
| Einstellungen | Einstellungen | Optionen |
| Mail | Mail, Mail-Domain | Email; E-Mail nur in festen Kategorien („E-Mail / Kommunikation“) |
| Personalzeit | Zeiten aus ITM | Arbeitszeit (= eingestellte Soll-Zeiten) |
| KI-Vorschläge | Vorschläge von Claude | KI-Einträge |
| Zuordnung ohne KI | feste Regeln, Zeile „Zuordnung o. KI“ | Regeln allein (alter Name) |

## Gekürzte und vereinheitlichte Texte (alt → neu)

| Stelle | alt | neu |
|---|---|---|
| `customers_dialogs.py` Fenstertitel und Überschrift | Kunden & Erkennung | Kundenliste |
| `app_daylist.py` Statuszeile | M42 | Matrix42 |
| `settings_dialogs.py` Regeln, Hinweis | Zuordnung ohne KI: Feste Regeln ordnen Verbindungen, Telefonate und Fenster einer Kategorie und einem Kunden zu, z. B. Outlook → „E-Mail / Kommunikation“. Das Ergebnis steht in der Timeline in der Zeile „Zuordnung o. KI“. Die erste passende Regel gewinnt, Wichtiges steht also oben. Verbindungen und Telefonate gehen immer vor PC-Fenstern. | Feste Regeln ordnen Verbindungen, Telefonate und Fenster einer Kategorie und einem Kunden zu, z. B. Outlook → „E-Mail / Kommunikation“. Ergebnis: Zeile „Zuordnung o. KI“. Die erste passende Regel gilt, Wichtiges also nach oben. Verbindungen und Telefonate gehen vor PC-Fenstern. |
| `settings_dialogs.py` KI, Einleitung | Zeitzeuge schickt die Einträge eines Tages an Claude von Anthropic. Zurück kommen Tätigkeiten mit Kunde, Kategorie und einem Satz fürs Ticket. Sie stehen in der Timeline in der Zeile „KI“ und in der Tagesliste unter „KI-Vorschläge“. … Gesendet wird nur, wenn du es anstößt (F6), und nur, wenn sich der Tag geändert hat. Ein Tag kostet meist wenige Cent. | Zeitzeuge schickt die Einträge eines Tages an Claude (Anthropic). Zurück kommen Tätigkeiten mit Kunde, Kategorie und einem Satz fürs Ticket: Zeile „KI“ in der Timeline, „KI-Vorschläge“ in der Tagesliste. … Gesendet wird nur auf Wunsch (F6) und nur, wenn sich der Tag geändert hat. Meist wenige Cent pro Tag. |
| `day_close_dialog.py` Einleitung | Zeitzeuge hat den Tag aus Verbindungen, Telefonaten, KI-Vorschlägen, Regeln und PC-Aktivität zu Blöcken je Kunde zusammengestellt. Prüfe die angehakten Zeilen, ändere Kunde, Ticket oder Text per Doppelklick und bestätige unten einmal für alle. Gebucht wird mit Status „Neu“, freigeben kannst du danach in Matrix42. | Der Tag als Blöcke je Kunde, aus Verbindungen, Telefonaten, KI-Vorschlägen, Regeln und PC-Aktivität. Angehakte Zeilen prüfen, per Doppelklick Kunde, Ticket oder Text ändern, unten einmal für alle bestätigen. Gebucht wird mit Status „Neu“, freigeben wie gewohnt in Matrix42. |
| `journal_dialogs.py` Nachfragen, Einleitung | Hat Zeitzeuge eine Tätigkeit erkannt, die du noch nicht dokumentiert hast, fragt es kurz nach: „Was hast du gemacht?“. So fehlt am Ende des Tages nichts im Ticket. Was zur selben Arbeit gehört (gleicher Kunde, gleiche Zeit), fragt es nur einmal ab. | Erkennt Zeitzeuge eine Tätigkeit ohne Dokumentation, fragt es nach: „Was hast du gemacht?“. So fehlt abends nichts im Ticket. Was zusammengehört (gleicher Kunde, gleiche Zeit), fragt es nur einmal ab. |
| `app_transfer.py` Daten übernehmen | Übernimm hier einen Export vom anderen PC (Datei oder Text aus der Zwischenablage). Die Daten erscheinen zusammen mit den Daten dieses PCs in Timeline und Tagesliste. | Export vom anderen PC übernehmen (Datei oder Text aus der Zwischenablage). Die Daten erscheinen zusammen mit denen dieses PCs in Timeline und Tagesliste. |
| `m42_booking_dialogs.py` (neu) | – | ⚠ Vielleicht gebucht: unklar, ob gebucht wurde (…). Bitte zuerst in Matrix42 nachsehen. |

Weitere Kandidaten zum Kürzen (nicht geändert, Inhalt nötig): Export-Erklärung in
`app_transfer.py:91` (553 Zeichen), Fenster-Filter-Hinweise in `settings_dialogs.py:498/531`.

## Neue Regeln für künftige Änderungen

- Ränder und Abstände nur mit `SPACE_*` (Python) bzw. `$space_*` (QSS); 0 bleibt 0.
- Schriftgrößen nur über Objektnamen (`#section_title`, `#page_title`, `#kpi_label` …), nie `setBold`/`setPointSize` für Titel, kein `<h3>`.
- Rundungen nur `$radius_sm`/`$radius`/`$radius_card`/`$radius_chip`.
- Kein `setStyleSheet` mit festen Farben außerhalb von `theme.py` (Ausnahme: Nutzerfarben wie der Farbknopf).
- Neue Fenster mit `python tests/layout_check.py` prüfen: kein abgeschnittener Text, keine horizontale Scrollleiste, passt auf 960 × 540.

---

# Anhang: Bestandsaufnahme vor der Umstellung

Erhoben per Skript (Regex und `ast`) über `src/*.py` auf dem Stand `39cea55` (main vor dem
Audit). Zeilennummern beziehen sich auf diesen Stand.

## A7. Struktur von theme.py (vorangestellt, da Basis für alle Vorschläge)

| Element | Zeile | Inhalt |
|---|---|---|
| `AppStyle(QProxyStyle)` | 17–71 | Fusion-Basis; `pixelMetric`: `PM_ToolBarExtensionExtent = 26`; `sizeFromContents` (SpinBox Qt5-Größe); `polish` (Header linksbündig); `drawControl` Rubber-Band-Linie `QColor(85,85,85,179)`, Pen 2 px, Dash [2,2]; `styleHint` WinLayout-Dialogknöpfe. **Hier ließen sich Layout-Defaults (`PM_LayoutLeftMargin`, `PM_LayoutHorizontalSpacing` …) zentral auf die Skala setzen.** |
| `install_translator`, `GERMAN` | 74–83 | Locale, nicht stilrelevant |
| `THEMES = {"dark": {...}, "light": {...}}` | 96–127 | 42 Tokens je Modus, flaches dict, Hex-Strings. Gruppen: Grund (`bg surface bar border text muted alt line handle control`), Interaktion (`accent onaccent hover pressed sel seltext primary onprimary`), Band/Toolbar (`band bandtext bandhover bandpressed`), Timeline (`now`), Chips (`chip chiptext`), Status (`good`), Buchungsquote (`rate_low/_mid/_ok/_over` + `_text`, `rate_value_low/_mid/_ok`). Doku der Tokens als Kommentar 85–95. |
| `RADIUS = 6`, `RADIUS_CARD = 10`, `RADIUS_CHIP = 11` | 130–132 | nur Python-Konstanten; QSS schreibt `6px/10px/11px` literal; Grep: nirgends importiert |
| `FONT_FAMILIES`, `FONT_CSS` | 136–137 | Segoe UI Variable Text → … → sans-serif; `FONT_CSS` wird per `.replace("$font", FONT_CSS)` beim Modulimport ins QSS gesetzt |
| `ui_font(point_size, bold)` | 140–144 | QFont in **Punkt** für Timeline |
| `PROSE_LINE_HEIGHT = 150`, `prose(label)` | 148, 161–174 | Rich-Text `<p style="line-height:150%; margin:0">` |
| `fit_bold(button)` | 151–158 | setzt **Inline** `QPushButton { min-width: Npx }` (+36 px) – dynamisch, bleibt |
| `STYLESHEET` | 176–361 | Ein großer `"""…"""`-String, **kein f-string, kein `string.Template`**: Platzhalter `$name`. `$font` wird sofort (Z. 361) ersetzt, alle anderen in `app_menus.py:807–826 apply_style()` per `str.replace`, **Schlüssel nach Länge absteigend sortiert** (`$bandtext` vor `$band`), plus `$checkmark` (PNG-Pfad aus `icons.check_mark_file(theme["onaccent"])`). |
| `readable_on(color)` | 364–375 | WCAG-Kontrast → `#FFFFFF` oder `#14181D` |

**Hell/Dunkel-Umschaltung**: `config["dark_mode"]` (bool) → `self.dark_mode`; `toggle_dark_mode` (`app_menus.py:801`) speichert und ruft `apply_style()`: Token-Ersetzung, `setStyleSheet("")`, `QPalette` aus Tokens (Window/Base/Text/Highlight/Accent …, `app_menus.py:813–823`), `setStyleSheet(sheet)` auf dem Hauptfenster, Icons neu einfärben, Einstellungsfenster neu aufbauen, `busy_bar.set_color(muted)`, `timeline.set_dark_mode()` → `timeline_only.py:591–605 init_timeline_colors()` liest `THEMES[...]` direkt. Weitere direkte `THEMES[...]`-Leser: `app_menus.py:234/249/289/347/539`, `app_tray.py:85`, `customers_dialogs.py:181`, `settings_window.py:546`, `week_dialogs.py:185`, `timeline_only.py:1452`. Hinweis: das Sheet hängt am Hauptfenster (nicht `QApplication`); Dialoge erben es als Kinder.

**Selektoren im QSS** (nur `#objectName` + Pseudozustände, **keine Property-Selektoren**):
- Toolbar/Status: `#tools #fixed #main_toolbar #qt_toolbar_ext_button #busy_text #cta #cta_secondary`
- Texte: `#hint` (51× gesetzt!), `#page_title` (20px bold), `#section_title` (14px bold), `#card_title`, `#row_title`, `#row_page`, `#row_value`, `#kpi_label`, `#kpi_value`, `#menu_header`, `#count`, `#example` (Monospace 12px), `#good` (**nirgends gesetzt**)
- Container: `#card #card_row #tile #notice #setting_row #divider #chips #customer_detail`
- Bedienelemente: `#chip #chip_add #link #switch #result_link #avatar #settings_nav #nav_list #view_menu`
- Buchungsquote: `#rate_low/_mid/_ok/_over` (QToolButton+QLabel), `#rate_value_low/_mid/_ok/_over/_none`
- Gesetzt, aber ohne QSS-Regel: `settings_page`, `source`, `busy_bar`, `settings_window`, `band_row` (letzteres per Inline-Sheet).

## A1. Abstände

### 1a. Layout-Aufrufe (Python)
**setContentsMargins**

| Wert | n | Fundstellen |
|---|---|---|
| `setContentsMargins(0, 0, 0, 0)` | 9 | app_menus.py:66, customers_dialogs.py:229, customers_dialogs.py:275, flow_layout.py:12, journal_dialogs.py:52, main_timeline.py:542, main_timeline.py:572, settings_window.py:564, settings_window.py:678 |
| `setContentsMargins(12, 10, 12, 10)` | 3 | customers_dialogs.py:71, customers_dialogs.py:285, journal_dialogs.py:470 |
| `setContentsMargins(14, 10, 14, 10)` | 3 | customers_dialogs.py:357, day_summary.py:129, day_summary.py:178 |
| `setContentsMargins(28, 20, 28, 20)` | 2 | settings_window.py:626, settings_window.py:738 |
| `setContentsMargins(8, 8, 8, 8)` | 2 | customers_dialogs.py:210, main_timeline.py:564 |
| `setContentsMargins(0, 0, 6, 0)` | 1 | day_summary.py:307 |
| `setContentsMargins(12, 10, 12, 12)` | 1 | settings_preview.py:171 |
| `setContentsMargins(14, 12, 14, 12)` | 1 | settings_window.py:469 |
| `setContentsMargins(16, 12, 16, 12)` | 1 | settings_window.py:567 |
| `setContentsMargins(16, 14, 16, 14)` | 1 | customers_dialogs.py:236 |
| `setContentsMargins(16, 16, 16, 12)` | 1 | customers_dialogs.py:189 |
| `setContentsMargins(16, 16, 16, 16)` | 1 | customers_dialogs.py:323 |
| `setContentsMargins(28, 20, 28, 8)` | 1 | settings_window.py:634 |
| `setContentsMargins(28, 4, 28, 20)` | 1 | settings_window.py:636 |
| `setContentsMargins(4, 0, 4, 0)` | 1 | busy_bar.py:99 |
| `setContentsMargins(4, 10, 4, 10)` | 1 | settings_window.py:323 |
| `setContentsMargins(4, 2, 4, 2)` | 1 | customers_dialogs.py:451 |
| `setContentsMargins(4, 6, 4, 6)` | 1 | day_summary.py:304 |
| `setContentsMargins(8, 8, 8, 0)` | 1 | day_summary.py:247 |

**setSpacing**

| Wert | n | Fundstellen |
|---|---|---|
| `.setSpacing(0)` | 7 | customers_dialogs.py:276, customers_dialogs.py:459, main_timeline.py:543, main_timeline.py:573, settings_window.py:565, settings_window.py:582, settings_window.py:679 |
| `.setSpacing(12)` | 5 | customers_dialogs.py:72, customers_dialogs.py:190, customers_dialogs.py:204, settings_window.py:324, settings_window.py:657 |
| `.setSpacing(6)` | 5 | day_summary.py:184, journal_dialogs.py:471, journal_dialogs.py:576, settings_preview.py:172, settings_window.py:470 |
| `.setSpacing(4)` | 4 | app_menus.py:67, customers_dialogs.py:79, settings_window.py:627, settings_window.py:635 |
| `.setSpacing(8)` | 4 | busy_bar.py:100, customers_dialogs.py:452, day_summary.py:135, day_summary.py:248 |
| `.setSpacing(2)` | 3 | day_summary.py:130, day_summary.py:179, settings_window.py:330 |
| `.setSpacing(10)` | 2 | customers_dialogs.py:237, settings_dialogs.py:268 |

**setHorizontalSpacing / setVerticalSpacing**

| Wert | n | Fundstellen |
|---|---|---|
| `setHorizontalSpacing(12)` | 2 | app_protect.py:261, journal_dialogs.py:476 |
| `setHorizontalSpacing(14)` | 1 | settings_dialogs.py:278 |
| `setVerticalSpacing(14)` | 1 | view_help.py:80 |
| `setVerticalSpacing(4)` | 1 | journal_dialogs.py:477 |
| `setVerticalSpacing(6)` | 1 | settings_dialogs.py:279 |

**addSpacing**

| Wert | n | Fundstellen |
|---|---|---|
| `addSpacing(8)` | 3 | day_summary.py:191, day_summary.py:193, settings_window.py:655 |
| `addSpacing(10)` | 1 | settings_window.py:644 |
| `addSpacing(12)` | 1 | settings_window.py:665 |
| `addSpacing(24)` | 1 | settings_window.py:571 |

### 1b. QSS padding / margin / spacing
**padding – theme.py**

| Wert | n | Fundstellen |
|---|---|---|
| `padding: 6px 8px` | 5 | theme.py:178, theme.py:186, theme.py:280, theme.py:301, theme.py:358 |
| `padding: 2px 8px` | 3 | theme.py:199, theme.py:228, theme.py:277 |
| `padding: 4px` | 3 | theme.py:211, theme.py:267, theme.py:357 |
| `padding: 0` | 2 | theme.py:180, theme.py:335 |
| `padding: 1px 9px` | 2 | theme.py:342, theme.py:346 |
| `padding: 2px 10px` | 2 | theme.py:339, theme.py:344 |
| `padding: 2px 12px` | 2 | theme.py:231, theme.py:234 |
| `padding: 5px 8px` | 2 | theme.py:203, theme.py:324 |
| `padding-left: 6px` | 1 | theme.py:272 |
| `padding-right: 6px` | 1 | theme.py:207 |
| `padding: 0 6px` | 1 | theme.py:256 |
| `padding: 12px 8px 8px 8px` | 1 | theme.py:255 |
| `padding: 1px 3px` | 1 | theme.py:349 |
| `padding: 2px 0` | 1 | theme.py:229 |
| `padding: 2px 4px` | 1 | theme.py:347 |
| `padding: 3px 10px` | 1 | theme.py:250 |
| `padding: 3px 5px` | 1 | theme.py:218 |
| `padding: 3px 8px` | 1 | theme.py:198 |
| `padding: 4px 28px 4px 12px` | 1 | theme.py:298 |
| `padding: 4px 8px` | 1 | theme.py:182 |
| `padding: 5px 13px` | 1 | theme.py:219 |
| `padding: 6px 0` | 1 | theme.py:308 |
| `padding: 6px 10px` | 1 | theme.py:309 |
| `padding: 6px 14px` | 1 | theme.py:213 |
| `padding: 6px 28px 6px 12px` | 1 | theme.py:268 |
| `padding: 8px 12px` | 1 | theme.py:322 |
| `padding: 8px 12px 2px 12px` | 1 | theme.py:300 |

**padding – Inline (außerhalb theme.py)**

| Wert | n | Fundstellen |
|---|---|---|
| `padding: 8px 10px` | 1 | timeline_only.py:627 |

**margin – theme.py**

| Wert | n | Fundstellen |
|---|---|---|
| `margin: 0` | 2 | theme.py:285, theme.py:286 |
| `margin: 6px 6px` | 2 | theme.py:179, theme.py:194 |
| `margin-top: 1.4em` | 1 | theme.py:254 |
| `margin: 0 2px` | 1 | theme.py:289 |
| `margin: 1px 0` | 1 | theme.py:358 |
| `margin: 1px 6px` | 1 | theme.py:309 |
| `margin: 2px 0` | 1 | theme.py:288 |
| `margin: 2px 4px` | 1 | theme.py:199 |
| `margin: 4px 0` | 1 | theme.py:271 |
| `margin:0` | 1 | theme.py:169 |

**spacing – theme.py**

| Wert | n | Fundstellen |
|---|---|---|
| `spacing: 4px` | 1 | theme.py:178 |
| `spacing: 6px` | 1 | theme.py:315 |
| `spacing: 8px` | 1 | theme.py:259 |

## A2. Feste Größen
**setFixed***

| Wert | n | Fundstellen |
|---|---|---|
| `setFixedWidth(20)` | 2 | customers_dialogs.py:75, customers_dialogs.py:288 |
| `setFixedHeight(26 + self.LIST_ROWS * 24 + 4)` | 1 | settings_preview.py:198 |
| `setFixedHeight(3)` | 1 | busy_bar.py:22 |
| `setFixedHeight(4)` | 1 | day_summary.py:155 |
| `setFixedHeight(70)` | 1 | snippets_dialogs.py:47 |
| `setFixedHeight(80)` | 1 | journal_dialogs.py:145 |
| `setFixedHeight(90)` | 1 | m42_booking_dialogs.py:135 |
| `setFixedHeight(self.TIMELINE_HEIGHT)` | 1 | settings_preview.py:183 |
| `setFixedSize(16, 16)` | 1 | busy_bar.py:57 |
| `setFixedSize(30, 30)` | 1 | customers_dialogs.py:455 |
| `setFixedSize(40, 40)` | 1 | customers_dialogs.py:241 |
| `setFixedWidth(1)` | 1 | day_summary.py:190 |
| `setFixedWidth(240)` | 1 | settings_window.py:586 |
| `setFixedWidth(280)` | 1 | customers_dialogs.py:208 |
| `setFixedWidth(8)` | 1 | day_summary.py:322 |

**setMinimum***

| Wert | n | Fundstellen |
|---|---|---|
| `setMinimumWidth(560)` | 7 | billing_dialogs.py:42, journal_dialogs.py:448, m42_booking_dialogs.py:29, m42_booking_dialogs.py:301, protect_dialogs.py:39, protect_dialogs.py:93, settings_dialogs.py:494 |
| `setMinimumWidth(520)` | 5 | app_readers.py:199, app_transfer.py:89, app_transfer.py:217, protect_dialogs.py:150, snippets_dialogs.py:17 |
| `setMinimumWidth(480)` | 3 | journal_dialogs.py:433, journal_dialogs.py:692, retention_dialogs.py:27 |
| `setMinimumWidth(460)` | 2 | journal_dialogs.py:523, timeline_only.py:409 |
| `setMinimumWidth(540)` | 2 | outlook_dialogs.py:24, settings_dialogs.py:408 |
| `setMinimumHeight(0)` | 1 | settings_preview.py:106 |
| `setMinimumHeight(160)` | 1 | snippets_dialogs.py:27 |
| `setMinimumHeight(180)` | 1 | m42_booking_dialogs.py:321 |
| `setMinimumHeight(200)` | 1 | timeline_only.py:573 |
| `setMinimumHeight(220)` | 1 | settings_dialogs.py:673 |
| `setMinimumHeight(28 * 7 + 40)` | 1 | week_dialogs.py:232 |
| `setMinimumHeight(90)` | 1 | week_dialogs.py:245 |
| `setMinimumHeight(low)` | 1 | timeline_only.py:1340 |
| `setMinimumHeight(self.code.sizeHint()` | 1 | protect_dialogs.py:50 |
| `setMinimumHeight(text.heightForWidth(self.minimumWidth()` | 1 | protect_dialogs.py:176 |
| `setMinimumSize(620, 480)` | 1 | setup_wizard.py:218 |
| `setMinimumSize(620, 560)` | 1 | view_help.py:69 |
| `setMinimumSize(720, 480)` | 1 | settings_window.py:545 |
| `setMinimumSize(900, 480)` | 1 | day_close_dialog.py:55 |
| `setMinimumSize(980, 680)` | 1 | customers_dialogs.py:183 |
| `setMinimumWidth(110)` | 1 | settings_dialogs.py:305 |
| `setMinimumWidth(220)` | 1 | customers_dialogs.py:105 |
| `setMinimumWidth(40)` | 1 | day_summary.py:86 |
| `setMinimumWidth(400)` | 1 | settings_dialogs.py:167 |
| `setMinimumWidth(580)` | 1 | settings_dialogs.py:39 |
| `setMinimumWidth(60)` | 1 | day_summary.py:266 |
| `setMinimumWidth(600)` | 1 | app_protect.py:252 |
| `setMinimumWidth(620)` | 1 | journal_dialogs.py:554 |
| `setMinimumWidth(640)` | 1 | settings_dialogs.py:266 |
| `setMinimumWidth(72)` | 1 | settings_dialogs.py:299 |
| `setMinimumWidth(720)` | 1 | settings_dialogs.py:651 |
| `setMinimumWidth(760)` | 1 | week_dialogs.py:180 |

**setMaximum***

| Wert | n | Fundstellen |
|---|---|---|
| `setMaximumHeight(120)` | 1 | settings_dialogs.py:555 |
| `setMaximumHeight(130)` | 1 | m42_booking_dialogs.py:69 |
| `setMaximumHeight(150)` | 1 | settings_dialogs.py:451 |
| `setMaximumHeight(240 if parts else 90)` | 1 | timeline_only.py:446 |
| `setMaximumHeight(90)` | 1 | settings_dialogs.py:522 |
| `setMaximumHeight(max(low, high)` | 1 | timeline_only.py:1341 |
| `setMaximumWidth(320)` | 1 | settings_window.py:382 |

**resize(...)**

| Wert | n | Fundstellen |
|---|---|---|
| `self.resize(1000, 660)` | 1 | settings_window.py:544 |
| `self.resize(1200, 720)` | 1 | main_timeline.py:435 |
| `self.resize(620, 820)` | 1 | settings_dialogs.py:495 |
| `self.resize(900, 760)` | 1 | settings_dialogs.py:652 |

**QSS min-/max-width/height (theme.py)**

| Wert | n | Fundstellen |
|---|---|---|
| `min-height: 22px` | 1 | theme.py:205 |
| `min-height: 30px` | 1 | theme.py:287 |
| `min-width: 102px` | 1 | theme.py:210 |
| `min-width: 30px` | 1 | theme.py:287 |
| `min-width: 80px` | 1 | theme.py:213 |
| `min-width: {width` | 1 | theme.py:158 |

**QSS width/height (theme.py; Indikatoren, Scrollbars, Trenner)**

| Wert | n | Fundstellen |
|---|---|---|
| `height: 16px` | 2 | theme.py:260, theme.py:316 |
| `width: 0` | 2 | theme.py:208, theme.py:290 |
| `width: 1px` | 2 | theme.py:179, theme.py:194 |
| `height: 0` | 1 | theme.py:290 |
| `height: 10px` | 1 | theme.py:285 |
| `height: 1px` | 1 | theme.py:271 |
| `height: 8px` | 1 | theme.py:284 |
| `width: 10px` | 1 | theme.py:286 |
| `width: 16px` | 1 | theme.py:260 |
| `width: 30px` | 1 | theme.py:316 |

## A3. Schrift
**QSS font-size**

| Wert | n | Fundstellen |
|---|---|---|
| `font-size: 12px` | 7 | theme.py:281, theme.py:299, theme.py:302, theme.py:305, theme.py:332, theme.py:335, theme.py:336 |
| `font-size: 20px` | 2 | theme.py:242, theme.py:303 |
| `font-size: 13px` | 1 | theme.py:177 |
| `font-size: 14px` | 1 | theme.py:331 |
| `font-size: 18px` | 1 | theme.py:333 |

**QSS font-weight**

| Wert | n | Fundstellen |
|---|---|---|
| `font-weight: bold` | 24 | theme.py:206, theme.py:215, theme.py:229, theme.py:230, theme.py:233, theme.py:236, theme.py:237, theme.py:238, theme.py:239, theme.py:242, theme.py:255, theme.py:280, theme.py:292, theme.py:299, theme.py:303, theme.py:304, theme.py:305, theme.py:306, theme.py:311, theme.py:315, theme.py:330, theme.py:331, theme.py:333, theme.py:335 |
| `font-weight: normal` | 1 | theme.py:257 |

**line-height**

| Wert | n | Fundstellen |
|---|---|---|
| `line-height:{PROSE_LINE_HEIGHT` | 1 | theme.py:169 |

**QFont(...)**

| Wert | n | Fundstellen |
|---|---|---|
| `QFont(FONT_FAMILIES, point_size)` | 1 | theme.py:142 |
| `QFont(button.font()` | 1 | theme.py:155 |
| `QFont(open_action.font()` | 1 | app_tray.py:110 |

**ui_font(pt) – Timeline-Zeichnung (Punktgrößen!)**

| Wert | n | Fundstellen |
|---|---|---|
| `ui_font(8)` | 2 | timeline_only.py:1083, timeline_only.py:1138 |
| `ui_font(8, bold=True)` | 2 | timeline_only.py:1198, timeline_only.py:1421 |
| `ui_font(point_size, bold=False)` | 1 | theme.py:140 |

**setPointSize/F, setPixelSize**

| Wert | n | Fundstellen |
|---|---|---|
| `setPointSizeF(max(font.pointSizeF()` | 1 | protect_dialogs.py:21 |

**setBold/setWeight (Python)**

| Wert | n | Fundstellen |
|---|---|---|
| `DayCloseDialog.__init__` | 1 | day_close_dialog.py:71 |
| `MenusMixin.update_view_button` | 1 | app_menus.py:241 |
| `TrayMixin._build_tray` | 1 | app_tray.py:111 |
| `WeekDialog.__init__` | 1 | week_dialogs.py:201 |
| `_code_font` | 1 | protect_dialogs.py:22 |
| `fit_bold` | 1 | theme.py:156 |
| `ui_font` | 1 | theme.py:143 |

## A4. Farben
**Hex – theme.py (THEMES + QToolTip + readable_on)**

| Wert | n | Fundstellen |
|---|---|---|
| `#FFFFFF` | 8 | theme.py:103, theme.py:108, theme.py:113, theme.py:113, theme.py:115, theme.py:116, theme.py:123, theme.py:374 |
| `#18181B` | 5 | theme.py:104, theme.py:114, theme.py:117, theme.py:119, theme.py:323 |
| `#1F1F23` | 4 | theme.py:100, theme.py:101, theme.py:102, theme.py:105 |
| `#FAFAFA` | 4 | theme.py:99, theme.py:102, theme.py:104, theme.py:119 |
| `#151517` | 3 | theme.py:98, theme.py:98, theme.py:101 |
| `#2A2A2F` | 3 | theme.py:100, theme.py:102, theme.py:103 |
| `#0C0C0E` | 2 | theme.py:98, theme.py:102 |
| `#27272A` | 2 | theme.py:99, theme.py:120 |
| `#4ADE80` | 2 | theme.py:105, theme.py:110 |
| `#6B6B74` | 2 | theme.py:101, theme.py:101 |
| `#85858D` | 2 | theme.py:116, theme.py:116 |
| `#E4E4E7` | 2 | theme.py:105, theme.py:114 |
| `#F4F4F5` | 2 | theme.py:120, theme.py:323 |
| `#F7F7F8` | 2 | theme.py:113, theme.py:117 |
| `#0E6B34` | 1 | theme.py:108 |
| `#0F5E2E` | 1 | theme.py:123 |
| `#14181D` | 1 | theme.py:374 |
| `#15803D` | 1 | theme.py:120 |
| `#16A34A` | 1 | theme.py:125 |
| `#173D27` | 1 | theme.py:108 |
| `#1A1033` | 1 | theme.py:100 |
| `#1E6B3A` | 1 | theme.py:123 |
| `#2E1065` | 1 | theme.py:118 |
| `#3F3F46` | 1 | theme.py:323 |
| `#463708` | 1 | theme.py:107 |
| `#4A1C1F` | 1 | theme.py:107 |
| `#62626B` | 1 | theme.py:114 |
| `#6B4E00` | 1 | theme.py:122 |
| `#6D28D9` | 1 | theme.py:115 |
| `#9BE8B8` | 1 | theme.py:108 |
| `#9F1D20` | 1 | theme.py:122 |
| `#A1A1AA` | 1 | theme.py:99 |
| `#A78BFA` | 1 | theme.py:100 |
| `#D97706` | 1 | theme.py:125 |
| `#DC2626` | 1 | theme.py:125 |
| `#DDF3E4` | 1 | theme.py:123 |
| `#E11D48` | 1 | theme.py:118 |
| `#E2E2E6` | 1 | theme.py:117 |
| `#E6E6EA` | 1 | theme.py:115 |
| `#ECE8FB` | 1 | theme.py:118 |
| `#ECECEF` | 1 | theme.py:117 |
| `#F0F0F2` | 1 | theme.py:116 |
| `#F1F1F3` | 1 | theme.py:115 |
| `#F43F5E` | 1 | theme.py:103 |
| `#FACC15` | 1 | theme.py:110 |
| `#FCE4E4` | 1 | theme.py:122 |
| `#FF8A8E` | 1 | theme.py:110 |
| `#FFB4B6` | 1 | theme.py:107 |
| `#FFE08A` | 1 | theme.py:107 |
| `#FFF1BF` | 1 | theme.py:122 |

**Hex – andere Dateien, UI/Chrome (kein Zeichnen)**

| Wert | n | Fundstellen |
|---|---|---|
| `#4682B4` | 5 | app_menus.py:365, app_menus.py:439, app_menus.py:439, settings_dialogs.py:225, timeline_only.py:134 |
| `#0067C0` | 3 | busy_bar.py:24, busy_bar.py:58, splash_screen.py:15 |
| `#FFFFFF` | 2 | settings_dialogs.py:237, settings_dialogs.py:247 |
| `#18181B` | 1 | timeline_only.py:626 |
| `#1F5FD6` | 1 | timeline_only.py:112 |
| `#3F3F46` | 1 | timeline_only.py:627 |
| `#BB8400` | 1 | app_menus.py:437 |
| `#E4E4E7` | 1 | splash_screen.py:16 |
| `#E5484D` | 1 | timeline_only.py:112 |
| `#F08A24` | 1 | timeline_only.py:112 |
| `#F4F4F5` | 1 | timeline_only.py:626 |

**Hex – Datenfarben (Aktivitätstypen/Kategorien: config_defaults, main_timeline, local_sources, timeline_only Klassenkonstanten)**

| Wert | n | Fundstellen |
|---|---|---|
| `#9B59B6` | 5 | config_defaults.py:53, config_defaults.py:58, config_defaults.py:60, config_defaults.py:61, main_timeline.py:260 |
| `#E06D10` | 5 | config_defaults.py:47, config_defaults.py:66, main_timeline.py:162, main_timeline.py:258, main_timeline.py:262 |
| `#0F9D8A` | 4 | config_defaults.py:45, config_defaults.py:67, main_timeline.py:160, main_timeline.py:258 |
| `#BB8400` | 4 | config_defaults.py:46, config_defaults.py:65, main_timeline.py:155, main_timeline.py:161 |
| `#139FB3` | 3 | config_defaults.py:52, config_defaults.py:68, main_timeline.py:163 |
| `#2E9E5B` | 3 | main_timeline.py:164, main_timeline.py:257, main_timeline.py:261 |
| `#009BBB` | 2 | main_timeline.py:150, main_timeline.py:267 |
| `#00A3C4` | 2 | main_timeline.py:150, main_timeline.py:173 |
| `#0D9F99` | 2 | main_timeline.py:151, main_timeline.py:262 |
| `#0EA5A4` | 2 | local_sources.py:51, local_sources.py:51 |
| `#0FB9B1` | 2 | main_timeline.py:151, main_timeline.py:171 |
| `#2272AD` | 2 | config_defaults.py:54, main_timeline.py:165 |
| `#25766B` | 2 | timeline_only.py:491, timeline_only.py:495 |
| `#267841` | 2 | timeline_only.py:491, timeline_only.py:495 |
| `#2A7285` | 2 | timeline_only.py:491, timeline_only.py:494 |
| `#3460DB` | 2 | config_defaults.py:64, main_timeline.py:259 |
| `#356CA9` | 2 | timeline_only.py:491, timeline_only.py:493 |
| `#3B5BDB` | 2 | main_timeline.py:152, main_timeline.py:172 |
| `#3C5CDB` | 2 | main_timeline.py:152, main_timeline.py:263 |
| `#3D8BFD` | 2 | main_timeline.py:263, main_timeline.py:264 |
| `#565EBF` | 2 | main_timeline.py:153, main_timeline.py:267 |
| `#7C51C8` | 2 | timeline_only.py:491, timeline_only.py:493 |
| `#85642A` | 2 | timeline_only.py:491, timeline_only.py:494 |
| `#BB3B50` | 2 | timeline_only.py:491, timeline_only.py:496 |
| `#C2185B` | 2 | main_timeline.py:154, main_timeline.py:170 |
| `#C7195D` | 2 | main_timeline.py:154, main_timeline.py:259 |
| `#00A8B5` | 1 | timeline_only.py:482 |
| `#00B894` | 1 | main_timeline.py:160 |
| `#0B7FA0` | 1 | main_timeline.py:268 |
| `#0F6CBD` | 1 | main_timeline.py:266 |
| `#14181D` | 1 | config_defaults.py:72 |
| `#16A085` | 1 | config_defaults.py:51 |
| `#18B34B` | 1 | timeline_only.py:481 |
| `#1ABC9C` | 1 | main_timeline.py:163 |
| `#1F7A8C` | 1 | main_timeline.py:173 |
| `#2563EB` | 1 | local_sources.py:51 |
| `#27AE60` | 1 | main_timeline.py:164 |
| `#2980B9` | 1 | main_timeline.py:165 |
| `#2F7BFF` | 1 | timeline_only.py:481 |
| `#3498DB` | 1 | config_defaults.py:50 |
| `#3F73D0` | 1 | local_sources.py:52 |
| `#464EB8` | 1 | main_timeline.py:153 |
| `#4A4A4A` | 1 | config_defaults.py:73 |
| `#4C6EF5` | 1 | timeline_only.py:482 |
| `#5B5FC7` | 1 | main_timeline.py:266 |
| `#5B8DEF` | 1 | main_timeline.py:260 |
| `#6264A7` | 1 | main_timeline.py:268 |
| `#64748B` | 1 | local_sources.py:50 |
| `#6B7280` | 1 | local_sources.py:50 |
| `#6E7781` | 1 | main_timeline.py:172 |
| `#7B8494` | 1 | local_sources.py:50 |
| `#7F8C8D` | 1 | main_timeline.py:170 |
| `#8395A7` | 1 | main_timeline.py:171 |
| `#8B7AA8` | 1 | local_sources.py:50 |
| `#8BC34A` | 1 | timeline_only.py:482 |
| `#9B3DF2` | 1 | timeline_only.py:481 |
| `#9C5831` | 1 | timeline_only.py:492 |
| `#A55EEA` | 1 | main_timeline.py:261 |
| `#B45309` | 1 | main_timeline.py:269 |
| `#B4B4B4` | 1 | config_defaults.py:72 |
| `#C0392B` | 1 | config_defaults.py:55 |
| `#D97706` | 1 | local_sources.py:51 |
| `#D99A00` | 1 | main_timeline.py:155 |
| `#E5242B` | 1 | timeline_only.py:482 |
| `#E5484D` | 1 | main_timeline.py:264 |
| `#E67E22` | 1 | main_timeline.py:162 |
| `#E84393` | 1 | config_defaults.py:59 |
| `#F1C40F` | 1 | main_timeline.py:161 |
| `#F5B700` | 1 | timeline_only.py:482 |
| `#FF2E8A` | 1 | timeline_only.py:481 |
| `#FF7A00` | 1 | timeline_only.py:481 |
| `#FFFFFF` | 1 | config_defaults.py:73 |

**Hex – Grafik/Icons (icons.py, paint/_render)**

| Wert | n | Fundstellen |
|---|---|---|
| `#FFFFFF` | 24 | icons.py:159, icons.py:179, icons.py:201, icons.py:205, icons.py:211, icons.py:212, icons.py:216, icons.py:220, icons.py:221, icons.py:225, icons.py:226, icons.py:229, icons.py:230, icons.py:233, icons.py:235, icons.py:238, icons.py:242, icons.py:244, icons.py:244, icons.py:248, icons.py:252, icons.py:259, icons.py:260, icons.py:280 |
| `#2F7BFF` | 2 | app_menus.py:501, icons.py:258 |
| `#7D8590` | 2 | icons.py:122, icons.py:167 |
| `#005BC8` | 1 | icons.py:245 |
| `#0067B8` | 1 | icons.py:210 |
| `#0078D7` | 1 | timeline_only.py:1537 |
| `#00A3E0` | 1 | icons.py:253 |
| `#0B2D6B` | 1 | icons.py:255 |
| `#0E8EE9` | 1 | icons.py:204 |
| `#0EA5A4` | 1 | icons.py:223 |
| `#0F6CBD` | 1 | icons.py:256 |
| `#0F9D8A` | 1 | icons.py:250 |
| `#18B34B` | 1 | timeline_only.py:1537 |
| `#1B1F24` | 1 | icons.py:254 |
| `#2563EB` | 1 | icons.py:232 |
| `#2B2F36` | 1 | icons.py:215 |
| `#2E9E5B` | 1 | icons.py:166 |
| `#4B5563` | 1 | icons.py:219 |
| `#5B5FC7` | 1 | icons.py:257 |
| `#6264A7` | 1 | icons.py:237 |
| `#6B4E00` | 1 | icons.py:165 |
| `#B2331F` | 1 | icons.py:208 |
| `#B45309` | 1 | icons.py:241 |
| `#D97706` | 1 | icons.py:228 |
| `#DA291C` | 1 | icons.py:247 |
| `#E5484D` | 1 | icons.py:121 |
| `#E8412C` | 1 | icons.py:207 |
| `#F5B800` | 1 | icons.py:165 |

**QColor(...) – alle (Literale + Token-Zugriffe)**

| Wert | n | Fundstellen |
|---|---|---|
| `QColor(color)` | 9 | busy_bar.py:118, icons.py:115, icons.py:194, icons.py:277, icons.py:294, theme.py:366, timeline_only.py:864, timeline_only.py:1438, timeline_only.py:1538 |
| `QColor("#0067C0")` | 2 | busy_bar.py:24, busy_bar.py:58 |
| `QColor(base)` | 2 | timeline_only.py:1153, timeline_only.py:1283 |
| `QColor(self.color)` | 2 | busy_bar.py:43, busy_bar.py:78 |
| `QColor(t["surface"])` | 2 | timeline_only.py:592, timeline_only.py:605 |
| `QColor("#0078D7" if zoom else "#18B34B")` | 1 | timeline_only.py:1537 |
| `QColor("#14181D")` | 1 | theme.py:374 |
| `QColor("#FFFFFF")` | 1 | theme.py:374 |
| `QColor(0, 0, 0, 10)` | 1 | timeline_only.py:1099 |
| `QColor(0, 0, 0, 80)` | 1 | timeline_only.py:600 |
| `QColor(255, 255, 255, 10)` | 1 | timeline_only.py:1099 |
| `QColor(255, 255, 255, 22)` | 1 | timeline_only.py:598 |
| `QColor(255, 255, 255, 9)` | 1 | timeline_only.py:599 |
| `QColor(27, 31, 36, 10)` | 1 | timeline_only.py:603 |
| `QColor(27, 31, 36, 14)` | 1 | timeline_only.py:604 |
| `QColor(27, 31, 36, 26)` | 1 | timeline_only.py:602 |
| `QColor(85, 85, 85, 179)` | 1 | theme.py:50 |
| `QColor(THEMES["dark" if self.dark_mode else "light"]["accent"])` | 1 | timeline_only.py:1452 |
| `QColor(c)` | 1 | timeline_only.py:1441 |
| `QColor(colors[direction])` | 1 | timeline_only.py:133 |
| `QColor(own)` | 1 | timeline_only.py:128 |
| `QColor(self.background_color)` | 1 | timeline_only.py:1428 |
| `QColor(self.call_color(direction))` | 1 | app_menus.py:449 |
| `QColor(self.config['type_colors'].get(type_name, "#FFFFFF"))` | 1 | settings_dialogs.py:237 |
| `QColor(self.row_color(key))` | 1 | app_menus.py:475 |
| `QColor(t["accent"])` | 1 | timeline_only.py:595 |
| `QColor(t["muted"])` | 1 | timeline_only.py:594 |
| `QColor(t["now"])` | 1 | timeline_only.py:596 |
| `QColor(t["text"])` | 1 | timeline_only.py:593 |
| `QColor(theme[key])` | 1 | app_menus.py:823 |

_rgb()/rgba() in QSS: keine Treffer._

## A5. Radien, Rahmen, Schatten
**border-radius**

| Wert | n | Fundstellen |
|---|---|---|
| `border-radius: 10px` | 8 | theme.py:254, theme.py:273, theme.py:275, theme.py:313, theme.py:316, theme.py:326, theme.py:350, timeline_only.py:627 |
| `border-radius: 6px` | 7 | theme.py:182, theme.py:203, theme.py:213, theme.py:231, theme.py:250, theme.py:309, theme.py:323 |
| `border-radius: 8px` | 4 | theme.py:267, theme.py:322, theme.py:335, theme.py:358 |
| `border-radius: 11px` | 2 | theme.py:339, theme.py:344 |
| `border-radius: 2px` | 2 | theme.py:352, theme.py:353 |
| `border-radius: 4px` | 2 | theme.py:261, theme.py:268 |
| `border-radius: 3px` | 1 | theme.py:287 |

**border***

| Wert | n | Fundstellen |
|---|---|---|
| `border: none` | 15 | theme.py:178, theme.py:180, theme.py:200, theme.py:208, theme.py:247, theme.py:277, theme.py:279, theme.py:282, theme.py:307, theme.py:320, theme.py:328, theme.py:347, theme.py:352, theme.py:356, theme.py:357 |
| `border: 1px solid $border` | 9 | theme.py:254, theme.py:267, theme.py:273, theme.py:275, theme.py:313, theme.py:326, theme.py:334, theme.py:338, theme.py:350 |
| `border: 1px solid $control` | 6 | theme.py:195, theme.py:202, theme.py:212, theme.py:226, theme.py:260, theme.py:322 |
| `border: 2px solid $accent` | 5 | theme.py:192, theme.py:217, theme.py:248, theme.py:342, theme.py:346 |
| `border-bottom: 1px solid $line` | 3 | theme.py:277, theme.py:320, theme.py:328 |
| `border: 1px solid $accent` | 3 | theme.py:224, theme.py:234, theme.py:349 |
| `border: 1px solid #3F3F46` | 2 | theme.py:323, timeline_only.py:627 |
| `border-bottom: 1px solid $border` | 1 | theme.py:280 |
| `border-left: 3px solid $accent` | 1 | theme.py:311 |
| `border-left: 3px solid transparent` | 1 | theme.py:309 |
| `border-right: 1px solid $border` | 1 | theme.py:307 |
| `border-top: 1px solid $border` | 1 | theme.py:197 |
| `border: 1px dashed $control` | 1 | theme.py:343 |
| `border: 1px solid $muted` | 1 | theme.py:225 |
| `border: 1px solid transparent` | 1 | theme.py:181 |
| `border: 2px solid $muted` | 1 | theme.py:316 |

**drawRoundedRect (Grafik)**

| Wert | n | Fundstellen |
|---|---|---|
| `drawRoundedRect(r, radius, radius)` | 1 | timeline_only.py:48 |

**QPen (Grafik: Linienstärken)**

| Wert | n | Fundstellen |
|---|---|---|
| `QPen(Qt.NoPen)` | 4 | timeline_only.py:1073, timeline_only.py:1154, timeline_only.py:1181, timeline_only.py:1294 |
| `QPen(self.hour_line, 1)` | 3 | timeline_only.py:1087, timeline_only.py:1131, timeline_only.py:1431 |
| `QPen(base, 1.5, Qt.DashLine)` | 2 | timeline_only.py:1292, timeline_only.py:1298 |
| `QPen(QColor(85, 85, 85, 179)` | 1 | theme.py:50 |
| `QPen(accent, 3)` | 1 | timeline_only.py:1453 |
| `QPen(base, 1.2, Qt.DashDotLine)` | 1 | timeline_only.py:1301 |
| `QPen(base, 1.2, Qt.DashLine)` | 1 | timeline_only.py:1289 |
| `QPen(base, 1.5, Qt.DotLine)` | 1 | timeline_only.py:1304 |
| `QPen(color, 1)` | 1 | timeline_only.py:1540 |
| `QPen(self.half_line, 1)` | 1 | timeline_only.py:1090 |
| `QPen(self.now_color, 2)` | 1 | timeline_only.py:1192 |
| `QPen(self.text_color, 1, Qt.DashLine)` | 1 | timeline_only.py:1195 |
| `QPen(track, 2.5)` | 1 | busy_bar.py:80 |

_QGraphicsDropShadowEffect: **keine Treffer** (auch kein setBlurRadius/setOffset)._

## A6. Inline setStyleSheet-Aufrufe

| Fundstelle | Funktion | Inhalt (gekürzt) |
|---|---|---|
| app_menus.py:64 | MenusMixin._build_toolbar | `header.setStyleSheet("#band_row { background: transparent; }")` |
| app_menus.py:824 | MenusMixin.apply_style | `self.setStyleSheet("")` |
| app_menus.py:826 | MenusMixin.apply_style | `self.setStyleSheet(sheet)` |
| settings_dialogs.py:250 | ActivityTypeSettingsDialog.update_color_button | `self.color_btn.setStyleSheet(f"background-color: {color}; color: {text};")` |
| theme.py:158 | fit_bold | `button.setStyleSheet(f"QPushButton {{ min-width: {width}px; }}")` |
| timeline_only.py:625 | TimelineView._create_tooltip | `tooltip.setStyleSheet( "QLabel { background-color: #18181B; color: #F4F4F5; " "border: 1px solid #3F3F46; padding: 8px 10px; border-radius: 10px; }" )` |

## A8. Grafikgeometrie (Timeline/Zeichnen) – getrennt, NICHT auf die Layout-Skala mappen

| Ort | Werte | Bemerkung |
|---|---|---|
| `timeline_only.py:40` `_RoundRect.RADIUS = 4.0`, `:48 drawRoundedRect` | Balkenradius 4 | passt zufällig auf Skala, ist aber Grafik |
| `timeline_only.py:484–502` | `LEFT 136`, `RIGHT 34`, `AXIS_H 26`, `PC_BAND_H 22`, `PC_RAW_H 14`, `LANE_H 26`, `LANE_GAP 6`, `MIN_LANE_H 16`, `MAX_LANES 10`, `BASE_PX_PER_MIN 1.2` | Zeichengeometrie |
| `timeline_only.py:1083/1138/1198/1421` | `ui_font(8)`, `ui_font(8, bold=True)` | **pt**, ≈ 10,7 px – einzige Stelle mit Punktgröße |
| `timeline_only.py:1438/1441/1443` | Legendenquadrat `fillRect(8, c-4, 8, 8)`, Streifen 2×8 @3 px, Text x=22 | Legende links |
| `timeline_only.py:1087–1304, 1431, 1453, 1540` | QPen 1 / 1.2 / 1.5 / 2 / 3 px (Dash/Dot) | Linienstärken |
| `timeline_only.py:598–604, 1099` | `QColor(255,255,255,22/9/10)`, `QColor(0,0,0,80/10)`, `QColor(27,31,36,26/10/14)` | Stunden-/Halbstundenlinien, Nicht-Arbeitszeit, Zebra – aus `text`-Token mit Alpha ableitbar |
| `timeline_only.py:1537` | `#0078D7` (Zoom-Rahmen), `#18B34B` (Auswahl) | → Kandidat Token `accent` / `good` |
| `timeline_only.py:481–496` | `APP_COLORS` (10), `BLOCK_COLORS` (8), `CATEGORY_COLORS` | Datenpalette |
| `timeline_only.py:1340–1341, 573` | `setMinimumHeight(200)`, dynamische Min/Max-Höhe | Widgetgröße der Timeline |
| `settings_preview.py:162–198` | `TIMELINE_HEIGHT 170`, `26 + LIST_ROWS*24 + 4` | an Timeline-Geometrie gekoppelt |
| `busy_bar.py:22/57/80` | Streifen 3 px, Spinner 16×16, Pen 2.5 | Grafik |
| `theme.py:50–51` | Rubber-Band Pen 2 px, `QColor(85,85,85,179)`, Dash [2,2] | Grafik |
| `icons.py` | SVG-Strichstärken 1.4–2.6, Markenfarben | Icons |

## A9. Farbgruppen (ähnliche Werte)

**theme.py (je Modus doppelt belegte Werte → Aliase, kein Handlungsbedarf, aber Hinweis)**
- dark: `#151517` = surface/bar/alt · `#1F1F23` = hover/line/chip/bandhover · `#2A2A2F` = pressed/sel/bandpressed · `#6B6B74` = handle/control · `#0C0C0E` = bg/band · `#FAFAFA` = text/bandtext/primary · `#4ADE80` = good/rate_value_ok
- light: `#FFFFFF` = surface/bar/alt/onaccent/rate_over_text · `#F7F7F8` = bg/band · `#85858D` = handle/control · `#18181B` = text/bandtext/primary · `#E4E4E7` = border (auch dark chiptext, splash TRACK)
- Grüntöne light: `#15803D` good, `#16A34A` rate_value_ok, `#1E6B3A` rate_ok_text, `#0F5E2E` rate_over – 4 nahe Grüns.
- Fest im QSS statt Token: QToolTip `#18181B / #F4F4F5 / #3F3F46` (Z. 323) – identisch in `timeline_only.py:626–627` dupliziert → eigene Tokens `tip/tiptext/tipborder`.
- `readable_on` dunkel `#14181D` ≠ Theme-Text `#18181B` (auch `config_defaults.py:72`).

**Andere Dateien – UI-Chrome (sollten Tokens werden)**
- Blau `#0067C0`: `busy_bar.py:24, :58`, `splash_screen.py:15` (busy_bar wird per `set_color(muted)` überschrieben; Splash läuft vor dem Theme).
- `#E4E4E7` `splash_screen.py:16` = light `border`.
- `#4682B4` Standard-Zeilen/Typfarbe: `app_menus.py:365, 437–439`, `settings_dialogs.py:225`, `timeline_only.py:134`.
- `#2F7BFF` PC-Zeile: `app_menus.py:501`, `icons.py:258`, `timeline_only.py:481`.
- Rot `#E5484D`: `icons.py:121`, `main_timeline.py:264`, `timeline_only.py:112` (→ ähnlich `now` `#F43F5E/#E11D48`).
- Grau `#7D8590`: `icons.py:122, 167`; `local_sources.py:50` Graus `#6B7280 #64748B #7B8494`.

**Datenfarben (Aktivitätstypen, nutzerkonfigurierbar – nicht ins UI-Token-System, aber entdoppeln)**
- Lila `#9B59B6` 5× (`config_defaults.py:53,58,60,61`, `main_timeline.py:260`) – Kommentar Z. 60/61 sagt „Grau“, Wert ist Lila.
- Türkis/Petrol: `#0F9D8A` (VPN, 5×), `#16A085`, `#00B894`, `#0EA5A4` (3×), `#139FB3`, `#0FB9B1/#0D9F99`, `#00A3C4/#009BBB`, `#0B7FA0`.
- Blau: `#3460DB`, `#3B5BDB/#3C5CDB`, `#2272AD/#2980B9`, `#3498DB`, `#3D8BFD`, `#5B8DEF`, `#2563EB`, `#0F6CBD`, `#1F5FD6`, `#356CA9`, `#4C6EF5`.
- Indigo/Teams: `#5B5FC7`, `#6264A7`, `#464EB8/#565EBF`.
- Gelb/Orange: `#BB8400` (5×), `#D99A00`, `#F1C40F`, `#E06D10` (4×), `#E67E22`, `#D97706`, `#B45309`, `#F08A24`, `#FF7A00`.
- Rot/Pink: `#C0392B`, `#C2185B/#C7195D`, `#E84393`, `#BB3B50`, `#E5242B`.
- `main_timeline.py:150–173` ist eine **Migrationstabelle alt→neu** (Paare), keine aktive Palette.

