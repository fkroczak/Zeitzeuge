# Übergabe Version 4.0.0: PySide6, Build, Aufteilung, pytest

Funktionen und Aussehen bleiben gleich. Einzige sichtbare Änderung: **Info** zeigt „Version 4.0.0“.

## Was gemacht wurde

| Bereich | Änderung | Warum | Rückgängig |
|---|---|---|---|
| Qt-Bindung | PyQt5 5.15 → **PySide6 6.12** (nur `PySide6-Essentials`) | Qt 5 bekommt keine freien Updates mehr; PySide6 ist LGPL statt GPL (wichtig bei Weitergabe der EXE) | Commit `Umstieg von PyQt5 auf PySide6` zurücknehmen |
| Aussehen unter Qt 6 | Drehfelder (Zeit/Datum/Zahl) so breit wie vorher, helles App-Schema gewinnt gegen ein dunkles Windows-Schema, `Accent`-Farbe = Design-Akzent, Umgehung eines Qt-6.12-Fehlers beim Textabstand in Drehfeldern | Ohne das wären Felder breiter und Farben teils vom Windows-Schema bestimmt | `theme.py` (`AppStyle.sizeFromContents`, Stylesheet `QAbstractSpinBox`) |
| Build | Versionsnummer nur in `version.py`; Versionsangaben in der EXE; **kein UPX** mehr; PyInstaller 6.22.3; Tag `v…` muss zu `version.py` passen | UPX und fehlende Versionsangaben lösen oft Fehlalarme von Virenscannern aus | `ZeitZeuge.spec` |
| Signieren | CI signiert die EXE, sobald die Secrets `SIGN_PFX_BASE64` und `SIGN_PFX_PASSWORD` hinterlegt sind; sonst Hinweis, kein Fehler | Nur eine Signatur beseitigt Fehlalarme und SmartScreen-Warnungen dauerhaft. Ein Zertifikat muss gekauft werden (z. B. OV-Code-Signing oder Azure Trusted Signing) | Schritt „EXE signieren“ in `build.yml` |
| Aufteilung | `main_timeline.py` 2.200 → 430 Zeilen. Neu: `theme.py`, `config_defaults.py`, `app_menus.py`, `app_daylist.py`, `app_docs.py`, `app_readers.py`, `app_tray.py` | Übersichtlicher, Design an einer Stelle (Farb-Tokens und Stylesheet unverändert, ein neues Design braucht nur neue Werte) | reine Verschiebung, Code per AST-Vergleich gleich |
| Tests | `pytest` statt 18 Einzelschritte. Logik-Tests als echte Testfunktionen (Fehler pro Fall), Qt-/Browser-Tests je in eigenem Prozess | Ein Befehl lokal und in CI, alle Fehler auf einmal sichtbar | `pytest.ini`, `tests/conftest.py` |
| Fehler beim Beenden | Beim Beenden werden alle laufenden Einlese-Threads abgewartet, nicht nur der letzte | Unter Windows-CI meldete sich ein älterer Thread nach dem Beenden | `TimelineView.shutdown` |

## Bewusst nicht gemacht

- **SQLite statt JSON:** Die Daten liegen meist in OneDrive (`Dokumente\Zeitzeuge`). Eine SQLite-Datei verträgt das Synchronisieren schlecht: OneDrive kann sie mitten im Schreiben hochladen, Konfliktkopien erzeugen oder die Nebendateien (`-wal`, `-journal`) getrennt synchronisieren, dann ist die Datenbank kaputt. Die JSON-Dateien werden atomar geschrieben (`.tmp` + Ersetzen), sind pro Tag aufgeteilt und bleiben bei einem Konflikt lesbar. Deshalb bleibt es bei JSON.
- **Nuitka statt PyInstaller:** bringt ohne Signatur kaum weniger Fehlalarme, aber einen neuen, ungetesteten Build-Weg.
- **3CX-API:** nicht gewünscht.

## Screenshots

`docs/screenshots/v4.0.0/vorher_3.3/` (PyQt5) und `nachher_4.0/` (PySide6), gleiche Demodaten.
Aufgenommen unter Linux (Xvfb); „nachher“ mit `QT_SCALE_FACTOR=1.0417`, weil Qt 6 die DPI des
virtuellen Bildschirms anders liest als Qt 5. Unter Windows gilt bei beiden die Windows-Skalierung.

Verbleibende kleine Unterschiede durch Qt 6:
- Menüzeilen, Listenzeilen und Eingabefelder ca. 1 px niedriger (Schriftmetrik), Dialoge dadurch 5–12 px kürzer.
- Unter Linux zeigt Qt 6 die Alt-Unterstriche im Menü immer; unter Windows erst beim Drücken von Alt (wie bisher).
- Leicht andere Kantenglättung der Schrift.

## Unter Windows prüfen

1. Dialoge mit Zeit-/Zahlenfeldern (Arbeitszeiten, 3CX, TeamViewer): Text sitzt sauber im Feld? Falls nicht: `PySide6-Essentials==6.11.2` in `requirements.txt`.
2. Windows im dunklen Modus, Zeitzeuge im hellen Design: alles hell?
3. Dialogknöpfe auf Deutsch („Abbrechen“) auch in der EXE.
