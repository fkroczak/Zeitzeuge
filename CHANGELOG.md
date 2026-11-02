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
- Jede Zeile der Timeline ausblendbar; „Regeln“ heißt jetzt „Zuordnung ohne KI“.
- Design „Metro Klar“ (hell und dunkel), Werkzeugleiste in Klar-Farben, Timeline ohne senkrechte Scrollleiste.
- ITM: Anmeldung ohne Edge, eigene Buchungen aus dem alten Backend, fehlerhafte Buchungen werden gemeldet.
- Nachfragen ab 1 Minute, Schwelle je Art einstellbar.
- Ladeanzeige: drehender Kreis mit Text neben „Arbeitszeit“ und Streifen über die ganze Breite; Timeline springt beim Laden nicht mehr.
- Versionsnummer zählt von selbst (4.1.0, 4.1.1, …); steht im Fenstertitel, unter **Info**, in fehler.log, in der EXE und im Namen der Downloads.

### Behoben
- Absturz beim Start, wenn „3CX direkt auslesen“ eingeschaltet ist.
- Anrufe: ein Gespräch wurde von einem Versuch in derselben Minute überschrieben.
- Eintragen: Beschriftung des Merken-Hakens landete im Textfeld.
- PC-Verlauf wird vor dem Löschen mit Nullen überschrieben; Teams-Logs vor 1970 unter Windows.

## 4.0.0 – 2026-10-22

- Umstieg von PyQt5 auf PySide6 (Qt 6), PyInstaller 6.22.3.
- Versionsangaben in der EXE, kein UPX mehr, optionale Signierung.
- Ein Rechtsklick-Menü für Timeline und Liste, Statussymbole für 3CX/ITM/Logs, Knopf für offene Tätigkeiten.
- Tests mit pytest.
