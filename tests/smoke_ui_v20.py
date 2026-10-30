"""Headless interactive smoke test for the Free/Pro settings screen."""
import os
import tempfile
from unittest.mock import patch
from ui import GameGraveApp

with tempfile.TemporaryDirectory() as tmp:
    os.environ['LOCALAPPDATA']=tmp
    app=GameGraveApp()
    app.withdraw()
    app.show_page('Settings')
    app.settings_tabs.select(4)
    app.update()
    assert app.edition.name == 'Free'
    assert app.license_status_var.get() == 'Free edition'
    with patch('ui.messagebox.showinfo') as info:
        app._activate_pro()
        assert 'not connected' in info.call_args.args[1]
    app.destroy()
print('Game Grave v2.0 Free/Pro GUI smoke test passed')
