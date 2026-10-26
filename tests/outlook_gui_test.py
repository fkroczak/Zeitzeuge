"""Outlook und Teams in der Oberfläche: Zeile, Tagesliste, Nachfragen, Menü, Dialog.

Läuft ohne Bildschirm mit einem leeren Datenordner, als eigener Prozess (Skript).
Ohne Outlook (CI): der Leser meldet das, nichts stürzt ab oder hängt.
"""
import faulthandler
import json
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
DATA = tempfile.mkdtemp()
os.environ["ZEITZEUGE_DATA"] = DATA
with open(os.path.join(DATA, "zeitzeuge_config.json"), "w", encoding="utf-8") as f:
    json.dump({"outlook_enabled": True, "teams_calls_enabled": True, "tracking_enabled": False,
               "prompt_mode": "off", "outlook_own_domains": ["itm-gruppe.de"]}, f)

FMT = "%Y-%m-%d %H:%M:%S"


def gui_test():
    global app, window
    import main_timeline
    import outlook_data
    import teams_calls
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())
    window = main_timeline.TimelineApp()
    window.tray.showMessage = lambda *a: None
    window.show()

    now = datetime.now().replace(microsecond=0)
    if now.hour < 3:
        print("Kurz nach Mitternacht: Oberflächentest übersprungen")
        return
    day = now.strftime("%Y-%m-%d")
    t = lambda minutes: (now - timedelta(minutes=minutes)).strftime(FMT)  # noqa: E731

    # Leser läuft, Outlook fehlt (CI): Meldung statt Absturz
    reader = window.outlook_reader
    assert reader is not None and reader in window.all_readers()
    deadline = time.time() + 30
    while reader.status == "Outlook: startet …" and time.time() < deadline:
        QTest.qWait(100)
    print("Status:", reader.status)
    assert reader.status != "Outlook: startet …"

    # Gelesene Daten wie aus Outlook und vom Mikrofon
    result = {"ok": True, "eigene_domain": ["itm-gruppe.de"], "termine": [
        {"start": t(150), "end": t(120), "subject": "Jour fixe Kunde Nord", "location": "Microsoft Teams",
         "teams": True, "all_day": False, "canceled": False, "free": False, "private": False,
         "domains": ["kunde-nord.de", "itm-gruppe.de"]}],
        "mails": [{"start": t(100), "subject": "Angebot Firewall", "recipients": 2,
                   "domains": ["kunde-nord.de"]}]}
    start = datetime.strptime(day, "%Y-%m-%d")
    outlook_data.save_days(main_timeline.OUTLOOK_FILE,
                           outlook_data.split_days(result, start, start + timedelta(days=1), now))
    teams_calls.store_sessions(main_timeline.TEAMS_CALLS_FILE, [
        {"start": t(60), "end": t(40), "source": "mikrofon", "app": "Teams", "running": False}])
    window.on_outlook_day(day)
    QTest.qWait(50)

    types = sorted(e["type"] for e in window.timeline.activities_for(window.current_date))
    assert types == ["Mail gesendet", "Teams-Anruf", "Teams-Besprechung"], types
    legend = [name for _y, _h, name, _c in window.timeline._legend]
    assert "Outlook" in legend and "Telefon" in legend, legend
    drawn = {e["type"] for e in window.timeline._day_entries}
    assert {"Mail gesendet", "Teams-Anruf", "Teams-Besprechung"} <= drawn, drawn

    # "Was hast du gemacht?" für den Teams-Anruf wie für 3CX, nicht für Termin und Mail
    open_types = [e["type"] for e in window.doc_candidates(day)]
    assert open_types == ["Teams-Anruf"], open_types

    # Tagesliste: Typen lesbar
    listed = [window.table.item(r, 3).text() for r in range(window.table.rowCount())]
    assert "Teams-Besprechung" in listed and "Mail gesendet" in listed and "Teams-Anruf" in listed, listed

    # Menü: Datenquellen und Zeile der Timeline
    assert window.source_actions["outlook_enabled"].isChecked()
    assert "outlook" in window.row_actions
    window.row_actions["outlook"].setChecked(False)
    assert "Outlook" not in [n for _y, _h, n, _c in window.timeline._legend]
    window.row_actions["outlook"].setChecked(True)

    # Dialog
    dialog = window.build_outlook_dialog()
    assert dialog.values()["outlook_own_domains"] == ["itm-gruppe.de"]
    dialog.close()

    # Abschalten: Leser aus, Einträge und Zeile weg
    window.source_actions["outlook_enabled"].setChecked(False)
    window.source_actions["teams_calls_enabled"].setChecked(False)
    assert window.outlook_reader is None
    window.timeline.draw_timeline(window.current_date)
    assert not [e for e in window.timeline.activities_for(window.current_date)
                if e["type"] in outlook_data.TYPES + (teams_calls.TYPE,)]
    assert "Outlook" not in [n for _y, _h, n, _c in window.timeline._legend]

    # PAW: Outlook bleibt aus
    window.config["pc_role"] = "paw"
    window.source_actions["outlook_enabled"].setChecked(True)
    assert window.outlook_reader is None and not window.config["outlook_enabled"]
    window.quit_app()


try:
    gui_test()
except BaseException:
    traceback.print_exc(file=sys.stdout)
    sys.stdout.flush()
    os._exit(1)
print("Outlook und Teams ok")
sys.stdout.flush()
os._exit(0)
