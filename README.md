# MarkItDownDesk

[![Latest Release](https://img.shields.io/github/v/release/MrSsg/MarkItDown?display_name=tag&sort=semver)](https://github.com/MrSsg/MarkItDown/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

MarkItDownDesk 是一个面向 Windows 的 Markdown 文档转换工作台，提供批量导入、队列调度、结果预览、历史记录和可选离线 OCR。

本项目基于微软开源项目 [MarkItDown](https://github.com/microsoft/markitdown) 进行二次开发。仓库中的 <code>packages/markitdown</code> 保留并使用 MarkItDown 的转换内核；<code>markitdown-desktop</code> 是本项目新增的 PySide6 桌面端，<code>ocr-engine</code> 是独立的本地 PaddleOCR 组件。MarkItDownDesk 是独立的衍生项目，并非微软官方发行版，也不代表微软官方立场。

## 当前版本

- 桌面端：<code>v1.2.2</code>
- 目标平台：Windows x64、CPU、支持 AVX
- 桌面包运行时：不依赖系统 Python、PaddlePaddle 或开发环境
- OCR：可选的本地 PaddleOCR，中英文 CPU 模型
- 核心许可证：MIT，详见 [LICENSE](./LICENSE)

## 功能

### 桌面转换

- PDF、DOCX、PPTX、XLSX、XLS、HTML、TXT、CSV、JSON、XML、Markdown、RTF
- JPG、JPEG、PNG 等图片
- WAV、MP3、M4A 等音频（部分音频能力可能需要系统中的外部解码器）
- MSG、EPUB、ZIP 等 MarkItDown 内核支持的格式
- Markdown 结果预览、复制和导出
- 文件拖放、批量队列、单任务调度、取消后续任务和失败项重试
- 明暗主题、历史面板、悬浮窗口和系统托盘

### 离线 OCR

- 仅在本地处理图片和 PDF，不上传用户文件
- 中文/英文 CPU 推理，OCR 作为独立可选组件安装
- 图片结果追加 <code>## OCR 文本</code>
- 扫描 PDF 只识别原生文本少于 32 个有效字符的页面，保留其他页面的原生文本和表格结果
- 支持在线安装和本地 ZIP 导入
- 组件安装前校验 Ed25519 签名、SHA-256、文件大小和版本要求
- 安装失败自动回滚到上一个可用版本

桌面端的 OCR 不使用云端视觉模型、API Key 或 LLM，也不处理 Office 文档内嵌图片。仓库中的 <code>packages/markitdown-ocr</code> 是独立的 LLM 插件代码，不会被打进当前桌面 EXE，也不是本项目的离线 OCR 实现。

### 资源保护

默认限制如下，部分上限可在设置中调整：

| 项目 | 默认值 |
| --- | ---: |
| 单文件大小 | 200 MiB |
| 单批次文件数 | 100 |
| PDF 页数 | 500 页 |
| ZIP 解压后大小 | 1 GiB |
| ZIP 文件数 | 10,000 项 |
| ZIP 最大压缩比 | 100:1 |

转换结果只保存在当前会话目录。退出应用或下次启动时，未固定的会话结果会被清理；历史记录只保存文件元数据和导出信息，不永久保存全文。

## 下载与使用

### 桌面端

从 [GitHub Releases](https://github.com/MrSsg/MarkItDown/releases) 下载最新的 Windows x64 压缩包，当前版本为 [MarkItDownDesk v1.2.2](https://github.com/MrSsg/MarkItDown/releases/tag/v1.2.2)。

1. 解压压缩包。
2. 运行 <code>MarkItDownDesk-fast.exe</code>。
3. 拖入文件或通过“导入文件”添加任务。
4. 在右侧查看 Markdown，按需复制或导出。

桌面包不需要安装 Python。首次勾选“启用离线 OCR”时，可在应用内安装 OCR 组件；也可以下载 [ocr-engine-v1](https://github.com/MrSsg/MarkItDown/releases/tag/ocr-engine-v1) 中的 ZIP，通过安装窗口导入。

### 命令行和 Python 内核

如果只需要使用微软 MarkItDown 的转换内核，可以从仓库源码安装：

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -e ".\packages\markitdown[all]"
markitdown path-to-file.pdf -o document.md
~~~

也可以直接使用 Python API：

~~~python
from markitdown import MarkItDown

converter = MarkItDown(enable_plugins=False)
result = converter.convert("report.docx")
print(result.markdown)
~~~

内核的原始使用方式、可选依赖和 API 说明，请参考微软上游项目 [microsoft/markitdown](https://github.com/microsoft/markitdown)。

## 从源码构建桌面端

### 构建环境

- Windows x64
- Python 3.12（推荐 3.12.10）
- PowerShell 7
- Git

桌面构建脚本会在 <code>markitdown-desktop/.venv-build</code> 创建独立环境，并安装 PyInstaller 和 MarkItDown 的桌面依赖：

~~~powershell
$env:MARKITDOWN_OCR_PUBLIC_KEYS_FILE = (Resolve-Path .\markitdown-desktop\app\ocr_public_keys.json)
pwsh .\markitdown-desktop\build_fast.ps1 -Clean
~~~

生成正式桌面压缩包：

~~~powershell
pwsh .\markitdown-desktop\package_release.ps1 -Clean
~~~

构建输出默认位于 <code>markitdown-desktop/dist</code>。发布前应使用真实 EXE 回归脚本验证 PDF、DOCX、XLSX 和图片转换：

~~~powershell
pwsh .\markitdown-desktop\test_release.ps1
~~~

### 构建 OCR 组件

OCR 组件必须在安全的发布环境中构建。签名私钥通过环境变量 <code>MARKITDOWN_OCR_SIGNING_KEY</code> 注入，不能写入仓库、日志或桌面包：

~~~powershell
$env:MARKITDOWN_OCR_SIGNING_KEY = "<仅在安全发布环境设置>"
pwsh .\markitdown-desktop\ocr-engine\build.ps1
~~~

组件构建、签名清单、健康检查和发布流程见 [ocr-engine/README.md](./markitdown-desktop/ocr-engine/README.md)。GitHub Actions 工作流位于 [.github/workflows/desktop.yml](./.github/workflows/desktop.yml)。

## 测试

桌面端单元测试：

~~~powershell
$env:PYTHONPATH = "$PWD\markitdown-desktop;$PWD\packages\markitdown\src"
& .\markitdown-desktop\.venv-build\Scripts\python.exe -m unittest discover -s .\markitdown-desktop\tests -v
~~~

发行版回归测试：

~~~powershell
pwsh .\markitdown-desktop\test_release.ps1 -ReleaseDirectory ".\markitdown-desktop\dist\MarkItDownDesk-fast-v1.2.2-windows-x64"
~~~

CI 会在 Windows Python 3.12 环境中执行桌面单元测试、真实 EXE 四格式转换和 OCR 集成冒烟测试。

## 项目结构

~~~text
packages/markitdown/           微软 MarkItDown 转换内核（本项目基础）
packages/markitdown-ocr/       独立的 LLM OCR 插件代码，不打包进桌面端
markitdown-desktop/app/        PySide6 桌面界面、队列、历史和 OCR 客户端
markitdown-desktop/ocr-engine/ 独立 PaddleOCR CPU 引擎及签名发布脚本
markitdown-desktop/assets/     桌面图标和界面资源
.github/workflows/             Windows 构建、回归测试和 OCR 发布流程
~~~

## 安全与隐私

- MarkItDown 内核以当前进程权限访问输入路径和资源。不要在未验证的情况下处理不可信路径、URL 或压缩包。
- 桌面端默认限制文件、PDF、ZIP 的大小和数量，避免意外的资源消耗。
- 离线 OCR 只读取本地文件；组件下载只获取 OCR 程序和模型，不上传用户文件。
- 桌面端不执行 Python 包自更新，升级通过完整的桌面发行版完成。
- 不要把 <code>MARKITDOWN_OCR_SIGNING_KEY</code>、私钥文件或用户转换结果提交到 Git。

## 已知限制

- 当前桌面发行版只面向 Windows x64、CPU 和支持 AVX 的设备。
- OCR 首版只支持独立图片和 PDF，不支持 GPU、云端 OCR 或 Office 内嵌图片。
- 普通转换超时后会等待第三方转换线程自然结束，不强制终止线程。
- 部分音频格式需要系统安装额外的解码器。

## 开源来源与许可证

本项目保留微软 MarkItDown 的上游版权和 MIT 许可证声明，并在其基础上增加桌面端、离线 OCR、打包和测试代码。上游项目地址：

- [Microsoft MarkItDown](https://github.com/microsoft/markitdown)
- [Microsoft MarkItDown 文档](https://github.com/microsoft/markitdown#readme)
- [本项目仓库](https://github.com/MrSsg/MarkItDown)

桌面端使用的 PySide6、PaddleOCR/PaddlePaddle 及其他第三方组件各自遵循其许可证；发布包中的第三方许可文件应一并保留。项目整体许可证见 [LICENSE](./LICENSE)。

## 贡献

欢迎提交 Issue 和 Pull Request。涉及桌面端、OCR、打包或发布链路的改动，请同时补充对应测试，并确保：

- 不提交任何签名私钥、API Key 或用户文件；
- 不把云端 OCR 或 LLM 依赖混入纯离线 OCR 路径；
- 修改转换内核后通过 PDF、DOCX、XLSX、图片的真实 EXE 回归；
- 修改发布流程后验证清单签名、SHA-256 和组件回滚。

开发范围和验收记录见 [开发计划书.md](./开发计划书.md)。
