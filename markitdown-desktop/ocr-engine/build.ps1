param(
    [string]$Output = "dist",
    [string]$ReleaseUrl = "https://github.com/MrSsg/MarkItDown/releases/download/ocr-engine-v1/ocr-engine.zip",
    [string]$Version = "1.1.0",
    [string]$MinimumAppVersion = "1.2.0",
    [string]$KeyId = "markitdown-ocr-v1"
)

$ErrorActionPreference = "Stop"
$python = Get-Command py -ErrorAction Stop
& $python.Source -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
$modelCache = Join-Path (Get-Location) ".model-cache"
if (Test-Path $modelCache) { Remove-Item -LiteralPath $modelCache -Recurse -Force }
$env:PADDLE_PDX_CACHE_HOME = $modelCache
& .\.venv\Scripts\python.exe -c "from paddleocr import PaddleOCR; PaddleOCR(lang='ch', enable_mkldnn=False)"
if (-not (Test-Path (Join-Path $modelCache "official_models"))) {
    throw "未能下载 PaddleOCR 模型"
}
$intermediate = Join-Path (Get-Location) (".pyinstaller-dist-" + [guid]::NewGuid().ToString("N"))
& .\.venv\Scripts\pyinstaller.exe .\ocr_engine.spec --noconfirm --clean --distpath $intermediate
Copy-Item -LiteralPath $modelCache -Destination (Join-Path $intermediate "ocr-engine\models") -Recurse -Force

New-Item -ItemType Directory -Force $Output | Out-Null
Compress-Archive -Path (Join-Path $intermediate "ocr-engine\*") -DestinationPath (Join-Path $Output "ocr-engine.zip") -Force
$archive = Join-Path $Output "ocr-engine.zip"
if (-not $env:MARKITDOWN_OCR_SIGNING_KEY) {
    throw "缺少 MARKITDOWN_OCR_SIGNING_KEY；拒绝生成未签名 OCR 组件"
}
& .\.venv\Scripts\python.exe .\sign_manifest.py `
    --archive $archive --output (Join-Path $Output "ocr-engine-manifest.json") `
    --url $ReleaseUrl --version $Version --min-app-version $MinimumAppVersion `
    --key-id $KeyId --private-key $env:MARKITDOWN_OCR_SIGNING_KEY
Get-FileHash $archive -Algorithm SHA256
Remove-Item -LiteralPath $modelCache -Recurse -Force
Remove-Item -LiteralPath $intermediate -Recurse -Force
