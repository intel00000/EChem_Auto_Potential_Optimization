import os
import customtkinter as ctk
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('tkinterdnd2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Define the path dynamically
icon_path = os.path.join("icons", "icons-red.ico")
ctk_path = ctk.__path__[0]

a = Analysis(
    ['pump_control.py'],
    pathex=['.'],
    binaries=binaries,
    datas=[('icons/icons-black.ico', 'icons'), ('icons/icons-white.ico', 'icons'), ('icons/icons-red.ico', 'icons'), ('xmls/combined_sequencer_methods.xml', 'xmls'), ('data/micropython-variants-uf2.json', '.'), (ctk_path, 'customtkinter')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='pump_control_noconsole',
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
    icon=icon_path,
)
