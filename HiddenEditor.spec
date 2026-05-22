# -*- mode: python ; coding: utf-8 -*-
#
# Spec PyInstaller per HiddenEditor.
#
# NON modificare hiddenimports / excludes / collect_all qui: la single source
# of truth è in editor/pyinstaller_common.py. Questo file delega a quel modulo.
#
# Riproducibilità: stessa versione di pyinstaller_common + stessa
# requirements.txt → stesso EXE.

from pathlib import Path
import sys

# Add project root al sys.path per importare editor.pyinstaller_common
_PROJECT_ROOT = Path(SPECPATH).resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from editor.pyinstaller_common import (  # noqa: E402
    spec_analysis_kwargs,
    read_version,
    write_version_info,
)

_VERSION = read_version(_PROJECT_ROOT)
print(f"[SPEC] Building HiddenEditor v{_VERSION}")

_ENTRY = str(_PROJECT_ROOT / "run_editor.py")
_ICON = _PROJECT_ROOT / "editor" / "assets" / "icon.ico"
_VERSION_INFO = write_version_info(
    _PROJECT_ROOT,
    product_name="HiddenEditor",
    file_description="HiddenEditor — level editor per giochi hidden object",
)

a = Analysis(
    [_ENTRY],
    pathex=[str(_PROJECT_ROOT)],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    noarchive=False,
    optimize=0,
    **spec_analysis_kwargs(_PROJECT_ROOT),
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HiddenEditor",
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
    icon=str(_ICON) if _ICON.exists() else None,
    version=str(_VERSION_INFO),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HiddenEditor",
)
