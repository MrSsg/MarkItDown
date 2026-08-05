param(
    [string]$Archive = (Join-Path $PSScriptRoot "dist\ocr-engine.zip")
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
    throw "OCR 发布归档不存在: $Archive"
}

$target = Join-Path ([System.IO.Path]::GetTempPath()) ("markitdown-ocr-test-" + [guid]::NewGuid().ToString("N"))
try {
    Expand-Archive -LiteralPath $Archive -DestinationPath $target -Force
    $fixtureDir = Join-Path $target "fixtures"
    $python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    & $python (Join-Path $PSScriptRoot "generate_test_fixtures.py") --output $fixtureDir
    if ($LASTEXITCODE -ne 0) { throw "无法生成 OCR 测试夹具" }
    $sample = (Resolve-Path (Join-Path $PSScriptRoot "..\..\packages\markitdown\tests\test_files\test_llm.jpg")).Path
    & $python (Join-Path $PSScriptRoot "verify_release_engine.py") --engine (Join-Path $target "ocr-engine.exe") --sample-image $sample --fixture-dir $fixtureDir
    if ($LASTEXITCODE -ne 0) { throw "OCR 发布归档验收失败" }
}
finally {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
