# -*- mode: python ; coding: utf-8 -*-
import os

# Расчётное ядро под текущую ОС: heat3d.exe (Windows) или heat3d (Linux)
ENGINE = 'heat3d.exe' if os.name == 'nt' else 'heat3d'


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[(ENGINE, '.'), ('heat3d.cpp', '.')],
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
    name='HeatSim3D',
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
)
