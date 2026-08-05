param(
    [string]$OutputRoot = "",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$scriptRoot = $PSScriptRoot
$about = Get-Content -LiteralPath (Join-Path $scriptRoot "app\__about__.py") -Raw -Encoding UTF8
$versionMatch = [regex]::Match($about, '__version__\s*=\s*["'']([^"'']+)["'']')
if (-not $versionMatch.Success) {
    throw "无法读取桌面版本号"
}
$version = $versionMatch.Groups[1].Value

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $scriptRoot "dist\releases"
}
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$buildRoot = Join-Path $OutputRoot ("build-" + [guid]::NewGuid().ToString("N"))
$releaseName = "MarkItDownDesk-fast-v$version-windows-x64"
$releaseDirectory = Join-Path $OutputRoot $releaseName
$archive = Join-Path $OutputRoot "$releaseName.zip"

if (Test-Path -LiteralPath $releaseDirectory) {
    throw "发行目录已存在，为避免覆盖请换一个 OutputRoot: $releaseDirectory"
}
if (Test-Path -LiteralPath $archive) {
    throw "发行压缩包已存在，为避免覆盖请换一个 OutputRoot: $archive"
}

$buildParams = @{ OutputRoot = $buildRoot }
if ($Clean) { $buildParams.Clean = $true }
& (Join-Path $scriptRoot "build_fast.ps1") @buildParams
if ($LASTEXITCODE -ne 0) {
    throw "桌面 PyInstaller 构建失败"
}

$builtRoot = Get-ChildItem -LiteralPath $buildRoot -Directory -Filter "py312-*" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $builtRoot) {
    throw "未找到桌面构建目录"
}
$builtDirectory = Join-Path $builtRoot.FullName "MarkItDownDesk-fast"
if (-not (Test-Path -LiteralPath $builtDirectory -PathType Container)) {
    throw "构建目录缺少 MarkItDownDesk-fast: $builtDirectory"
}

New-Item -ItemType Directory -Force -Path $releaseDirectory | Out-Null
Copy-Item -Path (Join-Path $builtDirectory "*") -Destination $releaseDirectory -Recurse -Force
Compress-Archive -Path $releaseDirectory -DestinationPath $archive -CompressionLevel Optimal

$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
$releaseMetadata = [ordered]@{
    desktop_version = $version
    archive = [IO.Path]::GetFileName($archive)
    sha256 = $hash
    size_bytes = (Get-Item -LiteralPath $archive).Length
}
$releaseMetadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputRoot "$releaseName.json") -Encoding UTF8

Write-Host "ReleaseDirectory=$releaseDirectory"
Write-Host "ReleaseArchive=$archive"
Write-Host "SHA256=$hash"
