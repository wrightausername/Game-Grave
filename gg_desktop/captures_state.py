"""Capture tags: a small private JSON file next to the settings. Tags never touch the captures themselves."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from core import _has_reparse_component, config_dir

MAX_TAG = 24
MAX_TAGS_PER_CAPTURE = 12
MAX_ENTRIES = 20_000


def tags_file():
    return config_dir() / "capture_tags.json"


def clean_tag(text):
    tag = " ".join(str(text).split())[:MAX_TAG]
    if not tag or any(ord(ch) < 32 for ch in tag):
        raise ValueError("Enter a tag of up to 24 letters, numbers or spaces.")
    return tag


def load_tags(path=None):
    path = Path(path) if path else tags_file()
    try:
        if not path.is_file() or _has_reparse_component(path) or path.stat().st_size > 8 * 1024 ** 2:
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    output = {}
    for key, values in list(raw.items())[:MAX_ENTRIES]:
        if isinstance(key, str) and isinstance(values, list):
            clean = []
            for value in values[:MAX_TAGS_PER_CAPTURE]:
                try:
                    clean.append(clean_tag(value))
                except ValueError:
                    continue
            if clean:
                output[key] = sorted(set(clean), key=str.casefold)
    return output


def save_tags(tags, path=None):
    path = Path(path) if path else tags_file()
    if len(tags) > MAX_ENTRIES:
        raise ValueError("Too many tagged captures.")
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    if _has_reparse_component(directory):
        raise ValueError("The settings folder is linked or redirected.")
    payload = json.dumps({k: v for k, v in tags.items() if v}, indent=1, ensure_ascii=False).encode("utf-8")
    fd, raw = tempfile.mkstemp(prefix=".gg-tags-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(raw, path)
    except OSError:
        try:
            os.unlink(raw)
        except OSError:
            pass
        raise


def add_tag(tags, keys, tag):
    tag = clean_tag(tag)
    output = {k: list(v) for k, v in tags.items()}
    for key in keys:
        current = output.get(key, [])
        if tag not in current:
            if len(current) >= MAX_TAGS_PER_CAPTURE:
                raise ValueError("A capture can have up to 12 tags.")
            current.append(tag)
        output[key] = sorted(current, key=str.casefold)
    return output


def remove_tag(tags, keys, tag):
    output = {k: list(v) for k, v in tags.items()}
    for key in keys:
        if tag in output.get(key, []):
            output[key].remove(tag)
            if not output[key]:
                del output[key]
    return output


def all_tags(tags):
    return sorted({tag for values in tags.values() for tag in values}, key=str.casefold)
