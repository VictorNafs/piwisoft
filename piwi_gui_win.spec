# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None
HERE = Path.cwd()  # construit depuis la racine du projet lors du build

# Embarquer icônes + scripts utiles au run (Windows -> WSL au besoin)
datas = []
for fn in (
    "piwi_icon.ico", "piwi_icon.png",
    "noyau.py", "path_resolver.py",
    "create_shortcut.sh", "setup_piwi.sh",
    "piwi_purge.sh", "launch.sh",
):
    p = HERE / fn
    if p.exists():
        datas.append((str(p), "."))

# (optionnel) embarquer le dossier 'wsl' si présent
if (HERE / "wsl").exists():
    datas.append((str(HERE / "wsl"), "wsl"))

# Plus de keyring / win32ctypes ici.
# Garder seulement ce qui peut manquer côté PyQt.
hiddenimports = [
    "PyQt5.sip",
    "sip",
]

a = Analysis(
    ['piwi_gui_win.py'],
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
    name='piwi_gui_win',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI
    icon=str(HERE / 'piwi_icon.ico') if (HERE / 'piwi_icon.ico').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='piwi_gui_win',
    distpath=str(HERE / 'dist'),
)
