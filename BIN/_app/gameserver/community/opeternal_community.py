"""
OPERATION ETERNAL LIBERATION community stats capture.

Optional module — present only on the -OPERATIONS- VPS. The listener imports
this with a guarded try/except; removing this file fully disables capture.

Activation: set OEL_STATS_DB=1 (or any non-empty value) in the environment.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def enabled():
    return bool(os.environ.get("OEL_STATS_DB"))


HISTORY_DAYS = int(os.environ.get("OEL_STATS_HISTORY_DAYS", "365"))

_cap = (os.environ.get("OEL_STATS_CAPTURE") or "all").strip().lower()
CAPTURE_ALL  = _cap in ("all", "")
CAPTURE_NONE = _cap == "none"
CAPTURE_ONLY = set() if (CAPTURE_ALL or CAPTURE_NONE) else {
    s.strip() for s in _cap.split(",") if s.strip()
}

DB_PATH    = Path(__file__).resolve().parent / "stats.db"
PII_FIELDS = frozenset({"mac_address", "mac_address_enc", "open_psid", "open_psid_enc"})

_lock = threading.Lock()
_OK   = (200, "application/json; charset=utf-8", b'{"result":"OK"}')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_pii(obj):
    if isinstance(obj, dict):
        return {k: _strip_pii(v) for k, v in obj.items() if k not in PII_FIELDS}
    if isinstance(obj, list):
        return [_strip_pii(i) for i in obj]
    return obj


def _connect():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _event_name(path):
    return path.rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# Schema + init
# ---------------------------------------------------------------------------

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS players (
    uid TEXT PRIMARY KEY,
    player_rank INTEGER,
    credit_gain INTEGER,
    nb_kill_air INTEGER,
    nb_kill_ground INTEGER,
    mileage INTEGER,
    coop_war_nb_win INTEGER,
    coop_war_nb_lost INTEGER,
    best_score INTEGER,
    s_rank_count INTEGER,
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS player_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    ts TEXT NOT NULL,
    player_rank INTEGER,
    credit_gain INTEGER,
    nb_kill_air INTEGER,
    nb_kill_ground INTEGER,
    mileage INTEGER,
    coop_war_nb_win INTEGER,
    coop_war_nb_lost INTEGER,
    s_rank_count INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ph_uid_ts ON player_history (uid, ts);

CREATE TABLE IF NOT EXISTS match_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    mission_name TEXT,
    mission_type INTEGER,
    user_score INTEGER,
    total_score INTEGER,
    clear_rank TEXT,
    credit_gain INTEGER,
    nb_kill_air INTEGER,
    nb_kill_ground INTEGER,
    nb_kill_player INTEGER,
    nb_death INTEGER,
    nb_crash INTEGER,
    room_id INTEGER,
    room_play_no INTEGER,
    room_members TEXT,
    received_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_mr_uid ON match_results (uid);
CREATE INDEX IF NOT EXISTS idx_mr_rcv ON match_results (received_at);

CREATE TABLE IF NOT EXISTS sorties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    aircraft_id INTEGER,
    aircraft_lv INTEGER,
    arms_id INTEGER,
    arms_lv INTEGER,
    is_host INTEGER,
    mission_name TEXT,
    mission_type INTEGER,
    room_id INTEGER,
    room_play_no INTEGER,
    received_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_so_uid_ac ON sorties (uid, aircraft_id);
CREATE INDEX IF NOT EXISTS idx_so_rcv ON sorties (received_at);

CREATE TABLE IF NOT EXISTS matchings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT,
    mode TEXT,
    matching_rate INTEGER,
    is_quick_matching INTEGER,
    regulation_id INTEGER,
    received_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ma_mode ON matchings (mode);
CREATE INDEX IF NOT EXISTS idx_ma_rcv ON matchings (received_at);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT,
    uid TEXT,
    utc_time TEXT,
    received_at TEXT,
    body_json TEXT
);
"""


def init():
    conn = _connect()
    try:
        conn.executescript(_SCHEMA)
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)
        ).strftime("%Y-%m-%dT%H:%M:%S")
        conn.execute("DELETE FROM player_history WHERE ts < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Generic events-table capture (called from typed handlers too)
# ---------------------------------------------------------------------------

def _capture_event(conn, path, uid, parsed):
    """Insert a PII-stripped body into events. Must be called inside an open conn."""
    name = _event_name(path)
    if CAPTURE_NONE:
        return
    if not CAPTURE_ALL and name not in CAPTURE_ONLY:
        return
    if not parsed:
        return
    utc_raw = parsed.get("utc_time", "")
    utc = utc_raw.get("$dt", "") if isinstance(utc_raw, dict) else str(utc_raw)
    conn.execute(
        "INSERT INTO events (endpoint, uid, utc_time, received_at, body_json) VALUES (?,?,?,?,?)",
        (path, uid, utc, _now(), json.dumps(_strip_pii(parsed), ensure_ascii=False)),
    )


# ---------------------------------------------------------------------------
# Typed handlers
# ---------------------------------------------------------------------------

def _handle_accum_data(body, path, parsed):
    if not parsed:
        return _OK
    uid = parsed.get("uid", "")
    if not uid:
        return _OK
    ad      = parsed.get("accum_data") or {}
    missions = ad.get("mission") or []
    best_score   = max((m.get("best_score", 0) for m in missions), default=0)
    s_rank_count = sum(1 for m in missions if m.get("clear_rank") == "S")
    coop   = ad.get("coop_war_record") or {}
    kill   = ad.get("nb_kill") or {}
    credit = ad.get("credit") or {}
    now    = _now()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO players
                       (uid, player_rank, credit_gain, nb_kill_air, nb_kill_ground,
                        mileage, coop_war_nb_win, coop_war_nb_lost,
                        best_score, s_rank_count, last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    uid,
                    ad.get("player_rank"),
                    credit.get("gain"),
                    kill.get("air"),
                    kill.get("ground"),
                    ad.get("mileage"),
                    coop.get("nb_win"),
                    coop.get("nb_lost"),
                    best_score,
                    s_rank_count,
                    now,
                ),
            )
            conn.execute(
                """INSERT INTO player_history
                       (uid, ts, player_rank, credit_gain, nb_kill_air, nb_kill_ground,
                        mileage, coop_war_nb_win, coop_war_nb_lost, s_rank_count)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    uid, now,
                    ad.get("player_rank"),
                    credit.get("gain"),
                    kill.get("air"),
                    kill.get("ground"),
                    ad.get("mileage"),
                    coop.get("nb_win"),
                    coop.get("nb_lost"),
                    s_rank_count,
                ),
            )
            _capture_event(conn, path, uid, parsed)
            conn.commit()
        finally:
            conn.close()
    return _OK


def _handle_ev_mission_result(body, path, parsed):
    if not parsed:
        return _OK
    uid = parsed.get("uid", "")
    if not uid:
        return _OK
    ev      = parsed.get("ev_mission_result") or {}
    mission = ev.get("mission") or {}
    kill    = ev.get("nb_kill") or {}
    members = ev.get("room_members") or []
    now     = _now()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO match_results
                       (uid, mission_name, mission_type, user_score, total_score,
                        clear_rank, credit_gain, nb_kill_air, nb_kill_ground, nb_kill_player,
                        nb_death, nb_crash, room_id, room_play_no, room_members, received_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    uid,
                    mission.get("name"),
                    mission.get("type"),
                    ev.get("user_score"),
                    ev.get("total_score"),
                    ev.get("clear_rank"),
                    ev.get("credit_gain"),
                    kill.get("air"),
                    kill.get("ground"),
                    kill.get("player"),
                    ev.get("nb_death"),
                    ev.get("nb_crash"),
                    ev.get("room_id"),
                    ev.get("room_play_no"),
                    json.dumps(members),
                    now,
                ),
            )
            _capture_event(conn, path, uid, parsed)
            conn.commit()
        finally:
            conn.close()
    return _OK


def _handle_ev_sortie(body, path, parsed):
    if not parsed:
        return _OK
    uid = parsed.get("uid", "")
    if not uid:
        return _OK
    ev      = parsed.get("ev_sortie") or {}
    mission = ev.get("mission") or {}
    now     = _now()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO sorties
                       (uid, aircraft_id, aircraft_lv, arms_id, arms_lv, is_host,
                        mission_name, mission_type, room_id, room_play_no, received_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    uid,
                    ev.get("aircraft_id"),
                    ev.get("aircraft_lv"),
                    ev.get("arms_id"),
                    ev.get("arms_lv"),
                    int(bool(ev.get("is_host"))),
                    mission.get("name"),
                    mission.get("type"),
                    ev.get("room_id"),
                    ev.get("room_play_no"),
                    now,
                ),
            )
            _capture_event(conn, path, uid, parsed)
            conn.commit()
        finally:
            conn.close()
    return _OK


def _handle_ev_matching_result(body, path, parsed):
    if not parsed:
        return _OK
    uid = parsed.get("uid", "")
    ev  = parsed.get("ev_matching_result") or {}
    sc  = ev.get("search_condition") or {}
    now = _now()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO matchings
                       (uid, mode, matching_rate, is_quick_matching, regulation_id, received_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    uid,
                    ev.get("mode"),
                    ev.get("matching_rate"),
                    int(bool(ev.get("is_quick_matching"))),
                    sc.get("regulation_id"),
                    now,
                ),
            )
            _capture_event(conn, path, uid, parsed)
            conn.commit()
        finally:
            conn.close()
    return _OK


def _handle_save_catchall(body, path, parsed):
    # Typed handlers above cover their events; this catches everything else.
    if CAPTURE_NONE:
        return _OK
    name = _event_name(path)
    if not CAPTURE_ALL and name not in CAPTURE_ONLY:
        return _OK
    if not parsed:
        return _OK
    uid = parsed.get("uid", "")
    with _lock:
        conn = _connect()
        try:
            _capture_event(conn, path, uid, parsed)
            conn.commit()
        finally:
            conn.close()
    return _OK


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def install(route_fn):
    """Register capture handlers using the listener's route decorator."""
    route_fn("/Wind/save/accum_data")(_handle_accum_data)
    route_fn("/Wind/save/ev_mission_result")(_handle_ev_mission_result)
    route_fn("/Wind/save/ev_sortie")(_handle_ev_sortie)
    route_fn("/Wind/save/ev_matching_result")(_handle_ev_matching_result)
    # Shortest prefix — lowest priority; catches all other /Wind/save/* events.
    route_fn("/Wind/save/")(_handle_save_catchall)
