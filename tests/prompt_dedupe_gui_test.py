"""Nachfragen im Hauptfenster: ein Thema je Arbeit, keine doppelten Nachfragen.

Fälle, die früher zu mehreren Nachfragen für denselben Kunden führten:
1. VPN und RDP zur selben Kanzlei gleichzeitig, dazu ein Telefonat kurz danach.
2. Eingetragene Zeit kürzer als erkannt (Rest blieb „offen“ und wurde wieder gefragt).
3. Erkannter Eintrag ändert sich später (Logs kommen nach, Startzeit verschiebt sich).
4. „Später fragen“ und danach wächst das Thema um einen weiteren Teil.

Läuft ohne Bildschirm als eigener Prozess (Skript).
"""
import faulthandler
import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout.reconfigure(line_buffering=True, errors="backslashreplace")
faulthandler.enable()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ZEITZEUGE_DATA"] = tempfile.mkdtemp()

FMT = "%Y-%m-%d %H:%M:%S"


def flush_deletes():
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def gui_test():
    global app, window
    import main_timeline
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    app = QApplication(sys.argv)
    app.setStyle(main_timeline.AppStyle())
    window = main_timeline.TimelineApp()
    window.tray.showMessage = lambda *a: None
    window.show()

    now = datetime.now().replace(microsecond=0, second=0)
    if now.hour < 2:
        print("Kurz nach Mitternacht: übersprungen")
        return
    base = now - timedelta(minutes=80)  # alles endet in der letzten Stunde (nur das wird gefragt)

    def at(minutes):
        return (base + timedelta(minutes=minutes)).strftime(FMT)

    vpn = {"start": at(0), "end": at(65), "type": "VPN-Verbindung",
           "customer_name": "Kanzlei Schmidt - SSL VPN", "details": "", "is_suggestion": True}
    rdp = {"start": at(2), "end": at(58), "type": "RDP-Verbindung",
           "customer_name": "Kanzlei Schmidt - DC01", "details": "", "is_suggestion": True}
    call = {"start": at(70), "end": at(74), "type": "Telefonat", "direction": "Eingehend",
            "customer_name": "Kanzlei Schmidt (0251 123456)", "details": "", "is_suggestion": True}
    other = {"start": at(30), "end": at(40), "type": "Telefonat", "direction": "Ausgehend",
             "customer_name": "Praxis Weber (0521 987654)", "details": "", "is_suggestion": True}
    window.activities.extend([vpn, rdp, call, other])
    window.timeline.draw_timeline(window.current_date)

    # 1. Ein Thema für die Kanzlei (VPN + RDP + Telefonat), eins für die Praxis
    window.check_prompts()
    queue = window._prompt_queue
    assert len(queue) == 2, [(q["type"], q["customer_name"]) for q in queue]
    kanzlei = next(q for q in queue if "Kanzlei" in q["customer_name"])
    assert len(kanzlei["parts"]) == 3, kanzlei.get("parts")
    # Zeile Dokumentation zeigt dieselben zwei offenen Themen
    bands = dict((k, e) for k, _t, e in window.timeline._bands)
    assert len([e for e in bands["doc"] if e.get("open")]) == 2, bands["doc"]
    window.check_prompts()
    assert len(window._prompt_queue) == 2, "zweite Prüfung darf nichts doppelt einreihen"

    # 2. Kanzlei beantworten, aber nur 20 Minuten eintragen (viel kürzer als erkannt)
    prompt = window._prompt_window
    assert prompt is not None
    if "Kanzlei" not in prompt.entry["customer_name"]:  # Reihenfolge: früheres Thema zuerst
        prompt.reject()  # Praxis später
        QTest.qWait(500)
        flush_deletes()
        prompt = window._prompt_window
    assert prompt is not None and "Kanzlei" in prompt.entry["customer_name"], prompt and prompt.entry
    prompt.form.customer_edit.setCurrentText("Kanzlei Schmidt")
    prompt.form.text_edit.setPlainText("Server neu gestartet")
    end_edit = prompt.form.end_edit
    end_edit.setDateTime(end_edit.dateTime().addSecs(-(74 - 20) * 60))
    prompt.save_btn.click()
    QTest.qWait(500)
    flush_deletes()
    items = window.journal.items(now.strftime("%Y-%m-%d"))
    assert len(items) == 1 and items[0].get("answered"), items
    window.check_prompts()
    open_now = window.doc_candidates(now.strftime("%Y-%m-%d"))
    assert not any("Kanzlei" in e["customer_name"] for e in open_now), \
        "Kanzlei trotz Antwort wieder offen (eingetragene Zeit kürzer als erkannt)"

    # 3. Logs kommen nach: VPN beginnt eine Minute früher, Name leicht anders
    vpn["start"], vpn["customer_name"] = at(-1), "Kanzlei Schmidt - SSL VPN 2"
    window.check_prompts()
    open_now = window.doc_candidates(now.strftime("%Y-%m-%d"))
    assert not any("Kanzlei" in e["customer_name"] for e in open_now), open_now
    assert all("Kanzlei" not in q["customer_name"] for q in window._prompt_queue)

    # 4. Praxis: „Später“, danach wächst das Thema um ein zweites Telefonat
    if window._prompt_window is None:
        window.show_next_prompt()
    prompt = window._prompt_window
    assert prompt is not None and "Praxis" in prompt.entry["customer_name"], prompt and prompt.entry
    prompt.reject()
    QTest.qWait(500)
    flush_deletes()
    window.activities.append({"start": at(42), "end": at(45), "type": "Telefonat", "direction": "Eingehend",
                              "customer_name": "Praxis Weber (0521 987654)", "details": "",
                              "is_suggestion": True})
    window.timeline.draw_timeline(window.current_date)
    window.check_prompts()
    assert window._prompt_window is None and not window._prompt_queue, \
        "zurückgestelltes Thema nach Zuwachs sofort wieder gefragt"

    # Nicht dokumentieren: ganzes Thema weg, auch später nicht wieder
    window._prompt_asked.clear()
    window._prompt_asked_spans.clear()
    window.check_prompts()
    prompt = window._prompt_window
    assert prompt is not None and len(prompt.entry.get("parts", [])) == 2, prompt and prompt.entry
    window.on_prompt_answered("ignore", prompt.entry, None)
    QTest.qWait(500)
    flush_deletes()
    window._prompt_asked.clear()
    window._prompt_asked_spans.clear()
    window.check_prompts()
    assert window._prompt_window is None and not window._prompt_queue
    window.quit_app()


try:
    gui_test()
except BaseException:
    traceback.print_exc(file=sys.stdout)
    sys.stdout.flush()
    os._exit(1)
print("Nachfragen ohne Doppelte ok")
sys.stdout.flush()
os._exit(0)
