"""
Ist ein Server erreichbar? Und wann versuchen wir es nach Fehlern wieder?

- reachable(url): kurzer TCP-Verbindungsaufbau zu Host und Port der Adresse (bzw. zum
  eingestellten Proxy). So startet Zeitzeuge ohne Internet keinen Edge umsonst.
  ZEITZEUGE_OFFLINE=1 tut so, als wäre nichts erreichbar (für Tests).
- Backoff: Wartezeit nach Fehlern in Folge, 20 s, 40 s, 80 s … höchstens 10 Minuten.
"""

import os
import socket
import sys
import urllib.request
from urllib.parse import urlsplit

PORTS = {"https": 443, "http": 80, "wss": 443, "ws": 80}


def _target(url):
    """(Host, Port), zu dem eine Verbindung zu url tatsächlich aufgebaut wird."""
    parts = urlsplit(url if "://" in url else f"https://{url}")
    scheme = parts.scheme or "https"
    host = parts.hostname or ""
    port = parts.port or PORTS.get(scheme, 443)
    # Mit Proxy (Umgebung oder Windows-Einstellung) zählt, ob der Proxy erreichbar ist
    try:
        proxy = urllib.request.getproxies().get(scheme)
        if proxy and host and not urllib.request.proxy_bypass(host):
            p = urlsplit(proxy if "://" in proxy else f"http://{proxy}")
            if p.hostname:
                return p.hostname, p.port or 8080
    except Exception:  # Proxy-Einstellung unlesbar: direkt prüfen
        pass
    return host, port


_pac = None


def _auto_proxy():
    """Windows: Proxy per Skript (PAC) oder automatischer Suche eingestellt? Dann lässt sich
    nicht direkt prüfen, ob ein Server erreichbar ist (Edge fragt das Skript)."""
    global _pac
    if _pac is None:
        _pac = False
        if sys.platform == "win32":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows"
                                    r"\CurrentVersion\Internet Settings") as key:
                    _pac = bool(winreg.QueryValueEx(key, "AutoConfigURL")[0])
            except OSError:
                pass
    return _pac


def reachable(url, timeout=3):
    """True, wenn sich zu Host:Port von url eine Verbindung aufbauen lässt."""
    if os.environ.get("ZEITZEUGE_OFFLINE") == "1":
        return False
    host, port = _target(url)
    if not host:
        return False
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except (OSError, ValueError):
        # Hinter einem Proxy-Skript ist "nicht erreichbar" nicht sicher: lieber versuchen
        return _auto_proxy()


class Backoff:
    """Wartezeit nach Fehlern in Folge: verdoppelt sich bis MAX, reset() nach Erfolg."""

    START = 20
    MAX = 10 * 60

    def __init__(self):
        self.failures = 0

    def fail(self):
        self.failures += 1
        return self.delay()

    def reset(self):
        self.failures = 0

    def delay(self):
        if not self.failures:
            return 0
        return min(self.MAX, self.START * 2 ** min(self.failures - 1, 16))
