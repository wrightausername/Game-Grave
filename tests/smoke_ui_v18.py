"""Xvfb UI smoke test for shareable UI presets and arbitrary color selection."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from ui import GameGraveApp, readable_foreground
from ui_presets import read_preset_file


with tempfile.TemporaryDirectory() as temp:
    os.environ['LOCALAPPDATA'] = temp
    app = GameGraveApp()
    app.withdraw()
    app.show_page('Settings')
    app.update()
    assert len(app.settings_tabs.tabs()) == 5
    app.accent_hex_var.set('#d01277')
    app._apply_custom_accent()
    app.update()
    assert app.settings['ui_accent'] == 'custom'
    assert app.settings['ui_custom_accent'] == '#D01277'
    with patch('ui.simpledialog.askstring', return_value='My favorite purple'):
        app.settings_tabs.select(1)
        app._save_ui_preset()
    assert 'My favorite purple' in app.settings['ui_presets']
    app.settings['ui_layout'] = 'advanced'
    app._apply_ui_preset()
    app.update()
    assert app.settings['ui_layout'] == 'simple'
    app.settings_tabs.select(1)
    output = Path(temp) / 'shared.json'
    with patch('ui.filedialog.asksaveasfilename', return_value=str(output)), patch('ui.messagebox.showinfo'):
        app._export_ui_preset()
    assert output.is_file()
    name, data = read_preset_file(output)
    assert name == 'My favorite purple'
    assert data['ui_custom_accent'] == '#D01277'
    app.settings['ui_presets'] = {}
    app.show_page('Settings')
    app.settings_tabs.select(1)
    with patch('ui.filedialog.askopenfilename', return_value=str(output)), patch('ui.messagebox.askyesno', side_effect=[True, False]):
        app._import_ui_preset()
    assert 'My favorite purple' in app.settings['ui_presets']
    assert readable_foreground('#000000') == '#FFFFFF'
    assert readable_foreground('#FFFFFF') == '#071721'
    app.destroy()
    print('Game Grave v1.8 UI preset and color-picker smoke test passed')
