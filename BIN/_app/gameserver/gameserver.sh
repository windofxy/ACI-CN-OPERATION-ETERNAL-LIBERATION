#!/usr/bin/env bash
# Standalone game-server launcher. Mirrors gameserver.bat for Linux/macOS.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

cat "$HERE/../assets/ascii.txt" || true
echo

PYEXE="$HERE/../python/bin/python3"
if [ ! -x "$PYEXE" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PYEXE="python3"
    else
        echo "Python not found. Run setup.sh first." >&2
        exit 1
    fi
fi

BIND_IP="${1:-0.0.0.0}"
HTTP_PORT="${2:-80}"
HTTPS_PORT="${3:-443}"

cd "$HERE"
exec "$PYEXE" opeternal_listener.py --bind-ip "$BIND_IP" --http-port "$HTTP_PORT" --https-port "$HTTPS_PORT"
