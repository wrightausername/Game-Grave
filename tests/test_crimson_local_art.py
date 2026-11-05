"""Read-only local game artwork regression tests."""
from pathlib import Path
from types import SimpleNamespace

from gg_desktop.local_art import game_cover_path


def _game(path, app_id=None, launcher="Steam"):
    return SimpleNamespace(install_path=str(path), app_id=app_id, launcher=launcher)


def test_steam_library_cache_poster_is_discovered(tmp_path):
    root = tmp_path / "Steam"
    game_dir = root / "steamapps" / "common" / "Example"
    game_dir.mkdir(parents=True)
    art = root / "appcache" / "librarycache" / "123_library_600x900.jpg"
    art.parent.mkdir(parents=True)
    art.write_bytes(b"a" * 2048)
    assert game_cover_path(_game(game_dir, "123")) == str(art)


def test_installed_game_root_cover_is_discovered(tmp_path):
    path = tmp_path / "sample"
    path.mkdir()
    img = path / "cover.png"
    img.write_bytes(b"x" * 2048)
    assert game_cover_path(_game(path, None, "Epic Games")) == str(img)


def test_no_recursive_directory_crawl_or_fake_art(tmp_path):
    path = tmp_path / "Example"
    deep = path / "nested" / "covers"
    deep.mkdir(parents=True)
    (deep / "cover.jpg").write_bytes(b"x" * 2048)
    assert game_cover_path(_game(path, None, "EA")) == ""


def test_tiny_or_oversized_art_rejected(tmp_path):
    path = tmp_path / "Example2"
    path.mkdir()
    (path / "cover.png").write_bytes(b"x" * 100)
    assert game_cover_path(_game(path, None, "GOG")) == ""


def test_symlinked_art_is_not_used(tmp_path):
    path = tmp_path / "Example3"
    path.mkdir()
    target = tmp_path / "target.jpg"
    target.write_bytes(b"x" * 2048)
    link = path / "cover.jpg"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        return
    assert game_cover_path(_game(path, None, "GOG")) == ""
