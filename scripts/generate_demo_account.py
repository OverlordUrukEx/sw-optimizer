#!/usr/bin/env python3
"""
CLI script to extract and sanitize a lightweight demo account (`src/data/demo_account.json`)
from a local SWEX export JSON, keeping the output under 150 KB and stripping all PII.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DEMO_OUTPUT = PROJECT_ROOT / "src" / "data" / "demo_account.json"

DEMO_WIZARD_ID = 10000001
DEMO_WIZARD_NAME = "Demo_Summoner"
DEMO_WIZARD_LEVEL = 100
DEMO_WIZARD_MANA = 25000000
DEMO_WIZARD_CRYSTAL = 1500

# Priority unit_master_id list:
# Includes required 19811 (Lapis), 22911 (Abigail), 11031 (Icaru 2A), 11532 (Spectra 2A),
# 1000113 (Homunculus), plus diverse Wind/Light/Dark units to reach 8 units.
PRIORITY_UNIT_MASTER_IDS: list[int] = [
    19811,    # Lapis (Water 6★)
    22911,    # Abigail (Water 6★)
    11031,    # Icaru (Water 2A)
    11532,    # Spectra (Fire 2A)
    1000113,  # Homunculus(Attack) -> "Demo_Homu"
    14513,    # Teshar (Wind 6★)
    19314,    # Loren (Light 6★)
    11035,    # Kro (Dark 2A)
    17115,    # Veromos (Dark 6★)
    25613,    # Riley (Wind 6★)
]


def _discover_local_swex_source() -> Path:
    """Locates a local SWEX export in the workspace root without hardcoding personal filenames."""
    candidates = sorted(
        p
        for p in PROJECT_ROOT.glob("*-*.json")
        if p.is_file() and p.name != "sample_swex.json"
    )
    if candidates:
        return candidates[0]
    return PROJECT_ROOT / "sample_swex.json"


def _sanitize_rune(
    raw_rune: dict[str, Any],
    synthetic_rune_id: int,
    occupied_id: int = 0,
) -> dict[str, Any]:
    """Keeps essential SWEX rune fields and anonymizes rune_id and wizard_id."""
    return {
        "rune_id": int(synthetic_rune_id),
        "wizard_id": DEMO_WIZARD_ID,
        "occupied_type": 1 if occupied_id else 2,
        "occupied_id": int(occupied_id),
        "slot_no": int(raw_rune["slot_no"]),
        "rank": int(raw_rune.get("rank", 15)),
        "class": int(raw_rune.get("class", 6)),
        "set_id": int(raw_rune["set_id"]),
        "upgrade_limit": 15,
        "upgrade_curr": int(raw_rune.get("upgrade_curr", 15)),
        "pri_eff": list(raw_rune["pri_eff"]),
        "prefix_eff": list(raw_rune.get("prefix_eff", [0, 0])),
        "sec_eff": [list(s) for s in raw_rune.get("sec_eff", [])],
    }


def _sanitize_artifact(
    raw_art: dict[str, Any],
    synthetic_art_id: int,
    occupied_id: int = 0,
) -> dict[str, Any]:
    """Keeps essential SWEX artifact fields and anonymizes rid and wizard_id."""
    pri = raw_art.get("pri_effect") or raw_art.get("pri_eff") or [100, 1500]
    sec = raw_art.get("sec_effects") or raw_art.get("sec_eff") or []
    return {
        "rid": int(synthetic_art_id),
        "wizard_id": DEMO_WIZARD_ID,
        "occupied_id": int(occupied_id),
        "slot": int(raw_art.get("slot", 1)),
        "type": int(raw_art.get("type", 1)),
        "attribute": int(raw_art.get("attribute", 0)),
        "unit_style": int(raw_art.get("unit_style", 0)),
        "natural_rank": int(raw_art.get("natural_rank", 5)),
        "rank": int(raw_art.get("rank", 15)),
        "level": int(raw_art.get("level", 15)),
        "pri_effect": list(pri),
        "sec_effects": [list(s) for s in sec],
    }


def _sanitize_unit(
    raw_unit: dict[str, Any],
    synthetic_unit_id: int,
    next_rune_id_start: int,
    next_art_id_start: int,
) -> tuple[dict[str, Any], int, int]:
    """Sanitizes a unit entry, its equipped runes/artifacts, and sets Demo_Homu if homunculus."""
    unit_master_id = int(raw_unit["unit_master_id"])
    is_homu = (
        int(raw_unit.get("homunculus", 0) or 0) == 1 or unit_master_id == 1000113
    )

    raw_runes = raw_unit.get("runes", [])
    if isinstance(raw_runes, dict):
        raw_runes = list(raw_runes.values())
    clean_runes: list[dict[str, Any]] = []
    curr_rune_id = next_rune_id_start
    for r in raw_runes:
        if isinstance(r, dict):
            clean_runes.append(
                _sanitize_rune(r, synthetic_rune_id=curr_rune_id, occupied_id=synthetic_unit_id)
            )
            curr_rune_id += 1

    raw_arts = raw_unit.get("artifacts", [])
    if isinstance(raw_arts, dict):
        raw_arts = list(raw_arts.values())
    clean_arts: list[dict[str, Any]] = []
    curr_art_id = next_art_id_start
    for a in raw_arts:
        if isinstance(a, dict):
            clean_arts.append(
                _sanitize_artifact(a, synthetic_art_id=curr_art_id, occupied_id=synthetic_unit_id)
            )
            curr_art_id += 1

    unit_dict = {
        "unit_id": int(synthetic_unit_id),
        "wizard_id": DEMO_WIZARD_ID,
        "unit_master_id": unit_master_id,
        "unit_level": int(raw_unit.get("unit_level", 40)),
        "class": int(raw_unit.get("class", 6)),
        "con": int(raw_unit["con"]),
        "atk": int(raw_unit["atk"]),
        "def": int(raw_unit["def"]),
        "spd": int(raw_unit["spd"]),
        "resist": int(raw_unit.get("resist", 15)),
        "accuracy": int(raw_unit.get("accuracy", 0)),
        "critical_rate": int(raw_unit.get("critical_rate", 15)),
        "critical_damage": int(raw_unit.get("critical_damage", 50)),
        "attribute": int(raw_unit.get("attribute", unit_master_id % 10)),
        "homunculus": 1 if is_homu else 0,
        "homunculus_name": "Demo_Homu" if is_homu else "",
        "runes": clean_runes,
        "artifacts": clean_arts,
    }
    return unit_dict, curr_rune_id, curr_art_id


def build_demo_account_payload(
    source_data: dict[str, Any],
    target_unit_count: int = 8,
    target_unequipped_runes: int = 30,
) -> dict[str, Any]:
    """Extracts 8 diverse units and 30 unequipped runes into a fully anonymized SWEX dictionary."""
    raw_units: list[dict[str, Any]] = [
        u for u in source_data.get("unit_list", []) if isinstance(u, dict)
    ]

    selected_units: list[dict[str, Any]] = []
    used_source_unit_ids: set[int] = set()
    next_unit_id = 100001
    next_rune_id = 500001
    next_art_id = 800001

    # 1. Pick priority unit_master_ids first (preferring units with equipped runes)
    for target_mid in PRIORITY_UNIT_MASTER_IDS:
        if len(selected_units) >= target_unit_count:
            break
        candidates = [
            u
            for u in raw_units
            if int(u.get("unit_master_id", 0)) == target_mid
            and int(u.get("unit_id", 0)) not in used_source_unit_ids
        ]
        if candidates:
            candidates.sort(key=lambda u: len(u.get("runes", [])), reverse=True)
            src_u = candidates[0]
            used_source_unit_ids.add(int(src_u.get("unit_id", 0)))
            chosen, next_rune_id, next_art_id = _sanitize_unit(
                deepcopy(src_u),
                synthetic_unit_id=next_unit_id,
                next_rune_id_start=next_rune_id,
                next_art_id_start=next_art_id,
            )
            next_unit_id += 1
            selected_units.append(chosen)

    # 2. Fill up to target_unit_count with any remaining well-runed level 40 units
    if len(selected_units) < target_unit_count:
        remaining = [
            u
            for u in raw_units
            if int(u.get("unit_id", 0)) not in used_source_unit_ids
        ]
        remaining.sort(
            key=lambda u: (len(u.get("runes", [])), int(u.get("unit_level", 0))),
            reverse=True,
        )
        for src_u in remaining:
            if len(selected_units) >= target_unit_count:
                break
            used_source_unit_ids.add(int(src_u.get("unit_id", 0)))
            chosen, next_rune_id, next_art_id = _sanitize_unit(
                deepcopy(src_u),
                synthetic_unit_id=next_unit_id,
                next_rune_id_start=next_rune_id,
                next_art_id_start=next_art_id,
            )
            next_unit_id += 1
            selected_units.append(chosen)

    # 3. Select 30 diverse unequipped runes balanced across slots 1..6 (5 per slot)
    raw_inventory_runes = [
        r for r in source_data.get("runes", []) if isinstance(r, dict)
    ]
    by_slot: dict[int, list[dict[str, Any]]] = {s: [] for s in range(1, 7)}
    for r in raw_inventory_runes:
        slot = int(r.get("slot_no", 1))
        if 1 <= slot <= 6:
            by_slot[slot].append(r)

    per_slot = max(1, target_unequipped_runes // 6)
    selected_runes: list[dict[str, Any]] = []
    used_source_rids: set[int] = set()
    for slot in range(1, 7):
        slot_pool = sorted(
            by_slot[slot],
            key=lambda r: (int(r.get("upgrade_curr", 0)), int(r.get("class", 6))),
            reverse=True,
        )
        for r in slot_pool[:per_slot]:
            used_source_rids.add(int(r.get("rune_id", 0)))
            selected_runes.append(
                _sanitize_rune(r, synthetic_rune_id=next_rune_id, occupied_id=0)
            )
            next_rune_id += 1

    # Top up if any slot had fewer than per_slot
    if len(selected_runes) < target_unequipped_runes:
        for r in raw_inventory_runes:
            if len(selected_runes) >= target_unequipped_runes:
                break
            rid = int(r.get("rune_id", 0))
            if rid not in used_source_rids:
                used_source_rids.add(rid)
                selected_runes.append(
                    _sanitize_rune(r, synthetic_rune_id=next_rune_id, occupied_id=0)
                )
                next_rune_id += 1

    return {
        "wizard_info": {
            "wizard_id": DEMO_WIZARD_ID,
            "wizard_name": DEMO_WIZARD_NAME,
            "wizard_level": DEMO_WIZARD_LEVEL,
            "wizard_mana": DEMO_WIZARD_MANA,
            "wizard_crystal": DEMO_WIZARD_CRYSTAL,
        },
        "unit_list": selected_units,
        "runes": selected_runes[:target_unequipped_runes],
        "artifacts": [],
        "world_arena_rune_equip_list": [],
        "world_arena_artifact_equip_list": [],
        "world_arena_rune_equip_sync": 1,
        "world_arena_artifact_equip_sync": 1,
    }


def generate_demo_account_file(
    source_path: Path | None = None,
    output_path: Path = DEFAULT_DEMO_OUTPUT,
) -> Path:
    """Loads source SWEX JSON, extracts sanitized demo payload, and writes demo_account.json."""
    resolved_source = source_path or _discover_local_swex_source()
    if not resolved_source.exists():
        resolved_source = PROJECT_ROOT / "sample_swex.json"

    raw_data = json.loads(resolved_source.read_text(encoding="utf-8"))
    demo_payload = build_demo_account_payload(raw_data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(demo_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate sanitized src/data/demo_account.json from a local SWEX export."
    )
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_DEMO_OUTPUT)
    args = parser.parse_args()

    out = generate_demo_account_file(args.source, args.output)
    size_kb = out.stat().st_size / 1024.0
    print(f"[generate_demo_account] Wrote {out} ({size_kb:.2f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
