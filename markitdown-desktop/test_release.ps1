param(
    [string]$ReleaseDirectory = ""
)

$ErrorActionPreference = "Stop"
if (-not $ReleaseDirectory) {
    $latest = Get-ChildItem (Join-Path $PSScriptRoot "dist") -Directory -Filter "py312-*" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latest) { throw "未找到 Python 3.12 发行目录" }
    $ReleaseDirectory = Join-Path $latest.FullName "MarkItDownDesk-fast"
}
$exe = Join-Path $ReleaseDirectory "MarkItDownDesk-fast.exe"
if (-not (Test-Path $exe)) { throw "未找到发行版 EXE: $exe" }

$fixtures = @(
    @{ Path = "..\packages\markitdown\tests\test_files\test.pdf"; Expected = "Introduction" },
    @{ Path = "..\packages\markitdown\tests\test_files\test.docx"; Expected = "AutoGen" },
    @{ Path = "..\packages\markitdown\tests\test_files\test.xlsx"; Expected = "Sheet1" },
    @{ Path = "..\packages\markitdown\tests\test_files\test.jpg"; Expected = "" }
)
foreach ($fixture in $fixtures) {
    $input = Join-Path $PSScriptRoot $fixture.Path
    $result = Join-Path $env:TEMP ("markitdown-smoke-" + [guid]::NewGuid().ToString("N") + ".txt")
    $process = Start-Process -FilePath $exe -ArgumentList @("--smoke-convert", $input, "--smoke-output", $result) -Wait -PassThru
    if (-not (Test-Path $result)) {
        throw "发行版未写入冒烟结果: $input (exit $($process.ExitCode))"
    }
    $content = Get-Content -LiteralPath $result -Raw
    Remove-Item -LiteralPath $result -Force
    if (-not $content.StartsWith("ok")) {
        throw "发行版转换失败: $input`n$content"
    }
    if ($fixture.Expected -and -not $content.ToLowerInvariant().Contains($fixture.Expected.ToLowerInvariant())) {
        throw "发行版结果缺少预期文本 '$($fixture.Expected)': $input`n$content"
    }
    Write-Host "OK: $($fixture.Path)"
}
