#!/usr/bin/env bash
# First-run setup: create a Python venv with cryptography + PySide6.
set -euo pipefail
APP="$(cd "$(dirname "$0")" && pwd)"
PYDIR="$APP/python"

cat <<'EOF'
============================================================
 OP ETERNAL - First-Time Setup
 (this runs once and takes a few minutes)
============================================================

EOF

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found. Install Python 3.10 or newer:"
    echo "  Debian/Ubuntu:  sudo apt install python3 python3-venv python3-pip"
    echo "  Fedora:         sudo dnf install python3 python3-pip"
    echo "  Arch:           sudo pacman -S python python-pip"
    exit 1
fi

if [ ! -x "$PYDIR/bin/python3" ]; then
    echo "Creating Python virtual environment at $PYDIR..."
    if ! python3 -m venv "$PYDIR"; then
        echo
        echo "ERROR: venv creation failed."
        echo "On Debian/Ubuntu install python3-venv:"
        echo "  sudo apt install python3-venv"
        exit 1
    fi
fi

echo "Upgrading pip..."
"$PYDIR/bin/python3" -m pip install --quiet --upgrade pip

echo "Installing packages (cryptography + PySide6)..."
"$PYDIR/bin/python3" -m pip install --quiet cryptography PySide6-Essentials

# Dedicated interpreter copy for the game server: it gets the ports 80/443
# capability (cap_net_bind_service) so the GUI interpreter never carries it.
# cp -L resolves the venv symlink into a private real binary.
if [ ! -e "$PYDIR/bin/python3-gameserver" ]; then
    cp -L "$PYDIR/bin/python3" "$PYDIR/bin/python3-gameserver" 2>/dev/null || true
fi

echo
echo "Setup complete."
echo "============================================================"
