param(
    [string]$Archive = (Join-Path $PSScriptRoot "dist\ocr-engine.zip"),
    [string]$Manifest = (Join-Path $PSScriptRoot "dist\ocr-engine-manifest.json")
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
    throw "OCR 发布归档不存在: $Archive"
}
if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) {
    throw "OCR 发布清单不存在: $Manifest"
}
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $python (Join-Path $PSScriptRoot "validate_manifest.py") `
    --manifest $Manifest --archive $Archive `
    --public-key-file (Resolve-Path (Join-Path $PSScriptRoot "ocr_public_keys.json")) `
    --require-release-url
if ($LASTEXITCODE -ne 0) { throw "OCR 发布清单验签失败" }

$target = Join-Path ([System.IO.Path]::GetTempPath()) ("markitdown-ocr-test-" + [guid]::NewGuid().ToString("N"))
try {
    Expand-Archive -LiteralPath $Archive -DestinationPath $target -Force
    $fixtureDir = Join-Path $target "fixtures"
    & $python (Join-Path $PSScriptRoot "generate_test_fixtures.py") --output $fixtureDir
    if ($LASTEXITCODE -ne 0) { throw "无法生成 OCR 测试夹具" }
    $sample = (Resolve-Path (Join-Path $PSScriptRoot "tests\sample.jpg")).Path
    & $python (Join-Path $PSScriptRoot "verify_release_engine.py") --engine (Join-Path $target "ocr-engine.exe") --sample-image $sample --fixture-dir $fixtureDir
    if ($LASTEXITCODE -ne 0) { throw "OCR 发布归档验收失败" }
}
finally {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
