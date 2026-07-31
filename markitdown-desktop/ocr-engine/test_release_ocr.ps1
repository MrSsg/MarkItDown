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
    $engine = Join-Path $target "ocr-engine.exe"
    if (-not (Test-Path -LiteralPath $engine -PathType Leaf)) {
        throw "OCR 归档缺少 ocr-engine.exe"
    }

    $health = & $engine --health 2>&1
    if ($LASTEXITCODE -ne 0 -or -not (($health | Out-String) -match '"type": "health"')) {
        throw "OCR 健康检查失败: $($health | Out-String)"
    }

    $image = Resolve-Path (Join-Path $PSScriptRoot "..\..\packages\markitdown\tests\test_files\test_llm.jpg")
    $request = @{ version = "1.0"; request_id = "release-test"; input_path = $image.Path; file_type = "image"; pages = @(); language = "ch" } | ConvertTo-Json -Compress
    $events = $request | & $engine 2>&1
    $eventText = $events | Out-String
    if ($LASTEXITCODE -ne 0 -or $eventText -notmatch '"type": "result"' -or $eventText -notmatch '"request_id": "release-test"') {
        throw "OCR 图像识别回归失败: $eventText"
    }
    Write-Host "OK: OCR 发布归档健康检查与图片识别"
}
finally {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
