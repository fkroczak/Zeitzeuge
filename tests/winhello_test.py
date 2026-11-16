"""Windows Hello beim Start (datakey/datastore, winhello.py). Außerhalb von Windows gibt es kein
Hello: Ein Ersatz mit einem RSA-Schlüssel im Speicher spielt den TPM-Schlüssel."""
import os
import struct
import sys
import tempfile

import pytest
from cryptography.hazmat.primitives.asymmetric import padding, rsa

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import datakey  # noqa: E402
import datastore  # noqa: E402
import winhello  # noqa: E402

D = "2026-10-20"
SECRET = "Müller Kundenname GmbH"
PIN = "Grüne Wiese 42"


class FakeHello:
    """Wie winhello: public_key legt den Schlüssel bei Bedarf an, decrypt „fragt“ nach Hello."""

    def __init__(self):
        self.private = None
        self.asked = 0
        self.cancel = False
        self.hwnds = []

    def available(self):
        return True

    def public_key(self, hwnd=None):
        if self.private is None:
            self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return self.private.public_key()

    def decrypt(self, data, hwnd=None):
        self.asked += 1
        self.hwnds.append(hwnd)
        if self.cancel:
            raise winhello.HelloCancelled("abgebrochen")
        if self.private is None:
            raise winhello.HelloMissing("fehlt")
        return self.private.decrypt(data, padding.PKCS1v15())


@pytest.fixture
def hello(monkeypatch):
    fake = FakeHello()
    monkeypatch.setattr(datakey, "hello_backend", fake)
    return fake


def new_store():
    folder = tempfile.mkdtemp()
    return datastore.Store(os.path.join(folder, "zeitzeuge.db"), folder).unlock()


def kinds(store):
    return sorted(k for k, _l, _c in store.protection()["auto"])


def test_hello_noetig_auch_mit_windows_anmeldung(hello):
    store = new_store()
    store.put("anrufe", D, [{"name": SECRET}])
    with pytest.raises(ValueError, match="Wiederherstellungsschlüssel"):
        store.enable_hello()
    code = store.new_recovery_code()
    store.enable_hello(hwnd=4711)
    assert hello.asked == 1 and hello.hwnds == [4711], "einmal zur Probe gefragt, vor dem Fenster"
    assert kinds(store) == [datakey.hello_kind()], "kein Fach ohne Abfrage mehr übrig"
    assert store.hello_required() and store.has_own_hello() and not store.pin_required()
    store.close()

    s = datastore.Store(store.path)
    with pytest.raises(datastore.NeedPin):
        s.unlock()  # Windows-Anmeldung allein reicht nicht
    hello.cancel = True
    with pytest.raises(winhello.HelloCancelled):
        s.unlock_with_hello()
    assert not s.unlocked
    hello.cancel = False
    assert s.unlock_with_hello().get("anrufe", D)[0]["name"] == SECRET
    s.close()

    # Hello zurückgesetzt (neuer TPM-Schlüssel): Fach passt nicht mehr, Wiederherstellung geht
    hello.private = None
    s = datastore.Store(store.path)
    with pytest.raises(winhello.HelloMissing):
        s.unlock_with_hello()
    hello.public_key()
    with pytest.raises(datakey.WrongKey):
        s.unlock_with_hello()
    s.unlock_with_code(code)
    assert kinds(s) == [datakey.hello_kind()], "mit Hello legt der Wiederherstellungsschlüssel kein offenes Fach an"
    s.enable_hello()  # neu einrichten ersetzt das eigene Fach
    assert kinds(s) == [datakey.hello_kind()]
    s.close()
    assert datastore.Store(store.path).unlock_with_hello().unlocked


def test_hello_und_pin_zusammen(hello):
    store = new_store()
    store.put("anrufe", D, [{"name": SECRET}])
    store.new_recovery_code()
    store.enable_pin(PIN)
    store.enable_hello()
    assert kinds(store) == sorted([datakey.pin_kind(), datakey.hello_kind()])
    store.close()
    assert datastore.Store(store.path).unlock_with_pin(PIN).unlocked, "PIN als Ausweg (z. B. RDP)"
    assert datastore.Store(store.path).unlock_with_hello().unlocked

    s = datastore.Store(store.path).unlock_with_pin(PIN)
    s.disable_pin()
    assert kinds(s) == [datakey.hello_kind()], "ohne PIN bleibt Hello, kein offenes Fach"
    s.enable_pin(PIN)
    assert kinds(s) == sorted([datakey.pin_kind(), datakey.hello_kind()]), "PIN löscht Hello nicht"
    s.disable_hello()
    assert kinds(s) == [datakey.pin_kind()] and not s.hello_required()
    s.disable_pin()
    assert kinds(s) == [datakey.auto_kind()]
    s.close()
    assert datastore.Store(store.path).unlock().get("anrufe", D)[0]["name"] == SECRET, "wieder ohne Abfrage"


def test_hello_anderes_konto(hello, monkeypatch):
    store = new_store()
    code = store.new_recovery_code()
    store.enable_hello()
    store.close()
    monkeypatch.setattr(datakey, "auto_unwrap",
                        lambda k, b: (_ for _ in ()).throw(datakey.WrongKey("anderes Konto")))
    s = datastore.Store(store.path)
    assert not s.has_own_hello()
    with pytest.raises(datastore.Locked) as info:
        s.unlock_with_hello()
    assert not isinstance(info.value, datastore.NeedPin) and "Windows Hello" in str(info.value)
    assert s.unlock_with_code(code).unlocked


def test_hello_probe_schlaegt_fehl(hello):
    """Liefert Hello beim Einschalten nicht den richtigen Schlüssel, bleibt alles wie es war."""
    store = new_store()
    store.new_recovery_code()
    hello.cancel = True
    with pytest.raises(winhello.HelloCancelled):
        store.enable_hello()
    assert kinds(store) == [datakey.auto_kind()] and not store.hello_required()


def test_rsa_blob_lesen():
    """BCRYPT_RSAPUBLIC_BLOB aus NCryptExportKey -> öffentlicher Schlüssel."""
    pub = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    nums = pub.public_numbers()
    exp, mod = nums.e.to_bytes(3, "big"), nums.n.to_bytes(256, "big")
    blob = struct.pack("<6I", 0x31415352, 2048, len(exp), len(mod), 0, 0) + exp + mod
    assert winhello.public_from_blob(blob).public_numbers() == nums
    with pytest.raises(winhello.HelloError):
        winhello.public_from_blob(struct.pack("<6I", 0x32415352, 2048, 3, 256, 0, 0) + exp + mod)


def test_ohne_windows_kein_hello():
    if sys.platform != "win32":
        assert not winhello.available() and not winhello.remote_session()


# ---------------------------------------------------------------- Start (protect_dialogs.ask_unlock)

@pytest.fixture
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def locked_hello_store():
    store = new_store()
    store.put("anrufe", D, [{"name": SECRET}])
    store.new_recovery_code()
    store.enable_hello()
    store.close()
    return datastore.Store(store.path)


def test_start_mit_hello(hello, qapp):
    import protect_dialogs
    s = locked_hello_store()
    hello.asked = 0
    assert protect_dialogs.ask_unlock(s) and s.unlocked and hello.asked == 1


def test_start_in_rdp_ohne_hello_abfrage(hello, qapp, monkeypatch):
    import protect_dialogs
    s = locked_hello_store()
    hello.asked = 0
    monkeypatch.setattr(winhello, "remote_session", lambda: True)
    shown = []
    monkeypatch.setattr(protect_dialogs.EnterCodeDialog, "exec",
                        lambda self: shown.append(self.windowTitle()) or 0)  # Abbrechen
    assert protect_dialogs.ask_unlock(s) is False and not s.unlocked
    assert hello.asked == 0 and shown == ["Daten sind gesperrt"]


def test_start_hello_abgebrochen_dann_beenden(hello, qapp, monkeypatch):
    import protect_dialogs
    s = locked_hello_store()
    hello.cancel = True
    monkeypatch.setattr(protect_dialogs.QMessageBox, "exec", lambda self: 0)  # kein Knopf -> beenden
    assert protect_dialogs.ask_unlock(s) is False and not s.unlocked
