# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller ZeitZeuge.spec  ->  dist/ZeitZeuge.exe
import os
import sys

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct,
                                                 StringTable, VarFileInfo, VarStruct,
                                                 VSVersionInfo)

import datetime  # noqa: E402
import subprocess  # noqa: E402

sys.path.insert(0, os.path.abspath(SPECPATH))


def _build_info():
    """Herkunft des Builds: GitHub Actions (Tag = Release, sonst Testversion) oder lokal."""
    env = os.environ
    info = {"date": datetime.date.today().isoformat()}
    if env.get("GITHUB_ACTIONS") == "true":
        info["channel"] = "release" if env.get("GITHUB_REF_TYPE") == "tag" else "test"
        info["build"] = int(env.get("GITHUB_RUN_NUMBER", "0") or 0)
        info["commit"] = env.get("GITHUB_SHA", "")[:7]
        info["branch"] = env.get("GITHUB_HEAD_REF") or env.get("GITHUB_REF_NAME", "")
    else:
        info["channel"] = "local"
        try:
            info["commit"] = subprocess.run(["git", "-C", SPECPATH, "rev-parse", "--short", "HEAD"],
                                            capture_output=True, text=True, timeout=5).stdout.strip()
        except OSError:
            pass
    return info


# build_info.py wird mit in die EXE gepackt (version.py liest es) und danach wieder gelöscht
BUILD_INFO_FILE = os.path.join(SPECPATH, "build_info.py")
BUILD = _build_info()
with open(BUILD_INFO_FILE, "w", encoding="utf-8") as f:
    f.write("# Beim Bauen erzeugt (ZeitZeuge.spec), nicht von Hand ändern\n")
    f.write(f"BUILD = {BUILD!r}\n")

import version  # noqa: E402
from version import VERSION, file_version, version_details  # noqa: E402

version._INFO = BUILD  # Angaben dieses Builds, nicht die aus git

nums = file_version()
print(f"Zeitzeuge {version_details()}")

# Versionsangaben in der EXE (Eigenschaften → Details). Virenscanner stufen
# EXE-Dateien ohne diese Angaben eher als verdächtig ein.
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=nums, prodvers=nums),
    kids=[
        StringFileInfo([StringTable("040704B0", [
            StringStruct("CompanyName", "Zeitzeuge"),
            StringStruct("FileDescription", "Zeitzeuge – Tages-Timeline der Arbeitsspuren"),
            StringStruct("FileVersion", ".".join(map(str, nums))),
            StringStruct("InternalName", "ZeitZeuge"),
            StringStruct("LegalCopyright", "siehe LICENSE"),
            StringStruct("OriginalFilename", "ZeitZeuge.exe"),
            StringStruct("ProductName", "Zeitzeuge"),
            StringStruct("ProductVersion", VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0407, 1200])]),
    ],
)

a = Analysis(
    ['main_timeline.py'],
    pathex=[],
    binaries=[],
    datas=[('zeitzeuge.png', '.'), ('zeitzeuge.ico', '.'), ('zeitzeuge.svg', '.'),
           ('zeitzeuge_anrufe.user.js', '.')],
    hiddenimports=['build_info'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)

# Zwei Varianten:
# - Standard: eine einzelne ZeitZeuge.exe. Sie entpackt sich bei jedem Start nach %TEMP%.
# - ZEITZEUGE_ONEDIR=1: Ordner mit ZeitZeuge.exe und _internal (nichts wird entpackt).
#   Für Rechner mit EDR/Virenscanner wie Cortex XDR (z. B. PAW): Programme, die beim Start
#   DLLs nach %TEMP% schreiben und laden, gelten dort schnell als verdächtig.
ONEDIR = os.environ.get("ZEITZEUGE_ONEDIR") == "1"

options = dict(
    name='ZeitZeuge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['zeitzeuge.ico'],
    version=version_info,
)
# Kein UPX (upx=False oben): mit UPX gepackte EXE-Dateien melden Virenscanner besonders oft fälschlich.

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **options)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ZeitZeuge-Ordner')
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **options)

os.remove(BUILD_INFO_FILE)  # sonst zeigte der Start aus dem Quelltext die Angaben dieses Builds
