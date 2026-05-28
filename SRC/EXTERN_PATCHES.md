# External patches

This project carries four patches against upstream source trees, applied by
`SRC\apply-patches.bat`:

- `SRC\PATCH\RPCS3\tss-support.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\p2ps-disconnect-fix.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\tree-transparency.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
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
