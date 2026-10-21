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
        self._close_browser()  # Profil darf nur von einem Edge benutzt werden
        self._set_status("3CX: Anmeldung im Edge-Fenster …")
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
            args += [f"--app={self.call_list_url()}", "--window-size=1100,800"]
        return args

    def _popen(self, args):
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        return subprocess.Popen(args, creationflags=flags,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _start_browser(self):
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
        self._tools.call("Page.navigate", url=self.call_list_url())

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
        try:
            proc = self._popen(self._browser_args(headless=False))
            proc.wait()  # bis du das Fenster schließt
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
                try:
                    if not self._tools:
                        self._start_browser()
                        last_load = time.time()
                        self._set_status("3CX: Seite lädt …")
                        self._wake.wait(10)  # Seite laden lassen
                        self._wake.clear()
                    elif time.time() - last_load > self.RELOAD_INTERVAL:
                        self._tools.call("Page.navigate", url=self.call_list_url())
                        last_load = time.time()
                        self._wake.wait(10)
                        self._wake.clear()
                    if not self._login_open and not self._stop.is_set():
                        self._read_once()
                except Exception as e:
                    if not self._login_open:  # beim Anmelden wird Edge absichtlich beendet
                        self._set_status(f"3CX: Fehler ({e}), neuer Versuch")
                    self._close_browser()
            self._wake.wait(self.READ_INTERVAL)
            self._wake.clear()
        self._close_browser()

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
