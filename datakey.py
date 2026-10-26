"""
Schlüssel für die verschlüsselte Datenbank (ohne Qt).

- Ein zufälliger Datenschlüssel (256 Bit) verschlüsselt alle Inhalte mit AES-256-GCM.
- Der Datenschlüssel liegt nie offen auf der Platte, nur verpackt in Schlüsselfächern:
  * "dpapi": mit der Windows-Anmeldung verpackt (CryptProtectData, CurrentUser).
    Start ohne Abfrage, nur dieser Windows-Benutzer kann es öffnen.
  * "wiederherstellung": mit dem Wiederherstellungsschlüssel verpackt (48 Ziffern in
    8 Blöcken wie bei BitLocker). Öffnet die Daten auf einem neuen PC oder Konto.
  * "datei": nur außerhalb von Windows (Entwicklung, Tests, CI). Schlüsseldatei im
    lokalen Ordner, schützt nicht vor Mitlesern.
- Derselbe Ziffernblock-Typ dient als Übertragungsschlüssel für den PAW-Export.

Jeder Block der Ziffernschlüssel ist durch 11 teilbar (wie bei BitLocker). So lässt sich
ein Tippfehler dem Block zuordnen, bevor überhaupt entschlüsselt wird. 8 Blöcke tragen
zusammen gut 131 Bit Zufall.
"""

import os
import secrets
import sys
import zlib

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

KEY_BYTES = 32
NONCE_BYTES = 12
BLOCKS = 8
DPAPI_ENTROPY = b"Zeitzeuge-Datenschluessel-1"
# scrypt für Ziffernschlüssel: ~50 ms, bremst Durchprobieren zusätzlich zu den 131 Bit
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1

# Erstes Byte jedes verschlüsselten Inhalts: Format
_PLAIN, _ZLIB = 1, 2
_COMPRESS_FROM = 512  # kleinere Inhalte nicht packen


class WrongKey(ValueError):
    """Schlüssel passt nicht oder Inhalt ist beschädigt."""


class BadCode(ValueError):
    """Ziffernschlüssel falsch eingegeben (Länge oder Prüfziffer eines Blocks)."""


# ------------------------------------------------------------ Datenverschlüsselung

def new_key():
    return secrets.token_bytes(KEY_BYTES)


class Cipher:
    """AES-256-GCM mit einem Datenschlüssel. aad bindet den Inhalt an seinen Platz
    (Ablage und Tag): vertauschte Zeilen fallen beim Entschlüsseln auf."""

    def __init__(self, key):
        if len(key) != KEY_BYTES:
            raise ValueError("Datenschlüssel muss 32 Byte lang sein")
        self._aead = AESGCM(key)

    def encrypt(self, data: bytes, aad: bytes = b"") -> bytes:
        if len(data) >= _COMPRESS_FROM:
            body, fmt = zlib.compress(data, 6), _ZLIB
        else:
            body, fmt = data, _PLAIN
        nonce = secrets.token_bytes(NONCE_BYTES)
        return bytes([fmt]) + nonce + self._aead.encrypt(nonce, body, bytes([fmt]) + aad)

    def decrypt(self, blob: bytes, aad: bytes = b"") -> bytes:
        try:
            fmt, nonce, body = blob[0], blob[1:1 + NONCE_BYTES], blob[1 + NONCE_BYTES:]
            data = self._aead.decrypt(nonce, body, bytes([fmt]) + aad)
            return zlib.decompress(data) if fmt == _ZLIB else data
        except (InvalidTag, IndexError, zlib.error) as e:
            raise WrongKey("Inhalt lässt sich nicht entschlüsseln") from e


# ------------------------------------------------------------ Ziffernschlüssel

def new_code():
    """Neuer Ziffernschlüssel: 8 Blöcke à 6 Ziffern, jeder durch 11 teilbar."""
    return "-".join(f"{secrets.randbelow(1_000_000 // 11) * 11:06d}" for _ in range(BLOCKS))


def normalize_code(text):
    """Eingabe prüfen und vereinheitlichen. Leerzeichen, Bindestriche, Zeilenumbrüche egal.
    BadCode mit verständlichem Text, wenn etwas nicht stimmt."""
    digits = "".join(ch for ch in (text or "") if ch.isdigit())
    other = [ch for ch in (text or "") if not (ch.isdigit() or ch in " -\t\r\n")]
    if other:
        raise BadCode("Der Schlüssel besteht nur aus Ziffern und Bindestrichen.")
    if len(digits) != BLOCKS * 6:
        raise BadCode(f"Der Schlüssel hat {BLOCKS * 6} Ziffern ({BLOCKS} Blöcke à 6), "
                      f"eingegeben sind {len(digits)}.")
    blocks = [digits[i:i + 6] for i in range(0, len(digits), 6)]
    for n, block in enumerate(blocks, 1):
        if int(block) % 11:
            raise BadCode(f"Block {n} ({block}) ist falsch. Bitte noch einmal genau abschreiben.")
    return "-".join(blocks)


def _code_kek(code, salt):
    digits = normalize_code(code).replace("-", "").encode("ascii")
    return Scrypt(salt=salt, length=KEY_BYTES, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(digits)


def wrap_with_code(key, code, purpose=b"slot"):
    """Datenschlüssel mit einem Ziffernschlüssel verpacken -> bytes (Salz, Nonce, Chiffrat)."""
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(NONCE_BYTES)
    return salt + nonce + AESGCM(_code_kek(code, salt)).encrypt(nonce, key, b"zeitzeuge-" + purpose)


def unwrap_with_code(blob, code, purpose=b"slot"):
    salt, nonce, body = blob[:16], blob[16:16 + NONCE_BYTES], blob[16 + NONCE_BYTES:]
    try:
        return AESGCM(_code_kek(code, salt)).decrypt(nonce, body, b"zeitzeuge-" + purpose)
    except InvalidTag as e:
        raise WrongKey("Der Schlüssel passt nicht zu diesen Daten.") from e


# ------------------------------------------------------------ Windows-Anmeldung (DPAPI)

def dpapi_available():
    return sys.platform == "win32"


def dpapi(data, encrypt, entropy=None):
    """CryptProtectData / CryptUnprotectData für den angemeldeten Windows-Benutzer."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(raw):
        buf = ctypes.create_string_buffer(raw, len(raw))
        return Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    blob_in, _keep_in = blob(data)
    entropy_blob, _keep_e = blob(entropy) if entropy else (None, None)
    blob_out = Blob()
    crypt = ctypes.windll.crypt32
    func = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    ok = func(ctypes.byref(blob_in), None, ctypes.byref(entropy_blob) if entropy_blob else None,
              None, None, 0x01, ctypes.byref(blob_out))  # CRYPTPROTECT_UI_FORBIDDEN
    if not ok:
        raise OSError("DPAPI fehlgeschlagen")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


# ------------------------------------------------------------ Ersatz außerhalb von Windows

def _file_key_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "Zeitzeuge", "schluessel_ohne_windows.bin")


def _file_key():
    path = _file_key_path()
    try:
        with open(path, "rb") as f:
            key = f.read()
        if len(key) == KEY_BYTES:
            return key
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    key = new_key()
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as f:
        f.write(key)
    os.chmod(tmp, 0o600)
    try:
        os.link(tmp, path)  # nur anlegen, wenn es sie noch nicht gibt (zwei Prozesse gleichzeitig)
    except FileExistsError:
        pass
    except OSError:
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    with open(path, "rb") as f:
        return f.read()


def auto_kind():
    """Fach, das ohne Abfrage öffnet: DPAPI unter Windows, sonst Schlüsseldatei."""
    return "dpapi" if dpapi_available() else "datei"


def auto_wrap(key):
    if dpapi_available():
        return dpapi(key, True, DPAPI_ENTROPY)
    nonce = secrets.token_bytes(NONCE_BYTES)
    return nonce + AESGCM(_file_key()).encrypt(nonce, key, b"zeitzeuge-datei")


def auto_unwrap(kind, blob):
    """Fach ohne Abfrage öffnen. WrongKey, wenn es nicht zu diesem Benutzer/PC gehört."""
    try:
        if kind == "dpapi" and dpapi_available():
            return dpapi(blob, False, DPAPI_ENTROPY)
        if kind == "datei" and not dpapi_available():
            nonce, body = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
            return AESGCM(_file_key()).decrypt(nonce, body, b"zeitzeuge-datei")
    except (OSError, InvalidTag) as e:
        raise WrongKey("Fach gehört zu einem anderen Benutzer oder PC") from e
    raise WrongKey("Fach passt nicht zu diesem System")
