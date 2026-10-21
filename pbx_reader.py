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
"""

import json
import os
import shlex
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime

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
    """Übrig gebliebene Edge-Prozesse mit dem 3CX-Profil beenden (z. B. Hintergrundmodus)."""
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
    """Ist ein sichtbares Edge-Fenster mit dem 3CX-Profil offen?"""
    procs = profile_processes(profile_dir)
    if sys.platform != "win32":
        # Hauptprozess (ohne --type=…) ohne --headless = sichtbares Fenster
        return any("--headless" not in cmd and "--type=" not in cmd and "-32000" not in cmd
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

    def call(self, method, **params):
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


class PbxReader(QObject):
    # Signale werden aus dem Hintergrund-Thread gesendet (Qt stellt sie zu)
    status_changed = pyqtSignal(str)
    calls_added = pyqtSignal(int)
    login_required = pyqtSignal()

    READ_INTERVAL = 60       # Sekunden zwischen zwei Lesevorgängen
    RELOAD_INTERVAL = 15 * 60

    def __init__(self, base_url, calls_file, profile_dir, userscript_text, parent=None):
        super().__init__(parent)
        self.base_url = base_url.strip().rstrip("/")
        self.calls_file = calls_file
        self.profile_dir = profile_dir
        self.js = build_reader_js(userscript_text)
        self.needs_login = False
        self.last_read = None
        self.last_count = 0
        self.status = "Startet …"

        self._proc = None
        self._tools = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._login_open = False
        self._thread = None
        # Nur ein Edge darf das Profil benutzen: Lesen und Anmelden wechseln sich ab
        self._browser_lock = threading.Lock()

    def call_list_url(self):
        return f"{self.base_url}/#/call_history/all"

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
        self._set_status("3CX: Anmeldung im Edge-Fenster …")
        threading.Thread(target=self._login_window, daemon=True).start()

    # ------------------------------------------------------------ Browser

    def _browser_args(self, mode):
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
        ]
        args += shlex.split(os.environ.get("ZEITZEUGE_BROWSER_ARGS", ""))
        if mode == "login":
            return args + [f"--app={self.call_list_url()}", "--window-size=1100,800"]
        args += ["--remote-debugging-port=0", "--remote-allow-origins=*", "--window-size=1100,2400"]
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
            raise RuntimeError("ein Edge-Fenster mit dem 3CX-Profil ist noch offen")
        mode = getattr(self, "_mode", "headless")
        try:
            port = self._launch(mode)
        except RuntimeError as e:
            if mode != "headless":
                raise
            # Unsichtbarer Modus klappt nicht (z. B. per Richtlinie gesperrt): Ersatzmodus
            self._set_status(f"3CX: unsichtbarer Modus geht nicht ({e}), nehme Ersatz")
            kill_profile_processes(self.profile_dir)
            self._mode = "hidden"
            port = self._launch("hidden")

        pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10))
        page = next(p for p in pages if p.get("type") == "page")
        self._tools = _DevTools(page["webSocketDebuggerUrl"])

        # Kein "HeadlessChrome" in der Kennung, sonst verhalten sich manche Seiten anders
        version = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=10))
        agent = version.get("User-Agent", "").replace("HeadlessChrome", "Chrome")
        if agent:
            self._tools.call("Network.setUserAgentOverride", userAgent=agent)
        self._tools.call("Page.navigate", url=self.call_list_url())

    def _launch(self, mode):
        """Edge starten und warten, bis er seine DevTools-Schnittstelle meldet. Gibt den Port zurück."""
        port_file = os.path.join(self.profile_dir, "DevToolsActivePort")
        if os.path.exists(port_file):
            os.remove(port_file)
        self._proc = self._popen(self._browser_args(mode))

        # Edge schreibt seinen Port in DevToolsActivePort. Er gibt beim Start oft an einen
        # anderen Prozess ab, darum zählt die Datei, nicht der gestartete Prozess.
        deadline = time.time() + 20
        while time.time() < deadline:
            if os.path.exists(port_file):
                with open(port_file, encoding="utf-8") as f:
                    first = f.readline().strip()
                if first.isdigit():
                    return int(first)
            code = self._proc.poll()
            if code is not None and not profile_processes(self.profile_dir):
                raise RuntimeError(f"Edge hat sich beendet, Code {code}")
            time.sleep(0.2)
        code = self._proc.poll()
        kill_profile_processes(self.profile_dir)
        raise RuntimeError("Edge antwortet nicht" + (f", Code {code}" if code is not None else ""))

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
        if self._proc:
            kill_profile_processes(self.profile_dir)  # falls Edge an einen anderen Prozess abgab
        self._proc = None

    def _login_window(self):
        self._wake.set()  # Lese-Schleife aus dem Warten holen
        with self._browser_lock:
            try:
                self._close_browser()  # unsichtbaren Edge beenden, Profil freigeben
                kill_profile_processes(self.profile_dir)  # Reste, an die Edge sonst weiterleitet
                self._wait_profile_free(15)
                self._popen(self._browser_args("login"))
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
                self._set_status("3CX: Anmeldefenster geschlossen, lese …")
            except Exception as e:
                self._set_status(f"3CX: {e}")
            finally:
                self._login_open = False
                self.needs_login = False
        self._wake.set()

    # ------------------------------------------------------------ Lesen

    def _set_status(self, text):
        self.status = text
        self.status_changed.emit(text)

    def _loop(self):
        last_load = 0
        while not self._stop.is_set():
            if not self._login_open:
                with self._browser_lock:
                    last_load = self._step(last_load)
            self._wake.wait(self.READ_INTERVAL)
            self._wake.clear()
        self._close_browser()

    def _step(self, last_load):
        """Ein Durchlauf: Browser bei Bedarf starten, ggf. neu laden, Liste lesen."""
        if self._login_open or self._stop.is_set():
            return last_load
        try:
            if not self._tools:
                self._start_browser()
                last_load = time.time()
                self._set_status("3CX: Seite lädt …")
                time.sleep(10)  # Seite laden lassen
            elif time.time() - last_load > self.RELOAD_INTERVAL:
                self._tools.call("Page.navigate", url=self.call_list_url())
                last_load = time.time()
                time.sleep(10)
            self._read_once()
        except Exception as e:
            self._set_status(f"3CX: Fehler ({e}), neuer Versuch")
            self._close_browser()
        return last_load

    def _read_once(self):
        result = self._tools.call("Runtime.evaluate", expression=self.js, returnByValue=True)
        raw = result.get("result", {}).get("value")
        self._on_result(raw)

    def _on_result(self, raw):
        try:
            data = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            data = None
        if not data:
            self._set_status("3CX: Seite lädt noch")
            return

        if data["login"]:
            if not self.needs_login:
                self.needs_login = True
                self.login_required.emit()
            self._set_status("3CX: Anmeldung nötig")
            return
        self.needs_login = False

        calls = data["calls"]
        if not calls:
            if "call_history" not in data["url"] and self._tools:
                self._tools.call("Page.navigate", url=self.call_list_url())
            self._set_status("3CX: noch keine Anrufe gelesen")
            return

        added = merge_calls(self.calls_file, calls)
        self.last_read = datetime.now()
        self.last_count = len(calls)
        self._set_status(f"3CX gelesen {self.last_read:%H:%M} ({len(calls)} Anrufe)")
        if added:
            self.calls_added.emit(added)
