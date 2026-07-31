param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $PSScriptRoot ".venv-build"
$releaseRoot = Join-Path $PSScriptRoot ("dist\py312-" + [guid]::NewGuid().ToString("N"))

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
    Write-Host "ReleaseDirectory=$(Join-Path $releaseRoot 'MarkItDownDesk-fast')"
} finally {
    Pop-Location
}
