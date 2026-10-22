# Screenshots der überarbeiteten Oberfläche (22.10.2026)

Alle Bilder zeigen **erfundene Demodaten** (Kunden, Nummern, Fenster) für Mittwoch, 21.10.2026.
Aufgenommen unter Linux mit virtuellem Bildschirm (Xvfb), Fenstermanager openbox und
Infobereich stalonetray. Deshalb weichen Fensterrahmen, Taskleiste und Schrift von Windows ab:
Unter Windows nutzt Zeitzeuge „Segoe UI Variable“ bzw. „Segoe UI“, hier ersatzweise „Inter“.

Neu erzeugen: `tests/screenshots.sh docs/screenshots/2026-10-22` (dunkel: zusätzlich `--dark`).
Zum Vergleich liegen fünf Bilder des alten Stands in [`vorher/`](vorher/).

| Bild | Ansicht | Wichtigste Änderungen |
|---|---|---|
| [01_hauptfenster.png](01_hauptfenster.png) | Hauptfenster im normalen Zustand | Werkzeugleiste mit einheitlichen Linien-Icons statt Zeichen (◀ ▶ ⟳ − +), in Gruppen: Tag · Aktualisieren · Ausschnitt · Liste · Einstellungen. „Dunkel“ ist ins Menü gewandert, dadurch passt die Leiste auch bei 1200 px. Timeline-Balken mit ruhigem, durchgezogenem Rand. Rechts unten neu: Zustand der Fensteraufzeichnung. |
| [02_hauptmenue.png](02_hauptmenue.png) | Menü „Einstellungen“ geöffnet | Nach Aufgaben gegliedert: Ansicht (Dunkles Design) · Aufzeichnung · häufige Einstellungen (Arbeitszeiten, Typen und Farben) · Untermenüs für Seltenes · Info und Beenden. Vorher 12 Einträge flach in einer Liste. |
| [03_menue_1_datenquellen.png](03_menue_1_datenquellen.png) | Untermenü „Datenquellen“ | TeamViewer, RDM, 3CX (zwei Wege), ITM gebündelt: richtet man einmal ein, braucht man selten. |
| [03_menue_2_datenspeicher.png](03_menue_2_datenspeicher.png) | Untermenü „Datenspeicher“ | Datenordner öffnen, Speicherort ändern. |
| [04_tagesliste_kontextmenue.png](04_tagesliste_kontextmenue.png) | Rechtsklick in der Tagesliste | Gleiche Icon-Sprache, Alt-Buchstaben, Kürzel auf Deutsch („Strg+C“). |
| [05_dialog_arbeitszeiten.png](05_dialog_arbeitszeiten.png) | Dialog Arbeitszeiten | Knöpfe auf Deutsch („Abbrechen“ statt „Cancel“), OK als hervorgehobener Hauptknopf, Zeitfelder ohne die zuvor kaputt gezeichneten Pfeile (Eingabe per Tastatur, Pfeiltasten oder Mausrad). |
| [06_dialog_teamviewer.png](06_dialog_teamviewer.png) | Dialog TeamViewer-Logs | Gruppenkästen mit fetter Überschrift, Beschriftungen ohne störenden Hintergrund-Block. |
| [07_dialog_3cx.png](07_dialog_3cx.png) | Dialog 3CX direkt auslesen | Einheitliche Knopfreihenfolge wie unter Windows: OK, Zusatzaktion, Abbrechen. |
| [08_dialog_details.png](08_dialog_details.png) | Details eines Eintrags | „Schließen“ statt „Close“. |
| [09_dialog_aktivitaetstypen.png](09_dialog_aktivitaetstypen.png) | Aktivitätstypen und Farben | Doppelter Eintrag „Website-Verbindung“ entfernt. |
| [10_tray_menue_aufzeichnung_aktiv.png](10_tray_menue_aufzeichnung_aktiv.png) | Infobereich mit offenem Menü, **Aufzeichnung aktiv** | Symbol mit grünem Punkt. Menü: Zeitzeuge öffnen (fett, auch per Klick aufs Symbol) · Zustand „Aufzeichnung aktiv“ · „Aufzeichnung pausieren“ · Logs neu einlesen · Datenquellen · Datenordner öffnen · Beenden. Vorher nur „Öffnen“ und „Beenden“. |
| [10_hauptfenster_aufzeichnung_aktiv.png](10_hauptfenster_aufzeichnung_aktiv.png) | Hauptfenster, Aufzeichnung aktiv | Statuszeile rechts: grüner Punkt „Aufzeichnung aktiv“ (ein Klick pausiert), PC-Band oben in der Timeline. |
| [11_tray_menue_aufzeichnung_pausiert.png](11_tray_menue_aufzeichnung_pausiert.png) | Infobereich mit offenem Menü, **Aufzeichnung pausiert** | Symbol mit grauem Punkt und Pause-Zeichen (nicht nur Farbe). Zustandszeile „Aufzeichnung pausiert“, Befehl wechselt zu „Aufzeichnung fortsetzen“. Tooltip des Symbols nennt den Zustand. |
| [11_hauptfenster_aufzeichnung_pausiert.png](11_hauptfenster_aufzeichnung_pausiert.png) | Hauptfenster, Aufzeichnung pausiert | Statuszeile „Aufzeichnung pausiert“. Das bisher Aufgezeichnete bleibt sichtbar (vorher verschwand das PC-Band beim Ausschalten komplett). |
| [12_hauptfenster_dunkel.png](12_hauptfenster_dunkel.png) | Hauptfenster, dunkles Design | Icons färben sich mit dem Design um. |
| [13_hauptmenue_dunkel.png](13_hauptmenue_dunkel.png) | Menü, dunkles Design | Häkchen zeigt „Dunkles Design“ an. |
| [14_tray_menue_dunkel.png](14_tray_menue_dunkel.png) | Infobereich, dunkles Design | Gleiches Menü, passende Farben. |
