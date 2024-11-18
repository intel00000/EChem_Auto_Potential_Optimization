import os

# Define the path dynamically
icon_path = os.path.join("icons", "icons-red.ico")

a = Analysis(
    ['pump_control.py'],
    pathex=['.'],
    binaries=[],
    datas=[('icons/icons-black.ico', 'icons'), ('icons/icons-white.ico', 'icons'), ('icons/icons-red.ico', 'icons')],
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
