# -*- mode: python ; coding: utf-8 -*-
# 빌드: pyinstaller --noconfirm DaCapture.spec  (또는 build.ps1)

EXCLUDES = [
    "tkinter", "unittest", "pydoc", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtConcurrent", "PySide6.QtDBus", "PySide6.QtSvg", "PySide6.QtXml",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
# 사용하지 않는 Qt 번역/대형 바이너리 제거
a.binaries = [b for b in a.binaries if not any(x in b[0] for x in (
    "Qt6Quick", "Qt6Qml", "Qt6Pdf", "opengl32sw", "Qt6VirtualKeyboard", "Qt6Svg"))]
a.datas = [d for d in a.datas if "translations" not in d[0] or "qtbase_ko" in d[0]]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DaCapture",
    icon="assets/dacapture.ico",
    version="version_info.txt",
    console=False,
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
)
