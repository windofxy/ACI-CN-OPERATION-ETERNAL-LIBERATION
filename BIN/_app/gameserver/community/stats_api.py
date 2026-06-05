"""
OPERATION ETERNAL LIBERATION community leaderboard API.

Standalone stdlib HTTP server — run separately from the listener, e.g.:
    python stats_api.py

Reads stats.db written by opeternal_community.py (WAL, safe for concurrent
reads while the listener writes). Protected by a static bearer token.

Config via .env file (same directory) or environment variables:
    OEL_API_TOKEN  — required; shared secret for Authorization: Bearer
    OEL_API_DB     — path to stats.db (default: sibling stats.db)
    OEL_API_BIND   — bind address (default: 0.0.0.0)
    OEL_API_PORT   — port (default: 8088)
"""

import argparse
import hmac
import http.server
import json
import os
import sqlite3
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# .env loader (no pip deps)
# ---------------------------------------------------------------------------

def _load_env(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if key and key not in os.environ:
            os.environ[key] = val


_load_env(HERE / ".env")

_TOKEN  = os.environ.get("OEL_API_TOKEN", "")
_DB     = Path(os.environ.get("OEL_API_DB", str(HERE / "stats.db")))
_BIND   = os.environ.get("OEL_API_BIND", "0.0.0.0")
_PORT   = int(os.environ.get("OEL_API_PORT", "8088"))


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def _db():
    """Open a read-only WAL-safe connection."""
    if not _DB.exists():
        return None
    conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn, sql, params=()):
    if conn is None:
        return []
    cur = conn.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------

_WEEKEND_DAYS = {5, 6}  # Saturday=5, Sunday=6


def _since_for_window(window: str, since_param: str) -> str | None:
    """Return ISO timestamp string for the start of the requested window, or None for 'all'."""
    if since_param:
        return since_param
    now = datetime.now(timezone.utc)
    if window == "week":
        return (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    if window == "weekend":
        # last Saturday 00:00 UTC
        days_since_sat = (now.weekday() - 5) % 7
        start = (now - timedelta(days=days_since_sat)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return start.strftime("%Y-%m-%dT%H:%M:%S")
    if window == "month":
        return (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    return None  # "all"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _check_auth(headers) -> bool:
    auth = headers.get("Authorization") or headers.get("X-Api-Token") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    else:
        token = auth.strip()
    return hmac.compare_digest(token, _TOKEN)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _json_response(obj, status=200):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return status, "application/json; charset=utf-8", body


_CORS = {"Access-Control-Allow-Origin": "*"}


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def _handle_leaderboard(qs):
    window   = (qs.get("window") or ["all"])[0]
    since_p  = (qs.get("since") or [""])[0]
    since    = _since_for_window(window, since_p)

    conn = _db()
    try:
        if since:
            top_air = _rows(conn,
                "SELECT uid, SUM(nb_kill_air) v FROM match_results "
                "WHERE received_at>=? GROUP BY uid ORDER BY v DESC LIMIT 10", (since,))
            top_gnd = _rows(conn,
                "SELECT uid, SUM(nb_kill_ground) v FROM match_results "
                "WHERE received_at>=? GROUP BY uid ORDER BY v DESC LIMIT 10", (since,))
            top_score = _rows(conn,
                "SELECT uid, MAX(user_score) v FROM match_results "
                "WHERE received_at>=? GROUP BY uid ORDER BY v DESC LIMIT 10", (since,))
        else:
            top_air = _rows(conn,
                "SELECT uid, SUM(nb_kill_air) v FROM match_results "
                "GROUP BY uid ORDER BY v DESC LIMIT 10")
            top_gnd = _rows(conn,
                "SELECT uid, SUM(nb_kill_ground) v FROM match_results "
                "GROUP BY uid ORDER BY v DESC LIMIT 10")
            top_score = _rows(conn,
                "SELECT uid, MAX(user_score) v FROM match_results "
                "GROUP BY uid ORDER BY v DESC LIMIT 10")

        top_credits  = _rows(conn,
            "SELECT uid, credit_gain v FROM players ORDER BY v DESC LIMIT 10")
        most_s_ranks = _rows(conn,
            "SELECT uid, s_rank_count v FROM players ORDER BY v DESC LIMIT 10")
        best_winrate = _rows(conn,
            "SELECT uid, "
            "  CAST(coop_war_nb_win AS REAL) / MAX(coop_war_nb_win + coop_war_nb_lost, 1) v, "
            "  coop_war_nb_win wins, coop_war_nb_lost losses "
            "FROM players WHERE coop_war_nb_win + coop_war_nb_lost > 0 "
            "ORDER BY v DESC LIMIT 10")
    finally:
        if conn:
            conn.close()

    return _json_response({
        "window": window,
        "since": since,
        "top_air_kills":    top_air,
        "top_ground_kills": top_gnd,
        "top_score":        top_score,
        "top_credits":      top_credits,
        "most_s_ranks":     most_s_ranks,
        "best_coop_winrate": best_winrate,
    })


def _handle_aircraft(qs):
    window  = (qs.get("window") or ["all"])[0]
    since_p = (qs.get("since") or [""])[0]
    uid_p   = (qs.get("uid") or [""])[0]
    since   = _since_for_window(window, since_p)

    conn = _db()
    try:
        if since and uid_p:
            rows = _rows(conn,
                "SELECT uid, aircraft_id, COUNT(*) n FROM sorties "
                "WHERE received_at>=? AND uid=? GROUP BY uid, aircraft_id ORDER BY n DESC",
                (since, uid_p))
        elif since:
            rows = _rows(conn,
                "SELECT uid, aircraft_id, COUNT(*) n FROM sorties "
                "WHERE received_at>=? GROUP BY uid, aircraft_id ORDER BY n DESC LIMIT 100",
                (since,))
        elif uid_p:
            rows = _rows(conn,
                "SELECT uid, aircraft_id, COUNT(*) n FROM sorties "
                "WHERE uid=? GROUP BY uid, aircraft_id ORDER BY n DESC", (uid_p,))
        else:
            rows = _rows(conn,
                "SELECT uid, aircraft_id, COUNT(*) n FROM sorties "
                "GROUP BY uid, aircraft_id ORDER BY n DESC LIMIT 100")
    finally:
        if conn:
            conn.close()

    return _json_response({"window": window, "since": since, "aircraft": rows})


def _handle_modes(qs):
    window  = (qs.get("window") or ["all"])[0]
    since_p = (qs.get("since") or [""])[0]
    since   = _since_for_window(window, since_p)

    conn = _db()
    try:
        if since:
            rows = _rows(conn,
                "SELECT mode, COUNT(*) plays FROM matchings "
                "WHERE received_at>=? GROUP BY mode ORDER BY plays DESC", (since,))
        else:
            rows = _rows(conn,
                "SELECT mode, COUNT(*) plays FROM matchings "
                "GROUP BY mode ORDER BY plays DESC")
    finally:
        if conn:
            conn.close()

    return _json_response({"window": window, "since": since, "modes": rows})


def _handle_player(uid):
    conn = _db()
    try:
        career = _rows(conn, "SELECT * FROM players WHERE uid=?", (uid,))
        matches = _rows(conn,
            "SELECT * FROM match_results WHERE uid=? ORDER BY received_at DESC LIMIT 10",
            (uid,))
    finally:
        if conn:
            conn.close()

    for m in matches:
        try:
            m["room_members"] = json.loads(m.get("room_members") or "[]")
        except (ValueError, TypeError):
            m["room_members"] = []

    return _json_response({
        "player": career[0] if career else None,
        "recent_matches": matches,
    })


def _handle_player_history(uid, qs):
    days = int((qs.get("days") or ["365"])[0])
    since = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).strftime("%Y-%m-%dT%H:%M:%S")

    conn = _db()
    try:
        rows = _rows(conn,
            "SELECT * FROM player_history WHERE uid=? AND ts>=? ORDER BY ts",
            (uid, since))
    finally:
        if conn:
            conn.close()

    return _json_response({"uid": uid, "days": days, "history": rows})


def _handle_matches(qs):
    conn = _db()
    try:
        rows = _rows(conn,
            "SELECT * FROM match_results ORDER BY received_at DESC LIMIT 50")
    finally:
        if conn:
            conn.close()

    for m in rows:
        try:
            m["room_members"] = json.loads(m.get("room_members") or "[]")
        except (ValueError, TypeError):
            m["room_members"] = []

    return _json_response({"matches": rows})


def _handle_events(qs):
    event = (qs.get("event") or [""])[0]
    limit = min(int((qs.get("limit") or ["50"])[0]), 500)

    conn = _db()
    try:
        if event:
            rows = _rows(conn,
                "SELECT * FROM events WHERE endpoint LIKE ? ORDER BY received_at DESC LIMIT ?",
                (f"%/{event}", limit))
        else:
            rows = _rows(conn,
                "SELECT * FROM events ORDER BY received_at DESC LIMIT ?", (limit,))
    finally:
        if conn:
            conn.close()

    return _json_response({"events": rows})


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class StatsHandler(http.server.BaseHTTPRequestHandler):
    server_version = "OELStats/1.0"

    def log_message(self, fmt, *args):
        return

    def _send(self, status, ctype, body, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        for k, v in (_CORS | (extra_headers or {})).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, "text/plain", b"", {
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, X-Api-Token",
        })

    def do_GET(self):
        if not _check_auth(self.headers):
            status, ctype, body = _json_response({"error": "unauthorized"}, 401)
            self._send(status, ctype, body)
            return

        parsed  = urlsplit(self.path)
        path    = parsed.path.rstrip("/") or "/"
        qs      = parse_qs(parsed.query)

        try:
            status, ctype, body = self._dispatch(path, qs)
        except Exception:
            traceback.print_exc()
            status, ctype, body = _json_response({"error": "internal server error"}, 500)

        self._send(status, ctype, body)

    def _dispatch(self, path, qs):
        if path == "/oel-api/health":
            return _json_response({"ok": True})
        if path == "/oel-api/leaderboard":
            return _handle_leaderboard(qs)
        if path == "/oel-api/aircraft":
            return _handle_aircraft(qs)
        if path == "/oel-api/modes":
            return _handle_modes(qs)
        if path == "/oel-api/matches":
            return _handle_matches(qs)
        if path == "/oel-api/events":
            return _handle_events(qs)
        if path.startswith("/oel-api/player/"):
            rest = path[len("/oel-api/player/"):]
            if rest.endswith("/history"):
                uid = rest[: -len("/history")]
                return _handle_player_history(uid, qs)
            return _handle_player(rest)
        return _json_response({"error": "not found"}, 404)


class _ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="OEL community leaderboard API")
    parser.add_argument("--bind",  default=_BIND)
    parser.add_argument("--port",  type=int, default=_PORT)
    args = parser.parse_args()

    if not _TOKEN:
        sys.exit(
            "[stats_api] OEL_API_TOKEN is not set.\n"
            "Add it to BIN/_app/gameserver/.env and restart."
        )

    addr = (args.bind, args.port)
    srv = _ThreadingHTTPServer(addr, StatsHandler)
    print(f"[stats_api] listening on {args.bind}:{args.port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("[stats_api] shutting down", flush=True)


if __name__ == "__main__":
    main()
