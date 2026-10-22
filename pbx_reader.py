"""
3CX-Anrufliste direkt aus Zeitzeuge lesen (ohne Tampermonkey).

Zeitzeuge nutzt den installierten Microsoft Edge (oder Chrome) mit einem
eigenen Profil (Ordner 3cx_profil):

- Anmelden: Edge öffnet ein normales Fenster mit dem 3CX-Webclient.
  Nach dem Anmelden schließt du es einfach.
- Lesen: Derselbe Edge läuft unsichtbar im Hintergrund (stumm, ohne
  Mikrofon/Benachrichtigungen). Zeitzeuge liest jede Minute die Anrufliste
  über die Entwickler-Schnittstelle (DevTools-Protokoll) von Edge.

Der installierte Edge ist immer aktuell, deshalb läuft auch der moderne
3CX-Webclient darin.

Die Edge-Steuerung steckt in BrowserReader und wird auch für die
ITM-Personalzeiten benutzt (itm_reader.py).
"""

import json
import os
import shlex
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import date, datetime, timedelta

import psutil
import websocket  # Paket websocket-client
from PyQt5.QtCore import QObject, pyqtSignal

import net
import safe_io
from call_import import load_calls, merge_calls

PARSER_START = "// ---- ANRUFLISTE LESEN: START ----"
PARSER_END = "// ---- ANRUFLISTE LESEN: ENDE ----"

BROWSER_PATHS = [
    r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe",
    r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe",
    r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe",
    r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
]


def build_reader_js(userscript_text):
    """Den Lese-Teil aus dem Tampermonkey-Skript nehmen und als Abfrage verpacken."""
    start = userscript_text.index(PARSER_START)
    end = userscript_text.index(PARSER_END)
    parser = userscript_text[start:end]
    return (
        "(function(){" + parser +
        "const login = !!document.querySelector('input[type=password]');"
        "return JSON.stringify({login: login, url: location.href, calls: login ? [] : sammeln()});"
        "})()"
    )


# Anrufliste nach unten scrollen, bis Anrufe vor dem Zieltag geladen sind.
# 3CX lädt ältere Anrufe erst beim Scrollen nach und entfernt dabei evtl. obere
# Einträge wieder, deshalb wird bei jedem Schritt gesammelt.
SCROLL_JS = """
async function zurueckBis(ziel) {
  const alle = new Map();
  const add = () => sammeln().forEach((a) => alle.set(a.start + "|" + (a.number || a.name), a));
  const erster = document.querySelector("app-call-history-item, [data-qa='call-history-item']");
  if (!erster) return {calls: [], erreicht: false, ende: false};
  let box = erster.parentElement;
  while (box && box !== document.body &&
         !(box.scrollHeight > box.clientHeight + 5 && /auto|scroll/.test(getComputedStyle(box).overflowY)))
    box = box.parentElement;
  const scroller = box && box !== document.body ? box : document.scrollingElement;
  let still = 0, erreicht = false;
  for (let i = 0; i < 400 && still < 6; i++) {
    add();
    const aeltester = [...alle.values()].reduce((m, a) => (a.start < m ? a.start : m), "9999");
    if (aeltester.slice(0, 10) < ziel) { erreicht = true; break; }
    const vorher = alle.size, hoehe = scroller.scrollHeight;
    scroller.scrollTop = scroller.scrollHeight;
    scroller.dispatchEvent(new Event("scroll"));
    await new Promise((r) => setTimeout(r, 700));
    add();
    still = alle.size === vorher && scroller.scrollHeight === hoehe ? still + 1 : 0;
  }
  scroller.scrollTop = 0;
  return {calls: [...alle.values()], erreicht: erreicht, ende: !erreicht};
}
"""


def build_scroll_js(userscript_text, target):
    """Wie build_reader_js, liest aber durch Scrollen bis zum Tag target (YYYY-MM-DD)."""
    start = userscript_text.index(PARSER_START)
    end = userscript_text.index(PARSER_END)
    return (
        "(async function(){" + userscript_text[start:end] + SCROLL_JS +
        "if (document.querySelector('input[type=password]')) return JSON.stringify({login: true});"
        f"return JSON.stringify(await zurueckBis({json.dumps(target)}));"
        "})()"
    )


def find_browser():
    """Pfad zu Edge/Chrome. ZEITZEUGE_BROWSER überschreibt (z. B. für Tests)."""
    if os.environ.get("ZEITZEUGE_BROWSER"):
        return os.environ["ZEITZEUGE_BROWSER"]
    for path in BROWSER_PATHS:
        path = os.path.expandvars(path)
        if os.path.exists(path):
            return path
    return None


def profile_in_use(profile_dir):
    """Ist das Edge-Profil gerade von einem Edge-Fenster belegt?

    Edge hält die Datei "lockfile" offen, solange es läuft (Windows);
    unter Linux/macOS gibt es den Verweis "SingletonLock".
    """
    if sys.platform == "win32":
        lock = os.path.join(profile_dir, "lockfile")
        if not os.path.exists(lock):
            return False
        try:
            os.remove(lock)  # geht nur, wenn kein Edge sie offen hält
            return False
        except PermissionError:
            return True
        except OSError:
            return False
    lock = os.path.join(profile_dir, "SingletonLock")  # Verweis auf "rechner-pid"
    if not os.path.islink(lock):
        return False
    try:
        os.kill(int(os.readlink(lock).rsplit("-", 1)[1]), 0)
        return True
    except (ValueError, IndexError, ProcessLookupError):
        return False
    except PermissionError:
        return True


def profile_processes(profile_dir):
    """Alle Edge/Chrome-Prozesse, die mit genau diesem Profil laufen (nie dein normaler Edge)."""
    wanted = os.path.normcase(os.path.abspath(profile_dir))
    exe = os.path.basename(find_browser() or "").lower()
    names = {n for n in (exe, "msedge.exe", "chrome.exe", "msedge", "chrome") if n}
    found = []
    # Nur den Namen aller Prozesse lesen (schnell), die Befehlszeile nur bei Edge/Chrome
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if (proc.info["name"] or "").lower() not in names:
                continue
            for arg in proc.cmdline() or []:
                if arg.startswith("--user-data-dir=") and \
                        os.path.normcase(os.path.abspath(arg.split("=", 1)[1].strip('"'))) == wanted:
                    found.append(proc)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            continue
    return found


def _cmdline(proc):
    try:
        return proc.cmdline() or []
    except psutil.Error:
        return []


def kill_profile_processes(profile_dir):
    """Übrig gebliebene Edge-Prozesse mit diesem Profil beenden (z. B. Hintergrundmodus)."""
    procs = profile_processes(profile_dir)
    for proc in procs:
        try:
            proc.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(procs, timeout=5)
    for proc in alive:
        try:
            proc.kill()
        except psutil.Error:
            pass
    return len(procs)


def login_window_open(profile_dir):
    """Ist ein sichtbares Edge-Fenster mit diesem Profil offen?"""
    procs = profile_processes(profile_dir)
    if sys.platform != "win32":
        # Hauptprozess (ohne --type=…) ohne --headless = sichtbares Fenster
        return any("--headless" not in cmd and "--type=" not in cmd and "-32000" not in cmd
                   for cmd in (" ".join(_cmdline(p)) for p in procs))
    import ctypes
    from ctypes import wintypes
    pids = {p.pid for p in procs}
    if not pids:
        return False
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def check(hwnd, _):
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if rect.left > -10000 and user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids:
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(check, 0)
    return bool(found)


class _DevTools:
    """Minimaler Client für das DevTools-Protokoll einer Seite."""

    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=15, suppress_origin=True)
        self._id = 0

    def call(self, method, timeout=15, **params):
        """Befehl senden und auf seine Antwort warten, höchstens timeout Sekunden insgesamt
        (Edge schickt dazwischen laufend Ereignisse, die zählen nicht als Antwort)."""
        if not self.alive():
            raise ConnectionError("Verbindung zu Edge getrennt")
        deadline = time.time() + timeout
        self._id += 1
        self.ws.settimeout(timeout)
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise TimeoutError(f"Edge antwortet nicht auf {method}")
            self.ws.settimeout(left)
            raw = self.ws.recv()
            if not raw:  # Verbindung zu (Edge beendet oder abgestürzt)
                raise ConnectionError("Verbindung zu Edge getrennt")
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message"))
                return msg.get("result", {})

    def alive(self):
        return bool(getattr(self.ws, "connected", False))

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


class BrowserReader(QObject):
    """Webseite unsichtbar in Edge offen halten und regelmäßig auslesen.

    Unterklassen setzen start_url() und _tick() (einmal lesen).
    """
    # Signale werden aus dem Hintergrund-Thread gesendet (Qt stellt sie zu)
    status_changed = pyqtSignal(str)
    login_required = pyqtSignal()
    recording_done = pyqtSignal(str)  # Pfad der Mitschnitt-Datei, leer bei Fehler
    trouble = pyqtSignal(str)  # einmal nach TROUBLE_AFTER Fehlschlägen in Folge (Infobereich)

    READ_INTERVAL = 60  # Sekunden zwischen zwei Durchläufen
    START_BROWSER = True  # False: der Leser startet Edge selbst nur bei Bedarf
    RETRY_INTERVAL = 20  # nach einem Fehler früher neu versuchen (verdoppelt sich, siehe net.Backoff)
    NAME = "Seite"
    LOGIN_TIMEOUT = 10 * 60  # Anmeldefenster schließt sich, wenn sich so lange niemand anmeldet
    STEP_TIMEOUT = 15 * 60   # länger darf ein Durchlauf nicht hängen, sonst Edge hart beenden
    PROBE_INTERVAL = 30      # offline: so oft prüfen, ob das Netz wieder da ist
    TROUBLE_AFTER = 5        # nach so vielen Fehlschlägen in Folge einmal melden

    def __init__(self, base_url, profile_dir, parent=None):
        super().__init__(parent)
        self.base_url = base_url.strip().rstrip("/")
        self.profile_dir = profile_dir
        self.needs_login = False
        self.status = "Startet …"

        self._proc = None
        self._tools = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._login_open = False
        self._started = False  # Browser frisch gestartet (Seite lädt noch)
        self._failed = False   # letzter Durchlauf mit Fehler
        self._thread = None
        # Nur ein Edge darf das Profil benutzen: Lesen und Anmelden wechseln sich ab
        self._browser_lock = threading.Lock()
        self._record_stop = threading.Event()
        self._backoff = net.Backoff()
        self._backoff.START = self.RETRY_INTERVAL
        self._offline = False
        self._step_started = None  # Beginn des laufenden Durchlaufs (für check_hung)
        self._cleaned = False      # Reste eines früheren Laufs beendet
        self.next_try = None       # nächster Versuch nach einem Fehler (datetime)

    def start_url(self):
        raise NotImplementedError

    # ------------------------------------------------------------ Steuerung

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name=f"Leser {self.NAME}")
        self._thread.start()

    def stop(self):
        """Lesen beenden. Auch ein offenes Anmelde- oder Mitschnitt-Fenster geht zu."""
        self._stop.set()
        self._record_stop.set()
        self._wake.set()
        self._close_browser()
        # Kein Edge mit unserem Profil darf übrig bleiben, auch nicht mitten im Anmelden
        try:
            kill_profile_processes(self.profile_dir)
        except Exception as e:
            safe_io.log(f"{self.NAME}: Edge-Reste nicht beendet: {e}")

    @property
    def stopped(self):
        return self._stop.is_set()

    def alive(self):
        """Läuft der Lese-Thread?"""
        return bool(self._thread and self._thread.is_alive())

    def check_hung(self):
        """Hängt ein Durchlauf länger als STEP_TIMEOUT: Edge hart beenden, dann bricht der
        Durchlauf mit Fehler ab und der nächste startet Edge neu. True, wenn es so war."""
        started = self._step_started
        if not started or time.time() - started < self.STEP_TIMEOUT:
            return False
        self._step_started = time.time()  # nicht jede Minute erneut
        safe_io.log(f"{self.NAME}: Durchlauf hängt seit {int(time.time() - started)} s, beende Edge")
        tools, self._tools = self._tools, None
        if tools:
            tools.close()
        # Prozesse suchen dauert etwas: nicht im Fenster-Thread
        threading.Thread(target=kill_profile_processes, args=(self.profile_dir,), daemon=True).start()
        return True

    def read(self):
        """Sofort lesen (statt auf den nächsten Durchlauf zu warten)."""
        self._wake.set()

    def show_login(self, parent=None):
        """Edge-Fenster zum Anmelden öffnen. Nach dem Schließen wird weitergelesen."""
        if self._login_open:
            return
        self._login_open = True
        self._set_status(f"{self.NAME}: Anmeldung im Edge-Fenster …")
        threading.Thread(target=self._login_window, daemon=True).start()

    def record(self, out_file, mode="login", max_seconds=30 * 60):
        """Mitschnitt: Edge-Fenster öffnen und aufzeichnen, welche Abfragen die Seite
        an ihren Server schickt, bis du das Fenster schließt. Ergebnis über recording_done."""
        if self._login_open:
            return False
        self._login_open = True
        self._record_stop.clear()
        threading.Thread(target=self._record_window, args=(out_file, mode, max_seconds),
                         daemon=True).start()
        return True

    def stop_recording(self):
        self._record_stop.set()

    # ------------------------------------------------------------ Browser

    def _browser_args(self, mode, debug=True, url=None):
        """mode: "headless" (unsichtbar), "hidden" (Fenster außerhalb des Bildschirms),
        "login" (normales Fenster zum Anmelden)."""
        exe = find_browser()
        if not exe:
            raise RuntimeError("Microsoft Edge oder Google Chrome nicht gefunden")
        os.makedirs(self.profile_dir, exist_ok=True)
        args = [
            exe,
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--mute-audio",
            "--deny-permission-prompts",
            "--disable-notifications",
            # Unsichtbare Seite nicht drosseln oder schlafen legen, sonst bleibt sie stehen
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
        ]
        args += shlex.split(os.environ.get("ZEITZEUGE_BROWSER_ARGS", ""))
        if debug:
            args += ["--remote-debugging-port=0", "--remote-allow-origins=*"]
        if mode == "login":
            return args + [f"--app={url or self.start_url()}", "--window-size=1100,800"]
        args += ["--window-size=1100,2400"]
        if mode == "headless":
            return args + ["--headless=new", "about:blank"]
        # Ersatz, falls der unsichtbare Modus gesperrt ist: Fenster weit außerhalb des Bildschirms
        return args + ["--window-position=-32000,-32000", "--app=about:blank"]

    def _popen(self, args):
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        return subprocess.Popen(args, creationflags=flags,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _wait_profile_free(self, seconds):
        deadline = time.time() + seconds
        while profile_in_use(self.profile_dir) and time.time() < deadline:
            time.sleep(0.5)
        return not profile_in_use(self.profile_dir)

    def _start_browser(self):
        if profile_in_use(self.profile_dir) and not login_window_open(self.profile_dir):
            # Unsichtbarer Rest (alter Lauf, Edge-Hintergrundmodus): beenden
            kill_profile_processes(self.profile_dir)
        if not self._wait_profile_free(10):
            raise RuntimeError(f"ein Edge-Fenster mit dem {self.NAME}-Profil ist noch offen")
        mode = getattr(self, "_mode", "headless")
        try:
            port = self._launch(mode)
        except RuntimeError as e:
            if mode != "headless":
                raise
            # Unsichtbarer Modus klappt nicht (z. B. per Richtlinie gesperrt): Ersatzmodus
            self._set_status(f"{self.NAME}: unsichtbarer Modus geht nicht ({e}), nehme Ersatz")
            kill_profile_processes(self.profile_dir)
            self._mode = "hidden"
            port = self._launch("hidden")

        self._connect(port)

        # Kein "HeadlessChrome" in der Kennung, sonst verhalten sich manche Seiten anders
        version = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=10))
        agent = version.get("User-Agent", "").replace("HeadlessChrome", "Chrome")
        if agent:
            self._tools.call("Network.setUserAgentOverride", userAgent=agent)
        self._on_browser_started()

    def _connect(self, port):
        pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10))
        page = next(p for p in pages if p.get("type") == "page")
        self._tools = _DevTools(page["webSocketDebuggerUrl"])

    def _launch(self, mode, url=None):
        """Edge starten und warten, bis er seine DevTools-Schnittstelle meldet. Gibt den Port zurück."""
        if self._stop.is_set():
            raise RuntimeError("Zeitzeuge beendet das Lesen")
        port_file = os.path.join(self.profile_dir, "DevToolsActivePort")
        if os.path.exists(port_file):
            os.remove(port_file)
        self._proc = self._popen(self._browser_args(mode, url=url))

        # Edge schreibt seinen Port in DevToolsActivePort. Er gibt beim Start oft an einen
        # anderen Prozess ab, darum zählt die Datei, nicht der gestartete Prozess.
        deadline = time.time() + 20
        next_check = 0
        while time.time() < deadline:
            first = ""
            try:
                with open(port_file, encoding="utf-8") as f:
                    first = f.readline().strip()
            except OSError:
                pass  # fehlt noch oder Edge schreibt gerade (unter Windows gesperrt)
            if first.isdigit():
                return int(first)
            code = self._proc.poll()
            # Alle Prozesse durchsuchen ist teuer: nur alle 2 s, nicht bei jedem Durchlauf
            if code is not None and time.time() > next_check:
                next_check = time.time() + 2
                if not profile_processes(self.profile_dir):
                    raise RuntimeError(f"Edge hat sich beendet, Code {code}")
            time.sleep(0.2)
        code = self._proc.poll()
        kill_profile_processes(self.profile_dir)
        raise RuntimeError("Edge antwortet nicht" + (f", Code {code}" if code is not None else ""))

    def _on_browser_started(self):
        self._tools.call("Page.navigate", url=self.start_url())

    def _close_browser(self):
        self._close_tools()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._proc:
            kill_profile_processes(self.profile_dir)  # falls Edge an einen anderen Prozess abgab
        self._proc = None

    def _login_window(self):
        self._wake.set()  # Lese-Schleife aus dem Warten holen
        timed_out = False
        with self._browser_lock:
            try:
                self._close_browser()  # unsichtbaren Edge beenden, Profil freigeben
                kill_profile_processes(self.profile_dir)  # Reste, an die Edge sonst weiterleitet
                self._wait_profile_free(15)
                port = None
                try:  # Seite beobachten, um das Fenster nach der Anmeldung selbst zu schließen
                    port = self._launch("login")
                    self._connect(port)
                    self._on_browser_started()
                    self._tools.call("Page.reload")  # mit den eben eingerichteten Skripten
                except Exception:
                    self._close_tools()  # dann schließt du das Fenster selbst
                    if port is None:  # Fernsteuerung gesperrt: Fenster wie früher ohne öffnen
                        kill_profile_processes(self.profile_dir)
                        self._wait_profile_free(15)
                        self._proc = self._popen(self._browser_args("login", debug=False))
                # Warten, bis die Anmeldung geklappt hat oder du das Fenster schließt. Edge gibt
                # beim Start an einen anderen Prozess ab, darum zählt ein sichtbares Fenster.
                started = opened = time.time()
                ok = 0
                while not self._stop.is_set():
                    ok = ok + 1 if self._tools and self._login_done() else 0
                    if ok >= 2:  # zweimal hintereinander, damit kein Zwischenstand zählt
                        self._set_status(f"{self.NAME}: angemeldet, Anmeldefenster wird geschlossen")
                        self._close_gracefully(port)
                        break
                    if time.time() - opened > self.LOGIN_TIMEOUT:
                        timed_out = True  # niemand meldet sich an: Fenster nicht ewig offen lassen
                        if port:
                            self._close_gracefully(port)
                        break
                    if login_window_open(self.profile_dir):
                        started = min(started, time.time() - 60)  # Fenster war schon da
                    elif time.time() - started > 30:
                        break  # Fenster zu (oder nach 30 s nie erschienen)
                    time.sleep(1)
                # Edge läuft nach dem Schließen oft im Hintergrund weiter: beenden
                self._close_tools()
                kill_profile_processes(self.profile_dir)
                self._proc = None
                if timed_out:
                    self._set_status(f"{self.NAME}: Anmeldung abgebrochen (Zeitüberschreitung)")
                    safe_io.log(f"{self.NAME}: Anmeldefenster nach {self.LOGIN_TIMEOUT} s "
                                "ohne Anmeldung geschlossen")
                else:
                    self._set_status(f"{self.NAME}: Anmeldefenster geschlossen, lese …")
            except Exception as e:
                self._set_status(f"{self.NAME}: {e}")
            finally:
                self._login_open = False
                self.needs_login = timed_out  # nach Zeitüberschreitung weiter nötig
        self._wake.set()

    def _record_window(self, out_file, mode, max_seconds):
        from request_recorder import Recorder  # nur hier gebraucht

        self._wake.set()  # Lese-Schleife aus dem Warten holen
        path = ""
        with self._browser_lock:
            try:
                self._close_browser()  # unsichtbaren Edge beenden, Profil freigeben
                kill_profile_processes(self.profile_dir)
                self._wait_profile_free(15)
                # Leer starten, damit schon die erste Abfrage der Seite mitgeschnitten wird
                port = self._launch(mode, url="about:blank")
                pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10))
                page = next(p for p in pages if p.get("type") == "page")
                version = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=10))
                recorder = Recorder(page["webSocketDebuggerUrl"], self.start_url(), self.NAME)
                self._set_status(f"{self.NAME}: Mitschnitt läuft, Fenster schließen zum Beenden")
                recorder.run(self._record_stop, max_seconds)
                data = recorder.result(version.get("Browser", ""))
                if not safe_io.write_json(out_file, data):
                    raise OSError("Datei konnte nicht gespeichert werden")
                path = out_file
                self._close_gracefully(port)  # Anmeldung aus dem Fenster bleibt gespeichert
                self._set_status(f"{self.NAME}: Mitschnitt gespeichert ({len(data['abfragen'])} Abfragen)")
            except Exception as e:
                self._set_status(f"{self.NAME}: Mitschnitt fehlgeschlagen ({e})")
            finally:
                self._close_tools()
                kill_profile_processes(self.profile_dir)
                self._proc = None
                self._login_open = False
        self.recording_done.emit(path)
        self._wake.set()

    def browser_cookies(self):
        """Alle Cookies aus dem Edge-Profil (auch HttpOnly). Startet Edge kurz unsichtbar,
        falls er gerade nicht läuft. Aufruf nur mit gehaltenem _browser_lock."""
        own = not self._tools
        if own:
            self._start_browser()
        try:
            return self._tools.call("Network.getAllCookies").get("cookies", [])
        finally:
            if own:
                self._close_browser()

    def _login_done(self):
        """Zeigt das Anmeldefenster schon die Seite nach der Anmeldung? (je Leser)"""
        return False

    def _close_tools(self):
        if self._tools:
            self._tools.close()
            self._tools = None

    def _close_gracefully(self, port):
        """Edge regulär beenden, damit die Anmeldung (Cookies) im Profil gespeichert wird."""
        try:
            info = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5))
            _DevTools(info["webSocketDebuggerUrl"]).call("Browser.close", timeout=5)
        except Exception:
            pass  # Edge schon zu: dann bleibt nur das Beenden danach
        deadline = time.time() + 10
        while profile_processes(self.profile_dir) and time.time() < deadline:
            time.sleep(0.5)

    # ------------------------------------------------------------ Lesen

    def _set_status(self, text):
        self.status = text
        self.status_changed.emit(text)

    def _need_login(self):
        if not self.needs_login:
            self.needs_login = True
            self.login_required.emit()
        self._set_status(f"{self.NAME}: Anmeldung nötig")

    def _evaluate(self, js, timeout=15):
        result = self._tools.call("Runtime.evaluate", timeout=timeout, expression=js,
                                  returnByValue=True, awaitPromise=True)
        return result.get("result", {}).get("value")

    def _loop(self):
        # Darf nie sterben: Jeder Fehler eines Durchlaufs wird gefangen und gemeldet
        while not self._stop.is_set():
            try:
                if not self._login_open:
                    with self._browser_lock:
                        if not self._cleaned:  # Reste eines abgestürzten Laufs (auch Anmeldefenster)
                            self._cleaned = True
                            kill_profile_processes(self.profile_dir)
                        self._step_started = time.time()
                        try:
                            self._step()
                        finally:
                            self._step_started = None
            except Exception as e:  # unerwartet (z. B. Fehler beim Aufräumen)
                if self._stop.is_set():
                    break
                safe_io.log(f"{self.NAME}: unerwarteter Fehler im Lese-Thread: {e!r}")
                self._failed_step(e)
            try:
                self._wait_next()
            except Exception as e:
                safe_io.log(f"{self.NAME}: Fehler beim Warten: {e!r}")
                self._wake.wait(self.RETRY_INTERVAL)
        self._close_browser()

    def _wait_next(self):
        """Bis zum nächsten Durchlauf warten. Nach Fehlern länger (Backoff). Offline wird
        zwischendurch geprüft, ob das Netz wieder da ist: dann geht es sofort weiter."""
        delay = self._backoff.delay() if self._failed else self.READ_INTERVAL
        end = time.time() + delay
        while not self._stop.is_set():
            left = end - time.time()
            if left <= 0:
                break
            if self._wake.wait(min(left, self.PROBE_INTERVAL) if self._offline else left):
                break
            if self._offline and net.reachable(self.base_url):
                break
        self._wake.clear()

    def _step(self):
        """Ein Durchlauf: Erreichbarkeit prüfen, Browser bei Bedarf starten, dann lesen."""
        if self._login_open or self._stop.is_set():
            return
        try:
            if not self._online():
                return
            if self._tools and not self._tools.alive():
                # Edge abgestürzt oder im Task-Manager beendet: aufräumen, gleich neu starten
                safe_io.log(f"{self.NAME}: Verbindung zu Edge verloren, starte neu")
                self._close_browser()
            if not self._tools and self.START_BROWSER:
                self._start_browser()
                self._started = True
            self._tick()
            self._failed = False
            self._backoff.reset()
            self.next_try = None
        except Exception as e:
            if self._stop.is_set():
                return  # beim Beenden abgebrochen: kein Fehler
            self._failed_step(e)
            self._close_browser()

    def _online(self):
        """Server erreichbar? Offline: Fehlversuch zählen und keinen Edge starten."""
        if net.reachable(self.base_url):
            if self._offline:
                self._offline = False
                safe_io.log(f"{self.NAME}: Server wieder erreichbar")
                self._on_back_online()
            return True
        if not self._offline:
            safe_io.log(f"{self.NAME}: Server nicht erreichbar ({self.base_url})")
        self._offline = True
        self._failed_step(None)
        return False

    def _on_back_online(self):
        """Netz ist wieder da (je Leser, z. B. Seite neu laden)."""

    def _failed_step(self, error):
        """Fehlschlag merken: Wartezeit verlängern, Status setzen, nach TROUBLE_AFTER einmal melden."""
        self._failed = True
        delay = self._backoff.fail()
        self.next_try = datetime.now() + timedelta(seconds=delay)
        when = f"{self.next_try:%H:%M}"
        if error is None:
            text = f"{self.NAME}: offline, nächster Versuch {when}"
        else:
            text = f"{self.NAME}: Fehler ({str(error)[:150] or type(error).__name__}), nächster Versuch {when}"
            safe_io.log(text)
        self._set_status(text)
        if self._backoff.failures == self.TROUBLE_AFTER:
            self.trouble.emit(
                f"{self.NAME}: Server nicht erreichbar. Zeitzeuge versucht es weiter." if error is None
                else f"{self.NAME} lässt sich seit {self.TROUBLE_AFTER} Versuchen nicht lesen "
                     f"({str(error)[:120]}). Zeitzeuge versucht es weiter.")

    def _tick(self):
        raise NotImplementedError


class PbxReader(BrowserReader):
    calls_added = pyqtSignal(int)
    check_done = pyqtSignal(str, str)  # Pfad des Prüfberichts (leer bei Fehler), Ergebnis

    # 3CX aktualisiert die Anrufliste im unsichtbaren Edge nicht zuverlässig von selbst,
    # darum die Seite regelmäßig neu laden
    RELOAD_INTERVAL = 5 * 60
    NAME = "3CX"
    def __init__(self, base_url, calls_file, profile_dir, userscript_text, parent=None,
                 days_back=14):
        super().__init__(base_url, profile_dir, parent)
        self.calls_file = calls_file
        self.days_back = days_back  # so viele Tage immer vollständig halten (Einstellung)
        self.userscript_text = userscript_text
        self.js = build_reader_js(userscript_text)
        self.last_read = None
        self.last_count = 0
        self._last_load = 0
        # Ab diesem Tag (YYYY-MM-DD) sind alle Anrufe in anrufe.json
        self.state_file = os.path.join(os.path.dirname(calls_file), "anrufe_stand.json")
        done = safe_io.read_json(self.state_file, {}, expect=dict).get("vollstaendig_ab")
        self.complete_from = done if isinstance(done, str) else None
        self._back_to = None   # angezeigter Tag, für den nachgelesen werden soll
        self._list_end = None  # ältester Tag, den 3CX noch zeigt (nur diese Sitzung)

    def want(self, date_str):
        """Anrufe bis zu diesem Tag nachlesen, falls sie noch fehlen (z. B. beim Blättern)."""
        if self.complete_from and date_str >= self.complete_from:
            return
        if self._list_end and date_str < self._list_end:
            return  # so alte Anrufe zeigt 3CX nicht mehr
        if not self._back_to or date_str < self._back_to:
            self._back_to = date_str
            if not self.needs_login:  # ohne Anmeldung erst nach dem Anmelden lesen
                self._wake.set()

    def call_list_url(self):
        return f"{self.base_url}/#/call_history/all"

    def _on_back_online(self):
        self._last_load = 0  # Seite zeigt evtl. noch einen Netzwerkfehler: neu laden

    start_url = call_list_url

    def _tick(self):
        if self._started:  # Browser frisch gestartet: Seite laden lassen
            self._started = False
            self._last_load = time.time()
            self._set_status("3CX: Seite lädt …")
            self._wait_load()
        # Nach Mitternacht sofort neu laden, sonst hieße "Heute 23:50" schon morgen
        elif (time.time() - self._last_load > self.RELOAD_INTERVAL
              or date.fromtimestamp(self._last_load) != date.today()):
            # Page.reload statt Page.navigate: Die Adresse endet auf "#/…", ein Navigieren
            # dorthin springt nur innerhalb der Seite und lädt nichts neu.
            self._tools.call("Page.reload", ignoreCache=True)
            self._last_load = time.time()
            self._wait_load()
        if not self._login_open and not self._stop.is_set() and self._read_once():
            target = self._back_to
            # Die eingestellten Tage zurück vollständig halten (auch wenn die Zahl erhöht wurde)
            first = (date.today() - timedelta(days=self.days_back)).isoformat()
            if ((not self.complete_from or first < self.complete_from)
                    and not (self._list_end and first < self._list_end)):
                target = min(target or first, first)
            if target:
                self._scroll_back(target)

    def _scroll_back(self, target):
        """Anrufliste bis zum Tag target zurückscrollen und alles übernehmen."""
        self._set_status(f"3CX: lese Anrufe bis {target} …")
        raw = self._evaluate(build_scroll_js(self.userscript_text, target), timeout=400)
        data = json.loads(raw) if raw else {}
        if data.get("login"):
            self._need_login()
            return
        self._back_to = None
        calls = data.get("calls") or []
        if not calls:
            return
        added = merge_calls(self.calls_file, calls)
        if data.get("ende"):
            self._list_end = min(c["start"][:10] for c in calls)
        done = target if data.get("erreicht") else self._list_end
        if not self.complete_from or done < self.complete_from:
            self.complete_from = done
            safe_io.write_json(self.state_file, {"vollstaendig_ab": done}, indent=None)
        self._set_status(f"3CX gelesen {datetime.now():%H:%M} (vollständig ab {done})")
        if added:
            self.calls_added.emit(added)

    def _login_done(self):
        try:
            data = json.loads(self._evaluate(self.js, timeout=5) or "null")
        except Exception:
            return False  # Seite lädt gerade neu
        return bool(data and not data["login"] and data["calls"])

    def _wait_load(self):
        time.sleep(10)  # Seite laden lassen

    def _read_once(self):
        """Sichtbare Anrufliste lesen. True, wenn Anrufe gelesen wurden."""
        return self._on_result(self._evaluate(self.js))

    def _on_result(self, raw):
        try:
            data = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            data = None
        if not data:
            self._set_status("3CX: Seite lädt noch")
            return False

        if data["login"]:
            self._need_login()
            return False
        self.needs_login = False

        # Nur die Ansicht "Alle Anrufe" enthält alles (3CX springt sonst z. B. auf "verpasst")
        if not data["url"].rstrip("/").endswith("#/call_history/all"):
            if self._tools:
                self._tools.call("Runtime.evaluate", expression="location.hash = '#/call_history/all'")
            self._set_status("3CX: wechsle zu „Alle Anrufe“ …")
            return False

        calls = data["calls"]
        if not calls:
            self._set_status("3CX: noch keine Anrufe gelesen")
            return False

        added = merge_calls(self.calls_file, calls)
        self.last_read = datetime.now()
        self.last_count = len(calls)
        self._set_status(f"3CX gelesen {self.last_read:%H:%M} ({len(calls)} Anrufe)")
        if added:
            self.calls_added.emit(added)
        return True

    # ------------------------------------------------------------ Direkt-Abfrage prüfen

    def check_direct(self, out_file):
        """Anrufe direkt vom Server holen (ohne Webseite) und mit anrufe.json vergleichen.

        Der Bericht enthält Zeiten und Feldwerte, Namen und Nummern nur maskiert. Damit
        lässt sich festlegen, welches Feld Dauer und Richtung trägt."""
        threading.Thread(target=self._check_direct, args=(out_file,), daemon=True).start()

    def _check_direct(self, out_file):
        from pbx_direct import LoginRequired, PbxClient, _jwt_claims
        from request_recorder import mask_text

        self._wake.set()
        try:
            with self._browser_lock:
                self._set_status("3CX: hole Anmeldung aus dem Edge-Profil …")
                cookies = self.browser_cookies()
            cookie = next((c["value"] for c in cookies if c.get("name") == "RefreshTokenCookie"), None)
            if not cookie:
                raise LoginRequired("kein Anmelde-Cookie im Edge-Profil, bitte bei 3CX anmelden")
            client = PbxClient(self.base_url, cookie)
            self._set_status("3CX: frage Anrufliste direkt ab …")
            client.login()
            calls = client.call_history(0) + client.call_history(80)  # zwei Seiten
        except Exception as e:
            self._set_status(f"3CX: Direkt-Abfrage fehlgeschlagen ({e})")
            self.check_done.emit("", f"Direkt-Abfrage fehlgeschlagen: {e}")
            return

        known = load_calls(self.calls_file)
        by_minute = {}
        for c in known:
            by_minute.setdefault(c.get("start", "")[:16], []).append(c)

        def fmt(t):
            return t.strftime("%Y-%m-%d %H:%M:%S") if t else None

        rows = []
        for call in calls:
            matches = []
            if call["start"]:
                for delta in (-1, 0, 1):
                    key = fmt(call["start"] + timedelta(minutes=delta))[:16]
                    matches += by_minute.get(key, [])
            rows.append({
                "start": fmt(call["start"]), "t3": fmt(call["t3"]), "ende": fmt(call["end"]),
                "flags": call["flags"], "status": call["status"],
                "nummer": mask_text(call["number"]), "name": mask_text(call["name"]),
                "f8": mask_text(call["f8"]), "firma": bool(call["company"]),
                "in_anrufe_json": [{"start": m.get("start"), "richtung": m.get("direction"),
                                    "dauer_s": m.get("duration_s"),
                                    "nummer": mask_text(m.get("number") or ""),
                                    "name": mask_text(m.get("name") or "")} for m in matches],
            })
        claims = _jwt_claims(client.token)
        report = {
            "erstellt": datetime.now().isoformat(timespec="seconds"),
            "nebenstelle": mask_text(client.extension),
            "token_felder": sorted(claims),
            "anrufe": len(calls),
            "vergleich": rows,
        }
        safe_io.write_json(out_file, report)
        found = sum(1 for r in rows if r["in_anrufe_json"])
        text = f"{len(calls)} Anrufe direkt gelesen, {found} davon auch in anrufe.json gefunden."
        self._set_status(f"3CX: Direkt-Abfrage klappt ({len(calls)} Anrufe)")
        self.check_done.emit(out_file, text)

