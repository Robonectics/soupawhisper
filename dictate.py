#!/usr/bin/env python3
"""
SoupaWhisper - Voice dictation tool using faster-whisper.
Hold the hotkey to record, release to transcribe and copy to clipboard.
"""

import argparse
import configparser
import subprocess
import tempfile
import threading
import selectors
import signal
import sys
import os
from pathlib import Path

import evdev
from evdev import ecodes
from faster_whisper import WhisperModel

__version__ = "0.1.0"


def detect_session_type():
    """Detect whether the session is Wayland or X11."""
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session in ("wayland", "x11"):
        return session
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "x11"  # default fallback


SESSION_TYPE = detect_session_type()

# Load configuration
CONFIG_PATH = Path.home() / ".config" / "soupawhisper" / "config.ini"


def load_config():
    config = configparser.ConfigParser()

    # Defaults
    defaults = {
        "model": "base.en",
        "device": "cpu",
        "compute_type": "int8",
        "key": "f12",
        "auto_type": "true",
        "notifications": "true",
    }

    if CONFIG_PATH.exists():
        config.read(CONFIG_PATH)

    return {
        "model": config.get("whisper", "model", fallback=defaults["model"]),
        "device": config.get("whisper", "device", fallback=defaults["device"]),
        "compute_type": config.get("whisper", "compute_type", fallback=defaults["compute_type"]),
        "key": config.get("hotkey", "key", fallback=defaults["key"]),
        "auto_type": config.getboolean("behavior", "auto_type", fallback=True),
        "notifications": config.getboolean("behavior", "notifications", fallback=True),
    }


CONFIG = load_config()


def get_hotkey(key_name):
    """Map key name to evdev key code."""
    key_name = key_name.lower()
    # Map common names to evdev key constants
    evdev_name = f"KEY_{key_name.upper()}"
    code = ecodes.ecodes.get(evdev_name)
    if code is not None:
        return code
    print(f"Unknown key: {key_name}, defaulting to f12")
    return ecodes.KEY_F12


def find_keyboards():
    """Find all keyboard input devices."""
    keyboards = []
    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        caps = dev.capabilities(verbose=False)
        # Check if device has EV_KEY and has typical keyboard keys
        if ecodes.EV_KEY in caps:
            keys = caps[ecodes.EV_KEY]
            if ecodes.KEY_A in keys and HOTKEY in keys:
                keyboards.append(dev)
    return keyboards


HOTKEY = get_hotkey(CONFIG["key"])
MODEL_SIZE = CONFIG["model"]
DEVICE = CONFIG["device"]
COMPUTE_TYPE = CONFIG["compute_type"]
AUTO_TYPE = CONFIG["auto_type"]
NOTIFICATIONS = CONFIG["notifications"]


class Dictation:
    def __init__(self):
        self.recording = False
        self.record_process = None
        self.temp_file = None
        self.model = None
        self.model_loaded = threading.Event()
        self.model_error = None
        self.running = True

        # Load model in background
        print(f"Loading Whisper model ({MODEL_SIZE})...")
        threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self):
        try:
            self.model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
            self.model_loaded.set()
            print(f"Model loaded. Ready for dictation!")
            print(f"Hold [{CONFIG['key'].upper()}] to record, release to transcribe.")
            print("Press Ctrl+C to quit.")
        except Exception as e:
            self.model_error = str(e)
            self.model_loaded.set()
            print(f"Failed to load model: {e}")
            if "cudnn" in str(e).lower() or "cuda" in str(e).lower():
                print("Hint: Try setting device = cpu in your config, or install cuDNN.")

    def notify(self, title, message, icon="dialog-information", timeout=2000):
        """Send a desktop notification."""
        if not NOTIFICATIONS:
            return
        subprocess.run(
            [
                "notify-send",
                "-a", "SoupaWhisper",
                "-i", icon,
                "-t", str(timeout),
                "-h", "string:x-canonical-private-synchronous:soupawhisper",
                title,
                message
            ],
            capture_output=True
        )

    def start_recording(self):
        if self.recording or self.model_error:
            return

        self.recording = True
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self.temp_file.close()

        # Record using arecord (ALSA) - works on most Linux systems
        self.record_process = subprocess.Popen(
            [
                "arecord",
                "-f", "S16_LE",  # Format: 16-bit little-endian
                "-r", "16000",   # Sample rate: 16kHz (what Whisper expects)
                "-c", "1",       # Mono
                "-t", "wav",
                self.temp_file.name
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print("Recording...")
        self.notify("Recording...", f"Release {CONFIG['key'].upper()} when done", "audio-input-microphone", 30000)

    def stop_recording(self):
        if not self.recording:
            return

        self.recording = False

        if self.record_process:
            self.record_process.terminate()
            self.record_process.wait()
            self.record_process = None

        print("Transcribing...")
        self.notify("Transcribing...", "Processing your speech", "emblem-synchronizing", 30000)

        # Wait for model if not loaded yet
        self.model_loaded.wait()

        if self.model_error:
            print(f"Cannot transcribe: model failed to load")
            self.notify("Error", "Model failed to load", "dialog-error", 3000)
            return

        # Transcribe
        try:
            segments, info = self.model.transcribe(
                self.temp_file.name,
                beam_size=5,
                vad_filter=True,
            )

            text = " ".join(segment.text.strip() for segment in segments)

            if text:
                # Copy to clipboard
                if SESSION_TYPE == "wayland":
                    process = subprocess.Popen(
                        ["wl-copy"],
                        stdin=subprocess.PIPE
                    )
                else:
                    process = subprocess.Popen(
                        ["xclip", "-selection", "clipboard"],
                        stdin=subprocess.PIPE
                    )
                process.communicate(input=text.encode())

                # Type it into the active input field
                if AUTO_TYPE:
                    if SESSION_TYPE == "wayland":
                        subprocess.run(["wtype", text])
                    else:
                        subprocess.run(["xdotool", "type", "--clearmodifiers", text])

                print(f"Copied: {text}")
                self.notify("Copied!", text[:100] + ("..." if len(text) > 100 else ""), "emblem-ok-symbolic", 3000)
            else:
                print("No speech detected")
                self.notify("No speech detected", "Try speaking louder", "dialog-warning", 2000)

        except Exception as e:
            print(f"Error: {e}")
            self.notify("Error", str(e)[:50], "dialog-error", 3000)
        finally:
            # Cleanup temp file
            if self.temp_file and os.path.exists(self.temp_file.name):
                os.unlink(self.temp_file.name)

    def stop(self):
        print("\nExiting...")
        self.running = False
        os._exit(0)

    def run(self):
        keyboards = find_keyboards()
        if not keyboards:
            print("No keyboard devices found. Check /dev/input permissions (need 'input' group).")
            sys.exit(1)

        print(f"Listening on: {', '.join(dev.name for dev in keyboards)}")

        # Use selectors to monitor multiple keyboards
        sel = selectors.DefaultSelector()
        for dev in keyboards:
            sel.register(dev, selectors.EVENT_READ)

        while self.running:
            for key, mask in sel.select(timeout=1):
                dev = key.fileobj
                try:
                    for event in dev.read():
                        if event.type == ecodes.EV_KEY and event.code == HOTKEY:
                            if event.value == 1:  # key down
                                self.start_recording()
                            elif event.value == 0:  # key up
                                self.stop_recording()
                except OSError:
                    pass  # device disconnected


def check_dependencies():
    """Check that required system commands are available."""
    missing = []

    if subprocess.run(["which", "arecord"], capture_output=True).returncode != 0:
        missing.append(("arecord", "alsa-utils"))

    if SESSION_TYPE == "wayland":
        if subprocess.run(["which", "wl-copy"], capture_output=True).returncode != 0:
            missing.append(("wl-copy", "wl-clipboard"))
        if AUTO_TYPE:
            if subprocess.run(["which", "wtype"], capture_output=True).returncode != 0:
                missing.append(("wtype", "wtype"))
    else:
        if subprocess.run(["which", "xclip"], capture_output=True).returncode != 0:
            missing.append(("xclip", "xclip"))
        if AUTO_TYPE:
            if subprocess.run(["which", "xdotool"], capture_output=True).returncode != 0:
                missing.append(("xdotool", "xdotool"))

    if missing:
        print(f"Missing dependencies (session: {SESSION_TYPE}):")
        for cmd, pkg in missing:
            print(f"  {cmd} - install with: sudo apt install {pkg}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="SoupaWhisper - Push-to-talk voice dictation"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"SoupaWhisper {__version__}"
    )
    parser.parse_args()

    print(f"SoupaWhisper v{__version__}")
    print(f"Session: {SESSION_TYPE}")
    print(f"Config: {CONFIG_PATH}")

    check_dependencies()

    dictation = Dictation()

    # Handle Ctrl+C gracefully
    def handle_sigint(sig, frame):
        dictation.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    dictation.run()


if __name__ == "__main__":
    main()
