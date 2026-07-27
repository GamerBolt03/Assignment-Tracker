# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['flask', 'googleapiclient', 'google_auth_oauthlib', 'google.auth', 'transformers', 'huggingface_hub', 'sqlite3', 'webview', 'oauthlib', 'requests']
hiddenimports += collect_submodules('email')


a = Analysis(
    ['C:/Users/Arhaan/Downloads/Assignment Tracker/app.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/Arhaan/Downloads/Assignment Tracker/templates', 'templates'), ('C:/Users/Arhaan/Downloads/Assignment Tracker/requirements.txt', '.')],
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
    name='AssignmentTracker',
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
    icon=['C:\\Users\\Arhaan\\Downloads\\Assignment Tracker\\app_icon.ico'],
)
