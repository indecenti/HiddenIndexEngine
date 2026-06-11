# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['cv2', 'numpy', 'scipy.ndimage', 'engine.minigames.arcade_eleven.arcade_eleven_game', 'engine.minigames.asteroids.asteroids_game', 'engine.minigames.centipede.centipede_game', 'engine.minigames.minipong.minipong_game', 'engine.minigames.slot_classic.slot_classic_game', 'engine.minigames.spot_differences.spot_differences_game', 'engine.minigames.sudoku.sudoku_game', 'engine.minigames.tetran.tetran_game', 'engine.minigames.tower.tower_game']
tmp_ret = collect_all('jsonschema')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('jsonschema_specifications')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('rpds')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['G:\\HIE git\\run_editor.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'torchaudio', 'onnxruntime', 'transformers', 'tokenizers', 'sklearn', 'matplotlib', 'pandas', 'pyarrow', 'llvmlite', 'numba', 'lxml', 'IPython', 'notebook', 'jupyter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HiddenEditor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HiddenEditor',
)
