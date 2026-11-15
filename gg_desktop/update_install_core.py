"""Qt-free parts of installing an update from inside Game Grave. The download, size check and SHA-256 check are the
Updater's own functions (`updater/gg_updater.py`); this module only words the questions and writes the small script
that runs the verified installer after Game Grave closes, records the installed build, and opens Game Grave again.
"""
from __future__ import annotations

import re

TAG = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
INSTALL_ARGS = ("/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS")


class UpdateInstallError(ValueError):
    pass


def download_question(tag, megabytes):
    return (f"Download Game Grave {tag} ({megabytes:.0f} MB) from this project's GitHub releases?\n\n"
            "It is checked against the SHA-256 published with the build and thrown away if it does not match. Nothing "
            "is installed yet: you are asked again before the installer runs.")


def install_question(tag):
    return (f"Install Game Grave {tag} now?\n\n"
            "What happens: Game Grave closes, the verified installer runs ("
            + " ".join(INSTALL_ARGS) + ") and replaces the Game Grave program files, the build is recorded as installed, "
            "and Game Grave opens again. Your games, mods, captures and Game Grave's settings and history are not touched. "
            "Windows may ask to allow the installer.")


def _ps(value):
    return "'" + str(value).replace("'", "''") + "'"


def install_script(setup_path, tag, state_file, exe_path):
    """PowerShell run after Game Grave closes. Only an installer that exits 0 is recorded as installed."""
    if not TAG.match(str(tag)):
        raise UpdateInstallError("The build name has characters Game Grave will not pass on.")
    args = ",".join(_ps(a) for a in INSTALL_ARGS)
    return "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"$setup = {_ps(setup_path)}; $state = {_ps(state_file)}; $exe = {_ps(exe_path)}; $tag = {_ps(tag)}",
        "Start-Sleep -Seconds 2",
        f"$p = Start-Process -FilePath $setup -ArgumentList {args} -Wait -PassThru",
        "if ($p.ExitCode -eq 0) {",
        "  New-Item -ItemType Directory -Force -Path (Split-Path $state) | Out-Null",
        "  $data = @{}",
        "  if (Test-Path -LiteralPath $state) { try { (Get-Content -LiteralPath $state -Raw | ConvertFrom-Json).psobject.properties"
        " | ForEach-Object { $data[$_.Name] = $_.Value } } catch {} }",
        "  $data['installed_tag'] = $tag",
        "  [IO.File]::WriteAllText($state, ($data | ConvertTo-Json))",
        "  Remove-Item -LiteralPath $setup -Force -ErrorAction SilentlyContinue",
        "}",
        "if (Test-Path -LiteralPath $exe) { Start-Process -FilePath $exe }",
    ])


def progress_text(done, total):
    return "Downloading the update: %.0f of %.0f MB" % (done / 1048576, max(total, 1) / 1048576)
