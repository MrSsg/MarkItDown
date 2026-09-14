param(
    [switch]$Clean,
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $PSScriptRoot ".venv-build"
$keyFile = if ($env:MARKITDOWN_OCR_PUBLIC_KEYS_FILE) {
    (Resolve-Path -LiteralPath $env:MARKITDOWN_OCR_PUBLIC_KEYS_FILE).Path
} else {
    (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "app\ocr_public_keys.json")).Path
}
if (-not (Test-Path -LiteralPath $keyFile -PathType Leaf)) {
    throw "未找到 OCR 公钥文件: $keyFile"
}
$keyData = Get-Content -LiteralPath $keyFile -Raw -Encoding UTF8 | ConvertFrom-Json
$keyProperties = @($keyData.PSObject.Properties)
if ($keyProperties.Count -eq 0) {
    throw "OCR 公钥文件为空，拒绝构建正式桌面发行版: $keyFile"
}
foreach ($property in $keyProperties) {
    try {
        $keyBytes = [Convert]::FromBase64String([string]$property.Value)
    } catch {
        throw "OCR 公钥不是有效 Base64: $($property.Name)"
    }
    if ($keyBytes.Length -ne 32) {
        throw "OCR Ed25519 公钥长度错误: $($property.Name)"
    }
}

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $PSScriptRoot "dist"
}
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$releaseRoot = Join-Path $OutputRoot ("py312-" + [guid]::NewGuid().ToString("N"))
$previousKeyFile = $env:MARKITDOWN_OCR_PUBLIC_KEYS_FILE
$env:MARKITDOWN_OCR_PUBLIC_KEYS_FILE = $keyFile

if ($Clean -and (Test-Path $venv)) {
    Remove-Item -LiteralPath $venv -Recurse -Force
}

& py -3.12 -m venv $venv
& "$venv\Scripts\python.exe" -m pip install --upgrade pip
& "$venv\Scripts\python.exe" -m pip install -r "$root\requirements.txt" pyinstaller
& "$venv\Scripts\python.exe" -m pip install -e "$root\packages\markitdown[all]"
Push-Location $PSScriptRoot
try {
    & "$venv\Scripts\pyinstaller.exe" build_fast.spec --noconfirm --clean --distpath $releaseRoot
    $releaseDirectory = Join-Path $releaseRoot "MarkItDownDesk-fast"
    $packagedKeyFile = Join-Path $releaseDirectory "_internal\app\ocr_public_keys.json"
    if (-not (Test-Path -LiteralPath $packagedKeyFile -PathType Leaf)) {
        throw "发行版缺少冻结的 OCR 公钥文件: $packagedKeyFile"
    }
    $actualKeyData = Get-Content -LiteralPath $packagedKeyFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $actualProperties = @($actualKeyData.PSObject.Properties)
    if ($actualProperties.Count -ne $keyProperties.Count) {
        throw "发行版内 OCR 公钥与构建输入不一致"
    }
    foreach ($property in $keyProperties) {
        if ([string]$actualKeyData.($property.Name) -ne [string]$property.Value) {
            throw "发行版内 OCR 公钥与构建输入不一致: $($property.Name)"
        }
    }
    $about = Get-Content -LiteralPath (Join-Path $PSScriptRoot "app\__about__.py") -Raw -Encoding UTF8
    $versionMatch = [regex]::Match($about, '__version__\s*=\s*["'']([^"'']+)["'']')
    if (-not $versionMatch.Success) {
        throw "无法读取桌面版本号"
    }
    $metadata = [ordered]@{
        desktop_version = $versionMatch.Groups[1].Value
        public_key_file = "app/ocr_public_keys.json"
        built_at_utc = [DateTime]::UtcNow.ToString("o")
    }
    $metadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $releaseDirectory "build-metadata.json") -Encoding UTF8
    Write-Host "ReleaseDirectory=$releaseDirectory"
} finally {
    if ($null -eq $previousKeyFile) {
        Remove-Item Env:MARKITDOWN_OCR_PUBLIC_KEYS_FILE -ErrorAction SilentlyContinue
    } else {
        $env:MARKITDOWN_OCR_PUBLIC_KEYS_FILE = $previousKeyFile
    }
    Pop-Location
}
