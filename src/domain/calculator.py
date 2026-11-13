"""Single source of truth for Summoners War mathematical calculations, RuneSetMechanics, StatCalculator, and Speed Tuning."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Iterable, Literal

from pydantic import BaseModel, Field

from src.domain.constants import (
    INTANGIBLE_SET_ID,
    MAX_ROLL_6STAR,
    PVE_TICK_SIZE,
    RTA_TICK_SIZE,
    SET_ID_MAP,
    SET_SIZES,
    SET_STAT_BONUSES,
    SWIFT_SET_ID,
)
from src.domain.models import (
    Artifact,
    Monster,
    MonsterStats,
    Rune,
)


def normalize_ratio(value: float) -> float:
    """Normalizes percentage inputs (e.g. 15 or 24) to decimal ratios (0.15 or 0.24) if value >= 1.0."""
    if value <= 0.0:
        return 0.0
    return value / 100.0 if value >= 1.0 else value


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
        """Computes aggregated set bonuses using a declarative map."""
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


class StatCalculator:
    """
    Pure domain service encapsulating all Summoners War stat, efficiency, EHP,
    and speed-tuning calculations without UI or persistence coupling.
    """

    @staticmethod
    def simulate_rune_plus15(rune: Rune) -> Rune:
        """Returns a deep copy of the rune with its main stat upgraded to +15 maximum value."""
        if rune.upgrade_curr >= 15:
            return rune.model_copy(deep=True)
        max_val = rune.get_main_stat_val(simulate_plus15=True)
        copy_rune = rune.model_copy(deep=True)
        copy_rune.upgrade_curr = 15
        copy_rune.pri_eff = (rune.main_stat_id, max_val)
        return copy_rune

    @staticmethod
    def calculate_rune_efficiency(
        rune: Rune,
        include_innate: bool = True,
        use_grinds: bool = True,
    ) -> float:
        """
        Computes Barion Rune Efficiency:
        Efficiency = ((1.0 + sum(effective_val / max_roll_6star)) / 2.8) * 100
        """
        sub_ratio_sum = 0.0

        if (
            include_innate
            and rune.innate_stat_id in MAX_ROLL_6STAR
            and rune.innate_stat_val > 0
        ):
            sub_ratio_sum += (
                rune.innate_stat_val / MAX_ROLL_6STAR[rune.innate_stat_id]
            )

        for sub in rune.sec_eff:
            max_roll = MAX_ROLL_6STAR.get(sub.stat_id)
            if max_roll:
                val = sub.effective_val if use_grinds else sub.base_val
                sub_ratio_sum += val / max_roll

        efficiency = ((1.0 + sub_ratio_sum) / 2.8) * 100.0
        return round(efficiency, 2)

    @staticmethod
    def calculate_ehp(total_hp: int | float, total_def: int | float) -> float:
        """Computes Effective HP (EHP) = Total_HP * (1140 + (Total_DEF * 3.5)) / 1000."""
        return round(
            (float(total_hp) * (1140.0 + (float(total_def) * 3.5))) / 1000.0, 2
        )

    @staticmethod
    def calculate_damage_score(
        total_atk: int | float, crate: int | float, cdmg: int | float
    ) -> float:
        """Computes expected average critical damage score: ATK * (1 + CR * CD)."""
        cr_ratio = min(100.0, float(crate)) / 100.0
        cd_ratio = float(cdmg) / 100.0
        return round(float(total_atk) * (1.0 + cr_ratio * cd_ratio), 2)

    @staticmethod
    def calculate_combat_spd(
        base_spd: int,
        rune_spd: int,
        swift_active: bool = False,
        sky_totem: float = 0.15,
        leader_skill_spd: float = 0.0,
    ) -> int:
        """
        Computes exact in-combat speed:
        Combat_SPD = Base_SPD + Rune_SPD + ceil(Base_SPD * (Sky_Totem_0.15 + Leader_Skill_SPD + Swift_Bonus_0.25))
        """
        totem_ratio = normalize_ratio(sky_totem)
        leader_ratio = normalize_ratio(leader_skill_spd)
        swift_ratio = 0.25 if swift_active else 0.0
        bonus_spd = math.ceil(base_spd * (totem_ratio + leader_ratio + swift_ratio))
        return base_spd + rune_spd + bonus_spd

    @classmethod
    def calculate_monster_stats(
        cls,
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
        """Calculates final monster statistics combining base stats, runes, artifacts, and set bonuses."""
        rune_list = list(runes)
        artifact_list = list(artifacts)

        sum_hp_flat = sum(
            r.get_stat_total(1, simulate_plus15=simulate_plus15) for r in rune_list
        )
        sum_hp_pct = float(
            sum(r.get_stat_total(2, simulate_plus15=simulate_plus15) for r in rune_list)
        )
        sum_atk_flat = sum(
            r.get_stat_total(3, simulate_plus15=simulate_plus15) for r in rune_list
        )
        sum_atk_pct = float(
            sum(r.get_stat_total(4, simulate_plus15=simulate_plus15) for r in rune_list)
        )
        sum_def_flat = sum(
            r.get_stat_total(5, simulate_plus15=simulate_plus15) for r in rune_list
        )
        sum_def_pct = float(
            sum(r.get_stat_total(6, simulate_plus15=simulate_plus15) for r in rune_list)
        )
        rune_spd = sum(
            r.get_stat_total(8, simulate_plus15=simulate_plus15) for r in rune_list
        )
        sum_crate = sum(
            r.get_stat_total(9, simulate_plus15=simulate_plus15) for r in rune_list
        )
        sum_cdmg = sum(
            r.get_stat_total(10, simulate_plus15=simulate_plus15) for r in rune_list
        )
        sum_res = sum(
            r.get_stat_total(11, simulate_plus15=simulate_plus15) for r in rune_list
        )
        sum_acc = sum(
            r.get_stat_total(12, simulate_plus15=simulate_plus15) for r in rune_list
        )

        for art in artifact_list:
            sum_hp_flat += art.flat_hp
            sum_atk_flat += art.flat_atk
            sum_def_flat += art.flat_def

        active_set_ids, intangible_target = RuneSetMechanics.resolve_active_sets(
            rune_list
        )
        set_bonuses = RuneSetMechanics.compute_set_bonuses(
            active_set_ids=active_set_ids,
            ally_fight_sets=ally_fight_sets,
            ally_determination_sets=ally_determination_sets,
            ally_enhance_sets=ally_enhance_sets,
            ally_accuracy_sets=ally_accuracy_sets,
            ally_tolerance_sets=ally_tolerance_sets,
        )

        sum_hp_pct += set_bonuses.hp_pct
        sum_atk_pct += set_bonuses.atk_pct
        sum_def_pct += set_bonuses.def_pct
        sum_crate += set_bonuses.crate
        sum_cdmg += set_bonuses.cdmg
        sum_res += set_bonuses.res
        sum_acc += set_bonuses.acc

        base_hp = monster.base_hp
        base_atk = monster.atk
        base_def = monster.def_
        base_spd = monster.spd

        total_hp = base_hp + round(base_hp * (sum_hp_pct / 100.0)) + sum_hp_flat
        total_atk = base_atk + round(base_atk * (sum_atk_pct / 100.0)) + sum_atk_flat
        total_def = base_def + round(base_def * (sum_def_pct / 100.0)) + sum_def_flat

        swift_flat_bonus = (
            math.ceil(base_spd * 0.25) if set_bonuses.swift_active else 0
        )
        total_spd = base_spd + rune_spd + swift_flat_bonus
        combat_spd = cls.calculate_combat_spd(
            base_spd=base_spd,
            rune_spd=rune_spd,
            swift_active=set_bonuses.swift_active,
            sky_totem=sky_totem,
            leader_skill_spd=leader_skill_spd,
        )

        crate = monster.critical_rate + sum_crate
        cdmg = monster.critical_damage + sum_cdmg
        res = monster.resist + sum_res
        acc = monster.accuracy + sum_acc

        if cap_stats:
            crate = min(100, crate)
            res = min(100, res)
            acc = min(100, acc)

        ehp = cls.calculate_ehp(total_hp, total_def)
        avg_eff = (
            round(
                sum(cls.calculate_rune_efficiency(r) for r in rune_list)
                / len(rune_list),
                2,
            )
            if rune_list
            else 0.0
        )

        return MonsterStats(
            unit_id=monster.unit_id,
            name=monster.name,
            base_hp=base_hp,
            base_atk=base_atk,
            base_def=base_def,
            base_spd=base_spd,
            total_hp=total_hp,
            total_atk=total_atk,
            total_def=total_def,
            rune_spd=rune_spd,
            total_spd=total_spd,
            combat_spd=combat_spd,
            crate=crate,
            cdmg=cdmg,
            res=res,
            acc=acc,
            ehp=ehp,
            active_sets=RuneSetMechanics.format_active_set_names(active_set_ids),
            intangible_replaced_set=SET_ID_MAP.get(intangible_target)
            if intangible_target
            else None,
            avg_efficiency=avg_eff,
        )

    @staticmethod
    def get_tick_size(mode: Literal["pve", "rta"] = "pve") -> float:
        return RTA_TICK_SIZE if mode == "rta" else PVE_TICK_SIZE


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
    return RTA_TICK_SIZE if mode == "rta" else PVE_TICK_SIZE


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
