#!/bin/bash
# Install SoupaWhisper on Linux
# Supports: Ubuntu, Pop!_OS, Debian, Fedora, Arch

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/soupawhisper"
SERVICE_DIR_SYSTEM="/etc/systemd/user"
SERVICE_DIR_USER="$HOME/.config/systemd/user"

# Detect package manager
detect_package_manager() {
    if command -v apt &> /dev/null; then
        echo "apt"
    elif command -v dnf &> /dev/null; then
        echo "dnf"
    elif command -v pacman &> /dev/null; then
        echo "pacman"
    elif command -v zypper &> /dev/null; then
        echo "zypper"
    else
        echo "unknown"
    fi
}

# Detect display server
detect_session_type() {
    if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
        echo "wayland"
    elif [ "$XDG_SESSION_TYPE" = "x11" ]; then
        echo "x11"
    elif [ -n "$WAYLAND_DISPLAY" ]; then
        echo "wayland"
    else
        echo "x11"
    fi
}

# Install system dependencies
install_deps() {
    local pm=$(detect_package_manager)
    local session=$(detect_session_type)

    echo "Detected package manager: $pm"
    echo "Detected session type: $session"
    echo "Installing system dependencies..."

    if [ "$session" = "wayland" ]; then
        local clipboard_pkg="wl-clipboard"
        local type_pkg="wtype"
    else
        local clipboard_pkg="xclip"
        local type_pkg="xdotool"
    fi

    case $pm in
        apt)
            sudo apt update
            sudo apt install -y alsa-utils $clipboard_pkg $type_pkg libnotify-bin
            ;;
        dnf)
            sudo dnf install -y alsa-utils $clipboard_pkg $type_pkg libnotify
            ;;
        pacman)
            sudo pacman -S --noconfirm alsa-utils $clipboard_pkg $type_pkg libnotify
            ;;
        zypper)
            sudo zypper install -y alsa-utils $clipboard_pkg $type_pkg libnotify-tools
            ;;
        *)
            echo "Unknown package manager. Please install manually:"
            echo "  alsa-utils $clipboard_pkg $type_pkg libnotify"
            ;;
    esac
}

# Install Python dependencies
install_python() {
    echo ""
    echo "Installing Python dependencies..."

    if ! command -v poetry &> /dev/null; then
        echo "Poetry not found. Please install Poetry first:"
        echo "  curl -sSL https://install.python-poetry.org | python3 -"
        exit 1
    fi

    poetry install
}

# Setup config file
setup_config() {
    echo ""
    echo "Setting up config..."
    mkdir -p "$CONFIG_DIR"

    if [ ! -f "$CONFIG_DIR/config.ini" ]; then
        cp "$SCRIPT_DIR/config.example.ini" "$CONFIG_DIR/config.ini"
        echo "Created config at $CONFIG_DIR/config.ini"
    else
        echo "Config already exists at $CONFIG_DIR/config.ini"
    fi
}

# Generate service file content
generate_service_content() {
    local session=$(detect_session_type)
    local venv_path="$SCRIPT_DIR/.venv"

    # Check if venv exists
    if [ ! -d "$venv_path" ]; then
        venv_path=$(poetry env info --path 2>/dev/null || echo "$SCRIPT_DIR/.venv")
    fi

    # Build environment lines based on session type
    local env_lines=""
    if [ "$session" = "wayland" ]; then
        local wayland_display="${WAYLAND_DISPLAY:-wayland-0}"
        env_lines="Environment=XDG_SESSION_TYPE=wayland
Environment=WAYLAND_DISPLAY=$wayland_display
Environment=DISPLAY=${DISPLAY:-:0}"
    else
        local display="${DISPLAY:-:0}"
        local xauthority="${XAUTHORITY:-$HOME/.Xauthority}"
        env_lines="Environment=DISPLAY=$display
Environment=XAUTHORITY=$xauthority"
    fi

    cat << EOF
[Unit]
Description=SoupaWhisper Voice Dictation
After=graphical-session.target
Requisite=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$venv_path/bin/python $SCRIPT_DIR/dictate.py
Restart=on-failure
RestartSec=5

$env_lines
Environment=XDG_RUNTIME_DIR=/run/user/%U
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=graphical-session.target
EOF
}

# Install systemd service for current user only
install_service_user() {
    echo ""
    echo "Installing systemd service for current user..."

    mkdir -p "$SERVICE_DIR_USER"
    generate_service_content > "$SERVICE_DIR_USER/soupawhisper.service"
    echo "Created service at $SERVICE_DIR_USER/soupawhisper.service"

    systemctl --user daemon-reload
    systemctl --user enable soupawhisper.service

    echo ""
    echo "Service installed for current user!"
    echo "It will auto-start with your graphical session."
    echo ""
    echo "Commands:"
    echo "  systemctl --user start soupawhisper   # Start"
    echo "  systemctl --user stop soupawhisper     # Stop"
    echo "  systemctl --user status soupawhisper   # Status"
    echo "  journalctl --user -u soupawhisper -f   # Logs"
}

# Install systemd service system-wide for all users
install_service_system() {
    echo ""
    echo "Installing systemd service system-wide..."

    sudo mkdir -p "$SERVICE_DIR_SYSTEM"
    generate_service_content | sudo tee "$SERVICE_DIR_SYSTEM/soupawhisper.service" > /dev/null
    echo "Created service at $SERVICE_DIR_SYSTEM/soupawhisper.service"

    # Enable globally for all users' graphical sessions
    sudo mkdir -p "$SERVICE_DIR_SYSTEM/graphical-session.target.wants"
    sudo ln -sf ../soupawhisper.service "$SERVICE_DIR_SYSTEM/graphical-session.target.wants/soupawhisper.service"

    # Reload for the current user
    systemctl --user daemon-reload

    # Warn if install directory may not be accessible to other users
    local dir_perms
    dir_perms=$(stat -c '%a' "$SCRIPT_DIR" 2>/dev/null || echo "unknown")
    if [ "$dir_perms" != "unknown" ] && [ "${dir_perms:2:1}" -lt 5 ] 2>/dev/null; then
        echo ""
        echo "WARNING: $SCRIPT_DIR may not be accessible to other users."
        echo "  For multi-user use, ensure the install directory is world-readable:"
        echo "  chmod o+rx $SCRIPT_DIR"
    fi

    echo ""
    echo "Service installed system-wide for all users!"
    echo "It will auto-start for every user's graphical session."
    echo ""
    echo "Commands (per-user):"
    echo "  systemctl --user start soupawhisper   # Start"
    echo "  systemctl --user stop soupawhisper     # Stop"
    echo "  systemctl --user status soupawhisper   # Status"
    echo "  journalctl --user -u soupawhisper -f   # Logs"
}

# Main
main() {
    echo "==================================="
    echo "  SoupaWhisper Installer"
    echo "==================================="
    echo ""

    install_deps
    install_python
    setup_config

    echo ""
    echo "Install as systemd service?"
    echo "  1) User only (current user, no sudo)"
    echo "  2) System-wide (all users, requires sudo)"
    echo "  n) Skip"
    read -p "Choice [1/2/n]: " -r
    echo ""

    case "$REPLY" in
        1) install_service_user ;;
        2) install_service_system ;;
        *) echo "Skipping systemd service install." ;;
    esac

    echo ""
    echo "==================================="
    echo "  Installation complete!"
    echo "==================================="
    echo ""
    echo "To run manually:"
    echo "  poetry run python dictate.py"
    echo ""
    echo "Config: $CONFIG_DIR/config.ini"
    echo "Hotkey: F12 (hold to record)"
    echo "Exit:   Ctrl+C"
}

main "$@"
