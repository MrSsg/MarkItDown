param(
    [string]$ReleaseDirectory = "",
    [string]$OcrArchive = "",
    [string]$OcrManifest = ""
)

$ErrorActionPreference = "Stop"
if (-not $ReleaseDirectory) {
    $latest = Get-ChildItem (Join-Path $PSScriptRoot "dist") -Directory -Filter "py312-*" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw "未找到 Python 3.12 发行目录" }
    $ReleaseDirectory = Join-Path $latest.FullName "MarkItDownDesk-fast"
}
if (-not $OcrArchive) {
    $OcrArchive = Join-Path $PSScriptRoot "ocr-engine\dist\ocr-engine.zip"
}
if (-not $OcrManifest) {
    $candidateManifest = Join-Path ([IO.Path]::GetDirectoryName($OcrArchive)) "ocr-engine-manifest.json"
    if (Test-Path -LiteralPath $candidateManifest -PathType Leaf) {
        $OcrManifest = $candidateManifest
    }
}
$exe = Join-Path $ReleaseDirectory "MarkItDownDesk-fast.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "未找到发行版 EXE: $exe" }
if (-not (Test-Path -LiteralPath $OcrArchive)) { throw "未找到 OCR 组件归档: $OcrArchive" }

$target = Join-Path ([IO.Path]::GetTempPath()) ("markitdown-desktop-ocr-" + [guid]::NewGuid().ToString("N"))
$fixtureDir = Join-Path $target "fixtures"
$python = Join-Path $PSScriptRoot "ocr-engine\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "未找到 OCR Python 3.12 环境: $python" }
if ($OcrManifest) {
    if (-not (Test-Path -LiteralPath $OcrManifest -PathType Leaf)) {
        throw "未找到 OCR 组件清单: $OcrManifest"
    }
    & $python (Join-Path $PSScriptRoot "ocr-engine\validate_manifest.py") `
        --manifest $OcrManifest --archive $OcrArchive `
        --public-key-file (Resolve-Path (Join-Path $PSScriptRoot "app\ocr_public_keys.json")) `
        --require-release-url
    if ($LASTEXITCODE -ne 0) { throw "OCR 组件清单验签失败" }
}
try {
    Expand-Archive -LiteralPath $OcrArchive -DestinationPath $target -Force
    & $python (Join-Path $PSScriptRoot "ocr-engine\generate_test_fixtures.py") --output $fixtureDir
    if ($LASTEXITCODE -ne 0) { throw "无法生成 OCR 测试夹具" }
    $engine = Join-Path $target "ocr-engine.exe"
    if (-not (Test-Path -LiteralPath $engine)) {
        $engine = Join-Path $target "ocr-engine\ocr-engine.exe"
    }
    if (-not (Test-Path -LiteralPath $engine)) { throw "OCR 归档缺少 ocr-engine.exe" }

    $fixtures = @(
        @{ Path = "ocr-chinese.jpg"; Expected = @("离线") },
        @{ Path = "ocr-scan.pdf"; Expected = @("离线") },
        @{ Path = "ocr-mixed.pdf"; Expected = @("NATIVE_PAGE_KEEP", "离线") }
    )
    foreach ($fixture in $fixtures) {
        $input = Join-Path $fixtureDir $fixture.Path
        $result = Join-Path $target ("result-" + [guid]::NewGuid().ToString("N") + ".txt")
        $process = Start-Process -FilePath $exe -ArgumentList @(
            "--smoke-convert", $input,
            "--smoke-output", $result,
            "--smoke-enable-ocr",
            "--smoke-ocr-engine", $engine
        ) -Wait -PassThru
        if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $result)) {
            throw "桌面 OCR 冒烟失败: $($fixture.Path) (exit $($process.ExitCode))"
        }
        $content = Get-Content -LiteralPath $result -Raw -Encoding UTF8
        if (-not $content.StartsWith("ok")) { throw "桌面 OCR 结果失败: $($fixture.Path)`n$content" }
        foreach ($expected in $fixture.Expected) {
            if (-not $content.Contains($expected)) {
                throw "桌面 OCR 结果缺少预期文本 '$expected': $($fixture.Path)`n$content"
            }
        }
        Write-Host "OK: $($fixture.Path)"
    }
}
finally {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
