"""Plain words and result colours for the More Tools windows."""
from gg_desktop import tools_words as w


def test_every_tool_has_a_plain_summary_and_tone():
    for key in ("windows_cleanup", "game_optimizer", "memory_optimizer", "command_runner", "file_associations",
                "junction_manager", "kit_menu", "hash"):
        assert w.summary(key) and w.summary(key).endswith(".")
        assert w.tone(key) in ("red", "cyan", "purple", "blue", "yellow")
        for sentence in (w.summary(key), *w.steps(key)):
            assert "—" not in sentence and "–" not in sentence
            assert "safe to" not in sentence.lower()


def test_optimizer_states_in_plain_words():
    assert w.optimizer_state("game_mode", [None]) == ("Not set, Windows decides", w.IDLE)
    assert w.optimizer_state("game_mode", [1]) == ("On", w.GOOD)
    assert w.optimizer_state("game_mode", [0]) == ("Off", w.IDLE)
    assert w.optimizer_state("background_recording", [0, 0]) == ("Off", w.GOOD)
    assert w.optimizer_state("background_recording", [1, None]) == ("On", w.IDLE)
    assert w.optimizer_state("background_recording", [0, 1]) == ("Partly off", w.IDLE)
    assert w.optimizer_state("background_recording", [None, None])[0] == "Not set, Windows decides"
    assert w.optimizer_state("power_plan", [], "Balanced", False) == ("Balanced", w.IDLE)
    assert w.optimizer_state("power_plan", [], "High performance", True) == ("High performance", w.GOOD)
    assert w.optimizer_state("power_plan", [], "Could not be read") == ("Could not be read", w.WARN)
    for key in w.OPTIMIZER_PLAIN:
        name, plain = w.optimizer_plain(key)
        assert name and plain and "\\" not in plain and "powercfg" not in plain


def test_button_counts():
    assert w.apply_label(0) == "Apply"
    assert w.apply_label(1) == "Apply 1 change"
    assert w.apply_label(3) == "Apply 3 changes"
    assert w.close_label(0) == "Close selected apps"
    assert w.close_label(1) == "Close 1 app" and w.close_label(2) == "Close 2 apps"
    assert w.plain_count(1, "link") == "1 link" and w.plain_count(1200, "file") == "1,200 files"


def test_result_tone_from_older_wording():
    cases = {
        "": w.IDLE,
        "Deleting…": w.WORKING,
        "Step 1 of 3: copying Saves": w.WORKING,
        "Deleted 1 files (100 B reported). 0 skipped because they changed, were in use or could not be removed.": w.GOOD,
        "Windows Cleanup stopped: access denied": w.BAD,
        "Tick at least one setting first.": w.WARN,
        "Type a command to run.": w.WARN,
        "Finished with exit code 0.": w.GOOD,
        "Finished with exit code 1.": w.WARN,
        "Asked 2 apps to close; 1 still running.": w.WARN,
        "Kit saved and checked: D:\\Kits\\Skyrim.zip": w.GOOD,
        "The kit was not made: disk full": w.BAD,
        "Cancelled. Nothing was kept.": w.WARN,
        "No junctions or links found there.": w.WARN,
    }
    for text, tone in cases.items():
        assert w.guess_tone(text) == tone, (text, w.guess_tone(text))
