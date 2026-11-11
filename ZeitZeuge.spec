# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller ZeitZeuge.spec  ->  dist/ZeitZeuge.exe
# Quellcode liegt in src/, Bilder und das 3CX-Skript in assets/.
import os
import sys

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct,
                                                 StringTable, VarFileInfo, VarStruct,
                                                 VSVersionInfo)

SRC = os.path.join(os.path.abspath(SPECPATH), "src")
ASSETS = os.path.join(os.path.abspath(SPECPATH), "assets")
sys.path.insert(0, SRC)

import version  # noqa: E402

# Herkunft des Builds (Version z. B. 4.1.3, Buildnummer, Commit, Datum) und Update-Zugang. build_info.py wird mit
# in die EXE gepackt (version.py liest es) und am Ende wieder gelöscht.
BUILD = version.collect_build_info()
BUILD_INFO_FILE = os.path.join(SRC, "build_info.py")
with open(BUILD_INFO_FILE, "w", encoding="utf-8") as f:
    f.write("# Beim Bauen erzeugt (ZeitZeuge.spec), nicht von Hand ändern\n")
    f.write(f"BUILD = {BUILD!r}\n")
    # Update-Zugang (src/updater.py): Lese-Token nur für das Release-Repo, aus dem Secret
    # UPDATE_READ_TOKEN der CI. Ohne Token sucht diese Version nicht nach Updates.
    UPDATE = {"repo": os.environ.get("ZEITZEUGE_UPDATE_REPO", "").strip(),
              "token": os.environ.get("ZEITZEUGE_UPDATE_TOKEN", "").strip()}
    f.write(f"UPDATE = {UPDATE!r}\n")
version._INFO = BUILD  # Angaben dieses Builds, nicht die aus git

nums = version.file_version()
VERSION = version.full_version()
print(f"Zeitzeuge {version.version_details()}")

# Versionsangaben in der EXE (Eigenschaften → Details). Virenscanner stufen
# EXE-Dateien ohne diese Angaben eher als verdächtig ein.
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=nums, prodvers=nums),
    kids=[
        StringFileInfo([StringTable("040704B0", [
            StringStruct("CompanyName", "Filip Kroczak"),
            StringStruct("FileDescription", "Zeitzeuge – Tages-Timeline der Arbeitsspuren"),
            StringStruct("FileVersion", ".".join(map(str, nums))),
            StringStruct("InternalName", "ZeitZeuge"),
            StringStruct("LegalCopyright", "Copyright (c) 2026 Filip Kroczak"),
            StringStruct("OriginalFilename", "ZeitZeuge.exe"),
            StringStruct("ProductName", "Zeitzeuge"),
            StringStruct("ProductVersion", VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0407, 1200])]),
    ],
)

a = Analysis(
    [os.path.join(SRC, 'main_timeline.py')],
    pathex=[SRC],
    binaries=[],
    datas=[(os.path.join(ASSETS, name), '.') for name in
           ('zeitzeuge.png', 'zeitzeuge.ico', 'zeitzeuge.svg', 'zeitzeuge_anrufe.user.js')],
    hiddenimports=['build_info'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)

# Startbild: zeigt der Bootloader sofort beim Doppelklick, noch während sich die EXE entpackt
# (das dauert mit Virenscanner mehrere Sekunden). Zeitzeuge schreibt unten links den Fortschritt
# hinein und schließt es, sobald das Fenster steht (main_timeline.py). Bild: tests/make_splash.py
# Ladebalken und Text: eigener Tcl-Teil statt der PyInstaller-Textzeile (src/splash_screen.py).
# Der Balken läuft beim Entpacken über die Zahl der Dateien, danach melden die Startschritte.
import splash_screen  # noqa: E402
splash_screen.install(len(a.binaries) + len(a.datas), ASSETS)  # Bilder je Skalierung
splash = Splash(
    os.path.join(ASSETS, 'splash.png'),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(26, 146),
    text_size=10,
    # Geschweifte Klammern: PyInstaller setzt den Namen ungeschützt ins Tcl-Skript. Ohne sie bricht
    # „Segoe UI“ (mit Leerzeichen) das Skript ab und es bleibt ein leeres Fenster „tk“ stehen.
    text_font='{Segoe UI}',
    text_color='#62626B',
    text_default='Zeitzeuge startet …',
    always_on_top=False,  # Rückfragen beim Start (Entsperren) dürfen nicht dahinter liegen
)

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
    icon=[os.path.join(ASSETS, 'zeitzeuge.ico')],
    version=version_info,
    # DPI-bewusst wie Qt, schon ab dem Startbild: sonst springt es beim Start klein nach links oben
    manifest=splash_screen.manifest(),
)
# Kein UPX (upx=False oben): mit UPX gepackte EXE-Dateien melden Virenscanner besonders oft fälschlich.

if ONEDIR:
    exe = EXE(pyz, a.scripts, splash, [], exclude_binaries=True, **options)
    coll = COLLECT(exe, a.binaries, a.datas, splash.binaries, strip=False, upx=False,
                   name='ZeitZeuge-Ordner')
else:
    exe = EXE(pyz, a.scripts, splash, splash.binaries, a.binaries, a.datas, [], **options)

os.remove(BUILD_INFO_FILE)  # sonst zeigte der Start aus dem Quelltext die Angaben dieses Builds
