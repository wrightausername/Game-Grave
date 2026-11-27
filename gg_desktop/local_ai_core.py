"""Optional local AI model for the AI Assistant: download, verify, run and remove. No Qt here.

What it is: an open language model (Qwen 3.5, Apache 2.0, GGUF files published by Unsloth on Hugging Face) run on this PC by
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
    vision: bool = True          # Qwen 3.5 reads images through its separate projector file (mmproj)

    @property
    def title(self):
        return f"{self.label} ({self.approx_bytes / 1024 ** 3:.1f} GB)"


GB = 1024 ** 3
MODELS = (
    ModelChoice("small", "Small", "unsloth/Qwen3.5-2B-GGUF", "Q4_K_M", int(1.3 * GB), 6,
                "Fastest and lightest. Fine for short answers; weaker on long problems."),
    ModelChoice("medium", "Medium", "unsloth/Qwen3.5-4B-GGUF", "Q4_K_M", int(2.7 * GB), 8,
                "A good balance. Runs on most gaming PCs and answers in a few seconds."),
    ModelChoice("large", "Large", "unsloth/Qwen3.5-9B-GGUF", "Q4_K_M", int(5.8 * GB), 16,
                "Much better answers. Wants 16 GB of memory and a graphics card with 8 GB for good speed."),
    ModelChoice("xl", "Extra Large", "unsloth/Qwen3.5-35B-A3B-GGUF", "Q4_K_M", int(21.5 * GB), 32,
                "The smartest. Only a small part of it works on each word, so it is fast for its size, but it needs "
                "32 GB of memory and about 23 GB of free space."),
)
BY_KEY = {m.key: m for m in MODELS}
# How much text each model may hold at once: the chat, what it looked up, and its thinking.
CONTEXT = {"small": 12288, "medium": 16384, "large": 16384, "xl": 16384}
THINKS = frozenset({"medium", "large", "xl"})       # these reason step by step before answering
MOE = frozenset({"xl"})                             # mixture of experts: the experts stay in memory, the rest on graphics
DEFAULT_MODEL = "medium"
GENERATION = "q35"                                  # in the file name, so an older Qwen3 file is never mistaken for this

# llama.cpp's own Windows builds. Vulkan uses NVIDIA, AMD or Intel graphics; CPU is the fallback that runs anywhere.
# Qwen 3.5 needs a 2026 build. Every file is checked against the SHA-256 GitHub records for the release asset.
RUNTIME_REPO = "ggml-org/llama.cpp"
RUNTIME_TAG = "b12189"
RUNTIMES = {"vulkan": f"llama-{RUNTIME_TAG}-bin-win-vulkan-x64.zip", "cpu": f"llama-{RUNTIME_TAG}-bin-win-cpu-x64.zip"}
PINNED_SHA256 = {}

ALLOWED_HOSTS = ("huggingface.co", "hf.co", "github.com", "githubusercontent.com")
MAX_DOWNLOAD = 24 * GB
SPARE_BYTES = 1 * GB


def recommend(ram_gb, vram_gb):
    """The size that fits this PC: what its memory and graphics memory can run at a usable speed."""
    ram, vram = float(ram_gb or 0), float(vram_gb or 0)
    if ram >= 32 and vram >= 6:                   # mixture of experts: lives mostly in memory, so RAM decides
        return "xl"
    if vram >= 8 and ram >= 16:
        return "large"
    if vram >= 4 or ram >= 12:
        return "medium"
    return "small"


def system_memory_gb():
    """Installed memory as Windows reports it (GlobalMemoryStatusEx), or 0 when it can't be read."""
    try:
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                        ("avail", ctypes.c_ulonglong), ("page_total", ctypes.c_ulonglong),
                        ("page_avail", ctypes.c_ulonglong), ("virtual_total", ctypes.c_ulonglong),
                        ("virtual_avail", ctypes.c_ulonglong), ("extended", ctypes.c_ulonglong)]
        status = Status()
        status.length = ctypes.sizeof(Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.total / GB
    except Exception:
        pass
    return 0.0


def graphics_memory_gb():
    """The largest graphics card's own memory, from the display adapters' driver keys (read only), or 0."""
    try:
        import winreg
    except ImportError:
        return 0.0
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    best = 0
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
            for i in range(0, 32):
                try:
                    name = winreg.EnumKey(root, i)
                except OSError:
                    break
                if not name.isdigit():
                    continue
                try:
                    with winreg.OpenKey(root, name) as key:
                        for value_name in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                            try:
                                value, _kind = winreg.QueryValueEx(key, value_name)
                            except OSError:
                                continue
                            if isinstance(value, bytes):
                                value = int.from_bytes(value[:8], "little")
                            best = max(best, int(value or 0))
                except OSError:
                    continue
    except OSError:
        return 0.0
    return best / GB


def recommended_for_this_pc():
    return recommend(system_memory_gb(), graphics_memory_gb())


class LocalAIError(RuntimeError):
    pass


class Canceled(LocalAIError):
    pass


# ------------------------------------------------------------------ places
def ai_dir(base=None) -> Path:
    return Path(base) if base else core.config_dir() / "ai"


def model_path(key, base=None) -> Path:
    return ai_dir(base) / "models" / f"{key}-{GENERATION}.gguf"


def vision_path(key, base=None) -> Path:
    """The image projector that lets the model read screenshots (optional: without it, text only)."""
    return ai_dir(base) / "models" / f"{key}-{GENERATION}-mmproj.gguf"


def legacy_path(key, base=None) -> Path:
    """A Qwen3 model downloaded by an earlier Game Grave. It still runs, and the panel offers the newer one."""
    return ai_dir(base) / "models" / f"{key}.gguf"


def model_file(key, base=None) -> Path:
    new = model_path(key, base)
    return new if new.is_file() else legacy_path(key, base)


def is_legacy(key, base=None) -> bool:
    return not model_path(key, base).is_file() and legacy_path(key, base).is_file()


def sees_images(key, base=None) -> bool:
    return model_path(key, base).is_file() and vision_path(key, base).is_file()


def runtime_dir(kind, base=None) -> Path:
    """Each engine version has its own folder, so an older engine is never mistaken for the one Qwen 3.5 needs."""
    return ai_dir(base) / "runtime" / RUNTIME_TAG / kind


def old_runtimes(base=None):
    """Engine folders from earlier versions (Game Grave's own folder only)."""
    root = ai_dir(base) / "runtime"
    if not root.is_dir():
        return []
    return [p for p in root.iterdir() if p.is_dir() and p.name != RUNTIME_TAG]


def server_exe(kind, base=None) -> Path | None:
    root = runtime_dir(kind, base)
    if not root.is_dir():
        return None
    found = sorted(root.rglob("llama-server.exe"))
    return found[0] if found else None


def installed_models(base=None):
    return [m.key for m in MODELS if model_file(m.key, base).is_file()]


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


def pick_vision_file(listing):
    """The F16 image projector (mmproj) at the top of the repo, with its SHA-256, or None when the repo has none."""
    hits = [f for f in listing if isinstance(f, dict) and f.get("type") == "file" and "/" not in str(f.get("path", ""))
            and str(f.get("path", "")).lower().startswith("mmproj") and str(f.get("path", "")).lower().endswith(".gguf")]
    if not hits:
        return None
    rank = lambda f: (0 if str(f["path"]).lower().endswith("-f16.gguf") else 1 if "bf16" in str(f["path"]).lower()
                      else 2, len(str(f["path"])))
    item = min(hits, key=rank)
    lfs = item.get("lfs") or {}
    sha = str(lfs.get("oid") or lfs.get("sha256") or "").lower()
    size = int(lfs.get("size") or item.get("size") or 0)
    if len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
        return None
    return item["path"], size, sha


def _listing(choice, opener=None):
    return _get_json(f"https://huggingface.co/api/models/{choice.repo}/tree/main", opener)


def _remote(choice, picked):
    name, size, sha = picked
    return Remote(name, f"https://huggingface.co/{choice.repo}/resolve/main/{urllib.parse.quote(name)}", size, sha)


def resolve_model(key, opener=None) -> Remote:
    choice = BY_KEY[key]
    return _remote(choice, pick_model_file(_listing(choice, opener), choice.quant))


def resolve_vision(key, opener=None):
    """The image projector for this model as a Remote, or None (then the model runs text only)."""
    choice = BY_KEY[key]
    if not choice.vision:
        return None
    picked = pick_vision_file(_listing(choice, opener))
    return _remote(choice, picked) if picked else None


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
        for old in old_runtimes(base):          # the earlier engine in Game Grave's own AI folder, replaced by this one
            shutil.rmtree(old, ignore_errors=True)
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
    """The model, then its image projector (when the repo has one; a failure there leaves the model text only)."""
    remote = resolve_model(key, opener)
    vision = None
    try:
        vision = resolve_vision(key, opener)
    except LocalAIError:
        vision = None
    total = remote.size + (vision.size if vision else 0)
    done_model = download(remote, model_path(key, base), lambda d, t: progress(d, total or t), cancel, opener)
    if vision is not None:
        try:
            download(vision, vision_path(key, base), lambda d, t: progress(remote.size + d, total), cancel, opener)
        except Canceled:
            raise
        except LocalAIError:
            pass
    legacy = legacy_path(key, base)             # the older Qwen3 file of the same size is replaced, not kept twice
    try:
        legacy.unlink()
    except OSError:
        pass
    return done_model


def remove_model(key, base=None) -> int:
    size = 0
    for path in (model_path(key, base), vision_path(key, base), legacy_path(key, base)):
        size += path.stat().st_size if path.is_file() else 0
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


def server_args(exe, model, port, kind, context=4096, vision=None, moe=False):
    args = [str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(port), "-c", str(context),
            "-t", str(threads()), "--jinja"]   # --jinja: the model's own chat template, needed for lookups (tool calls)
    if vision:
        args += ["--mmproj", str(vision)]
    if kind == "vulkan":
        args += ["-ngl", "99"]
        if moe:
            args += ["--cpu-moe"]          # the experts stay in system memory, so a 35B model fits next to an 8 GB card
    return args


class LocalServer:
    """One llama-server process for one model. start() blocks until it answers /health or fails."""

    def __init__(self, model_key, base=None, popen=subprocess.Popen, opener=None):
        self.model_key, self.base, self.popen, self.opener = model_key, base, popen, opener
        self.process = None
        self.port = 0
        self.kind = ""
        self.vision = False
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
        model = model_file(self.model_key, self.base)
        if exe is None or not model.is_file():
            raise LocalAIError("The local AI model or engine is not downloaded.")
        self.port, self.kind = free_port(), kind
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        vision = vision_path(self.model_key, self.base) if sees_images(self.model_key, self.base) else None
        self.vision = vision is not None
        self.process = self.popen(server_args(exe, model, self.port, kind, CONTEXT.get(self.model_key, 8192), vision,
                                              self.model_key in MOE),
                                  stdin=subprocess.DEVNULL,
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

    def _stream(self, body, timeout, on_text):
        """The reply built from llama-server's streamed pieces (server-sent events); on_text(text so far) is called as
        words arrive. Tool calls arrive in pieces too and are joined by their index."""
        data = json.dumps(dict(body, stream=True)).encode("utf-8")
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/chat/completions", data=data,
                                         headers={"Content-Type": "application/json"})
        opener = self.opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
        content, calls = [], {}
        with opener.open(request, timeout=timeout) as response:
            for raw in response:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = json.loads(payload)["choices"][0].get("delta") or {}
                except (ValueError, KeyError, IndexError, TypeError):
                    continue
                if delta.get("content"):
                    content.append(delta["content"])
                    if not calls:
                        on_text("".join(content))
                for piece in delta.get("tool_calls") or []:
                    slot = calls.setdefault(piece.get("index", len(calls)), {"id": "", "type": "function",
                                                                              "function": {"name": "", "arguments": ""}})
                    slot["id"] = piece.get("id") or slot["id"]
                    fn = piece.get("function") or {}
                    slot["function"]["name"] += fn.get("name") or ""
                    slot["function"]["arguments"] += fn.get("arguments") or ""
        message = {"role": "assistant", "content": "".join(content)}
        if calls:
            message["tool_calls"] = [calls[k] for k in sorted(calls)]
        return {"choices": [{"message": message}]}

    def chat_message(self, messages, tools=None, max_tokens=500, timeout=180, on_text=None, think=None):
        """The reply message as a dict (content, and tool_calls when the model asked for a lookup). The same system
        text is sent every time, so the server's prompt cache skips reading it again (cache_prompt). With on_text, the
        answer is streamed and on_text gets the text so far as it is written."""
        body = {"messages": messages, "max_tokens": max_tokens, "temperature": 0.6, "top_p": 0.9, "stream": False,
                "cache_prompt": True}
        if think is not None:                 # Qwen's chat template switch for reasoning before answering
            body["chat_template_kwargs"] = {"enable_thinking": bool(think)}
        if tools:
            body["tools"] = tools
        if on_text is not None:
            try:
                reply = self._stream(body, timeout, on_text)
            except (OSError, ValueError):
                reply = self._http("/v1/chat/completions", body, timeout=timeout)   # streaming refused: ask once whole
        else:
            reply = self._http("/v1/chat/completions", body, timeout=timeout)
        self.last_used = time.monotonic()
        try:
            message = dict(reply["choices"][0]["message"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise LocalAIError("The AI engine gave an empty answer.")
        message["content"] = str(message.get("content") or "")
        return message

    def chat(self, messages, max_tokens=500, timeout=180, think=None):
        return self.chat_message(messages, None, max_tokens, timeout, think=think)["content"]

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


def process_memory(process) -> int | None:
    """Bytes of memory a running process uses right now (Windows working set), or None when it can't be read."""
    if process is None or os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        handle = int(process._handle)          # subprocess.Popen keeps the Windows process handle
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    except Exception:
        return None


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
