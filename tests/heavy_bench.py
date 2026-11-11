"""Leistung mit realistisch vollen Daten: Zeichnen, Daten lesen, Tagesliste, Tag wechseln.

Aufruf:  python tests/heavy_bench.py [Durchläufe] [--profile]
Wie perf_bench.py, aber mit allen großen Quellen in der Datenbank:
  - aktive Fenster: heute 4000 Wechsel, dazu 90 Arbeitstage mit je 3000
  - Anrufe (40 je Arbeitstag, ein Jahr), Outlook (Termine und Mails), Tätigkeiten
  - Spuren vom PC (Browser, Dateien, Netzwerk, Sperren) für 90 Tage
  - TeamViewer- und RDM-Logs für ein Jahr
"Hin und her": zwischen heute und den zwei Vortagen wechseln (wie beim Nachtragen).
Am Ende: vergangenen Tag lesen vor und nach dem Verdichten (compact_days).
--profile schreibt je Messung die 25 teuersten Funktionen (cProfile, kumuliert).
Kein Test (läuft nicht in pytest).
"""
import cProfile
import io
import json
import os
import pstats
import random
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
DATA = tempfile.mkdtemp()
os.environ["ZEITZEUGE_DATA"] = DATA
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

LOG_DAYS, DB_DAYS = 365, 90
rng = random.Random(1)
today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
F = "%Y-%m-%d %H:%M:%S"
APPS = ["msedge.exe", "ms-teams.exe", "OUTLOOK.EXE", "mstsc.exe", "EXCEL.EXE", "WINWORD.EXE",
        "RemoteDesktopManager.exe", "TeamViewer.exe", "explorer.exe", "Code.exe"]
CUSTOMERS = [f"Kunde {i}" for i in range(40)]


def workdays(n):
    for d in range(n, -1, -1):
        day = today - timedelta(days=d)
        if day.weekday() < 5:
            yield day


def make_logs():
    tv, rdm = os.path.join(DATA, "Connections.txt"), os.path.join(DATA, "Connections.log")
    with open(tv, "w", encoding="utf-8") as f_tv, open(rdm, "w", encoding="utf-8") as f_rdm:
        for day in workdays(LOG_DAYS):
            t = day + timedelta(hours=7)
            for _ in range(20):
                s = t + timedelta(minutes=rng.randint(1, 10))
                e = s + timedelta(minutes=rng.randint(2, 25))
                f_tv.write(f"{rng.randrange(10**9, 2 * 10**9)}\t{s:%d-%m-%Y %H:%M:%S}\t"
                           f"{e:%d-%m-%Y %H:%M:%S}\tdemo\tRemoteControl\t{{x}}\n")
                t = e
            t = day + timedelta(hours=7)
            for i in range(30):
                s = t + timedelta(minutes=rng.randint(1, 5))
                e = s + timedelta(minutes=rng.randint(2, 15))
                name = f"{CUSTOMERS[i % 12]} - SRV{i % 7:02d}"
                f_rdm.write(f"[{s:%d.%m.%Y %H:%M:%S}] Verbinden - '{name}' (RDP (Microsoft Remote Desktop))\n")
                f_rdm.write(f"[{e:%d.%m.%Y %H:%M:%S}] Getrennt - '{name}' (RDP (Microsoft Remote Desktop))\n")
                t = e
    with open(os.path.join(DATA, "zeitzeuge_config.json"), "w", encoding="utf-8") as f:
        json.dump({"teamviewer_paths": [tv], "rdm_paths": [rdm], "tracking_enabled": True,
                   "setup_done": True, "show_pc_in_list": True,
                   # Kundenliste im aktuellen Format (Spuren): Stichwort und Mail-Domain
                   "customers": [{"name": c, "traces": [{"kind": "word", "value": c.lower()},
                                                        {"kind": "mail", "value": f"kunde{i}.de"}]}
                                 for i, c in enumerate(CUSTOMERS)]}, f)


def segments(day, n):
    t = day + timedelta(hours=6, minutes=30)
    for i in range(n):
        e = t + timedelta(seconds=rng.randint(3, 15))
        app = rng.choice(APPS)
        yield {"start": t.strftime(F), "end": e.strftime(F), "app": app,
               "title": f"{rng.choice(CUSTOMERS)} – Dokument {i % 150}"}
        t = e + timedelta(seconds=rng.randint(0, 2))


def fill_db(mt):
    import call_import
    import datastore
    import journal
    import outlook_data
    store, name = datastore.locate(mt.ACTIVITY_DIR, "row_files")
    rows = []
    for day in workdays(DB_DAYS):
        n = 4000 if day == today else 3000
        rows += [(s["start"][:10], s) for s in segments(day, n)]
    store.append_many(name, rows)

    calls, outlook, local = [], {}, {k: [] for k in ("locked", "sessions", "wlan", "events", "files", "browser")}
    j = journal.Journal(mt.JOURNAL_DIR)
    for day in workdays(LOG_DAYS):
        for _ in range(40):
            s = day + timedelta(hours=7, minutes=rng.randint(0, 600))
            calls.append({"start": s.strftime(F), "duration_s": rng.randint(0, 900),
                          "number": f"+49{rng.randrange(10**9)}", "name": rng.choice(CUSTOMERS),
                          "direction": rng.choice(["Eingehend", "Ausgehend"])})
    for day in workdays(DB_DAYS):
        doc = {"termine": [], "mails": [], "eingang": [], "chats": []}
        for _ in range(6):
            s = day + timedelta(hours=rng.randint(7, 16))
            doc["termine"].append({"start": s.strftime(F), "end": (s + timedelta(minutes=45)).strftime(F),
                                   "subject": f"Termin {rng.choice(CUSTOMERS)}", "location": "Büro",
                                   "domains": [f"kunde{rng.randrange(40)}.de"]})
        for key in ("mails", "eingang"):
            for _ in range(30):
                s = day + timedelta(hours=7, minutes=rng.randint(0, 600))
                doc[key].append({"start": s.strftime(F), "subject": "Re: Ticket", "recipients": 2,
                                 "domains": [f"kunde{rng.randrange(40)}.de"]})
        outlook[day.strftime("%Y-%m-%d")] = doc
        for i in range(12):
            s = day + timedelta(hours=7, minutes=40 * i)
            j.add({"start": s.strftime(F), "end": (s + timedelta(minutes=35)).strftime(F),
                   "customer": rng.choice(CUSTOMERS), "category": "Support", "text": "Arbeit"})
        for i in range(60):
            s = day + timedelta(hours=7, minutes=10 * i)
            local["browser"].append({"start": s.strftime(F), "end": (s + timedelta(minutes=6)).strftime(F),
                                     "domain": f"kunde{rng.randrange(40)}.de", "tickets": []})
            local["files"].append({"start": s.strftime(F), "end": s.strftime(F), "name": f"datei{i}.docx"})
        local["wlan"].append({"start": (day + timedelta(hours=7)).strftime(F),
                              "end": (day + timedelta(hours=17)).strftime(F), "ssid": "Büro",
                              "adapter": "Ethernet", "wireless": False})
        local["locked"].append({"start": (day + timedelta(hours=12)).strftime(F),
                                "end": (day + timedelta(hours=12, minutes=30)).strftime(F)})
    call_import.merge_calls(mt.CALLS_FILE, calls)
    outlook_data.save_days(mt.OUTLOOK_FILE, outlook)
    lstore, lname = datastore.locate(mt.LOCAL_FILE, "single")
    lstore.put(lname, "", local)
    return len(rows), len(calls)


def ms(seconds):
    return f"{seconds * 1000:8.1f} ms"


PROFILE = "--profile" in sys.argv


def measure(label, fn, runs):
    values = []
    prof = cProfile.Profile() if PROFILE else None
    for _ in range(runs):
        t0 = time.perf_counter()
        if prof:
            prof.enable()
        fn()
        if prof:
            prof.disable()
        values.append(time.perf_counter() - t0)
    print(f"{label:<36}{ms(statistics.median(values))}")
    if prof:
        out = io.StringIO()
        pstats.Stats(prof, stream=out).sort_stats("cumulative").print_stats(25)
        print("\n".join(out.getvalue().splitlines()[6:40]))
    return statistics.median(values)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    runs = int(args[0]) if args else 5
    make_logs()
    t0 = time.perf_counter()
    import main_timeline as mt
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication
    print(f"{'Import':<36}{ms(time.perf_counter() - t0)}")
    app = QApplication(sys.argv)
    w = mt.TimelineApp()
    tl = w.timeline
    n_rows, n_calls = fill_db(mt)
    print(f"Testdaten: {n_rows} Fensterwechsel, {n_calls} Anrufe, {DB_DAYS} Tage Outlook/Tätigkeiten/Spuren")

    def wait():
        while getattr(tl, "loading", False) or tl._tv_index is None:
            app.processEvents()
            time.sleep(0.001)
        app.processEvents()

    w.show()
    wait()
    tl.local_reader._data = None
    date = QDate.currentDate()
    tl._remote_cache.clear()

    def cold():  # wie nach dem Einlesen der Logs: Zwischenspeicher leer
        tl._remote_cache.clear()
        tl._sophos_index = tl._rdp_index = tl._local_index = None
        tl.local_reader._data = None
        tl.draw_timeline(date)
        app.processEvents()
    measure("Tag zeichnen (Zwischensp. leer)", cold, runs)
    measure("Tag zeichnen (heute, warm)", lambda: (tl.draw_timeline(date), app.processEvents()), runs)
    measure("Nur anordnen (Zoom/Größe)", tl.relayout, runs)
    measure("Tagesliste füllen (heute)",
            lambda: w.update_day_list(tl._day_data["activities"], tl.pc_entries_for(date)), runs)
    measure("Aktive Fenster lesen (heute)", lambda: tl.pc_entries_for(date), runs)

    def refresh():
        tl.refresh()
        wait()
    measure("Neu einlesen (alle 2 Min.)", refresh, runs)

    days = [date.addDays(-i) for i in range(1, 21)]

    def switch():
        for d in days:
            w.date_edit.setDate(d)
            app.processEvents()
    per = measure("Tag wechseln (20 Tage, gesamt)", switch, max(1, runs // 2))
    print(f"{'  = je Tag':<36}{ms(per / len(days))}")
    w.date_edit.setDate(date)
    app.processEvents()

    hops = [date.addDays(-1), date.addDays(-2), date] * 3  # wie beim Nachtragen: heute, gestern, …

    def back_and_forth():
        for d in hops:
            w.date_edit.setDate(d)
            app.processEvents()
    per = measure("Hin und her (3 Tage, 9 Wechsel)", back_and_forth, runs)
    print(f"{'  = je Wechsel':<36}{ms(per / len(hops))}")

    # Tag für Tag zurück, jeden Tag kurz ansehen (0,7 s): gezählt wird nur der Wechsel.
    # Andere Tage als oben, damit nichts schon im Zwischenspeicher liegt.
    def step_back():
        took = []
        d = date.addDays(-30)
        w.date_edit.setDate(d)
        for _ in range(8):
            end = time.perf_counter() + 0.7
            while time.perf_counter() < end:
                app.processEvents()
                time.sleep(0.005)
            d = d.addDays(-1)
            t0 = time.perf_counter()
            w.date_edit.setDate(d)
            app.processEvents()
            took.append(time.perf_counter() - t0)
        return statistics.median(took)
    print(f"{'Tag zurück, je Tag (mit Ansehen)':<36}{ms(step_back())}")
    w.date_edit.setDate(date)
    app.processEvents()
    import activity_tracker as at
    past = date.addDays(-1)
    while past.dayOfWeek() > 5:
        past = past.addDays(-1)
    past_str = past.toString("yyyy-MM-dd")

    def read_past():
        at._segment_cache.clear()
        at.read_segments(mt.ACTIVITY_DIR, past_str)
    measure("Vergangenen Tag lesen (Zeilen)", read_past, runs)
    t0 = time.perf_counter()
    at.compact_days(mt.ACTIVITY_DIR)
    print(f"{'Verdichten (alle vergangenen Tage)':<36}{ms(time.perf_counter() - t0)}")
    measure("Vergangenen Tag lesen (verdichtet)", read_past, runs)
    tl._pc_cache.clear()
    tl._block_cache = None

    def switch_packed():
        at._segment_cache.clear()
        tl._pc_cache.clear()
        switch()
    per = measure("Tag wechseln, verdichtet (20 Tage)", switch_packed, max(1, runs // 2))
    print(f"{'  = je Tag':<36}{ms(per / len(days))}")
    w.date_edit.setDate(date)
    app.processEvents()
    measure("Mausbewegung (Hinweis, 50x)",
            lambda: [tl._hover_text(m) for m in range(420, 920, 10)], runs)
    print(f"Tagesliste heute: {w.table.rowCount()} Zeilen")
    w.quit_app()


if __name__ == "__main__":
    main()
