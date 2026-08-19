# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec do motor Real Oficial (onedir).
# Build:  pyinstaller engine.spec --distpath ../engine-dist
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("ctranslate2", "faster_whisper", "onnxruntime"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += [
    ("assets", "assets"),
    ("app/reports/templates", "app/reports/templates"),
]
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "torchvision", "torchaudio", "tensorflow", "matplotlib",
              "PyQt5", "PySide6", "tkinter", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="real-oficial-engine",
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="real-oficial-engine",
)
