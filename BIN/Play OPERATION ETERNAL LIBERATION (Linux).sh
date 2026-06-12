#!/usr/bin/env bash
# Launches the OEL launcher. Triggers first-run setup if needed.
set -euo pipefail
cd "$(dirname "$0")"

PY_BIN="_app/python/bin"

if [ ! -x "$PY_BIN/python3" ]; then
    bash "_app/setup.sh"
    if [ ! -x "$PY_BIN/python3" ]; then
        echo "Setup failed. See above for details." >&2
        exit 1
    fi
fi

# The game server runs from its own interpreter copy so the ports 80/443
# capability (granted by the user, on the command the launcher shows) never
# applies to the GUI interpreter.
if [ ! -e "$PY_BIN/python3-gameserver" ]; then
    cp -L "$PY_BIN/python3" "$PY_BIN/python3-gameserver" 2>/dev/null || true
fi

rc=0
"$PY_BIN/python3" "_app/launcher.py" "$@" || rc=$?
if [ "$rc" -ne 0 ]; then
    echo
    echo "If the error above mentions a Qt platform plugin, install the X11 client libraries:"
    echo "  Debian/Ubuntu:  sudo apt install libxcb-cursor0 libxkbcommon-x11-0"
    echo "  Fedora:         sudo dnf install xcb-util-cursor libxkbcommon-x11"
    echo "  Arch:           sudo pacman -S xcb-util-cursor libxkbcommon-x11"
fi
exit "$rc"
