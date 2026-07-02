# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller-Spezifikation für SchattenBlase.

Build aus dem Projektverzeichnis:
    pyinstaller --clean --noconfirm SchattenBlase.spec

Optionales Icon:
    assets/icon.ico
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
project_root = Path(SPECPATH)
icon_file = project_root / "assets" / "icon.ico"
icon = str(icon_file) if icon_file.exists() else None

hiddenimports = []
hiddenimports += collect_submodules("lang")


a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "pytest",
        "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SchattenBlase",
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
    icon=icon,
)
