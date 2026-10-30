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
# Read the version actually embedded in the Inno Setup definition. The old
# hardcoded v2.0 name incorrectly rejected a successfully built v2.4 installer.
$versionLine = Select-String -Path (Join-Path $PSScriptRoot 'installer\GameGrave.iss') `
    -Pattern '^#define MyAppVersion "([^"]+)"
if (-not $versionLine -or $versionLine.Matches.Count -ne 1) {
    throw 'Cannot identify exactly one installer version in GameGrave.iss'
}
$version = $versionLine.Matches[0].Groups[1].Value
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
