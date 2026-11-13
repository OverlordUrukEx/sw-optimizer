"""Domain service for Summoners War Rune Set mechanics (4-piece, 2-piece, Broken, and Set 25 Intangible wildcard)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from src.models import (
     Rune,
    SET_ID_MAP,
    SET_SIZES,
    SET_STAT_BONUSES,
)

INTANGIBLE_SET_ID = 25
SWIFT_SET_ID = 3
MAX_SET_ID = 25


@dataclass(frozen=True, slots=True)
class SetBonusVector:
    """Data-driven vector of stat bonuses granted by completed rune sets."""

    hp_pct: float = 0.0
    atk_pct: float = 0.0
    def_pct: float = 0.0
    spd_pct: float = 0.0
    crate: int = 0
    cdmg: int = 0
    res: int = 0
    acc: int = 0
    swift_active: bool = False


class RuneSetMechanics:
    """
    Single source of truth (OCP & DRY) for Rune Set completion rules,
    Set 25 (Intangible) wildcard substitution, and data-driven set stat bonuses.
    """

    # Declarative mapping from stat_id -> attribute name on SetBonusVector (Open/Closed Principle)
    _STAT_ID_TO_FIELD: dict[int, str] = {
        2: "hp_pct",
        4: "atk_pct",
        6: "def_pct",
        8: "spd_pct",
        9: "crate",
        10: "cdmg",
        11: "res",
        12: "acc",
    }

    @classmethod
    def resolve_active_sets_from_ids(
        cls,
        set_ids: Iterable[int],
        preferred_set_ids: Iterable[int] | None = None,
    ) -> tuple[list[int], int | None]:
        """
        Determines all active completed set IDs from up to 6 rune set_ids,
        applying the official Summoners War Intangible (set_id = 25) rule:
        - Replaces 1 missing piece of any 2-piece or 4-piece set (maximum 1 active).

        Returns:
            (sorted_active_set_ids, intangible_replaced_set_id)
        """
        set_counts: Counter[int] = Counter(int(sid) for sid in set_ids)
        intangible_count = min(1, set_counts.pop(INTANGIBLE_SET_ID, 0))

        active_sets: list[int] = []
        remainders: dict[int, int] = {}

        for set_id, count in sorted(set_counts.items()):
            req_size = SET_SIZES.get(set_id)
            if not req_size:
                continue
            completed_num = count // req_size
            for _ in range(completed_num):
                active_sets.append(set_id)
            rem = count % req_size
            if rem > 0:
                remainders[set_id] = rem

        intangible_target: int | None = None
        if intangible_count == 1:
            preferred = set(preferred_set_ids or [])
            candidates: list[int] = [
                sid
                for sid, rem in remainders.items()
                if SET_SIZES.get(sid, 0) > 1 and rem == SET_SIZES[sid] - 1
            ]
            if candidates:
                candidates.sort(
                    key=lambda sid: (
                        1 if sid in preferred else 0,
                        SET_SIZES.get(sid, 0),
                        1 if sid in SET_STAT_BONUSES else 0,
                        -sid,
                    ),
                    reverse=True,
                )
                intangible_target = candidates[0]
                active_sets.append(intangible_target)

        active_sets.sort()
        return active_sets, intangible_target

    @classmethod
    def resolve_active_sets(
        cls,
        runes: Iterable[Rune],
        preferred_set_ids: Iterable[int] | None = None,
    ) -> tuple[list[int], int | None]:
        """Resolves active sets directly from an iterable of Rune domain objects."""
        return cls.resolve_active_sets_from_ids(
            (r.set_id for r in runes),
            preferred_set_ids=preferred_set_ids,
        )

    @classmethod
    def compute_set_bonuses(
        cls,
        active_set_ids: Iterable[int],
        ally_fight_sets: int = 0,
        ally_determination_sets: int = 0,
        ally_enhance_sets: int = 0,
        ally_accuracy_sets: int = 0,
        ally_tolerance_sets: int = 0,
    ) -> SetBonusVector:
        """
        Computes aggregated set bonuses using a declarative map (no sprawling if/elif chains).
        """
        totals: dict[str, float] = {
            "hp_pct": 8.0 * ally_enhance_sets,
            "atk_pct": 8.0 * ally_fight_sets,
            "def_pct": 8.0 * ally_determination_sets,
            "spd_pct": 0.0,
            "crate": 0.0,
            "cdmg": 0.0,
            "res": 10.0 * ally_tolerance_sets,
            "acc": 10.0 * ally_accuracy_sets,
        }
        swift_active = False

        for sid in active_set_ids:
            if sid == SWIFT_SET_ID:
                swift_active = True
            bonus = SET_STAT_BONUSES.get(sid)
            if bonus is not None:
                stat_id, val = bonus
                field_name = cls._STAT_ID_TO_FIELD.get(stat_id)
                if field_name is not None:
                    totals[field_name] += val

        return SetBonusVector(
            hp_pct=totals["hp_pct"],
            atk_pct=totals["atk_pct"],
            def_pct=totals["def_pct"],
            spd_pct=totals["spd_pct"],
            crate=int(totals["crate"]),
            cdmg=int(totals["cdmg"]),
            res=int(totals["res"]),
            acc=int(totals["acc"]),
            swift_active=swift_active,
        )

    @classmethod
    def is_broken_set(cls, active_set_ids: Iterable[int]) -> bool:
        """Returns True if the completed sets do not cover all 6 rune slots."""
        covered_slots = sum(SET_SIZES.get(sid, 0) for sid in active_set_ids)
        return covered_slots < 6

    @classmethod
    def format_active_set_names(cls, active_set_ids: Iterable[int]) -> list[str]:
        """Maps active set IDs to their human-readable competitive names."""
        return [SET_ID_MAP.get(sid, str(sid)) for sid in active_set_ids]
