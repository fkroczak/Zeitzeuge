# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller ZeitZeuge.spec  ->  dist/ZeitZeuge.exe

a = Analysis(
    ['main_timeline.py'],
    pathex=[],
    binaries=[],
    datas=[('zeitzeuge.png', '.'), ('zeitzeuge.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ZeitZeuge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['zeitzeuge.ico'],
)
