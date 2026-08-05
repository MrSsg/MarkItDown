param(
    [string]$ReleaseDirectory = ""
)

$ErrorActionPreference = "Stop"
if (-not $ReleaseDirectory) {
    $distRoot = Join-Path $PSScriptRoot "dist"
    $latest = Get-ChildItem $distRoot -Directory -Filter "MarkItDownDesk-fast-v*-windows-x64" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latest) {
        $latest = Get-ChildItem $distRoot -Directory -Filter "py312-*" |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($latest) {
            $latest = Get-Item (Join-Path $latest.FullName "MarkItDownDesk-fast")
        }
    }
    if (-not $latest) { throw "未找到桌面发行目录" }
    $ReleaseDirectory = $latest.FullName
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
    if ($process.ExitCode -ne 0) {
        throw "发行版进程退出失败: $input (exit $($process.ExitCode))`n$content"
    }
    if (-not $content.StartsWith("ok")) {
        throw "发行版转换失败: $input`n$content"
    }
    if (-not $content.Substring(2).Trim()) {
        throw "发行版结果为空: $input"
    }
    if ($fixture.Expected -and -not $content.ToLowerInvariant().Contains($fixture.Expected.ToLowerInvariant())) {
        throw "发行版结果缺少预期文本 '$($fixture.Expected)': $input`n$content"
    }
    Write-Host "OK: $($fixture.Path)"
}
