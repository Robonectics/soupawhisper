# SoupaWhisper

A simple push-to-talk voice dictation tool for Linux using faster-whisper. Hold a key to record, release to transcribe, and it automatically copies to clipboard and types into the active input.

## Requirements

- Python 3.10+
- Poetry
- Linux with X11 or Wayland (ALSA audio)

## Supported Distros

- Ubuntu / Pop!_OS / Debian (apt)
- Fedora (dnf)
- Arch Linux (pacman)
- openSUSE (zypper)

## Installation

```bash
git clone https://github.com/Robonectics/soupawhisper.git
cd soupawhisper
chmod +x install.sh
./install.sh
```

The installer will:
1. Detect your package manager
2. Install system dependencies
3. Set up the config file
4. Copy runtime files to `/opt/soupawhisper/` with a self-contained venv
5. Optionally install as a systemd service

After installation, the source repo can be safely removed — the service runs entirely from `/opt/soupawhisper/`.

### Manual Installation

**X11:**
```bash
# Ubuntu/Debian
sudo apt install alsa-utils xclip xdotool libnotify-bin

# Fedora
sudo dnf install alsa-utils xclip xdotool libnotify

# Arch
sudo pacman -S alsa-utils xclip xdotool libnotify
```

**Wayland:**
```bash
# Ubuntu/Debian
sudo apt install alsa-utils wl-clipboard wtype libnotify-bin

# Fedora
sudo dnf install alsa-utils wl-clipboard wtype libnotify

# Arch
sudo pacman -S alsa-utils wl-clipboard wtype libnotify
```

```bash
# Then install Python deps and copy runtime to /opt/soupawhisper
sudo mkdir -p /opt/soupawhisper
sudo cp dictate.py config.example.ini pyproject.toml poetry.lock /opt/soupawhisper/
sudo chown -R $USER:$USER /opt/soupawhisper
cd /opt/soupawhisper && poetry install
sudo chown -R root:root /opt/soupawhisper
```

### GPU Support (Optional)

For NVIDIA GPU acceleration, install cuDNN 9:

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install libcudnn9-cuda-12
```

Then edit `~/.config/soupawhisper/config.ini`:
```ini
device = cuda
compute_type = float16
```

## Usage

```bash
/opt/soupawhisper/.venv/bin/python /opt/soupawhisper/dictate.py
```

- Hold **F12** to record
- Release to transcribe → copies to clipboard and types into active input
- Press **Ctrl+C** to quit (when running manually)

## Run as a systemd Service

The installer can set this up automatically. When prompted, choose:

- **Option 1 — User only**: Installs to `~/.config/systemd/user/` (no sudo needed). The service runs for the current user only.
- **Option 2 — System-wide**: Installs to `/etc/systemd/user/` (requires sudo). The service auto-starts for all users' graphical sessions.

If you skipped it during install, run `./install.sh` again and select an option.

### Service Commands

```bash
systemctl --user start soupawhisper     # Start
systemctl --user stop soupawhisper      # Stop
systemctl --user restart soupawhisper   # Restart
systemctl --user status soupawhisper    # Status
journalctl --user -u soupawhisper -f    # View logs
```

## Configuration

Edit `~/.config/soupawhisper/config.ini`:

```ini
[whisper]
# Model size: tiny.en, base.en, small.en, medium.en, large-v3
model = base.en

# Device: cpu or cuda (cuda requires cuDNN)
device = cpu

# Compute type: int8 for CPU, float16 for GPU
compute_type = int8

[hotkey]
# Key to hold for recording: f12, scroll_lock, pause, etc.
key = f12

[behavior]
# Type text into active input field
auto_type = true

# Show desktop notification
notifications = true
```

Create the config directory and file if it doesn't exist:
```bash
mkdir -p ~/.config/soupawhisper
cp /opt/soupawhisper/config.example.ini ~/.config/soupawhisper/config.ini
```

## Troubleshooting

**No audio recording:**
```bash
# Check your input device
arecord -l

# Test recording
arecord -d 3 test.wav && aplay test.wav
```

**Permission issues with keyboard:**
```bash
sudo usermod -aG input $USER
# Then log out and back in
```

**cuDNN errors with GPU:**
```
Unable to load any of {libcudnn_ops.so.9...}
```
Install cuDNN 9 (see GPU Support section above) or switch to CPU mode.

## Model Sizes

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| tiny.en | ~75MB | Fastest | Basic |
| base.en | ~150MB | Fast | Good |
| small.en | ~500MB | Medium | Better |
| medium.en | ~1.5GB | Slower | Great |
| large-v3 | ~3GB | Slowest | Best |

For dictation, `base.en` or `small.en` is usually the sweet spot.
