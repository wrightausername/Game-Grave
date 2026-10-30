"""Bounded, read-only ESO/WoW addon descriptor recognition.

A .txt/.toc descriptor identifies a possible addon, not whether it is unused,
installed, safe to delete, or allowed by a game's policy. No archive extraction.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MAX_DESCRIPTOR = 64 * 1024
MAX_CANDIDATES = 30


@dataclass(frozen=True)
class AddonMetadata:
    ecosystem: str
    title: str
    descriptor: str
    dependencies: tuple[str, ...]
    evidence: tuple[str, ...]


def inspect_addon_metadata(path: str | Path) -> AddonMetadata | None:
    """Inspect only a single addon folder and tightly matched descriptor files."""
    target = Path(path)
    folder = target if target.is_dir() else target.parent
    try:
        if folder.is_symlink() or not folder.is_dir():
            return None
        pieces = [part.casefold() for part in folder.parts]
        if "addons" not in pieces:
            return None
        if "elder scrolls online" in pieces:
            ecosystem, suffix = "ESO", ".txt"
        elif "interface" in pieces and ("world of warcraft" in pieces or "wow" in pieces):
            ecosystem, suffix = "World of Warcraft", ".toc"
        else:
            return None
        candidates = [p for p in list(folder.iterdir())[:MAX_CANDIDATES]
                      if p.is_file() and not p.is_symlink() and p.suffix.casefold() == suffix
                      and p.stem.casefold() == folder.name.casefold()]
        if not candidates:
            return None
        desc = candidates[0]
        if desc.stat().st_size > MAX_DESCRIPTOR:
            return None
        fields = {}
        for line in desc.read_text(encoding="utf-8-sig", errors="replace").splitlines()[:350]:
            if not line.startswith("##") or ":" not in line:
                continue
            key, value = line[2:].split(":", 1)
            if key.strip().casefold() in {"title", "dependson", "dependencies", "interface", "apiversion"}:
                fields[key.strip().casefold()] = value.strip()[:160]
        deps = fields.get("dependson", fields.get("dependencies", ""))
        dependencies = tuple(x.strip()[:80] for x in deps.replace(",", " ").split()[:20] if x.strip())
        evidence = [f"Local {ecosystem} descriptor: {desc.name}"]
        if fields.get("apiversion") or fields.get("interface"):
            evidence.append("Declared API/interface version: " +
                            (fields.get("apiversion") or fields["interface"]))
        if dependencies:
            evidence.append("Declared dependencies: " + ", ".join(dependencies[:6]))
        return AddonMetadata(ecosystem, fields.get("title") or folder.name,
                             str(desc), dependencies, tuple(evidence))
    except (OSError, ValueError):
        return None
