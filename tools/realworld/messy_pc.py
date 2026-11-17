"""Messy PCs, on real Windows: an accented user name with spaces, very long paths, a drive that vanishes, Documents
moved to OneDrive, locked files, read-only files, and no internet. Only this check's own files are touched; the one
Windows setting it changes (where Documents lives) is put back at the end.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rw_common as rw  # noqa: E402

OLD = time.time() - 400 * 86400
SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"


def old(path: Path, data=b"old test file"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (OLD, OLD))
    return path


def free_letter():
    used = ctypes.windll.kernel32.GetLogicalDrives()
    return next(chr(65 + i) for i in range(25, 3, -1) if not used & (1 << i))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_ci_temp/realworld"))
    parser.add_argument("--child-saves", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child_saves:                       # a fresh process, so Windows' Documents answer is read fresh
        sys.path.insert(0, str(rw.ROOT))
        import save_discovery
        from gg_desktop import other_storage_data
        saves = [s.path for s in save_discovery.discover_saves()]
        spots = [str(s.path) for s in other_storage_data.known_spots() if s.name == "My Games"]
        Path(args.child_saves).write_text(json.dumps({"saves": saves, "my_games": spots,
                                                      "docs": [str(d) for d in save_discovery.documents_folders()]}))
        return 0

    scratch = rw.isolate("GG-rw-messy-")
    rep = rw.Report("messy-pc", args.output)
    import core
    import recovery

    # 1. Accented user name with spaces
    def accented():
        user = scratch / "José Müller-Ñúñez 李" / "Downloads"
        f = old(user / "Ünïcödé setup (1).zip")
        os.environ["LOCALAPPDATA"] = str(scratch / "José Müller-Ñúñez 李" / "AppData" / "Local")
        Path(os.environ["LOCALAPPDATA"]).mkdir(parents=True, exist_ok=True)
        settings = core.load_settings()
        settings["scan_folder"] = str(user)
        core.save_settings(settings)
        back = core.load_settings().get("scan_folder")
        rep.check("settings save and load under an accented user folder", back == str(user), back=back,
                  config=str(core.config_dir()))
        found = [Path(x.path).name for x in core.scan_old_files(user, 180)]
        rep.check("old files are found under an accented path", f.name in found, found=found)
        size = f.stat().st_size
        core.recycle_file(f)
        event = recovery.register_recycle(f, size, "Real-world check")
        restored = recovery.restore(event)
        rep.check("an accented file goes to the Recycle Bin and comes back", f.exists(), restore=restored)
    rw.guarded(rep, "accented user name", accented)

    # 2. Very long paths
    def long_paths():
        deep = Path("\\\\?\\" + str(scratch / "Long" / ("a very long folder name for testing " * 3).strip()
                                    / ("another long folder name here " * 3).strip()
                                    / ("and one more long folder name " * 3).strip()))
        f = old(deep / (("long_file_name_" * 6) + ".zip"))
        plain = Path(str(f)[4:])
        rep.note("long path made", length=len(str(plain)))
        try:
            found = [x.path for x in core.scan_old_files(scratch / "Long", 180)]
            rep.check("a scan through very long paths finishes", True, found=len(found))
        except Exception as exc:
            rep.check("a scan through very long paths finishes", False, error=f"{type(exc).__name__}: {exc}")
        try:
            core.recycle_file(plain)
            outcome = "recycled"
        except (ValueError, RuntimeError, OSError) as exc:
            outcome = f"refused: {exc}"
        rep.check("an over-long path is refused or recycled, never lost", f.exists() or outcome == "recycled",
                  outcome=outcome[:200], still_there=f.exists())
    rw.guarded(rep, "long paths", long_paths)

    # 3. A drive that vanishes (subst letter removed between the scan and the clean)
    def vanishing():
        target = scratch / "USB stick"
        f = old(target / "Downloads" / "old.zip")
        letter = free_letter()
        subprocess.run(["subst", f"{letter}:", str(target)], check=True)
        try:
            files = core.scan_old_files(Path(f"{letter}:\\Downloads"), 180)
            rep.check("a scan on the extra drive works", len(files) == 1, found=len(files))
        finally:
            subprocess.run(["subst", f"{letter}:", "/d"], check=False)
        try:
            core.recycle_file(Path(f"{letter}:\\Downloads\\old.zip"))
            outcome = "recycled"
        except Exception as exc:
            outcome = f"refused: {type(exc).__name__}: {exc}"
        rep.check("cleaning a file on a drive that's gone stops with a message, nothing lost",
                  outcome.startswith("refused") and f.exists(), outcome=outcome[:200])
        unchanged = core.is_unchanged(files[0]) if files else None
        rep.check("the vanished file is no longer offered as unchanged", unchanged is False, unchanged=unchanged)
        from gg_desktop.backend import Inventory, scan_inventory
        settings = dict(core.default_settings(), scan_folder=f"{letter}:\\Downloads")
        inv = scan_inventory(settings, lambda: False, parts={"files"}, base=Inventory())
        rep.check("a scan whose folder is gone finishes with a plain warning", any("Old Files" in w for w in inv.warnings),
                  warnings=inv.warnings)
    rw.guarded(rep, "vanishing drive", vanishing)

    # 4. Documents moved to OneDrive (a work account folder name, the hardest kind)
    def onedrive():
        home = Path(os.environ.get("USERPROFILE"))
        moved = scratch / "OneDrive - Contoso Ltd" / "Documents"
        (moved / "My Games" / "Skyrim Special Edition" / "Saves").mkdir(parents=True)
        (moved / "My Games" / "Skyrim Special Edition" / "Saves" / "Save 1.ess").write_bytes(b"save")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SHELL_FOLDERS, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
            saved = winreg.QueryValueEx(k, "Personal")
            winreg.SetValueEx(k, "Personal", 0, winreg.REG_EXPAND_SZ, str(moved))
        try:
            out = scratch / "child.json"
            subprocess.run([sys.executable, __file__, "--child-saves", str(out)], check=True, timeout=120)
            data = json.loads(out.read_text())
        finally:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SHELL_FOLDERS, 0, winreg.KEY_WRITE) as k:
                winreg.SetValueEx(k, "Personal", 0, saved[1], saved[0])
        game = str(moved / "My Games" / "Skyrim Special Edition").casefold()
        rep.check("saves in a moved Documents folder are found and protected",
                  any(s.casefold() == game for s in data["saves"]), docs=data["docs"][:4], saves=data["saves"][:6])
        rep.check("Other Storage shows the moved My Games folder",
                  any(s.casefold() == str(moved / "My Games").casefold() for s in data["my_games"]), my_games=data["my_games"])
        rep.check("a moved Documents counts as protected", core.is_protected_path(
            moved / "My Games" / "Skyrim Special Edition" / "Saves" / "Save 1.ess"))
        rep.note("home", home=str(home))
    rw.guarded(rep, "OneDrive Documents", onedrive)

    # 5. A locked file (another program has it open with no sharing)
    def locked():
        f = old(scratch / "Locked" / "in use.log")
        GENERIC_READ, OPEN_EXISTING = 0x80000000, 3
        k32 = ctypes.windll.kernel32
        k32.CreateFileW.restype = ctypes.c_void_p
        handle = k32.CreateFileW(str(f), GENERIC_READ, 0, None, OPEN_EXISTING, 0, None)
        try:
            try:
                core.recycle_file(f)
                outcome = "recycled"
            except Exception as exc:
                outcome = f"refused: {type(exc).__name__}: {exc}"
            rep.check("a file another program has locked is left alone with a message", f.exists()
                      and outcome.startswith("refused"), outcome=outcome[:200])
        finally:
            k32.CloseHandle(ctypes.c_void_p(handle))
    rw.guarded(rep, "locked file", locked)

    # 6. A read-only file
    def read_only():
        import stat
        f = old(scratch / "ReadOnly" / "kept.zip")
        os.chmod(f, stat.S_IREAD)
        size = f.stat().st_size
        try:
            core.recycle_file(f)
            outcome = "recycled"
        except Exception as exc:
            outcome = f"refused: {type(exc).__name__}: {exc}"
        where = recovery._run_ps(recovery._bin_script(str(f))) if not f.exists() else ""
        rep.check("a read-only file is either recycled (and restorable) or left alone, never lost",
                  f.exists() or where == "AVAILABLE", outcome=outcome[:200], in_bin=where)
        if not f.exists():
            event = recovery.register_recycle(f, size, "Real-world check")
            recovery.restore(event)
        if f.exists():
            os.chmod(f, stat.S_IREAD | stat.S_IWRITE)
    rw.guarded(rep, "read-only file", read_only)

    # 7. No internet: everything that reaches out fails quickly and politely
    def offline():
        dead = "http://127.0.0.1:9"
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ[name] = dead
        from types import SimpleNamespace
        from gg_desktop import game_artwork
        import updates
        started = time.time()
        try:
            game = SimpleNamespace(name="Skyrim Special Edition", key="steam:489830", steam_id="489830",
                                   appid="489830", install_path="", source="Steam")
            art = game_artwork.official_artwork(game, steam_id="489830")
            art_outcome = f"returned {type(art).__name__}"
        except Exception as exc:
            art_outcome = f"{type(exc).__name__}: {exc}"
        art_time = time.time() - started
        rep.check("game pictures with no internet give up in under 30 seconds", art_time < 30,
                  seconds=round(art_time, 1), outcome=art_outcome[:200])
        started = time.time()
        try:
            result = updates.check_for_updates()
            upd = f"returned {str(result)[:120]}"
        except Exception as exc:
            upd = f"{type(exc).__name__}: {exc}"
        rep.check("the update check with no internet gives up in under 30 seconds", time.time() - started < 30,
                  seconds=round(time.time() - started, 1), outcome=upd[:200])
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(name, None)
    rw.guarded(rep, "no internet", offline)
    return rep.finish()


if __name__ == "__main__":
    raise SystemExit(main())
