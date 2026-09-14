# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

from PyInstaller.building.datastruct import TOC
from PyInstaller.utils.hooks import collect_data_files

ocr_keys_file = os.environ.get('MARKITDOWN_OCR_PUBLIC_KEYS_FILE', 'app/ocr_public_keys.json')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/styles/dark.qss', 'app/styles'),
        ('app/styles/light.qss', 'app/styles'),
        ('assets/icon_16.png', 'assets'),
        ('assets/icon_32.png', 'assets'),
        ('assets/icon_128.png', 'assets'),
        ('assets/app_icon.ico', 'assets'),
        ('assets/markconvert_float_16.png', 'assets'),
        ('assets/markconvert_float_32.png', 'assets'),
        ('assets/markconvert_float_128.png', 'assets'),
        ('assets/check.png', 'assets'),
        ('assets/Convert.png', 'assets'),
        ('assets/copy.png', 'assets'),
        ('assets/delete.png', 'assets'),
        ('assets/open_file.png', 'assets'),
        ('assets/setting.png', 'assets'),
        ('assets/theme.png', 'assets'),
        (ocr_keys_file, 'app'),
        ('../packages/markitdown/src/markitdown/__about__.py', 'packages/markitdown/src/markitdown'),
    ] + collect_data_files('magika'),
    hiddenimports=[
        'markitdown', 'markitdown._markitdown', 'markitdown.converters',
        'markitdown.converters._pdf_converter', 'markitdown.converters._docx_converter',
        'markitdown.converters._pptx_converter', 'markitdown.converters._xlsx_converter',
        'markitdown.converters._html_converter', 'markitdown.converters._image_converter',
        'markitdown.converters._audio_converter', 'markitdown.converters._plain_text_converter',
        'markitdown.converters._csv_converter', 'markitdown.converters._epub_converter',
        'markitdown.converters._ipynb_converter', 'markitdown.converters._zip_converter',
        'markitdown.converters._exiftool', 'markitdown.converters._llm_caption',
        'markitdown.converters._markdownify', 'markitdown.converters._transcribe_audio',
        'markitdown._exceptions', 'markitdown._stream_info', 'markitdown._base_converter',
        'markitdown._uri_utils', 'markitdown.converter_utils', 'markitdown.converter_utils.docx',
        'markitdown.converter_utils.docx.pre_process', 'markitdown.converter_utils.docx.math',
        'markitdown.converter_utils.docx.math.omml', 'markitdown.converter_utils.docx.math.latex_dict',
    ],
    hookspath=[],
    hooksconfig={},
    excludes=[
        'tkinter', 'matplotlib', 'notebook', 'jupyter', 'jupyterlab',
        'test', 'tests',
    ],
)

# A local JDK contributes a duplicate UCRT DLL during dependency scanning.
# Windows already supplies this runtime; excluding the duplicate avoids a
# locked-file failure while COLLECT assembles the onedir release.
a.binaries = TOC(entry for entry in a.binaries if entry[0].lower() != 'ucrtbase.dll')

# Qt uses Windows' ICU API. A Poppler/Conda ICU found on PATH exports
# version-suffixed symbols and shadows the system DLL in a frozen app.
a.binaries = TOC(
    entry for entry in a.binaries
    if entry[0].lower() not in {'icuuc.dll', 'icudt78.dll'}
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MarkItDownDesk-fast',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='MarkItDownDesk-fast',
)
