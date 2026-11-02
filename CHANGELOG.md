# Änderungen

Alle sichtbaren Änderungen an Zeitzeuge, die neueste Version oben.

Versionsnummern nach [Semantic Versioning](https://semver.org/lang/de/): **MAJOR.MINOR.PATCH**
- **MAJOR**: Daten lassen sich mit einer älteren Version nicht mehr lesen (z. B. neues
  Speicherformat), oder die Bedienung ändert sich grundlegend.
- **MINOR**: neue Funktionen, alles Bisherige geht weiter.
- **PATCH**: nur Fehlerbehebungen.

Die Nummer steht nur in `version.py`. Eine neue Version: Nummer dort erhöhen, Abschnitt
hier unter „Unveröffentlicht“ umbenennen, dann Tag `v…` setzen (siehe README, „EXE bauen“).

## Unveröffentlicht

## 5.0.0 – 2026-11-02

**Achtung:** Die Daten liegen jetzt verschlüsselt in einer Datenbank. Ältere Versionen (4.x)
können sie nicht mehr lesen.

### Neu
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
- Versionsnummer mit Buildnummer, Commit und Datum im Fenstertitel, unter **Info** und in fehler.log.

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
