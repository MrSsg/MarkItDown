# OCR 组件构建

在 Windows x64 上安装 Python 3.12 后运行：

```powershell
pwsh ./build.ps1
```

首次发布先生成密钥：

```powershell
.\.venv\Scripts\python.exe .\generate_signing_key.py --public-key-output ..\app\ocr_public_keys.json
```

将脚本仅输出到终端的私钥值保存为 GitHub Actions Secret `MARKITDOWN_OCR_SIGNING_KEY`，然后用该公钥文件构建桌面 EXE：

```powershell
$env:MARKITDOWN_OCR_PUBLIC_KEYS_FILE = (Resolve-Path ../app/ocr_public_keys.json)
pwsh ../build_fast.ps1 -Clean
```

脚本会下载并打包中英文 CPU 模型，生成 `dist/ocr-engine.zip` 与签名的 `dist/ocr-engine-manifest.json`。发布前必须在安全环境设置 `MARKITDOWN_OCR_SIGNING_KEY`（Base64 编码的 Ed25519 私钥）；私钥不能提交到仓库。把两者上传到标签 `ocr-engine-v1` 的 GitHub Release；若 Release URL 不同，构建时传入 `-ReleaseUrl`。组件运行时只使用 ZIP 中的模型，不写入用户模型缓存。

桌面发布构建还必须设置 `MARKITDOWN_OCR_PUBLIC_KEYS_FILE`，指向仅含公钥的 JSON，例如 `{"markitdown-ocr-v1":"Base64 Ed25519 公钥"}`。该文件会冻结进 EXE；私钥仅保留在 GitHub Actions Secret 或离线发布环境。

正式桌面包使用 `../package_release.ps1` 生成带版本目录和 SHA-256 元数据的 ZIP：

```powershell
pwsh ../package_release.ps1 -Clean
```

`build.ps1` 和 `test_release_ocr.ps1` 会调用 `validate_manifest.py`，校验清单签名、归档哈希、文件大小和正式下载地址；占位地址不能通过发布门禁。引擎通过 `--jsonl` 持续处理同一 Job 的多个请求，Job 结束时由桌面端关闭子进程。

清单格式：

```json
{
  "version": "1.0.0",
  "url": "https://github.com/MrSsg/MarkItDown/releases/download/ocr-engine-v1/ocr-engine.zip",
  "sha256": "压缩包的 SHA-256",
  "size_bytes": 0,
  "min_app_version": "1.2.0",
  "key_id": "markitdown-ocr-v1",
  "signature": "Ed25519 签名"
}
```

清单文件名为 `ocr-engine-manifest.json`，上传至同一 GitHub Release。主程序安装前会校验 ZIP 哈希。
