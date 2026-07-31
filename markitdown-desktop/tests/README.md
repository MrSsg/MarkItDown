# 桌面端测试

```powershell
$env:PYTHONPATH = "$PWD\markitdown-desktop;$PWD\packages\markitdown\src"
& "$PWD\markitdown-desktop\.venv-build\Scripts\python.exe" -m unittest discover -s markitdown-desktop/tests -v
```

打包后，在不依赖全局 Python 的 Windows 环境运行：

```powershell
pwsh ./markitdown-desktop/test_release.ps1
```
