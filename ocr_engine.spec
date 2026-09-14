# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.building.datastruct import TOC
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = []
binaries = []
hiddenimports = ["unicodedata"]
for package in ("paddle", "paddlex", "paddleocr", "requests", "charset_normalizer"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

# PaddleX checks these distributions through importlib.metadata before it
# enables the lightweight OCR pipeline. Their Python modules are collected by
# the packages above, but their distribution metadata is not.
for distribution in (
    "paddlepaddle",
    "imagesize",
    "opencv-contrib-python",
    "pyclipper",
    "pypdfium2",
    "python-bidi",
    "shapely",
):
    datas += copy_metadata(distribution)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "notebook", "jupyter", "jupyterlab"],
)

# PyInstaller discovers a duplicate Universal CRT from the local JDK. Windows
# already provides the UCRT; retaining the JDK copy causes a locked-file error
# during COLLECT on this machine.
a.binaries = TOC(entry for entry in a.binaries if entry[0].lower() != "ucrtbase.dll")

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ocr-engine",
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ocr-engine")
