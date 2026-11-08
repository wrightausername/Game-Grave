"""Opt-in content analysis for Captures: exact duplicates and visually similar screenshots.

Both read file bytes, so they only run when the user asks. Neither changes anything. Exact duplicates are
identical bytes (SHA-256). Similar images are close by a small perceptual hash and are never called identical.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path
import warnings

from core import _has_reparse_component, is_protected_path
from screenshot_preview import ALLOWED_FORMATS, MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS

MAX_HASH_BYTES = 512 * 1024 ** 2
MAX_SIMILAR_IMAGES = 4000
SIMILAR_DISTANCE = 6


def sha256_of(path, canceled=lambda: False):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            if canceled():
                raise InterruptedError("Analysis canceled")
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicates(captures, canceled=lambda: False, progress=lambda done, total: None):
    """Groups of captures with identical contents: [[key, ...], ...], largest first. Needs two or more files."""
    by_size = defaultdict(list)
    for c in captures:
        if 0 < c.size <= MAX_HASH_BYTES and not _has_reparse_component(Path(c.path)):
            by_size[c.size].append(c)
    candidates = [group for group in by_size.values() if len(group) > 1]
    total = sum(len(group) for group in candidates)
    done, groups = 0, []
    for group in candidates:
        by_hash = defaultdict(list)
        for c in group:
            if canceled():
                raise InterruptedError("Analysis canceled")
            done += 1
            try:
                by_hash[sha256_of(c.path, canceled)].append(c)
            except OSError:
                continue
            if done % 10 == 0:
                progress(done, total)
        groups.extend(sorted(found, key=lambda c: (c.modified, c.path.casefold())) for found in by_hash.values() if len(found) > 1)
    groups.sort(key=lambda g: (-g[0].size * len(g), g[0].path.casefold()))
    return [[c.key for c in g] for g in groups]


def difference_hash(path):
    """64-bit dHash of an image, or None when it cannot be read safely."""
    from PIL import Image
    p = Path(path)
    try:
        if is_protected_path(p, []) or _has_reparse_component(p) or p.stat().st_size > MAX_IMAGE_BYTES:
            return None
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(p) as image:
                if image.format not in ALLOWED_FORMATS or image.width * image.height > MAX_IMAGE_PIXELS:
                    return None
                image.draft("L", (128, 128))
                small = image.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return None
    pixels = list(small.tobytes())
    value = 0
    for row in range(8):
        for col in range(8):
            value = (value << 1) | (pixels[row * 9 + col] > pixels[row * 9 + col + 1])
    return value


def distance(a, b):
    return bin(a ^ b).count("1")


def group_similar(hashes, threshold=SIMILAR_DISTANCE):
    """hashes: {key: int}. Groups of keys within `threshold` bits of one another (single linkage)."""
    parent = {key: key for key in hashes}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    buckets = defaultdict(list)
    for key, value in hashes.items():
        for part in range(8):  # threshold < 8, so similar hashes always share one whole byte
            buckets[(part, (value >> (part * 8)) & 0xFF)].append(key)
    for members in buckets.values():
        for i, first in enumerate(members):
            for second in members[i + 1:]:
                if distance(hashes[first], hashes[second]) <= threshold:
                    parent[find(first)] = find(second)
    groups = defaultdict(list)
    for key in hashes:
        groups[find(key)].append(key)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def find_similar(captures, canceled=lambda: False, progress=lambda done, total: None):
    """Visually similar screenshots: ([[key, ...], ...], images compared). Newest first, bounded."""
    shots = [c for c in captures if c.kind == "Screenshots"][:MAX_SIMILAR_IMAGES]
    hashes = {}
    for index, capture in enumerate(shots, 1):
        if canceled():
            raise InterruptedError("Analysis canceled")
        value = difference_hash(capture.path)
        if value is not None:
            hashes[capture.key] = value
        if index % 10 == 0:
            progress(index, len(shots))
    order = {c.key: i for i, c in enumerate(shots)}
    groups = [sorted(g, key=order.get) for g in group_similar(hashes)]
    groups.sort(key=lambda g: (-len(g), order[g[0]]))
    return groups, len(hashes)
