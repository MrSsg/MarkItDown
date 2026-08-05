# 桌面端测试

```powershell
$env:PYTHONPATH = "$PWD\markitdown-desktop;$PWD\packages\markitdown\src"
& "$PWD\markitdown-desktop\.venv-build\Scripts\python.exe" -m unittest discover -s markitdown-desktop/tests -v
```

打包后，在不依赖全局 Python 的 Windows 环境运行：

```powershell
pwsh ./markitdown-desktop/test_release.ps1
```

使用已构建的 OCR 归档验证桌面端安装外的 OCR 注册、图片、扫描 PDF 和混合 PDF：

```powershell
pwsh ./markitdown-desktop/test_release_ocr_desktop.ps1
```

脚本会自动使用归档旁的 `ocr-engine-manifest.json`（若存在）执行签名、哈希和正式下载地址校验。
