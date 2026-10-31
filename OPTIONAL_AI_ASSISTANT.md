# Optional Local AI Assistant (engineering feature)

Game Grave can use a **separately installed** Ollama local language model to explain gaming-storage findings and answer questions. The assistant is **off by default** and is entirely optional. Ordinary scanning, Graveyard, Mod Radar, safety rules, and recovery work without it.

## Enable on Windows

1. Install Ollama from its official website: https://ollama.com/download/windows
2. Open PowerShell and run: ollama pull qwen2.5:1.5b
3. Make sure Ollama is running on this PC. If needed, run: ollama serve
4. Open **Game Grave > Settings > AI Assistant** (classic) or **Settings > Local AI Assistant** (Crimson Qt preview).
5. Check **Enable optional local AI Assistant**, then click **Open local AI Assistant**.
6. Ask a question. The first local generation may take time on slower CPUs.

You may choose another already installed model by entering its Ollama model identifier in Settings, saving it, and reopening the assistant.

**Nothing is downloaded or installed by Game Grave itself.** Not enabling AI incurs no model storage, performance overhead, or service requests.

## Privacy and safety contract

- The only automatic request goes to http://127.0.0.1:11434/api/chat, on this computer. An HTTP proxy is explicitly bypassed.
- The request includes your manually typed question and, where available, **aggregate counts** of local scan findings (e.g., number of games, mods, screenshots, or Graveyard items).
- It does **not** automatically include game names, file paths, file contents, mods, screenshots, serial numbers, personal customer records, billing information, or logs.
- Game Grave does not persist chat transcripts, upload them to a cloud AI service, or collect AI analytics. Ollama and any model packages are third-party local software governed by their own privacy and operational behavior.
- AI **cannot initiate scanning, unprotect files, recycle files, delete data, restore data, install updates, or change settings**.
- File cleanup continues to require existing rule-based eligibility checks and explicit human confirmation; AI opinions have no effect on those checks.
- Responses may be inaccurate or incomplete. Don't rely on an AI suggestion as proof that a file or mod folder is unused.
- Turning off the checkbox blocks future assistant requests. An already-running local generation may finish; the checkbox does not stop Ollama's independent service.

## Architecture

- local_ai.py: pure-Python optional local HTTP client, bounded inputs/outputs, fixed loopback-only endpoint, no cleanup interfaces.
- ai_tk.py: optional classic UI chat, worker thread and queue so a slow model does not freeze the interface.
- gg_desktop/ai_dialog.py: optional Crimson Qt chat via existing UI job worker.
- core.default_settings(): disabled by default with a model identifier preference.
- tests/test_optional_local_ai.py: default-off, no-request, context minimization, fixed endpoint, disabled proxy, invalid model, and unavailable-service behavior.

## Limits and deployment

This is an **initial integration**, not a bundled offline model or a fully polished AI assistant release. On-device performance and RAM usage depend on the model and hardware. A hosted inference service or downloadable model packs are *not* enabled. The assistant does not know exact file ownership or permissions and cannot safely determine deletion eligibility on its own.

Acceptance for a Windows release includes classic and Qt smoke testing, running with no Ollama installed, confirming zero background requests while disabled, checking a locally installed model, verifying no file paths in outgoing requests, and user-facing failure messages.
