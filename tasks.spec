# -*- mode: python ; coding: utf-8 -*-
"""
tasks.spec - PyInstaller specification for Tasks.
Builds a unified onedir distribution with two executables:
  1. Tasks.exe     (Console subsystem for interactive TUI and CLI)
  2. TasksTray.exe (Windowed subsystem for silent background System Tray)
"""

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

spec_root = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(spec_root, 'assets'), 'assets'),
    (os.path.join(spec_root, 'src'), 'src'),
]

# Collect Textual and Rich themes and assets if available
try:
    datas += collect_data_files('textual')
except Exception:
    pass

hidden_imports = [
    'winotify',
    'pystray',
    'pystray._win32',
    'PIL',
    'PIL.Image',
    'fitz',
    'pymupdf',
    'fpdf',
    'textual',
    'rich',
    'playwright',
    'sqlite3',
]
try:
    hidden_imports += collect_submodules('src')
except Exception:
    pass

a = Analysis(
    ['main.py'],
    pathex=[
        spec_root,
        os.path.join(spec_root, 'src'),
        os.path.join(spec_root, 'src', 'core'),
        os.path.join(spec_root, 'src', 'services'),
        os.path.join(spec_root, 'src', 'ui'),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'IPython', 'unittest', 'pytest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# 1. Console executable: Tasks.exe
exe_main = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Tasks',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(spec_root, 'assets', 'app_icon.ico'),
    version=os.path.join(spec_root, 'installer', 'version_info.txt'),
)

# 2. Windowed/GUI executable: TasksTray.exe (no black console window)
exe_tray = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TasksTray',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(spec_root, 'assets', 'app_icon.ico'),
    version=os.path.join(spec_root, 'installer', 'version_info_tray.txt'),
)

# Unified Onedir distribution folder: dist/Tasks/
coll = COLLECT(
    exe_main,
    exe_tray,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Tasks',
)
