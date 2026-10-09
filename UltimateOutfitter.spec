# PyInstaller spec - build with:  pyinstaller --noconfirm UltimateOutfitter.spec
# Produces a single-file windowed executable: dist/UltimateOutfitter.exe (on Windows)
import sys

block_cipher = None

a = Analysis(
    ["run_ultimate_outfitter.py"],
    pathex=[],
    binaries=[],
    datas=[("assets/icon.png", "assets")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pytest", "PySide6.QtWebEngineCore",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="UltimateOutfitter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    icon="assets/icon.ico" if sys.platform.startswith("win") else None,
)
