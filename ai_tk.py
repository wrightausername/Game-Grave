"""A small, optional local AI dialog for the classic Tk interface."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

from local_ai import AssistantUnavailable, ask_local_assistant


def open_local_ai_dialog(app):
    if app.settings.get("ai_assistant_enabled") is not True:
        from tkinter import messagebox
        messagebox.showinfo("AI Assistant disabled",
                            "Enable Local AI Assistant under Settings first.", parent=app)
        return

    prior = getattr(app, "_local_ai_dialog", None)
    if prior is not None and prior.winfo_exists():
        prior.lift()
        prior.focus_force()
        return

    window = tk.Toplevel(app)
    app._local_ai_dialog = window
    window.title("Game Grave | Local AI Assistant")
    window.geometry("650x500")
    window.minsize(460, 350)

    body = ttk.Frame(window, padding=14)
    body.pack(fill="both", expand=True)
    ttk.Label(
        body, wraplength=590, justify="left",
        text=("Optional AI, installed directly by Game Grave when enabled in Settings. "
              "No cloud upload or file inspection; only anonymous scan counts "
              "are included automatically. Nothing can be deleted by AI. "
              "Chat is not saved."),
    ).pack(fill="x", pady=(0, 10))

    transcript = tk.Text(body, wrap="word", state="disabled", height=17)
    transcript.pack(fill="both", expand=True, pady=(0, 10))

    bar = ttk.Frame(body)
    bar.pack(fill="x")
    prompt_var = tk.StringVar()
    entry = ttk.Entry(bar, textvariable=prompt_var)
    entry.pack(side="left", fill="x", expand=True, padx=(0, 9))
    action = ttk.Button(bar, text="Ask local AI")
    action.pack(side="right")
    status_var = tk.StringVar(value="Built-in local AI • no account or subscription")
    ttk.Label(body, textvariable=status_var, wraplength=590).pack(anchor="w", pady=(8, 0))

    responses = queue.Queue()
    busy = False

    def append(text):
        transcript.configure(state="normal")
        transcript.insert("end", text + "\n\n")
        transcript.see("end")
        transcript.configure(state="disabled")

    def poll():
        nonlocal busy
        if not window.winfo_exists():
            return
        try:
            ok, reply = responses.get_nowait()
        except queue.Empty:
            pass
        else:
            append(("Assistant: " if ok else "Assistant unavailable: ") + reply)
            busy = False
            entry.configure(state="normal")
            action.configure(state="normal")
            status_var.set("Ready. AI never changes files.")
            entry.focus_set()
        app.after(130, poll)

    def submit(_event=None):
        nonlocal busy
        question = prompt_var.get().strip()
        if not question or busy:
            return
        if len(question) > 800:
            status_var.set("Keep questions to 800 characters or fewer.")
            return
        append("You: " + question)
        prompt_var.set("")
        busy = True
        entry.configure(state="disabled")
        action.configure(state="disabled")
        status_var.set("Waiting for local AI. No cloud request is made.")
        settings = dict(app.settings)
        # Count metadata only; never send actual game lists or file paths.
        summary = {}
        for name in ("games", "mods", "files", "recordings", "screenshots", "saves", "graveyard"):
            records = getattr(app, name, None)
            if records is not None:
                try:
                    summary[name] = len(records)
                except TypeError:
                    pass

        def worker():
            try:
                answer = ask_local_assistant(question, settings, summary)
                responses.put((True, answer))
            except AssistantUnavailable as exc:
                responses.put((False, str(exc)))
            except Exception:
                responses.put((False, "An unexpected local AI error occurred. No files changed."))

        threading.Thread(target=worker, daemon=True).start()

    action.configure(command=submit)
    entry.bind("<Return>", submit)
    poll()
    entry.focus_set()
