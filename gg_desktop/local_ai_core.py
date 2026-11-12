"""Optional local AI model for the AI Assistant: download, verify, run and remove. No Qt here.

What it is: a small open language model (Qwen3, Apache 2.0, published by ggml-org, the llama.cpp team, or by Qwen) run on this PC by
llama.cpp's own `llama-server.exe`. Nothing is sent anywhere: the server listens on 127.0.0.1 only, and the model only
sees the facts Game Grave already holds plus the question.

Rules this module keeps:
* It downloads only when the owner presses Download, only from the official places below (huggingface.co for the model,
  github.com / api.github.com for llama.cpp), following redirects only to those hosts' download servers.
* Every file is checked against the SHA-256 the publisher records (Hugging Face's file record, GitHub's release-asset
  digest); a file that does not match is deleted and never used. Free space is checked first. A cancel or failure removes
  the partial file.
* Everything lives in Game Grave's own folder (`<config>/ai`); Remove deletes exactly that model or engine folder.
* The server runs only while the assistant is answering, below normal priority, with at most half the CPU threads, and is
  stopped after a few idle minutes, when a game starts and when Game Grave closes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request
import zipfile

import core

# ------------------------------------------------------------------ what can be downloaded
@dataclass(frozen=True)
class ModelChoice:
    key: str
    label: str
    repo: str
    quant: str
    approx_bytes: int
    ram_gb: int
    blurb: str

    @property
    def title(self):
        return f"{self.label} ({self.approx_bytes / 1024 ** 3:.1f} GB)"


GB = 1024 ** 3
MODELS = (
    ModelChoice("small", "Small", "ggml-org/Qwen3-1.7B-GGUF", "Q4_K_M", int(1.28 * GB), 6,
                "Fastest and lightest. Fine for short answers; weaker on long questions."),
    ModelChoice("medium", "Medium", "ggml-org/Qwen3-4B-GGUF", "Q4_K_M", int(2.5 * GB), 8,
                "The best balance. Runs on most gaming PCs and answers in a few seconds."),
    ModelChoice("large", "Large", "Qwen/Qwen3-8B-GGUF", "Q4_K_M", int(5.03 * GB), 16,
                "Best answers. Needs 16 GB of memory and is slower without a strong graphics card."),
)
BY_KEY = {m.key: m for m in MODELS}
DEFAULT_MODEL = "medium"

# llama.cpp's own Windows builds. Vulkan uses NVIDIA, AMD or Intel graphics; CPU is the fallback that runs anywhere.
RUNTIME_REPO = "ggml-org/llama.cpp"
RUNTIME_TAG = "b7388"
RUNTIMES = {"vulkan": f"llama-{RUNTIME_TAG}-bin-win-vulkan-x64.zip", "cpu": f"llama-{RUNTIME_TAG}-bin-win-cpu-x64.zip"}
# Published by winget's manifest for ggml.llamacpp b7388; GitHub's own digest is checked as well.
PINNED_SHA256 = {RUNTIMES["vulkan"]: "10393a8ac9e891b86975d5e8ae4393eaa02700fcb48266b87cf9b778cb5190e3"}

ALLOWED_HOSTS = ("huggingface.co", "hf.co", "github.com", "githubusercontent.com")
MAX_DOWNLOAD = 8 * GB
SPARE_BYTES = 1 * GB


class LocalAIError(RuntimeError):
    pass


class Canceled(LocalAIError):
    pass


# ------------------------------------------------------------------ places
def ai_dir(base=None) -> Path:
    return Path(base) if base else core.config_dir() / "ai"


def model_path(key, base=None) -> Path:
    return ai_dir(base) / "models" / f"{key}.gguf"


def runtime_dir(kind, base=None) -> Path:
    return ai_dir(base) / "runtime" / kind


def server_exe(kind, base=None) -> Path | None:
    root = runtime_dir(kind, base)
    if not root.is_dir():
        return None
    found = sorted(root.rglob("llama-server.exe"))
    return found[0] if found else None


def installed_models(base=None):
    return [m.key for m in MODELS if model_path(m.key, base).is_file()]


def installed_runtime(base=None):
    for kind in ("vulkan", "cpu"):
        if server_exe(kind, base):
            return kind
    return ""


def folder_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else 0


# ------------------------------------------------------------------ network (allowlisted, verified)
def host_allowed(url) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_allowed(newurl):
            raise LocalAIError("A download tried to go somewhere other than Hugging Face or GitHub, so it was stopped.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener():
    return urllib.request.build_opener(_Redirects())


def _request(url, headers=None):
    if not host_allowed(url):
        raise LocalAIError("Only Hugging Face and GitHub downloads are allowed.")
    return urllib.request.Request(url, headers={"User-Agent": "GameGrave-LocalAI", **(headers or {})})


def _get_json(url, opener=None, timeout=20):
    with (opener or _opener()).open(_request(url, {"Accept": "application/json"}), timeout=timeout) as response:
        return json.loads(response.read(4_000_000).decode("utf-8"))


@dataclass(frozen=True)
class Remote:
    name: str
    url: str
    size: int
    sha256: str


def pick_model_file(listing, quant):
    """The single .gguf in a Hugging Face tree listing whose name ends with the quant, with its recorded SHA-256."""
    hits = [f for f in listing if isinstance(f, dict) and f.get("type") == "file"
            and str(f.get("path", "")).lower().endswith(f"{quant.lower()}.gguf") and "/" not in str(f.get("path", ""))
            and "-of-" not in str(f.get("path", "")).lower()]  # split files are not supported
    if not hits:
        names = ", ".join(str(f.get("path")) for f in listing if isinstance(f, dict))[:300]
        raise LocalAIError(f"Hugging Face lists no single {quant} model file (it has: {names}).")
    item = min(hits, key=lambda f: len(str(f["path"])))  # the plain name, not a variant like ...-UD-Q4_K_M
    lfs = item.get("lfs") or {}
    sha = str(lfs.get("oid") or lfs.get("sha256") or "").lower()
    size = int(lfs.get("size") or item.get("size") or 0)
    if len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
        raise LocalAIError("Hugging Face did not give a SHA-256 for the model, so it can't be checked.")
    return item["path"], size, sha


def resolve_model(key, opener=None) -> Remote:
    choice = BY_KEY[key]
    listing = _get_json(f"https://huggingface.co/api/models/{choice.repo}/tree/main", opener)
    name, size, sha = pick_model_file(listing, choice.quant)
    url = f"https://huggingface.co/{choice.repo}/resolve/main/{urllib.parse.quote(name)}"
    return Remote(name, url, size, sha)


def pick_runtime_asset(release, name):
    asset = next((a for a in release.get("assets", []) if a.get("name") == name), None)
    if not asset:
        raise LocalAIError(f"llama.cpp {RUNTIME_TAG} has no {name}.")
    digest = str(asset.get("digest") or "").lower()
    sha = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
    pinned = PINNED_SHA256.get(name, "")
    if pinned and sha and pinned != sha:
        raise LocalAIError("GitHub's fingerprint for the AI engine does not match the expected one, so it was not used.")
    sha = sha or pinned
    if len(sha) != 64:
        raise LocalAIError("GitHub did not give a SHA-256 for the AI engine, so it can't be checked.")
    return Remote(name, asset["browser_download_url"], int(asset.get("size") or 0), sha)


def resolve_runtime(kind, opener=None) -> Remote:
    release = _get_json(f"https://api.github.com/repos/{RUNTIME_REPO}/releases/tags/{RUNTIME_TAG}", opener)
    return pick_runtime_asset(release, RUNTIMES[kind])


def check_space(folder: Path, need: int, free=None):
    folder.mkdir(parents=True, exist_ok=True)
    have = free if free is not None else shutil.disk_usage(folder).free
    if have < need + SPARE_BYTES:
        raise LocalAIError(f"Not enough free space: this needs {need / GB:.1f} GB plus 1 GB spare, and the drive has "
                           f"{have / GB:.1f} GB free.")


def download(remote: Remote, dest: Path, progress=lambda done, total: None, cancel=lambda: False, opener=None):
    """Stream to dest.part, check the SHA-256, then move into place. Removes the partial file on any failure."""
    if remote.size and remote.size > MAX_DOWNLOAD:
        raise LocalAIError("The download is larger than expected, so it was not started.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    check_space(dest.parent, max(0, remote.size))
    digest = hashlib.sha256()
    done = 0
    try:
        with (opener or _opener()).open(_request(remote.url), timeout=60) as response, part.open("wb") as out:
            total = int(response.headers.get("Content-Length") or remote.size or 0)
            while True:
                if cancel():
                    raise Canceled("Download canceled.")
                block = response.read(1 << 20)
                if not block:
                    break
                done += len(block)
                if done > MAX_DOWNLOAD:
                    raise LocalAIError("The download is larger than expected, so it was stopped.")
                digest.update(block)
                out.write(block)
                progress(done, total)
        if digest.hexdigest() != remote.sha256:
            raise LocalAIError("The downloaded file does not match its published SHA-256, so it was deleted.")
        os.replace(part, dest)
    except BaseException:
        try:
            part.unlink()
        except OSError:
            pass
        raise
    return dest


def extract_runtime(archive: Path, kind, base=None):
    """Unpack the llama.cpp zip into its own folder, refusing any entry that would land outside it."""
    target = runtime_dir(kind, base)
    staging = target.with_name(kind + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive) as z:
            root = staging.resolve()
            for info in z.infolist():
                out = (staging / info.filename).resolve()
                if out != root and root not in out.parents:
                    raise LocalAIError("The AI engine archive has an unsafe path, so it was not used.")
            z.extractall(staging)
        if not sorted(staging.rglob("llama-server.exe")):
            raise LocalAIError("The AI engine archive has no llama-server.exe.")
        shutil.rmtree(target, ignore_errors=True)
        os.replace(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        try:
            archive.unlink()
        except OSError:
            pass
    return target


def install_runtime(kind, progress=lambda done, total: None, cancel=lambda: False, base=None, opener=None):
    remote = resolve_runtime(kind, opener)
    archive = ai_dir(base) / "runtime" / remote.name
    download(remote, archive, progress, cancel, opener)
    return extract_runtime(archive, kind, base)


def install_model(key, progress=lambda done, total: None, cancel=lambda: False, base=None, opener=None):
    remote = resolve_model(key, opener)
    return download(remote, model_path(key, base), progress, cancel, opener)


def remove_model(key, base=None) -> int:
    path = model_path(key, base)
    size = path.stat().st_size if path.is_file() else 0
    for p in (path, path.with_name(path.name + ".part")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    return size


def remove_all(base=None) -> int:
    """Removes Game Grave's own AI folder (models and engine) and nothing else."""
    root = ai_dir(base)
    size = folder_size(root)
    shutil.rmtree(root, ignore_errors=True)
    return size


# ------------------------------------------------------------------ running the model
def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def threads():
    return max(1, (os.cpu_count() or 2) // 2)


def server_args(exe, model, port, kind, context=4096):
    args = [str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(port), "-c", str(context),
            "-t", str(threads())]
    if kind == "vulkan":
        args += ["-ngl", "99"]
    return args


class LocalServer:
    """One llama-server process for one model. start() blocks until it answers /health or fails."""

    def __init__(self, model_key, base=None, popen=subprocess.Popen, opener=None):
        self.model_key, self.base, self.popen, self.opener = model_key, base, popen, opener
        self.process = None
        self.port = 0
        self.kind = ""
        self.last_used = 0.0

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def _http(self, path, body=None, timeout=10):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                         headers={"Content-Type": "application/json"})
        opener = self.opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            return json.loads(response.read(2_000_000).decode("utf-8") or "{}")

    def start(self, kind, wait=180, sleep=time.sleep):
        if self.running:
            return
        exe = server_exe(kind, self.base)
        model = model_path(self.model_key, self.base)
        if exe is None or not model.is_file():
            raise LocalAIError("The local AI model or engine is not downloaded.")
        self.port, self.kind = free_port(), kind
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        self.process = self.popen(server_args(exe, model, self.port, kind), stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags,
                                  cwd=str(exe.parent))
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.process = None
                raise LocalAIError(f"The AI engine ({kind}) closed while starting.")
            try:
                if self._http("/health", timeout=2).get("status") == "ok":
                    self.last_used = time.monotonic()
                    return
            except (OSError, ValueError):
                pass
            sleep(0.5)
        self.stop()
        raise LocalAIError("The AI engine did not start in time.")

    def chat(self, messages, max_tokens=500, timeout=180):
        reply = self._http("/v1/chat/completions", {"messages": messages, "max_tokens": max_tokens, "temperature": 0.3,
                                                    "top_p": 0.9, "stream": False}, timeout=timeout)
        self.last_used = time.monotonic()
        try:
            return str(reply["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raise LocalAIError("The AI engine gave an empty answer.")

    def stop(self):
        process, self.process = self.process, None
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=10)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


def start_best(server: LocalServer, base=None, progress=lambda done, total: None):
    """Start with the graphics (Vulkan) build when present; if it won't start on this PC, use the CPU build,
    downloading it once (verified like every other download) if it isn't there yet."""
    kind = installed_runtime(base)
    try:
        server.start(kind)
        return kind
    except LocalAIError:
        if kind != "vulkan":
            raise
    if not server_exe("cpu", base):
        install_runtime("cpu", progress, base=base)
    server.start("cpu")
    return "cpu"
