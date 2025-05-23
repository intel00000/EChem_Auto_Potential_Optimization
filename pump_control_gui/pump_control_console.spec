import os
import customtkinter as ctk

# Define the path dynamically
icon_path = os.path.join("icons", "icons-red.ico")
ctk_path = ctk.__path__[0]

a = Analysis(
    ['pump_control.py'],
    pathex=['.'],
    binaries=[],
    datas=[('icons/icons-black.ico', 'icons'), ('icons/icons-white.ico', 'icons'), ('icons/icons-red.ico', 'icons'), ('xmls/combined_sequencer_methods.xml', 'xmls'), (ctk_path, 'customtkinter')],
    hiddenimports=[],
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
    name='pump_control_console',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
