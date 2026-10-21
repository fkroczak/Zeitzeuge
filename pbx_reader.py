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

from call_import import merge_calls

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
    found = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            for arg in proc.info["cmdline"] or []:
                if arg.startswith("--user-data-dir=") and \
                        os.path.normcase(os.path.abspath(arg.split("=", 1)[1].strip('"'))) == wanted:
                    found.append(proc)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            continue
    return found


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
        return any("--headless" not in cmd and "--type=" not in cmd
                   for cmd in (" ".join(p.info["cmdline"] or []) for p in procs))
    import ctypes
    from ctypes import wintypes
    pids = {p.pid for p in procs}
    if not pids:
        return False
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def check(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd):
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
        self.ws.settimeout(timeout)
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message"))
                return msg.get("result", {})

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

    READ_INTERVAL = 60  # Sekunden zwischen zwei Durchläufen
    NAME = "Seite"

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
        self._thread = None
        # Nur ein Edge darf das Profil benutzen: Lesen und Anmelden wechseln sich ab
        self._browser_lock = threading.Lock()

    def start_url(self):
        raise NotImplementedError

    # ------------------------------------------------------------ Steuerung

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        self._close_browser()

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

    # ------------------------------------------------------------ Browser

    def _browser_args(self, headless):
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
        ]
        args += shlex.split(os.environ.get("ZEITZEUGE_BROWSER_ARGS", ""))
        if headless:
            args += [
                "--headless=new",
                "--remote-debugging-port=0",
                "--remote-allow-origins=*",
                "--window-size=1100,2400",
                "about:blank",
            ]
        else:
            args += [f"--app={self.start_url()}", "--window-size=1100,800"]
        return args

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
        port_file = os.path.join(self.profile_dir, "DevToolsActivePort")
        if os.path.exists(port_file):
            os.remove(port_file)
        self._proc = self._popen(self._browser_args(headless=True))

        # Edge schreibt seinen Port in DevToolsActivePort
        port = None
        for _ in range(100):
            if self._proc.poll() is not None:
                raise RuntimeError("Browser wurde sofort beendet")
            if os.path.exists(port_file):
                with open(port_file, encoding="utf-8") as f:
                    first = f.readline().strip()
                if first.isdigit():
                    port = int(first)
                    break
            time.sleep(0.2)
        if not port:
            raise RuntimeError("Browser antwortet nicht")

        pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10))
        page = next(p for p in pages if p.get("type") == "page")
        self._tools = _DevTools(page["webSocketDebuggerUrl"])

        # Kein "HeadlessChrome" in der Kennung, sonst verhalten sich manche Seiten anders
        version = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=10))
        agent = version.get("User-Agent", "").replace("HeadlessChrome", "Chrome")
        if agent:
            self._tools.call("Network.setUserAgentOverride", userAgent=agent)
        self._on_browser_started()

    def _on_browser_started(self):
        self._tools.call("Page.navigate", url=self.start_url())

    def _close_browser(self):
        if self._tools:
            self._tools.close()
            self._tools = None
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def _login_window(self):
        self._wake.set()  # Lese-Schleife aus dem Warten holen
        with self._browser_lock:
            try:
                self._close_browser()  # unsichtbaren Edge beenden, Profil freigeben
                kill_profile_processes(self.profile_dir)  # Reste, an die Edge sonst weiterleitet
                self._wait_profile_free(15)
                self._popen(self._browser_args(headless=False))
                # Warten, bis du das Fenster schließt. Edge gibt beim Start an einen anderen
                # Prozess ab, darum zählt ein sichtbares Fenster mit unserem Profil.
                started = time.time()
                while not self._stop.is_set():
                    if login_window_open(self.profile_dir):
                        started = min(started, time.time() - 60)  # Fenster war schon da
                    elif time.time() - started > 30:
                        break  # Fenster zu (oder nach 30 s nie erschienen)
                    time.sleep(1)
                # Edge läuft nach dem Schließen oft im Hintergrund weiter: beenden
                kill_profile_processes(self.profile_dir)
                self._set_status(f"{self.NAME}: Anmeldefenster geschlossen, lese …")
            except Exception as e:
                self._set_status(f"{self.NAME}: {e}")
            finally:
                self._login_open = False
                self.needs_login = False
        self._wake.set()

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
        while not self._stop.is_set():
            if not self._login_open:
                with self._browser_lock:
                    self._step()
            self._wake.wait(self.READ_INTERVAL)
            self._wake.clear()
        self._close_browser()

    def _step(self):
        """Ein Durchlauf: Browser bei Bedarf starten, dann lesen."""
        if self._login_open or self._stop.is_set():
            return
        try:
            if not self._tools:
                self._start_browser()
                self._started = True
            self._tick()
        except Exception as e:
            self._set_status(f"{self.NAME}: Fehler ({e}), neuer Versuch")
            self._close_browser()

    def _tick(self):
        raise NotImplementedError


class PbxReader(BrowserReader):
    calls_added = pyqtSignal(int)

    RELOAD_INTERVAL = 15 * 60
    NAME = "3CX"
    FIRST_DAYS = 14  # beim ersten Lauf so viele Tage zurück lesen

    def __init__(self, base_url, calls_file, profile_dir, userscript_text, parent=None):
        super().__init__(base_url, profile_dir, parent)
        self.calls_file = calls_file
        self.userscript_text = userscript_text
        self.js = build_reader_js(userscript_text)
        self.last_read = None
        self.last_count = 0
        self._last_load = 0
        # Ab diesem Tag (YYYY-MM-DD) sind alle Anrufe in anrufe.json
        self.state_file = os.path.join(os.path.dirname(calls_file), "anrufe_stand.json")
        try:
            with open(self.state_file, encoding="utf-8") as f:
                self.complete_from = json.load(f).get("vollstaendig_ab")
        except (OSError, ValueError, AttributeError):
            self.complete_from = None
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
            self._tools.call("Page.navigate", url=self.call_list_url())
            self._last_load = time.time()
            self._wait_load()
        if not self._login_open and not self._stop.is_set() and self._read_once():
            target = self._back_to
            if not self.complete_from:
                first = (date.today() - timedelta(days=self.FIRST_DAYS)).isoformat()
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
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({"vollstaendig_ab": done}, f)
        self._set_status(f"3CX gelesen {datetime.now():%H:%M} (vollständig ab {done})")
        if added:
            self.calls_added.emit(added)

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

        calls = data["calls"]
        if not calls:
            if "call_history" not in data["url"] and self._tools:
                self._tools.call("Page.navigate", url=self.call_list_url())
            self._set_status("3CX: noch keine Anrufe gelesen")
            return False

        added = merge_calls(self.calls_file, calls)
        self.last_read = datetime.now()
        self.last_count = len(calls)
        self._set_status(f"3CX gelesen {self.last_read:%H:%M} ({len(calls)} Anrufe)")
        if added:
            self.calls_added.emit(added)
        return True
