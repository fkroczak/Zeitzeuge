"""
Windows Hello für das Schlüsselfach „Windows-Anmeldung + Windows Hello“ (ohne Qt).

Zeitzeuge legt im Windows-Hello-Schlüsselspeicher („Microsoft Passport Key Storage Provider“)
einen eigenen RSA-Schlüssel an. Der private Teil liegt im TPM dieses PCs und verlässt ihn nie;
jede Nutzung verlangt Gesicht, Fingerabdruck oder die Windows-Hello-PIN.

- Verpacken braucht nur den öffentlichen Schlüssel (keine Abfrage).
- Entpacken (NCryptDecrypt) zeigt den Windows-Hello-Dialog vor dem Zeitzeuge-Fenster.

Wie KeePassWinHello: NCrypt direkt über ctypes, keine zusätzlichen Pakete. Gilt nur für
diesen PC: Neues Gerät, TPM gelöscht oder Hello neu eingerichtet -> Wiederherstellungsschlüssel.
"""

import sys

PROVIDER = "Microsoft Passport Key Storage Provider"
KEY_DOMAIN, KEY_SUBDOMAIN, KEY_NAME = "Zeitzeuge", "", "Datenschluessel"
USE_CONTEXT = "Zeitzeuge entsperren"

NCRYPT_OVERWRITE_KEY_FLAG = 0x80
NCRYPT_PAD_PKCS1_FLAG = 0x2
NCRYPT_ALLOW_DECRYPT_FLAG, NCRYPT_ALLOW_SIGNING_FLAG = 0x1, 0x2
NTE_BAD_KEYSET = 0x80090016
NTE_NO_KEY = 0x8009000D
NTE_NOT_FOUND = 0x80090011
NTE_USER_CANCELLED = 0x80090036
ERROR_CANCELLED = 0x800704C7
SCARD_W_CANCELLED_BY_USER = 0x8010006E
_CANCEL_CODES = {NTE_USER_CANCELLED, ERROR_CANCELLED, SCARD_W_CANCELLED_BY_USER}
SM_REMOTESESSION = 0x1000


class HelloError(OSError):
    """Windows Hello ging nicht (nicht eingerichtet, kein TPM, Fehler)."""


class HelloCancelled(HelloError):
    """Abfrage abgebrochen."""


class HelloMissing(HelloError):
    """Der Hello-Schlüssel von Zeitzeuge fehlt auf diesem PC (neues Gerät, Hello neu eingerichtet)."""


def available():
    """Windows mit Windows-Hello-Schlüsselspeicher. Ob Hello eingerichtet ist, zeigt erst create_key()."""
    if sys.platform != "win32":
        return False
    try:
        _close(_provider())
        return True
    except (HelloError, OSError, AttributeError):
        return False


def remote_session():
    """In einer RDP-Sitzung lässt sich Windows Hello meist nicht nutzen."""
    if sys.platform != "win32":
        return False
    import ctypes
    return bool(ctypes.windll.user32.GetSystemMetrics(SM_REMOTESESSION))


# ------------------------------------------------------------ ctypes

def _ncrypt():
    import ctypes
    from ctypes import wintypes
    lib = ctypes.windll.ncrypt
    handle, lpw, dword = ctypes.c_size_t, wintypes.LPCWSTR, wintypes.DWORD
    sigs = {
        "NCryptOpenStorageProvider": [ctypes.POINTER(handle), lpw, dword],
        "NCryptOpenKey": [handle, ctypes.POINTER(handle), lpw, dword, dword],
        "NCryptCreatePersistedKey": [handle, ctypes.POINTER(handle), lpw, lpw, dword, dword],
        "NCryptSetProperty": [handle, lpw, ctypes.c_void_p, dword, dword],
        "NCryptFinalizeKey": [handle, dword],
        "NCryptExportKey": [handle, handle, lpw, ctypes.c_void_p, ctypes.c_void_p, dword,
                            ctypes.POINTER(dword), dword],
        "NCryptDecrypt": [handle, ctypes.c_void_p, dword, ctypes.c_void_p, ctypes.c_void_p, dword,
                          ctypes.POINTER(dword), dword],
        "NCryptFreeObject": [handle],
    }
    for name, args in sigs.items():
        func = getattr(lib, name)
        func.argtypes, func.restype = args, ctypes.c_long
    return lib


def _check(status, what):
    code = status & 0xFFFFFFFF
    if code == 0:
        return
    if code in _CANCEL_CODES:
        raise HelloCancelled("Windows Hello wurde abgebrochen.")
    if code in (NTE_BAD_KEYSET, NTE_NO_KEY, NTE_NOT_FOUND):
        raise HelloMissing("Der Windows-Hello-Schlüssel von Zeitzeuge fehlt auf diesem PC.")
    raise HelloError(f"Windows Hello: {what} fehlgeschlagen (0x{code:08X}).")


def _provider():
    import ctypes
    prov = ctypes.c_size_t()
    _check(_ncrypt().NCryptOpenStorageProvider(ctypes.byref(prov), PROVIDER, 0), "Schlüsselspeicher öffnen")
    return prov


def _close(handle):
    if handle and handle.value:
        _ncrypt().NCryptFreeObject(handle)


def _user_sid():
    """SID des angemeldeten Benutzers als Text (S-1-5-21-…)."""
    import ctypes
    from ctypes import wintypes
    advapi, kernel = ctypes.windll.advapi32, ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
        raise HelloError("Windows-Benutzer nicht ermittelbar")
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # TokenUser
        buf = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buf, size, ctypes.byref(size)):
            raise HelloError("Windows-Benutzer nicht ermittelbar")
        sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]  # TOKEN_USER.User.Sid
        text = wintypes.LPWSTR()
        if not advapi.ConvertSidToStringSidW(ctypes.c_void_p(sid), ctypes.byref(text)):
            raise HelloError("Windows-Benutzer nicht ermittelbar")
        try:
            return text.value
        finally:
            kernel.LocalFree(text)
    finally:
        kernel.CloseHandle(token)


def _key_name():
    # Schema des Passport-Schlüsselspeichers: <SID>//<Domäne>/<Unterdomäne>/<Name>
    return f"{_user_sid()}//{KEY_DOMAIN}/{KEY_SUBDOMAIN}/{KEY_NAME}"


def _set(handle, name, value):
    import ctypes
    if isinstance(value, str):
        data = ctypes.create_unicode_buffer(value)
        size = ctypes.sizeof(data)
    elif name == "HWND Handle":
        data = ctypes.c_void_p(value)
        size = ctypes.sizeof(data)
    else:
        data = ctypes.c_uint32(value)
        size = 4
    return _ncrypt().NCryptSetProperty(handle, name, ctypes.byref(data), size, 0)


def _prepare(key, hwnd):
    """Hello-Dialog vor das Zeitzeuge-Fenster legen, Text dazu."""
    if hwnd:
        _set(key, "HWND Handle", int(hwnd))
    _set(key, "Use Context", USE_CONTEXT)


def _open_key(prov):
    import ctypes
    key = ctypes.c_size_t()
    _check(_ncrypt().NCryptOpenKey(prov, ctypes.byref(key), _key_name(), 0, 0), "Schlüssel öffnen")
    return key


def _export_public(key):
    import ctypes
    from ctypes import wintypes
    lib = _ncrypt()
    size = wintypes.DWORD()
    _check(lib.NCryptExportKey(key, 0, "RSAPUBLICBLOB", None, None, 0, ctypes.byref(size), 0),
           "öffentlichen Schlüssel lesen")
    buf = ctypes.create_string_buffer(size.value)
    _check(lib.NCryptExportKey(key, 0, "RSAPUBLICBLOB", None, buf, size, ctypes.byref(size), 0),
           "öffentlichen Schlüssel lesen")
    return public_from_blob(buf.raw[:size.value])


def public_from_blob(blob):
    """BCRYPT_RSAKEY_BLOB (Magic, Bits, cbExp, cbMod, cbP1, cbP2, Exponent, Modulus) -> RSA-Schlüssel."""
    import struct
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
    magic, _bits, cb_exp, cb_mod, _p1, _p2 = struct.unpack_from("<6I", blob)
    if magic != 0x31415352:  # "RSA1"
        raise HelloError("Unbekanntes Schlüsselformat von Windows Hello")
    exp = int.from_bytes(blob[24:24 + cb_exp], "big")
    mod = int.from_bytes(blob[24 + cb_exp:24 + cb_exp + cb_mod], "big")
    return RSAPublicNumbers(exp, mod).public_key()


# ------------------------------------------------------------ Schnittstelle

def public_key(hwnd=None):
    """Öffentlichen Teil des Zeitzeuge-Hello-Schlüssels holen. Fehlt er, anlegen: Dabei fragt
    Windows Hello nach Gesicht, Finger oder PIN. HelloError, wenn Hello nicht eingerichtet ist."""
    import ctypes
    lib = _ncrypt()
    prov = _provider()
    key = ctypes.c_size_t()
    try:
        try:
            key = _open_key(prov)
        except HelloMissing:
            key = ctypes.c_size_t()
            _check(lib.NCryptCreatePersistedKey(prov, ctypes.byref(key), "RSA", _key_name(), 0,
                                                NCRYPT_OVERWRITE_KEY_FLAG), "Schlüssel anlegen")
            _set(key, "Length", 2048)
            _set(key, "Key Usage", NCRYPT_ALLOW_DECRYPT_FLAG | NCRYPT_ALLOW_SIGNING_FLAG)
            # Jede Nutzung mit Geste, nicht aus dem Hello-Zwischenspeicher (älterer Name als Ersatz)
            if _set(key, "NgcCacheType", 1):
                _set(key, "NgcCacheTypeProperty", 1)
            _prepare(key, hwnd)
            _check(lib.NCryptFinalizeKey(key, 0), "Schlüssel anlegen")
        return _export_public(key)
    finally:
        _close(key)
        _close(prov)


def decrypt(data, hwnd=None):
    """Mit dem Hello-Schlüssel entschlüsseln. Zeigt den Windows-Hello-Dialog.
    HelloCancelled bei Abbruch, HelloMissing ohne Schlüssel, sonst HelloError."""
    import ctypes
    from ctypes import wintypes
    lib = _ncrypt()
    prov = _provider()
    key = ctypes.c_size_t()
    try:
        key = _open_key(prov)
        _prepare(key, hwnd)
        _set(key, "PinCacheIsGestureRequired", 1)
        src = ctypes.create_string_buffer(bytes(data), len(data))
        out = ctypes.create_string_buffer(1024)
        size = wintypes.DWORD()
        _check(lib.NCryptDecrypt(key, src, len(data), None, out, len(out), ctypes.byref(size),
                                 NCRYPT_PAD_PKCS1_FLAG), "Entsperren")
        return out.raw[:size.value]
    finally:
        _close(key)
        _close(prov)
