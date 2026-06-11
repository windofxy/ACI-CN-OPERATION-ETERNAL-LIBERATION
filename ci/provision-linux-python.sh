#!/usr/bin/env bash
# Provision the bundled Python runtime for the Linux client package.
# Linux analogue of setup.bat's embeddable-Python download: a standalone
# CPython (no system dependencies) with the launcher's packages preinstalled,
# placed at BIN/_app/python so launcher.py and Play (Linux).sh find it.
#
# Usage: provision-linux-python.sh [target-dir]   (default BIN/_app/python)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-$ROOT/BIN/_app/python}"

PBS_TAG="20260610"
PBS_BUILD="cpython-3.12.13+${PBS_TAG}-x86_64-unknown-linux-gnu-install_only_stripped"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${PBS_BUILD}.tar.gz"
PBS_SHA256="6682afef6b510037a0ad84e61150e5121af2e2785c9ca27b047e029270a840fe"

if [ -x "$TARGET/bin/python3" ]; then
    echo "Bundled Python already present at $TARGET"
else
    echo "Downloading $PBS_BUILD..."
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    curl -fsSL "$PBS_URL" -o "$TMP/python.tar.gz"
    echo "$PBS_SHA256  $TMP/python.tar.gz" | sha256sum -c -

    echo "Extracting to $TARGET..."
    rm -rf "$TARGET"
    mkdir -p "$(dirname "$TARGET")"
    # Extract in place (tarball top-level dir is "python"); avoids a
    # cross-device mv, which breaks on case-insensitive filesystems.
    tar -xzf "$TMP/python.tar.gz" -C "$(dirname "$TARGET")"
    if [ "$(basename "$TARGET")" != "python" ]; then
        mv "$(dirname "$TARGET")/python" "$TARGET"
    fi
fi

echo "Installing packages (cryptography + PySide6)..."
"$TARGET/bin/python3" -m pip install --quiet --no-warn-script-location \
    cryptography PySide6-Essentials

# Dedicated interpreter copy for the game server: users grant it
# cap_net_bind_service (ports 80/443) at install time, so the capability
# never applies to the GUI interpreter. Real copy, not a hardlink: file
# capabilities sit on the inode.
cp -L "$TARGET/bin/python3" "$TARGET/bin/python3-gameserver"

"$TARGET/bin/python3" -c "import PySide6.QtCore, cryptography; print('Bundled Python OK:', __import__('sys').version.split()[0])"
