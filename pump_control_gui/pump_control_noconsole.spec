import os
import customtkinter as ctk
from PyInstaller.utils.hooks import collect_all

# Define the path dynamically
icon_path = os.path.join("icons", "icons-red.ico")
ctk_path = ctk.__path__[0]

# Collect data files, binaries, and hidden imports for tkinterdnd2
datas = [
    ("icons/icons-black.ico", "icons"),
    ("icons/icons-white.ico", "icons"),
    ("icons/icons-red.ico", "icons"),
    ("xmls/combined_sequencer_methods.xml", "xmls"),
    ("data/micropython-variants-uf2.json", "data"),
    (ctk_path, "customtkinter"),
]
binaries = []
hiddenimports = []
tmp_ret = collect_all("tkinterdnd2")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    ["pump_control.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
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
    name="pump_control",
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
