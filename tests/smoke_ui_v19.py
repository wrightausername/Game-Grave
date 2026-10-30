"""Virtual desktop smoke coverage: small, simple v1.9 review paths only."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from core import ModFolder, OldFile, SteamGame
from ui import GameGraveApp

with tempfile.TemporaryDirectory() as temp:
    os.environ['LOCALAPPDATA'] = temp
    p = Path(temp) / 'skyrim-mod.7z'
    p.write_bytes(b'safe dummy data')
    app = GameGraveApp()
    app.withdraw()
    app.settings['scan_folder'] = temp
    app.games = [SteamGame('345', 'Skyrim', temp, str(Path(temp) / 'SteamGame'), 2_000_000,
                           1234567890., 'Steam local record')]
    folder = Path(temp) / 'MO2' / 'profiles'
    folder.mkdir(parents=True)
    app.mod_folders = [ModFolder('profiles', str(folder), temp, 'Managed profile',
                     ('profile',), 512, 1, False, 'Mod Organizer 2', 'Review in manager')]
    app.old_files = [OldFile(str(p), p.stat().st_size, p.stat().st_mtime)]
    app.last_scan = '12:00 PM'
    app.show_page('Make Room')
    app.update()
    assert app.goal_gb.get() == 100
    assert app.room_drive.get()
    app.goal_gb.set(50)
    app._render_room_plan()
    app.update()
    assert app.plan_body.winfo_children()
    app.show_page('Game Mods')
    app.update()
    app.mod_tree.selection_set(app.mod_tree.get_children()[0])
    with patch('ui.messagebox.showinfo') as message:
        app._detect_selected_mod()
        assert 'Mod or addon storage found' in message.call_args.args[1]
        assert 'Keep profiles' in message.call_args.args[1]
    app.show_page('The Graveyard')
    app.update()
    app.destroy()
print('Game Grave v1.9 File Detective / Make Room GUI smoke test passed')
