#!/usr/bin/env bash
# Apply OEL source patches against the cloned upstream submodules.
# The ordered patch list is SRC/PATCH/series -- the single source of truth.
# Add, remove, reorder, or disable a patch by editing that file.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
SERIES="$SRC/PATCH/series"

[ -f "$SERIES" ] || { echo "ERROR: missing $SERIES" >&2; exit 1; }

echo "============================================================"
echo " ACI-RPCS3 -- Apply source patches"
echo "============================================================"
echo

# Read the series into an ordered list of patch paths (relative to SRC/PATCH/).
# Strip CR (the file can check out CRLF on a /mnt/c WSL mount), skip blank lines
# and '#' comments, and keep only the first whitespace-delimited token (so a
# trailing "# comment" after the path is ignored).
patches=()
while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    read -r tok _ <<<"$line"
    case "$tok" in ''|\#*) continue ;; esac
    patches+=("$tok")
done < "$SERIES"

total=${#patches[@]}
[ "$total" -gt 0 ] || { echo "ERROR: no patches listed in $SERIES" >&2; exit 1; }

idx=0
for rel in "${patches[@]}"; do
    idx=$((idx + 1))
    # Target tree = first path component, lowercased (RPCS3 -> rpcs3, RPCN -> rpcn).
    repo="${rel%%/*}"
    repo="$(printf '%s' "$repo" | tr '[:upper:]' '[:lower:]')"
    echo "[$idx/$total] Applying $rel..."
    if ! ( cd "$SRC/GIT/$repo" && git apply "$SRC/PATCH/$rel" ); then
        echo
        echo "ERROR: failed to apply $rel."
        echo "Make sure SRC/GIT/$repo is a clean clone with no local modifications."
        exit 1
    fi
    echo "Done."
    echo
done

cat <<'EOF'
============================================================
 All patches applied successfully.

 Next steps:
   RPCS3: Follow SRC/GIT/rpcs3/BUILDING.md for the Linux build
          (cmake + ninja). Deploy the rpcs3 binary plus any
          shared libs into BIN/_app/RPCS3/.

   RPCN:  cd SRC/GIT/rpcn
          cargo build --release
          Copy target/release/rpcn into BIN/_app/rpcn/.
============================================================
EOF
