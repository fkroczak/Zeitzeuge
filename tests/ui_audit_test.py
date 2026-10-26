"""Bedienbarkeits-Test (Barrierefreiheit und UX) für Hauptfenster und Dialoge.

Läuft ohne Bildschirm (QT_QPA_PLATFORM=offscreen) und prüft, was sich
zuverlässig automatisch prüfen lässt:

  1. Jedes Bedienelement hat einen Namen für Screenreader (wie ihn Qt
     an Windows meldet), und dieser Name besteht nicht nur aus Symbolen.
  2. Text erreicht genug Kontrast (WCAG 1.4.3: mindestens 4,5 : 1).
  3. Der Tastaturfokus ist sichtbar (WCAG 2.4.7).
  4. Die Tagesliste lässt sich mit der Tastatur öffnen (Enter = Details).
  5. Menüs bleiben überschaubar (Hick: höchstens 5 Einträge pro Gruppe).
  6. Die Oberfläche skaliert mit der Windows-Anzeigegröße (WCAG 1.4.4).

Aufruf:  python tests/ui_audit_test.py
Ergebnis: Liste der Befunde, Exit-Code 1 bei mindestens einem Befund.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main_timeline  # setzt die Hi-DPI-Rundung vor dem QApplication-Start
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox, QApplication,
                               QComboBox, QLabel, QLineEdit, QListWidget,
                               QMenu, QTableWidget, QTextEdit, QToolBar,
                               QToolButton, QWidget)

import settings_dialogs
import timeline_only

problems = []


def problem(area, text):
    problems.append(f"[{area}] {text}")


# --------------------------------------------------------------- Hilfen

def accessible_name(widget):
    """Name, den Qt an Screenreader meldet (wie QAccessibleWidget::text).

    Ohne Screenreader liefert QAccessible nichts Verlässliches, daher die Regeln von Qt nachgebaut:
    accessibleName, sonst Knopftext, sonst Text eines Labels mit setBuddy().
    """
    if widget.accessibleName():
        return widget.accessibleName().strip()
    if isinstance(widget, QAbstractButton) and widget.text():
        return widget.text().replace("&", "").strip()
    parent = widget.parentWidget()
    while parent is not None:
        for label in parent.findChildren(QLabel):
            if label.buddy() is widget:
                return re.sub(r"<[^>]+>", "", label.text()).replace("&", "").strip()
        parent = parent.parentWidget()
    return ""


def describe(widget):
    return f"{type(widget).__name__} '{widget.objectName() or accessible_name(widget) or '?'}'"


CONTROLS = (QAbstractButton, QLineEdit, QAbstractSpinBox, QComboBox, QListWidget,
            QTableWidget, QTextEdit)


def check_names(area, root):
    """Jedes sichtbare Bedienelement braucht einen sprechenden Namen."""
    for w in root.findChildren(QWidget):  # PySide6: findChildren nimmt kein Tupel
        if not isinstance(w, CONTROLS):
            continue
        if not w.isVisibleTo(root) or w.focusPolicy() == Qt.NoFocus and not isinstance(w, QAbstractButton):
            continue
        if type(w).__name__.startswith("QCalendar") or w.parent().inherits("QCalendarWidget"):
            continue
        if w.objectName().startswith("qt_"):  # Qt-interne Teile (Scrollknöpfe, Kalender)
            continue
        name = accessible_name(w)
        if not name:
            problem(area, f"{type(w).__name__} ohne Namen für Screenreader")
        elif not re.search(r"[A-Za-zÄÖÜäöüß]", name):
            problem(area, f"{type(w).__name__} heißt für Screenreader nur '{name}'")


def luminance(color):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(color.red()) + 0.7152 * ch(color.green()) + 0.0722 * ch(color.blue())


def contrast(fg, bg):
    a, b = sorted((luminance(QColor(fg)), luminance(QColor(bg))), reverse=True)
    return (a + 0.05) / (b + 0.05)


def check_contrast(area, fg, bg, minimum=4.5):
    ratio = contrast(fg, bg)
    if ratio < minimum:
        problem(area, f"Kontrast {QColor(fg).name()} auf {QColor(bg).name()} = {ratio:.2f} : 1 "
                      f"(nötig {minimum} : 1)")


def close_dialog_later():
    def close():
        d = QApplication.activeModalWidget()
        if d:
            opened.append(type(d).__name__)
            d.reject()
    QTimer.singleShot(300, close)


opened = []

# --------------------------------------------------------------- Start

app = QApplication(sys.argv)
app.setStyle(main_timeline.AppStyle())

# Qt 6 skaliert immer; mit gerundetem Faktor wären 125 %/150 % aber 100 %/200 %
if QApplication.highDpiScaleFactorRoundingPolicy() != Qt.HighDpiScaleFactorRoundingPolicy.PassThrough:
    problem("Skalierung", "Hi-DPI-Faktor gerundet: bei 125 %/150 % Windows-Anzeige passt die Größe nicht")

window = main_timeline.TimelineApp()
window.resize(1200, 720)
# Beispieldaten, damit Liste und Timeline etwas zeigen
day = window.current_date.toString("yyyy-MM-dd")
window.activities.extend([
    {"start": f"{day} 09:00:00", "end": f"{day} 09:40:00", "type": "TeamViewer",
     "customer_name": "Musterkunde GmbH", "details": "ID 123 456 789"},
    {"start": f"{day} 10:15:00", "end": f"{day} 10:30:00", "type": "Anruf",
     "customer_name": "Max Muster", "details": "eingehend"},
])
# KI-Vorschlag für die Zeile "KI" in der Timeline
window.ai_store._cache[day] = {"items": [
    {"von": "09:00", "bis": "09:45", "kunde": "Musterkunde GmbH", "kategorie": "Fernwartung",
     "beschreibung": "Updates eingespielt", "sicherheit": 0.9}]}
window.show()
window.timeline.draw_timeline(window.current_date)
if not window.timeline._ai_band:
    problem("KI", "KI-Vorschläge erscheinen nicht in der Timeline")
QTest.qWait(200)

# 1. Namen im Hauptfenster
check_names("Hauptfenster", window)
for name, w in [("Timeline", window.timeline), ("Tagesliste", window.table),
                ("Datum", window.date_edit)]:
    if not accessible_name(w):
        problem("Hauptfenster", f"{name} ohne Namen für Screenreader")

# 2. Kontrast beider Designs (Werte aus dem Stylesheet und der Timeline)
for theme_name, t in main_timeline.THEMES.items():
    area = f"Kontrast {theme_name}"
    check_contrast(area, t["text"], t["bg"])
    check_contrast(area, t["text"], t["surface"])
    check_contrast(area, t["muted"], t["bar"])
    check_contrast(area, t["muted"], t["surface"])
    check_contrast(area, t["onaccent"], t["accent"])
    check_contrast(area, t["bandtext"], t["band"])  # Werkzeugleiste als farbiges Band
    check_contrast(area, t["bandtext"], t["bandhover"])
    check_contrast(area, t["seltext"], t["sel"])  # markierte Zeile
    check_contrast(area, t["muted"], t["bg"])  # Hinweistexte (QLabel#hint)
for dark in (False, True):
    window.timeline.dark_mode = dark
    window.timeline.init_timeline_colors()
    tl = window.timeline
    area = f"Kontrast Timeline {'dunkel' if dark else 'hell'}"
    check_contrast(area, tl.muted_text, tl.axis_bg)
    check_contrast(area, tl.text_color, tl.axis_bg)
    # Balken sind volle Kacheln (Metro): Schrift wählt readable_on, mindestens 4.5 : 1
    for type_name, color in window.config.get("type_colors", {}).items():
        check_contrast(f"{area}, Balken {type_name}", timeline_only.readable_on(color), color)
window.timeline.dark_mode = window.dark_mode
window.timeline.init_timeline_colors()

# Zustand im Infobereich: auf heller und dunkler Windows-Taskleiste erkennbar (Grafik, 3 : 1)
import icons  # noqa: E402
for taskbar in ("#F3F3F3", "#1F2329"):
    for color in (icons.ACTIVE_COLOR, icons.PAUSED_COLOR):
        check_contrast("Infobereich", color, taskbar, minimum=3.0)

# Graue Hinweistexte direkt im Code (nur Farbe "gray" ist auf hellem Grund zu blass)
for path in ["main_timeline.py", "theme.py", "app_menus.py", "app_daylist.py", "app_docs.py",
             "app_readers.py", "app_tray.py", "settings_dialogs.py", "timeline_only.py",
             "app_protect.py", "protect_dialogs.py", "app_transfer.py", "snippets_dialogs.py",
             "journal_dialogs.py"]:
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        for no, line in enumerate(f, 1):
            if re.search(r"color:\s*(gray|grey|#999|#aaa)\b", line, re.I):
                problem("Kontrast", f"{path}:{no} blasser Text ({line.strip()[:60]})")

# 3. Sichtbarer Fokus
sheet = main_timeline.STYLESHEET
for widget in ["QToolButton", "QPushButton", "QLineEdit"]:
    if not re.search(rf"{widget}[^{{]*:focus", sheet):
        problem("Fokus", f"{widget} hat keinen sichtbaren Tastaturfokus im Stylesheet")

# 4. Tastatur: Enter in der Tagesliste öffnet die Details
window.table.setFocus()
window.table.selectRow(0)
close_dialog_later()
QTest.keyClick(window.table, Qt.Key_Return)
QTest.qWait(400)
if "ActivityViewDialog" not in opened:
    problem("Tastatur", "Enter in der Tagesliste öffnet keine Details (nur Doppelklick)")

# 5. Menü Einstellungen: Gruppen klein halten, Tastatur-Kürzel (Alt+Buchstabe)
for menu in window.findChildren(QMenu):
    group = 0
    for action in menu.actions():
        if action.isSeparator():
            group = 0
            continue
        group += 1
        if group > 5:
            problem("Menü", f"mehr als 5 Einträge ohne Trennlinie (ab '{action.text()}')")
            group = -99
        # Reine Anzeigen (deaktiviert, z. B. Zustand im Infobereich) brauchen keinen Alt-Buchstaben
        if "&" not in action.text() and menu.parent() is window and action.isEnabled():
            problem("Menü", f"'{action.text()}' ohne Alt-Buchstaben")

# Dialoge: Namen, Hinweise
config = window.config
dialogs = {
    "Aktivitätsdetails": timeline_only.ActivityViewDialog(window.activities[0], window),
    "Arbeitszeiten": settings_dialogs.WorkHoursDialog(config, window),
    "Logeinstellungen": settings_dialogs.ConnectionSettingsDialog(config, "teamviewer", ["C:\\x"], "TV", window),
    "Aktivitätstypen": settings_dialogs.ActivityTypeSettingsDialog(config, window),
    "KI-Vorschläge": settings_dialogs.AiSettingsDialog(config, 0.0, window),
    "Fenster-Filter": settings_dialogs.TrackingFilterDialog(config, main_timeline.ACTIVITY_DIR, window),
    "Regeln": settings_dialogs.RulesDialog(config, window),
}
import journal_dialogs  # noqa: E402
from datetime import datetime as _dt  # noqa: E402
_tv = {"start": f"{day} 09:00:00", "end": f"{day} 09:40:00", "type": "TeamViewer",
       "customer_name": "", "tv_id": "123456789"}
dialogs["Tätigkeit nachtragen"] = journal_dialogs.EntryDialog(
    _dt(2026, 10, 20, 9), _dt(2026, 10, 20, 9, 30), ["Musterkunde GmbH"], ["Fernwartung"],
    tv_id="123456789", info="Erkannt: TeamViewer", can_delete=True, parent=window)
dialogs["Nachfrage"] = journal_dialogs.PromptWindow(_tv, ["Musterkunde GmbH"], ["Fernwartung"],
                                                    pending=2, parent=window)
dialogs["Nachfragen und Erinnerungen"] = journal_dialogs.DocPromptDialog(config, window)
# Eintragen mit Textbausteinen und Ticket-Vorschlag (Knopf „Übernehmen“ sichtbar)
_found = [{"ticket": "TCK0000049374", "label": "TCK0000049374 (Outlook, 12 min)"}]
dialogs["Tätigkeit mit Ticket-Vorschlag"] = journal_dialogs.EntryDialog(
    _dt(2026, 10, 20, 9), _dt(2026, 10, 20, 9, 30), ["Musterkunde GmbH"], ["Fernwartung"],
    parent=window, snippets=["Windows-Updates installiert"], ticket_suggestions=_found)
dialogs["Nachfrage mit Ticket-Vorschlag"] = journal_dialogs.PromptWindow(
    _tv, ["Musterkunde GmbH"], ["Fernwartung"], parent=window, ticket_suggestions=_found)
import snippets_dialogs  # noqa: E402
dialogs["Textbausteine"] = snippets_dialogs.SnippetsDialog(config, window)
if hasattr(window, "build_pbx_dialog"):
    dialogs["3CX direkt"] = window.build_pbx_dialog()
if hasattr(window, "build_itm_dialog"):
    dialogs["ITM-Personalzeiten"] = window.build_itm_dialog()
import protect_dialogs  # noqa: E402
dialogs["Schutz der Daten"] = window.build_protection_dialog()
dialogs["Wiederherstellungsschlüssel"] = protect_dialogs.CodeDialog(
    "Wiederherstellungsschlüssel", protect_dialogs.RECOVERY_INTRO, "000000-" * 7 + "000000",
    "Zeitzeuge Wiederherstellung", window)
dialogs["Wiederherstellungsschlüssel"].saved.setChecked(True)  # sonst fragt Schließen nach
dialogs["Schlüssel eingeben"] = protect_dialogs.EnterCodeDialog(
    "Daten sind gesperrt", "Text", "&Wiederherstellungsschlüssel:", lambda c: None, parent=window)
for area, dialog in dialogs.items():
    dialog.show()
    QTest.qWait(50)
    check_names(area, dialog)
    dialog.close()

# Arbeitszeiten: "bis" vor "von" muss als Fehler erkennbar sein
wh = dialogs["Arbeitszeiten"]
active, t_from, t_to, total = wh.rows[0]
active.setChecked(True)
t_from.setTime(t_from.time().fromString("17:00", "HH:mm"))
t_to.setTime(t_to.time().fromString("08:00", "HH:mm"))
if total.text() == "frei":
    problem("Arbeitszeiten", "Ende vor Beginn wird stumm als 'frei' angezeigt statt als Fehler")

# Fenster-Filter und Regeln: ungültige Regex als Text neben dem Feld, OK gesperrt
tf = dialogs["Fenster-Filter"]
tf.show()
tf.edits["tracking_skip"].setPlainText("steam\nre:(kaputt")
label = tf.error_labels["tracking_skip"]
if tf.ok_button.isEnabled() or not label.isVisible() or "Zeile 2" not in label.text():
    problem("Fenster-Filter", "ungültige Regex wird nicht neben dem Feld gemeldet oder OK bleibt frei")
tf.edits["tracking_skip"].setPlainText("steam")
if not tf.ok_button.isEnabled():
    problem("Fenster-Filter", "OK bleibt nach Korrektur gesperrt")
tf.close()
rd = dialogs["Regeln"]
rd.show()
rd.table.setCurrentCell(0, 1)
rd.match_edit.setText("re:[")
rd.match_edit.textEdited.emit("re:[")
if rd.ok_button.isEnabled() or not rd.match_error.isVisible() or not rd.table_error.isVisible():
    problem("Regeln", "ungültige Regex wird nicht neben dem Feld gemeldet oder OK bleibt frei")
rd.close()

# Fenster sehr schmal: wichtige Knöpfe bleiben erreichbar (Reflow)
window.resize(640, 480)
QTest.qWait(200)
toolbar = getattr(window, "tools_bar", None) or window.findChild(QToolBar)
ext = toolbar.findChild(QToolButton, "qt_toolbar_ext_button")
if ext is None or not ext.isVisible() or ext.width() < 20:
    problem("Reflow", "bei 640 px Breite ist der Knopf für ausgeblendete Befehle "
                      "fehlend oder kaum sichtbar")
# Jeder Knopf der Werkzeugleiste erklärt sich beim Darüberfahren
for bar in window.findChildren(QToolBar):
    for action in bar.actions():
        button = bar.widgetForAction(action)
        if isinstance(button, QToolButton) and not (button.toolTip() or action.toolTip()):
            problem("Werkzeugleiste", f"'{action.text() or button.accessibleName()}' ohne Hinweis")
# Einstellungen müssen auch im schmalen Fenster direkt sichtbar sein, nicht erst im Überlauf
for width in (640, 480):
    window.resize(width, 480)
    QTest.qWait(150)
    if not window.menu_button.isVisible():
        problem("Reflow", f"bei {width} px Breite ist „Einstellungen“ nur über » erreichbar")

# --------------------------------------------------------------- Ergebnis
window.quit_app()
if problems:
    print(f"{len(problems)} Befund(e):")
    for p in problems:
        print(" -", p)
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::error title=Bedienbarkeit::{p}")
    sys.stdout.flush()
    os._exit(1)
print("Bedienbarkeit ok")

# Direkt beenden: die Qt-Bindung räumt beim Interpreter-Ende sporadisch in falscher Reihenfolge auf
# (Zugriffsfehler unter Windows, auch mit altem Code). Alle Prüfungen sind hier gelaufen.
sys.stdout.flush()
os._exit(0)
