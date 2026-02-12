# -*- mode: python ; coding: utf-8 -*-
# Build with: uv run pyinstaller "LED Wall.spec"


import os
import glob

def get_effects():
    effects_dir = os.path.join('src', 'led_wall', 'effects')
    effects = []
    if os.path.exists(effects_dir):
        for f in os.listdir(effects_dir):
            if f.endswith('.py') and f not in ['__init__.py', 'base_effect.py', 'effect_manager.py']:
                effects.append('led_wall.effects.' + f[:-3])
    return effects

a = Analysis(
    ['entry_points\\main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('C:\\Users\\lorin\\Documents\\Programmieren\\LED_Wall\\.venv\\lib\\site-packages\\nicegui', 'nicegui'),
        ('src/led_wall/effects', 'led_wall/effects'),
        ('src/led_wall/ui/*.vue', 'led_wall/ui'),
        ('src/led_wall/static', 'led_wall/static'),
    ],
    hiddenimports=get_effects(),
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
    name='LED Wall',
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
    icon='icon.png'
)
