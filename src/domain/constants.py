"""Official Summoners War domain constants and lookup tables (`SwConstants`)."""

from __future__ import annotations

STAT_ID_MAP: dict[int, str] = {
    1: "HP flat",
    2: "HP%",
    3: "ATK flat",
    4: "ATK%",
    5: "DEF flat",
    6: "DEF%",
    8: "SPD",
    9: "CRate%",
    10: "CDmg%",
    11: "RES%",
    12: "ACC%",
}

SET_ID_MAP: dict[int, str] = {
    1: "Energy",
    2: "Guard",
    3: "Swift",
    4: "Blade",
    5: "Rage",
    6: "Focus",
    7: "Endure",
    8: "Fatal",
    10: "Despair",
    11: "Vampire",
    13: "Violent",
    14: "Nemesis",
    15: "Will",
    16: "Shield",
    17: "Revenge",
    18: "Destroy",
    19: "Fight",
    20: "Determination",
    21: "Enhance",
    22: "Accuracy",
    23: "Tolerance",
    24: "Seal",
    25: "Intangible",
}

NAME_TO_SET_ID: dict[str, int] = {v.lower(): k for k, v in SET_ID_MAP.items()}

SET_SIZES: dict[int, int] = {
    1: 2,   # Energy
    2: 2,   # Guard
    3: 4,   # Swift
    4: 2,   # Blade
    5: 4,   # Rage
    6: 2,   # Focus
    7: 2,   # Endure
    8: 4,   # Fatal
    10: 4,  # Despair
    11: 4,  # Vampire
    13: 4,  # Violent
    14: 2,  # Nemesis
    15: 2,  # Will
    16: 2,  # Shield
    17: 2,  # Revenge
    18: 2,  # Destroy
    19: 2,  # Fight
    20: 2,  # Determination
    21: 2,  # Enhance
    22: 2,  # Accuracy
    23: 2,  # Tolerance
    24: 4,  # Seal
    25: 1,  # Intangible (1-piece wildcard)
}

SET_STAT_BONUSES: dict[int, tuple[int, float]] = {
    1: (2, 15.0),    # Energy: +15% HP
    2: (6, 15.0),    # Guard: +15% DEF
    3: (8, 25.0),    # Swift: +25% Base SPD
    4: (9, 12.0),    # Blade: +12% CRate
    5: (10, 40.0),   # Rage: +40% CDmg
    6: (12, 20.0),   # Focus: +20% ACC
    7: (11, 20.0),   # Endure: +20% RES
    8: (4, 35.0),    # Fatal: +35% ATK
    19: (4, 8.0),    # Fight: +8% ATK
    20: (6, 8.0),    # Determination: +8% DEF
    21: (2, 8.0),    # Enhance: +8% HP
    22: (12, 10.0),  # Accuracy: +10% ACC
    23: (11, 10.0),  # Tolerance: +10% RES
}

MAIN_STAT_MAX_6STAR: dict[int, int] = {
    1: 2448,  # HP flat
    2: 63,    # HP%
    3: 160,   # ATK flat
    4: 63,    # ATK%
    5: 160,   # DEF flat
    6: 63,    # DEF%
    8: 42,    # SPD
    9: 58,    # CRate%
    10: 80,   # CDmg%
    11: 64,   # RES%
    12: 64,   # ACC%
}

MAIN_STAT_MAX_5STAR: dict[int, int] = {
    1: 2088,
    2: 51,
    3: 135,
    4: 51,
    5: 135,
    6: 51,
    8: 39,
    9: 47,
    10: 65,
    11: 51,
    12: 51,
}

MAX_ROLL_6STAR: dict[int, float] = {
    1: 1875.0,  # HP flat
    2: 40.0,    # HP%
    3: 100.0,   # ATK flat
    4: 40.0,    # ATK%
    5: 100.0,   # DEF flat
    6: 40.0,    # DEF%
    8: 30.0,    # SPD
    9: 30.0,    # CRate%
    10: 35.0,   # CDmg%
    11: 40.0,   # RES%
    12: 40.0,   # ACC%
}

INTANGIBLE_SET_ID: int = 25
SWIFT_SET_ID: int = 3
PVE_TICK_SIZE: float = 0.07
RTA_TICK_SIZE: float = 0.015


class SwConstants:
    """Centralized namespace for Summoners War domain constants (`SwConstants`)."""

    STAT_ID_MAP = STAT_ID_MAP
    SET_ID_MAP = SET_ID_MAP
    NAME_TO_SET_ID = NAME_TO_SET_ID
    SET_SIZES = SET_SIZES
    SET_STAT_BONUSES = SET_STAT_BONUSES
    MAIN_STAT_MAX_6STAR = MAIN_STAT_MAX_6STAR
    MAIN_STAT_MAX_5STAR = MAIN_STAT_MAX_5STAR
    MAX_ROLL_6STAR = MAX_ROLL_6STAR
    INTANGIBLE_SET_ID = INTANGIBLE_SET_ID
    SWIFT_SET_ID = SWIFT_SET_ID
    PVE_TICK_SIZE = PVE_TICK_SIZE
    RTA_TICK_SIZE = RTA_TICK_SIZE
