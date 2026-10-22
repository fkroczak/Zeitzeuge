"""Screenshots der Oberfläche mit erfundenen Demodaten (keine echten Kundendaten).

Läuft unter Linux mit virtuellem Bildschirm, Fenstermanager und Infobereich:

    tests/screenshots.sh docs/screenshots/2026-10-22

Das Skript startet Zeitzeuge mit einem leeren Datenordner, legt Beispiel-Logs
für einen Tag an und fotografiert Hauptfenster, Menüs, Dialoge und das Menü
im Infobereich. Es nutzt `import` (ImageMagick) für echte Bildschirmfotos.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
DARK = "--dark" in sys.argv
os.makedirs(OUT, exist_ok=True)

# ------------------------------------------------------------- Demodaten
DAY = datetime(2026, 10, 21)  # Mittwoch
DATA = tempfile.mkdtemp()
LOGS = tempfile.mkdtemp()


def t(hm, sec=0):
    h, m = map(int, hm.split(":"))
    return DAY + timedelta(hours=h, minutes=m, seconds=sec)


with open(os.path.join(LOGS, "Connections.txt"), "w", encoding="utf-8") as f:
    # TeamViewer speichert UTC, Korrektur in der Config = +1
    for tv_id, a, b in [("1076789144", "08:12", "08:47"), ("1123456789", "13:05", "13:52"),
                        ("1076789144", "15:30", "15:41")]:
        s, e = t(a) - timedelta(hours=1), t(b) - timedelta(hours=1)
        f.write(f"{tv_id}\t{s:%d-%m-%Y %H:%M:%S}\t{e:%d-%m-%Y %H:%M:%S}\tdemo\tRemoteControl\t{{x}}\n")

rdm = []
for name, kind, a, b in [("Kanzlei Schmidt - DC01", "RDP (Microsoft Remote Desktop)", "09:02", "09:58"),
                         ("Kanzlei Schmidt - SSL VPN", "VPN (OpenVPN)", "08:58", "10:03"),
                         ("Praxis Weber - Firewall", "SSH Shell", "10:20", "10:44"),
                         ("Praxis Weber - Firewall", "SSH Shell", "10:47", "11:05"),
                         ("Bäckerei Krause - NAS", "Website", "11:30", "11:52"),
                         ("Müller GmbH - TS01", "RDP (Microsoft Remote Desktop)", "14:10", "15:20"),
                         ("Müller GmbH - TS01", "RDP (Microsoft Remote Desktop)", "16:00", "16:35")]:
    rdm.append((t(a), f"Verbinden - '{name}' ({kind})"))
    rdm.append((t(b), f"Getrennt - '{name}' ({kind})"))
rdm.append((t("09:03", 20), "Passwort angezeigt - 'Kanzlei Schmidt - DC01' (RDP (Microsoft Remote Desktop))"))
rdm.append((t("10:21", 5), "One-Time Password angezeigt - 'Praxis Weber - Firewall' (SSH Shell)"))
with open(os.path.join(LOGS, "Connections.log"), "w", encoding="utf-8") as f:
    for when, text in sorted(rdm):
        f.write(f"[{when:%d.%m.%Y %H:%M:%S}] {text}\n")

calls = [("08:05", 240, "Kanzlei Schmidt", "0251 123456", "Eingehend"),
         ("12:40", 420, "Praxis Dr. Weber", "0521 987654", "Ausgehend"),
         ("13:58", 180, "Bäckerei Krause", "05731 4711", "Eingehend"),
         ("16:40", 0, "Unbekannt", "0171 5550123", "Verpasst")]
with open(os.path.join(DATA, "anrufe.json"), "w", encoding="utf-8") as f:
    json.dump([{"start": f"{t(a):%Y-%m-%d %H:%M:%S}", "duration_s": d, "name": n, "number": num,
                "direction": dr} for a, d, n, num, dr in calls], f)

os.makedirs(os.path.join(DATA, "aktivitaet"))
apps = [("outlook.exe", "Posteingang - Outlook"), ("mstsc.exe", "DC01 - Remotedesktopverbindung"),
        ("chrome.exe", "OPNsense | Dashboard - Google Chrome"), ("putty.exe", "root@fw-weber: ~"),
        ("teams.exe", "Chat | Microsoft Teams"), ("excel.exe", "Stundenzettel.xlsx - Excel")]
with open(os.path.join(DATA, "aktivitaet", f"{DAY:%Y-%m-%d}.jsonl"), "w", encoding="utf-8") as f:
    cur, i = t("07:55"), 0
    while cur < t("17:05"):
        app, title = apps[(i * 7 + i // 3) % len(apps)]
        end = cur + timedelta(minutes=6 + (i * 11) % 23)
        f.write(json.dumps({"start": f"{cur:%Y-%m-%d %H:%M:%S}", "end": f"{end:%Y-%m-%d %H:%M:%S}",
                            "app": app, "title": title}) + "\n")
        cur, i = end + timedelta(minutes=1 if i % 5 else 9), i + 1

with open(os.path.join(DATA, "zeitzeuge_config.json"), "w", encoding="utf-8") as f:
    json.dump({"teamviewer_paths": [os.path.join(LOGS, "Connections.txt")],
               "rdm_paths": [os.path.join(LOGS, "Connections.log")],
               "teamviewer_timezone_correction": 1,
               "teamviewer_names": {"1076789144": "Müller GmbH"},
               "dark_mode": DARK, "close_to_tray": True}, f)
os.environ["ZEITZEUGE_DATA"] = DATA

# ------------------------------------------------------------- Programm
import main_timeline  # noqa: E402  (nach ZEITZEUGE_DATA)
import timeline_only  # noqa: E402
from PySide6.QtCore import QDate, QPoint, QRect, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QToolButton  # noqa: E402

app = QApplication(sys.argv)
app.setStyle(main_timeline.AppStyle())
app.styleHints().setColorScheme(Qt.ColorScheme.Light)  # wie die App
app.setQuitOnLastWindowClosed(False)
if hasattr(main_timeline, "install_translator"):
    main_timeline.install_translator(app)
window = main_timeline.TimelineApp()
window.move(40, 30)
window.resize(1240, 760)
window.show()
window.date_edit.setDate(QDate(DAY.year, DAY.month, DAY.day))


def wait(seconds=0.4):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def shot(name, rect):
    """Bildschirmfoto des Bereichs rect (QRect, globale Koordinaten)."""
    wait()
    path = os.path.join(OUT, name + ".png")
    r = rect.adjusted(-6, -6, 6, 6)
    subprocess.run(["import", "-window", "root", "-crop",
                    f"{r.width()}x{r.height()}+{max(0, r.x())}+{max(0, r.y())}", path], check=True)
    print("gespeichert:", path)


def xrect(*search):
    """Echte Lage eines Fensters samt Rahmen laut X-Server (Qt kennt sie unter openbox nicht genau)."""
    wid = subprocess.run(["xdotool", "search", *search], capture_output=True,
                         text=True).stdout.split()[-1]
    out = subprocess.run(["xwininfo", "-id", wid], capture_output=True, text=True).stdout
    v = {k.strip(): int(val) for k, val in
         (line.split(":", 1) for line in out.splitlines() if ":" in line)
         if k.strip() in ("Absolute upper-left X", "Absolute upper-left Y", "Width", "Height")}
    rect = QRect(v["Absolute upper-left X"], v["Absolute upper-left Y"], v["Width"], v["Height"])
    # Rahmen des Fenstermanagers (links, rechts, oben, unten) dazunehmen
    ext = subprocess.run(["xprop", "-id", wid, "_NET_FRAME_EXTENTS"], capture_output=True,
                         text=True).stdout.split("=")[-1].split(",")
    if len(ext) == 4:
        left, right, top, bottom = (int(x) for x in ext)
        rect.adjust(-left, -top, right, bottom)
    return rect


def frame(widget=None):
    return xrect("--onlyvisible", "--name", f"^{(widget or window).windowTitle()}$")


def with_popup(widget):
    return frame().united(widget.frameGeometry())


wait(1.0)
window.table.selectRow(2)
shot("01_hauptfenster", frame())

# Hauptmenü öffnen (Knopf rechts in der Werkzeugleiste)
button = getattr(window, "menu_button", None) or [
    b for b in window.findChildren(QToolButton) if b.menu() and b.isVisible()][-1]
menu = button.menu()
menu.popup(button.mapToGlobal(QPoint(0, button.height())))
wait()
shot("02_hauptmenue", with_popup(menu))
# Untermenüs nacheinander aufklappen
for i, action in enumerate([a for a in menu.actions() if a.menu()]):
    menu.setActiveAction(action)
    action.menu().popup(menu.mapToGlobal(menu.actionGeometry(action).topRight()))
    wait()
    slug = action.text().replace("&", "").split()[0].lower()
    shot(f"03_menue_{i + 1}_{slug}", with_popup(menu).united(action.menu().frameGeometry()))
    action.menu().hide()
menu.hide()

# Tagesliste: Kontextmenü
rect = window.table.visualItemRect(window.table.item(2, 0))
pos = window.table.viewport().mapToGlobal(rect.center())
ctx = QMenu(window)
# Dasselbe Menü wie beim Rechtsklick (timeline_only.entry_menu_items)
for item in timeline_only.entry_menu_items(window.list_entries[2]):
    if item is None:
        ctx.addSeparator()
    else:
        ctx.addAction(item[0])
ctx.popup(pos)
wait()
shot("04_tagesliste_kontextmenue", with_popup(ctx))
ctx.hide()

# Dialoge
dialogs = [("05_dialog_arbeitszeiten", lambda: main_timeline.WorkHoursDialog(window.config, window)),
           ("06_dialog_teamviewer", lambda: main_timeline.ConnectionSettingsDialog(
               window.config, "teamviewer", [r"%APPDATA%\TeamViewer\Connections.txt"],
               "TeamViewer-Logeinstellungen", window)),
           ("07_dialog_3cx", window.build_pbx_dialog),
           ("08_dialog_details", lambda: main_timeline.ActivityViewDialog(window.list_entries[2], window))]
dialogs.append(("09_dialog_aktivitaetstypen",
                lambda: main_timeline.ActivityTypeSettingsDialog(window.config, window)))
for name, make in dialogs:
    d = make()
    d.show()
    wait(0.6)
    shot(name, frame(d))
    d.close()

# Infobereich (Tray): Menü bei aktiver und pausierter Aufzeichnung
if window.tray:
    geo = xrect("--class", "stalonetray")
    tray_menu = window.tray.contextMenu()
    tracking = window.tracking_action
    for state, name in [(True, "10_tray_menue_aufzeichnung_aktiv"),
                        (False, "11_tray_menue_aufzeichnung_pausiert")]:
        tracking.setChecked(state)
        wait()
        tray_menu.popup(QPoint(geo.right() - tray_menu.sizeHint().width(),
                               geo.top() - tray_menu.sizeHint().height() - 4))
        wait()
        area = tray_menu.frameGeometry().united(geo)
        shot(name, area.adjusted(-120, -10, 0, 0))
        tray_menu.hide()
        # Hauptfenster mit sichtbarem Zustand in der Statuszeile
        shot(name.replace("tray_menue", "hauptfenster"), frame())
    tracking.setChecked(True)
else:
    print("Kein Infobereich gefunden, Tray-Bilder fehlen")

window.quit_app()
# Ohne Event-Loop stürzt die Qt-Bindung beim Aufräumen sporadisch ab (auch mit altem Code, nicht in der App)
os._exit(0)
