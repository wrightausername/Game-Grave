"""On-demand, verified Windows AI runtime. Never installs or runs without consent.

Game Grave downloads a pinned CPU-only llama.cpp release and a pinned Qwen
GGUF file into its own per-user data folder. The original app stays small.
No PowerShell, external installer, or administrative rights are needed.

This module never has cleanup authority. The local inference server is bound
to 127.0.0.1, has a per-process API token, and is terminated at app exit.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile

from core import config_dir, _has_reparse_component

RUNTIME_VERSION = "b12020"
RUNTIME_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/b12020/"
    "llama-b12020-bin-win-cpu-x64.zip"
)
RUNTIME_SHA256 = "07e81782f5a16c7ffef42403183808e02f271c9ece3aa2d64040b2620ae8d519"
RUNTIME_MAX_BYTES = 32 * 1024 * 1024

MODEL_FILENAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/"
    "resolve/main/" + MODEL_FILENAME
)
MODEL_SHA256 = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
MODEL_MAX_BYTES = 1250 * 1024 * 1024

ROOT_NAME = "optional-ai"
SERVER_NAME = "llama-server.exe"
INSTALL_METADATA = "install.json"
INSTALL_MESSAGE = (
    "The optional AI assistant needs a one-time download of about 1.2 GB. "
    "Game Grave will install its local AI engine and model automatically. "
    "No Ollama installation, terminal, account, or AI subscription is needed. "
    "The assistant stays on this PC and cannot delete files. Continue?"
)
_lock = threading.RLock()
_process = None
_endpoint = None
_api_key = None


class AiSetupError(RuntimeError):
    """Safe, user-readable local AI installation or launch error."""


def ai_root() -> Path:
    return config_dir() / ROOT_NAME


def _validate_folder(folder: Path) -> None:
    if _has_reparse_component(folder):
        raise AiSetupError("The AI storage path contains a link or Windows reparse point.")
    folder.mkdir(parents=True, exist_ok=True)
    if _has_reparse_component(folder):
        raise AiSetupError("The AI storage path changed during setup.")


def _hash_file(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_regular_file(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink() and not _has_reparse_component(path)
    except OSError:
        return False


def _download_pinned(url: str, target: Path, expected_sha: str, max_size: int,
                     notify=None, stage: str = "Downloading") -> None:
    """Bounded streaming HTTPS download. Verify before publishing the file."""
    if _safe_regular_file(target) and target.stat().st_size <= max_size:
        if _hash_file(target) == expected_sha:
            if notify:
                notify(stage, 1.0)
            return
    _validate_folder(target.parent)
    if target.exists() and not _safe_regular_file(target):
        raise AiSetupError("Refusing to replace a linked or unusual AI asset.")
    if not url.startswith("https://"):
        raise AiSetupError("AI downloads must use HTTPS.")
    staging = target.with_name(target.name + "." + uuid.uuid4().hex + ".part")
    total = 0
    digest = hashlib.sha256()
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "GameGrave-OptionalLocalAI/1.0"}
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            length = int(response.headers.get("Content-Length", "0") or "0")
            if length > max_size:
                raise AiSetupError("The AI download exceeded its expected size.")
            with staging.open("xb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_size:
                        raise AiSetupError("The AI download exceeded its size limit.")
                    digest.update(chunk)
                    output.write(chunk)
                    if notify and length:
                        notify(stage, min(0.999, total / length))
                output.flush()
                os.fsync(output.fileno())
        if digest.hexdigest() != expected_sha:
            raise AiSetupError("AI download failed verification. Nothing was installed.")
        if _has_reparse_component(target.parent) or target.is_symlink():
            raise AiSetupError("The AI download destination was redirected.")
        os.replace(staging, target)
        if notify:
            notify(stage, 1.0)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AiSetupError("Could not download the optional AI components. Check your connection.") from exc
    finally:
        if staging.exists() and not staging.is_symlink():
            try:
                staging.unlink()
            except OSError:
                pass


def _extract_runtime(archive: Path, destination: Path) -> Path:
    """Extract pinned ZIP into an isolated stage, rejecting path tricks/bombs."""
    _validate_folder(destination)
    count = 0
    expanded = 0
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            count += 1
            expanded += entry.file_size
            if count > 300 or expanded > 180 * 1024 * 1024:
                raise AiSetupError("Unexpected runtime archive contents.")
            name = entry.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith("/") or ".." in parts
                    or ":" in name or not name.strip()):
                raise AiSetupError("Unexpected file in AI runtime archive.")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise AiSetupError("Linked files are not allowed in AI runtime.")
            target = destination.joinpath(*parts)
            if entry.is_dir():
                _validate_folder(target)
                continue
            _validate_folder(target.parent)
            if target.exists() or target.is_symlink():
                raise AiSetupError("Duplicate runtime file.")
            with package.open(entry) as source, target.open("xb") as out:
                shutil.copyfileobj(source, out)
    candidates = list(destination.rglob(SERVER_NAME))
    if len(candidates) != 1 or not _safe_regular_file(candidates[0]):
        raise AiSetupError("The pinned AI runtime does not contain one expected server.")
    return candidates[0]


def _metadata_ok(root: Path) -> bool:
    record = root / INSTALL_METADATA
    if not _safe_regular_file(record):
        return False
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
        return (data.get("runtime_sha256") == RUNTIME_SHA256
                and data.get("model_sha256") == MODEL_SHA256
                and data.get("version") == RUNTIME_VERSION)
    except (OSError, ValueError, TypeError):
        return False


def _server_file(root: Path) -> Path | None:
    if not _metadata_ok(root):
        return None
    paths = list((root / "runtime").rglob(SERVER_NAME)) if (root / "runtime").exists() else []
    if len(paths) != 1 or not _safe_regular_file(paths[0]):
        return None
    return paths[0]


def is_ai_installed() -> bool:
    """Fast UI indicator; full SHA-256 checks are repeated before execution."""
    root = ai_root()
    model = root / "models" / MODEL_FILENAME
    return (_server_file(root) is not None and _safe_regular_file(model)
            and 500 * 1024 * 1024 < model.stat().st_size <= MODEL_MAX_BYTES)


def install_ai(notify=None) -> None:
    """Explicitly invoked by an approved UI click, never during app startup.

    notify(stage, fraction) is called on the worker thread.
    """
    if sys.platform != "win32":
        raise AiSetupError("Automatic AI installation currently supports Windows only.")
    root = ai_root()
    _validate_folder(root)
    if is_ai_installed():
        if notify:
            notify("AI already installed", 1.0)
        return
    model_dir = root / "models"
    _validate_folder(model_dir)
    if notify:
        notify("Preparing optional AI", 0)
    archive = root / "runtime-download.zip"
    _download_pinned(RUNTIME_URL, archive, RUNTIME_SHA256,
                     RUNTIME_MAX_BYTES, notify, "Downloading AI engine")
    runtime = root / "runtime"
    existing_server = _server_file(root)
    if existing_server is None:
        staging = root / ("runtime-stage-" + uuid.uuid4().hex)
        try:
            server = _extract_runtime(archive, staging)
            if server.stat().st_size < 100_000:
                raise AiSetupError("Unexpected local AI executable.")
            if runtime.exists():
                current = list(runtime.rglob(SERVER_NAME))
                if (len(current) != 1 or not _safe_regular_file(current[0])
                        or _hash_file(current[0]) != _hash_file(server)):
                    raise AiSetupError("Existing AI runtime needs manual repair.")
                # Reuse our byte-identical runtime after an interrupted model download.
            else:
                os.replace(staging, runtime)
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
    if archive.exists() and not archive.is_symlink():
        archive.unlink()
    if notify:
        notify("Downloading AI model", 0)
    model = model_dir / MODEL_FILENAME
    _download_pinned(MODEL_URL, model, MODEL_SHA256,
                     MODEL_MAX_BYTES, notify, "Downloading AI model")
    metadata = {
        "version": RUNTIME_VERSION,
        "runtime_sha256": RUNTIME_SHA256,
        "model_sha256": MODEL_SHA256,
    }
    temp = root / ("." + uuid.uuid4().hex + ".json")
    try:
        temp.write_text(json.dumps(metadata), encoding="utf-8")
        if (root / INSTALL_METADATA).is_symlink() or _has_reparse_component(root):
            raise AiSetupError("The AI metadata destination was redirected.")
        os.replace(temp, root / INSTALL_METADATA)
    finally:
        if temp.exists():
            temp.unlink()
    if not is_ai_installed():
        raise AiSetupError("AI setup did not finish correctly.")
    if notify:
        notify("AI ready", 1.0)


def _port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop_ai() -> None:
    global _process, _endpoint, _api_key
    with _lock:
        proc = _process
        _process = None
        _endpoint = None
        _api_key = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    proc.kill()
                except OSError:
                    pass


atexit.register(stop_ai)


def local_server() -> tuple[str, str]:
    """Start pinned CPU-only inference on demand, returning endpoint and token."""
    global _process, _endpoint, _api_key
    if sys.platform != "win32":
        raise AiSetupError("The bundled local model currently supports Windows only.")
    with _lock:
        if _process is not None and _process.poll() is None and _endpoint and _api_key:
            return _endpoint, _api_key
        if not is_ai_installed():
            raise AiSetupError("Enable AI in Settings to install its optional components.")
        root = ai_root()
        executable = _server_file(root)
        model = root / "models" / MODEL_FILENAME
        if executable is None or _hash_file(model) != MODEL_SHA256:
            raise AiSetupError("AI components failed verification. Reinstall the optional AI pack.")
        token = secrets.token_urlsafe(32)
        port = _port()
        args = [
            str(executable), "--model", str(model), "--alias", "Game Grave AI", "--host", "127.0.0.1",
            "--port", str(port), "--api-key", token,
            "--no-webui", "--ctx-size", "2048", "--threads", "4",
            "--gpu-layers", "0",
        ]
        try:
            proc = subprocess.Popen(
                args, cwd=str(executable.parent),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise AiSetupError("Could not start the built-in AI engine.") from exc
        endpoint = f"http://127.0.0.1:{port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 55
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise AiSetupError("The local AI engine exited unexpectedly.")
            try:
                request = urllib.request.Request(endpoint + "/health",
                    headers={"Authorization": "Bearer " + token})
                with opener.open(request, timeout=2) as response:
                    if response.status == 200:
                        _process = proc
                        _endpoint = endpoint
                        _api_key = token
                        return endpoint, token
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
            time.sleep(0.3)
        proc.terminate()
        raise AiSetupError("The AI engine did not become ready. Try again.")
