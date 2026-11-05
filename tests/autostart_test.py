"""Mit Windows starten: Eintrag unter HKCU\\...\\Run setzen, entfernen, nach Umzug nachziehen."""
import sys
import types

import autostart


def _fake_registry(monkeypatch):
    values = {}

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def query(_key, name):
        if name not in values:
            raise FileNotFoundError(name)
        return values[name], 1

    def delete(_key, name):
        if name not in values:
            raise FileNotFoundError(name)
        del values[name]

    winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER=0, KEY_SET_VALUE=2, REG_SZ=1,
        OpenKey=lambda *a: Key(), QueryValueEx=query, DeleteValue=delete,
        SetValueEx=lambda _k, name, _r, _t, value: values.__setitem__(name, value))
    monkeypatch.setitem(sys.modules, "winreg", winreg)
    monkeypatch.setattr(sys, "platform", "win32")
    return values


def test_ein_aus_und_nachziehen(monkeypatch):
    values = _fake_registry(monkeypatch)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Tools\ZeitZeuge.exe")
    assert not autostart.is_enabled()
    autostart.refresh()  # nicht eingetragen: refresh legt nichts an
    assert not values
    assert autostart.set_enabled(True)
    assert values["Zeitzeuge"] == r'"C:\Tools\ZeitZeuge.exe" --minimized'
    # EXE umgezogen: beim Start zeigt der Eintrag auf die neue
    monkeypatch.setattr(sys, "executable", r"C:\Neu\ZeitZeuge.exe")
    autostart.refresh()
    assert values["Zeitzeuge"] == r'"C:\Neu\ZeitZeuge.exe" --minimized'
    assert autostart.set_enabled(False) and not autostart.is_enabled()
    assert autostart.set_enabled(False)  # schon weg: kein Fehler


def test_ohne_windows_nichts():
    if sys.platform == "win32":
        return
    assert not autostart.supported() and not autostart.is_enabled()
    assert autostart.set_enabled(True) is False
