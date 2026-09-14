# 离线 OCR 引擎

本分支 `offline-ocr` 只维护 PaddleOCR CPU 引擎、模型打包、签名和验收脚本。桌面程序及 OCR 客户端维护在 [main](https://github.com/MrSsg/MarkItDown/tree/main)。两个分支独立发布，不应整分支互相合并。

## 构建与验收

Windows x64、Python 3.12，在本分支根目录执行：

```powershell
pwsh ./build.ps1
pwsh ./test_release_ocr.ps1
```

构建前通过安全环境注入 `MARKITDOWN_OCR_SIGNING_KEY`。`ocr_public_keys.json` 仅含公钥，必须与主分支 `markitdown-desktop/app/ocr_public_keys.json` 保持一致；不要重新生成现有发布密钥。

输出是 `dist/ocr-engine.zip` 和 `dist/ocr-engine-manifest.json`。现有离线包见 [ocr-engine-v1](https://github.com/MrSsg/MarkItDown/releases/tag/ocr-engine-v1)。新版本通过 `build.ps1` 的 `-Version`、`-ReleaseUrl` 指定版本和下载地址。

无需模型的单元测试：

```powershell
python -m pip install cryptography
python -m unittest discover -s tests -v
```

GitHub Actions 在本分支执行单元测试；手动运行工作流时设置 `build_release=true`，才构建签名包并使用主分支桌面程序执行集成验收。`ocr-engine-*` 标签触发签名构建和发布，需要仓库 Secret `MARKITDOWN_OCR_SIGNING_KEY`。发布标签应指向本分支。
