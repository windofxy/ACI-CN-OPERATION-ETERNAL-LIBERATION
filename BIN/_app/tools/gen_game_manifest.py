"""Generate or update data/game_manifest.json from a known-good install.

Run this once per title against a verified, fully-updated game folder (the
directory that contains PARAM.SFO and USRDIR). It records the version string,
the approximate install size and the SHA-256 of every .PAC, .edat and .BIN
file, keyed by title ID, merging into the manifest so other titles are kept.

    python tools/gen_game_manifest.py "<path-to-NPUB31347>" --region US
    python tools/gen_game_manifest.py "<path-to-NPEB01839>" --region EU
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
from modules import game_verify as gv  # noqa: E402

_DEFAULT_OUT = APP_DIR / "data" / "game_manifest.json"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game_dir", type=Path,
                    help="title folder (contains PARAM.SFO and USRDIR)")
    ap.add_argument("--title-id", default=None,
                    help="manifest key for this title (default: folder name)")
    ap.add_argument("--region", default=None, help="region label, e.g. US/EU/JP")
    ap.add_argument("--out", type=Path, default=_DEFAULT_OUT,
                    help=f"output manifest (default: {_DEFAULT_OUT})")
    args = ap.parse_args()

    game_dir = args.game_dir.resolve()
    title_id = args.title_id or game_dir.name
    param = game_dir / "PARAM.SFO"
    if not param.exists():
        sys.exit(f"No PARAM.SFO under {game_dir} - point at the title folder.")

    found = gv.read_game_version(param)
    version = gv.normalize_version(found.get("APP_VER") or found.get("VERSION") or gv.EXPECTED_VERSION)

    files: dict[str, str] = {}
    for rel, ap_path in gv.iter_game_files(game_dir):
        files[rel] = gv.hash_file(ap_path)
        print(f"  hashed {rel}")

    entry: dict = {}
    if args.region:
        entry["region"] = args.region
    entry["game_version"] = version
    entry["approx_size_bytes"] = gv.dir_size(game_dir)
    entry["files"] = files

    manifest = gv.load_manifest(args.out) if args.out.exists() else {}
    games = manifest.get("games")
    if not isinstance(games, dict):
        games = {}
    games[title_id] = entry

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"games": games}, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {title_id} to {args.out}")
    print(f"  version {version}, {len(files)} files, ~{entry['approx_size_bytes']:,} bytes")
    if version != gv.EXPECTED_VERSION:
        print(f"  WARNING: version is {version}, expected {gv.EXPECTED_VERSION} - "
              f"is this install fully updated?")


if __name__ == "__main__":
    main()
