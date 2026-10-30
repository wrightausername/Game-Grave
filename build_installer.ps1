# Build an installable Windows setup executable, not a ZIP or Python script.
# Prerequisites: Windows 10/11, Python 3.10+, Inno Setup 6.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host 'Game Grave: running core tests…'
python -m pip install -r build-requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Failed to install Windows build dependencies' }
python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed; refusing installer build' }
Write-Host 'Building standalone app with PyInstaller…'
python -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name GameGrave `
    --hidden-import cryptography.hazmat.primitives.asymmetric.ed25519 `
    launcher.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }

$paths = @(
    $env:ISCC_PATH,
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) }
if (-not $paths) {
    throw 'Inno Setup 6 is required. Install it from https://jrsoftware.org/isinfo.php and rerun this script.'
}
& $paths[0] 'installer\GameGrave.iss'
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed' }
$installer = Join-Path $PSScriptRoot 'release\GameGrave_Setup_v2.0.0.exe'
if (-not (Test-Path $installer)) { throw 'The installer was not produced' }
Write-Host "Installer built: $installer"
Write-Host 'IMPORTANT: This installer is unsigned. Code-sign and QA on real Windows before distributing.'
