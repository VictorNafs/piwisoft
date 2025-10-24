# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None
HERE = Path.cwd()
WSL_DIR = HERE / "wsl"

# Collecter les rootfs et ressources dans dist\piwi_installer_gui\wsl\
datas = []
if WSL_DIR.exists():
    # embarque tout le dossier wsl (archives, marqueurs…)
    datas.append((str(WSL_DIR), "wsl"))

# Icônes & scripts nécessaires au post-install
for fn in ("piwi_icon.ico", "piwi_icon.png", "setup_piwi.sh", "create_shortcut.sh", "launch.sh", "path_resolver.py"):
    p = HERE / fn
    if p.exists():
        datas.append((str(p), "."))

hiddenimports = [
    # PyQt
    "PyQt5.sip",
]

a = Analysis(
    ['piwi_installer_gui.py'],
    pathex=[str(HERE)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='piwi_installer_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,        # éviter dépendance UPX
    console=False,    # GUI
    icon=str(HERE / 'piwi_icon.ico') if (HERE / 'piwi_icon.ico').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='piwi_installer_gui',
    distpath=str(HERE / 'dist'),
)
