# External patches

This project carries seven patches against upstream source trees, applied by
`SRC\apply-patches.bat`:

- `SRC\PATCH\RPCS3\tss-support.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\p2ps-disconnect-fix.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\tree-transparency.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\np-localnetinfo-byteorder-fix.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\np-signaling-conninfo-disconnect.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\np-disconnect-handling.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCN\tss-server.patch` against [rpcn](https://github.com/RipleyTom/rpcn)

The kit modifies upstream because the game depends on
two PSN features that aren't otherwise available in an offline or community-RPCN
setup, and to work around lobby-wide freezes we observed in RPCS3's P2P
TCP-over-UDP stack whenever any player disconnected:

- **Title Small Storage (TSS).** The game is online-only and pulls server-side
  TSS blobs to complete its login phase. Without them, login fails with
  "Failed to connect to Playstation Network".
- **Title User Storage (TUS).** Saves live exclusively in the cloud. The game's
  save format is fragile, and the game has its own server-side recovery
  routines whose protocol we haven't reverse-engineered. A corrupted cloud save
  leaves the player stuck with no way to fix it. We work around that by
  mirroring every cloud-save write to local disk so the launcher can put a
  known-good copy back.
- **P2PS disconnect handling.** When any player in a lobby dropped or timed
  out, every remaining player froze. The patch changes several behaviours
  in `lv2_socket_p2ps`, `tcp_timeout_monitor`, and the signaling handler;
  with it applied, lobbies recover from disconnects.

All patches were developed against the game object of this repository. They
are not claimed to be the correct fix for every RPCS3 game, but may be
useful as a reference point.

## RPCS3: `tss-support.patch`

Modifies `rpcs3/Emu/Cell/Modules/sceNpTus.cpp` and `rpcs3/Emu/NP/np_requests.cpp`.

### TSS file serving

`sceNpTssGetData` and `sceNpTssGetDataAsync` previously returned the stub
"no file" response. The game treats this as a fatal error and login fails with
"Failed to connect to Playstation Network". The patch replaces the stubs with a
real implementation (`scenp_tss_serve_file`):

1. Read from `<config_dir>/tss/<titleId>-<slot>.tss` if present.
2. Otherwise fetch over HTTP from
   `http://<rpcn_host>:<rpcn_port + 2>/tss/<titleId>/<titleId>-<slot>.tss`
   via libcurl (`scenp_tss_fetch_from_rpcn`).
3. If neither yields a file, fall through to the original stub.

The two-source design is for decentralization. TSS files can be distributed
locally with each install, or hosted once on the community RPCN server and
fetched on demand. Neither path is privileged. Range parameters (`offset`,
`lastByte`) are honoured; `ifParam` is logged but ignored.

The PSN online check at the top of both functions was removed. TSS data here
comes from the local filesystem or RPCN, never the real PSN, so the check would
only prevent legitimate offline use.

### World list allocation fix and padding

In `np::reply_get_world_list` (`np_requests.cpp`), two changes:

- The `SceNpMatching2World` array allocation was inside an
  `if (!world_list.empty())` branch, leaving `world_info->world` as a null
  pointer when RPCN returned no worlds. The allocation is now unconditional.
- The world list is padded with `worldId = 65537` until its length is at least
  10.

The padding works around a game-side assumption: the game reads
past the end of the returned list and crashes when the list is too short. The
proper fix would be on the game side, which we can't touch. The actual
workaround lives in our fork of RPCN: `servers.cfg` registers 5 worlds for
the game's community ID (see below), which is enough to avoid the crash. The client-side
padding to 10 entries here is an additional safety net.

### TUS restore via one-shot local files

`scenp_tus_serve_restore` (called from `scenp_tus_get_data` before the normal
RPCN path) checks for a file at
`<config_dir>/tus/<commId>/<npId>/<slot20d>.tdt.restore`:

- Empty file: report `SCE_NP_COMMUNITY_SERVER_ERROR_USER_STORAGE_DATA_NOT_FOUND`,
  matching RPCN's own "no data" response. The game treats this as a fresh
  account.
- Non-empty file: serve its contents as the TUS payload.

The file is deleted after the read regardless, so the next `GetData` falls
through to RPCN normally. This is the hook the launcher's "Backup / Restore"
and "New Game" features use to take effect on the next game boot.

### Automatic TUS backup on SetData

In `np::reply_tus_set_data` (`np_requests.cpp`), the patch writes a timestamped
local copy of the outgoing TUS payload before forwarding it to RPCN:

```
<config_dir>/tus/<commId>/<npId>/backups/YYYY-MM-DD_HHMMSS_<commId>_<slot20d>.tdt
```

The game's save format is fragile and the game's own server-side recovery
routines use a protocol we haven't reverse-engineered, so a corrupted cloud
save can't be fixed through normal game flow. The local mirror is a workaround:
every cloud-save write is dumped to disk, and the launcher's restore flow
hands a known-good copy back through the one-shot file path above.

## RPCS3: `p2ps-disconnect-fix.patch`

Modifies `rpcs3/Emu/Cell/lv2/sys_net.cpp`,
`rpcs3/Emu/Cell/lv2/sys_net/lv2_socket_p2ps.cpp`,
`rpcs3/Emu/Cell/lv2/sys_net/sys_net_helpers.cpp`,
`rpcs3/Emu/NP/signaling_handler.cpp`, and `rpcs3/Emu/NP/signaling_handler.h`.

Each P2PS stream is a TCP-over-UDP connection between two peers. RPCN itself
does not relay P2PS data; it only provides STUN-like signaling on UDP 3657.
When a peer dropped or timed out, the host froze indefinitely. The sections
below describe each change.

### Wake blocked recvfrom and select on close

`lv2_socket_p2ps::close_stream_nl` now drains the socket's `queue` of
`(thread, callback)` entries and signals a read event, so threads blocked
in `recvfrom` or `select` wake on close.

### `recvfrom` on closed socket returns ECONNRESET

With the stream closed and the buffer empty, `recvfrom` returned
`{0, {}, {}}` (zero bytes), which the game retried in a tight loop. `sendto`
on a closed socket already returned `-SYS_NET_ECONNRESET`; the patch makes
`recvfrom` match.

### `poll` and `select` on closed socket

`poll()` on a closed stream now unconditionally sets `POLLHUP`; `POLLIN` is
set only if data remains buffered. `select()` on a closed stream sets
`read_set = true` so the closed fd appears readable. This matches POSIX
behaviour where errors surface through the read set.

### Signaling INACTIVE before P2PS close

Without an NP signaling `INACTIVE` event
(`SCE_NP_SIGNALING_CONN_STATUS_INACTIVE`) preceding the P2PS teardown, the
game's disconnect handler stalled. RPCN was delivering `INACTIVE` via its
own keepalive detection roughly 18 seconds after the P2PS retry-timeout
fired, and the lobby stayed stuck for that gap.

The patch adds `signaling_handler::force_disconnect_by_addr(u32 addr, u16 port)`,
which the P2PS retry-timeout path calls immediately before `close_stream()`.
The function walks `sig_peers`, matches on `si->addr` or `si->mapped_addr`
(both already in network byte order), and dispatches `INACTIVE` with
`SCE_NP_SIGNALING_ERROR_TIMEOUT`. Signaling now arrives before the P2PS
hangup.

### `tcp_timeout_monitor` self-deadlock

`tcp_timeout_monitor::operator()` holds `data_mutex` while iterating the
retry map. On max retries the chain
`close_stream()` -> `close_stream_nl()` -> `clear_all_messages()` re-entered
`data_mutex` on the same thread; with the mutex non-recursive,
`bnet_select` calls including the closed fd then hung on the socket mutex.

The patch removes `clear_all_messages` from `close_stream_nl`. Each existing
caller now cleans up explicitly:

- `tcp_timeout_monitor::operator()`: scans and erases remaining `msgs`
  entries for the closed socket inline, while `data_mutex` is still held.
- FIN/RST path in `handle_data_pkt`: calls `clear_all_messages()` directly.

### RTT estimation: Karn and RFC 6298

`confirm_data_received` averaged in measured RTT samples even when the packet
had been retransmitted; per Karn's algorithm those samples are ambiguous.
The patch ignores RTT samples from retransmitted packets and applies the
RFC 6298 `RTTVAR` update (`RTTVAR = 3/4 RTTVAR + 1/4 |SRTT - R|`, then
`SRTT = 7/8 SRTT + 1/8 R`). `rtt_time` is recomputed as
`SRTT + max(G, 4 RTTVAR)` and clamped to the existing min/max bounds.

### Diagnostic trace calls

Additional `sys_net.trace` lines in `sys_net.cpp`, `sys_net_helpers.cpp`, and
`lv2_socket_p2ps.cpp`. Gated behind the emulator's per-channel log level;
emitted only when `sys_net` is set to `Trace` in `Logger`.

## RPCS3: `tree-transparency.patch`

Modifies `rpcs3/Emu/RSX/RSXThread.cpp`.

Moves the `RSX_SHADER_CONTROL_ALPHA_TEST` assignment out of the
polygon-class branch of `prepare_fragment_program` so it also applies to
non-polygon primitive classes. Intended to address opaque-black backgrounds
on point-sprite foliage in this game. Not confirmed to be the right fix in
general; included as a workaround pending a proper investigation upstream.

## RPCS3: `np-localnetinfo-byteorder-fix.patch`

Modifies `rpcs3/Emu/Cell/Modules/sceNp.cpp` (`sceNpSignalingGetLocalNetInfo`)
and `rpcs3/Emu/Cell/Modules/sceNp2.cpp`
(`sceNpMatching2SignalingGetLocalNetInfo`).

Both functions wrote the local and mapped IP addresses into PS3 emulated memory
byte-swapped, so any title that reads its own LAN/WAN address from these APIs to
advertise itself in a room attribute handed peers a corrupted address.

### The bug

`get_local_ip_addr()` / `get_public_ip_addr()` return a `u32` already in network
byte order (the raw `sin_addr.s_addr`, whose in-memory bytes are the IP octets in
order). The destination fields are `be_t<u32>`. A plain assignment to a `be_t`
runs through `to_data()`, which byteswaps on a little-endian host; feeding an
already-network-order value through that swap reverses the octets in emulated
memory. The PS3 Cell CPU is big-endian (host order == network order), so on real
hardware the field simply holds the network-order `s_addr`; only on RPCS3's LE
host does the extra swap corrupt it. For 192.168.1.11 (`C0 A8 01 0B`) the buggy
store produced `0B 01 A8 C0`.

The fix replaces the assignment with
`std::bit_cast<be_t<u32>, u32>(...)`, which reinterprets the network-order bytes
as a `be_t` without re-swapping. This is the same idiom the working sys_net path
already uses (`sys_net_helpers.cpp`, `native_addr_to_sys_net_addr`) to place a
network-order address into a PS3 `be_t<u32>`.

```cpp
info->local_addr  = std::bit_cast<be_t<u32>, u32>(nph.get_local_ip_addr());
info->mapped_addr = std::bit_cast<be_t<u32>, u32>(nph.get_public_ip_addr());
```

The neighbouring `nat_status` / `npport` / `natStatus` fields are left untouched:
those take logical integer constants, for which plain `be_t` assignment is
already correct. This is why, in a captured affected `roomBinAttrExternal` blob,
the port (`SCE_NP_PORT`) survived while the two IPs came through reversed.

### Scope

The corruption is game-visible only and lives on the advertising side: a host
writing its own room blob. RPCN stores `roomBinAttrExternal` as an opaque byte
array and echoes it back verbatim, never parsing it as an IP, so no server change
is needed and the fix works against the existing public RPCN. A searcher reads
the raw blob bytes regardless of its own build, so there is no double-swap risk;
an unpatched host produces the same swapped blob as before, with no regression.
The one mixed-fleet wrinkle is titles that compare their own `GetLocalNetInfo`
WAN against a peer's blob WAN to detect "same public IP, use LAN address": a
patched node's correct WAN will not match an unpatched peer's swapped WAN, which
can defeat that shortcut for two players behind the same router. All-patched and
all-unpatched fleets are each internally consistent, so the patch is best rolled
out to everyone at once.

This is not a standalone fix for "players behind CG-NAT can't see each other's
rooms", which is a P2P reachability failure (symmetric NAT can't complete the UDP
hole punch) that a flat overlay network addresses. It is complementary: it stops
the title's first probe from being aimed at a byte-swapped address that on
symmetric NAT can mis-prime the NAT mapping and break the hole punch.

## RPCS3: `np-signaling-conninfo-disconnect.patch`

Modifies `rpcs3/Emu/Cell/Modules/sceNp2.cpp`
(`sceNpMatching2SignalingGetConnectionInfo`).

`p2ps-disconnect-fix.patch` marks a timed-out peer's signaling connection
`INACTIVE` but keeps its `signaling_info` (the npid->conn_id mapping and the `si`
both survive, so the peer can still recover). `SignalingGetConnectionInfo`
resolves the peer by npid and returns its connection info (RTT, address, etc.) as
long as the `si` exists - it never checks `conn_status`. So after a P2PS timeout
this getter keeps returning success with a stale "connected" address.

Static analysis of the game (NPUB31347) shows it polls this getter (with
`code = PEER_ADDRESS`) while maintaining its per-member connection state, and only
reacts to a negative return. Because RPCS3 never returns an error for a
timed-out-but-still-present peer, the game's polled view never flips the member to
"disconnected" - a plausible cause of the mid-mission host hang on a peer drop: a
game loop waiting on the peer cannot observe the disconnect through this channel.

The patch returns `SCE_NP_SIGNALING_ERROR_CONN_NOT_FOUND` when the resolved `si`
is `INACTIVE`, so a poll of a dead peer fails instead of reporting it connected,
and the title's own disconnect/error handling can run. This is a polled
(synchronous) channel, so it works even when the game is stuck in a busy loop that
is not pumping `cellSysutilCheckCallback`.

The link from this getter to the specific mission hang is inferred from static
analysis of the game binary plus reproduction logs, not yet confirmed in-game. The change is
correct on its own terms regardless - a getter should not report a
connection that signaling has already declared inactive as still live.

A [FREEZE-DIAG] D2 probe was added: edge-triggered notice per (room, member) when
the getter returns CONN_NOT_FOUND for an INACTIVE peer, and again if that member
subsequently flips back to ACTIVE (flap detection).

## RPCS3: `np-disconnect-handling.patch`

Modifies `rpcs3/Emu/NP/np_cache.cpp`, `rpcs3/Emu/NP/signaling_handler.cpp`, and
`rpcs3/Emu/Cell/Modules/sceNp.cpp`. General hardening of peer-disconnect handling;
it changes behaviour only on the disconnect paths and adds edge-triggered logging.

**Ghost room member (`np_cache.cpp` `del_member`).** The function checked that the
room existed and then ran `rooms.erase(member_id)` - erasing from the rooms map
keyed by the *member* id, which is never a valid room id, so it removed nothing
while returning success. The departed member stayed in the room's member list, so
`GetRoomMemberDataInternalList` and friends kept returning a member whose leave
callback had already fired: a room slot that stayed occupied but showed no player.
The patch erases the member from `rooms[room_id].members` and returns false when
the member was not present, which also makes the caller's leave-callback guard
idempotent (no duplicate `MemberLeft`).

**Edge-triggered disconnect logging (`signaling_handler.cpp` `update_si_status`).**
A `warning`-level line is logged on the ACTIVE/PENDING -> INACTIVE signaling
transition only (`update_si_status` already gates that branch), so a healthy
session is silent and a real peer loss logs exactly once, with conn/room/member
ids and the error code.

**Consistent connection-info getter (`sceNp.cpp`
`sceNpSignalingGetConnectionInfo`).** Like its matching2 sibling (see
`np-signaling-conninfo-disconnect.patch`), this returned stale "connected" info for
a peer whose `si` had gone INACTIVE because it never checked `conn_status`. It now
returns `SCE_NP_SIGNALING_ERROR_CONN_NOT_FOUND` for an INACTIVE peer so a title
polling it observes the drop.

Known remaining gaps: the send-failure `close_stream` coverage gap is now closed by
`p2ps-disconnect-diagnostics.patch` (the RST/FIN path is intentionally left alone there,
since it is not a real teardown route for an established peer). Still open:
`sceNpSignalingGetPeerNetInfoResult` is a stub that always returns `CELL_OK` - out of
scope for disconnect handling, since the game tracks peer liveness via
`GetConnectionInfo`, not the peer-net-info request/result flow.

Two [FREEZE-DIAG] probes were added: D2 (non-matching2 sibling, keyed by conn_id)
mirrors the matching2 D2 probe above; D3 logs once per (room, member) when
`GetRoomMemberDataInternalLocal` succeeds for a member whose signaling is INACTIVE
(confirms del_member never ran for that member -- the smoking gun for the synthesized
MemberLeft fix path).

## RPCS3: `p2ps-disconnect-diagnostics.patch`

Modifies `rpcs3/Emu/NP/signaling_handler.cpp` and
`rpcs3/Emu/Cell/lv2/sys_net/lv2_socket_p2ps.cpp`. A follow-up to
`p2ps-disconnect-fix.patch`, kept as a separate file so it can be evaluated and
dropped independently of that validated patch. It closes coverage gaps on the
peer-teardown paths and sharpens disconnect logging; it changes behaviour only on
the disconnect paths.

**Exact peer match in `force_disconnect_by_addr` (`signaling_handler.cpp`).**
`p2ps-disconnect-fix.patch` added `force_disconnect_by_addr(addr, port)` but matched
on address only and returned on the first hit, ignoring the `port` argument. Two
peers behind one public IP share an external address and differ only by port, so an
address-only match could mark the wrong peer's signaling connection INACTIVE. The
function now prefers an exact address+port match - `si->port` and the passed port
are the same representation, both `bit_cast<u16, be_t<u16>>` of the peer's UDP
endpoint, which carries signaling and P2PS together - and falls back to the first
address-only match only when no port matches, so the common single-peer case is
unchanged and a dead peer is never left connected.

**Signaling INACTIVE on the send-failure close (`lv2_socket_p2ps.cpp`).**
`p2ps-disconnect-fix.patch` drives the peer's signaling connection INACTIVE (via
`force_disconnect_by_addr`) only on the retry-cap teardown. The send-failure path -
where `tcp_timeout_monitor` resends a packet, the local `sendto` fails, and the stream
is closed - tore the stream down without notifying signaling, so the polled
connection-info getters kept reporting the peer connected until the 60s signaling
timeout. This path now calls `force_disconnect_by_addr` for the dead peer too, mirroring
the retry-cap path and running in the same lock context (the `tcp_timeout_monitor` loop
already holds its own `data_mutex`; `force_disconnect_by_addr` takes the separate
signaling `data_mutex`). The RST/FIN-receive close is deliberately left alone: RPCS3
never sends FIN and only sends RST on a backlog-full connect rejection, so that branch
is not a real teardown route for an established peer.

**Disconnect logging at warning level (`signaling_handler.cpp`).** Two disconnect
chokepoints that previously logged at `notice` (easy to miss in a shared log) now log an
enriched `warning`: the 60s no-traffic signaling timeout, and the `force_disconnect_by_addr`
match. Both are edge-triggered (once per real transition), so no per-retry or per-frame spam
is added. The shared `update_si_status` headline carries the dropped peer's **npid (player
name)** plus conn/room/member ids and the error code, and is split by reason: a graceful
teardown (`TERMINATED_BY_PEER`/`TERMINATED_BY_MYSELF`) logs at `notice` so a normal player
leaving is not reported as a fault, while an abnormal loss (timeout / link death) stays at
`warning`. The npid matters for triage: a peer that drops silently never produces a
`UserLeftRoom` (which is the only other line carrying the player name), so without it a
frozen peer is only identifiable by member id.

A [FREEZE-DIAG] D1 probe was added to `cellSysutil.cpp`
(`cellSysutilCheckCallback`): emits a notice at most once per second to confirm the
per-frame callback pump is still running during a hang.

## RPCS3: `p2ps-disconnect-deadlock-fix.patch`

Modifies `rpcs3/Emu/Cell/lv2/sys_net/lv2_socket_p2ps.cpp`. Applies after
`p2ps-disconnect-fix.patch` and `p2ps-disconnect-diagnostics.patch` (it edits the same
`tcp_timeout_monitor::operator()` teardown those add).

`tcp_timeout_monitor::operator()` holds the monitor's global `data_mutex` while iterating
the retry map. On the retry cap and on a send failure it called
`force_disconnect_by_addr` (which takes the signaling `data_mutex`, then a match2 context
mutex and the sysutil queue) and `close_stream()` (which takes the per-socket `mutex`) with
`data_mutex` still held. The packet path takes those locks in the opposite order:
`handle_connected` holds the socket `mutex` and then calls `confirm_data_received`, which
takes `data_mutex`. Because `data_mutex` is a single instance shared by every P2P socket,
any concurrent `handle_connected` (or a guest `sendto`/`recvfrom` taking a socket `mutex`)
against the retry-cap teardown is an AB/BA deadlock; the parked threads stall the frame and
callback pump.

The patch defers the teardown out of the locked region. Inside the loop it only records the
dead peer (`sock_id`, `addr`, `port`) and erases that socket's queued messages while
`data_mutex` is held; the lock is released, then `force_disconnect_by_addr` and
`close_stream()` run for each recorded peer. No path now takes a socket `mutex` while
holding `data_mutex`, so the two acquisition orders can no longer cross. The send-failure
case also gains the signaling `INACTIVE` dispatch that previously only the retry cap had.

Credit: [VF0S-D](https://github.com/VF0S-D)

## rpcn: `tss-server.patch`

Modifies `src/server.rs` and `servers.cfg`, and adds `src/server/tss_server.rs`.

### TSS HTTP server module

The new file `src/server/tss_server.rs` defines a small `hyper`-based HTTP
server bound to `<host>:<rpcn_port + 2>` (same offset convention as the stat
server, which uses `port + 1`). It serves:

```
GET /tss/<com_id>/<filename>
```

from `tss_data/<com_id>/` on disk. Path-traversal characters (`..`, `/`, `\`)
in either segment return 400. Missing files return 404. Non-GET methods return
405. Started from `Server::start_tss_server`, called between the UDP and stat
servers in `Server::start`. Uses the existing `TerminateWatch` channel for
shutdown.

### `servers.cfg` entries

Five lines added for the game's community ID, registering worlds 1 through 5 each at
`worldId = 65537`. These satisfy the game's matchmaking world-list request.
Combined with the RPCS3-side padding above, the game sees the minimum list
length it expects.

## Applying and resetting

```
SRC\apply-patches.bat
```

Runs `git apply` against both submodules. Fails if either working tree isn't
clean.

```
SRC\reset-git-repos.bat
```

Runs `git reset --hard HEAD` and `git clean -ffdx` on both submodules,
restoring them to the pinned commits and removing patch-introduced files
(including the new `tss_server.rs`).
