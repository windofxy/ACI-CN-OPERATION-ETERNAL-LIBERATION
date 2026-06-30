"""Game profiles: the region-specific identifiers (title ID, comm ID) the
launcher builds its paths, config, RPCN and saves from.

Add a GameProfile to support a region, and a data/game_manifest.json entry for a
supported one. A supported=False profile is detected when installed but never
becomes ACTIVE.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GameProfile:
    title_id: str          # PS3 product code, the dev_hdd0/game/<id> folder
    comm_id: str           # PSN communication ID (TSS / TUS saves / trophies)
    region: str            # "US" / "EU" / "JP"
    name: str
    supported: bool = True

    @property
    def config_name(self) -> str:
        """RPCS3 per-game custom config file name."""
        return f"config_{self.title_id}.yml"


# Blank comm_id on the unsupported titles; only supported ones use it.
PROFILES: dict[str, GameProfile] = {
    "NPUB31347": GameProfile("NPUB31347", "NPWR04428_00", "US", "Ace Combat Infinity (US)", True),
    "NPEB01839": GameProfile("NPEB01839", "", "EU", "Ace Combat Infinity (EU)", False),
    "NPJB00481": GameProfile("NPJB00481", "", "JP", "Ace Combat Infinity (JP)", False),
}

# The title the launcher runs; everything but verification uses it.
ACTIVE: GameProfile = PROFILES["NPUB31347"]


def find_installed(game_base) -> GameProfile | None:
    """Return the profile whose game folder is present under game_base
    (dev_hdd0/game), supported or not, else None."""
    base = Path(game_base)
    for profile in PROFILES.values():
        if (base / profile.title_id / "PARAM.SFO").is_file():
            return profile
    return None
