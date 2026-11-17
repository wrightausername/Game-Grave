"""The Recycle Bin promise, on the real Windows Recycle Bin.

1. A real round trip: a test file goes to the Recycle Bin through Game Grave's own recycle path and comes back through
   its own restore path.
2. A file bigger than the drive's Recycle Bin limit: Windows would delete it for good. Game Grave must refuse instead
   (it must never silently fall back to a permanent delete).
3. The drive's "Don't move files to the Recycle Bin" setting: Game Grave must refuse.
Only files this check made in its own folder are ever passed to Windows. The drive's Recycle Bin settings are put back.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import uuid
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rw_common as rw  # noqa: E402

BITBUCKET = r"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume"


def volume_guid(path: Path) -> str:
    buf = ctypes.create_unicode_buffer(64)
    if not ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(str(Path(path.anchor)), buf, 64):
        raise OSError("volume name not found")
    name = buf.value                                  # \\?\Volume{guid}\
    return name[name.index("{"):name.index("}") + 1]


class BinSettings:
    """Sets this drive's Recycle Bin limit / delete-at-once switch for the test and puts the old values back."""

    def __init__(self, guid):
        self.key = BITBUCKET + "\\" + guid
        self.saved = {}

    def __enter__(self):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.key, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
            for name in ("MaxCapacity", "NukeOnDelete"):
                try:
                    self.saved[name] = winreg.QueryValueEx(k, name)
                except OSError:
                    self.saved[name] = None
        return self

    def set(self, **values):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.key, 0, winreg.KEY_WRITE) as k:
            for name, value in values.items():
                winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, int(value))

    def __exit__(self, *_):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.key, 0, winreg.KEY_WRITE) as k:
            for name, old in self.saved.items():
                if old is None:
                    try:
                        winreg.DeleteValue(k, name)
                    except OSError:
                        pass
                else:
                    winreg.SetValueEx(k, name, 0, old[1], old[0])


def in_bin(path: Path) -> str:
    import recovery
    return recovery._run_ps(recovery._bin_script(str(path)))


def make(folder: Path, size: int) -> Path:
    path = folder / f"gg-rw-{uuid.uuid4().hex[:8]}.bin"
    with open(path, "wb") as f:
        f.write(os.urandom(min(size, 1 << 20)))
        if size > 1 << 20:
            f.seek(size - 1)
            f.write(b"\0")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_ci_temp/realworld"))
    parser.add_argument("--case", choices=("round", "big", "nuke"))
    args = parser.parse_args()
    if args.case is None:
        # Each case in its own process: Windows reads a drive's Recycle Bin settings once per process.
        codes = [subprocess.call([sys.executable, __file__, "--output", str(args.output), "--case", c])
                 for c in ("round", "big", "nuke")]
        return 0 if not any(codes) else 1
    scratch = rw.isolate("GG-rw-recycle-")
    rep = rw.Report("recycle-real-" + args.case, args.output)
    import core
    import recovery
    folder = scratch / "Test files"
    folder.mkdir()
    guid = volume_guid(folder)
    rep.note("drive under test", drive=folder.anchor, volume=guid)

    # 1. Round trip through Game Grave's own paths
    def round_trip():
        f = make(folder, 4096)
        size = f.stat().st_size
        core.recycle_file(f)
        gone = not f.exists()
        where = in_bin(f)
        event = recovery.register_recycle(f, size, "Real-world check")
        state = recovery.check_restore(event)
        back = recovery.restore(event)
        rep.check("a recycled file is in the Recycle Bin and comes back", gone and where == "AVAILABLE" and f.exists(),
                  gone=gone, in_bin=where, check=state, restore=back, back=f.exists())
    if args.case == "round":
        rw.guarded(rep, "round trip", round_trip)

    # 2. Bigger than the drive's Recycle Bin limit
    def too_big():
        with BinSettings(guid) as bin_:
            bin_.set(MaxCapacity=1, NukeOnDelete=0)            # 1 MB limit for this test
            f = make(folder, 8 * 1024 * 1024)
            try:
                core.recycle_file(f)
                refused = None
            except Exception as exc:
                refused = f"{type(exc).__name__}: {exc}"
            exists = f.exists()
            where = "" if exists else in_bin(f)
            lost = not exists and where != "AVAILABLE"
            rep.check("a file bigger than the Recycle Bin is refused, never deleted for good", exists and not lost,
                      refused=refused, still_there=exists, in_bin=where, permanently_deleted=lost)
            if exists:
                f.unlink()
    if args.case == "big":
        rw.guarded(rep, "too big for the Recycle Bin", too_big)

    # 3. "Don't move files to the Recycle Bin" switched on for the drive
    def nuke():
        with BinSettings(guid) as bin_:
            bin_.set(NukeOnDelete=1)
            f = make(folder, 4096)
            try:
                core.recycle_file(f)
                refused = None
            except Exception as exc:
                refused = f"{type(exc).__name__}: {exc}"
            exists = f.exists()
            where = "" if exists else in_bin(f)
            rep.check("with the Recycle Bin switched off for the drive, nothing is deleted", exists,
                      refused=refused, still_there=exists, in_bin=where)
            if exists:
                f.unlink()
    if args.case == "nuke":
        rw.guarded(rep, "Recycle Bin off", nuke)
    return rep.finish()


if __name__ == "__main__":
    raise SystemExit(main())
