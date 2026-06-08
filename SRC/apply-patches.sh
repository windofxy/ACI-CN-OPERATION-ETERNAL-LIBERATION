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

step "1/11" rpcs3 "RPCS3/tss-support.patch"       "RPCS3 TSS patch"
step "2/11" rpcs3 "RPCS3/p2ps-disconnect-fix.patch" "RPCS3 P2PS disconnect fix patch"
step "3/11" rpcs3 "RPCS3/tree-transparency.patch"   "RPCS3 tree transparency patch"
step "4/11" rpcs3 "RPCS3/np-localnetinfo-byteorder-fix.patch" "RPCS3 NP LocalNetInfo byte order fix patch"
step "5/11" rpcs3 "RPCS3/np-signaling-conninfo-disconnect.patch" "RPCS3 NP signaling GetConnectionInfo disconnect fix patch"
step "6/11" rpcs3 "RPCS3/np-disconnect-handling.patch" "RPCS3 NP disconnect handling patch (ghost-member + logging)"
step "7/11" rpcs3 "RPCS3/p2ps-disconnect-diagnostics.patch" "RPCS3 P2PS disconnect diagnostics patch (teardown coverage + logging)"
step "8/11" rpcs3 "RPCS3/rpcn-roomdata-notfound-fix.patch" "RPCS3 RPCN roomdata notfound fix patch"
step "9/11" rpcs3 "RPCS3/rpcn-reconnect.patch" "RPCS3 RPCN reconnect patch"
step "10/11" rpcs3 "RPCS3/p2ps-disconnect-deadlock-fix.patch" "RPCS3 P2PS disconnect deadlock fix patch (defer teardown out of data_mutex)"
step "11/11" rpcn  "RPCN/tss-server.patch"          "RPCN TSS server patch"

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
