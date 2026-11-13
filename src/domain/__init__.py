"""Pure domain layer for SW-OptiPy (`RuneSetMechanics`, `StatCalculator`, and domain models)."""

from __future__ import annotations

from src.domain.rune_set_mechanics import (
    INTANGIBLE_SET_ID,
    SWIFT_SET_ID,
    RuneSetMechanics,
    SetBonusVector,
)
from src.domain.stat_calculator import (
    PVE_TICK_SIZE,
    RTA_TICK_SIZE,
    StatCalculator,
    normalize_ratio,
)
from src.models import (
    MAX_ROLL_6STAR,
    NAME_TO_SET_ID,
    SET_ID_MAP,
    SET_SIZES,
    SET_STAT_BONUSES,
    STAT_ID_MAP,
    AccountProfile,
    Artifact,
    Monster,
    MonsterStats,
    Rune,
    RuneSubstat,
)

__all__ = [
    "AccountProfile",
    "Artifact",
    "INTANGIBLE_SET_ID",
    "MAX_ROLL_6STAR",
    "Monster",
    "MonsterStats",
    "NAME_TO_SET_ID",
    "PVE_TICK_SIZE",
    "RTA_TICK_SIZE",
    "Rune",
    "RuneSetMechanics",
    "RuneSubstat",
    "SET_ID_MAP",
    "SET_SIZES",
    "SET_STAT_BONUSES",
    "STAT_ID_MAP",
    "SWIFT_SET_ID",
    "SetBonusVector",
    "StatCalculator",
    "normalize_ratio",
]
