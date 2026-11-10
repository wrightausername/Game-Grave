"""Time-bomb check for the unit tests.

Runs every tests/test_*.py with the clock moved by N days (time.time, datetime.now/today/utcnow, date.today).
A test that only passes today because of a fixed date fails when N is large.

    python tools/time_shift_tests.py 730      # two years ahead
    python tools/time_shift_tests.py -400     # back in time

Known false positives when N is positive: tests that create a brand new file and expect it to count as
recent (test_core file scan, test_winpc cleanup). New files are stamped by the real clock, so they look old
under a shifted one. Those are not date bombs. Modules that need tkinter or PySide6 cannot import without
them and are reported as IMPORTFAIL.
"""
import sys, os, time, datetime as dt, unittest
shift = float(sys.argv[1]) * 86400
sys.argv = [sys.argv[0]] + sys.argv[2:]
_t = time.time
time.time = lambda: _t() + shift
_dt = dt.datetime
class D(_dt):
    @classmethod
    def now(cls, tz=None):
        return _dt.now(tz) + dt.timedelta(seconds=shift)
    @classmethod
    def today(cls):
        return _dt.now() + dt.timedelta(seconds=shift)
    @classmethod
    def utcnow(cls):
        return _dt.utcnow() + dt.timedelta(seconds=shift)
dt.datetime = D
class DD(dt.date):
    @classmethod
    def today(cls):
        return (_dt.now() + dt.timedelta(seconds=shift)).date()
dt.date = DD
sys.path.insert(0, os.getcwd())
import glob, importlib
suite = unittest.TestSuite()
for f in sorted(glob.glob("tests/test_*.py")):
    name = "tests." + os.path.basename(f)[:-3]
    try:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(name)))
    except Exception as e:
        print("IMPORTFAIL", name, type(e).__name__)
r = unittest.TextTestRunner(verbosity=0).run(suite)
print("Ran", r.testsRun, "fail", len(r.failures), "err", len(r.errors))
