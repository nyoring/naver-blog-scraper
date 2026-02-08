# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all
from PyInstaller.building.datastruct import Tree

playwright_datas, playwright_binaries, playwright_hiddenimports = collect_all('playwright')

import playwright
_pw_tree = Tree(
    str(Path(playwright.__file__).parent),
    prefix='playwright',
    excludes=['__pycache__', '*.pyc'],
)

a = Analysis(
    ['app_entry.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
    ],
    hiddenimports=[
        'waitress',
        'jinja2.ext',
        'flask.json',
        'engineio.async_drivers.threading',
        *playwright_hiddenimports,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='App',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, _pw_tree, strip=False, upx=True, name='App')
