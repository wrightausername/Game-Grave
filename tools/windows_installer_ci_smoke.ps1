# Game Grave M5: disposable Windows installer lifecycle smoke.
# CI ONLY. Refuses to run on a human's computer or existing user profile.
# Never scans or touches real game/mod/save locations.
param(
    [Parameter(Mandatory=$true)][string]$SetupPath,
    [Parameter(Mandatory=$true)][string]$BuildManifest
)

$ErrorActionPreference = 'Stop'

if ($env:GITHUB_ACTIONS -ne 'true' -or -not $env:GITHUB_WORKSPACE) {
    throw 'Refusing installer lifecycle test outside an isolated GitHub Actions runner.'
}
$workspace = [IO.Path]::GetFullPath($env:GITHUB_WORKSPACE)
$setup = if ([IO.Path]::IsPathRooted($SetupPath)) {
    [IO.Path]::GetFullPath($SetupPath)
} else {
    [IO.Path]::GetFullPath((Join-Path $workspace $SetupPath))
}
$manifestFile = if ([IO.Path]::IsPathRooted($BuildManifest)) {
    [IO.Path]::GetFullPath($BuildManifest)
} else {
    [IO.Path]::GetFullPath((Join-Path $workspace $BuildManifest))
}
if (-not [IO.File]::Exists($setup) -or -not [IO.File]::Exists($manifestFile)) {
    throw 'Unsigned installer candidate or build manifest not found.'
}
if (-not $setup.StartsWith($workspace + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Installer must come from the current CI checkout.'
}
$report = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
$actualHash = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
if ($report.schema -ne 1 -or $report.product -ne 'Game Grave' -or
    $report.installer -ne [IO.Path]::GetFileName($setup) -or
    $report.installer_sha256 -ne $actualHash -or $report.signed -ne $false -or
    $report.release_approved -ne $false) {
    throw 'Build manifest does not match the actual unsigned candidate.'
}
if ($report.source_commit -ne $env:GITHUB_SHA) {
    throw 'Installer provenance does not match the current CI commit.'
}

$testRoot = Join-Path $workspace '_ci_installer_lifecycle'
if (Test-Path -LiteralPath $testRoot) {
    throw 'Lifecycle fixture directory already exists; refusing to overwrite it.'
}
# Unit tests may legitimately create settings in the ephemeral CI profile.
# Never overwrite them: hash the existing files, create a UNIQUE sentinel
# exclusively, and verify ALL original files remain intact after uninstall.
$profileDir = Join-Path $env:LOCALAPPDATA 'Game Grave'
$priorProfile = @()
if (Test-Path -LiteralPath $profileDir) {
    if ((Get-Item -LiteralPath $profileDir).Attributes -band
        [IO.FileAttributes]::ReparsePoint) {
        throw 'Game Grave profile root is redirected. Refusing smoke test.'
    }
    $priorProfile = @(Get-ChildItem -LiteralPath $profileDir -File -Recurse |
        ForEach-Object {
            [pscustomobject]@{
                Path = $_.FullName
                Hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            }
        })
} else {
    New-Item -ItemType Directory -Path $profileDir | Out-Null
}
New-Item -ItemType Directory -Path $testRoot | Out-Null
$installDir = Join-Path $testRoot 'Disposable Game Grave'
$unrelatedGame = Join-Path $testRoot 'untouched-game-save.bin'
$profileSentinel = Join-Path $profileDir "ci-smoke-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT.txt"
[IO.File]::WriteAllBytes($unrelatedGame, [byte[]](0..255))
$sentinelBytes = [Text.Encoding]::UTF8.GetBytes('settings and receipts must survive uninstall')
$stream = [IO.File]::Open($profileSentinel, [IO.FileMode]::CreateNew,
                         [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $stream.Write($sentinelBytes, 0, $sentinelBytes.Length) }
finally { $stream.Dispose() }
$beforeSave = (Get-FileHash $unrelatedGame -Algorithm SHA256).Hash
$beforeProfile = (Get-FileHash $profileSentinel -Algorithm SHA256).Hash

function Invoke-UnsignedInstaller([string]$label) {
    $logFile = Join-Path $testRoot "$label.log"
    $installerArguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
        '/CURRENTUSER', '/SP-', ('/DIR="' + $installDir + '"'),
        ('/LOG="' + $logFile + '"'))
    # Inno Setup is a GUI-subsystem executable. Invoking it with '&' can
    # return before the installer exits, leaving LASTEXITCODE null.
    $process = Start-Process -FilePath $setup -ArgumentList $installerArguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "$label failed with installer exit code $($process.ExitCode)"
    }
    $installedExe = Join-Path $installDir 'GameGrave.exe'
    if (-not [IO.File]::Exists($installedExe)) {
        throw "$label did not install GameGrave.exe at the isolated destination."
    }
    $bundledExe = Join-Path $workspace 'dist\GameGrave\GameGrave.exe'
    if (-not [IO.File]::Exists($bundledExe)) {
        throw 'Cannot compare installed executable to its PyInstaller build.'
    }
    if ((Get-FileHash $installedExe -Algorithm SHA256).Hash -ne
        (Get-FileHash $bundledExe -Algorithm SHA256).Hash) {
        throw 'Installed app executable differs from packaged build.'
    }
    Write-Host "$label installed expected application bytes."
}

Invoke-UnsignedInstaller 'FirstInstall'
Invoke-UnsignedInstaller 'RepeatInstall'
# This tests repeat install of the SAME version, not cross-version migration.

# Exercise the ACTUAL INSTALLED GUI executable on the ephemeral CI Windows desktop.
# An isolated environment prevents opening or scanning an existing profile.
$profileForLaunch = Join-Path $testRoot 'IsolatedAppProfile'
$localForLaunch = Join-Path $profileForLaunch 'Local'
$roamingForLaunch = Join-Path $profileForLaunch 'Roaming'
New-Item -ItemType Directory -Force $localForLaunch, $roamingForLaunch | Out-Null
$oldLocalAppData = $env:LOCALAPPDATA
$oldAppData = $env:APPDATA
$legacyPath = Join-Path $localForLaunch 'DustOff'
New-Item -ItemType Directory -Force $legacyPath | Out-Null
$legacyFile = Join-Path $legacyPath 'settings.json'
$legacyBytes = [Text.Encoding]::UTF8.GetBytes('{"ui_theme":"light","auto_enabled":false,"scan_on_launch":false}')
[IO.File]::WriteAllBytes($legacyFile, $legacyBytes)
$legacyHash = (Get-FileHash -LiteralPath $legacyFile -Algorithm SHA256).Hash
$appProcess = $null
try {
    $env:LOCALAPPDATA = $localForLaunch
    $env:APPDATA = $roamingForLaunch
    $installedExe = Join-Path $installDir 'GameGrave.exe'
    $appProcess = Start-Process -FilePath $installedExe -WorkingDirectory $installDir -PassThru
    Start-Sleep -Seconds 5
    $appProcess.Refresh()
    if ($appProcess.HasExited) {
        throw "Installed Game Grave app exited during GUI smoke (code $($appProcess.ExitCode))."
    }
    Write-Host 'PASS: installed GUI executable stayed running under disposable local profile.'
} finally {
    if ($null -ne $appProcess) {
        try {
            $appProcess.Refresh()
            if (-not $appProcess.HasExited) {
                Stop-Process -Id $appProcess.Id -Force -ErrorAction Stop
                $appProcess.WaitForExit(10000) | Out-Null
            }
        } catch {
            Write-Host 'QA-only app process exit was not clean; no user files selected.'
        }
    }
    $env:LOCALAPPDATA = $oldLocalAppData
    $env:APPDATA = $oldAppData
}
if ((Get-FileHash -LiteralPath $legacyFile -Algorithm SHA256).Hash -ne $legacyHash) {
    throw 'Installed app changed the legacy preferences during first GUI launch.'
}
Write-Host 'PASS: legacy settings remained byte-identical through actual installed GUI launch.'

$uninstallers = @(Get-ChildItem -LiteralPath $installDir -Filter 'unins*.exe' -File)
if ($uninstallers.Count -ne 1) {
    throw 'Expected precisely one uninstall executable in the CI-only install.'
}
$uninstallProcess = Start-Process -FilePath $uninstallers[0].FullName -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -Wait -PassThru
if ($uninstallProcess.ExitCode -ne 0) {
    throw "Uninstall failed with exit code $($uninstallProcess.ExitCode)"
}
if ([IO.File]::Exists((Join-Path $installDir 'GameGrave.exe'))) {
    throw 'Uninstall left the application executable behind.'
}
if (-not [IO.File]::Exists($unrelatedGame) -or
    (Get-FileHash $unrelatedGame -Algorithm SHA256).Hash -ne $beforeSave) {
    throw 'Uninstall changed unrelated disposable game data.'
}
if (-not [IO.File]::Exists($profileSentinel) -or
    (Get-FileHash $profileSentinel -Algorithm SHA256).Hash -ne $beforeProfile) {
    throw 'Uninstall changed saved local user preferences.'
}
foreach ($previous in $priorProfile) {
    if (-not [IO.File]::Exists($previous.Path) -or
        (Get-FileHash -LiteralPath $previous.Path -Algorithm SHA256).Hash -ne $previous.Hash) {
        throw 'Uninstall changed a preexisting Game Grave settings file.'
    }
}
Write-Host "PASS: $($priorProfile.Count) preexisting profile file(s) retained byte-identically."
Write-Host 'PASS: isolated install, repeat install, uninstall and SHA verification.'
Write-Host 'PASS: disposable game file and user-profile sentinel survived unchanged.'
Write-Host 'This is an unsigned CI install test, NOT an interactive Windows 10/11 release sign-off.'
