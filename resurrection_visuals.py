"""Resurrection Lab visual walkthrough. Native, responsive and read-only.

Small text-based guide is always present alongside the diagram. Drawing never
touches game files, starts scans or implies that ZIP integrity means a game works.
"""
from __future__ import annotations

import tkinter as tk


def resurrection_steps() -> tuple[tuple[str, str, str], ...]:
    return (
        ("PICK", "Choose your folders", "You approve saves, mods and profiles"),
        ("SEAL", "Verify the kit", "The archive gets a SHA-256 check"),
        ("REHEARSE", "Try an isolated restore", "Hashes match; live game untouched"),
        ("STAGE", "Move or roll back safely", "Use a new folder, then reconnect"),
    )


def _card(canvas, x0, y0, x1, y1, number, title, description, colors, highlighted=False):
    fill = colors["raised"]
    outline = colors["accent"] if highlighted else colors["line"]
    canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, width=2 if highlighted else 1)
    canvas.create_rectangle(x0 + 8, y0 + 8, x0 + 11, y1 - 8,
                            fill=colors["accent"] if highlighted else colors["blue"],
                            outline="")
    canvas.create_text(x0 + 23, y0 + 15, text=f"{number:02d}", anchor="w",
                       font=("Segoe UI Semibold", 10), fill=colors["accent"])
    canvas.create_text(x0 + 23, y0 + 39, text=title, anchor="w",
                       font=("Segoe UI Semibold", 12), fill=colors["text"])
    canvas.create_text(x0 + 23, y0 + 65, text=description, anchor="w",
                       font=("Segoe UI", 9), fill=colors["muted"])


def render_resurrection_flow(canvas, width: int, colors: dict) -> int:
    """Draw compact cards at large and small widths, return the display height."""
    canvas.delete("all")
    width = max(300, int(width))
    wide = width >= 760
    cards = resurrection_steps()
    margin = 12
    gap = 15
    if wide:
        card_width = (width - 2 * margin - 3 * gap) / 4
        height = 112
        for idx, (name, title, description) in enumerate(cards):
            left = margin + idx * (card_width + gap)
            _card(canvas, left, 8, left + card_width, 91, idx + 1,
                  name, title, colors, highlighted=(idx == 2))
            if idx < 3:
                canvas.create_line(left + card_width + 2, 49,
                    left + card_width + gap - 3, 49,
                    fill=colors["accent"], width=2, arrow="last")
    else:
        card_width = (width - 2 * margin - gap) / 2
        height = 204
        for idx, (name, title, description) in enumerate(cards):
            row, col = divmod(idx, 2)
            left = margin + col * (card_width + gap)
            top = 8 + row * 96
            _card(canvas, left, top, left + card_width, top + 84, idx + 1,
                  name, title, colors, highlighted=(idx == 2))
    canvas.configure(height=height, bg=colors["panel"])
    return height


def resurrection_guide(parent, *, colors: dict) -> tk.Frame:
    root = tk.Frame(parent, bg=colors["panel"])
    tk.Label(root, text="YOUR RESURRECTION JOURNEY",
             fg=colors["text"], bg=colors["panel"],
             font=("Segoe UI Semibold", 12), anchor="w").pack(fill="x")
    tk.Label(root, text="Four simple steps. Your live game files stay untouched.",
             fg=colors["muted"], bg=colors["panel"],
             font=("Segoe UI", 10), anchor="w").pack(fill="x", pady=(4, 7))
    canvas = tk.Canvas(root, bg=colors["panel"], height=204, highlightthickness=0)
    canvas.pack(fill="x")
    previous = {"width": 0}
    def resized(event=None):
        width = canvas.winfo_width()
        if width >= 300 and previous["width"] != width:
            previous["width"] = width
            render_resurrection_flow(canvas, width, colors)
    canvas.bind("<Configure>", resized)
    # Semantic text counterpart for users who cannot see the diagram.
    description = "  |  ".join(f"{i+1}. {title}: {note}"
                              for i, (name, title, note) in enumerate(resurrection_steps()))
    description_label = tk.Label(
        root, text=description, fg=colors["muted"], bg=colors["panel"],
        font=("Segoe UI", 9), wraplength=390,
        justify="left", anchor="w")
    description_label.pack(fill="x", pady=(7, 8))
    caution_label = tk.Label(
        root,
        text="Verified archive ≠ verified game compatibility. No automatic live rollback.",
        fg=colors["warn"], bg=colors["panel"],
        font=("Segoe UI Semibold", 10),
        wraplength=390, justify="left", anchor="w")
    caution_label.pack(fill="x")
    def wrap_text(event):
        bound = max(260, event.width - 20)
        description_label.configure(wraplength=bound)
        caution_label.configure(wraplength=bound)
    root.bind("<Configure>", wrap_text)
    return root
