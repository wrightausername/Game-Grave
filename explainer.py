"""Conservative plain-English explanation for a selected local folder."""
from __future__ import annotations
from pathlib import Path

from core import _is_reparse_point, _measured_files, _mod_markers, human_size, safe_scan_root

GUARDED = {"saves", "savegames", "playerprofiles", "worlds", "profiles", "backups", "overwrite"}


def explain_folder(folder: Path) -> str:
    folder = Path(folder)
    if not safe_scan_root(folder) or not folder.is_dir() or _is_reparse_point(folder):
        raise ValueError("Choose an ordinary non-system folder, not a whole drive or linked directory.")
    markers = _mod_markers(folder)
    total, count, truncated = _measured_files([folder], max_files=25000)
    name = folder.name.casefold()
    lines = [f"Location: {folder}", f"Visible file sizes: {human_size(total)} across {count} files" +
             (" (incomplete: scan limit reached)" if truncated else ""),
             "Apparent size is not guaranteed reclaimable space."]
    if markers:
        lines.append("Possible mod signatures: " + ", ".join(name for name, _ in markers[:12]))
    if name in GUARDED or any(bit in name for bit in ("save", "profile", "world")):
        lines.append("PROTECTED CONTENT POSSIBLE: saves, worlds, or profiles may be irreplaceable.")
    elif markers:
        lines.append("Likely game customization data. Active and disabled mod status cannot be verified here.")
    else:
        lines.append("Unidentified folder. No proof it is junk or safe to remove.")
    lines.append("Nothing has been deleted. Use the appropriate launcher/mod manager before removing managed files.")
    return "\n".join(lines)
