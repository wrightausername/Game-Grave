"""Game Grave Updater: one small standalone program that finds the newest Game Grave preview build,
downloads it, checks it against the published SHA-256, and (only after you click Install) runs the installer.

Nothing is downloaded or installed until you press the button. The installer is the same Setup.exe the
build produces; this program never touches your games, mods or Game Grave data. Standard library only.

Command line (used by the build checks, no window):
    GameGrave-Updater.exe --fetch <folder> <result.json>   find, download and verify, but do not install
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

REPO = "wrightausername/Game-Grave"
SETUP_NAME = "GameGrave-Crimson-Preview-Setup.exe"
SUM_NAME = "GameGrave-Crimson-Preview-Setup.sha256"
API = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
INSTALLED_EXE = ("Programs", "Game Grave Crimson Preview", "GameGrave-Crimson-Preview.exe")
MAX_SETUP_BYTES = 600 * 1024 * 1024
CHUNK = 1024 * 256


class UpdaterError(Exception):
    pass


# ---------------------------------------------------------------- local files

def state_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "Game Grave Updater"


def read_state() -> dict:
    try:
        data = json.loads((state_dir() / "state.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(**values) -> None:
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    data = read_state()
    data.update(values)
    (folder / "state.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def program_folder() -> Path:
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def find_token() -> str:
    """A GitHub token is only needed while preview builds are private drafts. Order: environment, a file
    next to the program, then the one saved by the 'GitHub token' button."""
    for name in ("GG_UPDATE_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    for path in (program_folder() / "updater_token.txt", state_dir() / "token.txt"):
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return ""


def save_token(value: str) -> None:
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "token.txt").write_text(value.strip(), encoding="utf-8")


# ---------------------------------------------------------------- network

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # we follow the redirect ourselves, without the token
        return None


def _real_open(url: str, headers: dict):
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        return urllib.request.build_opener(_NoRedirect()).open(request, timeout=60)
    except urllib.error.HTTPError as problem:
        if problem.code in (301, 302, 303, 307, 308):
            return problem  # carries .headers["Location"]; .code is the status
        raise


def _status(response) -> int:
    return getattr(response, "status", None) or getattr(response, "code", 200)


def _get(url: str, token: str, accept: str, opener=None):
    """GET with the token for api.github.com only. A redirect (to the file host) is followed without it."""
    opener = opener or _real_open
    if not url.startswith("https://"):
        raise UpdaterError("Refusing a non-HTTPS address.")
    headers = {"User-Agent": "GameGrave-Updater/1", "Accept": accept}
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = "Bearer " + token
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    try:
        response = opener(url, headers)
        for _ in range(3):
            code = _status(response)
            if code in (301, 302, 303, 307, 308):
                target = response.headers.get("Location", "")
                if not target.startswith("https://"):
                    raise UpdaterError("The download redirected somewhere that is not HTTPS.")
                response = opener(target, {"User-Agent": headers["User-Agent"], "Accept": accept})
                continue
            break
        else:
            raise UpdaterError("Too many redirects.")
    except urllib.error.HTTPError as problem:
        if problem.code in (401, 403, 404):
            raise UpdaterError(
                "GitHub did not allow this request (%d). Preview builds are private drafts, so a GitHub token "
                "with access to the repository is needed. Use the 'GitHub token' button." % problem.code)
        raise UpdaterError("GitHub answered with error %d." % problem.code)
    except (urllib.error.URLError, OSError) as problem:
        raise UpdaterError("Could not reach GitHub: %s" % getattr(problem, "reason", problem))
    if _status(response) != 200:
        raise UpdaterError("GitHub answered with status %s." % _status(response))
    return response


def _read(response, size=-1) -> bytes:
    """Read from a reply. A connection that drops half way is an updater problem, not a crash."""
    try:
        return response.read(size)
    except (OSError, http.client.HTTPException) as problem:
        raise UpdaterError("The connection to GitHub broke off: %s" % (problem or type(problem).__name__))


def list_releases(token: str, opener=None) -> list:
    response = _get(API, token, "application/vnd.github+json", opener)
    try:
        data = json.loads(_read(response).decode("utf-8"))
    except ValueError:
        raise UpdaterError("GitHub sent an answer that could not be read.")
    if not isinstance(data, list):
        raise UpdaterError("GitHub sent an unexpected answer.")
    return data


def pick_release(releases: list) -> dict | None:
    """Newest release that carries both the installer and its checksum file."""
    best = None
    for item in releases:
        if not isinstance(item, dict):
            continue
        assets = {a.get("name"): a for a in item.get("assets") or [] if isinstance(a, dict)}
        setup, checksum = assets.get(SETUP_NAME), assets.get(SUM_NAME)
        if not setup or not checksum:
            continue
        size = setup.get("size")
        if type(size) is not int or not 0 < size <= MAX_SETUP_BYTES:
            continue
        found = {
            "tag": str(item.get("tag_name") or ""),
            "name": str(item.get("name") or item.get("tag_name") or ""),
            "created": str(item.get("created_at") or ""),
            "draft": bool(item.get("draft")),
            "setup": {"url": setup.get("url"), "size": size},
            "sum": {"url": checksum.get("url"), "size": checksum.get("size")},
        }
        if not found["tag"] or not found["setup"]["url"] or not found["sum"]["url"]:
            continue
        if best is None or found["created"] > best["created"]:
            best = found
    return best


def parse_sha256(text: str, filename: str = SETUP_NAME) -> str:
    for line in text.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        digest = parts[0].lower()
        if len(digest) == 64 and all(c in "0123456789abcdef" for c in digest):
            if len(parts) == 1 or parts[-1].lstrip("*") == filename:
                return digest
    raise UpdaterError("The checksum file did not contain a SHA-256 for the installer.")


def fetch_checksum(release: dict, token: str, opener=None) -> str:
    response = _get(release["sum"]["url"], token, "application/octet-stream", opener)
    return parse_sha256(_read(response, 4096).decode("utf-8", "replace"))


def download_setup(release: dict, token: str, folder: Path, expected: str, progress=None, opener=None) -> Path:
    """Download to a partial file, check size and SHA-256, and only then give it its real name."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / SETUP_NAME
    total = release["setup"]["size"]
    response = _get(release["setup"]["url"], token, "application/octet-stream", opener)
    digest, done = hashlib.sha256(), 0
    fd, raw = tempfile.mkstemp(prefix=".gg-update-", suffix=".partial", dir=folder)
    partial = Path(raw)
    try:
        with os.fdopen(fd, "wb") as sink:
            while True:
                block = _read(response, CHUNK)
                if not block:
                    break
                done += len(block)
                if done > total:
                    raise UpdaterError("The download is larger than GitHub says it should be.")
                digest.update(block)
                sink.write(block)
                if progress:
                    progress(done, total)
        if done != total:
            raise UpdaterError("The download stopped early (%d of %d bytes)." % (done, total))
        if digest.hexdigest() != expected:
            raise UpdaterError("The download does not match its published SHA-256, so it was thrown away.")
        if target.exists():
            target.unlink()
        partial.replace(target)
        return target
    finally:
        try:
            if partial.exists():
                partial.unlink()
        except OSError:
            pass


def describe_status(release: dict | None, installed_tag: str) -> tuple[str, str]:
    """(kind, sentence) for the window: none / current / available / unknown."""
    if release is None:
        return "none", "No preview build with an installer was found."
    if installed_tag and installed_tag == release["tag"]:
        return "current", "You already have the newest build (%s)." % release["tag"]
    size = release["setup"]["size"] / (1024 * 1024)
    if installed_tag:
        return "available", "Newer build available: %s (%.0f MB). Installed: %s." % (release["tag"], size, installed_tag)
    return "available", "Newest build: %s (%.0f MB). This updater has not installed one yet." % (release["tag"], size)


def installed_exe() -> Path | None:
    base = os.environ.get("LOCALAPPDATA")
    path = Path(base).joinpath(*INSTALLED_EXE) if base else None
    return path if path and path.exists() else None


# ---------------------------------------------------------------- command line

def run_fetch(folder: Path, result_file: Path) -> int:
    result = {"ok": False}
    try:
        release = pick_release(list_releases(find_token()))
        if release is None:
            raise UpdaterError("No release with the installer and checksum was found.")
        expected = fetch_checksum(release, find_token())
        path = download_setup(release, find_token(), folder, expected)
        result = {"ok": True, "tag": release["tag"], "draft": release["draft"], "bytes": path.stat().st_size,
                  "sha256": expected}
    except UpdaterError as problem:
        result["error"] = str(problem)
    except OSError as problem:
        result["error"] = "Could not finish: %s" % problem
    Path(result_file).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


# ---------------------------------------------------------------- window

def run_window() -> int:
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk
    import webbrowser

    bg, panel, red, text, dim = "#02070a", "#0a1218", "#e5243b", "#f2f5f7", "#8fa1ad"
    root = tk.Tk()
    root.title("Game Grave Updater")
    root.configure(bg=bg)
    root.geometry("560x330")
    root.resizable(False, False)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("GG.Horizontal.TProgressbar", troughcolor=panel, background=red, bordercolor=panel,
                    lightcolor=red, darkcolor=red)

    tk.Label(root, text="Game Grave Updater", bg=bg, fg=text, font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=24, pady=(22, 0))
    tk.Label(root, text="Finds the newest build, checks it, and installs it only when you say so.",
             bg=bg, fg=dim, font=("Segoe UI", 9)).pack(anchor="w", padx=24)
    box = tk.Frame(root, bg=panel, highlightthickness=1, highlightbackground="#1b2a34")
    box.pack(fill="x", padx=24, pady=16)
    headline = tk.Label(box, text="Checking GitHub...", bg=panel, fg=text, font=("Segoe UI", 11, "bold"), anchor="w",
                        wraplength=490, justify="left")
    headline.pack(fill="x", padx=14, pady=(12, 2))
    detail = tk.Label(box, text="", bg=panel, fg=dim, font=("Segoe UI", 9), anchor="w", wraplength=490, justify="left")
    detail.pack(fill="x", padx=14, pady=(0, 10))
    bar = ttk.Progressbar(box, style="GG.Horizontal.TProgressbar", maximum=100)
    bar.pack(fill="x", padx=14, pady=(0, 14))

    buttons = tk.Frame(root, bg=bg)
    buttons.pack(fill="x", padx=24)

    def button(label, command, primary=False):
        b = tk.Button(buttons, text=label, command=command, relief="flat", bd=0, padx=14, pady=7,
                      bg=red if primary else panel, fg=text, activebackground="#ff3a52" if primary else "#14212b",
                      activeforeground=text, font=("Segoe UI", 9, "bold"), cursor="hand2", disabledforeground="#4a5a65")
        b.pack(side="left", padx=(0, 8))
        return b

    state = {"release": None, "busy": False}
    pending = []

    def post(fn):
        pending.append(fn)

    def pump():
        while pending:
            try:
                pending.pop(0)()
            except Exception:   # one bad update to the window must not stop the others
                pass
        root.after(80, pump)

    def set_busy(value):
        state["busy"] = value
        for b in (check_button, install_button):
            b.configure(state="disabled" if value else "normal")
        if not value and (state["release"] is None or describe_status(state["release"], read_state().get("installed_tag", ""))[0] == "current"):
            install_button.configure(state="disabled")

    def check():
        set_busy(True)
        headline.configure(text="Checking GitHub...")
        detail.configure(text="")
        bar.configure(value=0)

        def work():
            try:
                release = pick_release(list_releases(find_token()))
                kind, sentence = describe_status(release, read_state().get("installed_tag", ""))
                extra = ""
                if release:
                    extra = "Built %s%s" % (release["created"][:16].replace("T", " "), " (private draft)" if release["draft"] else "")
                post(lambda: (state.update(release=release), headline.configure(text=sentence), detail.configure(text=extra),
                              set_busy(False)))
            except Exception as problem:   # UpdaterError or anything unexpected: never leave the window stuck
                message = str(problem) if isinstance(problem, UpdaterError) else "Unexpected problem: %s" % problem
                post(lambda: (state.update(release=None), headline.configure(text="Could not check for updates"),
                              detail.configure(text=message), set_busy(False)))
        threading.Thread(target=work, daemon=True).start()

    def install():
        release = state["release"]
        if not release:
            return
        if not messagebox.askyesno("Install update", "Download %s and install it now?\n\nGame Grave will be closed if it is "
                                   "running. Your games, mods and settings are not touched." % release["tag"]):
            return
        set_busy(True)
        headline.configure(text="Downloading...")

        def progress(done, total):
            post(lambda: (bar.configure(value=done * 100 / total),
                          detail.configure(text="%.0f of %.0f MB" % (done / 1048576, total / 1048576))))

        def work():
            folder = None
            try:
                token = find_token()
                expected = fetch_checksum(release, token)
                folder = Path(tempfile.mkdtemp(prefix="GameGrave-Update-"))
                setup = download_setup(release, token, folder, expected, progress)
                post(lambda: (headline.configure(text="Verified. Installing..."),
                              detail.configure(text="The installer window is doing the work. Keep this open until it finishes.")))
                code = subprocess.call([str(setup), "/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS"])
                if code != 0:
                    raise UpdaterError("The installer stopped with code %d. Nothing was recorded as installed." % code)
                write_state(installed_tag=release["tag"])
                post(lambda: (headline.configure(text="Updated to %s" % release["tag"]), detail.configure(text=""),
                              set_busy(False), offer_open()))
            except Exception as problem:   # UpdaterError, OSError or anything unexpected
                message = str(problem) if isinstance(problem, UpdaterError) else "Unexpected problem: %s" % problem
                post(lambda: (headline.configure(text="Update did not finish"), detail.configure(text=message),
                              set_busy(False)))
            finally:
                if folder is not None:   # the downloaded installer is large; do not leave it in Temp
                    shutil.rmtree(folder, ignore_errors=True)
        threading.Thread(target=work, daemon=True).start()

    def offer_open():
        exe = installed_exe()
        if exe and messagebox.askyesno("Updated", "Open Game Grave now?"):
            subprocess.Popen([str(exe)])

    def ask_token():
        value = simpledialog.askstring("GitHub token", "Paste a GitHub token that can read this repository's releases.\n"
                                       "It is kept only on this PC.", show="*", parent=root)
        if value and value.strip():
            save_token(value)
            check()

    check_button = button("Check again", check)
    install_button = button("Download and install", install, primary=True)
    install_button.configure(state="disabled")
    button("GitHub token", ask_token)
    button("Releases page", lambda: webbrowser.open(RELEASES_PAGE))
    pump()
    root.after(200, check)
    root.mainloop()
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "--fetch":
        if len(argv) != 4:
            return 2
        return run_fetch(Path(argv[2]), Path(argv[3]))
    return run_window()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
