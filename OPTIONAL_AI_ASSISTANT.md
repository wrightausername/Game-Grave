# Built-in Optional AI Assistant (Windows engineering preview)

Game Grave AI is **off by default** and never required for scanning, Mod Radar, Graveyard or recovery. Customers do not need to know about Ollama, install external software, type commands or buy an AI subscription.

## Customer setup

1. Open **Settings > AI Assistant** in either desktop interface.
2. Tick **Enable AI Assistant**.
3. Approve the one-time model download (approximately 1.2 GB).
4. Game Grave downloads the local inference engine and the model into its own local per-user data folder; integrity checks are required before it becomes available.
5. Installation progress is shown in Settings. When it finishes, click **Open AI Assistant**.

No background or automatic download starts while AI is disabled. The rest of Game Grave works without it. On supported Windows PCs, a local inference server starts when asked and is stopped when the program exits.

## What customers can ask

The assistant is built to be the built-in help desk for Game Grave, including:
- Starting a scan, understanding findings and navigation
- Graveyard review, protection rules and why deletion is blocked
- Mod Radar, Game DNA, MO2/Vortex considerations
- Steam, Epic, EA, Ubisoft, GOG, Blizzard and other launcher discovery
- Screenshots, recordings and safe review
- Undo Center, Resurrection Kit, Save Vault and recovery limitations
- Settings, Free versus future lifetime Pro and preview limitations
- Common troubleshooting questions and warnings

The versioned local help facts in ai_help.py ground answers in documented features. The AI explains steps but does not actually operate any controls, cannot diagnose unobserved system state, and may still make mistakes. It should say when more information is needed instead of inventing options.

## Asset integrity and security

The optional components are pinned:
- llama.cpp Windows CPU x64 b12020 runtime from the official GitHub release; verify SHA-256 07e81782f5a16c7ffef42403183808e02f271c9ece3aa2d64040b2620ae8d519.
- Qwen2.5-1.5B-Instruct-GGUF Q4_K_M from the official Qwen Hugging Face repository; verify SHA-256 6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e.

These optional downloads require internet initially, but generation runs locally after installation. Neither is bundled in the main executable; this preserves its small size. Third-party license and notices require commercial redistribution review prior to a stable release.

## Privacy and safety

- Only the question typed by the customer and anonymous aggregate scan counts are passed to the local inference server bound to 127.0.0.1.
- The app does not automatically send game titles, filenames, filesystem paths, file contents, screenshots, payment records, or chat history.
- AI cannot scan, move files to the Recycle Bin, delete, unprotect, change settings, or override independent safety checks.
- AI messages are not persisted by Game Grave; the separately installed service compatibility mode may have its own data-handling behaviors.
- AI is optional. AI setup and calls run off the UI thread and cannot block the usual cleanup workflows.
- Existing users of a standalone Ollama installation can still use it as a compatibility fallback; *new users never need to install Ollama themselves*.

## Testing and release gate

This is an engineering implementation, not proof of production readiness. Before a retail release, verify on Windows 10/11 with real hardware:
- Signed-hash-verified first install and interrupted-download recovery
- CPU/RAM/disk impact and responsiveness on low-end PCs
- Windows Defender / firewall compatibility
- Privacy by monitoring network requests on local and cloud interfaces
- Full native packaging of ai_bundle.py, ai_help.py, ai_tk.py and gg_desktop/ai_dialog.py
- Successful fully local question-answer cycle and grounded how-to answers
- AI disabled by default with zero background requests
- Correct error messages and no file modification authority
- Install/uninstall lifecycle, and third-party notices/licenses

The Windows preview is unsigned and should not be distributed commercially until remaining release gates are met.
