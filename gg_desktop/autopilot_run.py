"""Doing a plan's steps with Game Grave's own tools. No Qt: every outside call comes through `env`, so tests use stand-ins.

`prepare` runs the checks (reads only) and fills in each change with what it would act on. `run_change` does one change
the owner approved with Run all, reading the PC again first, and writes one activity-log line for it.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from types import SimpleNamespace

from gg_desktop import autopilot_core as core

OPTIMIZER_KEY = {"game_mode_on": "game_mode", "recording_off": "background_recording", "power_high": "power_plan"}
BACKUP_NAME = "game-optimizer-backup.json"


def default_env(never_touch=()):
    """The real tools. Built only when a plan runs, never at import."""
    from core import config_dir, human_size, log_event
    from gg_desktop import update_check, upkeep_core, winpc
    return SimpleNamespace(
        reg=winpc.default_registry(), runner=winpc.Runner(), backup=Path(config_dir()) / BACKUP_NAME,
        never_touch=list(never_touch), size=human_size, sleep=time.sleep,
        roots=winpc.cleanup_roots, plan_cleanup=winpc.plan_cleanup, run_cleanup=winpc.run_cleanup,
        list_processes=winpc.list_processes, close_processes=winpc.close_processes,
        read_optimizer=winpc.read_optimizer, apply_optimizer=winpc.apply_optimizer, undo_optimizer=winpc.undo_optimizer,
        has_backup=winpc.has_backup, search_updates=upkeep_core.search_updates, install_updates=upkeep_core.install_updates,
        read_startup=upkeep_core.read_startup, set_startup=upkeep_core.set_enabled, check_update=update_check.check,
        log=lambda details, result: log_event("AI Assistant", details, result=result),
        mo2_profiles=lambda: [], set_mod=_set_mod, cache={},
        games=lambda: [], game_crashes=_game_crashes, read_runtimes=_read_runtimes, open_url=_open_url,
        install_vcredist=_install_vcredist)


def _game_crashes(game):
    """Black Box's crash records for this game (Windows Application log, program inside the game folder)."""
    from gg_desktop import blackbox_core as bb
    return bb.crashes_for(bb.parse_events(bb.query_events()), Path(game.install_path))


def _read_runtimes():
    """(Visual C++ 2015-2022 x64 installed, x86 installed, d3dx9_43.dll present). Reads only."""
    import os
    import winreg
    def installed(view):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\" + view,
                                0, winreg.KEY_READ | winreg.KEY_WOW64_32KEY) as key:
                return winreg.QueryValueEx(key, "Installed")[0] == 1
        except OSError:
            return False
    windir = os.environ.get("WINDIR", r"C:\Windows")
    d3dx = os.path.exists(os.path.join(windir, "System32", "d3dx9_43.dll")) or \
        os.path.exists(os.path.join(windir, "SysWOW64", "d3dx9_43.dll"))
    return installed("x64"), installed("x86"), d3dx


def _open_url(url):
    import os
    os.startfile(url)        # steam:// links go to Steam itself


def _install_vcredist():
    """Download Microsoft's installer from Microsoft only, check it is signed by Microsoft, run it (Windows asks)."""
    import subprocess
    import tempfile
    import urllib.request
    from gg_desktop import fixgame_core as fx

    class Guard(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not fx.safe_download(newurl):
                raise OSError("Download moved to a host that is not Microsoft's, so it was stopped.")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    folder = Path(tempfile.mkdtemp(prefix="gg-vcredist-"))
    target = folder / "vc_redist.x64.exe"
    opener = urllib.request.build_opener(Guard)
    with opener.open(urllib.request.Request(fx.VC_DOWNLOAD, headers={"User-Agent": "GameGrave/1"}), timeout=60) as response:
        if not fx.safe_download(response.geturl()):
            raise OSError("The download did not come from Microsoft, so it was stopped.")
        target.write_bytes(response.read(80 * 1024 * 1024))
    check = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                            "$s = Get-AuthenticodeSignature -LiteralPath $args[0]; \"$($s.Status)|$($s.SignerCertificate.Subject)\"",
                            str(target)], capture_output=True, text=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    status, _, subject = (check.stdout or "").strip().partition("|")
    if status != "Valid" or "Microsoft Corporation" not in subject:
        target.unlink(missing_ok=True)
        raise OSError("The installer's signature is not a valid Microsoft signature, so it was not run.")
    run = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                          "$p = Start-Process -FilePath $args[0] -ArgumentList '/install','/passive','/norestart' -Verb RunAs "
                          "-Wait -PassThru; exit $p.ExitCode", str(target)], capture_output=True, text=True, timeout=900,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    target.unlink(missing_ok=True)
    return run.returncode


def _set_mod(folder, name, on):
    from gg_desktop import mymods_core
    from gg_desktop.bisect_apply import mo2_running
    return mymods_core.set_enabled(Path(folder), [name], on, running=mo2_running)


def mo2_profiles(inventory_mods):
    """(game, profile name, profile folder, [(mod folder name, on, readable name)]) for the profile each Mod Organizer 2
    setup has selected. Reads only."""
    from manager_profiles import _mo2_roots
    from gg_desktop import mymods_core
    out = []
    for ini in _mo2_roots(inventory_mods or []):
        try:
            inst = mymods_core.read_instance(ini)
            names = [inst.selected] + [p for p in inst.profiles if p != inst.selected]
            profile = mymods_core.read_profile(inst, names[0])
        except Exception:
            continue
        mods = [(m.name, m.enabled, m.label) for m in profile.mods if m.kind == "mod"]
        out.append((inst.game, profile.name, profile.folder, mods))
    return out


def _plural(n, noun):
    return f"{n:,} {noun}" + ("" if n == 1 else "s")


def _not(notes):
    return any(re.search(r"\bnot\b", n, re.IGNORECASE) for n in notes)


def _mark(step, status, result):
    step.status, step.result = status, result
    return step


def _check(step, env, plan):
    """Run one check. May add change steps to the plan (apps to close, startup apps). Returns nothing; sets status."""
    if step.key == "check_memory":
        procs = env.list_processes(env.runner)
        biggest = ", ".join(f"{p.name} ({p.kb / 1024:,.0f} MB)" for p in procs[:3])
        _mark(step, "done", _plural(len(procs), "app") + " open." + (f" Biggest: {biggest}." if biggest else ""))
        new = core.close_steps(procs, step.args.get("mentioned", plan.request))
        if new:
            at = plan.steps.index(step) + 1
            plan.steps[at:at] = new
            if not any(s.ticked for s in new):
                step.result += " Tick the apps you want closed."
        return
    if step.key == "check_temp":
        roots = env.roots()
        found = env.plan_cleanup(roots, never_touch=env.never_touch)
        env.cache["cleanup"] = (roots, found)
        more = "+" if getattr(found, "truncated", False) else ""
        _mark(step, "done", f"{len(found.items):,}{more} old temporary files, {env.size(found.total)}." if found.items
              else "No temporary files older than 2 days.")
        for other in plan.steps:
            if other.key == "clear_temp" and other.status == "waiting":
                if found.items:
                    other.detail = (f"About {len(found.items):,}{more} files, {env.size(found.total)}. "
                                    "Each is checked again just before it is deleted.")
                else:
                    _mark(other, "skipped", "Nothing to delete.")
        return
    if step.key == "check_drivers":
        updates = env.search_updates()
        env.cache["drivers"] = updates
        names = ", ".join(u.title for u in updates[:3])
        _mark(step, "done", (f"Windows Update offers {_plural(len(updates), 'driver update')}: {names}" +
                             ("…" if len(updates) > 3 else ".")) if updates else "Windows Update offers no driver updates.")
        for other in plan.steps:
            if other.key == "install_drivers" and other.status == "waiting":
                if updates:
                    other.args = {"ids": [u.update_id for u in updates], "titles": [u.title for u in updates][:12]}
                    other.detail = _plural(len(updates), "update") + ". Windows asks you to allow it."
                else:
                    _mark(other, "skipped", "Nothing to install.")
        return
    if step.key == "check_startup":
        apps = env.read_startup()
        env.cache["startup"] = apps
        on = [a for a in apps if a.enabled]
        _mark(step, "done", f"{_plural(len(apps), 'app')} can start with Windows; {len(on):,} switched on.")
        new = core.startup_steps(apps, step.args.get("mentioned", plan.request), bool(step.args.get("off")))
        if new and step.args.get("off"):
            at = plan.steps.index(step) + 1
            plan.steps[at:at] = new
            if not any(s.ticked for s in new):
                step.result += " Tick the ones to switch off."
        return
    if step.key == "check_app_update":
        _kind, sentence = env.check_update()
        _mark(step, "done", sentence)
        return
    if step.key == "check_game_fix":
        _fix_check(step, env, plan)
        return
    if step.key == "check_mods":
        profiles = env.mo2_profiles()
        on = bool(step.args.get("on"))
        new, already = core.mod_steps(profiles, step.args.get("mentioned", plan.request), on)
        if not profiles:
            _mark(step, "problem", "No Mod Organizer 2 setup was found. Run Scan PC first, or switch mods in your mod "
                                   "manager. Steam Workshop items are changed in Steam.")
            return
        found = ", ".join(s.args["name"] for s in new)
        text = (f"Found {found}." if new else "No switched-" + ("off" if on else "on") + " mod with that name in your "
                "Mod Organizer 2 profiles.")
        if already:
            text += " Already " + ("on" if on else "off") + ": " + ", ".join(already[:5]) + "."
        _mark(step, "done", text)
        at = plan.steps.index(step) + 1
        plan.steps[at:at] = new
        return
    raise ValueError("Not a check: " + step.key)


def _fix_check(step, env, plan):
    from gg_desktop import fixgame_core as fx
    request = step.args.get("mentioned", plan.request)
    game = fx.game_named(env.games(), request)
    lines, new = [], []
    if game is None:
        lines.append("Name the game for a closer look (for example \"fix Elden Ring\"). These checks cover every game.")
    else:
        step.args["name"] = game.name
        try:
            lines.append(fx.crash_summary(env.game_crashes(game)))
        except Exception:
            lines.append("Windows' crash records could not be read.")
        link = fx.verify_link(game)
        if link:
            new.append(core.Step("verify_game", {"name": game.name, "url": link},
                                 detail="Steam re-downloads only damaged or missing files."))
        else:
            lines.append(fx.verify_words(game))
    try:
        overlays = fx.overlay_findings(p.name for p in env.list_processes(env.runner))
    except Exception:
        overlays = []
    if overlays:
        lines.append("Open overlays that hook into games: " + ", ".join(overlays) + ". Close them and try again.")
        procs = {p.name.casefold(): p for p in env.list_processes(env.runner)}
        for exe, label in fx.OVERLAYS.items():
            if label in overlays and exe in procs:
                new.append(core.Step("close_app", {"name": procs[exe].name, "pid": int(procs[exe].pid)},
                                     detail=label + " (overlay)", ticked=False))
    else:
        lines.append("No overlays known to cause trouble are open.")
    try:
        x64, x86, d3dx = env.read_runtimes()
        for finding in fx.runtime_findings(x64, x86, d3dx):
            lines.append(finding.detail)
        if not x64 or not x86:
            new.append(core.Step("install_vcredist", {}, detail="From Microsoft, signature checked. Windows asks to allow it."))
        if not d3dx:
            lines.append("DirectX End-User Runtime: " + fx.DIRECTX_PAGE)
        if x64 and x86:
            lines.append("Microsoft's Visual C++ runtime is installed.")
    except Exception:
        lines.append("The Microsoft runtimes could not be checked.")
    _mark(step, "done", " ".join(lines))
    at = plan.steps.index(step) + 1
    plan.steps[at:at] = new


def prepare(plan, env, game_running=lambda: False):
    """Run the plan's checks now (they only read) and fill in what each change would act on."""
    states = None
    for step in list(plan.steps):
        if step.status != "waiting":
            continue
        if step.kind == core.CHECK and step.key not in core.UI_CHECKS:
            if game_running():
                _mark(step, "skipped", "A game is running, so this waits.")
                continue
            try:
                _check(step, env, plan)
            except Exception as exc:  # one failed check never stops the others
                _mark(step, "problem", "Could not check: " + (str(exc)[:200] or type(exc).__name__))
        elif step.key in OPTIMIZER_KEY:
            try:
                states = states if states is not None else {s.key: s for s in env.read_optimizer(env.reg, env.runner)}
                state = states.get(OPTIMIZER_KEY[step.key])
                if state is not None and state.applied:
                    _mark(step, "skipped", "Already set.")
                elif state is not None:
                    step.detail = state.current
            except Exception:
                pass
        elif step.key == "undo_optimizer" and not env.has_backup(env.backup):
            _mark(step, "skipped", "Game Grave has not changed these settings, so there is nothing to put back.")
        elif step.key == "install_drivers" and not any(s.key == "check_drivers" for s in plan.steps):
            plan.steps.insert(plan.steps.index(step), core.Step("check_drivers"))
            return prepare(plan, env, game_running)
    return plan


def run_change(step, env, on_step=None):
    """Do one approved change. Reads the PC again first. Returns the step with its status and plain result."""
    key = step.key
    try:
        if key == "clear_temp":
            roots = env.roots()
            found = env.plan_cleanup(roots, never_touch=env.never_touch)  # fresh: the list may have changed since the check
            if not found.items:
                return _mark(step, "skipped", "No old temporary files were left to delete.")
            done = env.run_cleanup(list(found.items), roots)
            text = (f"Deleted {_plural(done.removed, 'file')} ({env.size(done.reported_bytes)} reported). "
                    f"{done.skipped:,} skipped because they changed, were in use or could not be removed.")
            env.log("Delete old temporary files: " + text, "Permanently deleted")
            return _mark(step, "done" if done.removed else "problem", text)
        if key in OPTIMIZER_KEY:
            notes = env.apply_optimizer(env.reg, env.runner, {OPTIMIZER_KEY[key]}, env.backup)
            text = " ".join(notes)
            env.log(step.title + ": " + text, "Changed")
            if any("already" in n.lower() for n in notes):
                return _mark(step, "skipped", "Already set.")
            return _mark(step, "problem" if _not(notes) else "done",
                         text.replace(": done.", ": done. Undo in Toolbox > Game Optimizer."))
        if key == "undo_optimizer":
            notes = env.undo_optimizer(env.reg, env.runner, env.backup)
            env.log("Put Windows settings back: " + " ".join(notes), "Restored")
            return _mark(step, "problem" if _not(notes) else "done",
                         "Some settings could not be put back." if _not(notes) else "Your previous settings are back.")
        if key == "close_app":
            pid, name = int(step.args["pid"]), str(step.args["name"])
            running = {p.pid: p.name for p in env.list_processes(env.runner)}
            if running.get(pid, "").casefold() != name.casefold():
                return _mark(step, "skipped", f"{name} was already closed.")
            env.close_processes(env.runner, [pid])
            env.sleep(1.5)
            still = pid in {p.pid for p in env.list_processes(env.runner)}
            text = (f"{name} is still open. It may be asking about unsaved work." if still else f"Closed {name}.")
            env.log(f"Asked {name} (PID {pid}) to close. " + text, "Some still running" if still else "Closed")
            return _mark(step, "problem" if still else "done", text)
        if key == "startup_off":
            apps = env.read_startup()
            app = next((a for a in apps if a.key == step.args.get("key")), None)
            if app is None:
                return _mark(step, "skipped", f"{step.args.get('name', 'That app')} is no longer in the startup list.")
            if not app.enabled:
                return _mark(step, "skipped", "Already switched off.")
            env.set_startup(app, False)
            text = f"{app.title} will no longer start with Windows. Turn it back on in Hardware > Drivers & Startup."
            env.log(text, "Startup off")
            return _mark(step, "done", text)
        if key in ("mod_off", "mod_on"):
            on = key == "mod_on"
            env.set_mod(step.args["folder"], step.args.get("key") or step.args["name"], on)
            text = (f"{step.args['name']} is now " + ("on" if on else "off") + f" in {step.args.get('game', 'Mod Organizer 2')}"
                    f" (profile {step.args.get('profile', '')}). Undo in Mods > My Mods.")
            env.log(text, "Mod switched " + ("on" if on else "off"))
            return _mark(step, "done", text)
        if key == "verify_game":
            url = str(step.args.get("url", ""))
            if not url.startswith("steam://validate/"):
                return _mark(step, "problem", "Only Steam's own verify can be opened from here.")
            env.open_url(url)
            text = f"Steam is checking {step.args.get('name', 'the game')}'s files. Watch Steam for the result."
            env.log(text, "Verify started")
            return _mark(step, "done", text)
        if key == "install_vcredist":
            code = env.install_vcredist()
            ok = code in (0, 1638, 3010)     # 1638: a newer one is already installed; 3010: restart to finish
            text = ("Microsoft's Visual C++ runtime is installed." + (" Restart the PC to finish." if code == 3010 else "")
                    if ok else f"The installer stopped with code {code}. Nothing else was changed.")
            env.log("Visual C++ runtime: " + text, "Installed" if ok else "Not finished")
            return _mark(step, "done" if ok else "problem", text)
        if key == "install_drivers":
            ids = list(step.args.get("ids") or [])
            updates = [u for u in env.cache.get("drivers") or env.search_updates() if not ids or u.update_id in ids]
            if not updates:
                return _mark(step, "skipped", "Windows Update offers no driver updates now.")
            ok, text, restart = env.install_updates(updates, on_step=on_step)
            env.log("Driver updates: " + text, "Installed" if ok else "Not finished")
            if restart:
                text += " Restart the PC to finish."
            return _mark(step, "done" if ok and not restart else "problem", text)
    except Exception as exc:  # the owner sees exactly why it stopped
        return _mark(step, "problem", "Stopped: " + (str(exc)[:240] or type(exc).__name__))
    return _mark(step, "problem", "Game Grave does not know how to do this step.")


def outcome(plan):
    """One closing sentence for the plan, and its colour."""
    ran = [s for s in plan.steps if s.ticked]
    if any(s.result == "Cancelled by you." for s in ran) and not any(s.status == "done" and s.kind == core.CHANGE
                                                                     for s in ran):
        return "Cancelled. Nothing was changed.", "warn"
    done = sum(1 for s in ran if s.status == "done")
    problems = sum(1 for s in ran if s.status == "problem")
    waiting = sum(1 for s in ran if s.status == "waiting")
    if waiting:
        return f"Stopped with {_plural(waiting, 'step')} not done.", "warn"
    if problems:
        return f"Finished: {done} done, {_plural(problems, 'step')} to look at.", "warn"
    return f"All done: {_plural(done, 'step')} finished." if done else "Nothing needed doing.", "good"
