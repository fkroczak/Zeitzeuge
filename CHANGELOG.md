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
- **Schneller bei vollen Tagen:** Tag wechseln etwa doppelt so schnell (240 → 110 ms mit 3000–4000 Fensterwechseln am Tag), Timeline zeichnen 159 → 73 ms, das Neueinlesen alle 2 Minuten 248 → 118 ms. Die Spuren-Aufzeichnung (SSH, Sperren) zeichnet nicht mehr alle 30 Sekunden neu, wenn ein anderer Tag angezeigt wird. Details in `docs/PERFORMANCE-2026-11-10.md`.
- **Noch schneller bei offenen Verbindungen und langen Listen:** Bei offener RDP-Sitzung oder VPN liest Zeitzeuge nicht mehr alle 30 Sekunden alle Logs neu, sondern nur die geänderte Aufzeichnung. Die Tagesliste mit vollem PC-Verlauf (4200 Zeilen) baut sich in 0,12 statt 0,45 s auf. Vergangene Tage der Fensteraufzeichnung werden einmal am Tag im Hintergrund verdichtet und lesen sich dreimal so schnell. Die Spuren vom PC liegen je Tag in der Datenbank, eine Änderung schreibt nur noch ihren Tag (1 statt 13 ms).
- **Aktivitätsdetails als Textfelder:** Unter Einstellungen → Ansicht lassen sich die Werte (Kunde, Zeit, Details …) wieder in schreibgeschützten Textfeldern zeigen. Hineinklicken, Strg+A, Strg+C – so kopiert man einzelne Werte schneller heraus.
- **Fahrzeit zum Kunden berechnen:** In der Kundenliste hat jeder Kunde jetzt „Adresse und Fahrzeit“. „Berechnen“ fragt OpenStreetMap nach der Fahrzeit mit dem Auto vom Büro (aufgerundet auf 5 Minuten). Nach außen gehen dabei nur die beiden Adressen, und nur auf Knopfdruck. Die Startadresse (Büro) steht unter Einstellungen → Orte und Fahrzeiten. Termine des Kunden (über Name oder Mail-Domains) bekommen diese Fahrzeit als vermutete Hin- und Rückfahrt.
- **Menü Einstellungen → Orte und Fahrzeiten …** (neben der Kundenliste) öffnet Startadresse, Orte und Fahrzeiten direkt. Unter Datenquellen → Einrichten heißt der Eintrag jetzt „Fahrten: Orte und Fahrzeiten …“.
- **Orte und Kunden mit Fahrzeit:** Unter Einstellungen → Orte und Fahrzeiten trägst du Orte oder Kunden (aus der Kundenliste wählbar) mit ihrer Fahrzeit ein. Steht der Name im Ort, im Betreff oder beim Kunden eines Termins, plant Zeitzeuge genau diese Fahrzeit statt der ganzen Lücke (bis 90 Min.) davor. 0 Minuten heißt keine Fahrt, z. B. für den eigenen Besprechungsraum. Eine vermutete Fahrt reicht nie mehr in einen anderen Termin hinein.
- **Feinschliff am Aussehen:**
  - **Design „Wie Windows“** im Menü Ansicht: Hell oder Dunkel folgt der Einstellung von Windows. Das doppelte Häkchen „Dunkles Design“ im Menü Einstellungen fällt weg.
  - **Dunkle Titelleiste** unter Windows 10/11 im dunklen Design.
  - **Eine Hauptfarbe:** Im hellen Design sind aktiver Chip und Hauptknopf blau statt schwarz, wie im dunklen.
  - **Kacheln** oben bündig, „Nach Kunde“ zeigt ohne Einträge einen grauen Hinweis.
  - **Chips** zeigen die Anzahl als kleines Abzeichen neben dem Namen. Im ausgewählten Chip ist die Zahl jetzt lesbar (war weiß auf weiß).
  - **Tagesliste:** höhere Zeilen, Dauer einheitlich als „0:35 h“ und rechtsbündig.
  - **Aktivitätsdetails:** Werte als Text statt in Eingabefeldern (markieren und kopieren geht weiter).
  - **Zeitachse:** links unter der Legende keine halb abgeschnittene Uhrzeit mehr.
  - **Timeline:** feine Linien zwischen den Zeilen statt grauer Streifen (die Streifen gibt es weiter unter Ansicht → Zeilen der Timeline → „Zeilen abwechselnd hinterlegen“), Legende in normaler Schrift, an Tagen ohne Spuren ein Hinweis statt leerer Fläche.
  - **Tagesliste:** runde Farbpunkte wie in der Legende, die markierte Zeile hat links eine blaue Kante.
  - **Aktivitätstypen verwalten:** Farbpunkt je Typ, Suchfeld, Doppelklick ändert die Farbe.
  - **Arbeitszeiten:** Freie Tage zeigen nur „frei“, die Spalten „Pause von/bis“ erscheinen erst, wenn ein Tag eine Pause hat. „Montag übertragen“ ist ein Link.
  - **3CX, Zeiterfassung, Ticketsystem:** Zustand oben als farbiges Abzeichen, die Erklärung zur Anmeldung klappt bei Bedarf auf.
  - **Hinweise der Werkzeugleiste** nennen zuerst den Namen des Knopfs und erscheinen auch, wenn Zeitzeuge nicht das aktive Fenster ist.
- **Ruhigere Timeline und Statuszeile:** Ohne Zeiterfassung hat die Arbeitszeit keine eigene Zeile mehr. Sie steht als blaue Linie unter den Uhrzeiten und als zarte Fläche dahinter. Die Legende zeigt runde Farbpunkte in den Farben, die in der Zeile wirklich vorkommen (Telefon z. B. blau und orange). Der Knopf „… offen – jetzt eintragen“ unten rechts fällt weg, „Jetzt eintragen“ steht in der Kachel „Offen“. „Wiederherstellungsschlüssel einrichten“ ist ein Link statt eines umrandeten Knopfs.
- **Design im Menü Ansicht:** Hell, Dunkel oder eigene Farben. Das dunkle Design sieht jetzt aus wie Google Chrome im dunklen Modus (Grautöne statt fast Schwarz). Unter „Eigene Farben festlegen …“ wählst du Hintergrund, Flächen, Kopfleiste, Schrift und Akzent selbst.
- **Akzentfarbe Windows-Blau** statt Lila (Auswahl, Schalter, Häkchen). Hellgrau, Dunkelblau und Lila gibt es weiter unter „Eigene Farben“.
- **Benachrichtigungen abschaltbar:** Der Menüpunkt heißt jetzt „Nachfragen und Benachrichtigungen …“ (Einstellungen). Dort lässt sich die Meldung „Zeitzeuge läuft weiter“ beim Schließen des Fensters abschalten. Nachfragen im Infobereich und Feierabend-Erinnerungen stellst du wie bisher im selben Fenster ein.
- **Installationsassistent** (`Zeitzeuge-Setup.exe`, unter Releases): installiert ohne Adminrechte, aktualisiert eine vorhandene Installation, findet alte `ZeitZeuge.exe` (Desktop, OneDrive-Desktop, Downloads, Autostart) und ersetzt sie durch Verknüpfungen. Einstellungen und Datenbank werden weiter genutzt und vor dem Update gesichert. Die installierte Version startet schneller (kein Entpacken nach `%TEMP%`).
- **Ticket direkt im Feld suchen:** Beim Dokumentieren Kunde, Titel oder Benutzer ins Feld „Ticket“ tippen (ab 3 Zeichen). Die Treffer aus dem Ticketsystem erscheinen darunter, die Auswahl setzt die Ticketnummer (und den Kunden, wenn er noch fehlt). „Suchen …“ übernimmt den getippten Text.
- **Startbild:** Die EXE zeigt sofort beim Doppelklick ein Startbild mit Ladebalken und dem aktuellen Schritt („Programm entpacken …“, „Datenbank öffnen …“, „Fenster aufbauen …“), bis das Fenster steht. Bisher sah man mehrere Sekunden nichts und war versucht, Zeitzeuge ein zweites Mal zu starten.
- **Mit Windows starten:** neuer Schalter unter Einstellungen → Allgemein. Trägt Zeitzeuge für deinen Benutzer in den Autostart ein (im Infobereich, ohne Adminrechte) und zieht den Eintrag nach, wenn die EXE umzieht. Die Verknüpfung in `shell:startup` braucht es nicht mehr.
- **Einrichtungsassistent, 3CX und Ticketsystem:** „Weiter“ geht erst nach „einrichten und anmelden“ (oder wenn du das Häkchen „verwenden“ herausnimmst). Der Anmeldeknopf ist dort der Hauptknopf.
- **Hell/Dunkel im Menü Ansicht:** „Dunkles Design“ lässt sich jetzt direkt im Menü Ansicht umschalten, nicht nur unter Einstellungen.
- **Anruffarben je Richtung:** Unter Ansicht → Zeilen der Timeline → Farben der Zeilen (und per Rechtsklick auf „Telefon“ in der Legende) gibt es getrennte Farben für eingehende und ausgehende Anrufe. Eine bisher gewählte Farbe für die ganze Zeile bleibt für die andere Richtung erhalten.
- **Zuschlag ignorieren:** neuer Haken neben Kulanz und Reise beim Dokumentieren und im Fenster „Im Ticketsystem buchen“ (dort mit Grund, vorbelegt „Zuschlag ignoriert“). Beim Buchen setzt Zeitzeuge im Ticketsystem „Zuschlag ignorieren“, auch beim Buchen aus dem Tagesabschluss.
- **Ticket beim Dokumentieren suchen:** Neben dem Feld „Ticket“ sitzt der Knopf „Suchen …“. Er öffnet die Ticketsuche des Ticketsystems (vorbelegt mit dem Kunden), ein Doppelklick übernimmt das Ticket. So steht das passende Ticket schon vor dem Buchen in der Tätigkeit. Nur sichtbar, wenn das Ticketsystem eingeschaltet ist.
- **Neues Design**: ruhige Zink-Grautöne in Hell und Dunkel, runde Ecken an Feldern, Knöpfen, Menüs und Timeline-Balken, Karten mit feinem Rand, Hauptknopf in Textfarbe, Violett für Fokus und Links.
- **Kennzahlen über der Timeline:** Erfasst (von Soll, mit Balken), Offen („Jetzt eintragen“), Vorschläge („Ansehen“), Buchungsquote gleich hinter Erfasst (heute | 7 Tage als große Zahl in der Farbe der Stufe, bisher in der Statuszeile; Klick öffnet den Wochenabschluss) und Nach Kunde. Über der Tagesliste Chips für die Ansichten Alle, Offen / Doku, Vorschläge, Telefonate und Arbeitsblöcke.
- **Kunden & Erkennung:** neues Fenster mit Kundenliste links (Suche, Kürzel, Merkmale, Stunden der letzten 7 Tage) und Merkmalen als Chips rechts, je Art mit Trefferzahl. Neue Merkmale: **Ordner und Dateipfade**, **Rechnernamen und Hosts** (auch `*.kunde.local`), **IP-Adressen und -Bereiche** (CIDR). Dazu Kundennummer und der Schalter „Kalendertermine“. Domains aus dem Browser-Verlauf zählen wie Mail-Domains.
- **Zeitraum nachtragen:** Beim Ziehen in der Timeline zeigt das Fenster, was Rechner, Kalender, Anrufe und Verbindungen in dieser Zeit sagen. Ein Termin oder Anruf, der den Zeitraum überwiegend füllt, wird als Kunde und Text vorgeschlagen.
- **Leerlauf-Nachfrage:** „Du warst 42 Min. nicht am Rechner (10:15–10:57). Was hast du gemacht?“ mit Chips zur Schnellauswahl.
- **Jede Datenquelle hat ihr eigenes Einrichtungsfenster** mit eigenem Schalter: Sophos Connect, FortiClient, weitere VPN-Logs (OpenVPN …), Outlook und Teams-Anrufe sind jetzt getrennt (bisher teilten sich je mehrere ein Fenster). Auch TeamViewer und RDM lassen sich im Fenster ein- und ausschalten.
- **RDM Better** als Datenquelle: Zeitzeuge liest die Starts aus `%LOCALAPPDATA%\RDM Better\launcher.log` (Ziel, Benutzer; Zeit in UTC, wird in Ortszeit umgerechnet). Das Ende kommt aus der mstsc-Aufzeichnung.
- **Remotedesktop (mstsc)** als Datenquelle: Zeitzeuge prüft alle 30 Sekunden, welche Remotedesktopverbindungen offen sind, und zeigt sie mit Ziel, Beginn und Ende wie die Verbindungen aus RDM.
- **FortiClient** liest `logs\trace\FortiVPN_1.log`: jede Verbindung mit ihrem Namen aus FortiClient (z. B. „Kunde Weber“), Beginn und Ende; Ruhezustand beendet sie. Bisher kamen aus Sophos' `charon.log` nur Zeiten ohne Namen; das bleibt als Ersatz, wenn die Datei fehlt.
- **Spuren vom eigenen PC** als neue Datenquellen, jede einzeln schaltbar und mit eigenem Fenster:
  - **PC gesperrt / Ruhezustand:** Sperren prüft Zeitzeuge alle 30 Sekunden selbst. Ruhezustand, ausgeschaltet und abgemeldet liest es aus dem Windows-Ereignisprotokoll, auch für Zeiten, in denen Zeitzeuge nicht lief. Eigene Zeile „PC-Zustand“.
  - **SSH und PowerShell:** offene Sitzungen von ssh.exe, PuTTY, KiTTY, plink, WinSCP und PowerShell-Fernsitzungen (Enter-PSSession) mit Ziel, Beginn und Ende, bei den Verbindungen wie RDM.
  - **Zuletzt geöffnete Dateien:** Dateiname und Uhrzeit aus „Zuletzt verwendet“ von Windows, Zeile „Dateien & Web“.
  - **Browser-Verlauf** von Edge und Chrome: nur Domain und Ticketnummer, keine Adressen und keine Seitentitel. Suchmaschinen und Anmeldeseiten fallen weg.
  - **WLAN:** mit welchem Netz der PC verbunden war, eigene Zeile „WLAN“.
  - Diese Spuren lösen keine Nachfrage „Was hast du gemacht?“ aus und zählen nicht im Tagesabschluss (SSH-Sitzungen schon, wie Verbindungen).
- **Netzwerk statt nur WLAN:** Zeitzeuge merkt sich das Netzwerkprofil von Windows, auch über Kabel und Dockingstation (Büro, Homeoffice, Kundennetz). VPN-Adapter zählen nicht. Ein Netz lässt sich einem Kunden zuordnen (neue Spur „Netzwerk“ in der Kundenliste).
- **Beantwortete Mails:** Eingegangene Mails, auf die du geantwortet oder die du weitergeleitet hast, stehen beim Eingang als „Mail beantwortet“ in der Zeile Outlook (Einstellung im Outlook-Fenster).
- **Teams-Chats** als eigene Datenquelle (standardmäßig aus): aus dem Postfach über das klassische Outlook, nur Uhrzeit, eigene Nachricht ja/nein und die Domains der Gesprächspartner. Blöcke „Chat mit kunde.de“ in der Zeile Outlook.
- **Fahrten (vermutet):** Vor und nach einem Outlook-Termin mit Ort schlägt Zeitzeuge die Lücke ohne PC-Arbeit als Hin- und Rückfahrt vor (10–90 Minuten), ebenso beim Wechsel in ein Kundennetz. Zeitzeuge fragt danach und schlägt „Fahrt / Reise“ vor.
- **Devolutions Password Manager:** In der PC-Aktivität heißt `devolutions.exe` jetzt „Password Manager“, die Zuordnung ohne KI ordnet die Zeit als „Zugangsdaten / Sicherheit“ ein.
- **Zeilen der Timeline verschieben:** Namen links in der Legende anfassen und an die gewünschte Stelle ziehen; eine blaue Linie zeigt, wo die Zeile landet. Die Reihenfolge bleibt gespeichert, **Zeilen der Timeline → Reihenfolge zurücksetzen** stellt den Standard wieder her. PC-Aktivität bleibt oben, Remote / Weitere unten.
- **Pausen bei den Arbeitszeiten:** je Wochentag eine Pause (von – bis). Sie ist in der Timeline abgedunkelt und zählt nicht als Arbeitszeit. Das Fenster ist breiter und nicht mehr gestaucht.
- Einstellungen: „Aktive Fenster aufzeichnen“, Fenster-Filter und Leerlauf stehen jetzt unter **Datenquellen**. Knöpfe heißen nach dem, was sie tun („Beenden …“, „Exportieren …“, „Im Explorer zeigen“ statt immer „Öffnen …“). **Zeitzeuge beenden** fragt vorher nach.
- **Bessere Kundenerkennung:** Anrufer (Ansprechpartner oder Kollegen) werden nicht mehr als Kunde vorgeschlagen; der Kunde eines Telefonats kommt nur aus der Kundenliste. Gemessen an echten Buchungen sanken falsch vorgeschlagene Kunden im Tagesabschluss von 40 % auf 14 % der gebuchten Zeit.
- **Stichwörter je Kunde:** Text in Fenstertitel, Betreff oder Verbindungsname („Lindenhof“, „LDH-“) ordnet den Eintrag dem Kunden zu, auch in Arbeitsblöcken am PC, in der Zuordnung ohne KI und im Tagesabschluss. Zeitzeuge lernt Stichwörter aus deinen Ticketsystem-Buchungen oder schlägt sie unter „Neu entdeckt“ vor.
- **Regeln mit mehreren Bedingungen** (z. B. Programm *und* Fenstertitel), dazu Spalte „7 Tage“ mit den Treffern jeder Regel und eine Vorschau „Passt auf 14 Einträge der letzten 7 Tage, z. B. …“ beim Bearbeiten.
- **Kollegen erkennen:** Durchwahlen, Handys von Kollegen und die Zentrale erkennt Zeitzeuge selbst. Anrufe von Kollegen bleiben sichtbar und werden nachgefragt, nur der Kollege ist nie der Kunde.
- **Kundenliste lernt aus dem Ticketsystem:** Telefonnummern, TeamViewer-IDs, RDM-Einträge und VPN-Verbindungen, die immer wieder mit Buchungen auf denselben Kunden zusammenfallen, ordnet Zeitzeuge von selbst zu. Heißt ein Kunde im Ticketsystem anders, schlägt die Kundenliste unter „Neu entdeckt“ das Umbenennen vor.
- **Maus in der Timeline:** Mit links ziehen markiert einen Zeitraum und öffnet „Tätigkeit nachtragen“ mit genau diesen Zeiten. Mit rechts ziehen zoomt auf den Zeitraum (bisher die linke Taste). Einfacher Rechtsklick öffnet weiter das Menü, ESC bricht das Ziehen ab.
- **Tagesabschluss** (Menü Ansicht, Wochenabschluss, Meldung bei Feierabend): Zeitzeuge stellt den Tag aus eigenen Tätigkeiten, Verbindungen, Telefonaten, KI-Vorschlägen, Regeln und PC-Aktivität zu Blöcken je Kunde zusammen, mit Ticket (aus Fenstertiteln oder zuletzt für den Kunden benutzt) und kurzem Tickettext. Ein Klick dokumentiert alles und bucht die Zeilen mit Ticket nacheinander im Ticketsystem. Oben steht, wie viel Prozent der Personalzeit danach erfasst sind. Ohne Rückfrage werden nur sichere Tickets gebucht. **Erkennung messen …** vergleicht die Vorschläge der letzten 20 Tage mit deinen echten Buchungen.
- Zwei Menüs: **Ansicht** (Tagesliste, Zeilen der Timeline, Zeitraum, Übersichten, Design) und **Einstellungen** als eigenes Fenster mit Bereichen, Suche und Datenquellen als Kacheln mit Zustand. Schnellzugriffe (Tag, Heute, Ganzer Tag, Arbeitszeit …) bleiben in der Werkzeugleiste.
- **Mehrzeilige Timeline:** Überschneiden sich Einträge in einer Zeile (Ticketsystem, Dokumentation, Telefon, Outlook, VPN, TeamViewer …), steht der spätere in einer weiteren Zeile darunter statt verdeckt. Was nur aneinanderstößt, bleibt in einer Zeile.
- **Buchungsquote wie im Ticketsystem:** gebucht ÷ gestempelt, gebucht mit der gerundeten Arbeitszeit jeder Buchung aus dem Ticketsystem, Überschneidungen zählen voll. Bisher wurden Buchungen zeitlich zusammengelegt und ungerundet gezählt (Beispiel 19.10.: 88 % statt 96 %). „Ticketsystem gebucht … h“ in der Statuszeile zeigt dieselbe Zahl.
- **Buchungsquote in der Statuszeile** gilt für den gewählten Tag: Am 02.11. steht dort „Quote 02.11. … · 7 Tage …“ mit den 7 gestempelten Tagen bis zu diesem Tag. Für heute bleibt es „Quote heute“.
- Hilfe zu den Ansichten der Tagesliste (Zusammengefasst, Einzeln …) mit Beispielen, F1.
- Symbole überall, Datenquellen mit Zeichen in der Farbe des Herstellers.
- Anrufe: eingehend blau ↙, ausgehend orange ↗. Die Richtung aus 3CX wird zuverlässiger erkannt.
- Nachfrage nach Abwesenheit am PC: ab 15 Minuten ohne Eingabe (einstellbar) fragt Zeitzeuge bei der ersten Eingabe, was war. Schnellauswahl Telefonat, Besprechung, Vor Ort, Fahrt / Reise, Pause.
- Kulanz und Reise an jeder Tätigkeit, beim Buchen im Ticketsystem übernommen. Neue Kategorien „Vor-Ort-Einsatz“ und „Fahrt / Reise“.
- Timeline kräftiger: weniger Transparenz bei Regeln, KI und offenen Einträgen, bunte Programmfarben, Ticketsystem-Buchungen blau statt grau.
- Daten verschlüsselt in einer Datenbank statt vieler Dateien, PIN beim Start (schützt auch vor Domänen-Admins).
- Ticketsystem: gebuchte Zeiten lesen und abgleichen, Buchungen über die Schnittstelle, Buchungsquote und Wochenabschluss, Prüfung bei Feierabend.
- Outlook (Termine, Teams-Besprechungen, gesendete Mails) und Teams-Anrufe als Quellen.
- Kundenliste mit allen Spuren, Lernen aus Korrekturen.
- Eintragen: Textbausteine, letzte Texte je Kunde, Ticket-Format und Ticketnummer-Vorschlag; Ticketzeile mit echten und abgerechneten Zeiten.
- Abrechnungstakt je Kunde (z. B. 15 Minuten), PC-Verlauf automatisch löschen.
- Zwei PCs: Export/Import (z. B. für die PAW), PAW-Modus ohne Edge, Ordner-Variante der EXE für Rechner mit EDR.
- Personalzeit als eigene Zeile mit Beginn und Ende.
- Tagesliste: neue Ansicht **Telefonate** (Menü Ansicht): nur Anrufe aus 3CX und Teams, jeder einzeln.
- Einstellungen: Einrichtungsassistent oben auf „Datenquellen“; Vorschau unter „Ansicht“ kleiner und schemenhaft, beim Darüberfahren kräftig.
- Einstellungen → **Fehlersuche & Analyse**: Mitschnitte (3CX, Ticketsystem, Zeiterfassung, Buchung im Ticketsystem) und die 3CX-Direkt-Abfrage stehen jetzt dort statt in den Einrichtungsdialogen.
- Jede Zeile der Timeline ausblendbar; „Regeln“ heißt jetzt „Zuordnung ohne KI“.
- Design „Metro Klar“ (hell und dunkel), Werkzeugleiste in Klar-Farben, Timeline ohne senkrechte Scrollleiste.
- Nachfragen zu mehr Themen: Arbeitsblöcke am PC (z. B. M365-Admin, Remotedesktop), Teams-Besprechungen mit erkennbarer Teilnahme, Mails an Kunden aus der Kundenliste; auf Wunsch angezeigte Zugangsdaten.
- Keine doppelten Nachfragen mehr: Was zum selben Kunden zur selben Zeit gehört (VPN + RDP + Telefonat), ist eine Nachfrage. Beantwortetes, Ignoriertes und Zurückgestelltes erkennt Zeitzeuge über Zeitraum und Kunde wieder, auch bei kürzer eingetragener Zeit oder später nachgeladenen Logs.
- Einstellungen → **Ansicht** mit Vorschau: alle Darstellungs-Einstellungen auf einer Seite, darüber Timeline und Tagesliste eines Beispieltags. Beim Darüberfahren über einen Schalter oder beim Durchgehen einer Auswahl zeigt die Vorschau die Änderung schon vorher, ohne zu speichern. Erklärtexte bleiben in breiten Fenstern links und werden nicht mehr abgeschnitten.
- PC-Aktivität als Arbeitsblöcke: Fenster werden je Tätigkeit zusammengefasst (Zuordnung ohne KI, sonst Programm), kurze Sprünge zählen zur Haupttätigkeit, wenn es danach dort weitergeht oder der Kunde passt. Beschriftete Blöcke in gedeckten Farben, Hinweis mit Anteilen der Programme, Fensterwechseln und Fokus. Umschalten zwischen Blöcken und jedem Fenster einzeln über **Ansicht → PC-Aktivität als Arbeitsblöcke**, per Rechtsklick auf die Legende oder unter Einstellungen → Allgemein.
- Timeline startet in der Arbeitszeit (merkt sich „Ganzer Tag“), offene Einträge dicht hintereinander als ein Block „? 3 offen“, keine abgeschnittenen Mini-Beschriftungen mehr.
- Aufgeräumt: Leere Zeilen der Timeline verschwinden von selbst, „Zuordnung ohne KI“ fließt in die Zeile Dokumentation ein (eigene Zeile standardmäßig aus). Menü **Ansicht** von rund 30 auf 13 Einträge: Zeilen der Timeline als Untermenü und per Rechtsklick auf die Legende, Dunkles Design und Datenquellen direkt im Pfeil-Menü der Einstellungen. Tagesliste ohne doppelte Details, kürzere Statuszeile, Zoom per STRG + Mausrad statt Lupen-Knöpfen.
- Besser lesbar nach 16 UI-Design-Regeln: Spaltenköpfe und Menü-Überschriften ohne Großbuchstaben, nur noch normal und fett, kräftigere Rahmen um Felder und Knöpfe (3 : 1), Gruppen ohne Rahmen, Erklärtexte mit mehr Zeilenabstand, eine Schrift auch in der Timeline. Sechs Timeline-Farben (u. a. RDP, Mail gesendet, Teams-Anruf) etwas kräftiger, damit sie sich in beiden Designs abheben; selbst gewählte Farben bleiben.
- Zeiterfassung: Anmeldung ohne Edge, eigene Buchungen aus dem alten Backend, fehlerhafte Buchungen werden gemeldet.
- Nachfragen ab 1 Minute, Schwelle je Art einstellbar.
- Ladeanzeige: drehender Kreis mit Text neben „Arbeitszeit“ und Streifen über die ganze Breite; Timeline springt beim Laden nicht mehr.
- Versionsnummer zählt von selbst (4.1.0, 4.1.1, …); steht im Fenstertitel, unter **Info**, in fehler.log, in der EXE und im Namen der Downloads.

- **Eigene Farben je Zeile der Timeline:** Rechtsklick auf den Zeilennamen links → „Farbe für … ändern“, oder Ansicht → Zeilen der Timeline → Farben der Zeilen. Gilt für Balken, Legende und Tagesliste; „Standardfarbe“ setzt zurück.
- **Remotedesktop (mstsc) aus dem Windows-Ereignisprotokoll:** Zeitzeuge liest zusätzlich `Microsoft-Windows-TerminalServices-RDPClient/Operational` (Aufbau 1024, Trennung 1026). Das füllt Zeiten, in denen Zeitzeuge nicht lief, und macht Beginn und Ende sekundengenau; mit der eigenen Aufzeichnung wird es zu einer Sitzung zusammengeführt. Abschaltbar unter Datenquellen → Remotedesktop (mstsc).

### Behoben
- **Zeitzeuge wirkte aufgehängt nach „Suchen …“ beim Ticket im Nachfrage-Fenster:** Die Ticketsuche konnte hinter dem Nachfrage-Fenster (immer im Vordergrund) landen und sperrte dabei das ganze Programm. Jetzt liegt sie obenauf und sperrt nur das Nachfrage-Fenster.
- **Kachel Buchungsquote** saß tiefer als die anderen Kacheln; Überschrift und Zahlen stehen jetzt auf einer Höhe.
- **ITM: Nachträglich gestempeltes Gehen kam nicht an.** Ein vergangener Tag wurde pro Sitzung nur einmal gelesen, und Aktualisieren (F5) las ITM gar nicht neu. Lief Zeitzeuge z. B. über den Ruhezustand weiter, blieb der Stand vom Mittag („13:21 – jetzt“). Jetzt liest F5 auch ITM neu, ein Tag mit fehlendem Gehen wird beim Anzeigen erneut gelesen (höchstens alle 5 Minuten), und nach dem Tageswechsel liest Zeitzeuge den Vortag noch einmal.
- **Personalzeit: „13:21 – jetzt“ an einem vergangenen Tag.** Fehlte in ITM das Gehen, lief der Abschnitt bis Mitternacht und alles danach galt als „nicht gebucht“. Jetzt steht er gestrichelt als „13:21 – Gehen fehlt“ bis zum geplanten Feierabend da, zählt nicht als Personalzeit (wie bei ITM) und erzeugt keine Lücke „nicht gebucht“.
- **Anrufe:** Zwei Anrufe in derselben Minute an dieselbe Nummer (z. B. 13:23 min und 0:02 min um 14:40) zählten als ein Anruf, der kurze überschrieb das Gespräch. Jetzt bleiben beide; Zeitzeuge unterscheidet sie an der Dauer. Fehlende Anrufe kommen beim nächsten Lesen der 3CX-Liste dazu, solange sie dort noch stehen.
- **Startbild bei Bildschirmskalierung (z. B. 125 %):** Es sprang beim Start aus der Mitte klein nach links oben. Zeitzeuge ist jetzt von Anfang an DPI-bewusst und zeigt ein scharfes Startbild in passender Größe, mittig.
- **Matrix42: Anmeldefenster schloss sich, bevor man angemeldet war.** Ein abgelaufenes Token im Edge-Profil galt schon als „angemeldet“, das Fenster ging nach zwei Sekunden zu, und danach kam bei allem Fehler 406. Jetzt gilt die Anmeldung erst, wenn Matrix42 eine angemeldete Abfrage der Seite erfolgreich beantwortet hat. Bleibt es bei 406, zeigt Zeitzeuge „Anmeldung nötig“ statt eines Fehlers.
- **Matrix42: „Fehler 406“ beim Ticket suchen, Buchen und Lesen behoben.** Zeitzeuge nahm für seine Abfragen das Token aus dem Edge-Profil, das abgelaufen sein kann. Jetzt meldet es sich genauso an wie die Matrix42-Seite selbst (gleiche Kopfzeilen). Kommt trotzdem 406, lädt es die Seite neu und versucht es einmal. Im Fehlertext steht jetzt auch die Antwort von Matrix42.
- **Matrix42: „Fehler (Inspected target navigated or closed)“ in Dauerschleife behoben.** Leitet die Matrix42-Seite beim Lesen über die automatische Anmeldung weiter (z. B. altes Token nach Netzwechsel, dann Fehler 406), liest Zeitzeuge auf der neuen Seite weiter, statt Edge neu zu starten und es mit immer längeren Pausen erneut zu versuchen. Die Schnittstelle wartet außerdem auf die fertige Kalenderseite, bevor sie das Token benutzt.
- **Nächtlicher Audit 06.11.2026** (Details: `docs/AUDIT-2026-11-06.md`):
  - **Matrix42: keine Doppelbuchung mehr nach Zeitüberschreitung.** War die Buchung schon abgeschickt, meldet Zeitzeuge jetzt „Vielleicht gebucht … bitte zuerst in Matrix42 nachsehen“ und sperrt den Knopf, statt „Nicht gebucht“ zu zeigen.
  - **Tätigkeit auf einen anderen Tag verschieben** verliert sie nicht mehr, wenn das Speichern scheitert. Die Fehlermeldung im Buchungsfenster bleibt stehen. Ein Matrix42-Termin „10:00 - 10:00“ wird nicht mehr zur 24-Stunden-Buchung.
  - **Schneller:** Tagesabschluss öffnet in 0,16 s statt 0,73 s, das Hauptfenster steht rund 40 ms früher (Symbole werden nur einmal gezeichnet). Das Windows-Ereignisprotokoll für Remotedesktop wird im Hintergrund gelesen statt alle 2 Minuten im Fenster.
  - **Kleine Fenster und 150/200 % Anzeige:** Die Kacheln unter Einstellungen → Datenquellen nehmen so viele Spalten, wie passen (keine waagerechte Scrollleiste mehr), lange Pfade werden mit „…“ gekürzt, die Kundenliste passt auf Full HD mit 200 %.
  - **Einheitliches Aussehen:** feste Abstände (4/8/12/16/24/32/48 px), vier Schriftgrößen und vier Rundungen für alle Fenster (`docs/DESIGN-TOKENS.md`). Tooltips der Timeline sehen aus wie alle anderen.
  - **Sicherheit:** Edge-Fenster für 3CX, ITM und Matrix42 nehmen keine DevTools-Verbindungen fremder Webseiten mehr an; der Mitschnitt schwärzt auch SAML-Anmeldungen; Outlook-Ordner mit ’ im Namen funktionieren.
  - **TeamViewer: Sommer- und Winterzeit automatisch.** TeamViewer speichert UTC, Zeitzeuge addierte bisher fest eine Stunde – im Sommer standen Verbindungen eine Stunde zu früh. Jetzt rechnet es jede Zeit mit der Sommer- oder Winterzeit ihres Datums um (abschaltbar im TeamViewer-Fenster).
  - **Im Infobereich sparsamer:** Liegt Zeitzeuge im Infobereich oder ist minimiert, liest es die Logs weiter (für die Nachfragen), zeichnet Timeline und Liste aber erst beim Öffnen.
  - **Spuren-Verlauf aufbewahren:** neue Einstellung unter Einstellungen → Daten & Schutz (Standard 365 Tage). Ältere Spuren vom PC, Remotedesktop- und VPN-Verbindungen löscht Zeitzeuge einmal am Tag. Tätigkeiten bleiben.
  - **Regeln und Fenster-Filter** passen auf kleine Bildschirme (Inhalt scrollt, Knöpfe bleiben unten). „Im Explorer zeigen“ wird nicht mehr abgeschnitten.
  - **Texte:** „Kunden & Erkennung“ heißt jetzt wie im Menü „Kundenliste“, „M42“ in der Statuszeile „Matrix42“; fünf lange Erklärungen gekürzt.
- **Einstellungen → Ansicht hing bis zu einer Minute:** Die Vorschau maß bei jeder Zelle der Beispielliste alle Spalten neu. Mit „PC-Verlauf in der Liste“ und Fenstern einzeln sind das über 100 Zeilen bei jedem Darüberfahren. Jetzt einmal nach dem Füllen (2,6 s → 0,1 s).
- **Einstellungsfenster träge:** Die Vorschau zeichnet nur noch, wenn sie zu sehen ist, beim schnellen Darüberwischen nur für die Zeile, auf der die Maus bleibt. Die Kacheln der Datenquellen bauen sich alle 3 s nur noch neu auf, wenn sich ihr Zustand geändert hat. Seitenwechsel 60–80 ms → unter 30 ms.
- **Erfasst zeigt die Personalzeit:** „5:53 h von 7:18 h gestempelt“ statt „von 8:00 h“ (Soll). Ohne Zeiterfassung steht dort die eingestellte Arbeitszeit („… Arbeitszeit“).
- **Ruhigere Kennzahlen-Leiste:** Die Kacheln sind nur so breit wie ihr Inhalt, „Nach Kunde“ nimmt den Rest und zeigt ganze Kunden plus „+2“, statt mitten im Namen abzuschneiden (alle im Hinweis). „Vorschläge“ erscheint nur, wenn welche warten.
- **Ansichten der Tagesliste nur noch als Chips:** Über der Liste stehen alle acht Ansichten (auch „Zuordnung ohne KI“ und „Buchungsabgleich“), die aktive ist markiert. Im Menü **Ansicht** stehen sie nicht mehr doppelt.
- **Timeline mit Rahmen**, damit man sieht, wo sie endet. Die Kachel Buchungsquote hat die Überschrift „Buchungsquote“ wie die anderen Kacheln. Rahmen der ausgewählten Timeline und Ladebalken sind dunkelgrau statt lila.
- **Farben im Hinweis der Timeline:** Vor jedem Eintrag steht ein Quadrat in der Farbe seines Balkens, so siehst du, aus welcher Zeile er kommt.
- **Schmales Fenster:** Die Chips über der Tagesliste („Alle“, „Offen / Doku“ …) rücken in eine zweite Zeile, statt das Fenster auf mindestens ~600 px Breite festzuhalten. Damit passt Zeitzeuge wieder in einen halben Bildschirm und bei 200 % Anzeige.
- **Schnellerer Start und flüssigeres Blättern:** Zeitzeuge startet etwa viermal so schnell (Fenster mit Daten nach 0,4 s statt 1,6 s), weil das KI-Paket erst bei der ersten KI-Anfrage geladen wird. Zeichnen des heutigen Tags mit vielen Fensterwechseln braucht ein Drittel der Zeit, Tageswechsel halb so lange (Messung in `docs/BEWERTUNG-webview-asynccron-threads.md`).
- **Nachfrage „Was hast du gemacht?“ zeigt das Datum** und lässt es ändern (Kalender), wie beim Nachtragen.
- **Das Feld „Tätigkeit“ hat wieder einen Rahmen** und ist im dunklen Design als Eingabefeld erkennbar.
- **Haken-Kästchen (z. B. „Kulanz“, „Reise / Anfahrt“) sind im dunklen Design sichtbar**: mit Rahmen, angehakt blau mit Haken.
- **Symbol in der Taskleiste** fehlte: Das Logo kommt jetzt zusätzlich aus PNG/SVG (nicht nur aus der .ico), Dialoge vor dem Hauptfenster tragen es auch, und Windows ordnet Zeitzeuge eine eigene Kennung zu.
- **Timeline wird nicht mehr abgeschnitten:** Sie ist mindestens so hoch, dass alle Zeilen in kleiner Höhe passen, und höchstens so hoch wie alle Zeilen in voller Höhe. Mehr oder weniger Fensterhöhe bekommt die Tagesliste.
- **Trennleiste zwischen Timeline und Liste:** Beim Ziehen zeigt eine gestrichelte Linie die neue Größe, neu gezeichnet wird erst beim Loslassen. Auch beim Ändern der Fenstergröße zeichnet die Timeline erst, wenn die Größe kurz stillsteht – das Ziehen ruckelt nicht mehr.
- **Zoomen geht sofort:** Reinzoomen (STRG + Mausrad, rechts ziehen, Ganzer Tag/Arbeitszeit) las bisher jedes Mal alle Daten neu und baute die Tagesliste neu auf (rund 3 Sekunden). Jetzt wird nur neu angeordnet; schnelles Drehen am Mausrad zeichnet nur einmal.
- **Mauszeiger:** Nach dem Darüberfahren über die Legende blieb überall die Hand statt des Pfeils.
- **VPN doppelt:** Derselbe FortiClient-Tunnel stand zweimal da (einmal mit Namen, einmal nur „FortiClient“). Die namenlose Kopie fällt jetzt weg, auch alte Einträge im Archiv.
- **Einstellungen → Datenquellen:** „Aktive Fenster aufzeichnen“ und „Fenster-Filter“ standen doppelt (Kachel und darunter). Jetzt nur noch auf der Kachel; darunter bleibt „Leerlauf nach“.
- Tagesliste: Die Spalte „Dauer“ zeigt nur noch die echte Dauer („35 min“) statt „35 min → abgerechnet 0:45 h“. Die abgerechnete Zeit steht im Hinweis beim Darüberfahren und weiter in der Statuszeile.
- Einstellungen: kein Fokusrahmen mehr um den gewählten Bereich links. Der Datenordner steht mit `\` statt gemischten Schrägstrichen da, lange Pfade werden in der Mitte gekürzt (ganzer Pfad im Tooltip).
- **Zeile Dokumentation leer** und wiederholt „Interner Fehler (AttributeError)“, sobald ein PC-Arbeitsblock noch offen war: der Text der Nachfrage las die Programmliste des Blocks als Einträge. Auch die Nachfrage selbst stürzte deshalb ab.
- Ticketsystem: „Beim Ticketsystem anmelden“ öffnete das Fenster nur kurz und schloss es gleich wieder. Es bleibt jetzt offen, bis die Anmeldung wirklich geklappt hat.
- Absturz beim Start, wenn „3CX direkt auslesen“ eingeschaltet ist.
- Anrufe: ein Gespräch wurde von einem Versuch in derselben Minute überschrieben.
- Eintragen: Beschriftung des Merken-Hakens landete im Textfeld.
- PC-Verlauf wird vor dem Löschen mit Nullen überschrieben; Teams-Logs vor 1970 unter Windows.
- Aktualisieren (F5) lädt jetzt auch die 3CX-Anrufliste sofort neu; neue Anrufe kamen sonst erst nach bis zu 6 Minuten. Die Liste wird außerdem alle 2 statt 5 Minuten neu geladen.
- Ticketsystem: Aktualisieren holt die Einträge der Woche wirklich neu (vorher zeigte die Kalenderseite oft noch den alten Stand, bis 30 Minuten lang) und versucht nach einem Aussetzer wieder die Schnittstelle.

## 4.0.0 – 2026-10-22

- Umstieg von PyQt5 auf PySide6 (Qt 6), PyInstaller 6.22.3.
- Versionsangaben in der EXE, kein UPX mehr, optionale Signierung.
- Ein Rechtsklick-Menü für Timeline und Liste, Statussymbole für 3CX/Zeiterfassung/Logs, Knopf für offene Tätigkeiten.
- Tests mit pytest.
