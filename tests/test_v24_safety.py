import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from activity_history import group_activity, session_counts, session_caption
from core import OldFile
from graveyard import build_graveyard
from ui import GameGraveApp


class GraveyardOverrideTests(unittest.TestCase):
    def test_user_never_touch_archive_can_be_manually_overridden_but_not_removed_automatically(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'skyrim-mod.zip';p.write_bytes(b'hello')
            f=OldFile(str(p),5,1)
            found=build_graveyard([],[],[f],365,never_touch=[tmp],now=365*86400+500)
            self.assertEqual(len(found),1)
            self.assertFalse(found[0].can_recycle)
            app=SimpleNamespace(settings={'never_touch':[tmp]})
            self.assertTrue(GameGraveApp._grave_can_override(app,found[0]))
            self.assertTrue(p.exists(), 'Read-only classification must not touch files')

    def test_save_or_managed_mod_archive_cannot_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            save=Path(tmp)/'Saved Games'; save.mkdir()
            p=save/'skyrim-mod.zip';p.write_bytes(b'hello')
            f=OldFile(str(p),5,1)
            found=build_graveyard([],[],[f],365,never_touch=[tmp],now=365*86400+500)
            self.assertEqual(len(found),1)
            self.assertFalse(GameGraveApp._grave_can_override(SimpleNamespace(settings={'never_touch':[tmp]}),found[0]))


class AuditTrailTests(unittest.TestCase):
    def test_sessions_expand_to_show_individual_files_and_outcomes(self):
        rows=[{'session_id':'abc','kind':'Cleanup finished', 'details':'Done'},
              {'session_id':'abc','kind':'Manual recycled','path':'C:/mods/mod1.zip'},
              {'session_id':'abc','kind':'Cleanup skipped','path':'C:/mods/save.ess'},
              {'session_id':'abc','kind':'Cleanup started','details':'Begin'},
              {'kind':'Scan completed','details':'Read only'}]
        grouped=group_activity(rows)
        self.assertEqual(len(grouped),2)
        self.assertEqual(len(grouped[0]['events']),4)
        self.assertEqual(session_counts(grouped[0]['events'])['removed'],1)
        self.assertEqual(session_counts(grouped[0]['events'])['skipped'],1)
        self.assertIn('recycled',session_caption(grouped[0]))
        self.assertFalse(grouped[1]['session'])

if __name__=='__main__':unittest.main()
