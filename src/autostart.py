"""Mit Windows starten: Eintrag unter HKCU\\...\\Run (nur dieser Benutzer, ohne Adminrechte).

Zeitzeuge startet dann mit --minimized direkt im Infobereich. Der Eintrag zeigt auf die
EXE, von der aus er gesetzt wurde; zieht die EXE um, zieht refresh() ihn beim Start nach.
"""
import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Zeitzeuge"


def supported():
    return sys.platform == "win32"


def command():
    """Befehlszeile für den Autostart: EXE, im Quelltext pythonw mit main_timeline.py."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    exe = sys.executable
    windowed = os.path.join(os.path.dirname(exe), "pythonw.exe")
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main_timeline.py")
    return f'"{windowed if os.path.exists(windowed) else exe}" "{script}" --minimized'


def current():
    """Eingetragene Befehlszeile oder "" (nicht eingetragen, kein Windows)."""
    if not supported():
        return ""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return str(winreg.QueryValueEx(key, NAME)[0])
    except OSError:
        return ""


def is_enabled():
    return bool(current())


def set_enabled(on):
    """Eintragen oder entfernen. False, wenn es nicht ging (kein Windows, Richtlinie)."""
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def refresh():
    """Beim Start: Eintrag auf die laufende EXE nachziehen (z. B. nach Umzug oder Update)."""
    if is_enabled() and current() != command():
        set_enabled(True)
