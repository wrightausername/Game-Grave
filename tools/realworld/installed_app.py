"""The real installed program, the way a person gets it: install, first launch, upgrade over the previous version,
Windows Defender scan, uninstall.

1. If the previous preview installer is given, it is installed first and settings a person would have (two chats, a
   note, a Never Touch rule, a scan folder) are written the way that version keeps them.
2. The new installer runs silently over it. The installed EXE (not the source) is started with --self-check, which
   imports every part, scans once, opens every tab with a picture each, and writes its report.
3. Settings from before the upgrade must still be there, byte for byte where nothing needed changing.
4. Windows Defender scans the installed folder and the installer.
5. Uninstall: the program goes, the person's settings stay.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rw_common as rw  # noqa: E402

EXE = "GameGrave-Crimson-Preview.exe"


def install(setup: Path, folder: Path):
    done = subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={folder}",
                           f"/LOG={folder.parent / (setup.stem + '-install.log')}"], timeout=600)
    return done.returncode


def seed(settings_file: Path):
    now = time.time()
    data = json.loads(settings_file.read_text(encoding="utf-8")) if settings_file.is_file() else {}
    data.update({
        "assistant_chats": [
            {"id": "chat-one", "title": "Why does Skyrim crash", "updated": now - 3600,
             "messages": [{"role": "user", "text": "why does skyrim crash"},
                          {"role": "assistant", "text": "Crash Doctor can find the mod causing it."}]},
            {"id": "chat-two", "title": "Free up space", "updated": now - 7200,
             "messages": [{"role": "user", "text": "free up space"}, {"role": "assistant", "text": "Here's a plan."}]},
        ],
        "assistant_notes": [{"when": now - 100, "text": "I play on a laptop, keep things light."}],
        "never_touch": ["C:\\Users\\Keep\\My Mods"],
        "files_stale_days": 240,
    })
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def defender(paths):
    exe = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Windows Defender" / "MpCmdRun.exe"
    if not exe.is_file():
        return None, "Windows Defender's scanner isn't on this machine"
    results = []
    for path in paths:
        done = subprocess.run([str(exe), "-Scan", "-ScanType", "3", "-File", str(path), "-DisableRemediation"],
                              capture_output=True, text=True, timeout=1800)
        results.append({"path": str(path), "code": done.returncode, "said": (done.stdout + done.stderr)[-600:]})
    return results, ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_ci_temp/realworld"))
    parser.add_argument("--setup", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    rep = rw.Report("installed-app", args.output)
    local = Path(os.environ["LOCALAPPDATA"])
    folder = local / "Programs" / "Game Grave Crimson Preview"
    settings_file = local / "Game Grave" / "settings.json"
    seeded = None

    if args.previous and args.previous.is_file():
        code = install(args.previous, folder)
        rep.check("the previous version installs", code == 0 and (folder / EXE).is_file(), exit_code=code)
        seeded = seed(settings_file)
        rep.note("settings from the previous version", chats=2, notes=1, file=str(settings_file))
    else:
        rep.note("no previous installer to upgrade from; installing fresh")

    code = install(args.setup, folder)
    rep.check("the new version installs silently" + (" over the previous one" if seeded else ""),
              code == 0 and (folder / EXE).is_file(), exit_code=code)
    entry = subprocess.run(["reg", "query", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall", "/s", "/f",
                            "Game Grave Crimson Preview"], capture_output=True, text=True)
    rep.check("it appears in Installed apps", "Game Grave Crimson Preview" in entry.stdout,
              version=[l.strip() for l in entry.stdout.splitlines() if "DisplayVersion" in l][:1])

    report_dir = args.output / "self-check"
    if report_dir.exists():
        shutil.rmtree(report_dir)
    started = time.time()
    try:
        done = subprocess.run([str(folder / EXE), "--self-check", str(report_dir)], timeout=1500,
                              env=dict(os.environ, GAME_GRAVE_TRAY="0"))
        code = done.returncode
    except subprocess.TimeoutExpired:
        code = "timed out"
    data = {}
    if (report_dir / "self-check.json").is_file():
        data = json.loads((report_dir / "self-check.json").read_text(encoding="utf-8"))
    rep.check("the installed program starts, scans and opens every tab (its own self-check)", code == 0 and data.get("passed"),
              exit_code=code, minutes=round((time.time() - started) / 60, 1),
              failed=[s for s in data.get("steps", []) if not s.get("ok")], errors=data.get("errors", [])[:3],
              app_errors=data.get("app_errors", [])[:5])
    for s in data.get("steps", []):
        rep.note("self-check: " + s.get("step", ""), **{k: v for k, v in s.items() if k not in ("step",)})

    if seeded:
        after = json.loads(settings_file.read_text(encoding="utf-8")) if settings_file.is_file() else {}
        kept = {k: after.get(k) == v for k, v in seeded.items()
                if k in ("assistant_notes", "never_touch", "files_stale_days")}
        chats = {c.get("id") for c in after.get("assistant_chats", []) if isinstance(c, dict)}
        rep.check("chats, notes, Never Touch and settings survive the upgrade", all(kept.values())
                  and {"chat-one", "chat-two"} <= chats, kept=kept, chats=sorted(chats))
        step = next((s for s in data.get("steps", []) if s.get("step") == "settings kept"), {})
        rep.check("the upgraded program sees the old chats and note", step.get("chats", 0) >= 2 and step.get("notes", 0) >= 1,
                  seen=step)

    results, why = defender([folder, args.setup])
    if results is None:
        rep.note("Defender scan skipped", why=why)
    else:
        rep.check("Windows Defender finds nothing in the installed program or the installer",
                  all(r["code"] == 0 for r in results), results=results)

    unins = folder / "unins000.exe"
    done = subprocess.run([str(unins), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=600)
    for _ in range(30):                      # the uninstaller finishes in a copy of itself
        if not (folder / EXE).exists():
            break
        time.sleep(1)
    rep.check("uninstall removes the program", done.returncode == 0 and not (folder / EXE).exists(),
              exit_code=done.returncode)
    rep.check("uninstall keeps the person's settings", settings_file.is_file())
    return rep.finish()


if __name__ == "__main__":
    raise SystemExit(main())
