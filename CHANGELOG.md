# Änderungen

Alle sichtbaren Änderungen an Zeitzeuge, die neueste Version oben.

Versionsnummer **MAJOR.MINOR.PATCH**, z. B. 4.1.3. Sie zählt von selbst (siehe `version.py`):
- **PATCH**: +1 für jeden PR, der in main gemergt wird.
- **MINOR**: +1 mit dem ersten Merge in einem neuen Monat (oder `[minor]` im PR-Titel);
  PATCH beginnt dann bei 0.
- **MAJOR**: nur mit `[major]` im PR-Titel, z. B. wenn ältere Versionen die Daten nicht mehr
  lesen können.

Testversionen aus Branches tragen die Version ihres main-Stands plus Buildnummer
(„4.1.3 · Test 186“). Ein Abschnitt hier gehört zu einer MINOR-Stufe.

## 4.1 – November 2026

**Achtung:** Die Daten liegen jetzt verschlüsselt in einer Datenbank. Versionen vor dem
26.10.2026 können sie nicht mehr lesen.

### Neu
- **Tagesabschluss** (Menü Ansicht, Wochenabschluss, Meldung bei Feierabend): Zeitzeuge stellt den Tag aus eigenen Tätigkeiten, Verbindungen, Telefonaten, KI-Vorschlägen, Regeln und PC-Aktivität zu Blöcken je Kunde zusammen, mit Ticket (aus Fenstertiteln oder zuletzt für den Kunden benutzt) und kurzem Tickettext. Ein Klick dokumentiert alles und bucht die Zeilen mit Ticket nacheinander in Matrix42. Oben steht, wie viel Prozent der Personalzeit danach erfasst sind. Ohne Rückfrage werden nur sichere Tickets gebucht. **Erkennung messen …** vergleicht die Vorschläge der letzten 20 Tage mit deinen echten Buchungen.
- Zwei Menüs: **Ansicht** (Tagesliste, Zeilen der Timeline, Zeitraum, Übersichten, Design) und **Einstellungen** als eigenes Fenster mit Bereichen, Suche und Datenquellen als Kacheln mit Zustand. Schnellzugriffe (Tag, Heute, Ganzer Tag, Arbeitszeit …) bleiben in der Werkzeugleiste.
- Hilfe zu den Ansichten der Tagesliste (Zusammengefasst, Einzeln …) mit Beispielen, F1.
- Symbole überall, Datenquellen mit Zeichen in der Farbe des Herstellers.
- Anrufe: eingehend blau ↙, ausgehend orange ↗. Die Richtung aus 3CX wird zuverlässiger erkannt.
- Nachfrage nach Abwesenheit am PC: ab 15 Minuten ohne Eingabe (einstellbar) fragt Zeitzeuge bei der ersten Eingabe, was war. Schnellauswahl Telefonat, Besprechung, Vor Ort, Fahrt / Reise, Pause.
- Kulanz und Reise an jeder Tätigkeit, beim Buchen in Matrix42 übernommen. Neue Kategorien „Vor-Ort-Einsatz“ und „Fahrt / Reise“.
- Timeline kräftiger: weniger Transparenz bei Regeln, KI und offenen Einträgen, bunte Programmfarben, Matrix42-Buchungen blau statt grau.
- Daten verschlüsselt in einer Datenbank statt vieler Dateien, PIN beim Start (schützt auch vor Domänen-Admins).
- Matrix42: gebuchte Zeiten lesen und abgleichen, Buchungen über die Schnittstelle, Buchungsquote und Wochenabschluss, Prüfung bei Feierabend.
- Outlook (Termine, Teams-Besprechungen, gesendete Mails) und Teams-Anrufe als Quellen.
- Kundenliste mit allen Spuren, Lernen aus Korrekturen.
- Eintragen: Textbausteine, letzte Texte je Kunde, Ticket-Format und Ticketnummer-Vorschlag; Ticketzeile mit echten und abgerechneten Zeiten.
- Abrechnungstakt je Kunde (z. B. 15 Minuten), PC-Verlauf automatisch löschen.
- Zwei PCs: Export/Import (z. B. für die PAW), PAW-Modus ohne Edge, Ordner-Variante der EXE für Rechner mit EDR.
- Personalzeit als eigene Zeile mit Beginn und Ende.
- Tagesliste: neue Ansicht **Telefonate** (Menü Ansicht): nur Anrufe aus 3CX und Teams, jeder einzeln.
- Einstellungen: Einrichtungsassistent oben auf „Datenquellen“; Vorschau unter „Ansicht“ kleiner und schemenhaft, beim Darüberfahren kräftig.
- Einstellungen → **Fehlersuche & Analyse**: Mitschnitte (3CX, Matrix42, ITM, Matrix42-Buchung) und die 3CX-Direkt-Abfrage stehen jetzt dort statt in den Einrichtungsdialogen.
- Jede Zeile der Timeline ausblendbar; „Regeln“ heißt jetzt „Zuordnung ohne KI“.
- Design „Metro Klar“ (hell und dunkel), Werkzeugleiste in Klar-Farben, Timeline ohne senkrechte Scrollleiste.
- Nachfragen zu mehr Themen: Arbeitsblöcke am PC (z. B. M365-Admin, Remotedesktop), Teams-Besprechungen mit erkennbarer Teilnahme, Mails an Kunden aus der Kundenliste; auf Wunsch angezeigte Zugangsdaten.
- Keine doppelten Nachfragen mehr: Was zum selben Kunden zur selben Zeit gehört (VPN + RDP + Telefonat), ist eine Nachfrage. Beantwortetes, Ignoriertes und Zurückgestelltes erkennt Zeitzeuge über Zeitraum und Kunde wieder, auch bei kürzer eingetragener Zeit oder später nachgeladenen Logs.
- Einstellungen → **Ansicht** mit Vorschau: alle Darstellungs-Einstellungen auf einer Seite, darüber Timeline und Tagesliste eines Beispieltags. Beim Darüberfahren über einen Schalter oder beim Durchgehen einer Auswahl zeigt die Vorschau die Änderung schon vorher, ohne zu speichern. Erklärtexte bleiben in breiten Fenstern links und werden nicht mehr abgeschnitten.
- PC-Aktivität als Arbeitsblöcke: Fenster werden je Tätigkeit zusammengefasst (Zuordnung ohne KI, sonst Programm), kurze Sprünge zählen zur Haupttätigkeit, wenn es danach dort weitergeht oder der Kunde passt. Beschriftete Blöcke in gedeckten Farben, Hinweis mit Anteilen der Programme, Fensterwechseln und Fokus. Umschalten zwischen Blöcken und jedem Fenster einzeln über **Ansicht → PC-Aktivität als Arbeitsblöcke**, per Rechtsklick auf die Legende oder unter Einstellungen → Allgemein.
- Timeline startet in der Arbeitszeit (merkt sich „Ganzer Tag“), offene Einträge dicht hintereinander als ein Block „? 3 offen“, keine abgeschnittenen Mini-Beschriftungen mehr.
- Aufgeräumt: Leere Zeilen der Timeline verschwinden von selbst, „Zuordnung ohne KI“ fließt in die Zeile Dokumentation ein (eigene Zeile standardmäßig aus). Menü **Ansicht** von rund 30 auf 13 Einträge: Zeilen der Timeline als Untermenü und per Rechtsklick auf die Legende, Dunkles Design und Datenquellen direkt im Pfeil-Menü der Einstellungen. Tagesliste ohne doppelte Details, kürzere Statuszeile, Zoom per STRG + Mausrad statt Lupen-Knöpfen.
- Besser lesbar nach 16 UI-Design-Regeln: Spaltenköpfe und Menü-Überschriften ohne Großbuchstaben, nur noch normal und fett, kräftigere Rahmen um Felder und Knöpfe (3 : 1), Gruppen ohne Rahmen, Erklärtexte mit mehr Zeilenabstand, eine Schrift auch in der Timeline. Sechs Timeline-Farben (u. a. RDP, Mail gesendet, Teams-Anruf) etwas kräftiger, damit sie sich in beiden Designs abheben; selbst gewählte Farben bleiben.
- ITM: Anmeldung ohne Edge, eigene Buchungen aus dem alten Backend, fehlerhafte Buchungen werden gemeldet.
- Nachfragen ab 1 Minute, Schwelle je Art einstellbar.
- Ladeanzeige: drehender Kreis mit Text neben „Arbeitszeit“ und Streifen über die ganze Breite; Timeline springt beim Laden nicht mehr.
- Versionsnummer zählt von selbst (4.1.0, 4.1.1, …); steht im Fenstertitel, unter **Info**, in fehler.log, in der EXE und im Namen der Downloads.

### Behoben
- Matrix42: „Bei Matrix42 anmelden“ öffnete das Fenster nur kurz und schloss es gleich wieder. Es bleibt jetzt offen, bis die Anmeldung wirklich geklappt hat.
- Absturz beim Start, wenn „3CX direkt auslesen“ eingeschaltet ist.
- Anrufe: ein Gespräch wurde von einem Versuch in derselben Minute überschrieben.
- Eintragen: Beschriftung des Merken-Hakens landete im Textfeld.
- PC-Verlauf wird vor dem Löschen mit Nullen überschrieben; Teams-Logs vor 1970 unter Windows.

## 4.0.0 – 2026-10-22

- Umstieg von PyQt5 auf PySide6 (Qt 6), PyInstaller 6.22.3.
- Versionsangaben in der EXE, kein UPX mehr, optionale Signierung.
- Ein Rechtsklick-Menü für Timeline und Liste, Statussymbole für 3CX/ITM/Logs, Knopf für offene Tätigkeiten.
- Tests mit pytest.
