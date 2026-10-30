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

$compilerCandidates = @(
    $env:ISCC_PATH
    (Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Inno Setup 6\ISCC.exe')
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
)
$iscc = $compilerCandidates | Where-Object { $_ -and (Test-Path $_) } |
    Select-Object -First 1
if (-not $iscc) {
    throw 'Inno Setup 6 is required. Install it from https://jrsoftware.org/isinfo.php and rerun this script.'
}
& $iscc 'installer\GameGrave.iss'
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed' }
# Read the exact version embedded in the Inno Setup definition. Do not
# assume a hardcoded old filename and incorrectly report successful builds as failed.
$definition = Join-Path $PSScriptRoot 'installer\GameGrave.iss'
$versionLines = @(Get-Content -LiteralPath $definition |
    Where-Object { $_.StartsWith('#define MyAppVersion "') })
if ($versionLines.Count -ne 1) {
    throw 'Cannot identify exactly one installer version in GameGrave.iss'
}
$version = ($versionLines[0] -split '"')[1]
if (-not [regex]::IsMatch($version, '\A\d+\.\d+\.\d+\z')) {
    throw 'Installer version must be a strictly numeric three-part version'
}
$installer = Join-Path $PSScriptRoot "release\GameGrave_Setup_v$version.exe"
if (-not (Test-Path $installer)) {
    throw "Inno Setup ran, but the expected versioned installer was not produced: $installer"
}
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLowerInvariant()
$hashFile = Join-Path $PSScriptRoot "release\GameGrave_Setup_v$version.sha256"
("$hash  " + [System.IO.Path]::GetFileName($installer)) |
    Out-File -FilePath $hashFile -Encoding ascii
Write-Host "Unsigned candidate installer built: $installer"
Write-Host "SHA-256 manifest: $hashFile"
Write-Host 'NOT A PRODUCTION RELEASE: Requires Authenticode signing, manual clean-Windows QA and 1.0 release gates.'
