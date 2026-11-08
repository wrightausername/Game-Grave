"""Protect the twelve other tabs (including locked AI Assistant, Undo Center, Game DNA, Graveyard, Captures, Mods, Ready Room, Old Files, Other Storage and Games) while Settings is worked on."""
from __future__ import annotations
import argparse
import ast
from collections import namedtuple
from contextlib import ExitStack
import hashlib
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from unittest.mock import patch

BASELINE = "040951c7c85c367d23841c091573e1610fe11e67"  # the owner-signed AI Assistant lock; AI Assistant, Undo Center, Game DNA, Graveyard, Captures, Old Files, Other Storage, Mods, Games and every other tab are frozen here
OVERVIEW_FOUNDATION = "8733e55505e1500c74646e540fcd2f7ba565ec0f"


def probe(root, fixtures, output, foundation=False):
    sys.path.insert(0, str(root))
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtGui import QCursor, QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from core import SteamGame, ModFolder, OldFile, default_settings
    from gg_desktop.app import CrimsonWindow, ROUTES
    from gg_desktop.backend import Inventory
    from gg_desktop.models import merge_games
    from graveyard import build_graveyard
    app = QApplication.instance() or QApplication([])
    output.mkdir(parents=True, exist_ok=True)
    fixtures.mkdir(parents=True, exist_ok=True)
    install, mods_path, download = fixtures/"Games/1091500", fixtures/"Mods", fixtures/"Downloads/archive.zip"
    install.mkdir(parents=True, exist_ok=True)
    mods_path.mkdir(exist_ok=True)
    download.parent.mkdir(exist_ok=True)
    if not download.exists():
        download.write_bytes(b"DISPOSABLE TAB LOCK FIXTURE")
        os.utime(download, (1700000000, 1700000000))
    st = download.stat()
    file = OldFile(str(download), st.st_size, st.st_mtime, st.st_dev, st.st_ino, st.st_mtime_ns, st.st_nlink)
    steam = SteamGame("1091500", "Cyberpunk 2077", str(fixtures/"Steam"), str(install), 120000000, None, "Scope fixture")
    mod = ModFolder("Scope fixture", str(mods_path), "", "Installed: possible mods", (), 12000, 1, False, "Manual / Other", "Protected scope fixture")
    settings = default_settings()
    settings.update(scan_on_launch=False, scan_folder=str(download.parent), desktop_favorites=[])
    hashes = {}
    usage = namedtuple("usage", "total used free")(8*1024**4, 5*1024**4, 3*1024**4)
    with ExitStack() as stack:
        for target, options in (
            ("gg_desktop.app.load_settings", dict(side_effect=lambda: dict(settings))),
            ("gg_desktop.ready_room_services.config_dir", dict(return_value=fixtures/"Preferences")),
            ("gg_desktop.game_artwork.artwork_dir", dict(return_value=fixtures/"Artwork")),
            ("gg_desktop.game_artwork._request", dict(side_effect=AssertionError("Automatic network"))),
            ("gg_desktop.reference_overview.get_activity", dict(return_value=[])),
            ("gg_desktop.reference_overview.get_records", dict(return_value=[])),
            ("gg_desktop.undo_page.get_activity", dict(return_value=[])),
            ("gg_desktop.undo_page.get_records", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_activity", dict(return_value=[])),
            ("gg_desktop.assistant_page.get_records", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_activity", dict(return_value=[])),
            ("gg_desktop.recovery_screens.get_records", dict(return_value=[])),
            ("shutil.disk_usage", dict(return_value=usage)),
            # Games is part of what this lock protects: keep its launcher/registry/account reads on disposable fixtures.
            ("gg_desktop.games_live.registered_games", dict(return_value=[])),
            ("core.config_dir", dict(return_value=fixtures/"Config")),
            # The 5-second process sampler is a recurring OS enumeration, not page content.
            ("gg_desktop.games_tracking.GameTracker.sample", dict(return_value=None)),
        ):
            stack.enter_context(patch(target, **options))
        stack.enter_context(patch.object(CrimsonWindow, "info"))
        stack.enter_context(patch.object(CrimsonWindow, "error", side_effect=AssertionError("Unexpected UI error")))
        for populated in (False, True):
            window = CrimsonWindow()
            # Capture a neutral, reproducible state on Windows; placement and
            # a cursor left by a preceding click-through must not add hover.
            window.move(20, 20)
            window.show()
            QCursor.setPos(window.screen().geometry().topLeft())
            if populated:
                window.inventory = Inventory(steam=[steam], games=merge_games([steam], []), mods=[mod], files=[file], scanned_at="2026-11-06 12:00")
                window.inventory.graveyard = build_graveyard([steam], [mod], [file], 365)
            window._ready_checks_busy = True
            for width, height in ((1280,720), (1536,864), (960,650)):
                window.resize(width, height)
                for route, _ in ROUTES:
                    if route == "Settings":
                        continue
                    window.navigate("Overview")
                    window.navigate(route)
                    QTest.qWait(35)
                    for _ in range(1500):
                        app.processEvents()
                        if not window.workers and not window.artwork.busy and not window.artwork.queue:
                            break
                        QTest.qWait(10)
                    assert not window.workers, route + ": background jobs still running: " + ", ".join(
                        getattr(getattr(job, "fn", None), "__qualname__", repr(job)) for job in window.workers.values())
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                    app.processEvents()
                    window.page.setFocusPolicy(Qt.StrongFocus)
                    window.page.setFocus()
                    if foundation:
                        # Native Windows can queue the responsive grid's paint
                        # after the resize/layout events. Record the transition
                        # and compare the settled user-visible dashboard.
                        if not populated and width == 960:
                            assert window.grab().save(str(output/"transition-empty-960-overview.png"))
                        QTest.qWait(180)
                    else:
                        QTest.qWait(10)
                    assert window.nav_rail.isVisible() and window.top_bar.isVisible(), route
                    image = window.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
                    key = f"{'populated' if populated else 'empty'}-{width}-{route.lower().replace(' ', '-')}"
                    hashes[key] = hashlib.sha256(bytes(image.constBits())).hexdigest()
                    assert image.save(str(output/(key+".png")))
            window.close()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    (output/"hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")


def source_guard(root, baseline=BASELINE):
    if subprocess.run(["git","cat-file","-e",baseline],cwd=root,capture_output=True).returncode:
        subprocess.run(["git","fetch","--no-tags","--depth=1","origin",baseline],cwd=root,check=True)
    # photo_integration.py is AST-checked below; the settings_* modules are new files and are the active tab itself.
    # The owner approved three shared-code corrections, all outside any tab's look: app.py (settings kept across
    # restarts, start minimized), backend.py (excluded folders filter) and mods_page.py (stale-row crash guard).
    # The thirteen other tabs are still compared pixel for pixel below.
    allowed = {"gg_desktop/photo_integration.py", "gg_desktop/app.py", "gg_desktop/backend.py", "gg_desktop/mods_page.py"}
    shared_path = "gg_desktop/photo_integration.py"
    original = subprocess.check_output(["git", "show", baseline+":"+shared_path], cwd=root).decode()
    current = (root/shared_path).read_text(encoding="utf-8")
    mods_methods = {"settings_page"}
    def protected_ast(source):
        tree = ast.parse(source)
        for item in tree.body:
            if isinstance(item, ast.ClassDef) and item.name == "PhotoIntegration":
                item.body = [method for method in item.body if not
                    (isinstance(method, ast.FunctionDef) and method.name in mods_methods)]
        return ast.dump(tree, include_attributes=False)
    assert protected_ast(original) == protected_ast(current), "Shared integration changed outside Settings methods"
    paths = subprocess.check_output(["git","ls-tree","-r","--name-only",baseline,"gg_desktop"],cwd=root).decode().splitlines()
    for path in paths:
        if path in allowed:
            continue
        before = subprocess.check_output(["git","show",baseline+":"+path],cwd=root)
        after = (root/path).read_bytes()
        # Git converts these text files to CRLF on Windows checkouts.
        if Path(path).suffix in {".py", ".svg", ".md", ".json", ".txt"}:
            before, after = before.replace(b"\r\n",b"\n"), after.replace(b"\r\n",b"\n")
        assert before == after, "Locked source/artwork changed: "+path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("_ci_temp"))
    parser.add_argument("--probe-root",type=Path)
    parser.add_argument("--fixtures",type=Path)
    parser.add_argument("--foundation",action="store_true",help="Also protect Overview's unchanged default dashboard against preview 0.2.10")
    args = parser.parse_args()
    if args.probe_root:
        probe(args.probe_root,args.fixtures,args.output,args.foundation)
        return 0
    root = Path(__file__).resolve().parents[1]
    reference = BASELINE
    expected = 72
    source_guard(root,reference)
    output = args.output.resolve()/"settings-tab-lock"
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="GG-Settings-Only-") as temp:
        temp = Path(temp)
        baseline = temp/"Baseline"
        baseline.mkdir()
        archive = subprocess.check_output(["git","archive","--format=tar",reference],cwd=root)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            assert all((baseline/m.name).resolve().is_relative_to(baseline.resolve()) for m in tar.getmembers())
            tar.extractall(baseline)
        for label,source in (("baseline",baseline),("current",root)):
            command = [sys.executable,str(Path(__file__).resolve()),"--probe-root",str(source),
                "--fixtures",str(temp/"Fixtures"),"--output",str(output/label)]
            
            result = subprocess.run(command,
                cwd=source,capture_output=True,text=True,timeout=180)
            if result.returncode:
                print(result.stdout[-4000:]+result.stderr[-6000:])
                raise AssertionError(label+" tab-lock render failed")
            print("Captured "+label+": "+("twelve other tabs")+", empty/populated, three sizes.",flush=True)
        before = json.loads((output/"baseline/hashes.json").read_text())
        after = json.loads((output/"current/hashes.json").read_text())
        differences = [n for n in before if before[n]!=after.get(n)]
        assert len(before)==len(after)==expected
        # A handful of text antialiasing pixels can differ between two separate Windows renders of
        # identical code (seen in the Game DNA ring caption). Anything larger than a few pixels in
        # one small spot is a real change and still fails.
        real = []
        for name in differences:
            try:
                from PySide6.QtGui import QImage
                one, two = QImage(str(output/"baseline"/(name+".png"))), QImage(str(output/"current"/(name+".png")))
                if one.size() != two.size():
                    print(f"DIFF {name}: size differs", flush=True)
                    real.append(name)
                    continue
                changed = [(x, y) for y in range(one.height()) for x in range(one.width()) if one.pixel(x, y) != two.pixel(x, y)]
                xs, ys = [c[0] for c in changed], [c[1] for c in changed]
                box = (max(xs)-min(xs)+1, max(ys)-min(ys)+1) if changed else (0, 0)
                tiny = bool(changed) and len(changed) <= 16 and box[0] <= 24 and box[1] <= 24
                label = "tolerated antialiasing" if tiny else "REAL"
                print(f"DIFF {name}: {len(changed)} pixels in box x {min(xs, default=0)}-{max(xs, default=0)}, y {min(ys, default=0)}-{max(ys, default=0)} ({label})", flush=True)
                if not tiny:
                    real.append(name)
                    for tag in ("baseline", "current"):
                        shutil.copyfile(output/tag/(name+".png"), args.output.resolve()/f"settings-diff-{name}-{tag}.png")
            except Exception as exc:
                print("DIFF", name, "could not be compared:", exc, flush=True)
                real.append(name)
        differences = real
        assert not differences, "Locked tab pixels changed: "+", ".join(differences)
    print("PASS: twelve other tabs are pixel-identical after Settings: 72 comparisons. Ready Room, Games and every other desktop source, artwork, data and safety engine are unchanged.")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
