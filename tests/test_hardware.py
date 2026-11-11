import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from gg_desktop import hardware_core as hw

GB = 1024 ** 3
SAMPLE = {
    "cpu": [{"Name": "AMD Ryzen 5 5600X 6-Core Processor  ", "NumberOfCores": 6, "NumberOfLogicalProcessors": 12,
             "MaxClockSpeed": 3701, "SocketDesignation": "AM4"}],
    "gpu": [{"Name": "Microsoft Basic Display Adapter"},
            {"Name": "NVIDIA GeForce RTX 3060 Ti", "DriverVersion": "32.0.15.6636", "CurrentHorizontalResolution": 2560,
             "CurrentVerticalResolution": 1440, "CurrentRefreshRate": 144}],
    "mem": [{"Capacity": 16 * GB, "Speed": 3200, "ConfiguredClockSpeed": 2133, "SMBIOSMemoryType": 26}] * 2,
    "slots": 4,
    "board": {"Manufacturer": "Micro-Star International", "Product": "B550 TOMAHAWK"},
    "bios": {"SMBIOSBIOSVersion": "7C91v1E"},
    "os": {"Caption": "Microsoft Windows 11 Pro", "Version": "10.0.22631"},
    "disks": [{"DeviceId": "0", "FriendlyName": "Samsung SSD 970 EVO", "MediaType": "SSD", "BusType": "NVMe", "Size": 1000 * GB},
              {"DeviceId": "1", "FriendlyName": "WDC WD20EZAZ", "MediaType": "HDD", "BusType": "SATA", "Size": 2000 * GB}],
    "parts": [{"DriveLetter": "C", "DiskNumber": 0}, {"DriveLetter": "D", "DiskNumber": 1}],
    "vols": [{"DeviceID": "C:", "VolumeName": "", "Size": 1000 * GB, "FreeSpace": 412 * GB},
             {"DeviceID": "D:", "VolumeName": "Games", "Size": 2000 * GB, "FreeSpace": 1100 * GB}],
}


def specs():
    return hw.parse_specs(json.dumps(SAMPLE))


def session(vram=None, total=8192, ram=18.0, cpu_avg=40.0, cpu_peak=70.0, gpu_avg=88.0, ram_total=32.0, start=1000.0):
    return hw.Session(start, 1800, 900, cpu_avg, cpu_peak, gpu_avg if vram else None, 99.0 if vram else None, ram, ram_total,
                      vram, total if vram else None)


class Parse(unittest.TestCase):
    def test_parts(self):
        s = specs()
        self.assertEqual((s.cpu.name, s.cpu.cores, s.cpu.threads, s.cpu.base_ghz), ("AMD Ryzen 5 5600X 6-Core Processor", 6, 12, 3.7))
        self.assertEqual([g.name for g in s.gpus], ["NVIDIA GeForce RTX 3060 Ti"], "the basic adapter is skipped")
        self.assertEqual(s.display, "2560 x 1440 at 144 Hz")
        self.assertEqual((s.memory.total_gb, s.memory.sticks, s.memory.slots, s.memory.kind, s.memory.rated_mts,
                          s.memory.running_mts), (32.0, 2, 4, "DDR4", 3200, 2133))
        self.assertEqual(s.board, "Micro-Star International B550 TOMAHAWK")
        self.assertEqual([(d.letter, d.kind) for d in s.drives], [("C", "NVMe"), ("D", "hard drive")])

    def test_junk_is_harmless(self):
        for bad in ("", "not json", "[]", "null", '{"cpu": "x", "mem": 5, "vols": [1, 2]}'):
            result = hw.parse_specs(bad)
            self.assertIsNone(result.cpu)
            self.assertEqual(result.drives, ())

    def test_single_objects_work_like_lists(self):
        data = dict(SAMPLE, cpu=SAMPLE["cpu"][0], vols=SAMPLE["vols"][0])
        s = hw.parse_specs(json.dumps(data))
        self.assertEqual(s.cpu.cores, 6)
        self.assertEqual(len(s.drives), 1)

    def test_unknown_drive_kind_is_not_guessed(self):
        data = dict(SAMPLE, disks=[], parts=[])
        self.assertEqual({d.kind for d in hw.parse_specs(json.dumps(data)).drives}, {"unknown"})

    def test_spec_sheet_has_only_read_facts(self):
        text = hw.spec_sheet(specs())
        for line in ("CPU: AMD Ryzen 5 5600X", "GPU: NVIDIA GeForce RTX 3060 Ti, driver 32.0.15.6636", "Drive D:", "Display: 2560 x 1440"):
            self.assertIn(line, text)


class Live(unittest.TestCase):
    def test_nvidia(self):
        gpu = hw.parse_nvidia("NVIDIA GeForce RTX 3060 Ti, 61, 5120, 8192, 71\n")
        self.assertEqual((gpu.load, gpu.mem_used_mb, gpu.mem_total_mb, gpu.temp_c), (61.0, 5120.0, 8192.0, 71.0))
        odd = hw.parse_nvidia("Card, [N/A], [N/A], 4096, [N/A]")
        self.assertEqual((odd.load, odd.mem_used_mb, odd.mem_total_mb), (None, None, 4096.0))
        self.assertIsNone(hw.parse_nvidia(""))
        self.assertIsNone(hw.parse_nvidia("a, b"))

    def test_sampler_cpu_needs_two_readings(self):
        ticks = iter([(100, 1000), (150, 1100), (150, 1200)])
        s = hw.Sampler(cpu_times=lambda: next(ticks), memory=lambda: (9.5, 32.0), gpu=lambda: None, clock=lambda: 7.0)
        first, second, third = s.sample(), s.sample(), s.sample()
        self.assertIsNone(first.cpu)
        self.assertEqual(round(second.cpu), 50)   # 50 idle of 100 ticks
        self.assertEqual(round(third.cpu), 100)   # no idle at all
        self.assertEqual((first.mem_used_gb, first.mem_total_gb, first.gpu, first.when), (9.5, 32.0, None, 7.0))

    def test_failing_sources_never_raise(self):
        def boom():
            raise RuntimeError("no")
        live = hw.Sampler(cpu_times=boom, memory=boom, gpu=boom).sample()
        self.assertEqual((live.cpu, live.mem_used_gb, live.gpu), (None, None, None))


class Sessions(unittest.TestCase):
    def reading(self, cpu, ram, load=None, used=None, total=8192.0):
        gpu = hw.GpuLive("NVIDIA", load, used, total, 60.0) if load is not None else None
        return hw.Live(0.0, cpu, ram, 32.0, gpu)

    def test_summary_and_short_recordings(self):
        rows = [self.reading(20, 10, 50, 4000), self.reading(60, 18, 90, 7900), self.reading(None, 12)]
        got = hw.summarize(rows, 1000.0, 1000.0 + 600)
        self.assertEqual((got.seconds, got.samples, got.cpu_peak, got.ram_peak_gb, got.vram_peak_mb, got.gpu_peak),
                         (600, 3, 60, 18, 7900, 90))
        self.assertEqual(got.cpu_avg, 40)
        self.assertIsNone(hw.summarize(rows, 0.0, hw.MIN_SESSION_SECONDS - 1))
        self.assertIsNone(hw.summarize([], 0.0, 9999.0))

    def test_no_gpu_means_no_gpu_numbers(self):
        got = hw.summarize([self.reading(20, 10)], 0.0, 600.0)
        self.assertEqual((got.gpu_avg, got.gpu_peak, got.vram_peak_mb), (None, None, None))

    def test_store_round_trip_and_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(hw.load_sessions(root), [])
            for i in range(hw.KEEP_SESSIONS + 5):
                hw.save_session(session(vram=7000, start=1000.0 + i), root)
            kept = hw.load_sessions(root)
            self.assertEqual(len(kept), hw.KEEP_SESSIONS)
            self.assertEqual(kept[-1].started, 1000.0 + hw.KEEP_SESSIONS + 4)
            hw.clear_sessions(root)
            self.assertEqual(hw.load_sessions(root), [])

    def test_bad_files_and_entries_are_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = hw.sessions_path(root)
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual(hw.load_sessions(root), [])
            good = {n: None for n in hw.Session.__dataclass_fields__}
            good.update(started=5, seconds=900, samples=10, ram_peak_gb=4)
            bad = dict(good, seconds=5)
            negative = dict(good, ram_peak_gb=-1)
            path.write_text(json.dumps([good, bad, negative, "x", None]), encoding="utf-8")
            self.assertEqual(len(hw.load_sessions(root)), 1)


class Advice(unittest.TestCase):
    def notes(self, sessions, games=(), s=None):
        return {n.key: n for n in hw.advise(s or specs(), list(sessions), list(games))}

    def test_no_sessions_means_no_claims(self):
        n = self.notes([])
        for key in ("gpu", "memory", "cpu"):
            self.assertEqual(n[key].tag, "NEEDS SESSIONS", key)
        self.assertEqual(n["gpu"].tone, "muted")

    def test_two_sessions_are_still_not_evidence(self):
        n = self.notes([session(vram=8000), session(vram=8000)])
        self.assertEqual(n["gpu"].tag, "NEEDS SESSIONS")
        self.assertIn("1 more", n["gpu"].points[0])

    def test_gpu_signal_uses_the_numbers(self):
        sessions = [session(vram=7900), session(vram=7950), session(vram=7000), session(vram=5000)]
        note = self.notes(sessions)["gpu"]
        self.assertEqual((note.tag, note.tone), ("STRONGEST SIGNAL", "red"))
        self.assertIn("2 of 4 sessions", note.points[0])
        self.assertIn("7.8 GB of 8 GB", note.points[0])
        self.assertIn("88%", note.points[1])
        low = self.notes([session(vram=4000)] * 3)["gpu"]
        self.assertEqual(low.tag, "NO SIGN OF A LIMIT")

    def test_non_nvidia_sessions_are_not_judged(self):
        note = self.notes([session()] * 4)["gpu"]
        self.assertEqual(note.tag, "CANNOT BE READ")

    def test_memory_and_cpu(self):
        calm = self.notes([session(ram=18.4, cpu_avg=40, cpu_peak=71)] * 3)
        self.assertEqual(calm["memory"].tag, "NOT NEEDED YET")
        self.assertIn("18.4 GB of 32 GB", calm["memory"].points[0])
        self.assertEqual(calm["cpu"].tag, "NO SIGN OF A LIMIT")
        tight = self.notes([session(ram=30.5, cpu_avg=92, cpu_peak=99)] * 3)
        self.assertEqual((tight["memory"].tag, tight["cpu"].tag), ("WORTH A LOOK", "WORTH A LOOK"))

    def test_memory_profile_fact_comes_from_reported_speeds(self):
        self.assertTrue(any("2133 MT/s" in p and "3200 MT/s" in p for p in self.notes([])["memory"].points))
        data = json.loads(json.dumps(SAMPLE))
        for stick in data["mem"]:
            stick["ConfiguredClockSpeed"] = 3200
        fine = self.notes([], s=hw.parse_specs(json.dumps(data)))["memory"]
        self.assertFalse(any("MT/s" in p for p in fine.points))

    def game(self, letter, gb):
        return SimpleNamespace(install_path=f"{letter}:\\Games\\X", size_bytes=None if gb is None else gb * GB)

    def test_storage_found_from_install_folders(self):
        note = self.notes([], [self.game("D", 100), self.game("D", 112), self.game("C", 50)])["storage"]
        self.assertEqual((note.tag, note.tone), ("NO PURCHASE NEEDED", "green"))
        self.assertIn("212 GB", note.points[0])
        self.assertEqual(note.action, ("Open More Tools", "More Tools"))
        tight = self.notes([], [self.game("D", 500)])["storage"]
        self.assertEqual(tight.tag, "WORTH A LOOK", "412 GB free on the fast drive is not enough for 500 GB")
        none = self.notes([], [self.game("C", 50)])["storage"]
        self.assertEqual(none.tag, "NOTHING TO MOVE")

    def test_unknown_sizes_are_counted_not_summed(self):
        note = self.notes([], [self.game("D", 100), self.game("D", None)])["storage"]
        self.assertTrue(any("no known size" in p for p in note.points))

    def test_power_is_never_judged(self):
        note = self.notes([session(vram=8000)] * 5)["power"]
        self.assertEqual(note.tag, "CANNOT BE READ")

    def test_no_forbidden_claims_anywhere(self):
        cases = [[], [session(vram=8100)] * 4, [session()] * 4, [session(ram=31, cpu_avg=95)] * 4]
        for sessions in cases:
            for note in hw.advise(specs(), sessions, [self.game("D", 100)]):
                text = " ".join((note.title, note.tag, note.summary, note.limit) + note.points).casefold()
                for banned in ("safe to", "fps", "frame rate will", "guarantee", "freed", "$"):
                    self.assertNotIn(banned, text, note.key)


class Helpers(unittest.TestCase):
    def test_short_time(self):
        self.assertEqual(hw.short_time(125), "2 min 05 s")
        self.assertEqual(hw.short_time(3725), "1 h 02 min")


if __name__ == "__main__":
    unittest.main()


class WindowsGpuCounters(unittest.TestCase):
    A = "luid_0x00000000_0x0000d2e5"
    B = "luid_0x00000000_0x0000aaaa"

    def test_load_is_the_sum_of_one_cards_3d_rows(self):
        engine = [(f"pid_10_{self.A}_phys_0_eng_0_engtype_3D", 31.5), (f"pid_22_{self.A}_phys_0_eng_0_engtype_3D", 12.0),
                  (f"pid_22_{self.A}_phys_0_eng_3_engtype_VideoDecode", 80.0), (f"pid_9_{self.B}_phys_0_eng_0_engtype_3D", 2.0)]
        memory = [(f"{self.A}_phys_0", 3 * 1024 ** 3), (f"{self.B}_phys_0", 200 * 1024 ** 2)]
        load, used = hw.combine_gpu_counters(engine, memory)
        self.assertAlmostEqual(load, 43.5)
        self.assertAlmostEqual(used, 3 * 1024)

    def test_clamped_idle_and_unreadable(self):
        self.assertEqual(hw.combine_gpu_counters([(f"pid_1_{self.A}_eng_0_engtype_3D", 250.0)], [])[0], 100.0)
        self.assertEqual(hw.combine_gpu_counters([], []), (None, None))
        self.assertEqual(hw.combine_gpu_counters([("junk", 5.0), (f"x_{self.A}_engtype_3D", float("nan"))], None), (None, None))
        idle = hw.combine_gpu_counters([(f"p_{self.A}_engtype_3D", 0.0), (f"p_{self.B}_engtype_3D", 0.0)],
                                       [(f"{self.A}_phys_0", 10 * 1024 ** 2), (f"{self.B}_phys_0", 900 * 1024 ** 2)])
        self.assertEqual(idle[0], 0.0)
        self.assertAlmostEqual(idle[1], 900.0, msg="With no load anywhere, the card holding the most memory is shown")

    def test_reading_has_no_name_total_or_temperature(self):
        live = hw.query_windows_gpu(lambda: (12.0, 512.0))
        self.assertEqual((live.load, live.mem_used_mb, live.mem_total_mb, live.temp_c), (12.0, 512.0, None, None))
        self.assertIsNone(hw.query_windows_gpu(lambda: None))
        self.assertIsNone(hw.WindowsGpuCounters().read() if __import__("os").name != "nt" else None)
