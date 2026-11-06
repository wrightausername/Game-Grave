"""Protect unmodified owner photos and the existing safety engines."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

BASELINE = "3d5afa29d336c73de351e63a79e898352addf631"
PHOTO_SOURCE = "25f5955583b3d7a596a8f50cba9cf2bf9b9d17cb"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_ci_temp"))
    parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    assets = root / "gg_desktop/assets/references"
    for commit in (BASELINE, PHOTO_SOURCE):
        if subprocess.run(["git", "cat-file", "-e", commit], cwd=root, capture_output=True).returncode:
            subprocess.run(["git", "fetch", "--no-tags", "--depth=1", "origin", commit], cwd=root, check=True)
    records = json.loads((assets / "locked_photos.json").read_text())
    assert len(records) == 8
    for name, expected in records.items():
        raw = (assets / (name + ".jpg")).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected["sha256"], "Owner photo changed: " + name
        original = subprocess.check_output(["git", "show", PHOTO_SOURCE + ":gg_desktop/assets/references/" + name + ".jpg"], cwd=root)
        assert raw == original, "Owner photo differs from its original upload: " + name
    for path in ("core.py", "cleanup_actions.py", "recovery.py", "graveyard.py", "graveyard_protection.py",
                 "manager_profiles.py", "mod_sources.py", "gg_desktop/mods_data.py", "gg_desktop/mod_conflicts.py",
                 "gg_desktop/game_artwork.py", "gg_desktop/games_data.py", "gg_desktop/old_files_data.py",
                 "gg_desktop/ready_room_actions.py", "gg_desktop/ready_room_data.py", "gg_desktop/ready_room_services.py"):
        original = subprocess.check_output(["git", "show", BASELINE + ":" + path], cwd=root).decode("utf-8").replace("\r\n", "\n")
        assert (root / path).read_text(encoding="utf-8") == original, "Safety/data engine changed: " + path
    print("PASS: Eight original owner photos are unchanged; scanning, protection, recovery, artwork, mod evidence and Ready Room data engines match the tested baseline. Visual layout is checked against the photos by photo_ui_smoke and actual render review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
