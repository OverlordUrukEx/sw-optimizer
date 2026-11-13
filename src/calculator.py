"""Facade for mathematical calculations delegating to `src.domain.stat_calculator.StatCalculator` and `RuneSetMechanics`."""

from __future__ import annotations

import math
from typing import Iterable, Literal

from pydantic import BaseModel, Field

from src.domain.rune_set_mechanics import RuneSetMechanics
from src.domain.stat_calculator import (
    PVE_TICK_SIZE,
    RTA_TICK_SIZE,
    StatCalculator,
    normalize_ratio,
)
from src.models import (
    Artifact,
    Monster,
    MonsterStats,
    Rune,
)


def simulate_rune_plus15(rune: Rune) -> Rune:
    """Delegates to `StatCalculator.simulate_rune_plus15`."""
    return StatCalculator.simulate_rune_plus15(rune)


def calculate_rune_efficiency(
    rune: Rune,
    include_innate: bool = True,
    use_grinds: bool = True,
) -> float:
    """Delegates to `StatCalculator.calculate_rune_efficiency` (Barion Formula)."""
    return StatCalculator.calculate_rune_efficiency(
        rune=rune,
        include_innate=include_innate,
        use_grinds=use_grinds,
    )


def evaluate_active_sets(
    runes: Iterable[Rune],
    preferred_set_ids: Iterable[int] | None = None,
) -> tuple[list[int], int | None]:
    """Delegates to `RuneSetMechanics.resolve_active_sets`."""
    return RuneSetMechanics.resolve_active_sets(
        runes=runes,
        preferred_set_ids=preferred_set_ids,
    )


def calculate_ehp(total_hp: int | float, total_def: int | float) -> float:
    """Delegates to `StatCalculator.calculate_ehp`."""
    return StatCalculator.calculate_ehp(total_hp=total_hp, total_def=total_def)


def calculate_combat_spd(
    base_spd: int,
    rune_spd: int,
    swift_active: bool = False,
    sky_totem: float = 0.15,
    leader_skill_spd: float = 0.0,
) -> int:
    """Delegates to `StatCalculator.calculate_combat_spd`."""
    return StatCalculator.calculate_combat_spd(
        base_spd=base_spd,
        rune_spd=rune_spd,
        swift_active=swift_active,
        sky_totem=sky_totem,
        leader_skill_spd=leader_skill_spd,
    )


def calculate_monster_stats(
    monster: Monster,
    runes: Iterable[Rune] = (),
    artifacts: Iterable[Artifact] = (),
    simulate_plus15: bool = False,
    sky_totem: float = 0.15,
    leader_skill_spd: float = 0.0,
    ally_fight_sets: int = 0,
    ally_determination_sets: int = 0,
    ally_enhance_sets: int = 0,
    ally_accuracy_sets: int = 0,
    ally_tolerance_sets: int = 0,
    cap_stats: bool = True,
) -> MonsterStats:
    """Delegates to `StatCalculator.calculate_monster_stats`."""
    return StatCalculator.calculate_monster_stats(
        monster=monster,
        runes=runes,
        artifacts=artifacts,
        simulate_plus15=simulate_plus15,
        sky_totem=sky_totem,
        leader_skill_spd=leader_skill_spd,
        ally_fight_sets=ally_fight_sets,
        ally_determination_sets=ally_determination_sets,
        ally_enhance_sets=ally_enhance_sets,
        ally_accuracy_sets=ally_accuracy_sets,
        ally_tolerance_sets=ally_tolerance_sets,
        cap_stats=cap_stats,
    )


class SpeedTuneMember(BaseModel):
    """Configuration for a team member in Speed Tuning simulation."""

    unit_id: int
    name: str
    base_spd: int
    rune_spd: int
    swift_active: bool = False
    atb_boost_pct: float = 0.0
    spd_buff_turns: int = 0


class SpeedTuneEntryResult(BaseModel):
    """Per-monster result of Speed Tuning tick simulation."""

    unit_id: int
    name: str
    combat_spd: int
    first_turn_tick: int
    actual_turn_order: int
    expected_turn_order: int
    min_combat_spd_required: int
    min_rune_spd_required: int
    is_tuned: bool


class SpeedTuneReport(BaseModel):
    """Full Speed Tuning simulation report for PVE (0.07) or RTA (0.015)."""

    mode: Literal["pve", "rta"]
    tick_size: float
    is_perfectly_tuned: bool
    turn_sequence: list[str] = Field(default_factory=list)
    members: list[SpeedTuneEntryResult] = Field(default_factory=list)


def get_tick_size(mode: Literal["pve", "rta"] = "pve") -> float:
    """Returns the ATB fill multiplier per tick (PVE 0.07, RTA 0.015)."""
    return StatCalculator.get_tick_size(mode)


def calculate_ticks_to_turn(
    combat_spd: int, mode: Literal["pve", "rta"] = "pve"
) -> int:
    """Calculates the number of ticks required to reach >= 100% ATB from 0."""
    if combat_spd <= 0:
        raise ValueError("combat_spd must be positive")
    tick_size = get_tick_size(mode)
    return math.ceil(100.0 / (combat_spd * tick_size))


def calculate_min_follower_combat_spd(
    leader_combat_spd: int,
    atb_boost_pct: float = 0.0,
    spd_buff_active: bool = False,
    mode: Literal["pve", "rta"] = "pve",
    step_offset: int = 1,
) -> int:
    """
    Calculates the minimum Combat SPD for a follower to move `step_offset` ticks
    after the opener without being cut, accounting for tick_size, ATB boost, and SPD buff.
    """
    tick_size = get_tick_size(mode)
    leader_ticks = calculate_ticks_to_turn(leader_combat_spd, mode=mode)
    needed_atb = max(0.0, 100.0 - atb_boost_pct)
    if needed_atb == 0.0:
        return 1

    buff_mult = 1.30 if spd_buff_active else 1.0
    effective_tick_multiplier = (leader_ticks + (step_offset * buff_mult)) * tick_size
    return math.ceil(needed_atb / effective_tick_multiplier)


def simulate_speed_tuning(
    team: list[SpeedTuneMember],
    mode: Literal["pve", "rta"] = "pve",
    sky_totem: float = 0.15,
    leader_skill_spd: float = 0.0,
) -> SpeedTuneReport:
    """
    Simulates tick-by-tick (PVE 0.07 or RTA 0.015) first turn order for a team
    and verifies whether actual turn order matches the expected order.
    """
    tick_size = get_tick_size(mode)
    n = len(team)
    if n == 0:
        return SpeedTuneReport(
            mode=mode, tick_size=tick_size, is_perfectly_tuned=True
        )

    combat_spds: list[int] = [
        calculate_combat_spd(
            base_spd=m.base_spd,
            rune_spd=m.rune_spd,
            swift_active=m.swift_active,
            sky_totem=sky_totem,
            leader_skill_spd=leader_skill_spd,
        )
        for m in team
    ]

    atb: list[float] = [0.0] * n
    spd_buff_active: list[bool] = [False] * n
    acted: list[bool] = [False] * n
    first_turn_tick: list[int] = [0] * n
    turn_order_indices: list[int] = []

    tick = 0
    max_ticks = 5000
    while len(turn_order_indices) < n and tick < max_ticks:
        tick += 1
        for i in range(n):
            if not acted[i]:
                mult = 1.30 if spd_buff_active[i] else 1.0
                atb[i] += combat_spds[i] * mult * tick_size

        ready = [i for i in range(n) if not acted[i] and atb[i] >= 100.0 - 1e-9]
        if ready:
            ready.sort(key=lambda idx: (atb[idx], -idx), reverse=True)
            actor = ready[0]
            acted[actor] = True
            first_turn_tick[actor] = tick
            turn_order_indices.append(actor)

            boost = team[actor].atb_boost_pct
            gives_spd_buff = team[actor].spd_buff_turns > 0
            for j in range(n):
                if not acted[j]:
                    if boost > 0:
                        atb[j] += boost
                    if gives_spd_buff:
                        spd_buff_active[j] = True

    total_boost = 0.0
    any_spd_buff = False
    lead_c_spd = combat_spds[0]

    member_results: list[SpeedTuneEntryResult] = []
    for idx, member in enumerate(team):
        actual_pos = (
            turn_order_indices.index(idx) + 1 if idx in turn_order_indices else n
        )
        expected_pos = idx + 1

        if idx == 0:
            min_c_spd = combat_spds[0]
        else:
            min_c_spd = calculate_min_follower_combat_spd(
                leader_combat_spd=lead_c_spd,
                atb_boost_pct=total_boost,
                spd_buff_active=any_spd_buff,
                mode=mode,
                step_offset=idx,
            )

        totem_r = normalize_ratio(sky_totem)
        leader_r = normalize_ratio(leader_skill_spd)
        swift_r = 0.25 if member.swift_active else 0.0
        tower_lead_swift_bonus = math.ceil(
            member.base_spd * (totem_r + leader_r + swift_r)
        )
        min_rune_spd = max(0, min_c_spd - member.base_spd - tower_lead_swift_bonus)

        member_results.append(
            SpeedTuneEntryResult(
                unit_id=member.unit_id,
                name=member.name,
                combat_spd=combat_spds[idx],
                first_turn_tick=first_turn_tick[idx],
                actual_turn_order=actual_pos,
                expected_turn_order=expected_pos,
                min_combat_spd_required=min_c_spd,
                min_rune_spd_required=min_rune_spd,
                is_tuned=(actual_pos == expected_pos),
            )
        )

        total_boost += member.atb_boost_pct
        if member.spd_buff_turns > 0:
            any_spd_buff = True

    is_perfect = all(m.is_tuned for m in member_results)
    sequence_names = [team[i].name for i in turn_order_indices]

    return SpeedTuneReport(
        mode=mode,
        tick_size=tick_size,
        is_perfectly_tuned=is_perfect,
        turn_sequence=sequence_names,
        members=member_results,
    )
