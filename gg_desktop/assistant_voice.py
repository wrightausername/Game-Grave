"""Talk to the assistant and hear it back, with what Windows and Qt already have. Nothing is downloaded or sent anywhere.

Reading aloud uses Qt's text-to-speech (Windows' own voices). Speaking a question uses Windows' built-in speech
recognition (System.Speech, the dictation recognizer that ships with Windows) in a hidden PowerShell that listens for one
sentence on the default microphone, up to 10 seconds, and prints the words. When Windows has no recognizer for the
language, it says so. While a game runs, listening is off, like the rest of the assistant's background work.
"""
from __future__ import annotations

import re
import subprocess

READ_KEY = "assistant_read_aloud"
LISTEN_SECONDS = 10

_SCRIPT = (
    "$ErrorActionPreference='Stop';"
    "Add-Type -AssemblyName System.Speech;"
    "$r=New-Object System.Speech.Recognition.SpeechRecognitionEngine;"
    "$r.SetInputToDefaultAudioDevice();"
    "$r.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar));"
    "$r.InitialSilenceTimeout=[TimeSpan]::FromSeconds(5);"
    "$r.EndSilenceTimeout=[TimeSpan]::FromSeconds(1.2);"
    "$res=$r.Recognize([TimeSpan]::FromSeconds({seconds}));"
    "if($res){{[Console]::Out.Write($res.Text)}}"
)


def clean_for_speech(text):
    """Words worth reading out: no paths, links or bracketed notes."""
    text = re.sub(r"https?://\S+", "", str(text or ""))
    text = re.sub(r"[A-Za-z]:\\\S+", "that folder", text)
    text = re.sub(r"\(Double-check:.*?\)", "", text, flags=re.S)
    return " ".join(text.split())[:1500]


def listen_command(seconds=LISTEN_SECONDS):
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
            _SCRIPT.format(seconds=int(seconds))]


def recognize(run=subprocess.run, seconds=LISTEN_SECONDS):
    """The words heard, or ("", reason). Blocks for up to `seconds` plus start-up; run it in a worker."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = run(listen_command(seconds), capture_output=True, text=True, timeout=seconds + 20, creationflags=flags)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "", f"Windows speech recognition didn't start ({exc.__class__.__name__})."
    words = (done.stdout or "").strip()
    if words:
        return words, ""
    err = (done.stderr or "").strip()
    if "recognizer" in err.casefold() or "No recognizer" in err:
        return "", "Windows has no speech recognizer installed for your language (Settings > Time & language > Speech)."
    if "audio" in err.casefold() or "device" in err.casefold():
        return "", "No microphone was found."
    return "", "I didn't catch that. Try again a little closer to the microphone."


# ------------------------------------------------------------------ Qt parts
_SPEAKER = {}


def can_speak():
    try:
        from PySide6.QtTextToSpeech import QTextToSpeech  # noqa: F401
        return True
    except Exception:
        return False


def say(window, text):
    try:
        from PySide6.QtTextToSpeech import QTextToSpeech
    except Exception:
        window.status.setText("Reading aloud isn't available on this PC.")
        return
    speaker = _SPEAKER.get(id(window))
    if speaker is None:
        speaker = QTextToSpeech(window)
        _SPEAKER[id(window)] = speaker
    speaker.stop()
    speaker.say(clean_for_speech(text))


def stop(window):
    speaker = _SPEAKER.get(id(window))
    if speaker is not None:
        speaker.stop()


def after_answer(window, text):
    if (window.settings or {}).get(READ_KEY) and can_speak():
        say(window, text)


def listen(window, box):
    """Mic button: listen once and put the words in the message box (the user presses Send)."""
    from gg_desktop import local_ai_ui
    if local_ai_ui.game_running(window):
        window.status.setText("Listening is paused while a game is running.")
        return
    window.status.setText(f"Listening… say your question (up to {LISTEN_SECONDS} seconds).")
    if hasattr(box, "setPlaceholderText"):
        box.setPlaceholderText("Listening…")

    def heard(result):
        words, why = result
        if hasattr(box, "setPlaceholderText"):
            box.setPlaceholderText("Ask anything, or tell me what to do… (Enter to send)")
        if words:
            box.setText(words)
            box.setFocus()
            window.status.setText("Heard you. Press Enter to send, or fix the words first.")
        else:
            window.status.setText(why)
    window.job(lambda _p: recognize(), heard, error_title="Listening didn't work")
