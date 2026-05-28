#!/usr/bin/env bash
# Apply OEL source patches against the cloned upstream submodules.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"

echo "============================================================"
echo " ACI-RPCS3 -- Apply source patches"
echo "============================================================"
echo

step() {
    local idx="$1" repo="$2" patch="$3" label="$4"
    echo "[$idx] Applying $label..."
    if ! ( cd "$SRC/GIT/$repo" && git apply "$SRC/PATCH/$patch" ); then
        echo
        echo "ERROR: $label failed."
        echo "Make sure SRC/GIT/$repo is a clean clone with no local modifications."
        exit 1
    fi
    echo "Done."
    echo
}

step "1/4" rpcs3 "RPCS3/tss-support.patch"       "RPCS3 TSS patch"
step "2/4" rpcs3 "RPCS3/p2ps-disconnect-fix.patch" "RPCS3 P2PS disconnect fix patch"
step "3/4" rpcs3 "RPCS3/tree-transparency.patch"   "RPCS3 tree transparency patch"
step "4/4" rpcn  "RPCN/tss-server.patch"          "RPCN TSS server patch"

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
