"""Optional, private AI chat. Never scans files or authorizes cleanup.

Requires a user-installed local Ollama model. Not bundled with Game Grave.
Only the user's question and anonymous aggregate scan counts are sent to
127.0.0.1, with system proxy settings explicitly disabled.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

ENDPOINT = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen2.5:3b"
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
MAX_QUESTION = 800
MAX_REPLY = 5000
SYSTEM_PROMPT = (
    "You are Game Grave's optional, LOCAL ONLY gaming-storage advisor. "
    "Be concise, practical, and honest about uncertainty. "
    "You may explain storage findings, mod management, recovery, and safe review. "
    "Counts are aggregate only: you have no access to actual file paths, contents, "
    "screenshots, private game lists, or deletion authority. "
    "Never claim to have inspected a specific file, verified an uninstall, "
    "or performed any operation. Never tell the user a folder is definitely safe "
    "to remove from counts alone. Game Grave's deterministic protections and "
    "explicit confirmation always decide whether a move to Recycle Bin is allowed. "
    "You cannot bypass safety checks, change settings, or delete files."
)


class AssistantUnavailable(RuntimeError):
    """AI is disabled, misconfigured or its local model is not ready."""


def aggregate_scan_context(inventory=None) -> dict[str, int]:
    """Only anonymous counts, never file names, locations or user records."""
    if inventory is None:
        return {}
    if isinstance(inventory, dict):
        allowed = ("games", "mods", "files", "recordings", "screenshots", "saves", "graveyard")
        return {name: min(inventory[name], 1000000) for name in allowed
                if type(inventory.get(name)) is int and inventory[name] >= 0}
    result = {}
    for name in ("games", "mods", "files", "recordings", "screenshots", "saves", "graveyard"):
        items = getattr(inventory, name, None)
        if items is not None:
            try:
                result[name] = min(len(items), 1000000)
            except TypeError:
                pass
    return result


def _model_name(settings: dict) -> str:
    name = settings.get("ai_model", DEFAULT_MODEL)
    if not isinstance(name, str) or not MODEL_PATTERN.fullmatch(name):
        raise AssistantUnavailable("Choose a valid local model name in Settings.")
    return name


def ask_local_assistant(question: str, settings: dict, inventory=None) -> str:
    """Query an installed local Ollama model on demand. No autonomous actions.

    This function must run on a background UI thread. It never calls external
    hosts, cannot select arbitrary URLs, and does not save conversations.
    """
    if settings.get("ai_assistant_enabled") is not True:
        raise AssistantUnavailable("Enable the optional AI Assistant in Settings first.")
    if not isinstance(question, str) or not question.strip():
        raise AssistantUnavailable("Type a question first.")
    question = question.strip()
    if len(question) > MAX_QUESTION:
        raise AssistantUnavailable("Please keep questions to 800 characters or fewer.")
    model = _model_name(settings)
    context = aggregate_scan_context(inventory)
    context_line = ("Current aggregate scan counts: " + json.dumps(context, sort_keys=True)
                    if context else "No scan counts available.")
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + "\n" + context_line},
            {"role": "user", "content": question},
        ],
        "options": {"temperature": 0.2, "num_predict": 450},
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Prevent a machine's HTTP_PROXY environment variables from moving local
    # questions to any remote service.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=90) as response:
            if response.status != 200:
                raise AssistantUnavailable("The local AI service could not complete the request.")
            raw = response.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            raise AssistantUnavailable("The local AI returned an oversized response.")
        reply = json.loads(raw.decode("utf-8"))
        answer = reply.get("message", {}).get("content", "")
        if not isinstance(answer, str) or not answer.strip():
            raise AssistantUnavailable("The local model returned no answer.")
        return answer.strip()[:MAX_REPLY]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise AssistantUnavailable(
                f"Local model '{model}' is not installed. Run: ollama pull {model}"
            ) from None
        raise AssistantUnavailable(f"Local AI service returned HTTP {exc.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AssistantUnavailable(
            "Local AI is unavailable. Install Ollama, run 'ollama serve', "
            f"then 'ollama pull {model}'. No cloud connection was attempted."
        ) from None
    except (ValueError, UnicodeError, TypeError, KeyError):
        raise AssistantUnavailable("Local AI returned an unreadable response.") from None
