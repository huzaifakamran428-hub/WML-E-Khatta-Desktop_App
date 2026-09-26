# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=['PyQt6.QtSvg'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtQml', 'PyQt6.QtQuick', 'chardet'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='WML E-Khatta',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/WaqareMedina.ico',
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=True,
    name='WML E-Khatta',
)
