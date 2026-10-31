"""User-requested, bounded screenshot decode, never triggered during PC scanning.

Image bytes stay on device and are decoded only after an individual user clicks
Preview. Never follows links, opens oversized files, produces cached thumbnails
or initiates deletion. Return a Pillow image to be converted to a Tk photo on
the UI thread.
"""
from __future__ import annotations

import warnings
from pathlib import Path

from core import OldFile, _has_reparse_component, is_unchanged, is_protected_path
from screenshots import looks_like_screenshot

MAX_IMAGE_BYTES = 80 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
PREVIEW_SIZE = (920, 560)
ALLOWED_FORMATS = frozenset({"PNG", "JPEG", "WEBP", "BMP"})


def decode_screenshot_preview(record: OldFile):
    """Return a small image from an unchanged, ordinary screenshot candidate."""
    path = Path(record.path)
    if (not looks_like_screenshot(path) or _has_reparse_component(path)
            or is_protected_path(path, [])
            or record.size < 1 or record.size > MAX_IMAGE_BYTES
            or not is_unchanged(record)):
        raise ValueError("Image was protected, changed or exceeds the safe preview size.")
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise ValueError(
            "Image preview needs Pillow. Install it for source runs; "
            "it is bundled in the Windows application.") from exc
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                if source.format not in ALLOWED_FORMATS:
                    raise ValueError("File contents are not a supported screenshot image.")
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image resolution exceeds the safe preview limit.")
                frame = ImageOps.exif_transpose(source)
                frame.thumbnail(PREVIEW_SIZE, Image.Resampling.LANCZOS)
                preview = frame.convert("RGB").copy()
        if not is_unchanged(record):
            raise ValueError("Image changed during preview; scan again.")
        return preview
    except (OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError("Image could not be safely decoded for preview.") from exc
