"""Robustheit: kaputte Dateien, große und UTF-16-Logs, ohne Internet, abgestürzter
Lese-Thread, Anmeldefenster ohne Anmeldung, Fehler in einem Slot.

Läuft ohne Bildschirm und ohne Edge (Browser und Netz werden nachgebaut).
"""
import glob
import json
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # Browser-Skript wird relativ gesucht (resource_path)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
DATA = tempfile.mkdtemp()
os.environ["ZEITZEUGE_DATA"] = DATA
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()  # Edge-Profile und Sperre nicht im echten Ordner


def check(ok, what):
    if not ok:
        print(f"::error title=Robustheit::{what}")
        sys.stdout.flush()
        os._exit(1)
    print("ok:", what)


def defekt(path):
    return glob.glob(path + ".defekt-*")


# ---------------------------------------------------------------- kaputte Config
CONFIG = os.path.join(DATA, "zeitzeuge_config.json")
BROKEN_CONFIG = '{"teamviewer_names": {"1076789144": "Müller GmbH"}, "work_days": {"Mo": "07:'
with open(CONFIG, "w", encoding="utf-8") as f:
    f.write(BROKEN_CONFIG)

import main_timeline  # noqa: E402
import net  # noqa: E402
import pbx_reader  # noqa: E402
import safe_io  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
app = QApplication(sys.argv)
app.setStyle(main_timeline.AppStyle())  # wie die App (Fusion), Windows-Stil stürzt ohne Bildschirm ab
main_timeline.install_error_hooks()
window = main_timeline.TimelineApp()
# Ohne Bildschirm gibt es keinen echten Infobereich: Sprechblasen am vorgetäuschten Symbol
# stürzen unter Windows in Qt ab. Meldungen hier nur mitschreiben.
tray_messages = []
window.tray.showMessage = lambda title, text, *a: tray_messages.append((title, text))

saved = defekt(CONFIG)
check(len(saved) == 1, "kaputte Config beiseitegelegt")
with open(saved[0], encoding="utf-8") as f:
    check(f.read() == BROKEN_CONFIG, "Inhalt der kaputten Config unverändert aufgehoben")
with open(CONFIG, encoding="utf-8") as f:
    check(json.load(f)["work_days"]["Mo"] == "08:00-17:00", "neue Config mit Standardwerten, Start klappt")
window.show_problems(startup=True)
check("beschädigt" in window.statusBar().currentMessage(), "Hinweis auf die kaputte Config in der Statuszeile")

# ---------------------------------------------------------------- anrufe.json
from call_import import load_call_suggestions, load_calls, merge_calls  # noqa: E402

calls = os.path.join(DATA, "anrufe_test.json")
BROKEN_CALLS = '[{"start": "2026-10-20 08:00:00", "number": "0301", "duration_s": 60}, {"start": '
with open(calls, "w", encoding="utf-8") as f:
    f.write(BROKEN_CALLS)
new_call = {"start": "2026-10-21 09:00:00", "number": "0302", "duration_s": 90, "direction": "Eingehend"}
merge_calls(calls, [new_call])
saved = defekt(calls)
check(len(saved) == 1 and open(saved[0], encoding="utf-8").read() == BROKEN_CALLS,
      "kaputte anrufe.json beiseitegelegt statt überschrieben")
check(load_calls(calls) == [new_call], "neue Anrufe trotzdem gespeichert")

good = [{"start": "2026-10-19 10:00:00", "number": "1", "duration_s": 30}, "Müll",
        {"start": "kaputt"}, {"start": "2026-10-19 11:00:00", "number": "2", "duration_s": 40}]
with open(calls, "w", encoding="utf-8") as f:
    json.dump(good, f)
merge_calls(calls, [new_call])
check(len(load_calls(calls)) == 3 and len(defekt(calls)) == 1,
      "einzelne kaputte Anrufe übersprungen, die anderen bleiben")
check(len(load_call_suggestions(calls, "2026-10-19")) == 2, "Anrufe des Tages trotz kaputter Einträge angezeigt")

# ---------------------------------------------------------------- weitere Dateien
from ai_classifier import AiStore  # noqa: E402
from itm_reader import load_days  # noqa: E402
from vpn_reader import VpnReader  # noqa: E402

days_file = os.path.join(DATA, "personalzeiten_test.json")
with open(days_file, "w", encoding="utf-8") as f:
    f.write('{"2026-10-20": {"soll": 480')
check(load_days(days_file) == {} and len(defekt(days_file)) == 1, "kaputte personalzeiten.json beiseitegelegt")

vpn_file = os.path.join(DATA, "vpn_test.json")
with open(vpn_file, "w", encoding="utf-8") as f:
    json.dump({"connections": [{"start": "2026-10-20 08:00:00", "end": "2026-10-20 09:00:00",
                                "vpn_source": "Sophos", "vpn_id": "1", "customer_name": "A"}, 42],
               "adapter": "kaputt", "names": {}}, f)
vpn = VpnReader(archive_file=vpn_file, dirs=[DATA], adapter_func=lambda: [])
check(len(vpn._archive()["connections"]) == 1 and vpn._archive()["adapter"] == [],
      "VPN-Archiv: kaputte Einträge übersprungen")

ai_dir = os.path.join(DATA, "ki_test")
os.makedirs(ai_dir)
with open(os.path.join(ai_dir, "2026-10-20.json"), "w", encoding="utf-8") as f:
    f.write("{nicht json")
check(AiStore(ai_dir).load("2026-10-20") is None and len(defekt(os.path.join(ai_dir, "2026-10-20.json"))) == 1,
      "kaputte KI-Vorschläge beiseitegelegt")

# ---------------------------------------------------------------- Logdateien
from log_parsers import TeamViewerParser  # noqa: E402


def tv_line(i):
    return f"{1000 + i}\t20-10-2026 08:{i % 60:02d}:00\t20-10-2026 09:{i % 60:02d}:00\tIch\tRemoteControl\t{{guid}}\n"


big = os.path.join(DATA, "Connections_gross.txt")
with open(big, "w", encoding="utf-8") as f:
    f.writelines(tv_line(i) for i in range(100))
old_limits = safe_io.MAX_LOG_BYTES, safe_io.TAIL_BYTES
safe_io.MAX_LOG_BYTES, safe_io.TAIL_BYTES = 2000, 1000
safe_io.take_problems()
ids = [c["tv_id"] for c in TeamViewerParser({"teamviewer_paths": [big], "teamviewer_timezone_correction": 0}).parse_logs()]
safe_io.MAX_LOG_BYTES, safe_io.TAIL_BYTES = old_limits
check(0 < len(ids) < 20 and "1099" in ids and "1000" not in ids, f"große Logdatei: nur das Ende gelesen ({len(ids)} Zeilen)")
check(all(1000 <= int(i) <= 1099 for i in ids), "erste angeschnittene Zeile übersprungen")
check(any("sehr groß" in p for p in safe_io.take_problems()), "große Logdatei gemeldet")

utf16 = os.path.join(DATA, "Connections_utf16.txt")
with open(utf16, "w", encoding="utf-16") as f:  # mit BOM, wie Windows-Werkzeuge
    f.writelines(tv_line(i) for i in range(3))
ids = [c["tv_id"] for c in TeamViewerParser({"teamviewer_paths": [utf16], "teamviewer_timezone_correction": 0}).parse_logs()]
check(ids == ["1000", "1001", "1002"], "UTF-16-TeamViewer-Log gelesen")

junk = os.path.join(DATA, "Connections_muell.txt")
with open(junk, "wb") as f:
    f.write(tv_line(1).encode() + b"\x00\xff\xfe\x81\x9d M\xfcll \x00\x00\n" + os.urandom(300) + b"\n" + tv_line(2).encode())
ids = [c["tv_id"] for c in TeamViewerParser({"teamviewer_paths": [junk], "teamviewer_timezone_correction": 0}).parse_logs()]
check("1001" in ids and "1002" in ids, "Binärmüll in der Logdatei bricht das Lesen nicht ab")

# ---------------------------------------------------------------- ohne Internet
online = {"up": False}
real_reachable = net.reachable
net.reachable = lambda url, timeout=3: online["up"]


class FakeTools:
    def call(self, method, timeout=15, **params):
        return {}

    def close(self):
        pass

    def alive(self):
        return True


starts = []


class OfflineReader(pbx_reader.PbxReader):
    def _start_browser(self):
        starts.append(1)
        self._tools = FakeTools()

    def _tick(self):
        pass


script = open(os.path.join(ROOT, "zeitzeuge_anrufe.user.js"), encoding="utf-8").read()
reader = OfflineReader("https://3cx.example.invalid:5001", os.path.join(DATA, "anrufe_off.json"),
                       os.path.join(DATA, "profil_off"), script)
troubles = []
reader.trouble.connect(troubles.append)
delays = []
for _ in range(6):
    reader._step()
    delays.append(reader._backoff.delay())
check(not starts, "offline: kein Edge gestartet")
check(delays == [20, 40, 80, 160, 320, 600], f"offline: Wartezeit wächst ({delays})")
check("offline" in reader.status and "nächster Versuch" in reader.status, f"Status: {reader.status}")
check(len(troubles) == 1, "nach 5 Fehlschlägen genau eine Meldung")
online["up"] = True
reader._step()
check(starts == [1] and reader._backoff.delay() == 0 and not reader._failed,
      "Netz wieder da: Edge startet, Wartezeit zurückgesetzt")

# Wartet der Leser offline, geht es weiter, sobald das Netz zurück ist
reader._failed, reader._offline, reader.PROBE_INTERVAL = True, True, 0.2
reader._backoff.failures = 6  # 600 s Wartezeit
online["up"] = False
threading.Timer(0.5, lambda: online.update(up=True)).start()
began = time.time()
reader._wait_next()
check(time.time() - began < 5, "nach dem Wiederkommen des Netzes sofort weitergelesen")

# ITM: Netzwerkfehler schalten die Direkt-Abfrage nicht dauerhaft ab
from itm_reader import ItmReader  # noqa: E402

itm = ItmReader("https://itm.example.invalid", os.path.join(DATA, "pz.json"), os.path.join(DATA, "itm_profil"))
itm._valid_token = lambda: "token"
itm._api = "http://127.0.0.1:9/"  # hier lauscht niemand: Verbindung abgelehnt
try:
    itm._read_day("2026-10-20")
    check(False, "ITM: Netzwerkfehler nicht gemeldet")
except OSError:
    pass
check(itm._direct_ok, "ITM: Netzwerkfehler lässt die Direkt-Abfrage an")

# KI ohne Netz: klare Meldung
online["up"] = False
failed = []
window.ai.failed.connect(lambda d, m: failed.append(m))
window.ai._run("2026-10-20", "x", "h", "claude-haiku-5-5", ["Fernwartung"], "sk-ant-test", "low")
check(failed and failed[-1].startswith("Keine Internetverbindung"), f"KI offline: {failed[-1:]}")

# ---------------------------------------------------------------- Anmeldefenster
kills = []
real_kill, real_open, real_in_use = (pbx_reader.kill_profile_processes, pbx_reader.login_window_open,
                                     pbx_reader.profile_in_use)
pbx_reader.kill_profile_processes = lambda d: kills.append(d) or 0
pbx_reader.login_window_open = lambda d: True  # Fenster bleibt offen, niemand meldet sich an
pbx_reader.profile_in_use = lambda d: False
closed = []


class LoginReader(pbx_reader.PbxReader):
    LOGIN_TIMEOUT = 1

    def _launch(self, mode, url=None):
        return 4711

    def _connect(self, port):
        self._tools = FakeTools()

    def _on_browser_started(self):
        pass

    def _close_gracefully(self, port):
        closed.append(port)


login = LoginReader("https://3cx.example.invalid", os.path.join(DATA, "anrufe_login.json"),
                    os.path.join(DATA, "profil_login"), script)
login.needs_login = True
login.show_login()
deadline = time.time() + 10
while login._login_open and time.time() < deadline:
    time.sleep(0.1)
check(not login._login_open and closed == [4711] and kills, "Anmeldefenster nach Zeitüberschreitung geschlossen")
check(login.needs_login and "Zeitüberschreitung" in login.status, f"Status: {login.status}, Anmeldung weiter nötig")

# ---------------------------------------------------------------- Wächter
online["up"] = False  # Leser im Hauptfenster startet keinen Edge
window.config["calls_3cx_url"] = "https://3cx.example.invalid"
window.start_pbx_reader()
reader = window.pbx_reader
check(reader.alive(), "3CX-Leser läuft")


def crash():
    raise SystemExit  # beendet den Thread trotz "except Exception"


reader._step = crash
reader.read()
deadline = time.time() + 5
while reader.alive() and time.time() < deadline:
    time.sleep(0.05)
check(not reader.alive(), "Lese-Thread abgestürzt (nachgestellt)")
del reader._step
window._watch_readers()
check(reader.alive(), "Wächter hat den Lese-Thread neu gestartet")
with open(os.path.join(DATA, "fehler.log"), encoding="utf-8") as f:
    check("Wächter startet ihn neu" in f.read(), "Neustart steht in fehler.log")
reader._tools = FakeTools()
reader._step_started = time.time() - reader.STEP_TIMEOUT - 1
check(reader.check_hung() and reader._tools is None, "hängender Durchlauf: Edge wird hart beendet")
check(not reader.check_hung(), "hängender Durchlauf wird nicht jede Minute erneut beendet")
stopped = len(kills)
window.stop_pbx_reader()
check(len(kills) > stopped, "Leser aus: Edge mit seinem Profil wird beendet")

# ---------------------------------------------------------------- Fehler in einem Slot
safe_io.take_problems()
QTimer.singleShot(0, lambda: 1 / 0)
threading.Thread(target=lambda: {}["fehlt"], name="Testthread").start()
end = time.time() + 1
while time.time() < end:
    app.processEvents()
    time.sleep(0.02)
with open(os.path.join(DATA, "fehler.log"), encoding="utf-8") as f:
    log = f.read()
check("ZeroDivisionError" in log and "Traceback" in log, "Ausnahme im Slot mit Stacktrace in fehler.log")
check("KeyError" in log and "Testthread" in log, "Ausnahme im Thread in fehler.log")
check("'fehlt'" not in log, "Text der Ausnahme (kann Nutzdaten enthalten) nicht in fehler.log")
window.show_problems()
check("Interner Fehler" in window.statusBar().currentMessage(), "Hinweis in der Statuszeile (einmal pro Minute)")
check(window.isEnabled(), "Zeitzeuge läuft nach der Ausnahme weiter")

# ---------------------------------------------------------------- nur eine Instanz
lock = os.path.join(DATA, "test.lock")
check(main_timeline.acquire_single_instance(lock, 100), "erste Instanz bekommt die Sperre")
held = main_timeline._instance_lock
check(not main_timeline.acquire_single_instance(lock, 100), "zweite Instanz wird abgewiesen")
held.unlock()
check(main_timeline.acquire_single_instance(lock, 100), "nach dem Beenden wieder frei")

pbx_reader.kill_profile_processes, pbx_reader.login_window_open, pbx_reader.profile_in_use = (
    real_kill, real_open, real_in_use)
net.reachable = real_reachable
window.quit_app()
print("Robustheit ok")

# Direkt beenden: die Qt-Bindung räumt beim Interpreter-Ende sporadisch in falscher Reihenfolge auf
# (Zugriffsfehler unter Windows). Alle Prüfungen sind hier gelaufen.
sys.stdout.flush()
os._exit(0)
