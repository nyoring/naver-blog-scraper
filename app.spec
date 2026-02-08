# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

playwright_datas, playwright_binaries, playwright_hiddenimports = collect_all('playwright')

import playwright
_pw_pkg = Path(playwright.__file__).parent
print(f"[SPEC] playwright package: {_pw_pkg}")
print(f"[SPEC] collect_all datas: {len(playwright_datas)}, binaries: {len(playwright_binaries)}")

_pw_driver_dir = _pw_pkg / 'driver'
_pw_driver_files = []
if _pw_driver_dir.is_dir():
    for _f in _pw_driver_dir.rglob('*'):
        if _f.is_file():
            _rel = str(Path('playwright') / _f.parent.relative_to(_pw_pkg))
            _pw_driver_files.append((str(_f), _rel))
    print(f"[SPEC] driver files collected: {len(_pw_driver_files)}")
    for _d in _pw_driver_files[:10]:
        print(f"[SPEC]   {_d}")
else:
    print(f"[SPEC] WARNING: driver dir not found at {_pw_driver_dir}")

a = Analysis(
    ['app_entry.py'],
    pathex=[],
    binaries=playwright_binaries,
    datas=[
        ('templates', 'templates'),
        *playwright_datas,
        *_pw_driver_files,
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
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name='App')
