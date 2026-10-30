"""Headless UI validation for user-facing v2.1 Save Vault, sort and status strip."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from save_discovery import SaveLocation
from core import SteamGame, ModFolder
from ui import GameGraveApp

with tempfile.TemporaryDirectory() as tmp:
    os.environ['LOCALAPPDATA'] = tmp
    app = GameGraveApp()
    app.withdraw()
    assert 'Save Vault' in app.nav_buttons  # simple mode must expose it
    assert app.scan_progress_text.get() == 'Ready to scan'
    path = str(Path(tmp) / 'Saved Games' / 'Example')
    Path(path).mkdir(parents=True)
    app.save_findings = [SaveLocation('Example', path, 'Game saves', 'Test fixture')]
    app.show_page('Save Vault')
    app.update()
    assert len(app.saves_tree.get_children()) == 1
    app.saves_tree.selection_set('0')
    app._protect_selected_saves()
    assert path in app.settings['never_touch']
    with patch('ui.messagebox.askyesno', return_value=True):
        app._review_selected_saves()
    assert path in app.settings['save_review_paths']
    assert path not in app.settings['never_touch']
    g1 = SteamGame('100', 'Zeta', tmp, tmp, 100, 1000, 'Steam')
    g2 = SteamGame('200', 'Alpha', tmp, tmp, 200, 2000, 'Steam')
    app.games = [g1, g2]
    app.show_page('Steam Games')
    app._game_column_sort('Name A-Z', 'Name Z-A')
    names = [app.game_tree.item(k, 'values')[0] for k in app.game_tree.get_children()]
    assert names == ['Alpha', 'Zeta'], names
    app._game_column_sort('Name A-Z', 'Name Z-A')
    names = [app.game_tree.item(k, 'values')[0] for k in app.game_tree.get_children()]
    assert names == ['Zeta', 'Alpha'], names
    modpath = str(Path(tmp) / 'some-mods')
    Path(modpath).mkdir()
    app.mod_folders = [ModFolder('Active Mod', modpath, 'Steam game folder', 'Installed: possible mods', (), 50, 1, False)]
    app.show_page('Game Mods')
    app.mod_tree.selection_set('0')
    with patch('ui.messagebox.showinfo'):
        app._send_mod_to_graveyard()
    assert modpath in app.settings['graveyard_watchlist']
    assert any(entry.path == modpath and not entry.can_recycle for entry in app.graveyard_entries)
    app.destroy()
print('Game Grave v2.1 UI smoke checks passed')
