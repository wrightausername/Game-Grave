"""Manual headless Tk smoke test (run using xvfb). Not a substitute for Windows QA."""
import os
import tempfile
from pathlib import Path
from ui import GameGraveApp
from unittest.mock import patch
from core import SteamGame, OldFile, ModFolder
import time

with tempfile.TemporaryDirectory() as tmp:
    os.environ['LOCALAPPDATA']=tmp
    app=GameGraveApp()
    app.withdraw()
    now=time.time()
    p=Path(tmp)/'old-skyrim-mod.zip'
    p.write_text('not a mod')
    app.old_files=[OldFile(str(p), 12*1024**2, now-1000*86400)]
    app.games=[SteamGame('1','Example old game','lib','C:/games/example',10*1024**3,now-900*86400,'Steam')]
    for name in ('Steam Games','Game Mods','Old Files','The Graveyard','Settings'):
        app.show_page(name)
        app.update()
        print('opened', name)
    app.show_page('The Graveyard')
    app.update()
    assert len(app.graveyard_lookup)==2
    app.grave_status_var.set('Reviewable archives')
    app._grave_view_changed()
    app.update()
    assert len(app.graveyard_lookup)==1
    app.grave_sort_var.set('Age')
    app.grave_order_var.set('Ascending')
    app._grave_view_changed()
    app.update()
    assert app.settings['graveyard_sort']=='Age'
    assert app.settings['graveyard_status']=='Reviewable archives'
    assert os.path.isfile(os.path.join(tmp, 'Game Grave', 'settings.json'))
    with patch('ui.simpledialog.askstring', return_value='Old mods'):
        app._grave_save_view()
    assert 'Old mods' in app.settings['graveyard_saved_views']
    app.grave_order_var.set('Descending')
    app._grave_view_changed()
    app.grave_preset_var.set('Old mods')
    app._grave_load_view()
    app.update()
    assert app.grave_order_var.get() == 'Ascending'
    assert app.grave_preset_var.get() == 'Old mods'
    app._grave_column_sort('Age')
    assert app.grave_order_var.get() == 'Descending'
    assert p.exists(), 'view controls must never delete files'
    app.destroy()
    print('all UI smoke checks passed')
