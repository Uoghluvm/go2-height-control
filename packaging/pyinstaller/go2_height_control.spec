# -*- mode: python ; coding: utf-8 -*-

import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve().parents[1]

hiddenimports = []
hiddenimports += collect_submodules("unitree_webrtc_connect")
hiddenimports += collect_submodules("aiortc")
hiddenimports += collect_submodules("av")

datas = [
    (str(ROOT / "go2_height_control_ui" / "static"), "go2_height_control_ui/static"),
    (str(ROOT / "go2_height_control_legacy_114"), "go2_height_control_legacy_114"),
]
datas += collect_data_files("wasmtime", include_py_files=False)

wasmtime_dir = Path(importlib.util.find_spec("wasmtime").origin).parent
wasmtime_binaries = []
for path in wasmtime_dir.glob("*/*"):
    suffix = path.suffix.lower()
    if suffix in {".so", ".dll", ".dylib"} or ".so." in path.name:
        target = Path("wasmtime") / path.parent.relative_to(wasmtime_dir)
        wasmtime_binaries.append((str(path), str(target)))

a = Analysis(
    [str(ROOT / "go2_height_control_ui" / "backend.py")],
    pathex=[str(ROOT)],
    binaries=wasmtime_binaries,
    datas=datas,
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
    [],
    exclude_binaries=True,
    name="go2-height-control",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name="go2-height-control",
)
