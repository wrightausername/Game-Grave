"""M1 Windows session gate tests, using fake kernel APIs only."""
import unittest
import core


class _Kernel:
    def __init__(self, active, current, success=1):
        self.active = active
        self.current = current
        self.success = success

    def WTSGetActiveConsoleSessionId(self):
        return self.active

    def GetCurrentProcessId(self):
        return 12345

    def ProcessIdToSessionId(self, process_id, pointer):
        if process_id != 12345:
            raise AssertionError("unexpected PID")
        pointer._obj.value = self.current
        return self.success


class RecycleInteractiveSessionTests(unittest.TestCase):
    def test_matching_nonzero_console_session_allowed(self):
        self.assertTrue(core._recycle_shell_session_ready(_Kernel(2, 2)))

    def test_windows_service_session_zero_blocked(self):
        self.assertFalse(core._recycle_shell_session_ready(_Kernel(2, 0)))
        self.assertFalse(core._recycle_shell_session_ready(_Kernel(0, 0)))

    def test_disconnected_console_session_blocked(self):
        self.assertFalse(core._recycle_shell_session_ready(_Kernel(0xFFFFFFFF, 2)))

    def test_remote_or_different_session_blocked(self):
        self.assertFalse(core._recycle_shell_session_ready(_Kernel(2, 4)))

    def test_failed_process_lookup_blocked(self):
        self.assertFalse(core._recycle_shell_session_ready(_Kernel(2, 2, success=0)))


if __name__ == "__main__":
    unittest.main()
