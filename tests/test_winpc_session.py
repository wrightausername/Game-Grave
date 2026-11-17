"""The process list keeps apps in Game Grave's own session, whatever Windows calls it (Remote Desktop included)."""
import unittest
from types import SimpleNamespace

from gg_desktop import winpc

ROWS = ('"GameGrave.exe","100","RDP-Tcp#0","2","50,000 K"\r\n'
        '"Skyrim.exe","200","RDP-Tcp#0","2","2,000,000 K"\r\n'
        '"svchost.exe","300","Services","0","9,000 K"\r\n'
        '"Other.exe","400","Console","1","8,000 K"\r\n')


class Runner:
    def run(self, args, **_):
        return SimpleNamespace(code=0, output=ROWS)


class SessionTests(unittest.TestCase):
    def test_remote_desktop_session_is_used(self):
        names = [p.name for p in winpc.list_processes(Runner(), own_pid=100)]
        self.assertEqual(names, ["Skyrim.exe"])

    def test_console_when_own_process_is_not_listed(self):
        names = [p.name for p in winpc.list_processes(Runner(), own_pid=999)]
        self.assertEqual(names, ["Other.exe"])


if __name__ == "__main__":
    unittest.main()
