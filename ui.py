"""Game Grave dark-theme Windows desktop UI. No third-party packages required."""
from __future__ import annotations

import os
import json
import queue
import subprocess
import sys
import threading
import time
import zipfile
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from graveyard import build_graveyard, looks_like_game_archive
from cleanup_actions import recycle_reviewed_entries, recycle_old_files
from safety_selftest import check_disposable_undo, SafetySelfCheckError
from graveyard_protection import protection_action, set_item_protection
from recordings import find_old_recordings, RECORDING_EXTENSIONS
from duplicates import inspect_duplicate_archives
from ui_presets import (MAX_PRESETS, capture_presentation, normalize_color, validate_name,
                        read_preset_file, sanitize_local_presets, write_preset_file)
from view_options import (GRAVE_SORT_KEYS, SORT_DIRECTIONS, GRAVE_STATES, GRAVE_SIZES,
    GRAVE_PRESET_FIELDS, GAMES_SORT_OPTIONS, MOD_SORT_OPTIONS, FILES_SORT_OPTIONS,
    filter_sort_graveyard, sanitize_saved_views, sort_games, sort_mods, sort_files)
from insights import load_history, record_scan, compare_scans, make_room_plan
from recovery import register_recycle, get_records, check_restore, restore
from explainer import explain_folder
from file_detective import investigate, friendly_report
from game_intelligence import (build_game_dna, capture_mod_observation, load_observation,
                               save_observation, ghost_watch, what_broke_my_game,
                               patch_fallout, regret_calculator, exodus_plan)
from resurrection_kit import create_resurrection_kit
from resurrection_v2 import create_complete_kit, inspect_restore, restore_kit
from kit_discovery import discover_setup, select_sources
from mo2_reconnect import preview_mo2_reconnect, reconnect_to_mo2
from resurrection_v2 import _manifest_for
from resurrection_lab import (
    missing_pieces, compare_kits, plan_living_update, create_living_update,
    rehearse_kit, list_snapshots, prepare_pc_transfer,
)
from resurrection_visuals import resurrection_guide
from ui_shortcuts import PAGE_SHORTCUTS, shortcut_help_text
from ui_viewport import initial_window_bounds
from ui_scroll import page_wheel_allowed
from ui_paging import page_window, DEFAULT_PAGE_SIZE
from kit_watch import register_kit_watch, list_kit_watches, check_kit_watches, stop_kit_watch
from manager_profiles import inspect_manager_profiles, summarize_manager_profile
from mod_radar_audit import audit_mod_radar, private_audit_summary
from dna_visuals import dna_visual, mod_radar_visual
from space_planner import plan_for_drive
from launchers import LauncherGame, find_launcher_games
from save_vault import create_backup
from save_discovery import discover_saves
from scan_progress import STAGES, eta_seconds, format_eta
from shader_cache import inspect_steam_shader_cache, file_still_matches
from activity_history import group_activity, session_caption
from licensing import (LicenseError, activation_ready, activate_key, read_edition,
                       remove_local_activation)
from updates import UpdateError, check_for_updates, update_ready

from core import (
    APP_NAME, AUTO_BASE_EXTENSIONS, AUTO_EXTRA_EXTENSIONS, GAME_AGE_OPTIONS, TASK_NAME,
    SteamGame, ModFolder, OldFile, age_text, config_dir, default_settings, downloads_dir,
    export_activity_csv, find_games, find_all_mod_storage, friendly_activity, get_activity, human_size,
    is_game_neglected, is_unchanged, load_settings, log_event,
    recycle_file, run_auto_cleanup, safe_scan_root, save_settings, scan_old_files, is_protected_path,
)

BG = "#0B101A"
SIDEBAR = "#101827"
PANEL = "#172133"
RAISED = "#1D2A3C"
TEXT = "#ECF2FC"
MUTED = "#9DAEC5"
ACCENT = "#50DCC5"
BLUE = "#6B9EFF"
WARN = "#FFCD7E"
RED = "#FF8989"
LINE = "#303C50"
ON_ACCENT = "#071721"


def readable_foreground(hex_color: str) -> str:
    """Choose whichever of near-black and white contrasts better with custom accent."""
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    luminance = sum(v * k for v, k in zip(linear, (0.2126, 0.7152, 0.0722)))
    return "#071721" if (luminance + 0.05) / 0.057 > 1.05 / (luminance + 0.05) else "#FFFFFF"


def apply_palette(settings):
    """Accessible, user-selected palette. All colors are local preferences."""
    global BG, SIDEBAR, PANEL, RAISED, TEXT, MUTED, ACCENT, BLUE, WARN, RED, LINE, ON_ACCENT
    light = settings.get("ui_theme") == "light"
    if settings.get("ui_theme") == "system":
        # Read Windows app color preference only when settings are applied.
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                  r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                light = winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 1
        except (ImportError, OSError):
            light = False
    BG, SIDEBAR, PANEL, RAISED = (("#F3F6FA", "#FFFFFF", "#FFFFFF", "#E5EDF5") if light else
                                   ("#0B101A", "#101827", "#172133", "#1D2A3C"))
    TEXT, MUTED = (("#162638", "#4A6178") if light else ("#ECF2FC", "#9DAEC5"))
    palette = {"teal": ("#147A68" if light else "#50DCC5"),
               "blue": ("#205FC3" if light else "#6B9EFF"),
               "purple": ("#6947BD" if light else "#B9A0FF"),
               "orange": ("#9C510C" if light else "#FFBB7A")}
    if settings.get("ui_accent") == "custom":
        try:
            ACCENT = normalize_color(settings.get("ui_custom_accent"))
        except ValueError:
            ACCENT = palette["teal"]
    else:
        ACCENT = palette.get(settings.get("ui_accent"), palette["teal"])
    ON_ACCENT = readable_foreground(ACCENT)
    BLUE, WARN, RED, LINE = (("#205FC3", "#935100", "#AC2A2A", "#D5DEE9") if light else
                             ("#6B9EFF", "#FFCD7E", "#FF8989", "#303C50"))


class GameGraveApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Game Grave v2.4 | Gaming Storage Manager")
        bounds = initial_window_bounds(self.winfo_screenwidth(), self.winfo_screenheight())
        self.geometry(f"{bounds.width}x{bounds.height}+{bounds.left}+{bounds.top}")
        self.minsize(bounds.min_width, bounds.min_height)
        self.configure(bg=BG)
        self.settings = load_settings()
        self.edition = read_edition()  # Free unless a genuine signed license is verified
        apply_palette(self.settings)
        self.tk.call("tk", "scaling", {"compact": 1.0, "normal": 1.16, "large": 1.42}.get(self.settings.get("ui_scale"), 1.16))
        self.configure(bg=BG)
        self.games: list[SteamGame] = []
        self.other_games: list[LauncherGame] = []
        self.mod_folders: list[ModFolder] = []
        self.old_files: list[OldFile] = []
        self.recordings: list[OldFile] = []
        self.save_findings = []
        self.profile_report = None
        self._scan_started = 0.0
        self._scan_stage = 0
        self._scan_stage_name = ""
        self.scan_progress_text = tk.StringVar(value="Ready to scan")
        self.scan_percent = tk.DoubleVar(value=0)
        self.graveyard_entries = []
        self.graveyard_lookup = {}
        self.grave_checked: set[str] = set()
        self.file_lookup: dict[str, OldFile] = {}
        self.game_lookup: dict[str, SteamGame] = {}
        self._pager_indices = {}
        self._pager_controls = {}
        self.active = "Overview"
        self.scanning = False
        self.cleanup_running = False
        self._selfcheck_busy = False
        self.last_scan: str | None = None
        self.status_text = tk.StringVar(value="Ready. Choose Scan PC to begin. No background scan is running.")
        self.events: queue.Queue = queue.Queue()
        self._cancel_scan = threading.Event()
        self._ui_style()
        self._layout()
        self._install_keyboard_shortcuts()
        self.show_page("Overview")
        self.after(120, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close_safely)
        if self.settings.get("scan_on_launch", False):
            self.after(250, self.scan_all)

    def _close_safely(self):
        if self.cleanup_running or self._selfcheck_busy:
            messagebox.showinfo("Cleanup still running",
                                "Wait for the current Windows Recycle Bin check to finish. "
                                "Closing now could interrupt recovery records.")
            return
        self.destroy()

    def _ui_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Data.Treeview", background=PANEL, foreground=TEXT,
                        fieldbackground=PANEL, borderwidth=0, relief="flat",
                        rowheight=34, font=("Segoe UI", 10))
        style.map("Data.Treeview", background=[("selected", ACCENT)],
                  foreground=[("selected", ON_ACCENT)])
        style.configure("Data.Treeview.Heading", background=RAISED, foreground=TEXT,
                        font=("Segoe UI Semibold", 10), relief="flat", padding=(12, 10))
        style.map("Data.Treeview.Heading", background=[("active", PANEL)])
        style.configure("GG.Horizontal.TProgressbar", troughcolor=RAISED, background=ACCENT,
                        thickness=7, borderwidth=0)
        style.configure("Dark.TCombobox", fieldbackground=RAISED, background=RAISED,
                        foreground=TEXT, arrowcolor=TEXT)
        style.map("Dark.TCombobox", fieldbackground=[("readonly", RAISED)],
                  foreground=[("readonly", TEXT)], selectbackground=[("readonly", RAISED)])
        style.configure("Dark.TCheckbutton", background=PANEL, foreground=TEXT,
                        font=("Segoe UI", 10))
        style.map("Dark.TCheckbutton", background=[("active", PANEL)],
                  foreground=[("disabled", MUTED)])
        style.configure("Dark.Vertical.TScrollbar", background=RAISED, troughcolor=BG)
        style.configure("Dust.TNotebook", background=BG, borderwidth=0)
        style.configure("Dust.TNotebook.Tab", background=RAISED, foreground=TEXT,
                        font=("Segoe UI Semibold", 10), padding=(17, 12), borderwidth=0)
        style.map("Dust.TNotebook.Tab", background=[("selected", PANEL)],
                  foreground=[("selected", ACCENT)])

    def _layout(self):
        self.sidebar = tk.Frame(self, bg=SIDEBAR, width=224)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        brand = tk.Frame(self.sidebar, bg=SIDEBAR)
        brand.pack(fill="x", padx=21, pady=(25, 22))
        tk.Label(brand, text="◉", bg=SIDEBAR, fg=ACCENT,
                 font=("Segoe UI", 23)).pack(side="left", padx=(0, 10))
        tk.Label(brand, text="Game Grave", bg=SIDEBAR, fg=TEXT,
                 font=("Segoe UI Semibold", 21)).pack(side="left")
        tk.Label(self.sidebar, text="YOUR GAMING STORAGE", bg=SIDEBAR, fg=MUTED,
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=23, pady=(0, 13))
        # Navigation must remain reachable even when all 14 entries exceed
        # the available laptop height or the user selects large text.
        self.nav_container = tk.Frame(self.sidebar, bg=SIDEBAR)
        self.nav_container.pack(fill="both", expand=True)
        self.nav_canvas = tk.Canvas(self.nav_container, bg=SIDEBAR,
                                    highlightthickness=0, borderwidth=0)
        self.nav_scrollbar = ttk.Scrollbar(
            self.nav_container, orient="vertical", command=self.nav_canvas.yview)
        self.nav_canvas.configure(yscrollcommand=self.nav_scrollbar.set)
        self.nav_scrollbar.pack(side="right", fill="y")
        self.nav_canvas.pack(side="left", fill="both", expand=True)
        self.nav_list = tk.Frame(self.nav_canvas, bg=SIDEBAR)
        self._nav_window = self.nav_canvas.create_window(
            (0, 0), window=self.nav_list, anchor="nw")
        self.nav_list.bind("<Configure>", lambda _e:
                           self.nav_canvas.configure(scrollregion=self.nav_canvas.bbox("all")))
        self.nav_canvas.bind("<Configure>", lambda e:
                             self.nav_canvas.itemconfigure(self._nav_window, width=e.width))
        self.nav_buttons = {}
        # Simple mode shows only primary destinations. Secondary tools remain reachable
        # from Overview and Settings; advanced mode restores every sidebar link.
        items = [("Overview", "▦"), ("Steam Games", "▣"), ("Other Launchers", "▣"),
                 ("Game Mods", "◇"), ("The Graveyard", "☠"), ("Game DNA", "⌁"),
                 ("Save Vault", "♡"), ("Undo Center", "↶"), ("Settings", "⚙")]
        if self.settings.get("ui_layout") == "advanced":
            items = [("Overview", "▦"), ("Steam Games", "▣"), ("Other Launchers", "▣"),
                     ("Game Mods", "◇"), ("Old Files", "▤"), ("The Graveyard", "☠"),
                     ("Make Room", "◉"), ("Game DNA", "⌁"), ("Save Vault", "♡"),
                     ("Undo Center", "↶"), ("Cleanup History", "◷"), ("Storage History", "◷"),
                     ("Automation", "◴"), ("Settings", "⚙")]
        for title, symbol in items:
            b = tk.Button(self.nav_list, text=f"{symbol}    {title}", anchor="w",
                          font=("Segoe UI", 11), bg=SIDEBAR, fg=MUTED,
                          bd=0, highlightthickness=1, highlightcolor=ACCENT,
                          highlightbackground=SIDEBAR, takefocus=1,
                          relief="flat", padx=21, pady=10,
                          cursor="hand2", command=lambda n=title: self.show_page(n))
            b.pack(fill="x", padx=9, pady=1)
            self.nav_buttons[title] = b
        tk.Label(self.sidebar, text=f"{self.edition.name.upper()} EDITION  •  LOCAL-FIRST", bg=SIDEBAR, fg=MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=22, pady=(0, 8))
        tk.Label(self.sidebar, text="Game removals require approval", bg=SIDEBAR, fg=ACCENT,
                 font=("Segoe UI", 9), wraplength=175, justify="left").pack(anchor="w", padx=22, pady=(0, 25))

        self.main = tk.Frame(self, bg=BG)
        self.main.pack(side="left", fill="both", expand=True)
        top = tk.Frame(self.main, bg=BG, height=74)
        top.pack(fill="x", padx=30, pady=(14, 0))
        top.pack_propagate(False)
        tk.Label(top, textvariable=self.status_text, bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left", pady=17)
        self.scan_button = self.button(top, "↻  Scan PC", self.scan_all, primary=True)
        self.scan_button.pack(side="right", pady=8)
        self.cancel_button = self.button(top, "Cancel scan", self._cancel_active_scan)
        self.cancel_button.configure(state="disabled")
        self.cancel_button.pack(side="right", padx=(0, 10), pady=8)
        # Persistent progress strip. UI remains responsive while workers scan.
        self.progress_area = tk.Frame(self.main, bg=BG)
        self.progress_area.pack(fill="x", padx=30, pady=(0, 10))
        self.progress_bar = ttk.Progressbar(self.progress_area, style="GG.Horizontal.TProgressbar",
                                            maximum=100, variable=self.scan_percent,
                                            mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 4))
        self.progress_label = tk.Label(self.progress_area, textvariable=self.scan_progress_text,
                           bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.progress_label.pack(fill="x")
        # Keep crowded pages usable on 720p laptops and at larger DPI.
        # A scrollbar belongs to the page, not to its inner Treeviews.
        self.content_shell = tk.Frame(self.main, bg=BG)
        self.content_shell.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self.content_canvas = tk.Canvas(self.content_shell, bg=BG,
                                        highlightthickness=0, borderwidth=0,
                                        takefocus=0)
        self.content_scrollbar = ttk.Scrollbar(
            self.content_shell, orient="vertical",
            command=self.content_canvas.yview)
        self.content_canvas.configure(yscrollcommand=self.content_scrollbar.set)
        self.content_scrollbar.pack(side="right", fill="y")
        self.content_canvas.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(self.content_canvas, bg=BG)
        self._content_window = self.content_canvas.create_window(
            (0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._update_content_scrollregion)
        self.content_canvas.bind("<Configure>", self._fit_content_width)
        self.bind("<MouseWheel>", self._scroll_page_on_wheel, add="+")

    def _update_content_scrollregion(self, _event=None):
        """Update the outer page's scroll extent after page controls reflow."""
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _fit_content_width(self, event):
        self.content_canvas.itemconfigure(self._content_window, width=event.width)
        self._update_content_scrollregion()

    def _scroll_page_on_wheel(self, event):
        """Use the outer page wheel only if an inner scrollable does not own it."""
        try:
            found = self.winfo_containing(event.x_root, event.y_root)
            if found is None:
                return
            direction = -1 if event.delta > 0 else 1
            if (hasattr(self, "nav_list") and
                    page_wheel_allowed(found, self.nav_list, self.nav_canvas, ())):
                bounds = self.nav_canvas.bbox("all")
                if bounds and bounds[3] > self.nav_canvas.winfo_height():
                    self.nav_canvas.yview_scroll(direction * 3, "units")
                    return "break"
                return
            if not page_wheel_allowed(
                    found, self.content, self.content_canvas,
                    (ttk.Treeview, tk.Text, tk.Listbox, ttk.Combobox, ttk.Notebook)):
                return
            bounds = self.content_canvas.bbox("all")
            if not bounds or bounds[3] <= self.content_canvas.winfo_height():
                return
            self.content_canvas.yview_scroll(direction * 3, "units")
            return "break"
        except (tk.TclError, AttributeError):
            return

    def button(self, parent, label, command, primary=False, danger=False):
        fg = ON_ACCENT if primary else (RED if danger else TEXT)
        bg = ACCENT if primary else PANEL
        b = tk.Button(parent, text=label, command=command, bg=bg, fg=fg,
                      activebackground=ACCENT if primary else RAISED,
                      activeforeground=ON_ACCENT if primary else TEXT,
                      font=("Segoe UI Semibold", 10), padx=15, pady=9,
                      bd=0, relief="flat", highlightthickness=1,
                      highlightcolor=ACCENT, highlightbackground=LINE,
                      takefocus=1, cursor="hand2")
        return b

    def text(self, parent, value, size=11, fg=TEXT, bold=False, **kw):
        return tk.Label(parent, text=value, bg=parent.cget("bg"), fg=fg,
                        font=("Segoe UI Semibold" if bold else "Segoe UI", size),
                        justify="left", **kw)

    def header(self, title, subtitle):
        self.text(self.content, title, 25, bold=True).pack(anchor="w", pady=(3, 4))
        self.text(self.content, subtitle, 11, MUTED).pack(anchor="w", pady=(0, 14))

    def panel(self, parent=None, pad=19):
        frame = tk.Frame(parent or self.content, bg=PANEL, padx=pad, pady=pad,
                         highlightbackground=LINE, highlightthickness=1)
        return frame

    def _install_keyboard_shortcuts(self):
        """Navigation only, a read-only scan, and safe scan cancellation."""
        for shortcut, _label, destination in PAGE_SHORTCUTS:
            number = shortcut.removeprefix("Ctrl+")
            self.bind("<Control-KeyPress-" + number + ">",
                      lambda _event, page=destination: self._navigate_shortcut(page))
        self.bind("<F1>", self._open_keyboard_shortcuts)
        self.bind("<F5>", self._shortcut_scan)
        self.bind("<Escape>", self._shortcut_cancel_scan)

    def _scroll_navigation_to(self, page):
        """Reveal keyboard-selected navigation button even if below the fold."""
        if not hasattr(self, "nav_canvas"):
            return
        button = self.nav_buttons.get(page)
        if button is None:
            return
        try:
            self.nav_canvas.update_idletasks()
            top = self.nav_canvas.canvasy(0)
            height = self.nav_canvas.winfo_height()
            position = button.winfo_y()
            bottom = position + button.winfo_height()
            total = max(1, self.nav_list.winfo_height())
            if height <= 1:
                return
            if position < top:
                self.nav_canvas.yview_moveto(position / total)
            elif bottom > top + height:
                self.nav_canvas.yview_moveto(max(0, bottom - height) / total)
        except tk.TclError:
            return

    def _navigate_shortcut(self, page):
        self.show_page(page)
        control = self.nav_buttons.get(page, self.scan_button)
        if hasattr(self, "_scroll_navigation_to"):
            self._scroll_navigation_to(page)
        control.focus_set()
        return "break"

    def _shortcut_scan(self, _event=None):
        # F5 has the same behavior as the explicit "Scan PC" button.
        if not self.scanning:
            self.scan_all()
        return "break"

    def _shortcut_cancel_scan(self, _event=None):
        # Escape cannot invoke a recycle or other destructive action.
        if self.scanning:
            self._cancel_active_scan()
            return "break"

    def _open_keyboard_shortcuts(self, _event=None):
        existing = getattr(self, "_keyboard_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_set()
                    return "break"
            except tk.TclError:
                pass
        window = tk.Toplevel(self)
        self._keyboard_window = window
        window.title("Game Grave · Keyboard shortcuts")
        window.geometry("530x500")
        window.minsize(440, 450)
        window.configure(bg=BG)
        frame = self.panel(window, 16)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        self.text(frame, "Keyboard quick guide", 18, ACCENT, True).pack(
            anchor="w", pady=(0, 12))
        tk.Label(frame, text=shortcut_help_text(), bg=PANEL, fg=TEXT,
                 font=("Consolas", 11), justify="left", anchor="w",
                 wraplength=465).pack(anchor="w", fill="x")
        close = self.button(frame, "Close guide", window.destroy)
        close.pack(anchor="e", pady=(18, 0))
        window.bind("<Escape>", lambda _event: window.destroy())
        close.focus_set()
        return "break"

    def show_page(self, title):
        self.active = title
        if hasattr(self, "content_canvas"):
            self.content_canvas.yview_moveto(0)
        for name, b in self.nav_buttons.items():
            selected = name == title
            b.configure(bg=RAISED if selected else SIDEBAR, fg=ACCENT if selected else MUTED)
        for widget in self.content.winfo_children():
            widget.destroy()
        {
            "Overview": self._overview,
            "Steam Games": self._games_page,
            "Other Launchers": self._other_launchers_page,
            "Game Mods": self._mods_page,
            "Old Files": self._files_page,
            "The Graveyard": self._graveyard_page,
            "Make Room": self._make_room_page,
            "Game DNA": self._game_dna_page,
            "Undo Center": self._undo_page,
            "Cleanup History": self._activity_page,
            "Save Vault": self._save_vault_page,
            "Resurrection Lab": self._resurrection_lab_page,
            "Storage History": self._history_page,
            "Settings": self._settings_page,
            "Automation": self._automation_page,
            "Activity": self._activity_page,
        }[title]()

    def _overview(self):
        self.header("Take back your storage", "See what's been gathering digital dust before you remove anything.")
        metrics = tk.Frame(self.content, bg=BG)
        metrics.pack(fill="x", pady=(0, 13))
        stale = [g for g in self.games if is_game_neglected(g, self.settings["game_stale_days"])]
        unknown = [g for g in self.games if g.last_played is None]
        reviewable_files = {f.path: f.size for f in (*self.old_files, *self.recordings)}
        values = [
            ("GAMES FOUND", str(len(self.games) + len(self.other_games)), "Steam + discovered launchers"),
            ("LONG UNPLAYED", str(len(stale)), f"{self.settings['game_stale_days']}+ days, where known"),
            ("MOD FINDINGS", str(len(self.mod_folders)), "Steam / Workshop / mod managers"),
            ("REVIEWABLE SIZE", human_size(sum(g.size for g in stale) + sum(reviewable_files.values())),
             "not free space yet"),
        ]
        if not self.last_scan:
            values = [(label, "Not scanned", "Press Scan PC to inspect this computer") for label, _, _ in values]
        for index, (label, value, note) in enumerate(values):
            box = self.panel(metrics, 13)
            box.grid(row=0, column=index, sticky="nsew", padx=(0, 11) if index < 3 else 0)
            metrics.grid_columnconfigure(index, weight=1, uniform="metric")
            self.text(box, label, 9, MUTED, True).pack(anchor="w")
            self.text(box, value, 23, ACCENT, True).pack(anchor="w", pady=(10, 4))
            self.text(box, note, 9, MUTED, wraplength=160).pack(anchor="w")
        middle = self.panel()
        middle.pack(fill="x", pady=(0, 12))
        self.text(middle, "Your cleanup checklist", 15, bold=True).pack(anchor="w", pady=(0, 15))
        rows = [
            ("1", "Review unplayed games", f"{len(stale)} games have known old play dates; {len(unknown)} have unknown dates.",
             "View games", lambda: self.show_page("Steam Games")),
            ("2", "Review hidden game and mod storage", f"{len(self.mod_folders)} findings across game folders, Steam Workshop and mod managers.",
             "Review mods", lambda: self.show_page("Game Mods")),
            ("3", "Check old downloads and game clips", f"{len(self.old_files)} old files; {len(self.recordings)} possible old recordings.",
             "View files", lambda: self.show_page("Old Files")),
            ("4", "Make room for a game", "Enter a storage target and preview your review options.",
             "Make room", lambda: self.show_page("Make Room")),
        ]
        for idx, (num, title, description, action, callback) in enumerate(rows):
            strip = tk.Frame(middle, bg=PANEL, pady=5)
            strip.pack(fill="x")
            self.text(strip, num, 14, ACCENT, True).pack(side="left", padx=(5, 20))
            details = tk.Frame(strip, bg=PANEL)
            details.pack(side="left", fill="x", expand=True)
            self.text(details, title, 11, bold=True).pack(anchor="w")
            self.text(details, description, 9, MUTED).pack(anchor="w", pady=(4, 0))
            self.button(strip, action, callback).pack(side="right")
            if idx < len(rows) - 1:
                tk.Frame(middle, bg=LINE, height=1).pack(fill="x", pady=4)
        notice = self.panel(pad=12)
        notice.pack(fill="x")
        self.text(notice, "Built to avoid surprise deletions", 13, ACCENT, True).pack(anchor="w", pady=(0, 8))
        self.text(notice,
                  "Unknown play dates stay unknown. Old timestamps are not proof of non-use. "
                  "Automatic cleanup is OFF by default. Every deletion needs your approval.",
                  10, MUTED, wraplength=810).pack(anchor="w")

    def _add_page_controls(self, key, render):
        """Draw only a bounded slice of each inventory, never truncate stored findings."""
        self._pager_indices[key] = 0
        strip = tk.Frame(self.content, bg=BG)
        strip.pack(fill="x", pady=(5, 0))
        prior = self.button(strip, "◀ Previous",
                            lambda: self._change_inventory_page(key, -1, render))
        prior.pack(side="left")
        label = tk.StringVar(value="Loading findings…")
        self.text(strip, "", 9, MUTED, textvariable=label).pack(side="left", padx=10)
        following = self.button(strip, "Next ▶",
                                lambda: self._change_inventory_page(key, 1, render))
        following.pack(side="left")
        self._pager_controls[key] = (prior, following, label)

    def _change_inventory_page(self, key, direction, render):
        self._pager_indices[key] = max(0, self._pager_indices.get(key, 0) + direction)
        render()

    def _reset_inventory_page(self, key, render):
        self._pager_indices[key] = 0
        render()

    def _update_inventory_page(self, key, page):
        self._pager_indices[key] = page.page
        prior, following, label = self._pager_controls[key]
        prior.configure(state="normal" if page.page > 0 else "disabled")
        following.configure(state="normal" if page.page + 1 < page.pages else "disabled")
        label.set(page.label)

    def _tree(self, parent, columns, headings, widths):
        holder = tk.Frame(parent, bg=PANEL)
        holder.pack(fill="both", expand=True)
        tree = ttk.Treeview(holder, columns=columns, show="headings", height=7,
                            selectmode="extended", style="Data.Treeview")
        for i, col in enumerate(columns):
            tree.heading(col, text=headings[i])
            tree.column(col, width=widths[i], minwidth=70, stretch=(i in (0, len(columns) - 1)))
        scrollbar = ttk.Scrollbar(holder, command=tree.yview, style="Dark.Vertical.TScrollbar")
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        tree.tag_configure("even", background=RAISED)
        return tree

    def _game_dna_page(self):
        """Simple relationship view first; technical tools available when requested."""
        self.header("Game DNA", "See which games, mods and saves belong together. Nothing is deleted.")
        dna = build_game_dna(self.games, self.other_games, self.mod_folders, self.save_findings,
                             manager_profiles=(self.profile_report or {}).get("profiles", []))
        summary = self.panel(pad=15)
        summary.pack(fill="x", pady=(0, 12))
        if not self.last_scan:
            self.text(summary, "STEP 1  Scan your PC", 15, bold=True).pack(anchor="w")
            self.text(summary, "Choose Scan PC in the top right. Game Grave will look for games "
                      "and possible mod connections without changing files.",
                      10, MUTED, wraplength=800).pack(anchor="w", pady=(5, 0))
        else:
            self.text(summary, "Your gaming setup at a glance", 15, bold=True).pack(anchor="w")
            self.text(summary,
                      f"{len(dna['games'])} games found   •   "
                      f"{len(dna['unresolved'])} files or folders need review",
                      12, ACCENT, True).pack(anchor="w", pady=(9, 4))
            self.text(summary, "A connection is based on available installation records. "
                      "Unmatched does not mean abandoned or safe to delete.",
                      10, MUTED, wraplength=800).pack(anchor="w")

        guide = self.panel(pad=15)
        guide.pack(fill="x", pady=(0, 12))
        self.text(guide, "STEP 2  Pick a game", 15, bold=True).pack(anchor="w", pady=(0, 7))
        self.text(guide, "Choose a game to see how many mod-storage locations are linked to it.",
                  10, MUTED, wraplength=780).pack(anchor="w", pady=(0, 8))
        self._dna_game_options = {
            f"{g['game']}  ·  {g['launcher']}  (#{i + 1})": g
            for i, g in enumerate(dna["games"])
        }
        self.dna_pick_var = tk.StringVar(
            value=next(iter(self._dna_game_options), "No games found yet"))
        selector = ttk.Combobox(guide, textvariable=self.dna_pick_var,
                                values=tuple(self._dna_game_options),
                                state="readonly", style="Dark.TCombobox", width=55)
        selector.pack(anchor="w", pady=(0, 9))
        selector.bind("<<ComboboxSelected>>", lambda _event: self._dna_selected_game())
        self.dna_explanation_var = tk.StringVar()
        self._dna_selected_game()
        self.text(guide, "", 11, textvariable=self.dna_explanation_var,
                  wraplength=790).pack(anchor="w", pady=(0, 10))
        self.button(guide, "View visual relationship map",
                    lambda: self._open_dna_visual_map(dna)).pack(anchor="w")

        next_steps = self.panel(pad=15)
        next_steps.pack(fill="x", pady=(0, 12))
        self.text(next_steps, "STEP 3  Check for changes", 15, bold=True).pack(anchor="w")
        self.text(next_steps, "Save a snapshot of your mod-folder information. The next time "
                  "you check, Game Grave shows what looks different. No mod files are edited.",
                  10, MUTED, wraplength=790).pack(anchor="w", pady=(5, 9))
        self.button(next_steps, "Check what changed", self._capture_intelligence,
                    primary=True).pack(anchor="w")
        previous = load_observation()
        self.text(next_steps, "Previous snapshot: " +
                  (str(previous.get("time", "date unknown")) if previous else "None yet"),
                  9, MUTED).pack(anchor="w", pady=(9, 0))
        if getattr(self, "_intel_report", None):
            report = self._intel_report
            self.text(next_steps, f"{report.get('count', 0)} changes detected. "
                      "Changes are clues, not proof of a broken mod.",
                      10, WARN, True, wraplength=780).pack(anchor="w", pady=(7, 0))
            for message in what_broke_my_game(report)[:3]:
                self.text(next_steps, "• " + message, 9, MUTED,
                          wraplength=760).pack(anchor="w", pady=2)

        advanced_toggle = tk.Frame(self.content, bg=BG)
        advanced_toggle.pack(fill="x", pady=(0, 6))
        self.button(advanced_toggle, "Advanced tools and mod-manager profiles",
                    self._dna_toggle_advanced).pack(side="left")
        self.text(advanced_toggle, "Optional: backups, migration, deeper diagnostics",
                  9, MUTED).pack(side="left", padx=(10, 0))
        self.dna_advanced_panel = self.panel(pad=15)
        self.text(self.dna_advanced_panel, "Advanced tools", 14, bold=True).pack(anchor="w", pady=(0, 9))
        tools1 = tk.Frame(self.dna_advanced_panel, bg=PANEL)
        tools1.pack(fill="x", pady=(0, 7))
        self.button(tools1, "Inspect mod-manager profiles", self._inspect_manager_profiles).pack(side="left")
        self.button(tools1, "Mod ownership audit", self._show_mod_radar_audit).pack(side="left", padx=8)
        tools2 = tk.Frame(self.dna_advanced_panel, bg=PANEL)
        tools2.pack(fill="x", pady=(0, 7))
        self.button(tools2, "Find setup for backup", self._start_auto_kit).pack(side="left")
        self.button(tools2, "Resurrection Lab", lambda: self.show_page("Resurrection Lab")).pack(
            side="left", padx=8)
        tools3 = tk.Frame(self.dna_advanced_panel, bg=PANEL)
        tools3.pack(fill="x", pady=(0, 9))
        self.button(tools3, "Moving to another PC?", self._preview_exodus).pack(side="left")
        self.button(tools3, "Export private QA report", self._export_private_m2_qa).pack(
            side="left", padx=8)
        profiles = self.profile_report
        if profiles is not None:
            self.text(self.dna_advanced_panel,
                      f"Mod-manager profiles inspected: {profiles['count']}",
                      12, bold=True).pack(anchor="w", pady=(6, 6))
            if profiles["profiles"]:
                area = tk.Frame(self.dna_advanced_panel, bg=PANEL, height=180)
                area.pack(fill="both", expand=True, pady=(0, 6))
                self.profile_tree = self._tree(
                    area, ("manager", "profile", "game", "enabled", "disabled", "status"),
                    ("MANAGER", "PROFILE", "GAME", "ON", "OFF", "DATA STATUS"),
                    (115, 130, 190, 65, 65, 170))
                self.profile_lookup = {}
                for idx, profile in enumerate(profiles["profiles"]):
                    stats = summarize_manager_profile(profile)
                    self.profile_lookup[str(idx)] = profile
                    name = profile.get("verified_game") or "Unverified"
                    status = ("Outdated snapshot" if profile.get("stale") else
                              "Incomplete" if stats["incomplete"] else "Recorded data")
                    self.profile_tree.insert("", "end", iid=str(idx),
                        values=(profile["manager"], profile["profile"], name,
                                stats["enabled"], stats["disabled"], status))
                self.profile_tree.bind("<Double-1>", lambda _event: self._view_manager_profile())
                self.button(self.dna_advanced_panel, "View selected profile",
                            self._view_manager_profile).pack(anchor="w", pady=(2, 8))
            for warning in profiles.get("warnings", [])[:2]:
                self.text(self.dna_advanced_panel, "• " + warning, 9, WARN,
                          wraplength=780).pack(anchor="w")
        self.text(self.dna_advanced_panel,
                  "Unknown associations always stay protected. These tools only inspect "
                  "available records until you explicitly approve a separate action.",
                  9, MUTED, wraplength=780).pack(anchor="w", pady=(9, 0))
        if getattr(self, "_dna_advanced_open", False):
            self.dna_advanced_panel.pack(fill="x", pady=(0, 12))

    def _dna_selected_game(self):
        game = self._dna_game_options.get(self.dna_pick_var.get())
        if game is None:
            self.dna_explanation_var.set("Run Scan PC to start. No games are listed yet.")
            return
        count = len(game["assets"])
        self.dna_explanation_var.set(
            f"{game['game']}  •  {game['launcher']}\n"
            f"{count} mod-storage location(s) linked using available records. "
            "A link is not permission to delete anything.")

    def _dna_toggle_advanced(self):
        self._dna_advanced_open = not getattr(self, "_dna_advanced_open", False)
        if self._dna_advanced_open:
            self.dna_advanced_panel.pack(fill="x", pady=(0, 12))
        else:
            self.dna_advanced_panel.pack_forget()

    def _open_dna_visual_map(self, dna):
        """Readable, zoomable native diagram; never launches any file action."""
        window = tk.Toplevel(self)
        window.title("Game Grave · Game DNA visual guide")
        window.geometry("790x350")
        window.minsize(420, 330)
        window.configure(bg=BG)
        frame = tk.Frame(window, bg=PANEL, padx=18, pady=18,
                         highlightbackground=LINE, highlightthickness=1)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        palette = {"panel": PANEL, "raised": RAISED, "text": TEXT,
                   "muted": MUTED, "line": LINE, "blue": BLUE,
                   "accent": ACCENT, "warn": WARN}
        dna_visual(frame, dna, palette=palette, scanned=bool(self.last_scan)).pack(
            fill="both", expand=True)
        self.text(frame, "GREEN / TEAL = associated evidence   ·   GOLD = review needed   ·   "
                  "BLUE = protected by default",
                  9, MUTED, wraplength=690).pack(anchor="w", pady=(9, 0))
        self.button(frame, "Close visual guide", window.destroy).pack(anchor="e", pady=(10, 0))
        window.bind("<Escape>", lambda _event: window.destroy())

    def _export_private_m2_qa(self):
        """User-initiated aggregate JSON export; never writes names or paths."""
        if not self.last_scan:
            messagebox.showinfo("Scan first", "Run Scan PC before exporting a local M2 report.")
            return
        profile_rows = (self.profile_report or {}).get("profiles", [])
        audit = audit_mod_radar(
            self.games, self.other_games, self.mod_folders, self.save_findings,
            profile_rows)
        report = private_audit_summary(
            audit, profiles_examined=self.profile_report is not None)
        if not messagebox.askyesno(
                "Export private Mod Radar report?",
                "Create a JSON file containing only scan counts and uncertainty "
                "categories? No game names, mod names, paths, usernames, "
                "profile IDs or file contents will be included.\n\n"
                "Nothing will be deleted, uploaded or repaired."):
            return
        selected = filedialog.asksaveasfilename(
            title="Choose a new QA report filename",
            defaultextension=".json",
            initialfile="GameGrave-M2-private-audit.json",
            filetypes=[("JSON report", "*.json")])
        if not selected:
            return
        path = Path(selected)
        try:
            if path.exists() or path.is_symlink():
                raise FileExistsError("That report already exists. Choose a new name.")
            with path.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
            self.status_text.set("Private Mod Radar QA report exported")
            messagebox.showinfo("Report created",
                "Count-only audit exported to the location you selected.\n\n"
                "A real Windows/launcher QA review is still needed to finish M2.")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot save QA report", str(exc))

    def _show_mod_radar_audit(self):
        """Summarize existing scan relationships, never perform cleanup."""
        if not self.last_scan:
            messagebox.showinfo("Scan PC first", "Run Scan PC before auditing game/mod ownership.")
            return
        result = audit_mod_radar(
            self.games, self.other_games, self.mod_folders, self.save_findings,
            (self.profile_report or {}).get("profiles", []))
        overview = [
            "MOD RADAR · READ-ONLY OWNERSHIP AUDIT",
            "",
            f"Recorded installations: {result['recorded_games']}",
            f"Scanned mod storage locations: {result['scanned_mod_locations']}",
            f"Associated by unique installation path or Steam app ID: "
            f"{result['associated_mod_locations']}",
            f"Unassigned storage locations: {result['unassigned_mod_locations']}",
            f"Ambiguous ownership claims: {result['ambiguous_claims']}",
            f"Linked/redirected paths requiring review: {result['redirected_locations']}",
            f"Stale manager snapshots: {result['stale_manager_snapshots']}",
            f"Incomplete manager snapshots: {result['incomplete_manager_snapshots']}",
            f"MO2/Vortex recorded enabled/disabled references: "
            f"{result['enabled_profile_references']}/{result['disabled_profile_references']}",
            "",
            "Unresolved sample (not deletion recommendations):",
        ]
        if result["examples"]:
            overview.extend(
                f"• {x['item'][:40]}: {x['reason'][:110]}"
                for x in result["examples"][:12])
        else:
            overview.append("• No unresolved records in the current scan.")
        overview.extend([
            "",
            "0 items approved for cleanup. Active status and orphan status are "
            "NOT established from folder age, missing manifests or manager markers.",
            "Re-scan after changing games or mod manager paths.",
        ])
        messagebox.showinfo("Game Grave · Mod Radar evidence audit", "\n".join(overview))

    def _inspect_manager_profiles(self):
        if not self.last_scan:
            messagebox.showinfo("Scan first", "Run Scan PC to identify manager folders and installed games.")
            return
        mods, games, other = list(self.mod_folders), list(self.games), list(self.other_games)
        self.status_text.set("Inspecting local MO2 modlists and Vortex backup profiles…")
        def worker():
            try:
                result = inspect_manager_profiles(mods, games, other)
                self.events.put(("manager_profiles_result", result))
            except (OSError, ValueError, RuntimeError) as exc:
                self.events.put(("manager_profiles_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _view_manager_profile(self):
        if (not hasattr(self, "profile_tree") or
                not self.profile_tree.winfo_exists() or not self.profile_tree.selection()):
            messagebox.showinfo("Select a profile", "Choose a manager profile in the Game DNA table.")
            return
        profile = self.profile_lookup.get(self.profile_tree.selection()[0])
        if not profile:
            return
        from manager_profiles import summarize_manager_profile
        summary = summarize_manager_profile(profile)
        flags = ("Outdated snapshot; " if profile.get("stale") else "") + (
                 "partial data; " if profile.get("incomplete") else "")
        lines = [
            f"{profile['manager']} · {profile['profile']}",
            f"Reported game: {profile.get('game_hint') or 'Unknown'}",
            f"Verified installed match: {profile.get('verified_game') or 'None'}",
            f"Profile entries: {len(profile.get('mods', []))} "
            f"(enabled {summary['enabled']}, disabled {summary['disabled']}, other {summary['other']})",
            f"Data quality: {flags or 'Recorded metadata only'}",
            "",
            "First 35 entries (status is recorded, not confirmed loaded):",
        ]
        for item in profile.get("mods", [])[:35]:
            lines.append(f"• {item['name']}: {item['status']} · {item['storage']}")
        if len(profile.get("mods", [])) > 35:
            lines.append(f"... plus {len(profile['mods']) - 35} additional entries")
        lines += ["", profile.get("note", ""),
                  "Disabled does NOT mean unused or safe to delete. Nothing was modified."]
        messagebox.showinfo("Game DNA · manager profile", "\n".join(lines))

    def _capture_intelligence(self):
        if not self.last_scan:
            messagebox.showinfo("Scan first", "Run Scan PC before capturing a mod-storage baseline.")
            return
        self.status_text.set("Comparing selected mod-folder metadata; no file contents are read…")
        mods = list(self.mod_folders)
        def worker():
            try:
                before = load_observation()
                after = capture_mod_observation(mods)
                save_observation(after)
                self.events.put(("intelligence_result", ghost_watch(before, after)))
            except (OSError, ValueError, RuntimeError) as exc:
                self.events.put(("intelligence_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _preview_exodus(self):
        dna = build_game_dna(self.games, self.other_games, self.mod_folders, self.save_findings)
        plan = exodus_plan(dna)
        lines = [f"{g['name']} ({g['launcher']}): launcher reinstall/verification needed; "
                 f"{len(g['related_storage'])} associated mod location(s)."
                 for g in plan["games"][:12]]
        messagebox.showinfo("Exodus · migration preview",
            "\n".join(lines) if lines else "Run Scan PC first to inventory games.")
        messagebox.showinfo("Exodus limitations",
            f"{plan['unresolved_count']} save or mod locations remain unverified.\n\n"
            "This is a planning checklist, not a file transfer. "
            "Preserve saves and mod profiles separately and use each game launcher for installation.")

    def _games_page(self):
        self.header("Steam Games", "Sort out games you haven't launched in a while. You approve every uninstall in Steam.")
        controls = tk.Frame(self.content, bg=BG)
        controls.pack(fill="x", pady=(0, 12))
        self.game_search = tk.StringVar()
        search = tk.Entry(controls, textvariable=self.game_search, bg=PANEL, fg=TEXT,
                          insertbackground=TEXT, relief="flat", font=("Segoe UI", 11), width=33)
        search.pack(side="left", ipady=9, padx=(0, 14))
        self.game_search.trace_add("write", lambda *_: self._reset_inventory_page("games", self._populate_games))
        self.only_old = tk.BooleanVar(value=False)
        self.game_old_check = ttk.Checkbutton(controls, text=f"Only {self.settings['game_stale_days']}+ days",
                                variable=self.only_old, style="Dark.TCheckbutton",
                                command=lambda: self._reset_inventory_page("games", self._populate_games))
        self.game_old_check.pack(side="left")
        secondary_filters = tk.Frame(self.content, bg=BG)
        secondary_filters.pack(fill="x", pady=(0, 10))
        self.text(secondary_filters, "Threshold (days):", 9, MUTED).pack(side="left", padx=(0, 9))
        self.game_days_var = tk.StringVar(value=str(self.settings["game_stale_days"]))
        days = ttk.Combobox(secondary_filters, textvariable=self.game_days_var, values=tuple(map(str, GAME_AGE_OPTIONS)),
                            state="readonly", style="Dark.TCombobox", width=5)
        days.pack(side="left")
        days.bind("<<ComboboxSelected>>", self._change_game_days)
        self.text(secondary_filters, "Sort", 9, MUTED).pack(side="left", padx=(15, 6))
        self.game_sort_var = tk.StringVar(value=self.settings.get("game_sort", "Oldest first"))
        game_sort = ttk.Combobox(secondary_filters, textvariable=self.game_sort_var,
                                 values=GAMES_SORT_OPTIONS, state="readonly", style="Dark.TCombobox", width=15)
        game_sort.pack(side="left")
        game_sort.bind("<<ComboboxSelected>>", lambda _e: self._set_view_sort("game_sort", self.game_sort_var, self._populate_games))
        p = self.panel(pad=10)
        p.pack(fill="both", expand=True)
        self.game_tree = self._tree(p, ("name", "last", "size", "source"),
                                    ("GAME", "LAST PLAYED", "INSTALL SIZE", "DATE SOURCE"),
                                    (295, 140, 125, 210))
        self.game_tree.bind("<Double-1>", lambda e: self._uninstall_game())
        for column, first, second in (("name", "Name A-Z", "Name Z-A"),
                                      ("last", "Oldest first", "Newest first"),
                                      ("size", "Largest first", "Smallest first"),
                                      ("source", "Date source A-Z", "Date source Z-A")):
            self.game_tree.heading(column, command=lambda a=first, b=second:
                                   self._game_column_sort(a, b))
        self._add_page_controls("games", self._populate_games)
        self._populate_games()
        actions = tk.Frame(self.content, bg=BG)
        actions.pack(fill="x", pady=(14, 0))
        self.button(actions, "Uninstall selected via Steam", self._uninstall_game, primary=True).pack(side="left")
        self.button(actions, "Open installation folder", self._open_game_folder).pack(side="left", padx=12)
        more_actions = tk.Frame(self.content, bg=BG)
        more_actions.pack(fill="x", pady=(5, 0))
        self.button(more_actions, "Clear shader cache…", self._clear_game_shader_cache).pack(side="left")
        self.button(more_actions, "Add Steam library", self._add_steam_library).pack(side="left", padx=12)
        self.text(self.content,
                  "Unknown means local records don't confirm the last play date. Installation timestamps are NOT used to guess playtime.",
                  9, MUTED, wraplength=840).pack(anchor="w", pady=(16, 0))

    def _game_column_sort(self, first, second):
        current = self.game_sort_var.get()
        self.game_sort_var.set(second if current == first else first)
        self._set_view_sort("game_sort", self.game_sort_var, self._populate_games)

    def _change_game_days(self, event=None):
        self.settings["game_stale_days"] = int(self.game_days_var.get())
        save_settings(self.settings)
        self.game_old_check.configure(text=f"Only {self.settings['game_stale_days']}+ days")
        self._reset_inventory_page("games", self._populate_games)

    def _populate_games(self):
        if not hasattr(self, "game_tree") or not self.game_tree.winfo_exists():
            return
        self.game_tree.delete(*self.game_tree.get_children())
        self.game_lookup = {}
        query = self.game_search.get().strip().lower()
        visible = [g for g in sort_games(self.games, self.game_sort_var.get())
                   if (not query or query in g.name.lower()) and
                   (not self.only_old.get() or is_game_neglected(g, self.settings["game_stale_days"]))]
        page = page_window(visible, self._pager_indices.get("games", 0))
        for game in page.items:
            self.game_tree.insert("", "end", iid=game.app_id,
                                  values=(game.name, age_text(game.last_played),
                                          human_size(game.size) if game.size else "Unknown", game.source))
            self.game_lookup[game.app_id] = game
        self._update_inventory_page("games", page)

    def _selected_game(self):
        if not hasattr(self, "game_tree") or not self.game_tree.winfo_exists():
            return None
        selected = self.game_tree.selection()
        if len(selected) != 1:
            messagebox.showinfo("Choose one game", "Select a single Steam game first.")
            return None
        return self.game_lookup.get(selected[0])

    def _uninstall_game(self):
        game = self._selected_game()
        if not game:
            return
        if not messagebox.askyesno("Open Steam uninstall?",
                                   f"Open Steam's uninstall confirmation for:\n\n{game.name}\n\n"
                                   "Game Grave will not delete the game folder itself. Steam handles the uninstall."):
            return
        try:
            if os.name != "nt":
                raise RuntimeError("This shortcut requires Windows and Steam.")
            os.startfile(f"steam://uninstall/{game.app_id}")
            log_event("Steam uninstall opened", game.name)
            self.status_text.set(f"Steam uninstall opened for {game.name}")
        except (OSError, RuntimeError) as exc:
            messagebox.showerror("Could not open Steam", str(exc))

    def _open_game_folder(self):
        game = self._selected_game()
        if game:
            try:
                if os.name != "nt" or not Path(game.install_path).is_dir():
                    raise OSError("Game installation folder is unavailable.")
                os.startfile(game.install_path)
            except OSError as exc:
                messagebox.showerror("Could not open folder", str(exc))

    def _clear_game_shader_cache(self):
        """Only Steam's verified per-app cache for a selected installed game."""
        if getattr(self, "cleanup_running", False) or self.scanning:
            messagebox.showinfo("Game Grave is busy",
                                "Finish the current scan or cleanup before clearing shaders.")
            return
        game = self._selected_game()
        if game is None:
            return
        self.status_text.set(f"Checking shader cache for {game.name}…")
        def inspect():
            try:
                cache = inspect_steam_shader_cache(game)
                self.events.put(("shader_preview", (game, cache)))
            except (OSError, ValueError) as exc:
                self.events.put(("shader_error", str(exc)))
        threading.Thread(target=inspect, daemon=True).start()

    def _confirm_shader_cache(self, game, cache):
        if getattr(self, "cleanup_running", False) or self.scanning:
            messagebox.showinfo("Game Grave is busy",
                                "Finish the current scan or cleanup before clearing shaders.")
            return
        if cache is None or not cache.files:
            messagebox.showinfo("No shader cache found",
                                f"No eligible Steam shader files were found for {game.name}.\n\n"
                                "Other launchers and graphics-driver caches were not touched.")
            return
        if not messagebox.askyesno(
            "Clear this game's shader cache?",
            f"{game.name}\n\n{len(cache.files)} files  ·  {human_size(cache.bytes_total)} apparent size\n"
            f"Skipped unsafe files/folders: {cache.skipped}\n\n"
            "Close this game and Steam before proceeding. Shaders will rebuild or redownload "
            "next time you play, which can cause longer loading or temporary stutter.\n\n"
            "Files go to the Windows Recycle Bin, so disk space may not be freed immediately.\n"
            "No saves, mods, installed game files, or shared GPU caches will be removed.\n\n"
            "Delete ONLY these verified shader-cache files?",
            parent=self,
        ):
            return
        self.cleanup_running = True
        self.scan_button.configure(state="disabled", bg=RAISED)
        self.status_text.set(f"Deleting verified shader files for {game.name}…")
        def cleanup():
            import uuid
            session = str(uuid.uuid4())
            log_event("Cleanup started", f"Shader cache: {game.name}", session_id=session,
                      source="Steam per-game shader cache")
            removed, skipped = 0, []
            for file in cache.files:
                try:
                    if not file_still_matches(cache, file):
                        raise ValueError("File changed or is no longer safe to recycle")
                    recycle_file(file.path)
                    try:
                        rid = register_recycle(file.path, file.size, f"Shader cache: {game.name}")
                    except OSError:
                        rid = None
                        log_event("Recovery warning", "Could not save Undo Center entry", session_id=session,
                                  path=str(file.path), source="Shader cache")
                    log_event("Manual recycled", "Steam shader cache file moved to Recycle Bin",
                              session_id=session, path=str(file.path), size_bytes=file.size,
                              source=f"Shader cache: {game.name}", result="Recycled", recovery_id=rid)
                    removed += 1
                except (OSError, ValueError, RuntimeError) as exc:
                    skipped.append(f"{file.path.name}: {exc}")
                    log_event("Cleanup skipped", str(exc), session_id=session,
                              path=str(file.path), source=f"Shader cache: {game.name}", result="Skipped")
            log_event("Cleanup finished", f"Shader cache: {game.name}; {removed} recycled; "
                      f"{len(skipped)} skipped. Recycle Bin may still occupy disk space.",
                      session_id=session, source="Steam per-game shader cache")
            self.events.put(("shader_result", (game.name, removed, skipped)))
        def guarded_cleanup():
            try:
                cleanup()
            except Exception as exc:
                self.events.put(("shader_cleanup_error", str(exc)[:350]))
        try:
            threading.Thread(target=guarded_cleanup, daemon=True).start()
        except RuntimeError as exc:
            self.cleanup_running = False
            self.scan_button.configure(state="normal", bg=ACCENT)
            messagebox.showerror("Shader deletion could not start", str(exc))

    def _add_steam_library(self):
        folder = filedialog.askdirectory(title="Select Steam install or SteamLibrary folder")
        if not folder:
            return
        if not (Path(folder) / "steamapps").is_dir():
            messagebox.showerror("Invalid library", "Select a folder containing a steamapps subfolder.")
            return
        existing = self.settings["steam_extra_roots"]
        if folder not in existing:
            existing.append(folder)
            save_settings(self.settings)
        self.scan_all()


    def _other_launchers_page(self):
        self.header("Other Launchers", "Epic, GOG, Riot, Ubisoft, EA and selected libraries. Results are read-only.")
        summary = self.panel(pad=12)
        summary.pack(fill="x", pady=(0, 12))
        self.text(summary, f"{len(self.other_games)} records found. Local manifests and registries may be incomplete.",
                  11, bold=True).pack(anchor="w")
        self.text(summary, "Not every launcher exposes reliable install records. Unknown folders are not called junk. No uninstall is performed.",
                  9, WARN, wraplength=800).pack(anchor="w", pady=(5, 0))
        panel = self.panel(pad=8)
        panel.pack(fill="both", expand=True)
        self.other_tree = self._tree(panel, ("game", "launcher", "reported", "status"),
                                     ("GAME / FOLDER", "LAUNCHER", "REPORTED SIZE", "EVIDENCE"),
                                     (250, 135, 110, 320))
        self.other_lookup = {}
        self.other_sort_column = getattr(self, "other_sort_column", "game")
        self.other_sort_reverse = getattr(self, "other_sort_reverse", False)
        for column in ("game", "launcher", "reported", "status"):
            self.other_tree.heading(column, command=lambda c=column: self._sort_other_launchers(c))
        self._add_page_controls("other", self._populate_other_launchers)
        self._populate_other_launchers()
        actions = tk.Frame(self.content, bg=BG)
        actions.pack(fill="x", pady=(12, 0))
        self.button(actions, "Open selected folder", self._open_other_game, primary=True).pack(side="left")
        self.button(actions, "Add a game library folder", self._add_other_library).pack(side="left", padx=10)
        self.button(actions, "Manage library folders", self._manage_other_libraries).pack(side="left")

    def _populate_other_launchers(self):
        if not hasattr(self, "other_tree") or not self.other_tree.winfo_exists():
            return
        self.other_tree.delete(*self.other_tree.get_children())
        self.other_lookup = {}
        page = page_window(self._ordered_other_games(), self._pager_indices.get("other", 0))
        for offset, game in enumerate(page.items):
            key = str(page.start + offset)
            self.other_lookup[key] = game
            self.other_tree.insert("", "end", iid=key, values=(
                game.name, game.launcher,
                human_size(game.reported_bytes) if game.reported_bytes is not None else "Not reported",
                game.status))
        self._update_inventory_page("other", page)

    def _ordered_other_games(self):
        column = getattr(self, "other_sort_column", "game")
        reverse = getattr(self, "other_sort_reverse", False)
        def key(g):
            if column == "reported":
                return (g.reported_bytes is None, g.reported_bytes or 0)
            return str(getattr(g, {"game": "name", "launcher": "launcher", "status": "status"}.get(column, "name"))).casefold()
        return sorted(self.other_games, key=key, reverse=reverse)

    def _sort_other_launchers(self, column):
        self.other_sort_reverse = not self.other_sort_reverse if getattr(self, "other_sort_column", "game") == column else False
        self.other_sort_column = column
        self.show_page("Other Launchers")

    def _open_other_game(self):
        chosen = self.other_tree.selection()
        if len(chosen) != 1:
            messagebox.showinfo("Choose a game", "Select one installation or folder first.")
            return
        game = self.other_lookup.get(chosen[0])
        if game and os.name == "nt":
            try:
                os.startfile(game.install_path)
            except OSError as exc:
                messagebox.showerror("Could not open", str(exc))

    def _add_other_library(self):
        folder = filedialog.askdirectory(title="Select a game library folder (NOT a whole drive)")
        if not folder:
            return
        path = Path(folder)
        if path == Path(path.anchor) or not path.is_dir() or path.is_symlink() or path == Path.home():
            messagebox.showerror("Choose a narrower folder", "Choose a specific game library, not a drive or home directory.")
            return
        if folder not in self.settings["other_library_roots"]:
            self.settings["other_library_roots"].append(folder)
            save_settings(self.settings)
        self.scan_all()

    def _manage_other_libraries(self):
        roots = self.settings["other_library_roots"]
        if not roots:
            messagebox.showinfo("No added folders", "No extra game library folders configured.")
            return
        chosen = tk.Toplevel(self)
        chosen.title("Game library folders")
        chosen.geometry("680x310")
        lst = tk.Listbox(chosen, font=("Segoe UI", 11))
        lst.pack(fill="both", expand=True, padx=12, pady=12)
        for name in roots:
            lst.insert("end", name)
        def remove():
            selection = lst.curselection()
            if selection:
                del roots[selection[0]]
                save_settings(self.settings)
                chosen.destroy()
                self.scan_all()
        self.button(chosen, "Stop scanning selected folder", remove).pack(padx=12, pady=(0, 12))

    def _mods_page(self):
        self.header("Game Mods & Hidden Storage", "Steam game folders, Workshop downloads, Vortex staging, and Mod Organizer 2 instances.")
        summary = self.panel(pad=13)
        summary.pack(fill="x", pady=(0, 10))
        sources = {source: sum(f.source == source for f in self.mod_folders)
                   for source in sorted({row.source for row in self.mod_folders})}
        self.text(summary, "   •   ".join(f"{source}: {count}" for source, count in sources.items()),
                  10, bold=True, wraplength=810).pack(anchor="w")
        self.text(summary, "READ-ONLY: No items will be deleted. Apparent sizes may double count linked files. "
                  "Missing game records, unindexed Workshop folders, and old timestamps are NOT proof of safe deletion.",
                  9, WARN, wraplength=815).pack(anchor="w", pady=(7, 0))
        palette = {"panel": PANEL, "raised": RAISED, "text": TEXT,
                   "muted": MUTED, "line": LINE, "blue": BLUE,
                   "accent": ACCENT, "warn": WARN}
        mod_radar_visual(summary, palette=palette).pack(fill="x", pady=(11, 3))
        selector = tk.Frame(self.content, bg=BG)
        selector.pack(fill="x", pady=(0, 10))
        self.mod_filter = tk.StringVar(value="All sources")
        pick = ttk.Combobox(selector, textvariable=self.mod_filter, state="readonly", style="Dark.TCombobox",
                            values=("All sources", *sorted({row.source for row in self.mod_folders})), width=20)
        pick.pack(side="left")
        pick.bind("<<ComboboxSelected>>", lambda *_: self._reset_inventory_page("mods", self._populate_mods))
        self.mod_search = tk.StringVar()
        self.mod_search.trace_add("write", lambda *_: self._reset_inventory_page("mods", self._populate_mods))
        tk.Entry(selector, textvariable=self.mod_search, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                 relief="flat", font=("Segoe UI", 10), width=28).pack(side="left", padx=(12, 0), ipady=7)
        self.text(selector, "Sort", 9, MUTED).pack(side="left", padx=(12, 5))
        self.mod_sort_var = tk.StringVar(value=self.settings.get("mod_sort", "Largest first"))
        mod_sort = ttk.Combobox(selector, textvariable=self.mod_sort_var, values=MOD_SORT_OPTIONS,
                                state="readonly", style="Dark.TCombobox", width=17)
        mod_sort.pack(side="left")
        mod_sort.bind("<<ComboboxSelected>>", lambda _e: self._set_view_sort("mod_sort", self.mod_sort_var, self._populate_mods))
        box = self.panel(pad=8)
        box.pack(fill="both", expand=True)
        self.mod_tree = self._tree(box, ("game", "source", "status", "count", "size"),
                                   ("GAME / LIBRARY", "SOURCE", "TYPE / STATUS", "ITEMS", "APPARENT SIZE"),
                                   (220, 155, 233, 75, 110))
        self.mod_tree.configure(height=7)
        self.mod_tree.bind("<<TreeviewSelect>>", self._show_mod_details)
        self._add_page_controls("mods", self._populate_mods)
        self._populate_mods()
        actions = tk.Frame(self.content, bg=BG)
        actions.pack(fill="x", pady=(10, 0))
        self.button(actions, "Why is this here?", self._detect_selected_mod, primary=True).pack(side="left")
        self.button(actions, "Open folder", self._open_mod_folder).pack(side="left", padx=8)
        self.button(actions, "Send to Graveyard", self._send_mod_to_graveyard).pack(side="left", padx=8)
        self.button(actions, "Rescan", self.scan_all).pack(side="left")
        more = tk.Frame(self.content, bg=BG)
        more.pack(fill="x", pady=(4, 0))
        self.button(more, "Add folder", self._add_mod_storage_folder).pack(side="left")
        self.button(more, "Manage folders", self._manage_mod_storage_folders).pack(side="left", padx=8)
        self.button(more, "Identify other folder", self._detect_any_folder).pack(side="left")
        details = self.panel(pad=12)
        details.pack(fill="x", pady=(10, 0))
        self.mod_details = tk.StringVar(value="Select a finding to see the path, evidence, and safety guidance.")
        tk.Label(details, textvariable=self.mod_details, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9), wraplength=815, justify="left").pack(anchor="w")

    def _populate_mods(self):
        if not hasattr(self, "mod_tree") or not self.mod_tree.winfo_exists():
            return
        self.mod_tree.delete(*self.mod_tree.get_children())
        self.mod_lookup = {}
        view = self.mod_filter.get()
        query = self.mod_search.get().strip().casefold()
        visible = [folder for folder in sort_mods(self.mod_folders, self.mod_sort_var.get())
                   if (view == "All sources" or view == folder.source) and
                   (not query or query in (folder.name + " " + folder.path + " " +
                                           folder.status + " " + folder.source).casefold())]
        page = page_window(visible, self._pager_indices.get("mods", 0))
        for i, folder in enumerate(page.items):
            key = str(page.start + i)
            items = str(folder.item_count) if folder.item_count else "—"
            self.mod_tree.insert("", "end", iid=key,
                                 values=(folder.name, folder.source, folder.status, items,
                                         human_size(folder.apparent_bytes) + ("+" if folder.truncated else "")))
            self.mod_lookup[key] = folder
        self._update_inventory_page("mods", page)

    def _current_mod_folder(self):
        if not hasattr(self, "mod_tree") or not self.mod_tree.winfo_exists():
            return None
        keys = self.mod_tree.selection()
        return self.mod_lookup.get(keys[0]) if keys else None

    def _show_mod_details(self, event=None):
        folder = self._current_mod_folder()
        if folder:
            if folder.source == "Steam game folder":
                explanation = ("Steam has no matching installed-game record. This could be an uninstall remnant, "
                               "a manual install, or another game." if folder.status == "Unmatched Steam folder" else
                               "Installed game; identified mod-like files only. Not necessarily safe to remove.")
            else:
                explanation = folder.advice
            signals = ", ".join(folder.indicators) or "No specific signatures detected"
            warning = "  Scan capped at its file limit; size is incomplete." if folder.truncated else ""
            self.mod_details.set(explanation + "\nEvidence: " + signals +
                                 "\nLocation: " + folder.path + warning)

    def _send_mod_to_graveyard(self):
        """Send a mod *finding for review*, never the actual folder for deletion."""
        item = self._current_mod_folder()
        if not item:
            messagebox.showinfo("Choose a mod", "Select a mod or addon folder first.")
            return
        self.settings.setdefault("graveyard_watchlist", [])
        if item.path not in self.settings["graveyard_watchlist"]:
            self.settings["graveyard_watchlist"].append(item.path)
            self.settings["graveyard_watchlist"] = self.settings["graveyard_watchlist"][-150:]
            save_settings(self.settings)
        messagebox.showinfo("Added for review", "This mod is now marked for Graveyard review.\n\n"
                            "No files were moved or deleted. Active and uncertain mod folders remain protected.")
        self.show_page("The Graveyard")

    def _detect_selected_mod(self):
        item = self._current_mod_folder()
        if not item:
            messagebox.showinfo("Choose a finding", "Select a mod or addon folder first.")
            return
        self._show_detective_report(item.path)

    def _detect_any_folder(self):
        folder = filedialog.askdirectory(title="Choose a folder to identify (read-only)")
        if folder:
            self._show_detective_report(folder)

    def _show_detective_report(self, path):
        verdict = investigate(path, self.games, self.other_games, self.mod_folders,
                              self.settings.get("never_touch", []))
        messagebox.showinfo("File Detective: What is this?", friendly_report(verdict, path))

    def _open_mod_folder(self):
        folder = self._current_mod_folder()
        if not folder:
            messagebox.showinfo("Select a folder", "Choose a finding to inspect first.")
            return
        try:
            if os.name != "nt":
                raise OSError("This shortcut requires Windows.")
            if not Path(folder.path).is_dir():
                raise OSError("The folder is unavailable. Run a new scan.")
            os.startfile(folder.path)
        except OSError as exc:
            messagebox.showerror("Unable to open folder", str(exc))

    def _add_mod_storage_folder(self):
        folder = filedialog.askdirectory(title="Select Vortex, MO2, or other mod storage folder")
        if not folder:
            return
        path = Path(folder)
        # Use explicitly chosen folders only, never a disk root or user's whole home.
        if path == Path(path.anchor) or path.resolve() == Path.home().resolve():
            messagebox.showerror("Too broad", "Select a specific mod manager or mod storage folder, not a drive or your home directory.")
            return
        configured = self.settings.setdefault("mod_extra_roots", [])
        if folder not in configured:
            configured.append(folder)
            save_settings(self.settings)
            log_event("Mod folder added", folder)
        self.scan_all()

    def _manage_mod_storage_folders(self):
        configured = self.settings.get("mod_extra_roots", [])
        if not configured:
            messagebox.showinfo("No custom locations", "No extra mod folders have been added yet.")
            return
        popup = tk.Toplevel(self)
        popup.title("Custom mod storage folders")
        popup.geometry("660x300")
        popup.configure(bg=BG)
        self.text(popup, "Game Grave also checks common Vortex and MO2 locations automatically.",
                  10, MUTED).pack(anchor="w", padx=18, pady=(17, 10))
        folder_list = tk.Listbox(popup, bg=PANEL, fg=TEXT, selectbackground="#225F76",
                                 relief="flat", font=("Segoe UI", 10))
        folder_list.pack(fill="both", expand=True, padx=18)
        for path in configured:
            folder_list.insert("end", path)
        def remove():
            selection = folder_list.curselection()
            if not selection:
                return
            ix = selection[0]
            removed = configured.pop(ix)
            save_settings(self.settings)
            log_event("Mod folder removed", removed)
            popup.destroy()
            self.scan_all()
        self.button(popup, "Stop scanning selected location", remove).pack(anchor="e", padx=18, pady=12)


    def _graveyard_page(self):
        """Clear review workflow, with advanced filters available on demand."""
        self.header("The Graveyard", "Find forgotten gaming files and clips. Review before deleting.")
        # Tk destroys widgets on navigation, but Python attributes otherwise survive.
        # Clear old buttons before populating the new page and refreshing their states.
        for old_button in ("grave_delete_button", "grave_protection_button",
                           "grave_delete_checked_button"):
            if hasattr(self, old_button):
                delattr(self, old_button)
        self._applying_grave_preset = False
        saved = sanitize_saved_views(self.settings.get("graveyard_saved_views", {}))
        self.settings["graveyard_saved_views"] = saved
        self.graveyard_entries = build_graveyard(
            self.games, self.mod_folders, self.old_files,
            self.settings.get("graveyard_days", 365), self.settings.get("never_touch", []),
            watched_mods=self.settings.get("graveyard_watchlist", []),
            recordings=getattr(self, "recordings", []))

        search_row = tk.Frame(self.content, bg=BG)
        search_row.pack(fill="x", pady=(0, 8))
        self.text(search_row, "Find", 10, MUTED).pack(side="left")
        self.grave_search_var = tk.StringVar(value=self.settings.get("graveyard_search", ""))
        tk.Entry(search_row, textvariable=self.grave_search_var, bg=PANEL, fg=TEXT,
                 insertbackground=TEXT, relief="flat", font=("Segoe UI", 11), width=32).pack(
                 side="left", padx=(8, 15), ipady=7)
        self.text(search_row, "Older than", 10, MUTED).pack(side="left")
        self.grave_days_var = tk.StringVar(value=str(self.settings.get("graveyard_days", 365)))
        days = ttk.Combobox(search_row, textvariable=self.grave_days_var,
                            values=("180", "365", "730", "1095"), state="readonly",
                            style="Dark.TCombobox", width=6)
        days.pack(side="left", padx=(7, 13))
        days.bind("<<ComboboxSelected>>", self._change_grave_days)
        self.button(search_row, "More filters", self._grave_toggle_advanced).pack(side="left")
        self.grave_search_var.trace_add("write", lambda *_: self._grave_view_changed())

        self.grave_extra_filters = tk.Frame(self.content, bg=BG)
        row = tk.Frame(self.grave_extra_filters, bg=BG)
        row.pack(fill="x", pady=(0, 6))
        categories = ("All types", *sorted({e.category for e in self.graveyard_entries}))
        current_cat = self.settings.get("graveyard_category", "All types")
        if current_cat not in categories:
            current_cat = "All types"
        self.text(row, "Type", 9, MUTED).pack(side="left")
        self.grave_category_var = tk.StringVar(value=current_cat)
        category = ttk.Combobox(row, textvariable=self.grave_category_var, values=categories,
                                state="readonly", style="Dark.TCombobox", width=24)
        category.pack(side="left", padx=(6, 14))
        category.bind("<<ComboboxSelected>>", self._grave_view_changed)
        self.text(row, "Status", 9, MUTED).pack(side="left")
        self.grave_status_var = tk.StringVar(
            value=("Ready to delete" if self.settings.get("graveyard_status") == "Reviewable archives"
                   else self.settings.get("graveyard_status", "All findings")))
        safety = ttk.Combobox(row, textvariable=self.grave_status_var, values=GRAVE_STATES,
                              state="readonly", style="Dark.TCombobox", width=23)
        safety.pack(side="left", padx=(6, 0))
        safety.bind("<<ComboboxSelected>>", self._grave_view_changed)
        row2 = tk.Frame(self.grave_extra_filters, bg=BG)
        row2.pack(fill="x", pady=(0, 6))
        self.text(row2, "Minimum size", 9, MUTED).pack(side="left")
        self.grave_min_size_var = tk.StringVar(value=self.settings.get("graveyard_min_size", "Any size"))
        minimum = ttk.Combobox(row2, textvariable=self.grave_min_size_var,
                               values=tuple(GRAVE_SIZES), state="readonly",
                               style="Dark.TCombobox", width=11)
        minimum.pack(side="left", padx=(6, 14))
        minimum.bind("<<ComboboxSelected>>", self._grave_view_changed)
        self.text(row2, "Sort by", 9, MUTED).pack(side="left")
        self.grave_sort_var = tk.StringVar(value=self.settings.get("graveyard_sort", "Size"))
        sort = ttk.Combobox(row2, textvariable=self.grave_sort_var, values=GRAVE_SORT_KEYS,
                            state="readonly", style="Dark.TCombobox", width=11)
        sort.pack(side="left", padx=(6, 9))
        sort.bind("<<ComboboxSelected>>", self._grave_view_changed)
        self.grave_order_var = tk.StringVar(value=self.settings.get("graveyard_order", "Descending"))
        direction = ttk.Combobox(row2, textvariable=self.grave_order_var,
                                 values=SORT_DIRECTIONS, state="readonly",
                                 style="Dark.TCombobox", width=13)
        direction.pack(side="left")
        direction.bind("<<ComboboxSelected>>", self._grave_view_changed)

        views = tk.Frame(self.grave_extra_filters, bg=BG)
        views.pack(fill="x", pady=(0, 7))
        self.text(views, "Saved view", 9, MUTED).pack(side="left")
        self.grave_preset_var = tk.StringVar(value="Custom")
        self.grave_preset_selector = ttk.Combobox(
            views, textvariable=self.grave_preset_var, values=("Custom", *sorted(saved)),
            state="readonly", style="Dark.TCombobox", width=22)
        self.grave_preset_selector.pack(side="left", padx=(6, 9))
        self.grave_preset_selector.bind("<<ComboboxSelected>>", self._grave_load_view)
        self.button(views, "Save", self._grave_save_view).pack(side="left", padx=(0, 6))
        self.button(views, "Remove", self._grave_remove_view).pack(side="left", padx=(0, 6))
        self.button(views, "Reset", self._grave_reset_view).pack(side="left")
        dedup = tk.Frame(self.grave_extra_filters, bg=BG)
        dedup.pack(fill="x", pady=(0, 9))
        self.button(dedup, "Find exact duplicate archives", self._inspect_duplicates).pack(side="left")
        self.button(dedup, "Cancel duplicate check", self._cancel_duplicate_check).pack(
            side="left", padx=(8, 0))
        self.text(dedup, "On-demand SHA-256 comparison, read-only. No deletion suggested.",
                  9, MUTED).pack(side="left", padx=(10, 0))

        note = self.panel(pad=12)
        note.pack(fill="x", pady=(0, 9))
        self.grave_count_panel = note
        self.grave_count_var = tk.StringVar()
        self.text(note, "", 11, bold=True, textvariable=self.grave_count_var).pack(anchor="w")
        self.grave_selection_var = tk.StringVar(value="Select a finding to see available actions.")
        self.text(note, "", 10, textvariable=self.grave_selection_var,
                  wraplength=800).pack(anchor="w", pady=(4, 0))
        self.text(note, "Select one file below. Delete moves it to Windows Recycle Bin after approval. "
                  "Protect prevents deleting that item; Unprotect removes only your own rule. "
                  "Installed games and managed mods remain protected.",
                  9, MUTED, wraplength=830).pack(anchor="w", pady=(4, 0))

        area = self.panel(pad=8)
        area.pack(fill="both", expand=True)
        self.grave_tree = self._tree(area,
            ("check", "name", "category", "age", "size", "decision"),
            ("SELECT", "FILE OR GAME", "TYPE", "LAST MODIFIED", "SIZE", "STATUS"),
            (54, 235, 160, 112, 108, 146))
        self.grave_tree.tag_configure("protected", foreground=WARN)
        self.grave_tree.bind("<Double-1>", lambda _e: self._grave_details())
        self.grave_tree.bind("<Button-1>", self._grave_toggle_click)
        self.grave_tree.bind("<space>", self._grave_toggle_keyboard)
        self.grave_tree.bind("<Button-3>", self._grave_context_click)
        self.grave_tree.bind("<Shift-F10>", self._grave_context_keyboard)
        self.grave_tree.bind("<Menu>", self._grave_context_keyboard)
        self.grave_tree.bind("<<TreeviewSelect>>", lambda _e: self._grave_sync_actions())
        for column, sort_key in (("name", "Name"), ("category", "Category"),
                                 ("age", "Age"), ("size", "Size"), ("decision", "Safety")):
            self.grave_tree.heading(column, command=lambda key=sort_key: self._grave_column_sort(key))
        self.graveyard_lookup = {}
        self._grave_page_keys = set()
        self._add_page_controls("grave", self._populate_graveyard)
        self._populate_graveyard()

        actions = tk.Frame(self.content, bg=BG)
        actions.pack(fill="x", pady=(9, 0))
        self.grave_delete_button = self.button(actions, "Delete selected", self._grave_recycle_one, primary=True)
        self.grave_delete_button.pack(side="left")
        self.grave_protection_button = self.button(actions, "Protect selected", self._grave_toggle_protection)
        self.grave_protection_button.pack(side="left", padx=(8, 0))
        self.button(actions, "Open folder", self._grave_open_folder).pack(side="left", padx=(8, 0))
        self.button(actions, "Why is this here?", self._grave_details).pack(side="left", padx=(8, 0))
        bulk = tk.Frame(self.content, bg=BG)
        bulk.pack(fill="x", pady=(7, 0))
        self.button(bulk, "Check eligible", self._grave_select_eligible).pack(side="left")
        self.button(bulk, "Check page", self._grave_select_all).pack(side="left", padx=(7, 0))
        self.button(bulk, "Clear checks", self._grave_clear_checks).pack(side="left", padx=(7, 0))
        self.grave_delete_checked_button = self.button(bulk, "Delete checked", self._grave_recycle_selected, danger=True)
        self.grave_delete_checked_button.pack(side="left", padx=(7, 0))
        self.text(self.content,
                  "Delete is reversible through Windows Recycle Bin when recovery is available. "
                  "It does not free space until you empty the bin. Max 160 files per approval.",
                  9, MUTED, wraplength=820).pack(anchor="w", pady=(10, 0))
        self._grave_sync_actions()

    def _inspect_duplicates(self):
        """Opt-in content read on a worker; never scan whole disks implicitly."""
        if getattr(self, "_dupe_busy", False):
            messagebox.showinfo("Already checking", "Duplicate inspection is running.")
            return
        if self.scanning or getattr(self, "cleanup_running", False):
            messagebox.showinfo("Finish current task", "Finish the scan or cleanup first.")
            return
        candidates = tuple(self.old_files)
        if not candidates:
            messagebox.showinfo("Scan first",
                "Run Scan PC first. Duplicate inspection only checks old archives "
                "from your selected Old Files folder.")
            return
        if not messagebox.askyesno("Compare archive contents?",
                "Game Grave will read up to 600 previously scanned archives and "
                "compare complete SHA-256 hashes for likely duplicates. "
                "Reading file contents may take time, but nothing is moved or changed. "
                "No deletion is authorized by matching hashes. Continue?"):
            return
        self._dupe_busy = True
        self._dupe_cancel = threading.Event()
        rules = tuple(self.settings.get("never_touch", ()))
        self.status_text.set("Checking matching-size old game archives. Read-only…")
        def work():
            try:
                report = inspect_duplicate_archives(
                    candidates, rules, cancel=self._dupe_cancel.is_set)
                self.events.put(("duplicates_found", report))
            except InterruptedError:
                self.events.put(("duplicates_canceled", None))
            except Exception as exc:
                self.events.put(("duplicates_error", str(exc)[:250]))
        try:
            threading.Thread(target=work, daemon=True).start()
        except RuntimeError as exc:
            self._dupe_busy = False
            messagebox.showerror("Could not inspect", str(exc))

    def _cancel_duplicate_check(self):
        event = getattr(self, "_dupe_cancel", None)
        if not getattr(self, "_dupe_busy", False) or event is None:
            messagebox.showinfo("No comparison running", "There is no active duplicate check.")
            return
        event.set()
        self.status_text.set("Cancel requested; stopping after the current chunk…")

    def _grave_toggle_advanced(self):
        if self.grave_extra_filters.winfo_manager():
            self.grave_extra_filters.pack_forget()
        else:
            self.grave_extra_filters.pack(fill="x", pady=(0, 8), before=self.grave_count_panel)

    def _grave_sync_actions(self):
        entry = self._grave_selected_entry()
        busy = getattr(self, "cleanup_running", False)
        action, reason = protection_action(
            entry.path, self.settings.get("never_touch", [])) if (
                entry and entry.old_file is not None) else (None, "")
        if hasattr(self, "grave_delete_button"):
            self.grave_delete_button.configure(state="normal" if entry and entry.can_recycle and not busy else "disabled")
        if hasattr(self, "grave_protection_button"):
            self.grave_protection_button.configure(
                text=(action + " selected") if action else "Protected by Game Grave",
                state="normal" if action and not busy else "disabled")
        if hasattr(self, "grave_delete_checked_button"):
            self.grave_delete_checked_button.configure(
                state="normal" if self.grave_checked and not busy else "disabled")
        if hasattr(self, "grave_selection_var"):
            if entry is None:
                self.grave_selection_var.set("Select a finding to see available actions.")
            else:
                status = ("Ready for reviewed deletion" if entry.can_recycle else
                          reason if reason else entry.protection)
                self.grave_selection_var.set(f"Selected: {entry.name}  •  {status}")

    def _populate_graveyard(self):
        if not hasattr(self, "grave_tree") or not self.grave_tree.winfo_exists():
            return
        selected = set(self.grave_tree.selection())
        visible = filter_sort_graveyard(
            self.graveyard_entries, search=self.grave_search_var.get(),
            category=self.grave_category_var.get(), status=self.grave_status_var.get(),
            minimum=self.grave_min_size_var.get(), sort=self.grave_sort_var.get(),
            order=self.grave_order_var.get())
        self.grave_tree.delete(*self.grave_tree.get_children())
        # Full filtered lookup is retained for checked items across pages.
        # The Treeview itself only creates a small bounded page.
        self.graveyard_lookup = {entry.key: entry for entry in visible}
        self.grave_checked.intersection_update(self.graveyard_lookup)
        page = page_window(visible, self._pager_indices.get("grave", 0))
        self._grave_page_keys = {entry.key for entry in page.items}
        for item in page.items:
            override = self._grave_can_override(item)
            self.grave_tree.insert("", "end", iid=item.key, values=(
                "☑" if item.key in self.grave_checked else "☐",
                item.name, item.category, f"{item.age_days} days" if item.age_days is not None else "Unknown",
                human_size(item.apparent_bytes),
                "Ready to delete" if item.can_recycle else
                ("Protected by you" if override else "Review only / protected")),
                tags=() if item.can_recycle else ("protected",))
        still_selected = [key for key in selected if key in self._grave_page_keys]
        if still_selected:
            self.grave_tree.selection_set(still_selected)
        self._grave_summary = (
            f"{page.label}  •  {len(visible)} filtered of {len(self.graveyard_entries)}"
            f"  •  {sum(entry.can_recycle for entry in visible)} eligible across pages")
        self._update_inventory_page("grave", page)
        self._grave_update_count()
        if hasattr(self, "grave_delete_button"):
            self._grave_sync_actions()

    def _grave_view_changed(self, event=None):
        if self._applying_grave_preset:
            return
        self.settings.update({
            "graveyard_sort": self.grave_sort_var.get(),
            "graveyard_order": self.grave_order_var.get(),
            "graveyard_category": self.grave_category_var.get(),
            "graveyard_status": self.grave_status_var.get(),
            "graveyard_min_size": self.grave_min_size_var.get(),
            "graveyard_search": self.grave_search_var.get()[:120],
        })
        save_settings(self.settings)
        if hasattr(self, "grave_preset_var"):
            self.grave_preset_var.set("Custom")
        self._reset_inventory_page("grave", self._populate_graveyard)

    def _grave_column_sort(self, key):
        if self.grave_sort_var.get() == key:
            self.grave_order_var.set("Ascending" if self.grave_order_var.get() == "Descending" else "Descending")
        else:
            self.grave_sort_var.set(key)
            self.grave_order_var.set("Ascending" if key in ("Name", "Category") else "Descending")
        self._grave_view_changed()

    def _grave_save_view(self):
        name = simpledialog.askstring("Save Graveyard view", "Name this filter/sort preset (32 characters max):", parent=self)
        if name is None:
            return
        name = name.strip()
        if not 1 <= len(name) <= 32 or name == "Custom":
            messagebox.showwarning("Invalid name", "Choose a name from 1 to 32 characters other than Custom.")
            return
        views = sanitize_saved_views(self.settings.get("graveyard_saved_views", {}))
        if name not in views and len(views) >= 30:
            messagebox.showwarning("Too many views", "You can save up to 30 views.")
            return
        if name in views and not messagebox.askyesno("Replace saved view?", f"Replace the existing '{name}' view?"):
            return
        views[name] = {k: self.settings[k] for k in GRAVE_PRESET_FIELDS}
        self.settings["graveyard_saved_views"] = views
        save_settings(self.settings)
        self.grave_preset_selector.configure(values=("Custom", *sorted(views)))
        self.grave_preset_var.set(name)

    def _grave_load_view(self, event=None):
        name = self.grave_preset_var.get()
        views = sanitize_saved_views(self.settings.get("graveyard_saved_views", {}))
        if name not in views:
            return
        previous_age = self.settings.get("graveyard_days", 365)
        self._applying_grave_preset = True
        self.settings.update(views[name])
        save_settings(self.settings)
        self._applying_grave_preset = False
        if previous_age != self.settings["graveyard_days"]:
            # Refresh inventory if a saved view needs files older than an earlier threshold.
            if self.settings["files_stale_days"] > self.settings["graveyard_days"]:
                self.settings["files_stale_days"] = self.settings["graveyard_days"]
                save_settings(self.settings)
                self.scan_all()
                return
        self.show_page("The Graveyard")
        self.grave_preset_var.set(name)

    def _grave_remove_view(self):
        name = self.grave_preset_var.get()
        views = sanitize_saved_views(self.settings.get("graveyard_saved_views", {}))
        if name not in views:
            messagebox.showinfo("Choose a saved view", "Pick a named saved view to remove.")
            return
        views.pop(name)
        self.settings["graveyard_saved_views"] = views
        save_settings(self.settings)
        self.grave_preset_selector.configure(values=("Custom", *sorted(views)))
        self.grave_preset_var.set("Custom")

    def _grave_reset_view(self):
        defaults = default_settings()
        for key in GRAVE_PRESET_FIELDS:
            self.settings[key] = defaults[key]
        save_settings(self.settings)
        if self.settings["files_stale_days"] > self.settings["graveyard_days"]:
            self.settings["files_stale_days"] = self.settings["graveyard_days"]
            save_settings(self.settings)
            self.scan_all()
        else:
            self.show_page("The Graveyard")

    def _change_grave_days(self, event=None):
        self.settings["graveyard_days"] = int(self.grave_days_var.get())
        save_settings(self.settings)
        if self.settings["files_stale_days"] > self.settings["graveyard_days"]:
            self.settings["files_stale_days"] = self.settings["graveyard_days"]
            save_settings(self.settings)
            self.scan_all()
        else:
            self.show_page("The Graveyard")

    def _grave_can_override(self, entry):
        """Only an otherwise ordinary archive excluded by the user's Never Touch paths."""
        return (entry.old_file is not None and
                looks_like_game_archive(Path(entry.path)) and
                is_protected_path(Path(entry.path), self.settings.get("never_touch", [])) and
                not is_protected_path(Path(entry.path), []))

    def _grave_toggle_click(self, event):
        if self.grave_tree.identify_region(event.x, event.y) != "cell" or self.grave_tree.identify_column(event.x) != "#1":
            return
        key = self.grave_tree.identify_row(event.y)
        self._grave_toggle(key)
        if key:
            self.grave_tree.selection_set(key)
            self.grave_tree.focus(key)
        return "break"

    def _grave_toggle_keyboard(self, event=None):
        for key in self.grave_tree.selection():
            self._grave_toggle(key)
        return "break"

    def _grave_update_count(self):
        self.grave_count_var.set(
            f"{getattr(self, '_grave_summary', 'Graveyard review')}  •  "
            f"{len(self.grave_checked)} checked across filtered pages")

    def _grave_toggle(self, key):
        if key not in self._grave_page_keys or key not in self.graveyard_lookup:
            return
        if key in self.grave_checked:
            self.grave_checked.remove(key)
        else:
            self.grave_checked.add(key)
        self.grave_tree.set(key, "check", "☑" if key in self.grave_checked else "☐")
        self._grave_update_count()
        if hasattr(self, "grave_delete_checked_button"):
            self._grave_sync_actions()

    def _grave_select_all(self):
        # "Check page" must not silently select thousands of other findings.
        self.grave_checked.update(self._grave_page_keys)
        self._grave_refresh_checks()

    def _grave_select_eligible(self):
        self.grave_checked.update(
            key for key in self._grave_page_keys
            if self.graveyard_lookup[key].can_recycle)
        self._grave_refresh_checks()

    def _grave_clear_checks(self):
        self.grave_checked.clear()
        self._grave_refresh_checks()

    def _grave_refresh_checks(self):
        for key in self._grave_page_keys:
            self.grave_tree.set(key, "check", "☑" if key in self.grave_checked else "☐")
        self._grave_update_count()
        if hasattr(self, "grave_delete_checked_button"):
            self._grave_sync_actions()

    def _grave_details(self):
        ids = self.grave_tree.selection()
        if not ids:
            messagebox.showinfo("Nothing selected", "Select a Graveyard finding first.")
            return
        e = self.graveyard_lookup[ids[0]]
        verdict = investigate(e.path, self.games, self.other_games, self.mod_folders,
                              self.settings.get("never_touch", []))
        messagebox.showinfo("Why this was found", f"{e.name}\n\n"
                            f"Why shown: {e.finding}\n\nSafety: {e.protection}\n\n"
                            + friendly_report(verdict, e.path)
                            + "\n\nFile size is not guaranteed recoverable space.")

    def _grave_selected_entry(self):
        selection = self.grave_tree.selection()
        return self.graveyard_lookup.get(selection[0]) if len(selection) == 1 else None

    def _grave_open_folder(self):
        entry = self._grave_selected_entry()
        if entry is None:
            messagebox.showinfo("Select one", "Select one Graveyard finding first.")
            return
        path = Path(entry.path)
        folder = path if path.is_dir() else path.parent
        if not folder.is_dir():
            messagebox.showwarning("Folder unavailable", "This folder no longer exists. Scan again to refresh the result.")
            return
        try:
            # Open a directory, never execute the selected file.
            if os.name == "nt":
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except (OSError, RuntimeError) as exc:
            messagebox.showerror("Could not open folder", str(exc))

    def _grave_toggle_protection(self):
        if getattr(self, "cleanup_running", False):
            messagebox.showinfo("Cleanup in progress",
                                "Finish the current deletion before changing protection.")
            return
        entry = self._grave_selected_entry()
        if entry is None:
            messagebox.showinfo("Choose a file", "Click an individual file in the Graveyard first.")
            return
        if entry.old_file is None:
            messagebox.showinfo("Managed file protection",
                "Installed games and managed folders are protected by Game Grave.")
            return
        action, reason = protection_action(entry.path, self.settings.get("never_touch", []))
        if action is None:
            messagebox.showinfo("Protected by Game Grave", reason)
            return
        if action == "Unprotect" and not messagebox.askyesno(
                "Unprotect this file?",
                f"Remove only your Never Touch rule for this file?\n\n{entry.path}\n\n"
                "No files will be deleted. Built-in protection remains enabled."):
            return
        try:
            updated = set_item_protection(self.settings.get("never_touch", []), entry.path,
                                          protect=(action == "Protect"))
            self.settings["never_touch"] = updated
            save_settings(self.settings)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Protection unchanged", str(exc))
            return
        self.graveyard_entries = build_graveyard(
            self.games, self.mod_folders, self.old_files,
            self.settings.get("graveyard_days", 365), updated,
            watched_mods=self.settings.get("graveyard_watchlist", []),
            recordings=getattr(self, "recordings", []))
        if action == "Protect":
            self.grave_checked.discard(entry.key)
        self._populate_graveyard()
        self.status_text.set(f"{entry.name}: {action} succeeded. No files were deleted.")
        messagebox.showinfo("Protection changed", f"{entry.name}\n\n" +
            ("Now protected. Delete is disabled." if action == "Protect" else
             "Personal protection removed. Deletion still requires explicit approval.") +
            "\n\nNo files were deleted.")

    def _grave_context_click(self, event):
        key = self.grave_tree.identify_row(event.y)
        if not key or key not in self.graveyard_lookup:
            return
        self.grave_tree.selection_set(key)
        self.grave_tree.focus(key)
        self._grave_show_context(event.x_root, event.y_root)
        return "break"

    def _grave_context_keyboard(self, event=None):
        entry = self._grave_selected_entry()
        if entry is None:
            key = self.grave_tree.focus()
            if key not in self.graveyard_lookup:
                return "break"
            self.grave_tree.selection_set(key)
        self._grave_show_context(self.grave_tree.winfo_rootx() + 45,
                                 self.grave_tree.winfo_rooty() + 45)
        return "break"

    def _grave_show_context(self, x, y):
        entry = self._grave_selected_entry()
        if entry is None:
            return
        action, _reason = (protection_action(entry.path, self.settings.get("never_touch", []))
                           if entry.old_file is not None else (None, "Managed item"))
        menu = tk.Menu(self.grave_tree, tearoff=False)
        menu.add_command(label="Details", command=self._grave_details)
        menu.add_command(label="Open folder", command=self._grave_open_folder)
        menu.add_command(label=action or "Protected by Game Grave",
                         command=self._grave_toggle_protection,
                         state="normal" if action else "disabled")
        menu.add_separator()
        menu.add_command(label="Delete…", command=self._grave_recycle_one,
                         state="normal" if entry.can_recycle else "disabled")
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _grave_detect(self):
        ids = self.grave_tree.selection()
        if not ids:
            messagebox.showinfo("Choose a finding", "Select a Graveyard item first.")
            return
        self._show_detective_report(self.graveyard_lookup[ids[0]].path)

    def _grave_recycle_one(self):
        ids = self.grave_tree.selection()
        if len(ids) != 1:
            messagebox.showinfo("Select one", "Select exactly one file to delete.")
            return
        self._grave_recycle_ids(ids)

    def _grave_recycle_selected(self):
        if not self.grave_checked:
            messagebox.showinfo("Nothing checked", "Tick files in the leftmost column first.")
            return
        self._grave_recycle_ids(list(self.grave_checked))

    def _grave_recycle_all(self):
        self._grave_recycle_ids(
            [key for key in self._grave_page_keys
             if self.graveyard_lookup[key].can_recycle])

    def _grave_recycle_ids(self, ids):
        """Confirm on the Tk thread, then process slow Windows Shell work off-UI."""
        import uuid
        if getattr(self, "cleanup_running", False) or getattr(self, "scanning", False):
            messagebox.showinfo("Game Grave is busy",
                "Wait for the current scan or deletion to finish before starting another.")
            return
        if len(ids) > DEFAULT_PAGE_SIZE:
            messagebox.showwarning("Too many files selected",
                f"Select at most {DEFAULT_PAGE_SIZE} files per cleanup. "
                "Narrow your filters or clear checks. Nothing was deleted.")
            return
        chosen = [self.graveyard_lookup[k] for k in ids if k in self.graveyard_lookup]
        if not chosen:
            messagebox.showinfo("No files selected", "Choose a file or tick eligible files first.")
            return
        if any(not entry.can_recycle for entry in chosen):
            messagebox.showwarning("Protected: deletion blocked",
                "One or more items are protected. Remove any personal protection "
                "separately before choosing Delete. Installed games, saves and mods "
                "remain protected. Nothing was deleted.")
            return
        total = sum(entry.apparent_bytes for entry in chosen)
        preview = "\n".join("• " + entry.name for entry in chosen[:7])
        if len(chosen) > 7:
            preview += f"\n…and {len(chosen) - 7} more"
        if not messagebox.askyesno("Delete selected files?",
                f"Move {len(chosen)} file(s) ({human_size(total)} apparent size) to the "
                "Windows Recycle Bin?\n\n" + preview +
                "\n\nCheck recordings and archives before deleting. Each file needs "
                "Windows recovery verification, which may take a little time. "
                "Nothing is permanently deleted. Disk space is not reclaimed "
                "until the Recycle Bin is emptied."):
            return

        # The user has approved an exact immutable inventory snapshot. Never ask
        # Tk questions or manipulate widgets from the worker thread.
        session = str(uuid.uuid4())
        selected = tuple(chosen)
        protected = tuple(self.settings.get("never_touch", ()))
        self.cleanup_running = True
        self.scan_button.configure(state="disabled", bg=RAISED)
        self.status_text.set(f"Delete started: verifying Windows recovery for {len(selected)} file(s)…")
        self._grave_sync_actions()

        def worker():
            try:
                result = recycle_reviewed_entries(
                    selected, protected, session,
                    progress=lambda done, count: self.events.put(
                        ("grave_cleanup_progress", (done, count))))
                self.events.put(("grave_cleanup_complete", result))
            except Exception as exc:
                # Always reset busy state on the UI thread, never claim success.
                self.events.put(("grave_cleanup_error", str(exc)[:350]))

        try:
            threading.Thread(target=worker, daemon=True).start()
        except RuntimeError as exc:
            self.cleanup_running = False
            self.scan_button.configure(state="normal", bg=ACCENT)
            self._grave_sync_actions()
            messagebox.showerror("Deletion could not start", str(exc))

    def _files_page(self):
        self.header("Old Files", "Review files by last-modified date. Multi-select and send only what you choose to Recycle Bin.")
        bar = tk.Frame(self.content, bg=BG)
        bar.pack(fill="x", pady=(0, 13))
        folder = self.settings["scan_folder"]
        self.text(bar, f"Scanning: {folder}", 10, MUTED, wraplength=580).pack(side="left", fill="x", expand=True)
        self.button(bar, "Change folder", self._change_folder).pack(side="right")
        self.file_days_var = tk.StringVar(value=str(self.settings["files_stale_days"]))
        days = ttk.Combobox(bar, textvariable=self.file_days_var, values=("30", "90", "180", "365", "730"),
                            state="readonly", style="Dark.TCombobox", width=5)
        days.pack(side="right", padx=(5, 18))
        days.bind("<<ComboboxSelected>>", self._change_file_days)
        self.text(bar, "Older than (days)", 9, MUTED).pack(side="right")
        sort_bar = tk.Frame(self.content, bg=BG)
        sort_bar.pack(fill="x", pady=(0, 8))
        self.text(sort_bar, "Sort old files by", 9, MUTED).pack(side="left")
        self.files_sort_var = tk.StringVar(value=self.settings.get("files_sort", "Largest first"))
        file_sort = ttk.Combobox(sort_bar, textvariable=self.files_sort_var, values=FILES_SORT_OPTIONS,
                                 state="readonly", style="Dark.TCombobox", width=18)
        file_sort.pack(side="left", padx=(9, 0))
        file_sort.bind("<<ComboboxSelected>>", lambda _e: self._set_view_sort("files_sort", self.files_sort_var, self._populate_files))
        p = self.panel(pad=10)
        p.pack(fill="both", expand=True)
        self.file_tree = self._tree(p, ("file", "age", "size", "location"),
                                    ("FILENAME", "LAST MODIFIED", "SIZE", "LOCATION"),
                                    (235, 140, 115, 300))
        self.file_tree.tag_configure("protected", foreground=WARN)
        self._add_page_controls("files", self._populate_files)
        self._populate_files()
        actions = tk.Frame(self.content, bg=BG)
        actions.pack(fill="x", pady=(14, 0))
        self.button(actions, "Delete selected", self._recycle_selected, primary=True).pack(side="left")
        self.button(actions, "Select all shown", lambda: self.file_tree.selection_set(self.file_tree.get_children())).pack(
            side="left", padx=12)
        self.button(actions, "Open containing folder", self._open_file_folder).pack(side="left")
        self.text(self.content,
                  "No permanent deletion. Windows Recycle Bin must be emptied later to free the space. "
                  "Files changed since this scan are skipped.",
                  9, MUTED, wraplength=820).pack(anchor="w", pady=(15, 0))

    def _change_file_days(self, event=None):
        self.settings["files_stale_days"] = int(self.file_days_var.get())
        save_settings(self.settings)
        self.scan_all()

    def _populate_files(self):
        if not hasattr(self, "file_tree") or not self.file_tree.winfo_exists():
            return
        self.file_tree.delete(*self.file_tree.get_children())
        self.file_lookup = {}
        page = page_window(sort_files(self.old_files, self.files_sort_var.get()),
                           self._pager_indices.get("files", 0))
        for index, item in enumerate(page.items):
            iid = str(page.start + index)
            path = Path(item.path)
            protected = is_protected_path(path, self.settings.get("never_touch", []))
            self.file_tree.insert("", "end", iid=iid,
                                  values=(("PROTECTED: " if protected else "") + path.name,
                                          age_text(item.modified), human_size(item.size), str(path.parent)),
                                  tags=("protected",) if protected else ())
            self.file_lookup[iid] = item
        self._update_inventory_page("files", page)

    def _change_folder(self):
        folder = filedialog.askdirectory(title="Choose folder to scan for old files", initialdir=self.settings["scan_folder"])
        if not folder:
            return
        if not safe_scan_root(Path(folder)):
            messagebox.showerror("Folder blocked", "Choose an ordinary folder. System folders and entire drives are blocked.")
            return
        self.settings["scan_folder"] = folder
        save_settings(self.settings)
        self.scan_all()

    def _open_file_folder(self):
        selected = self.file_tree.selection()
        if not selected:
            return
        item = self.file_lookup.get(selected[0])
        if item and os.name == "nt":
            try:
                os.startfile(str(Path(item.path).parent))
            except OSError as exc:
                messagebox.showerror("Cannot open folder", str(exc))

    def _recycle_selected(self):
        """Confirm on the UI thread, perform slow Windows Shell work separately."""
        import uuid
        if getattr(self, "cleanup_running", False) or self.scanning:
            messagebox.showinfo("Game Grave is busy",
                                "Finish the current scan or deletion before starting another.")
            return
        if not hasattr(self, "file_tree") or not self.file_tree.winfo_exists():
            return
        items = [self.file_lookup[k] for k in self.file_tree.selection() if k in self.file_lookup]
        if not items:
            messagebox.showinfo("No files selected", "Select files first.")
            return
        if len(items) > DEFAULT_PAGE_SIZE:
            messagebox.showwarning("Too many files", f"Select at most {DEFAULT_PAGE_SIZE} files.")
            return
        if not messagebox.askyesno("Delete selected files?",
                f"Move {len(items)} file(s) ({human_size(sum(f.size for f in items))} apparent size) "
                "to Windows Recycle Bin?\n\nWindows will verify safe recovery for each file. "
                "This can take a little time; the app will remain responsive. "
                "No permanent deletion is performed. Disk space will not be freed until "
                "the Recycle Bin is emptied."):
            return
        session = str(uuid.uuid4())
        selected = tuple(items)
        protected = tuple(self.settings.get("never_touch", ()))
        reviewed_root = Path(self.settings["scan_folder"])
        reviewed_age = int(self.settings.get("files_stale_days", 180))
        self.cleanup_running = True
        self.scan_button.configure(state="disabled", bg=RAISED)
        self.status_text.set(f"Delete started: verifying {len(selected)} file(s)…")

        def worker():
            try:
                outcome = recycle_old_files(
                    selected, protected, session,
                    progress=lambda done, count: self.events.put(
                        ("old_cleanup_progress", (done, count))),
                    review_root=reviewed_root, min_age_days=reviewed_age)
                self.events.put(("old_cleanup_complete", outcome))
            except Exception as exc:
                self.events.put(("old_cleanup_error", str(exc)[:350]))

        try:
            threading.Thread(target=worker, daemon=True).start()
        except RuntimeError as exc:
            self.cleanup_running = False
            self.scan_button.configure(state="normal", bg=ACCENT)
            messagebox.showerror("Deletion could not start", str(exc))

    def _automation_page(self):
        self.header("Automation", "Weekly housekeeping, without giving a program permission to wipe your game library.")
        settings = self.panel()
        settings.pack(fill="x", pady=(0, 15))
        self.text(settings, "Weekly Downloads cleanup", 15, bold=True).pack(anchor="w", pady=(0, 7))
        self.text(settings, "Sunday at 12:00 PM  •  Windows Task Scheduler  •  initially OFF", 10, MUTED).pack(anchor="w")
        cfg = tk.Frame(settings, bg=PANEL)
        cfg.pack(fill="x", pady=(19, 12))
        self.text(cfg, "Delete files older than", 11).pack(side="left")
        self.auto_days_var = tk.StringVar(value=str(self.settings["auto_days"]))
        age = ttk.Combobox(cfg, textvariable=self.auto_days_var, values=("180", "365", "730"),
                           state="readonly", style="Dark.TCombobox", width=7)
        age.pack(side="left", padx=15)
        self.text(cfg, "days (based on last modified date)", 10, MUTED).pack(side="left")
        self.extra_var = tk.BooleanVar(value=self.settings["auto_include_archives"])
        ttk.Checkbutton(settings, text="Also include old ZIP, 7z, RAR, ISO, MSI and EXE files",
                        variable=self.extra_var, style="Dark.TCheckbutton").pack(anchor="w", pady=(3, 8))
        self.text(settings, "Without that checkbox, only .tmp and .log files qualify. Documents, pictures, saves, "
                  "game installations and other folders are excluded.",
                  10, MUTED, wraplength=790).pack(anchor="w", pady=(0, 15))
        buttons = tk.Frame(settings, bg=PANEL)
        buttons.pack(fill="x")
        self.button(buttons, "Preview eligible files", self._preview_auto).pack(side="left")
        self.button(buttons, "Enable weekly cleanup" if not self.settings["auto_enabled"]
                    else "Update weekly cleanup", self._enable_schedule, primary=True).pack(side="left", padx=12)
        if self.settings["auto_enabled"]:
            self.button(buttons, "Disable automation", self._disable_schedule, danger=True).pack(side="left")
        info = self.panel()
        info.pack(fill="x")
        self.text(info, "Current settings", 15, bold=True).pack(anchor="w", pady=(0, 13))
        enabled = self.settings["auto_enabled"]
        self.text(info, f"Schedule: {'ENABLED' if enabled else 'DISABLED'}", 12,
                  ACCENT if enabled else WARN, True).pack(anchor="w", pady=(0, 10))
        self.text(info, "Rules always apply only to your Windows Downloads folder, even if you manually scan "
                  "another location. Files go to the Recycle Bin; Steam games are never automatically removed.",
                  10, MUTED, wraplength=780).pack(anchor="w")
        self.text(info, "Note: Recycle Bin contents still use disk space until Windows empties the bin.",
                  10, WARN).pack(anchor="w", pady=(10, 0))

    def _save_auto_controls(self):
        self.settings["auto_days"] = int(self.auto_days_var.get())
        self.settings["auto_include_archives"] = bool(self.extra_var.get())
        save_settings(self.settings)

    def _preview_auto(self):
        self._save_auto_controls()
        extensions = AUTO_BASE_EXTENSIONS | (AUTO_EXTRA_EXTENSIONS if self.extra_var.get() else set())
        try:
            found = scan_old_files(downloads_dir(), self.settings["auto_days"], allowed_extensions=extensions)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Unable to preview", str(exc))
            return
        example = "\n".join(Path(item.path).name for item in sorted(found, key=lambda f: -f.size)[:7])
        messagebox.showinfo("Automatic cleanup preview",
                            f"Eligible files: {len(found)}\nTotal apparent size: {human_size(sum(f.size for f in found))}\n\n"
                            f"Examples:\n{example or '(none)'}\n\nNothing was deleted."
                            )

    def _enable_schedule(self):
        if os.name != "nt":
            messagebox.showerror("Windows only", "Task scheduling requires Windows.")
            return
        self._save_auto_controls()
        count_text = ".tmp and .log"
        if self.settings["auto_include_archives"]:
            count_text += ", ZIP/7z/RAR/ISO/MSI/EXE"
        if not messagebox.askyesno("Enable automated recycling?",
                                   f"Every Sunday at noon, Game Grave will recycle {count_text} files "
                                   f"in Downloads last modified over {self.settings['auto_days']} days ago.\n\n"
                                   "This does not uninstall games or empty the Recycle Bin. Enable?"):
            return
        previous = self.settings["auto_enabled"]
        try:
            folder = config_dir()
            folder.mkdir(parents=True, exist_ok=True)
            if getattr(sys, "frozen", False):
                command = f'"{sys.executable}" --auto'
            else:
                python = Path(sys.executable)
                no_window = python.with_name("pythonw.exe")
                if no_window.is_file():
                    python = no_window
                app = Path(__file__).resolve().parent / "launcher.py"
                command = f'"{python}" "{app}" --auto'
            launcher = folder / "Run_Weekly_Cleanup.cmd"
            launcher.write_text("@echo off\n" + command + "\n", encoding="utf-8")
            args = ["schtasks", "/Create", "/SC", "WEEKLY", "/D", "SUN", "/ST", "12:00",
                    "/TN", TASK_NAME, "/TR", f'"{launcher}"', "/F"]
            result = subprocess.run(args, capture_output=True, text=True,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=15)
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout or "Windows Task Scheduler refused the task.").strip())
            self.settings["auto_enabled"] = True
            save_settings(self.settings)
            log_event("Automation enabled", f"Weekly at noon Sunday; days={self.settings['auto_days']}")
            self.show_page("Automation")
            messagebox.showinfo("Scheduled", "Weekly cleanup is enabled for Sundays at 12:00 PM.")
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.settings["auto_enabled"] = previous
            save_settings(self.settings)
            messagebox.showerror("Couldn't schedule cleanup", str(exc))

    def _disable_schedule(self):
        if not messagebox.askyesno("Disable cleanup?", "Stop automatic weekly recycling?"):
            return
        # Disable locally first so even an orphaned task cannot delete files.
        self.settings["auto_enabled"] = False
        save_settings(self.settings)
        if os.name == "nt":
            result = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                                    capture_output=True, text=True,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                messagebox.showwarning("Cleanup disabled",
                                       "Automatic recycling is OFF inside Game Grave, but Windows did not confirm "
                                       "task deletion. Check Task Scheduler if needed.")
        log_event("Automation disabled", "Weekly cleanup disabled")
        self.show_page("Automation")

    def _activity_page(self):
        self.header("Cleanup History", "Plain-English history of what Game Grave did, skipped, and only suggested.")
        self.activity_events = get_activity()
        self.activity_lookup = {}
        filters = tk.Frame(self.content, bg=BG)
        filters.pack(fill="x", pady=(0, 11))
        self.activity_search = tk.StringVar(value="")
        entry = tk.Entry(filters, textvariable=self.activity_search, bg=PANEL, fg=TEXT,
                         insertbackground=TEXT, relief="flat", font=("Segoe UI", 11), width=28)
        entry.pack(side="left", ipady=8, padx=(0, 12))
        self.activity_search.trace_add("write", lambda *_: self._populate_activity())
        self.activity_status = tk.StringVar(value="All activity")
        status_picker = ttk.Combobox(filters, textvariable=self.activity_status,
                                     values=("All activity", "Done", "Needs review", "Skipped", "Preview", "Settings"),
                                     state="readonly", style="Dark.TCombobox", width=16)
        status_picker.pack(side="left", padx=(0, 12))
        status_picker.bind("<<ComboboxSelected>>", lambda *_: self._populate_activity())
        self.button(filters, "Export CSV", self._export_activity).pack(side="right")
        self.button(filters, "Refresh", lambda: self.show_page("Activity")).pack(side="right", padx=(0, 10))
        self.activity_count = tk.StringVar(value="")
        tk.Label(self.content, textvariable=self.activity_count, bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 9))
        listing = self.panel(pad=8)
        listing.pack(fill="both", expand=True)
        self.activity_tree = self._tree(listing, ("date", "status", "title", "summary"),
                                       ("WHEN", "RESULT", "WHAT HAPPENED", "ITEM OR DETAILS"),
                                       (185, 125, 235, 350))
        self.activity_tree.configure(selectmode="browse", height=11, show="tree headings")
        self.activity_tree.heading("#0", text="▸")
        self.activity_tree.column("#0", width=36, minwidth=36, stretch=False)
        self.activity_tree.tag_configure("Needs review", foreground=WARN)
        self.activity_tree.tag_configure("Skipped", foreground=WARN)
        self.activity_tree.tag_configure("Done", foreground=ACCENT)
        self.activity_tree.bind("<<TreeviewSelect>>", self._show_activity_detail)
        detail = self.panel(pad=13)
        detail.pack(fill="x", pady=(12, 0))
        self.activity_detail_title = tk.StringVar(value="Select an entry to see what happened and whether you need to do anything.")
        self.activity_detail_explanation = tk.StringVar(value="")
        self.activity_detail_path = tk.StringVar(value="")
        tk.Label(detail, textvariable=self.activity_detail_title, bg=PANEL, fg=TEXT,
                 font=("Segoe UI Semibold", 11), anchor="w").pack(anchor="w")
        tk.Label(detail, textvariable=self.activity_detail_explanation, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 10), wraplength=820, justify="left").pack(anchor="w", pady=(5, 2))
        tk.Label(detail, textvariable=self.activity_detail_path, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9), wraplength=820, justify="left").pack(anchor="w", pady=(3, 0))
        self.text(self.content, "History is stored on this PC only. CSV exports may contain local file paths.",
                  9, MUTED).pack(anchor="w", pady=(8, 0))
        self._populate_activity()

    def _filtered_activity(self):
        query = self.activity_search.get().strip().lower()
        status = self.activity_status.get()
        results = []
        for event in self.activity_events:
            item = friendly_activity(event)
            if status != "All activity" and item["status"] != status:
                continue
            if query and query not in (item["title"] + " " + item["details"] + " " + item["status"]).lower():
                continue
            results.append((event, item))
        return results

    def _populate_activity(self):
        if not hasattr(self, "activity_tree") or not self.activity_tree.winfo_exists():
            return
        self.activity_tree.delete(*self.activity_tree.get_children())
        self.activity_lookup.clear()
        matches = [raw for raw, _item in self._filtered_activity()]
        for i, group in enumerate(group_activity(matches)):
            events = group["events"]
            if group["session"]:
                newest = friendly_activity(events[0])
                key = f"session:{i}"
                summary = session_caption(group)
                self.activity_tree.insert("", "end", iid=key, open=False,
                    values=(newest["date"], "Session", "Cleanup session (expand)", summary))
                self.activity_lookup[key] = {
                    "title": "Full cleanup session", "status": "Details",
                    "explanation": f"{len(events)} recorded events. Click the triangle at left to inspect every item.",
                    "details": summary,
                }
                for j, raw in enumerate(reversed(events)):
                    item = friendly_activity(raw)
                    iid = f"{key}:{j}"
                    self.activity_tree.insert(key, "end", iid=iid,
                        values=(item["date"], item["status"], item["title"], item["summary"]),
                        tags=(item["status"],))
                    self.activity_lookup[iid] = item
            else:
                item = friendly_activity(events[0])
                key = f"event:{i}"
                self.activity_tree.insert("", "end", iid=key,
                    values=(item["date"], item["status"], item["title"], item["summary"]),
                    tags=(item["status"],))
                self.activity_lookup[key] = item
        self.activity_count.set(f"Showing {len(matches)} of {len(self.activity_events)} recorded events. "
                                "Expand a session to see every file and result.")
        self.activity_detail_title.set("Choose an event or expand a cleanup session to see exactly what happened.")
        self.activity_detail_explanation.set("")
        self.activity_detail_path.set("")

    def _show_activity_detail(self, event=None):
        chosen = self.activity_tree.selection()
        if not chosen:
            return
        item = self.activity_lookup.get(chosen[0])
        if not item:
            return
        self.activity_detail_title.set(item["title"] + "  |  " + item["status"])
        self.activity_detail_explanation.set(item["explanation"])
        self.activity_detail_path.set("Recorded detail: " + item["details"])

    def _export_activity(self):
        items = [raw for raw, _ in self._filtered_activity()]
        if not items:
            messagebox.showinfo("Nothing to export", "No activity matches the current filters.")
            return
        target = filedialog.asksaveasfilename(title="Save Game Grave history", defaultextension=".csv",
                    initialfile="Game Grave_Cleanup_History.csv", filetypes=[("CSV spreadsheet", "*.csv")])
        if not target:
            return
        try:
            count = export_activity_csv(Path(target), items)
            messagebox.showinfo("Report saved", f"Saved {count} history entries to your chosen location.\n\n"
                                "Reminder: the report may include local file paths.")
        except OSError as exc:
            messagebox.showerror("Could not export report", str(exc))


    def _explain_any_folder(self):
        folder = filedialog.askdirectory(title="Select a game or mod folder to explain")
        if not folder:
            return
        try:
            messagebox.showinfo("Game Grave folder explanation", explain_folder(Path(folder)))
        except (OSError, ValueError) as exc:
            messagebox.showwarning("Unable to inspect folder", str(exc))

    def _available_drives(self):
        """List present volumes only. Users can always choose a target folder."""
        seen = set()
        values = []
        for raw in ([self.settings.get("scan_folder", "")] +
                    [g.install_path for g in self.games] +
                    [g.install_path for g in self.other_games]):
            try:
                p = Path(raw)
                if not p.exists():
                    continue
                root = str(Path(p.anchor or p))
                if root not in seen:
                    values.append(root)
                    seen.add(root)
            except (ValueError, OSError):
                continue
        if not values and os.name == "nt":
            for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
                path = letter + ":\\"
                if Path(path).exists():
                    values.append(path)
        return values

    def _make_room_page(self):
        self.header("Make Room", "Need space for another game? Find your options in three simple steps.")
        header = self.panel()
        header.pack(fill="x", pady=(0, 12))
        self.text(header, "1. How much free space do you want?", 14, bold=True).pack(anchor="w")
        controls = tk.Frame(header, bg=PANEL)
        controls.pack(fill="x", pady=(9, 12))
        self.goal_gb = tk.IntVar(value=100)
        tk.Spinbox(controls, from_=1, to=4000, increment=25, textvariable=self.goal_gb,
                   width=7, bg=RAISED, fg=TEXT, insertbackground=TEXT,
                   font=("Segoe UI", 14)).pack(side="left")
        self.text(controls, "GB", 11, MUTED, True).pack(side="left", padx=9)
        self.text(header, "2. Which drive will hold the game?", 14, bold=True).pack(anchor="w")
        target_row = tk.Frame(header, bg=PANEL)
        target_row.pack(fill="x", pady=(9, 9))
        drives = self._available_drives()
        self.room_drive = tk.StringVar(value=drives[0] if drives else "")
        self.room_drive_combo = ttk.Combobox(target_row, textvariable=self.room_drive,
                  state="readonly", values=drives, style="Dark.TCombobox", width=20)
        self.room_drive_combo.pack(side="left")
        self.button(target_row, "Choose other folder", self._choose_room_drive).pack(side="left", padx=9)
        self.text(header, "3. Review your options. Nothing is deleted here.", 13, bold=True).pack(anchor="w", pady=(5, 6))
        self.button(header, "Find ways to make room", self._render_room_plan, primary=True).pack(anchor="w")
        self.plan_body = self.panel()
        self.plan_body.pack(fill="both", expand=True, pady=(12, 0))
        self._render_room_plan()

    def _choose_room_drive(self):
        chosen = filedialog.askdirectory(title="Choose a folder on the drive where the game will go")
        if not chosen:
            return
        drive = str(Path(chosen).anchor or Path(chosen))
        existing = list(self.room_drive_combo.cget("values"))
        if drive not in existing:
            self.room_drive_combo.configure(values=existing + [drive])
        self.room_drive.set(drive)
        self._render_room_plan()

    def _render_room_plan(self):
        if not hasattr(self, "plan_body") or not self.plan_body.winfo_exists():
            return
        for child in self.plan_body.winfo_children():
            child.destroy()
        try:
            goal = int(self.goal_gb.get())
            drive = self.room_drive.get().strip()
            if not drive:
                self.text(self.plan_body, "Choose a drive, then scan your PC.",
                          12, MUTED).pack(anchor="w")
                return
            result = plan_for_drive(goal, drive, self.old_files, self.games,
                                    self.settings.get("never_touch", []))
        except (OSError, ValueError, tk.TclError) as exc:
            self.text(self.plan_body, "Can't check that drive. Choose an available drive and try again.",
                      12, WARN).pack(anchor="w")
            return
        self.text(self.plan_body, "Your space plan", 15, bold=True).pack(anchor="w", pady=(0, 6))
        self.text(self.plan_body, f"Free right now: {human_size(result['free_bytes'])}.  "
                 f"Your goal: {human_size(result['target_bytes'])}, plus 10 GB of breathing room.",
                 11, bold=True, wraplength=800).pack(anchor="w", pady=(0, 6))
        if result['missing_bytes']:
            self.text(self.plan_body, f"Still needed: {human_size(result['missing_bytes'])}.",
                      12, WARN, True).pack(anchor="w", pady=(0, 8))
        else:
            self.text(self.plan_body, "This drive already has enough free space for your target.",
                      11, ACCENT, True).pack(anchor="w", pady=(0, 8))
        self.text(self.plan_body, "Verified space ready to reclaim: 0 GB. "
                  "File sizes are not guaranteed savings.", 10, WARN,
                  wraplength=800).pack(anchor="w", pady=(0, 8))
        if not self.last_scan:
            self.text(self.plan_body, "Run Scan PC above first to find games and older downloads.",
                      10, MUTED).pack(anchor="w", pady=(0, 7))
        candidates = result['candidates'][:3]
        cost_notes = regret_calculator(candidates,
                    build_game_dna(self.games, self.other_games, self.mod_folders, self.save_findings))
        self.text(self.plan_body, "Old game/mod downloads to review", 12, bold=True).pack(anchor="w")
        if not candidates:
            self.text(self.plan_body, "No matching older game archives found on this drive. "
                      "You can still review games or scan another folder.",
                      10, MUTED, wraplength=800).pack(anchor="w", pady=(3, 5))
        for candidate, cost in zip(candidates, cost_notes):
            self.text(self.plan_body, f"• {candidate.name}  ·  {human_size(candidate.apparent_bytes)} "
                      f"· recovery effort: {cost['recovery_cost']} (check before removing)",
                      10, MUTED, wraplength=800).pack(anchor="w", pady=2)
        self.text(self.plan_body, "Installed games to inspect in Steam", 12, bold=True).pack(anchor="w", pady=(10, 2))
        if result['games_to_review']:
            for g in result['games_to_review'][:2]:
                self.text(self.plan_body, f"• {g.name}  ·  {human_size(g.size)} "
                          "(launcher uninstall only)", 10, MUTED).pack(anchor="w", pady=2)
        else:
            self.text(self.plan_body, "No Steam games with known activity dates on this drive.",
                      10, MUTED).pack(anchor="w", pady=(3, 5))
        actions = tk.Frame(self.plan_body, bg=PANEL)
        actions.pack(fill="x", pady=(12, 0))
        self.button(actions, "Review The Graveyard", lambda: self.show_page("The Graveyard"),
                    primary=True).pack(side="left")
        self.button(actions, "Review games", lambda: self.show_page("Steam Games")).pack(side="left", padx=9)
        self.button(actions, "Inspect mods", lambda: self.show_page("Game Mods")).pack(side="left")
        self.text(self.plan_body, "Protected modlists and settings are excluded. Moving an archive to the Recycle Bin "
                  "doesn't immediately free space on that drive.",
                  9, MUTED, wraplength=800).pack(anchor="w", pady=(8, 0))

    def _undo_page(self):
        self.header("Undo Center", "Check and restore files sent to the Windows Recycle Bin where recovery remains possible.")
        box = self.panel(pad=9)
        box.pack(fill="both", expand=True)
        self.undo_tree = self._tree(box, ("name", "date", "size", "status"),
                                    ("FILE", "WHEN", "ORIGINAL SIZE", "RECOVERY STATUS"),
                                    (270, 210, 140, 180))
        self.undo_lookup = {}
        for idx, rec in enumerate(reversed(get_records())):
            key = str(idx)
            self.undo_lookup[key] = rec
            self.undo_tree.insert("", "end", iid=key,
                                  values=(Path(rec["path"]).name, rec.get("time", "")[:19].replace("T", " "),
                                          human_size(rec.get("size", 0)), rec.get("state", "Not checked")))
        row = tk.Frame(self.content, bg=BG)
        row.pack(fill="x", pady=(12, 0))
        self.button(row, "Check selected recovery", self._check_undo, primary=True).pack(side="left")
        self.button(row, "Restore selected file", self._restore_undo).pack(side="left", padx=10)
        self.button(row, "Refresh history", lambda: self.show_page("Undo Center")).pack(side="left")
        self.text(self.content, "Restore is refused when there are multiple possible matches or a file already exists at its original path. "
                  "Windows may empty the Recycle Bin at any time. Recycled bytes are not counted as freed space.",
                  9, MUTED, wraplength=810).pack(anchor="w", pady=(15, 0))

    def _undo_record(self):
        if not hasattr(self, "undo_tree") or not self.undo_tree.winfo_exists():
            return None
        selected = self.undo_tree.selection()
        if len(selected) != 1:
            messagebox.showinfo("Choose a file", "Select exactly one file from the recovery history.")
            return None
        return self.undo_lookup.get(selected[0])

    def _check_undo(self):
        rec = self._undo_record()
        if rec is None:
            return
        self._undo_worker(rec, perform=False)

    def _restore_undo(self):
        rec = self._undo_record()
        if rec is None:
            return
        if not messagebox.askyesno("Restore selected file?", "Ask Windows to restore this file to its original path?\n\n"
                                   + rec["path"] + "\n\nGame Grave will not overwrite an existing file."):
            return
        self._undo_worker(rec, perform=True)

    def _undo_worker(self, rec, perform):
        self.status_text.set("Checking Recycle Bin…" if not perform else "Requesting a cautious restore…")
        def worker():
            try:
                result = restore(rec["id"]) if perform else check_restore(rec["id"])
                self.events.put(("undo_result", (perform, result)))
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                self.events.put(("undo_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _resurrection_lab_page(self):
        self.header("Resurrection Lab", "Five tools to check, rehearse, preserve, rewind, and move your gaming setup.")
        self.button(self.content, "See how Resurrection works · visual guide",
                    self._open_resurrection_visual).pack(anchor="w", pady=(0, 10))
        actions = [
            ("01 · Missing Pieces", "Find missing MO2 mod folders and unresolved recovery dependencies. "
             "The ZIP is checked, but an intact archive never proves game compatibility.",
             self._lab_missing_pieces),
            ("02 · Resurrection Rehearsal", "Temporarily extract and hash-check a full kit in an isolated "
             "test folder. It never touches live games and removes its own temporary copy.",
             self._lab_rehearsal),
            ("03 · Living Kits", "Compare an older kit with the folders you choose now. "
             "Save an independent new version only after reviewing changes.",
             self._lab_living),
            ("04 · Time Machine", "Compare kit versions with SHA-256 content checks, then optionally stage "
             "an older snapshot without overwriting current saves.",
             self._lab_time_machine),
            ("05 · PC-to-PC Resurrection", "Prepare a verified folder for a USB drive or other transfer. "
             "Reinstall the game through its launcher on the destination PC.",
             self._lab_transfer),
        ]
        for label, desc, fn in actions:
            panel = self.panel(pad=11)
            panel.pack(fill="x", pady=(0, 8))
            self.button(panel, label, fn, primary=(label.startswith("01"))).pack(side="left", padx=(0, 16))
            self.text(panel, desc, 9, MUTED, wraplength=560).pack(side="left", anchor="w")
        footer = tk.Frame(self.content, bg=BG)
        footer.pack(fill="x", pady=(5, 0))
        self.button(footer, "See kit versions in a folder", self._lab_list_versions).pack(side="left")
        self.button(footer, "Restore older kit safely", self._preview_resurrection_kit).pack(
            side="left", padx=8)
        self.button(footer, "Back to Save Vault", lambda: self.show_page("Save Vault")).pack(
            side="right")
        watch_buttons = tk.Frame(self.content, bg=BG)
        watch_buttons.pack(fill="x", pady=(6, 0))
        self.button(watch_buttons, "Track a kit (opt in)", self._lab_track).pack(side="left")
        self.button(watch_buttons, "Check tracked kits", self._lab_check_watches).pack(side="left", padx=8)
        self.button(watch_buttons, "Stop tracking a kit", self._lab_stop_watching).pack(side="left")
        self.text(self.content, "Local-only, on-demand. No cloud uploads, forced accounts, "
                  "automatic live file rollback, or hidden background monitoring. "
                  "Only new, user-approved backup/transfer files are created.",
                  9, WARN, wraplength=810).pack(anchor="w", pady=(10, 0))

    def _open_resurrection_visual(self):
        """A simple, responsive explanation of recovery safety and user control."""
        window = tk.Toplevel(self)
        window.title("Game Grave · Resurrection visual guide")
        window.geometry("820x345")
        window.minsize(440, 420)
        window.configure(bg=BG)
        frame = tk.Frame(window, bg=PANEL, padx=16, pady=16,
                         highlightbackground=LINE, highlightthickness=1)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        colors = {"panel": PANEL, "raised": RAISED, "text": TEXT,
                  "muted": MUTED, "accent": ACCENT, "blue": BLUE,
                  "warn": WARN, "line": LINE}
        resurrection_guide(frame, colors=colors).pack(fill="both", expand=True)
        self.button(frame, "Got it", window.destroy).pack(anchor="e", pady=(5, 0))
        window.bind("<Escape>", lambda _event: window.destroy())

    def _lab_manifest(self, label="Choose Resurrection Kit manifest"):
        return filedialog.askopenfilename(
            title=label,
            filetypes=[("Game Grave Resurrection Kit", "*.ggkit.json"), ("JSON files", "*.json")])

    def _lab_work(self, event, description, task):
        self.status_text.set(description)
        def worker():
            try:
                output = task()
                self.events.put((event, output))
            except (OSError, ValueError, RuntimeError, PermissionError,
                    FileExistsError, zipfile.BadZipFile, EOFError) as exc:
                self.events.put(("lab_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _lab_missing_pieces(self):
        manifest = self._lab_manifest("Select kit to check for missing components")
        if manifest:
            self._lab_work("lab_missing", "Checking kit integrity and required MO2 entries…",
                           lambda: missing_pieces(Path(manifest)))

    def _lab_rehearsal(self):
        manifest = self._lab_manifest("Choose kit to rehearse safely")
        if not manifest:
            return
        parent = filedialog.askdirectory(
            title="Choose a scratch folder with sufficient free space (NOT a live game directory)")
        if not parent:
            return
        if not messagebox.askyesno("Rehearse restoration?",
                "Game Grave will create a temporary copy of this kit in:\n"
                + parent + "\n\n"
                "It will hash-check the extracted files and remove ONLY its own "
                "temporary test folder. This can require significant disk space. "
                "The game and mod manager will NOT be launched. Proceed?"):
            return
        self._lab_work("lab_rehearsal", "Rehearsing kit extraction and SHA-256 checks…",
                       lambda: rehearse_kit(Path(manifest), Path(parent), record=True))

    def _lab_living(self):
        previous = self._lab_manifest("Choose existing kit to compare with live folders")
        if not previous:
            return
        try:
            meta, _archive = _manifest_for(Path(previous))
            if meta.get("schema") != 2 or not isinstance(meta.get("roles"), list):
                raise ValueError("Living revisions require an existing v2 kit manifest.")
            roles = [r.get("name") for r in meta["roles"] if isinstance(r, dict)]
            if not roles or len(roles) != len(set(roles)) or not set(roles).issubset(
                    {"Saves", "Mods", "Profiles", "Configs"}):
                raise ValueError("This kit lists unsupported backup folder categories.")
        except (OSError, ValueError) as exc:
            messagebox.showwarning("Unsupported kit", str(exc))
            return
        sources = {}
        for role in roles:
            path = filedialog.askdirectory(
                title=f"Select current {role} folder corresponding to the old kit")
            if not path:
                return
            sources[role] = Path(path)
        self._lab_work(
            "lab_living_preview", "Comparing actual file contents against the saved kit…",
            lambda: (previous, sources, plan_living_update(Path(previous), sources)))

    def _lab_track(self):
        manifest = self._lab_manifest("Choose kit to track for changes locally")
        if not manifest:
            return
        try:
            meta, _archive = _manifest_for(Path(manifest))
            if meta.get("schema") != 2 or not isinstance(meta.get("roles"), list):
                raise ValueError("Local watches require a full v2 Resurrection Kit.")
            roles = [r.get("name") for r in meta["roles"] if isinstance(r, dict)]
            if not roles or len(set(roles)) != len(roles) or not set(roles).issubset(
                    {"Saves", "Mods", "Profiles", "Configs"}):
                raise ValueError("Unknown or duplicated backup categories.")
        except (ValueError, OSError) as exc:
            messagebox.showwarning("Cannot track this kit", str(exc))
            return
        folders = {}
        for role in roles:
            location = filedialog.askdirectory(
                title=f"Choose the LOCAL {role} folder to track for this kit")
            if not location:
                return
            folders[role] = Path(location)
        if not messagebox.askyesno("Opt in to local change tracking?",
                "Game Grave will remember the following folders IN A LOCAL FILE "
                "on this PC:\n\n" +
                "\n".join(f"• {key}: {path}" for key, path in folders.items()) +
                "\n\nOnly when you press 'Check tracked kits', Game Grave will "
                "look for file size/timestamp changes. No file contents are read "
                "during these quick checks. Nothing uploads or backs up automatically. "
                "You can stop tracking whenever you choose. Proceed?"):
            return
        self._lab_work("lab_watch_saved", "Recording opted-in local kit watch…",
                       lambda: register_kit_watch(Path(manifest), folders, approved=True))

    def _lab_check_watches(self):
        if not list_kit_watches():
            messagebox.showinfo("No tracked kits", "Choose 'Track a kit (opt in)' first.")
            return
        self._lab_work("lab_watch_check", "Checking opted-in kit folder metadata…",
                       check_kit_watches)

    def _lab_stop_watching(self):
        watched = list_kit_watches()
        if not watched:
            messagebox.showinfo("No tracked kits", "There are no local kit watches.")
            return
        names = "\n".join(f"{i+1}. {r.get('game', 'Unknown')} · "
                          f"{Path(r['manifest']).name}" for i, r in enumerate(watched))
        index = simpledialog.askinteger(
            "Stop tracking", "Choose watch to remove:\n\n" + names,
            parent=self, minvalue=1, maxvalue=len(watched))
        if index is None:
            return
        target = watched[index-1]
        if not messagebox.askyesno("Forget these local paths?",
                f"Stop watching {target.get('game', 'Unknown')}?\n\n"
                "This removes the locally stored watch entry and paths. "
                "It does not remove any source folders or Resurrection Kits."):
            return
        self._lab_work("lab_watch_removed", "Stopping local kit monitoring…",
                       lambda: stop_kit_watch(target["id"], approved=True))

    def _lab_time_machine(self):
        older = self._lab_manifest("Choose older kit snapshot")
        if not older:
            return
        newer = self._lab_manifest("Choose newer snapshot of the SAME game")
        if not newer:
            return
        self._lab_work("lab_time_machine", "Checking and comparing full kit snapshots…",
                       lambda: compare_kits(Path(older), Path(newer)))

    def _lab_list_versions(self):
        parent = filedialog.askdirectory(
            title="Choose the folder that contains your Resurrection Kits")
        if not parent:
            return
        self._lab_work("lab_versions", "Reading local kit snapshot manifests…",
                       lambda: list_snapshots(Path(parent)))

    def _lab_transfer(self):
        manifest = self._lab_manifest("Choose kit to copy to another PC")
        if not manifest:
            return
        destination = filedialog.askdirectory(
            title="Choose a USB / transfer drive folder with enough free space")
        if not destination:
            return
        if not messagebox.askyesno("Prepare PC-to-PC transfer?",
                f"Copy the kit and manifest into a NEW folder within:\n{destination}\n\n"
                "No game binaries or game licenses are included. "
                "The entire copy is verified. The destination PC still needs the "
                "game installed through its launcher.\n\nContinue?"):
            return
        self._lab_work("lab_transfer", "Preparing and verifying portable kit copy…",
                       lambda: prepare_pc_transfer(
                           Path(manifest), Path(destination), approved=True))

    def _save_vault_page(self):
        self.header("Save Vault", "Find game saves automatically. Choose what stays protected.")
        intro = self.panel(pad=13)
        intro.pack(fill="x", pady=(0, 12))
        self.text(intro, "Your saves come first", 15, ACCENT, True).pack(anchor="w")
        self.text(intro, "Game Grave checks common save locations without changing anything. "
                  "Keep important saves protected, or mark a folder for manual review. "
                  "Review does NOT permit automatic deletion.", 10, MUTED, wraplength=820).pack(anchor="w", pady=(6, 0))
        action = tk.Frame(self.content, bg=BG)
        action.pack(fill="x", pady=(0, 10))
        self.button(action, "Find my saves", self._refresh_saves, primary=True).pack(side="left")
        self.button(action, "Keep selected protected", self._protect_selected_saves).pack(side="left", padx=8)
        self.button(action, "Mark for manual review", self._review_selected_saves).pack(side="left")
        self.save_summary_var = tk.StringVar(value="0 save folders found")
        self.text(self.content, "", 10, MUTED, textvariable=self.save_summary_var).pack(anchor="w", pady=(0, 7))
        area = self.panel(pad=8)
        area.pack(fill="both", expand=True)
        self.saves_tree = self._tree(area, ("game", "kind", "status", "location"),
                                     ("GAME / PROFILE", "TYPE", "PROTECTION", "FOLDER"),
                                     (190, 160, 165, 380))
        self._populate_saves()
        bottom = tk.Frame(self.content, bg=BG)
        bottom.pack(fill="x", pady=(12, 0))
        self.button(bottom, "Back up selected to ZIP", self._backup_selected_save).pack(side="left")
        self.button(bottom, "Back up another folder", self._choose_save_backup).pack(side="left", padx=10)
        self.button(bottom, "Preserve setup (Kit)", self._make_resurrection_kit).pack(side="left", padx=10)
        self.button(bottom, "Preview / Restore Kit", self._preview_resurrection_kit).pack(side="left", padx=10)
        helper = tk.Frame(self.content, bg=BG)
        helper.pack(fill="x", pady=(5, 0))
        self.button(helper, "Find my setup automatically", self._start_auto_kit).pack(side="left")
        self.button(helper, "Reconnect verified MO2 kit", self._begin_mo2_reconnect).pack(side="left", padx=10)
        self.button(helper, "Resurrection Lab", lambda: self.show_page("Resurrection Lab")).pack(side="left", padx=10)
        self.text(self.content, "Nothing is deleted from Save Vault. Save profiles and known save folders remain "
                  "excluded from bulk cleanup, even when marked for manual review. "
                  "Close the game before making a backup.", 9, WARN, wraplength=830).pack(anchor="w", pady=(10, 0))
        if not self.save_findings and not getattr(self, "_saves_loading", False):
            self.after(10, self._refresh_saves)

    def _refresh_saves(self):
        if getattr(self, "_saves_loading", False):
            return
        self._saves_loading = True
        self.status_text.set("Looking for saves in common game folders…")
        def worker():
            try:
                found = discover_saves()
                self.events.put(("saves_complete", found))
            except Exception as exc:
                self.events.put(("saves_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _populate_saves(self):
        if not hasattr(self, "saves_tree") or not self.saves_tree.winfo_exists():
            return
        selected_paths = {self.saves_lookup[k].path for k in self.saves_tree.selection()
                          if k in getattr(self, 'saves_lookup', {})}
        self.saves_tree.delete(*self.saves_tree.get_children())
        self.saves_lookup = {}
        if hasattr(self, "save_summary_var"):
            count = len(self.save_findings)
            self.save_summary_var.set(f"{count} save/profile folder{'s' if count != 1 else ''} found. "
                                      "Found folders are protected by default." if count else
                                      "No known saves found yet. You can still back up any folder manually.")
        review = set(self.settings.get("save_review_paths", []))
        for i, entry in enumerate(self.save_findings):
            self.saves_lookup[str(i)] = entry
            status = "Manual review only" if entry.path in review else "Protected"
            self.saves_tree.insert("", "end", iid=str(i), values=(entry.game, entry.kind, status, entry.path))
            if entry.path in selected_paths:
                self.saves_tree.selection_add(str(i))

    def _selected_saves(self):
        if not hasattr(self, "saves_tree") or not self.saves_tree.winfo_exists():
            return []
        return [self.saves_lookup[k] for k in self.saves_tree.selection() if k in self.saves_lookup]

    def _protect_selected_saves(self):
        chosen = self._selected_saves()
        if not chosen:
            messagebox.showinfo("Choose saves", "Select one or more game save folders first.")
            return
        review = set(self.settings.get("save_review_paths", []))
        for entry in chosen:
            review.discard(entry.path)
            if entry.path not in self.settings["never_touch"]:
                self.settings["never_touch"].append(entry.path)
        self.settings["save_review_paths"] = sorted(review)
        save_settings(self.settings)
        self._populate_saves()

    def _review_selected_saves(self):
        chosen = self._selected_saves()
        if not chosen:
            messagebox.showinfo("Choose saves", "Select one or more game save folders first.")
            return
        if not messagebox.askyesno("Mark for manual review?", "These folders will be marked for manual review, "
                "not deletion. They remain excluded from bulk cleanup and automatic deletion. Continue?"):
            return
        review = set(self.settings.get("save_review_paths", []))
        for entry in chosen:
            review.add(entry.path)
            if entry.path in self.settings.get("never_touch", []):
                self.settings["never_touch"].remove(entry.path)
        self.settings["save_review_paths"] = sorted(review)[:500]
        save_settings(self.settings)
        self._populate_saves()

    def _backup_selected_save(self):
        chosen = self._selected_saves()
        if len(chosen) != 1:
            messagebox.showinfo("Choose one folder", "Select one save folder to back up at a time.")
            return
        self._choose_save_backup(chosen[0].path)

    def _choose_save_backup(self, preselected=None):
        source = preselected or filedialog.askdirectory(title="Choose a specific saved game, world or mod profile folder")
        if not source:
            return
        destination = filedialog.asksaveasfilename(title="Save backup as ZIP", defaultextension=".zip",
                                                    filetypes=[("ZIP archive", "*.zip")],
                                                    initialfile=Path(source).name + "_Game Grave_backup.zip")
        if not destination:
            return
        if not messagebox.askyesno("Create backup?", "Back up the following folder?\n\n" + source +
                                   "\n\nDestination: " + destination +
                                   "\n\nClose the game first. Game Grave will not modify your source files."):
            return
        self.status_text.set("Backing up and verifying your save files…")
        def worker():
            try:
                result = create_backup(Path(source), Path(destination))
                self.events.put(("backup_result", result))
            except (OSError, ValueError, RuntimeError, InterruptedError, zipfile.BadZipFile) as exc:
                self.events.put(("backup_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _start_auto_kit(self):
        """Small setup picker; no scan or source writes happen before user approval."""
        games = list(self.games) + list(self.other_games)
        if not games:
            messagebox.showinfo("Scan PC first",
                "Run Scan PC to identify installed games and associated mod folders.")
            return
        if getattr(self, "_kit_dialog", None) is not None:
            try:
                if self._kit_dialog.winfo_exists():
                    self._kit_dialog.destroy()
            except tk.TclError:
                pass
        window = tk.Toplevel(self)
        self._kit_dialog = window
        window.title("Resurrection Kit · Discover my setup")
        window.geometry("900x640")
        window.minsize(650, 460)
        window.configure(bg=BG)
        window.transient(self)
        frame = tk.Frame(window, bg=BG, padx=18, pady=15)
        frame.pack(fill="both", expand=True)
        self.text(frame, "Build a Resurrection Kit", 18, bold=True).pack(anchor="w")
        self.text(frame, "Choose one installed game. Game Grave will suggest files with evidence, "
                  "then you approve exactly what goes into the kit.",
                  10, MUTED, wraplength=810).pack(anchor="w", pady=(4, 10))
        labels = [f"{g.name}  [{getattr(g, 'launcher', 'Steam')}]  {g.install_path}"
                  for g in games]
        selected = tk.StringVar(value=labels[0])
        combo = ttk.Combobox(frame, textvariable=selected, values=labels,
                             state="readonly", width=100, style="Dark.TCombobox")
        combo.pack(fill="x", pady=(0, 10))
        self._kit_result_frame = tk.Frame(frame, bg=BG)
        self._kit_result_frame.pack(fill="both", expand=True)
        def on_discover():
            index = combo.current()
            if index < 0:
                return
            game = games[index]
            self._kit_target_game = game
            self.status_text.set("Discovering saves and mod-manager folders for " + game.name)
            def worker():
                try:
                    report = inspect_manager_profiles(
                        list(self.mod_folders), list(self.games), list(self.other_games))
                    data = discover_setup(game, mods=list(self.mod_folders),
                                          saves=list(self.save_findings),
                                          manager_report=report)
                    self.events.put(("kit_discovery_result", (game.name, data)))
                except (OSError, ValueError, RuntimeError) as exc:
                    self.events.put(("kit_error", str(exc)))
            threading.Thread(target=worker, daemon=True).start()
        self.button(frame, "Find recommended folders", on_discover, primary=True).pack(
            anchor="w", pady=(8, 0))

    def _show_kit_discovery(self, game_name, data):
        window = getattr(self, "_kit_dialog", None)
        if window is None or not window.winfo_exists():
            return
        body = self._kit_result_frame
        for child in body.winfo_children():
            child.destroy()
        rows = data["candidates"]
        self.text(body, f"{len(rows)} possible setup folders found for {game_name}. "
                  "Nothing is selected without review.", 11, bold=True).pack(
            anchor="w", pady=(0, 4))
        self._kit_role_vars = {}
        if not rows:
            self.text(body, "No verified setup folders found. Try adding custom mod roots "
                      "in Game Mods, or use Preserve setup (Kit) to pick folders manually.",
                      10, WARN, wraplength=790).pack(anchor="w")
            return
        canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        bar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="top", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG)
        key = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _evt: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda evt: canvas.itemconfigure(key, width=evt.width))
        for role, group in data["groups"].items():
            if not group:
                continue
            self.text(inner, role + " · choose at most one", 12, bold=True).pack(
                anchor="w", pady=(9, 3))
            var = tk.StringVar(value="")
            self._kit_role_vars[role] = var
            tk.Radiobutton(inner, text="Do not include this type", variable=var,
                           value="", bg=BG, fg=MUTED, selectcolor=PANEL,
                           activebackground=BG, activeforeground=TEXT).pack(anchor="w")
            for j, candidate in enumerate(group):
                if j == 0 and candidate["default"]:
                    var.set(candidate["path"])
                label = f"{candidate['path']}\n   {candidate['evidence']}"
                tk.Radiobutton(inner, text=label, variable=var,
                               value=candidate["path"], anchor="w", justify="left",
                               wraplength=760, bg=BG, fg=TEXT, selectcolor=PANEL,
                               activebackground=BG, activeforeground=TEXT).pack(
                    anchor="w", pady=2)
        def preserve():
            selected = [c for c in rows if self._kit_role_vars.get(c["role"])
                        and self._kit_role_vars[c["role"]].get() == c["path"]]
            try:
                sources, hints = select_sources(data, selected)
            except (ValueError, OSError) as exc:
                messagebox.showwarning("Review sources", str(exc), parent=window)
                return
            destination = filedialog.asksaveasfilename(
                parent=window, title="Save verified Resurrection Kit ZIP",
                defaultextension=".zip", filetypes=[("ZIP archive", "*.zip")],
                initialfile=game_name.replace("/", "_").replace("\\", "_") + "_Resurrection.zip")
            if not destination:
                return
            path_lines = "\n".join(f"• {role}: {path}" for role, path in sources.items())
            if not messagebox.askyesno("Approve these kit sources?",
                    f"Game: {game_name}\n\n{path_lines}\n\n"
                    f"Kit: {destination}\n\nClose the game and mod manager first. "
                    "Game Grave preserves only the listed locations. "
                    "Missing dependencies are not silently included. Continue?",
                    parent=window):
                return
            window.destroy()
            self.status_text.set("Preserving selected setup folders…")
            def worker():
                try:
                    result = create_complete_kit(game_name, sources, Path(destination),
                                                 manager_context=hints)
                    self.events.put(("kit_result", result))
                except (OSError, ValueError, RuntimeError, InterruptedError,
                        zipfile.BadZipFile) as exc:
                    self.events.put(("kit_error", str(exc)))
            threading.Thread(target=worker, daemon=True).start()
        self.button(body, "Create verified kit from selected folders", preserve,
                    primary=True).pack(anchor="w", pady=(6, 0))

    def _begin_mo2_reconnect(self):
        """No guessed instance location, no manager-state edits, no overwrite."""
        known = {}
        for mod in self.mod_folders:
            if getattr(mod, "source", "") != "Mod Organizer 2":
                continue
            for indicator in getattr(mod, "indicators", ()):
                if isinstance(indicator, str) and indicator.startswith("MO2 INI: "):
                    known[indicator[9:]] = True
        if not known:
            messagebox.showinfo("MO2 not found",
                "Scan PC first and add your MO2 instance in Game Mods if needed. "
                "Direct MO2 restoration is unavailable without a recognized instance. "
                "Preview / Restore Kit still recovers into a safe separate folder.")
            return
        manifest = filedialog.askopenfilename(
            title="Select MO2 Resurrection Kit manifest",
            filetypes=[("Game Grave kit", "*.ggkit.json"), ("JSON file", "*.json")])
        if not manifest:
            return
        roots = sorted(known)
        if len(roots) == 1:
            ini = roots[0]
        else:
            options = "\n".join(f"{i+1}. {path}" for i, path in enumerate(roots[:20]))
            selected = simpledialog.askinteger("Choose MO2 instance",
                "Choose the MO2 instance number:\n\n" + options, parent=self,
                minvalue=1, maxvalue=min(20, len(roots)))
            if selected is None:
                return
            ini = roots[selected-1]
        games, other_games = list(self.games), list(self.other_games)
        self.status_text.set("Checking MO2 profile, file conflicts, disk space and kit integrity…")
        def worker():
            try:
                plan = preview_mo2_reconnect(
                    Path(manifest), Path(ini), games, other_games)
                self.events.put(("mo2_reconnect_preview", (manifest, ini, plan)))
            except (OSError, ValueError, RuntimeError, FileExistsError, zipfile.BadZipFile) as exc:
                self.events.put(("mo2_reconnect_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_mo2_reconnect(self, manifest, ini, plan):
        games, other_games = list(self.games), list(self.other_games)
        self.status_text.set("Reconnecting verified mod and profile folders into MO2…")
        def worker():
            try:
                result = reconnect_to_mo2(Path(manifest), Path(ini), games, other_games,
                    approved=True, expected_fingerprint=plan["fingerprint"])
                self.events.put(("mo2_reconnect_result", result))
            except (OSError, ValueError, RuntimeError, FileExistsError) as exc:
                self.events.put(("mo2_reconnect_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _make_resurrection_kit(self):
        chosen = self._selected_saves()
        if len(chosen) > 1:
            messagebox.showinfo("Choose one game", "Select just one save/profile folder at a time.")
            return
        if chosen:
            source, game = Path(chosen[0].path), chosen[0].game
        else:
            selected = filedialog.askdirectory(
                title="Choose the save or profile folder you want to preserve")
            if not selected:
                return
            source = Path(selected)
            game = simpledialog.askstring("Game name", "What game is this setup for?",
                                          initialvalue=source.name, parent=self)
            if not game:
                return
        sources = {"Saves": source}
        include_mods = messagebox.askyesno("Include your mod setup?",
            "Resurrection Kit will preserve your selected save folder.\n\n"
            "Do you also want to add a mod/mod-manager profile folder? "
            "You'll choose its exact location. Nothing is guessed or removed.")
        if include_mods:
            folder = filedialog.askdirectory(
                title="Choose the mod or mod-manager profile folder to preserve")
            if not folder:
                return  # User chose to include mod data, so don't silently omit it.
            sources["Mods"] = Path(folder)
        destination = filedialog.asksaveasfilename(
            title="Save your Resurrection Kit ZIP", defaultextension=".zip",
            filetypes=[("ZIP archive", "*.zip")],
            initialfile=source.name + "_Resurrection.zip")
        if not destination:
            return
        folders = "\n".join(f"• {role}: {path}" for role, path in sources.items())
        if not messagebox.askyesno("Preserve this setup?",
                f"Game: {game}\n\nFolders to preserve:\n{folders}\n\n"
                f"Kit ZIP: {destination}\n\n"
                "Game Grave saves only these selected folders. Close the game and "
                "mod manager first. This does not archive the game installation or "
                "promise automatic mod activation. Continue?"):
            return
        self.status_text.set("Creating and verifying Resurrection Kit…")
        def worker():
            try:
                created = create_complete_kit(game, sources, Path(destination))
                self.events.put(("kit_result", created))
            except (OSError, ValueError, RuntimeError, InterruptedError, zipfile.BadZipFile) as exc:
                self.events.put(("kit_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _preview_resurrection_kit(self, preselected_manifest=None):
        manifest = preselected_manifest or filedialog.askopenfilename(
            title="Choose your Resurrection Kit manifest (.ggkit.json)",
            filetypes=[("Game Grave kit", "*.ggkit.json"), ("JSON file", "*.json")])
        if not manifest:
            return
        parent = filedialog.askdirectory(
            title="Choose where to create a NEW restored folder (no files overwritten)")
        if not parent:
            return
        self.status_text.set("Checking Resurrection Kit checksum and ZIP files…")
        def worker():
            try:
                checked = inspect_restore(Path(manifest), Path(parent))
                self.events.put(("kit_preview", (manifest, parent, checked)))
            except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, FileExistsError) as exc:
                self.events.put(("kit_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _restore_verified_kit(self, manifest, parent):
        self.status_text.set("Recovering kit into a new folder; existing game files are untouched…")
        def worker():
            try:
                restored = restore_kit(Path(manifest), Path(parent), approved=True)
                self.events.put(("kit_restore_result", restored))
            except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, FileExistsError) as exc:
                self.events.put(("kit_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _history_page(self):
        self.header("Storage History", "Compare on-demand scans. No 24/7 game update monitoring.")
        history = load_history()
        summary = self.panel()
        summary.pack(fill="x", pady=(0, 12))
        self.text(summary, f"{len(history)} snapshots saved on this PC", 16, bold=True).pack(anchor="w")
        if history:
            self.text(summary, "Most recent: " + history[-1].get("time", ""), 10, MUTED).pack(anchor="w", pady=5)
        self.text(summary, "Recorded changes since the preceding scan", 13, bold=True).pack(anchor="w", pady=(14, 9))
        for item in compare_scans(history)[:12]:
            self.text(summary, "• " + item, 10, MUTED, wraplength=810).pack(anchor="w", pady=3)
        self.text(summary, "Different scan roots, missing drives, hard links, and shared files can affect comparisons. "
                  "Game Grave does not infer what caused unobserved changes.", 9, WARN, wraplength=810).pack(anchor="w", pady=(14, 0))
        if history:
            sources = self.panel()
            sources.pack(fill="x")
            self.text(sources, "Most recent detected ecosystems", 13, bold=True).pack(anchor="w", pady=(0, 10))
            for name, data in sorted(history[-1].get("mod_sources", {}).items(),
                                     key=lambda item: -item[1].get("count", 0))[:14]:
                self.text(sources, f"{name}: {data['count']} findings, {human_size(data['apparent_bytes'])} apparent",
                          10, MUTED).pack(anchor="w", pady=3)
        self.button(self.content, "Scan again", self.scan_all, primary=True).pack(anchor="w", pady=12)

    def _settings_page(self):
        self.header("Settings", "Make Game Grave look and work the way you want. File safety never changes with themes.")
        tabs = ttk.Notebook(self.content, style="Dust.TNotebook")
        tabs.pack(fill="both", expand=True)
        appearance_tab, presets_tab, protected_tab, tools_tab, edition_tab = (tk.Frame(tabs, bg=BG) for _ in range(5))
        self.settings_tabs = tabs
        tabs.add(appearance_tab, text="Appearance")
        tabs.add(presets_tab, text="Shareable Presets")
        tabs.add(protected_tab, text="Never Touch")
        tabs.add(tools_tab, text="More tools")
        tabs.add(edition_tab, text="Free / Pro")
        settings = self.panel(appearance_tab)
        settings.pack(fill="x", pady=(0, 12))
        self.text(settings, "Appearance and navigation", 14, bold=True).pack(anchor="w", pady=(0, 11))
        picks = [("Theme", "ui_theme", ("dark", "light", "system")),
                 ("Accent color", "ui_accent", ("teal", "blue", "purple", "orange", "custom")),
                 ("Text size", "ui_scale", ("compact", "normal", "large")),
                 ("Navigation", "ui_layout", ("simple", "advanced"))]
        for label, setting, choices in picks:
            bar = tk.Frame(settings, bg=PANEL)
            bar.pack(anchor="w", pady=5)
            self.text(bar, label + ":", 10, MUTED).pack(side="left", padx=(0, 12))
            value = tk.StringVar(value=self.settings.get(setting, choices[0]))
            select = ttk.Combobox(bar, textvariable=value, values=choices, state="readonly",
                                  style="Dark.TCombobox", width=15)
            select.pack(side="left")
            select.bind("<<ComboboxSelected>>", lambda e, key=setting, var=value: self._set_ui_setting(key, var.get()))
        custom_row = tk.Frame(settings, bg=PANEL)
        custom_row.pack(anchor="w", pady=(7, 3))
        self.text(custom_row, "Custom HEX:", 10, MUTED).pack(side="left", padx=(0, 8))
        self.accent_hex_var = tk.StringVar(value=self.settings.get("ui_custom_accent", "#50DCC5"))
        tk.Entry(custom_row, textvariable=self.accent_hex_var, bg=RAISED, fg=TEXT,
                 insertbackground=TEXT, width=11, relief="flat",
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 8), ipady=4)
        self.button(custom_row, "Apply HEX", self._apply_custom_accent).pack(side="left", padx=(0, 7))
        self.button(custom_row, "Choose any color…", self._choose_custom_accent).pack(side="left")
        tk.Label(custom_row, bg=ACCENT, width=4, height=2, relief="solid", bd=1).pack(side="left", padx=9)
        self.text(settings, "The color dialog opens your system's full color picker. "
                  "Enter any #RRGGBB shade or choose one visually.", 9, MUTED).pack(anchor="w", pady=(1, 4))
        self.text(settings, "Sort choices for Steam Games, Mods, Old Files, and Graveyard are saved automatically. "
                  "Graveyard also supports named custom views, category/size/safety filters, and search.",
                  9, MUTED, wraplength=810).pack(anchor="w", pady=(8, 4))
        self.text(settings, "Save Vault, Cleanup History and safety are always visible. Advanced adds storage trends and automation.",
                  9, MUTED, wraplength=810).pack(anchor="w", pady=(8, 6))
        self.scan_start_var = tk.BooleanVar(value=self.settings.get("scan_on_launch", False))
        ttk.Checkbutton(settings, text="Scan when I open Game Grave (off by default)", variable=self.scan_start_var,
                        command=self._save_startup_pref, style="Dark.TCheckbutton").pack(anchor="w", pady=7)
        setting_actions = tk.Frame(settings, bg=PANEL)
        setting_actions.pack(anchor="w", pady=(8, 0))
        self.button(setting_actions, "Reset appearance", self._reset_appearance).pack(side="left")
        self.button(setting_actions, "Keyboard guide (F1)", self._open_keyboard_shortcuts).pack(
            side="left", padx=(9, 0))

        preset_panel = self.panel(presets_tab)
        preset_panel.pack(fill="x", pady=(0, 12))
        self.text(preset_panel, "Save and share your setup", 14, bold=True).pack(anchor="w", pady=(0, 8))
        self.text(preset_panel, "Presets contain your theme, custom color, display scale, navigation layout, "
                  "and sorting/filter preferences. They never include file lists, search terms, "
                  "local paths, cleanup permissions, or protection settings.",
                  10, MUTED, wraplength=770).pack(anchor="w", pady=(0, 14))
        saved_presets = sanitize_local_presets(self.settings.get("ui_presets", {}))
        self.settings["ui_presets"] = saved_presets
        row = tk.Frame(preset_panel, bg=PANEL)
        row.pack(fill="x", pady=(0, 10))
        self.text(row, "Saved presets", 10, MUTED).pack(side="left", padx=(0, 10))
        self.ui_preset_var = tk.StringVar(value="Select a preset")
        self.ui_preset_selector = ttk.Combobox(row, textvariable=self.ui_preset_var,
                    values=("Select a preset", *sorted(saved_presets)), state="readonly",
                    style="Dark.TCombobox", width=30)
        self.ui_preset_selector.pack(side="left")
        row2 = tk.Frame(preset_panel, bg=PANEL)
        row2.pack(anchor="w", pady=(0, 9))
        self.button(row2, "Save current setup", self._save_ui_preset).pack(side="left", padx=(0, 8))
        self.button(row2, "Apply", self._apply_ui_preset).pack(side="left", padx=(0, 8))
        self.button(row2, "Delete preset", self._remove_ui_preset).pack(side="left")
        row3 = tk.Frame(preset_panel, bg=PANEL)
        row3.pack(anchor="w", pady=(0, 8))
        self.button(row3, "Export to share…", self._export_ui_preset).pack(side="left", padx=(0, 8))
        self.button(row3, "Import preset…", self._import_ui_preset).pack(side="left")
        self.text(preset_panel, "Share the exported .ggtheme.json file with friends. "
                  "Imports are validated, local-only, and never change deletion safety rules.",
                  9, WARN, wraplength=770).pack(anchor="w", pady=(8, 0))

        edition_panel = self.panel(edition_tab)
        edition_panel.pack(fill="x", pady=(0, 12))
        self.text(edition_panel, "Your Game Grave edition", 14, bold=True).pack(anchor="w", pady=(0, 9))
        self.license_status_var = tk.StringVar(value=f"{self.edition.name} edition")
        tk.Label(edition_panel, textvariable=self.license_status_var, bg=PANEL, fg=ACCENT,
                 font=("Segoe UI Semibold", 16)).pack(anchor="w", pady=(0, 9))
        self.text(edition_panel, "Free: scan games, review the Graveyard, protect important files, "
                  "use Undo Center, and customize your interface. No account or license key needed.",
                  10, MUTED, wraplength=760).pack(anchor="w", pady=(0, 10))
        self.text(edition_panel, "Lifetime Pro: one purchase, no subscription. "
                  "Extra features will only be enabled after verified activation. "
                  "Core file safety will always stay free.",
                  10, MUTED, wraplength=760).pack(anchor="w", pady=(0, 12))
        controls = tk.Frame(edition_panel, bg=PANEL)
        controls.pack(anchor="w")
        self.button(controls, "Activate Pro key…", self._activate_pro).pack(side="left", padx=(0, 8))
        self.button(controls, "Remove activation from this PC", self._deactivate_pro).pack(side="left")
        self.text(edition_panel, "Activation is only contacted when you enter a key and click Activate. "
                  "This preview does not have a live activation service yet. "
                  "Importing UI presets can never unlock Pro or change deletion permissions.",
                  9, WARN, wraplength=770).pack(anchor="w", pady=(13, 0))

        protected = self.panel(protected_tab)
        protected.pack(fill="x", pady=(0, 12))
        self.text(protected, "Never Touch list", 14, bold=True).pack(anchor="w")
        self.text(protected, "Game Grave refuses to recycle files in these locations.", 9, MUTED).pack(anchor="w", pady=(3, 10))
        self.protected_list = tk.Listbox(protected, bg=RAISED, fg=TEXT, selectbackground=ACCENT,
                                         selectforeground=BG, height=4, relief="flat", font=("Segoe UI", 10))
        self.protected_list.pack(fill="x")
        for path in self.settings.get("never_touch", []):
            self.protected_list.insert("end", path)
        buttons = tk.Frame(protected, bg=PANEL)
        buttons.pack(fill="x", pady=(8, 0))
        self.button(buttons, "Protect a folder", self._protect_folder).pack(side="left")
        self.button(buttons, "Remove protection", self._unprotect_folder).pack(side="left", padx=9)

        extra = self.panel(tools_tab)
        extra.pack(fill="x")
        self.text(extra, "Advanced tools", 13, bold=True).pack(anchor="w", pady=(0, 10))
        for title in ("Old Files", "Make Room", "Cleanup History", "Storage History", "Automation"):
            self.button(extra, title, lambda page=title: self.show_page(page)).pack(side="left", padx=(0, 8))
        self.button(extra, "Test Windows recovery (disposable file)",
                    self._start_disposable_undo_check).pack(anchor="w", pady=(11, 3))
        self.text(extra, "Checks Windows Recycle Bin and Undo using one new test file "
                  "in a folder you choose. Never touches your games or saves.",
                  9, MUTED, wraplength=790).pack(anchor="w", pady=(0, 8))
        self.text(extra, "Free forever or optional $24.99 lifetime Pro target. No subscriptions or account requirement.",
                  9, MUTED, wraplength=810).pack(anchor="w", pady=(12, 0))
        recording_panel = self.panel(tools_tab)
        recording_panel.pack(fill="x", pady=(12, 0))
        self.text(recording_panel, "Old game recordings", 14, bold=True).pack(anchor="w", pady=(0, 5))
        self.text(recording_panel,
                  "On Scan PC, Game Grave checks common local Videos folders for possible "
                  "Game Bar, OBS, ShadowPlay and similar clips. Video contents are never opened. "
                  "Add a folder if you record somewhere else. Clips only appear for review; "
                  "nothing is automatically deleted.",
                  10, MUTED, wraplength=770).pack(anchor="w", pady=(0, 8))
        self.recording_root_list = tk.Listbox(
            recording_panel, bg=RAISED, fg=TEXT, selectbackground=ACCENT,
            selectforeground=ON_ACCENT, relief="flat", height=3, font=("Segoe UI", 10))
        self.recording_root_list.pack(fill="x", pady=(0, 7))
        for folder in self.settings.get("recording_roots", []):
            self.recording_root_list.insert("end", folder)
        capture_actions = tk.Frame(recording_panel, bg=PANEL)
        capture_actions.pack(fill="x")
        self.button(capture_actions, "Add capture folder", self._add_recordings_folder).pack(side="left")
        self.button(capture_actions, "Remove selected folder", self._remove_recordings_folder).pack(
            side="left", padx=(8, 0))

        updates_panel = self.panel(tools_tab)
        updates_panel.pack(fill="x", pady=(12, 0))
        self.text(updates_panel, "Verified updates", 14, bold=True).pack(anchor="w", pady=(0, 8))
        self.text(updates_panel,
                  "Only your click can start an update check. Game Grave first verifies a "
                  "release signature, exact download host and installer SHA-256 metadata. "
                  "This screen never downloads or installs files automatically.",
                  10, MUTED, wraplength=750).pack(anchor="w", pady=(0, 8))
        self.button(updates_panel, "Check for signed updates", self._check_updates_clicked).pack(anchor="w")
        if not update_ready():
            self.text(updates_panel, "Engineering preview: update service not connected. No internet request is made.",
                      9, WARN, wraplength=760).pack(anchor="w", pady=(7, 0))

    def _add_recordings_folder(self):
        folder = filedialog.askdirectory(title="Choose a game recording folder")
        if not folder:
            return
        path = Path(folder)
        if not safe_scan_root(path):
            messagebox.showwarning("Folder not allowed",
                "Choose a local capture folder, not a drive root, system folder or game installation.")
            return
        roots = list(self.settings.get("recording_roots", []))
        if os.path.normcase(os.path.abspath(folder)) in {
                os.path.normcase(os.path.abspath(existing)) for existing in roots}:
            messagebox.showinfo("Already included", "That recording folder is already selected.")
            return
        roots.append(str(path))
        self.settings["recording_roots"] = roots
        save_settings(self.settings)
        self.recording_root_list.insert("end", str(path))
        self.status_text.set("Recording folder added. Choose Scan PC to look for older clips.")

    def _remove_recordings_folder(self):
        selected = self.recording_root_list.curselection()
        if not selected:
            messagebox.showinfo("Choose a folder", "Select a custom recordings folder to remove.")
            return
        index = selected[0]
        roots = list(self.settings.get("recording_roots", []))
        if index >= len(roots):
            return
        roots.pop(index)
        self.settings["recording_roots"] = roots
        save_settings(self.settings)
        self.recording_root_list.delete(index)
        self.status_text.set("Custom recording folder removed. Existing files were not touched.")

    def _start_disposable_undo_check(self):
        if self.scanning or self.cleanup_running or getattr(self, "_selfcheck_busy", False):
            messagebox.showinfo("Game Grave is busy",
                "Finish the current scan, cleanup or safety check before starting another.")
            return
        folder = filedialog.askdirectory(
            title="Select an ordinary local folder for a disposable Windows Undo test",
            initialdir=self.settings.get("scan_folder", str(downloads_dir())))
        if not folder:
            return
        path = Path(folder)
        if not safe_scan_root(path) or is_protected_path(
                path, self.settings.get("never_touch", [])):
            messagebox.showwarning("Test folder protected",
                "Choose an ordinary local folder outside game installs, saves, "
                "system folders and your Never Touch rules.")
            return
        if not messagebox.askyesno("Test Windows Recycle Bin and Undo?",
                "Game Grave will create ONE tiny disposable test file in your chosen "
                "folder, move it to the Windows Recycle Bin and try to restore "
                "the exact bytes. It removes only its own verified test data at the end. "
                "No games, saves, mods or recordings are touched. "
                "A failed restore may leave the test file in the Recycle Bin. "
                "Start this on-demand test?"):
            return
        self._selfcheck_busy = True
        self.status_text.set("Windows recovery safety check running on disposable data…")
        rules = tuple(self.settings.get("never_touch", []))

        def work():
            try:
                report = check_disposable_undo(path, rules)
                self.events.put(("undo_selfcheck_pass", report))
            except SafetySelfCheckError as exc:
                self.events.put(("undo_selfcheck_fail", str(exc)))
            except Exception:
                self.events.put(("undo_selfcheck_fail",
                    "An unexpected local safety check failure occurred. No user files were selected."))

        try:
            threading.Thread(target=work, daemon=True).start()
        except RuntimeError as exc:
            self._selfcheck_busy = False
            messagebox.showerror("Safety check not started", str(exc))

    def _choose_custom_accent(self):
        current = self.settings.get("ui_custom_accent", "#50DCC5")
        picked = colorchooser.askcolor(color=current, title="Game Grave custom accent color", parent=self)
        if picked and picked[1]:
            self.accent_hex_var.set(picked[1].upper())
            self._apply_custom_accent()

    def _apply_custom_accent(self):
        try:
            color = normalize_color(self.accent_hex_var.get())
        except ValueError as exc:
            messagebox.showwarning("Invalid color", str(exc), parent=self)
            return
        self.settings["ui_custom_accent"] = color
        self._set_ui_setting("ui_accent", "custom")

    def _selected_ui_preset_name(self):
        name = self.ui_preset_var.get()
        if name not in sanitize_local_presets(self.settings.get("ui_presets", {})):
            messagebox.showinfo("Choose a preset", "First select a saved preset.", parent=self)
            return None
        return name

    def _save_ui_preset(self):
        name = simpledialog.askstring("Save UI preset", "Name your UI preset (up to 40 characters):", parent=self)
        if name is None:
            return
        try:
            name = validate_name(name)
            data = capture_presentation(self.settings)
        except ValueError as exc:
            messagebox.showwarning("Invalid preset", str(exc), parent=self)
            return
        presets = sanitize_local_presets(self.settings.get("ui_presets", {}))
        if name not in presets and len(presets) >= MAX_PRESETS:
            messagebox.showwarning("Preset limit", "You can save up to 30 UI presets.", parent=self)
            return
        if name in presets and not messagebox.askyesno("Replace preset?", f"Replace '{name}'?", parent=self):
            return
        presets[name] = data
        self.settings["ui_presets"] = presets
        save_settings(self.settings)
        self.ui_preset_selector.configure(values=("Select a preset", *sorted(presets)))
        self.ui_preset_var.set(name)

    def _apply_ui_preset(self):
        name = self._selected_ui_preset_name()
        if not name:
            return
        presets = sanitize_local_presets(self.settings.get("ui_presets", {}))
        # Presentation only. Scanner, file protections, automation and removal flags untouched.
        self.settings.update(presets[name])
        save_settings(self.settings)
        self._refresh_presentation("Shareable Presets")
        self.ui_preset_var.set(name)

    def _remove_ui_preset(self):
        name = self._selected_ui_preset_name()
        if name and messagebox.askyesno("Delete saved preset?", f"Delete '{name}' from this PC?", parent=self):
            presets = sanitize_local_presets(self.settings.get("ui_presets", {}))
            presets.pop(name, None)
            self.settings["ui_presets"] = presets
            save_settings(self.settings)
            self.ui_preset_selector.configure(values=("Select a preset", *sorted(presets)))
            self.ui_preset_var.set("Select a preset")

    def _export_ui_preset(self):
        name = self._selected_ui_preset_name()
        if not name:
            return
        target = filedialog.asksaveasfilename(title="Export Game Grave UI preset",
                        defaultextension=".json", initialfile="gamegrave-theme.json",
                        filetypes=[("Game Grave JSON presets", "*.json")], parent=self)
        if not target:
            return
        try:
            write_preset_file(target, name, self.settings["ui_presets"][name])
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not export preset", str(exc), parent=self)
            return
        messagebox.showinfo("Preset exported", "Only UI settings were exported. "
                            "No local files, scan data or cleanup settings were included.", parent=self)

    def _import_ui_preset(self):
        source = filedialog.askopenfilename(title="Import Game Grave UI preset",
                    filetypes=[("Game Grave JSON presets", "*.json")], parent=self)
        if not source:
            return
        try:
            name, data = read_preset_file(source)
        except (OSError, UnicodeError, ValueError) as exc:
            messagebox.showerror("Unsafe or invalid preset", str(exc), parent=self)
            return
        if not messagebox.askyesno("Review imported UI preset",
                f"Import '{name}'?\n\nTheme: {data['ui_theme']}\nColor: "
                f"{data['ui_custom_accent'] if data['ui_accent']=='custom' else data['ui_accent']}\n"
                f"Layout: {data['ui_layout']}\nText size: {data['ui_scale']}\n\n"
                "Only appearance, sorting, and display filters can change. "
                "No file operations or protection settings are imported.", parent=self):
            return
        presets = sanitize_local_presets(self.settings.get("ui_presets", {}))
        if name not in presets and len(presets) >= MAX_PRESETS:
            messagebox.showwarning("Preset limit", "You can save up to 30 UI presets.", parent=self)
            return
        if name in presets and not messagebox.askyesno("Replace preset?", f"Replace '{name}'?", parent=self):
            return
        presets[name] = data
        self.settings["ui_presets"] = presets
        save_settings(self.settings)
        self.ui_preset_selector.configure(values=("Select a preset", *sorted(presets)))
        self.ui_preset_var.set(name)
        if messagebox.askyesno("Apply preset?", "Apply this preset now?", parent=self):
            self._apply_ui_preset()

    def _check_updates_clicked(self):
        """Never make a network request unless the user explicitly clicks."""
        if not update_ready():
            messagebox.showinfo(
                "Update service not connected",
                "Signed update discovery is not enabled in this engineering preview. "
                "No internet request was made. The app remains usable offline.\n\n"
                "A production signing key and reviewed release service are required.",
                parent=self)
            return
        if getattr(self, "_update_check_active", False):
            return
        self._update_check_active = True
        self.status_text.set("Checking signed release metadata at your request…")
        def worker():
            try:
                report = check_for_updates()
                self.events.put(("update_check_result", report))
            except UpdateError as exc:
                self.events.put(("update_check_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _activate_pro(self):
        if not activation_ready():
            messagebox.showinfo("Pro is coming later", "Free is ready to use without a key.\n\n"
                "Lifetime Pro activation is not connected to a license service in this preview. "
                "No payment or key is required right now.", parent=self)
            return
        key = simpledialog.askstring("Activate lifetime Pro", "Enter your Game Grave Pro key.\n"
               "It will be sent securely to the activation service only when you confirm.",
               show="*", parent=self)
        if not key:
            return
        self.status_text.set("Checking your Pro license…")
        def worker():
            try:
                result = activate_key(key)
                self.events.put(("license_activated", result))
            except LicenseError as exc:
                self.events.put(("license_error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _deactivate_pro(self):
        if not self.edition.is_pro:
            messagebox.showinfo("Free edition", "This PC is already using Free.", parent=self)
            return
        if not messagebox.askyesno("Remove Pro from this PC?",
                 "This removes only this PC's local activation receipt. "
                 "It does not cancel your lifetime purchase or delete your files. Continue?", parent=self):
            return
        try:
            remove_local_activation()
        except LicenseError as exc:
            messagebox.showwarning("Couldn't remove activation", str(exc), parent=self)
            return
        self.edition = read_edition()
        self._layout_after_edition_change()

    def _layout_after_edition_change(self):
        self.status_text.set(f"{self.edition.name} edition ready. No scan was started.")
        self.sidebar.destroy()
        self.main.destroy()
        self._layout()
        self.show_page("Settings")
        self.settings_tabs.select(4)

    def _refresh_presentation(self, settings_tab="Appearance"):
        apply_palette(self.settings)
        self.tk.call("tk", "scaling", {"compact": 1.0, "normal": 1.16, "large": 1.42}.get(self.settings.get("ui_scale"), 1.16))
        self.configure(bg=BG)
        self.sidebar.destroy()
        self.main.destroy()
        self._ui_style()
        self._layout()
        self.show_page("Settings")
        if settings_tab == "Shareable Presets":
            self.settings_tabs.select(1)

    def _set_view_sort(self, key, var, refresh):
        """Save a per-page presentation choice without affecting scanner or safety rules."""
        self.settings[key] = var.get()
        save_settings(self.settings)
        refresh()

    def _set_ui_setting(self, key, value):
        self.settings[key] = value
        save_settings(self.settings)
        self._refresh_presentation()

    def _save_startup_pref(self):
        self.settings["scan_on_launch"] = bool(self.scan_start_var.get())
        save_settings(self.settings)

    def _reset_appearance(self):
        for key in ("ui_theme", "ui_accent", "ui_custom_accent", "ui_scale", "ui_layout"):
            self.settings[key] = default_settings()[key]
        self._set_ui_setting("ui_layout", "simple")

    def _protect_folder(self):
        if getattr(self, "cleanup_running", False):
            messagebox.showinfo("Cleanup in progress", "Finish deletion before updating Never Touch.")
            return
        folder = filedialog.askdirectory(title="Never Touch: protect a folder")
        if folder and folder not in self.settings["never_touch"]:
            self.settings["never_touch"].append(folder)
            save_settings(self.settings)
            self.show_page("Settings")

    def _unprotect_folder(self):
        if getattr(self, "cleanup_running", False):
            messagebox.showinfo("Cleanup in progress", "Finish deletion before updating Never Touch.")
            return
        selection = self.protected_list.curselection()
        if selection and messagebox.askyesno("Remove protection?", "Remove this folder from your Never Touch list?\nNo files will be deleted."):
            del self.settings["never_touch"][selection[0]]
            save_settings(self.settings)
            self.show_page("Settings")

    def _cancel_active_scan(self):
        if self.scanning:
            self._cancel_scan.set()
            self.status_text.set("Cancel requested. Waiting for the current folder check to stop…")

    def _check_scan_cancel(self):
        """Cooperative checkpoint between slower read-only inventory stages."""
        if self._cancel_scan.is_set():
            raise InterruptedError("Scan canceled. Previous inventory remains unchanged.")

    def _scan_canceled_status(self):
        """Never publish a scan result after the user explicitly canceled."""
        self.scanning = False
        self.scan_progress_text.set("Scan canceled · Previous results preserved")
        self.status_text.set("Scan canceled. No new inventory was saved, and no cleanup ran.")
        self.scan_button.configure(state="normal", bg=ACCENT)
        self.cancel_button.configure(state="disabled")
        log_event("Scan canceled", "User canceled the read-only inventory before acceptance.")

    def scan_all(self):
        if self.scanning or getattr(self, "cleanup_running", False) or getattr(self, "_selfcheck_busy", False):
            return
        self.scanning = True
        self.scan_button.configure(state="disabled", bg=RAISED)
        self.cancel_button.configure(state="normal")
        self._scan_started = time.monotonic()
        self._scan_stage = 0
        self._scan_stage_name = STAGES[0][0]
        self.scan_percent.set(0)
        self.scan_progress_text.set("Starting scan · Calculating ETA…")
        self.status_text.set("Scanning your gaming PC…")
        self._cancel_scan.clear()
        chosen_folder = Path(self.settings["scan_folder"])
        games_extra = list(self.settings["steam_extra_roots"])
        file_days = self.settings["files_stale_days"]
        mod_roots = list(self.settings.get("mod_extra_roots", []))
        other_roots = list(self.settings.get("other_library_roots", []))
        recording_roots = list(self.settings.get("recording_roots", []))
        recording_days = min(file_days, self.settings.get("graveyard_days", 365))

        def task():
            try:
                self.events.put(("scan_stage", (0, STAGES[0][0])))
                games = find_games(games_extra)
                self._check_scan_cancel()
                self.events.put(("scan_stage", (1, STAGES[1][0])))
                other = find_launcher_games(other_roots, cancel=self._cancel_scan.is_set)
                self._check_scan_cancel()
                self.events.put(("scan_stage", (2, STAGES[2][0])))
                mods = find_all_mod_storage(games_extra, mod_roots,
                                            games=games, cancel=self._cancel_scan.is_set)
                self._check_scan_cancel()
                self.events.put(("scan_stage", (3, STAGES[3][0])))
                try:
                    files = scan_old_files(chosen_folder, file_days, cancel=self._cancel_scan.is_set)
                    warning = ""
                except (ValueError, OSError) as exc:
                    files = []
                    warning = str(exc)
                self._check_scan_cancel()
                try:
                    recordings = find_old_recordings(recording_days, recording_roots,
                                                     cancel=self._cancel_scan.is_set)
                except (ValueError, OSError) as exc:
                    recordings = []
                    warning += ("; " if warning else "") + "Recordings: " + str(exc)
                self._check_scan_cancel()
                self.events.put(("scan_stage", (4, STAGES[4][0])))
                saves = discover_saves()
                self._check_scan_cancel()
                self.events.put(("scan_complete", (games, other, mods, files, recordings, saves, warning)))
            except Exception as exc:
                self.events.put(("scan_error", str(exc)))
        threading.Thread(target=task, daemon=True).start()

    def _poll(self):
        try:
            while True:
                name, payload = self.events.get_nowait()
                if name == "scan_stage":
                    self._scan_stage, self._scan_stage_name = payload
                    self.scan_percent.set(round(100 * sum(w for _, w in STAGES[:self._scan_stage])))
                elif name == "scan_complete":
                    if self._cancel_scan.is_set():
                        self._scan_canceled_status()
                        continue
                    self.games, self.other_games, self.mod_folders, self.old_files, self.recordings, self.save_findings, warning = payload
                    self.profile_report = None  # Profiles must be re-inspected after inventory changes.
                    self.scan_percent.set(100)
                    self.scan_progress_text.set("Scan complete · 100%")
                    try:
                        drive_paths = [Path(self.settings["scan_folder"])] + [Path(g.install_path) for g in self.games]
                        record_scan(self.games, self.mod_folders, self.old_files,
                                    self.settings["scan_folder"], drive_paths)
                    except (OSError, ValueError) as exc:
                        log_event("History warning", str(exc))
                    log_event("Mod inventory completed", f"{len(self.games)} games; {len(self.mod_folders)} mod/storage findings; {len(self.old_files)} old files" +
                              (f"; Files warning: {warning}" if warning else ""))
                    self.scanning = False
                    self.last_scan = datetime.now().strftime("%I:%M %p").lstrip("0")
                    self.status_text.set(f"Scan finished at {self.last_scan}  •  {len(self.games) + len(self.other_games)} games, {len(self.mod_folders)} mods, {len(self.old_files)} old files, {len(self.recordings)} possible game clips" +
                                         ("  •  File folder unavailable" if warning else ""))
                    self.scan_button.configure(state="normal", bg=ACCENT)
                    self.cancel_button.configure(state="disabled")
                    self.show_page(self.active)
                elif name == "grave_cleanup_progress":
                    completed, total = payload
                    self.status_text.set(
                        f"Delete in progress: checked {completed} of {total} file(s). "
                        "Windows is verifying recovery for each item…")
                elif name == "grave_cleanup_complete":
                    self.cleanup_running = False
                    self.grave_checked.clear()
                    completed = payload["completed"]
                    skipped = payload["skipped"]
                    warnings = payload["recovery_warnings"]
                    self.status_text.set(
                        f"Delete finished: {completed} moved to Recycle Bin; "
                        f"{len(skipped)} not moved.")
                    self.scan_all()
                    message = (f"{completed} file(s) moved to Windows Recycle Bin. "
                               f"{len(skipped)} not moved.\n\n" +
                               "\n".join(skipped[:6]))
                    if warnings:
                        message += (f"\n\nWarning: {warnings} moved item(s) could not be "
                                    "registered with Undo Center. Inspect Windows "
                                    "Recycle Bin for manual restore.")
                    message += ("\n\nIf Windows recovery could not be verified, "
                                "Game Grave refused to move the affected files. "
                                "Empty the Recycle Bin separately to reclaim space.")
                    if skipped or warnings:
                        messagebox.showwarning("Delete results", message)
                    else:
                        messagebox.showinfo("Delete complete", message)
                elif name == "grave_cleanup_error":
                    self.cleanup_running = False
                    self.status_text.set("Deletion stopped unexpectedly. Review existing files and Undo Center.")
                    self.scan_button.configure(state="normal", bg=ACCENT)
                    if self.active == "The Graveyard":
                        self._grave_sync_actions()
                    messagebox.showerror("Delete interrupted",
                        payload + "\n\nNot all items may have been processed. "
                        "Check Recycle Bin and Undo Center before retrying.")
                elif name == "old_cleanup_progress":
                    done, total = payload
                    self.status_text.set(f"Deleting old files: {done} of {total} checked. "
                                         "Windows recovery is verified per file.")
                elif name == "old_cleanup_complete":
                    self.cleanup_running = False
                    completed = payload["completed"]
                    skipped = payload["skipped"]
                    warnings = payload["recovery_warnings"]
                    self.status_text.set(
                        f"Old Files: {completed} moved to Recycle Bin; {len(skipped)} not moved.")
                    self.scan_all()
                    message = (f"{completed} file(s) moved to Windows Recycle Bin; "
                               f"{len(skipped)} not moved.\n\n" + "\n".join(skipped[:6]))
                    if warnings:
                        message += (f"\n\n{warnings} item(s) moved, but Undo Center could "
                                    "not save a recovery record. Check Windows Recycle Bin.")
                    message += "\n\nEmpty Recycle Bin separately to actually reclaim disk space."
                    if skipped or warnings:
                        messagebox.showwarning("Delete results", message)
                    else:
                        messagebox.showinfo("Delete complete", message)
                elif name == "old_cleanup_error":
                    self.cleanup_running = False
                    self.status_text.set("Old Files deletion interrupted. Check Recycle Bin before retrying.")
                    self.scan_button.configure(state="normal", bg=ACCENT)
                    messagebox.showerror(
                        "Deletion interrupted", payload +
                        "\n\nSome items may already have moved. Check Windows Recycle Bin and Undo Center.")
                elif name == "duplicates_found":
                    self._dupe_busy = False
                    report = payload
                    count = len(report.groups)
                    self.status_text.set(f"Read-only duplicate check: {count} exact group(s), "
                                         f"{report.hashed_files} file(s) compared.")
                    lines = []
                    for group in report.groups[:8]:
                        sample = ", ".join(Path(path).name for path in group.paths[:3])
                        lines.append(f"• {len(group.paths)} exact copies ({human_size(group.size_bytes)} each): {sample}")
                    messagebox.showinfo("Exact duplicate archive evidence",
                        f"{count} identical archive group(s) in {report.hashed_files} files hashed.\n"
                        f"Total compared: {human_size(report.hashed_bytes)}\n"
                        f"Potential redundant apparent size: "
                        f"{human_size(report.potential_redundant_apparent_bytes)}\n"
                        "Verified reclaimable space: 0 (not measured).\n"
                        + ("\n".join(lines) if lines else "\nNo identical groups found.")
                        + ("\n\nPartial scan: some items were skipped or a limit was reached."
                           if report.truncated else "")
                        + "\n\nIdentical bytes do not prove a file is unused or safe to delete. "
                          "Nothing changed. Use the file's owning game or manager to review.")
                elif name == "duplicates_canceled":
                    self._dupe_busy = False
                    self.status_text.set("Duplicate check canceled. Nothing changed.")
                elif name == "duplicates_error":
                    self._dupe_busy = False
                    self.status_text.set("Duplicate check incomplete. Nothing changed.")
                    messagebox.showwarning("Duplicate inspection incomplete", payload)
                elif name == "undo_selfcheck_pass":
                    self._selfcheck_busy = False
                    self.status_text.set("Disposable Recycle Bin and exact-byte Undo check passed.")
                    messagebox.showinfo("Recovery self-check passed",
                        "Windows moved and restored the exact bytes of one tiny Game Grave "
                        "test file, which was then cleaned up. No games, saves or mods "
                        "were touched. This is a local diagnostic, not full Windows "
                        "10/11 release acceptance.")
                elif name == "undo_selfcheck_fail":
                    self._selfcheck_busy = False
                    self.status_text.set("Windows recovery check failed. Cleanup must remain conservative.")
                    messagebox.showwarning("Recovery self-check failed",
                        payload + "\n\nGame Grave will not bypass its Recycle Bin "
                        "safety checks. The disposable test file might remain in "
                        "the Recycle Bin. No user game or save was selected.")
                elif name == "manager_profiles_result":
                    self.profile_report = payload
                    self.status_text.set(
                        f"Inspected {payload['count']} manager profiles. Nothing was modified.")
                    if self.active == "Game DNA":
                        self.show_page("Game DNA")
                elif name == "manager_profiles_error":
                    self.status_text.set("Manager profile inspection incomplete.")
                    messagebox.showwarning("Profile inspection incomplete", payload)
                elif name == "intelligence_result":
                    self._intel_report = payload
                    self.status_text.set("Game DNA change comparison complete. No game files changed.")
                    if self.active == "Game DNA":
                        self.show_page("Game DNA")
                    if payload.get("first_observation"):
                        messagebox.showinfo("Ghost Watch baseline",
                            "First on-demand mod metadata snapshot saved. Compare after a later scan.")
                elif name == "intelligence_error":
                    self.status_text.set("Game intelligence inspection incomplete.")
                    messagebox.showwarning("Game DNA inspection incomplete", payload)
                elif name == "kit_discovery_result":
                    name, discovery = payload
                    self.status_text.set("Setup discovery finished. Review suggested sources.")
                    self._show_kit_discovery(name, discovery)
                elif name == "mo2_reconnect_preview":
                    manifest, ini, plan = payload
                    self.status_text.set("MO2 restore preview verified. Approval required.")
                    if messagebox.askyesno("Approve MO2 profile reconstruction?",
                            f"Installed game: {plan['game']}\n"
                            f"Create new profile: {plan['profile_target']}\n"
                            f"Add {plan['mods_count']} missing mod folder(s) into:\n"
                            f"{plan['mod_root']}\n\n"
                            f"Files: {plan['files']} · size: {human_size(plan['bytes'])}\n\n"
                            "Close MO2 first. Existing folders and game files will not "
                            "be merged, replaced or deleted.\n\n"
                            f"Other roles not reconnected: {', '.join(plan['not_reconnected_roles']) or 'none'}\n"
                            "Save/config folders remain available in the verified kit for "
                            "separate safe recovery.\n\n"
                            "Afterwards, select the new GameGrave profile in MO2.\n\n"
                            "Create the new profile and mod folders?"):
                        self._apply_mo2_reconnect(manifest, ini, plan)
                elif name == "mo2_reconnect_result":
                    self.status_text.set("MO2 kit reconnected as a new profile")
                    log_event("MO2 Resurrection Kit reconnected", payload["profile"])
                    messagebox.showinfo("MO2 profile recreated",
                        f"New profile:\n{payload['profile']}\n\n"
                        f"{payload['added_mod_folders']} mod folders restored. "
                        "Open MO2 and select the restored profile. "
                        f"Kit roles not reconnected: {', '.join(payload['not_reconnected_roles']) or 'none'}. "
                        "Game Grave did not overwrite an existing setup.")
                elif name == "mo2_reconnect_error":
                    self.status_text.set("MO2 restore not completed; existing setup protected.")
                    messagebox.showwarning("MO2 restore stopped safely", payload)
                elif name == "lab_missing":
                    message = (f"{payload['game']} · {payload['readiness']}\n"
                        f"Verified archive: {payload['files']} files\n"
                        f"Manager: {payload['manager']}\n\n")
                    message += ("Isolated restore rehearsal: " +
                                ("passed (game launch not tested)" if payload.get("restore_rehearsed")
                                 else "not yet recorded") + "\n\n")
                    if payload["missing_count"]:
                        message += (f"Missing enabled mod folders ({payload['missing_count']}):\n" +
                                    "\n".join("• " + v for v in payload["missing_enabled_mods"][:20]) + "\n\n")
                    if payload["issues"]:
                        message += "Problems:\n" + "\n".join("• " + v for v in payload["issues"][:10]) + "\n\n"
                    message += ("Still unverified:\n" +
                        "\n".join("• " + v for v in payload["unknown"][:8]) +
                        "\n\nNo original download links were invented.")
                    self.status_text.set("Missing Pieces audit completed (read-only)")
                    messagebox.showinfo("Resurrection Readiness", message)
                elif name == "lab_rehearsal":
                    self.status_text.set("Isolated Resurrection Rehearsal verified")
                    messagebox.showinfo("Rehearsal passed",
                        f"{payload['game']}: extracted and SHA-256 checked "
                        f"{payload['files_verified']} files in an isolated scratch folder.\n\n"
                        "The temporary files were cleaned up. " +
                        ("A local checksum receipt was recorded. " if payload.get("receipt_recorded")
                         else "No receipt was recorded. ") +
                        "Game launch, manager compatibility and original save consistency "
                        "are NOT verified.")
                elif name == "lab_watch_saved":
                    self.status_text.set("Kit folders saved for optional local checks")
                    messagebox.showinfo("Living Kit tracked",
                        f"{payload['game']} · {payload['folders']} folders.\n\n"
                        "Game Grave will check metadata only when you ask. "
                        "No background polling or automatic ZIP updates.")
                elif name == "lab_watch_removed":
                    self.status_text.set("Local watch entry removed")
                    messagebox.showinfo("Stopped tracking",
                        "Watch entry removed. Existing kits and game files are untouched.")
                elif name == "lab_watch_check":
                    changed = [r for r in payload if r["status"] == "possible changes"]
                    unknown = [r for r in payload if r["status"] == "unknown"]
                    self.status_text.set(
                        f"{len(changed)} tracked kit(s) may have changed; "
                        f"{len(unknown)} need inspection.")
                    lines = "\n".join(
                        f"• {r['game']}: {r['status']}" for r in payload[:16])
                    if changed and messagebox.askyesno("Living Kit watch results",
                            f"{lines}\n\n"
                            "Metadata differences are not proof of changed contents. "
                            "Run a complete content review for a changed kit now?"):
                        if len(changed) == 1:
                            chosen = changed[0]
                        else:
                            labels = "\n".join(
                                f"{i+1}. {item['game']} - {Path(item['manifest']).name}"
                                for i, item in enumerate(changed))
                            index = simpledialog.askinteger("Review which kit?",
                                "Choose one changed kit:\n\n" + labels,
                                parent=self, minvalue=1, maxvalue=len(changed))
                            if index is None:
                                continue
                            chosen = changed[index-1]
                        sources = {role: Path(path) for role, path in chosen["sources"].items()}
                        self._lab_work(
                            "lab_living_preview", "Comparing watched kit against actual file contents…",
                            lambda entry=chosen, roots=sources: (
                                entry["manifest"], roots,
                                plan_living_update(Path(entry["manifest"]), roots)))
                    elif not changed:
                        messagebox.showinfo("Living Kit watch results",
                            f"{lines or 'No kits tracked.'}\n\n"
                            "Unchanged metadata is not proof of identical file contents. "
                            "Use Living Kits for full content review when needed.")
                elif name == "lab_living_preview":
                    previous, sources, plan = payload
                    self.status_text.set("Living Kit comparison completed")
                    if not plan["changed"]:
                        messagebox.showinfo("Already current",
                            "No file-content differences found. The existing kit is still current. "
                            "No new ZIP was created.")
                        continue
                    preview = "\n".join(
                        f"• {c['change']}: {c['path']}" for c in plan["changes"][:18])
                    if not messagebox.askyesno("Save a new kit version?",
                            f"Game: {plan['game']}\nChanges: {plan['change_count']}\n"
                            f"Files in new version: {plan['files']}\n\n"
                            f"{preview}\n\n"
                            "A NEW independent ZIP will be created; the previous kit remains "
                            "unchanged. The new kit will NOT inherit old manager identity "
                            "evidence. Continue?"):
                        continue
                    destination = filedialog.asksaveasfilename(
                        title="Save new immutable Resurrection Kit version",
                        defaultextension=".zip", filetypes=[("ZIP archive", "*.zip")],
                        initialfile=plan["game"].replace("/", "_").replace("\\", "_") +
                                    "_Resurrection_vNext.zip")
                    if not destination:
                        continue
                    self._lab_work("lab_living_created", "Creating verified new kit version…",
                        lambda prev=previous, roots=sources, dest=destination, p=plan:
                        create_living_update(Path(prev), roots, Path(dest), approved=True,
                                             expected_source_fingerprint=p["source_fingerprint"],
                                             expected_previous_archive_hash=p["previous_archive_hash"]))
                elif name == "lab_living_created":
                    self.status_text.set("New Living Kit version saved")
                    log_event("Living Resurrection Kit version created", payload["archive"])
                    messagebox.showinfo("New version verified",
                        f"{payload['files']} files preserved in independent ZIP:\n"
                        f"{payload['archive']}\n\nManifest:\n{payload['manifest']}\n\n"
                        "The previous version was not changed.")
                elif name == "lab_time_machine":
                    self.status_text.set("Time Machine comparison completed")
                    lines = "\n".join(
                        f"• {c['change']}: {c['path']}" for c in payload["changes"][:22])
                    if messagebox.askyesno("Time Machine · Snapshot comparison",
                            f"{payload['game']}\n"
                            f"{payload['older_files']} older files → {payload['newer_files']} newer\n"
                            f"{payload['change_count']} differences detected\n\n"
                            f"{lines or '(No detected differences)'}\n\n"
                            "Differences use size + ZIP CRC32. Both full archive "
                            "checksums passed, but game compatibility is unverified.\n\n"
                            "Stage the OLDER kit in a NEW recovery folder?"):
                        self._preview_resurrection_kit(payload["before"])
                elif name == "lab_versions":
                    self.status_text.set(f"Found {len(payload)} local kit versions")
                    listing = "\n".join(
                        f"• {r['game']} — {Path(r['manifest']).name} "
                        "(not integrity-checked yet)" for r in payload[:30])
                    messagebox.showinfo("Kit versions", listing or
                        "No readable Resurrection Kit manifests found in that directory.")
                elif name == "lab_transfer":
                    self.status_text.set("Portable PC-to-PC kit copy verified")
                    log_event("Resurrection PC transfer prepared", payload["target"])
                    messagebox.showinfo("Portable transfer ready",
                        f"Verified {payload['files_in_kit']} kit files.\n\n"
                        f"Transfer folder:\n{payload['target']}\n\n"
                        "Copy the ENTIRE folder to the new PC. Follow READ_ME_FIRST.txt. "
                        "Install the game normally through its launcher; restore "
                        "game saves and mods only after review.")
                elif name == "lab_error":
                    self.status_text.set("Resurrection Lab operation stopped safely")
                    messagebox.showwarning("Resurrection Lab incomplete", payload)
                elif name == "kit_result":
                    self.status_text.set("Resurrection Kit saved and verified")
                    log_event("Resurrection Kit created", payload["archive"])
                    messagebox.showinfo("Setup preserved",
                        f"Verified {payload['files']} files in: {', '.join(payload['roles'])}.\n"
                        f"ZIP: {payload['archive']}\nManifest: {payload['manifest']}\n\n"
                        "KEEP BOTH FILES TOGETHER. Game installation and any unselected "
                        "mod folders are not included.")
                elif name == "kit_preview":
                    manifest, parent, checked = payload
                    self.status_text.set("Resurrection Kit verified. Ready for your approval.")
                    if messagebox.askyesno("Restore verified Resurrection Kit?",
                            f"Game: {checked['game']}\n"
                            f"Verified files: {checked['files']}\n"
                            f"Uncompressed data: {human_size(checked['bytes'])}\n"
                            f"Included folders: {', '.join(checked['roles'])}\n\n"
                            f"NEW recovery folder:\n{checked['target']}\n\n"
                            "Existing files will NOT be replaced. This will not "
                            "automatically install mods or alter the live game.\n\n"
                            "Create this recovered copy?"):
                        self._restore_verified_kit(manifest, parent)
                elif name == "kit_restore_result":
                    self.status_text.set("Resurrection Kit files restored to a separate folder")
                    log_event("Resurrection Kit restored", payload["target"])
                    if messagebox.askyesno("Recovery files verified",
                            f"Recovered {payload['files']} files into:\n{payload['target']}\n\n"
                            "Your installed game and existing saves were not replaced.\n"
                            "Reconnect the files through the game or mod manager as needed.\n\n"
                            "Open the new folder in Explorer?"):
                        try:
                            if os.name == "nt":
                                os.startfile(payload["target"])
                        except OSError as exc:
                            messagebox.showwarning("Unable to open recovered folder", str(exc))
                elif name == "kit_error":
                    self.status_text.set("Resurrection Kit could not be completed")
                    messagebox.showwarning("Resurrection Kit incomplete", payload)
                elif name == "shader_preview":
                    game, cache = payload
                    self._confirm_shader_cache(game, cache)
                elif name == "shader_result":
                    self.cleanup_running = False
                    game_name, removed, skipped = payload
                    self.status_text.set(f"{game_name}: {removed} shader-cache files recycled")
                    messagebox.showinfo("Shader cleanup finished",
                        f"{game_name}\n\n{removed} file(s) sent to Recycle Bin."
                        f"\n{len(skipped)} skipped.\n\n"
                        "Shader files may rebuild at the next launch. Empty the Recycle Bin "
                        "separately if you need to reclaim disk space.\n\n" +
                        "\n".join(skipped[:5]))
                    self.scan_all()
                elif name == "shader_cleanup_error":
                    self.cleanup_running = False
                    self.status_text.set("Shader deletion was interrupted. Check Recycle Bin and Undo Center.")
                    self.scan_button.configure(state="normal", bg=ACCENT)
                    messagebox.showwarning("Shader deletion interrupted",
                        payload + "\n\nSome files may already have moved. "
                        "Check Recycle Bin and Undo Center before trying again.")
                    self.scan_all()
                elif name == "shader_error":
                    self.status_text.set("Shader cache check incomplete. Nothing was removed.")
                    messagebox.showwarning("Shader cache check incomplete", payload)
                elif name == "update_check_result":
                    self._update_check_active = False
                    if payload.status == "available":
                        self.status_text.set("A newer signed release was verified. No files were downloaded.")
                        messagebox.showinfo(
                            "Verified update available",
                            f"Installed release: {payload.installed_version}\n"
                            f"New stable release: {payload.release.version}\n\n"
                            f"Verified metadata download URL:\n{payload.release.download_url}\n\n"
                            f"Published installer SHA-256:\n{payload.release.installer_sha256}\n\n"
                            "Game Grave did NOT download, run, or install the update. "
                            "Installer Authenticode and byte checksum verification "
                            "are separate release requirements.",
                            parent=self)
                    else:
                        self.status_text.set("No newer signed stable release was advertised.")
                        messagebox.showinfo(
                            "No newer signed stable update",
                            f"Installed release: {payload.installed_version}\n"
                            "The verified metadata did not advertise a newer version. "
                            "No files were changed.",
                            parent=self)
                elif name == "update_check_error":
                    self._update_check_active = False
                    self.status_text.set("Signed update check incomplete. Game Grave remains offline-capable.")
                    messagebox.showwarning("Update not verified", payload, parent=self)
                elif name == "license_activated":
                    self.edition = payload
                    self._layout_after_edition_change()
                    messagebox.showinfo("Pro activated", "Lifetime Pro is active on this PC.", parent=self)
                elif name == "license_error":
                    self.status_text.set("Still using Free edition. No files changed.")
                    messagebox.showwarning("Couldn't activate Pro", payload, parent=self)
                elif name == "backup_result":
                    self.status_text.set("Verified backup created")
                    log_event("Save backup created", payload["destination"])
                    messagebox.showinfo("Backup verified", f"Saved {payload['files']} files to:\n{payload['destination']}\n\n"
                                        "ZIP archive passed integrity verification. Your source files were not modified.")
                elif name == "backup_error":
                    self.status_text.set("Backup was not completed")
                    messagebox.showwarning("Backup incomplete", payload)
                elif name == "undo_result":
                    perform, result = payload
                    self.status_text.set("Recycle Bin check: " + result.replace("_", " ").lower())
                    messagebox.showinfo("Recovery result", ("Restore result: " if perform else "Recovery check: ")
                                        + result.replace("_", " ") + "\n\nIf not found, Windows may have emptied the Recycle Bin.")
                    if self.active == "Undo Center":
                        self.show_page("Undo Center")
                elif name == "undo_error":
                    self.status_text.set("Recovery could not be checked")
                    messagebox.showwarning("Recovery not verified", payload)
                elif name == "saves_complete":
                    self._saves_loading = False
                    self.save_findings = payload
                    self.status_text.set(f"Found {len(payload)} possible save or profile folders. Nothing changed.")
                    if self.active == "Save Vault":
                        self._populate_saves()
                elif name == "saves_error":
                    self._saves_loading = False
                    self.status_text.set("Couldn't scan saved-game folders.")
                    messagebox.showwarning("Save discovery incomplete", payload)
                elif name == "scan_error":
                    if self._cancel_scan.is_set():
                        self._scan_canceled_status()
                    else:
                        self.scanning = False
                        self.scan_progress_text.set("Scan incomplete. No cleanup was performed.")
                        self.status_text.set("Scan could not finish. Check the chosen folder.")
                        self.scan_button.configure(state="normal", bg=ACCENT)
                        self.cancel_button.configure(state="disabled")
                        log_event("Scan failed", payload)
                        messagebox.showwarning("Scan incomplete", payload)
        except queue.Empty:
            pass
        if self.scanning:
            elapsed = time.monotonic() - self._scan_started
            eta = format_eta(eta_seconds(elapsed, self._scan_stage))
            self.scan_progress_text.set(f"{self._scan_stage_name} · {self.scan_percent.get():.0f}% stages complete "
                                        f"· {eta} · {int(elapsed)}s elapsed")
        self.after(180, self._poll)
