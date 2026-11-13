"""Single source of truth (`StatCalculator`) for Summoners War rune & monster mathematical formulas."""

from __future__ import annotations

import math
from typing import Iterable, Literal

from src.domain.rune_set_mechanics import RuneSetMechanics
from src.models import (
    MAX_ROLL_6STAR,
    SET_ID_MAP,
    Artifact,
    Monster,
    MonsterStats,
    Rune,
)

PVE_TICK_SIZE: float = 0.07
RTA_TICK_SIZE: float = 0.015


def normalize_ratio(value: float) -> float:
    """Normalizes percentage inputs (e.g. 15 or 24) to decimal ratios (0.15 or 0.24) if value >= 1.0."""
    if value <= 0.0:
        return 0.0
    return value / 100.0 if value >= 1.0 else value


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
        """
        Computes Effective HP (EHP):
        EHP = Total_HP * (1140 + (Total_DEF * 3.5)) / 1000
        """
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
        """
        Calculates final monster statistics by combining base stats, rune stats,
        artifact flat stats, and data-driven set bonuses from `RuneSetMechanics`.
        """
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
