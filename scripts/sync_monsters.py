#!/usr/bin/env python3
"""
Standalone build script to synchronize the Summoners War monster catalog from
the public SWARFARM v2 API (`https://swarfarm.com/api/v2/monsters/`), handling
pagination, and generating a lightweight static lookup map at `src/data/monster_map.json`.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.services.monster_data_service import (
    DEFAULT_MONSTER_MAP_PATH,
    MonsterDataService,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync monster catalog from SWARFARM v2 API to src/data/monster_map.json"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_MONSTER_MAP_PATH,
        help="Target path for monster_map.json (default: src/data/monster_map.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=True,
        help="Force remote sync from SWARFARM API even if local file exists",
    )
    args = parser.parse_args()

    service = MonsterDataService(map_path=args.output, auto_load=True)
    try:
        count = service.sync_from_swarfarm(force=args.force)
        print(f"[sync_monsters] Synced {count:,} monsters -> {service.map_path}")
        return 0
    except Exception as exc:
        service.save_local_map()
        print(
            f"[sync_monsters] Warning: Remote SWARFARM sync failed ({exc}). "
            f"Saved fallback map ({service.size:,} monsters) -> {service.map_path}",
            file=sys.stderr,
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
