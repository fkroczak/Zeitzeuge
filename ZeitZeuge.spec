# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller ZeitZeuge.spec  ->  dist/ZeitZeuge.exe
import os
import sys

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct,
                                                 StringTable, VarFileInfo, VarStruct,
                                                 VSVersionInfo)

sys.path.insert(0, os.path.abspath(SPECPATH))
from version import VERSION  # noqa: E402

nums = tuple(int(n) for n in (VERSION.split(".") + ["0"] * 4)[:4])

# Versionsangaben in der EXE (Eigenschaften → Details). Virenscanner stufen
# EXE-Dateien ohne diese Angaben eher als verdächtig ein.
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=nums, prodvers=nums),
    kids=[
        StringFileInfo([StringTable("040704B0", [
            StringStruct("CompanyName", "Zeitzeuge"),
            StringStruct("FileDescription", "Zeitzeuge – Tages-Timeline der Arbeitsspuren"),
            StringStruct("FileVersion", VERSION),
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
    hiddenimports=[],
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
