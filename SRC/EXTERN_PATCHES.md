# External patches

This project carries nine patches against upstream source trees, applied by
`SRC\apply-patches.bat`:

- `SRC\PATCH\RPCS3\tss-support.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\tree-transparency.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\np-localnetinfo-byteorder-fix.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\p2ps-disconnect-fix.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\np-freeze-tracer.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\lv2-cond-tracer.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\framelimit-lock.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
- `SRC\PATCH\RPCS3\rpcn-disconnect-fix.patch` against [RPCS3](https://github.com/RPCS3/rpcs3)
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

## RPCS3: `p2ps-disconnect-fix.patch`

Modifies `rpcs3/Emu/Cell/lv2/sys_net/lv2_socket_p2ps.cpp`,
`rpcs3/Emu/NP/signaling_handler.cpp`, `rpcs3/Emu/NP/signaling_handler.h`,
`rpcs3/Emu/NP/np_cache.cpp`, `rpcs3/Emu/Cell/Modules/sceNp.cpp`, and
`rpcs3/Emu/Cell/Modules/sceNp2.cpp`.

Each P2PS stream is a TCP-over-UDP connection between two peers; RPCN provides
only the signaling, never relaying the data. When a player stopped responding,
RPCS3's P2PS layer used to let the whole lobby hang. This patch detects the
timeout and queues a forced disconnect on the client side, so the dropped player
is cleaned up locally and the remaining players keep playing.

What it changes:

- A dead stream is reported to the game instead of hidden. A read on a closed
  stream returns `ECONNRESET`, a read or `select` blocked at close time is woken,
  and `poll` reports `POLLHUP`, so a game loop waiting on the dropped peer stops
  waiting instead of spinning on a zero-length read.
- The signaling status getters (`sceNpMatching2SignalingGetConnectionInfo` and
  `sceNpSignalingGetConnectionInfo`) report a timed-out peer as gone rather than
  still connected, so a title that polls them observes the drop.
- The retry path uses RFC 6298 round-trip estimation with exponential backoff and
  a retry cap; on timeout it hands the dead endpoint to the signaling thread,
  which marks the peer inactive and closes the local stream.
- The room cache drops a departed member correctly, so a left player no longer
  lingers as an empty occupied slot.

An earlier attempt at this disconnect handling introduced a lock-order deadlock:
callbacks and packets were dispatched while the signaling handler held its state
lock, so a peer teardown could cross with a concurrent socket operation taking
the same locks the other way. This patch handles the disconnect in a thread-safe
manner: the handler records callbacks and packets while the lock is held and runs
them after releasing it, and the timeout monitor hands the disconnect to the
signaling thread rather than reaching into that lock itself, so neither side
holds one domain's lock while taking the other's.

## RPCS3: `np-freeze-tracer.patch`

Adds `rpcs3/Emu/NP/freeze_tracer.h` and probes in `signaling_handler.cpp`,
`lv2_socket_p2ps.cpp`, `sceNp.cpp`, `sceNp2.cpp`, and `cellSysutil.cpp`.

Pure-observation diagnostics for the lobby-disconnect freeze. Every probe is a single
relaxed atomic counter bump; nothing changes control flow, locking, timing, or return
values, so the build stays functionally identical to the one without it. It exists to
make a recurrence self-describing from the log instead of needing a live repro.

What it records:

- Two heartbeats: one bumped at the top of the signaling handler loop, one in
  `cellSysutilCheckCallback` (the game's callback pump). The P2PS `tcp_timeout_monitor`,
  which never takes the signaling state lock, reads both and logs an edge-triggered
  `[freeze-tracer]` warning when either stops advancing for a few seconds, plus a second
  warning when it resumes. A stalled pump with a live signaling thread and a stalled
  signaling thread point at different causes.
- Enqueue/deliver counters for the Dead and Established signaling callbacks (enqueued
  under the state lock, delivered after it is released). When signaling stalls, the
  monitor logs the four counters once; enqueued greater than delivered indicates the
  callback pump is wedged rather than the signaling thread.
- Per-second call-rate logging for the three connection-info / room-member getters, so a
  title busy-polling a peer we report as gone is distinguishable from a blocked wait.

All logging is rate-limited or edge-triggered, so a healthy session stays quiet. The
counters live in one header included by each touched translation unit.

## RPCS3: `lv2-cond-tracer.patch`

Adds cond-variable tracing in `rpcs3/Emu/Cell/lv2/sys_cond.cpp`, a trigger in
`lv2_socket_p2ps.cpp`, and an arming flag in `rpcs3/Emu/NP/freeze_tracer.h`.

A follow-on to `np-freeze-tracer.patch`, kept separate so it can be dropped on its own.
Also pure observation, and inert in normal play: it does nothing until the freeze-tracer
stale-watcher detects the signaling thread has stopped making progress.

When that happens the P2PS monitor arms a flag and takes a read-only snapshot of every PPU
thread parked on an lv2 condition variable (walked through `idm` under its own read lock),
logging each one with its cond id and game instruction address; it repeats the snapshot
about ten seconds later, so a thread sitting on the same cond at the same address in both
snapshots is genuinely stuck rather than mid-handoff. While the flag is armed, the three
`sys_cond` signal syscalls log the cond id, the signaling thread, and its instruction
address, which records who would have released each wait. The flag is cleared when progress
resumes. With the flag clear the only cost in those syscalls is one relaxed atomic-flag
read, so a healthy session is unaffected.

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

## RPCS3: `rpcn-disconnect-fix.patch`

Modifies `rpcs3/Emu/NP/np_cache.cpp`, `rpcs3/Emu/NP/np_cache.h`,
`rpcs3/Emu/NP/np_handler.cpp`, `rpcs3/Emu/NP/rpcn_client.cpp`,
`rpcs3/Emu/NP/rpcn_client.h`, and `rpcs3/Emu/NP/np_requests.cpp`.

Two RPCN-link recovery changes, both contributed by VF0S-D and previously
carried as separate patches (`rpcn-reconnect.patch` and
`rpcn-roomdata-notfound-fix.patch`).

### Auto-reconnect after a dropped RPCN link

Adds an auto-reconnect loop in `np_handler::operator()` (the RPCN polling
thread). When `is_psn_active` is set but `rpcn->is_connected()` is false after
authentication has been established, the loop waits a short grace period then
calls `rpcn->prepare_reconnect()` on the existing client object and
re-runs `wait_for_connection()` / `wait_for_authentified()` / `get_addr_sig()`
with progressive backoff. A new `prepare_reconnect()` method on `rpcn_client`
(and its declaration in the header) resets the client's socket/SSL state and
clears the sticky error flag so those entry points re-execute their login path
rather than returning the cached failure. A new `cache_manager::has_active_rooms()`
helper (and its declaration in `np_cache.h`) lets the loop distinguish
single-player from in-room play and apply different patience: single-player
retries quietly indefinitely; in-room play retries for up to 5 minutes before
going offline.

Reported symptom: RPCN link drops after approximately 10 minutes under some
VPN configurations (issue #8). Hardened before landing: the original
`rpcn.reset()` / `rpcn_client::get_instance()` recreation (a weak_ptr
resurrection race) was replaced with the in-place `prepare_reconnect()` call.
The root cause of the link drop (why UDP traffic
stops ~10 min into a session under some VPN setups) has not been identified;
this works around it at the reconnect layer. Tested by the contributor on
their VPN setup; not reproduced or validated independently in-house.

### Room-data NotFound after a disconnect

Maps `rpcn::ErrorType::NotFound` to `SCE_NP_MATCHING2_SERVER_ERROR_NO_SUCH_ROOM`
in four matching2 room reply handlers: `reply_set_roomdata_external`,
`reply_get_roomdata_internal`, `reply_set_roomdata_internal`, and
`reply_send_room_message`. Each already handles `rpcn::ErrorType::RoomMissing`
with the same mapping; previously `NotFound` fell through to
`fmt::throw_exception`, a fatal emulator stop.

After a player disconnects, the server removes their room, so the game's
end-of-match room-data calls (the results/reward screen) receive `NotFound`
and crash. Returning a normal `NO_SUCH_ROOM` lets the game handle the missing
room gracefully and continue to its progression save instead of crashing.
Symptom: disconnected players crash on the reward screen and lose progression;
with the patch they save normally. Contributed by VF0S-D (contributor-tested;
exact game-side handling not reverse-engineered).

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
