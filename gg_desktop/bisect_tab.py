"""Mods > Bisect: the screen layer. It draws `bisect_model` (rows and the inspector panel) and forwards clicks.

Qt only. Every decision, claim and file rule lives in the pure modules (`bisect_core`, `bisect_flow`, `bisect_model`,
`bisect_apply`), which are unit tested; this file never decides anything the model does not return. The only things it
writes are the files the owner asks for (a saved list or report) and, through `bisect_apply`, a COPY of a Mod
Organizer 2 profile.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QCheckBox, QFileDialog, QLineEdit, QMenu
from shiboken6 import isValid

import core
from gg_desktop import bisect_clues as clues_mod
from gg_desktop import bisect_model as bm
from gg_desktop import bisect_units as units_mod
from gg_desktop import blackbox_core as bb
from gg_desktop.reference_library import _checked
from gg_desktop.reference_widgets import detail_line, detail_section, tool

TONES = {"Cause": "amber", "On in test": "green", "Always on": "green", "Ruled out": "muted",
         "Not the cause": "muted", "Off in test": "muted"}
HEADERS = ("", "Mod", "Added", "Status", "Why look here")
WIDTHS = (25, 150, 128, 88, 140)
GOOD = "#27dc74"


# ---------------------------------------------------------------- state
def model_for(window) -> bm.Model:
    model = getattr(window, "_bisect_model", None)
    if model is None:
        model = bm.Model(core.config_dir())
        window._bisect_model = model
    return model


def chosen_profile(window, control):
    profiles = control.catalog.profiles
    if not profiles:
        return None
    key = window._mod_profile_keys.get("Bisect", "")
    return (next((p for p in profiles if p.key == key), None) or next((p for p in profiles if p.selected), None)
            or profiles[0])


def profile_info(window, control, profile) -> bm.ProfileInfo:
    folder = Path(profile.source).parent if profile.manager == "Mod Organizer 2" else None
    game = next((g for g in window.inventory.games if g.key == profile.game_key), None)
    entry = next((e for e in control.catalog.entries if profile.key in e.profiles), None)
    return bm.ProfileInfo(profile.key, profile.name, profile.manager, folder, getattr(game, "name", "") if game else "",
                          getattr(game, "install_path", "") if game else "",
                          entry.manager_folder if entry else "")


def refresh(window):
    if isValid(window) and getattr(window, "current_route", "") == "Mods" and getattr(window, "_mod_tab", "") == "Bisect":
        window._fill_mods(requested_page=window.mod_pager.page)


def checked_keys(window) -> list:
    rows = getattr(window, "_mod_tab_rows", [])
    return [rows[i].key for i in _checked(window.mod_table) if 0 <= i < len(rows)]


# ---------------------------------------------------------------- the table
def tab_rows(window, control):
    from gg_desktop.mods_page import TabRow
    model = model_for(window)
    profile = chosen_profile(window, control)
    info = profile_info(window, control, profile) if profile else None
    marker = (id(control.catalog), profile.source_mtime_ns if profile else 0)
    if model.sync(info, marker):
        start_load(window, control, model, profile, marker)
    out = []
    for r in model.rows():
        tone = TONES.get(r.status, "")
        out.append(TabRow(r.key, (r.name, r.added, r.status, r.why), r, hay=" ".join((r.name, r.status, r.why)),
                          kinds={3: tone} if tone else {}, tip=r.why))
    return out, model.notice()


def start_load(window, control, model, profile, marker):
    work = model.load_job(control.catalog, profile, control.canceled)
    key = profile.key

    def finish(result, error):
        if model.profile is None or model.profile.key != key or model.marker != marker:
            return                                  # the owner moved on; a newer read owns the state
        model.load_done(result, error)
        refresh(window)
    control.task(lambda emit: work(emit), finish)


# ---------------------------------------------------------------- crash reports
def documents_folders() -> list:
    found = [Path.home() / "Documents"]
    one_drive = os.environ.get("OneDrive")
    if one_drive:
        found.append(Path(one_drive) / "Documents")
    return [p for p in found if p.is_dir()]


def collect_reports(units, files, profile, folders=None):
    """Worker: find crash logs near the game, read the Windows crash records, match both to the mods."""
    roots = units_mod.default_report_roots(profile.install_path or None, profile.base_folder or None, None)
    for docs in documents_folders():
        roots += units_mod.default_report_roots(None, None, docs)
    paths = units_mod.find_reports(roots, now=time.time())
    texts = units_mod.read_reports_text(paths)
    crashes = []
    try:
        crashes = bb.parse_events(bb.query_events())
        if profile.install_path:
            crashes = bb.crashes_for(crashes, Path(profile.install_path))
    except OSError:
        crashes = []
    return clues_mod.read_reports(units, files, texts, crashes, folders), len(paths)


def start_reports(window, control, model):
    work = model.reports_job(collect_reports)
    key = model.profile.key if model.profile else ""

    def finish(result, error):
        if model.profile is None or model.profile.key != key:
            return
        model.reports_done(result, error)
        refresh(window)
    control.task(lambda emit: work(emit), finish)


# ---------------------------------------------------------------- building a test profile
def start_apply(window, control, model):
    work = model.apply_job()
    if work is None:
        return
    key = model.profile.key if model.profile else ""

    def finish(result, error):
        if model.profile is None or model.profile.key != key:
            return
        model.apply_done(result, error)
        refresh(window)
    control.task(lambda emit: work(emit), finish)


# ---------------------------------------------------------------- clicks
def choose_pack(window, model):
    choices = model.pack_choices()[:15]
    if not choices:
        model.message = "No group of mods installed together was found."
        return
    menu = QMenu(window)
    for text, keys in choices:
        action = menu.addAction(text)
        action.setData(list(keys))
    picked = menu.exec(QCursor.pos())
    menu.deleteLater()
    if picked is not None:
        keys = picked.data() or []
        model.use_hints(keys, picked.text())


def write_text_file(window, model, kind, text, name):
    start = str(Path.home() / "Documents" / name)
    target, _ = QFileDialog.getSaveFileName(window, "Save " + kind, start, "Text files (*.txt)")
    if not target:
        return
    try:
        Path(target).write_text(text, encoding="utf-8")
    except OSError as exc:
        window.error("Could not save", str(exc))
        return
    window.info("Saved", "Saved to " + target)


def act(window, control, key):
    model = model_for(window)
    if key == "start":
        model.start()
    elif key == "use_checked":
        keys = checked_keys(window)
        if keys:
            model.use_hints(keys, f"{len(keys)} mods you ticked")
        else:
            model.message = "Tick the mods you added just before the crashes began, then press this."
    elif key == "pick_pack":
        choose_pack(window, model)
    elif key == "always_on":
        keys = checked_keys(window)
        if keys:
            model.mark_always_on(keys)
        else:
            model.message = "Tick the mods that must stay on (frameworks other mods need), then press this."
    elif key == "clear_clues":
        model.clear_hints()
        model.clear_always_on()
    elif key == "read_reports":
        start_reports(window, control, model)
    elif key == "build":
        start_apply(window, control, model)
    elif key in ("crash", "ok", "unsure"):
        model.answer(key)
    elif key == "undo":
        model.undo()
    elif key == "stop":
        if window.confirm("Stop searching?", "Your answers so far will be forgotten. Nothing in your mods or profiles "
                                             "was changed."):
            model.stop()
    elif key == "restart":
        model.restart()
    elif key == "copy_list":
        QApplication.clipboard().setText(model.copy_text_for_step())
        model.message = "Copied. Paste it anywhere to follow along."
    elif key == "save_list":
        write_text_file(window, model, "list", model.copy_text_for_step(), "bisect-mods-to-turn-on.txt")
    elif key == "copy_report":
        QApplication.clipboard().setText(model.report_text())
        model.message = "Report copied."
    elif key == "save_report":
        path = model.save_report()
        model.message = "Report saved to " + str(path)
        window.info("Report saved", str(path))
    elif key == "open_copy" and model.copy is not None:
        from gg_desktop.mods_page import open_path
        open_path(window, str(model.copy.folder))
    refresh(window)


# ---------------------------------------------------------------- the inspector
def details(window, control, contents, item):
    from gg_desktop.mods_page import plain_label
    model = model_for(window)
    panel = model.panel()
    contents.addWidget(plain_label(panel.title, "detailTitle"))
    for kind, text in panel.lines:
        if kind == "section":
            detail_section(contents, text)
        elif kind.startswith("key:"):
            detail_line(contents, "mods", kind[4:], text)
        elif kind == "caption":
            contents.addWidget(plain_label(text, "caption"))
        elif kind == "warn":
            contents.addWidget(plain_label(text, "warning"))
        elif kind == "good":
            good = plain_label(text, "subtle")
            good.setStyleSheet("color:" + GOOD + ";")
            contents.addWidget(good)
        else:
            contents.addWidget(plain_label(text, "subtle"))
    for field in panel.fields:
        contents.addWidget(plain_label(field.label, "caption"))
        edit = QLineEdit(field.value)
        edit.setPlaceholderText(field.placeholder)
        edit.setAccessibleName(field.label)
        edit.setFixedHeight(28)
        edit.textChanged.connect(lambda text, key=field.key: model.set_field(key, text))
        edit.editingFinished.connect(lambda: refresh(window))
        contents.addWidget(edit)
    for toggle in panel.toggles:
        box = QCheckBox(toggle.text)
        box.setChecked(toggle.checked)
        box.setAccessibleName(toggle.text)
        box.toggled.connect(lambda on, key=toggle.key: (model.set_sometimes(on) if key == "sometimes" else None))
        contents.addWidget(box)
    for button in panel.buttons:
        control_ = tool(button.text, button.symbol, lambda _=False, key=button.key: act(window, control, key),
                        kind="primary" if button.primary else "", tip=button.tip)
        control_.setEnabled(button.enabled)
        contents.addWidget(control_)
    if item is not None and model.units:
        detail_section(contents, "Selected Mod")
        detail_line(contents, "calendar", "Added", item.payload.added)
        detail_line(contents, "scan", "Status", item.payload.status)
        for reason in model.reasons_for(item.key)[:5]:
            contents.addWidget(plain_label(reason, "caption"))
