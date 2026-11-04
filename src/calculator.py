"""Cálculo de eficiencia (Barion), simulación a +15, EHP, Sets (incl. Intangible) y Speed Tuning."""

from __future__ import annotations

from collections import Counter
import math
from typing import Iterable, Literal

from pydantic import BaseModel, Field

from src.models import (
    MAIN_STAT_MAX_5STAR,
    MAIN_STAT_MAX_6STAR,
    MAX_ROLL_6STAR,
    SET_ID_MAP,
    SET_SIZES,
    SET_STAT_BONUSES,
    Artifact,
    Monster,
    MonsterStats,
    Rune,
)

PVE_TICK_SIZE: float = 0.07
RTA_TICK_SIZE: float = 0.015


def normalize_ratio(value: float) -> float:
    """Convierte porcentajes (ej. 15 o 24) a razón decimal (0.15 o 0.24) si value >= 1.0."""
    if value <= 0.0:
        return 0.0
    return value / 100.0 if value >= 1.0 else value


def simulate_rune_plus15(rune: Rune) -> Rune:
    """Devuelve una copia de la runa simulando su subida a +15 si upgrade_curr < 15."""
    if rune.upgrade_curr >= 15:
        return rune.model_copy(deep=True)
    max_val = rune.get_main_stat_val(simulate_plus15=True)
    copy_rune = rune.model_copy(deep=True)
    copy_rune.upgrade_curr = 15
    copy_rune.pri_eff = (rune.main_stat_id, max_val)
    return copy_rune


def calculate_rune_efficiency(
    rune: Rune,
    include_innate: bool = True,
    use_grinds: bool = True,
) -> float:
    """
    Calcula la Eficiencia de Runa mediante la Fórmula oficial de Barion:
    Eficiencia = ((1.0 + sum(val_efectivo / max_roll_6star)) / 2.8) * 100
    """
    sub_ratio_sum = 0.0

    if include_innate and rune.innate_stat_id in MAX_ROLL_6STAR and rune.innate_stat_val > 0:
        sub_ratio_sum += rune.innate_stat_val / MAX_ROLL_6STAR[rune.innate_stat_id]

    for sub in rune.sec_eff:
        max_roll = MAX_ROLL_6STAR.get(sub.stat_id)
        if max_roll:
            val = sub.effective_val if use_grinds else sub.base_val
            sub_ratio_sum += val / max_roll

    efficiency = ((1.0 + sub_ratio_sum) / 2.8) * 100.0
    return round(efficiency, 2)


def evaluate_active_sets(
    runes: Iterable[Rune],
    preferred_set_ids: Iterable[int] | None = None,
) -> tuple[list[int], int | None]:
    """
    Determina los sets activos a partir de una colección de hasta 6 runas,
    incluyendo la regla de runa Intangible (set_id = 25):
    - Puede sustituir 1 pieza faltante de cualquier set de 2 o 4 piezas (máximo 1 activa).

    Retorna:
        (active_set_ids, intangible_replaced_set_id)
    """
    set_counts: Counter[int] = Counter(r.set_id for r in runes)
    intangible_count = min(1, set_counts.pop(25, 0))  # Máximo 1 Intangible activa

    active_sets: list[int] = []
    remainders: dict[int, int] = {}

    for set_id, count in sorted(set_counts.items()):
        req_size = SET_SIZES.get(set_id)
        if not req_size:
            continue
        complete_num = count // req_size
        for _ in range(complete_num):
            active_sets.append(set_id)
        rem = count % req_size
        if rem > 0:
            remainders[set_id] = rem

    intangible_target: int | None = None
    if intangible_count == 1:
        preferred = set(preferred_set_ids or [])
        # Candidatos a los que les falta exactamente 1 pieza (rem == req_size - 1)
        candidates: list[int] = [
            sid
            for sid, rem in remainders.items()
            if SET_SIZES.get(sid, 0) > 1 and rem == SET_SIZES[sid] - 1
        ]
        if candidates:
            # Prioridad:
            # 1) Está en preferred_set_ids
            # 2) Set de 4 piezas antes que set de 2 piezas
            # 3) Sets que dan stats directos (SET_STAT_BONUSES)
            # 4) Menor set_id para determinismo
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


def calculate_ehp(total_hp: int | float, total_def: int | float) -> float:
    """
    Calcula el Effective HP (EHP):
    Effective_HP (EHP) = Total_HP * (1140 + (Total_DEF * 3.5)) / 1000
    """
    return round((float(total_hp) * (1140.0 + (float(total_def) * 3.5))) / 1000.0, 2)


def calculate_combat_spd(
    base_spd: int,
    rune_spd: int,
    swift_active: bool = False,
    sky_totem: float = 0.15,
    leader_skill_spd: float = 0.0,
) -> int:
    """
    Calcula la velocidad de combate exacta:
    Combat_SPD = Base_SPD + Rune_SPD + ceil(Base_SPD * (Sky_Totem_0.15 + Leader_Skill_SPD + Swift_Bonus_0.25))
    """
    totem_ratio = normalize_ratio(sky_totem)
    leader_ratio = normalize_ratio(leader_skill_spd)
    swift_ratio = 0.25 if swift_active else 0.0
    bonus_spd = math.ceil(base_spd * (totem_ratio + leader_ratio + swift_ratio))
    return base_spd + rune_spd + bonus_spd


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
    """
    Calcula las estadísticas finales de un monstruo aplicando las fórmulas exactas:
    - Total_HP = Base_HP + round(Base_HP * (Sum_HP% / 100)) + Sum_HP_Flat (ídem para ATK y DEF)
    - Combat_SPD = Base_SPD + Rune_SPD + ceil(Base_SPD * (Sky_Totem_0.15 + Leader_Skill_SPD + Swift_Bonus_0.25))
    - Effective_HP (EHP) = Total_HP * (1140 + (Total_DEF * 3.5)) / 1000
    """
    rune_list = list(runes)
    artifact_list = list(artifacts)

    # Acumular estadísticas de runas
    sum_hp_flat = sum(r.get_stat_total(1, simulate_plus15=simulate_plus15) for r in rune_list)
    sum_hp_pct = float(sum(r.get_stat_total(2, simulate_plus15=simulate_plus15) for r in rune_list))
    sum_atk_flat = sum(r.get_stat_total(3, simulate_plus15=simulate_plus15) for r in rune_list)
    sum_atk_pct = float(sum(r.get_stat_total(4, simulate_plus15=simulate_plus15) for r in rune_list))
    sum_def_flat = sum(r.get_stat_total(5, simulate_plus15=simulate_plus15) for r in rune_list)
    sum_def_pct = float(sum(r.get_stat_total(6, simulate_plus15=simulate_plus15) for r in rune_list))
    rune_spd = sum(r.get_stat_total(8, simulate_plus15=simulate_plus15) for r in rune_list)
    sum_crate = sum(r.get_stat_total(9, simulate_plus15=simulate_plus15) for r in rune_list)
    sum_cdmg = sum(r.get_stat_total(10, simulate_plus15=simulate_plus15) for r in rune_list)
    sum_res = sum(r.get_stat_total(11, simulate_plus15=simulate_plus15) for r in rune_list)
    sum_acc = sum(r.get_stat_total(12, simulate_plus15=simulate_plus15) for r in rune_list)

    # Sumar main stats de artefactos (HP flat, ATK flat, DEF flat)
    for art in artifact_list:
        sum_hp_flat += art.flat_hp
        sum_atk_flat += art.flat_atk
        sum_def_flat += art.flat_def

    # Evaluar sets activos (incluyendo Intangible)
    active_set_ids, intangible_target = evaluate_active_sets(rune_list)
    swift_active = 3 in active_set_ids

    for sid in active_set_ids:
        if sid == 3:
            # Swift se aplica sobre Base_SPD
            continue
        bonus = SET_STAT_BONUSES.get(sid)
        if bonus:
            stat_id, val = bonus
            if stat_id == 2:
                sum_hp_pct += val
            elif stat_id == 4:
                sum_atk_pct += val
            elif stat_id == 6:
                sum_def_pct += val
            elif stat_id == 9:
                sum_crate += int(val)
            elif stat_id == 10:
                sum_cdmg += int(val)
            elif stat_id == 11:
                sum_res += int(val)
            elif stat_id == 12:
                sum_acc += int(val)

    # Bonificaciones de sets de equipo adicionales (Fight, Determination, Enhance, Accuracy, Tolerance)
    sum_atk_pct += 8.0 * ally_fight_sets
    sum_def_pct += 8.0 * ally_determination_sets
    sum_hp_pct += 8.0 * ally_enhance_sets
    sum_acc += 10 * ally_accuracy_sets
    sum_res += 10 * ally_tolerance_sets

    base_hp = monster.base_hp
    base_atk = monster.atk
    base_def = monster.def_
    base_spd = monster.spd

    total_hp = base_hp + round(base_hp * (sum_hp_pct / 100.0)) + sum_hp_flat
    total_atk = base_atk + round(base_atk * (sum_atk_pct / 100.0)) + sum_atk_flat
    total_def = base_def + round(base_def * (sum_def_pct / 100.0)) + sum_def_flat

    swift_flat_bonus = math.ceil(base_spd * 0.25) if swift_active else 0
    total_spd = base_spd + rune_spd + swift_flat_bonus
    combat_spd = calculate_combat_spd(
        base_spd=base_spd,
        rune_spd=rune_spd,
        swift_active=swift_active,
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

    ehp = calculate_ehp(total_hp, total_def)
    avg_eff = (
        round(sum(calculate_rune_efficiency(r) for r in rune_list) / len(rune_list), 2)
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
        active_sets=[SET_ID_MAP.get(sid, str(sid)) for sid in active_set_ids],
        intangible_replaced_set=SET_ID_MAP.get(intangible_target) if intangible_target else None,
        avg_efficiency=avg_eff,
    )


class SpeedTuneMember(BaseModel):
    """Configuración de un miembro del equipo para simulación de Speed Tuning."""

    unit_id: int
    name: str
    base_spd: int
    rune_spd: int
    swift_active: bool = False
    atb_boost_pct: float = 0.0  # Ej: 30.0 para Bernard/Tiana, 20.0 para Bastet
    spd_buff_turns: int = 0     # Si aplica buff de +30% Combat SPD al equipo


class SpeedTuneEntryResult(BaseModel):
    """Resultado de Speed Tuning por cada monstruo en el equipo."""

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
    """Reporte completo de simulación de Speed Tuning para PVE (0.07) o RTA (0.015)."""

    mode: Literal["pve", "rta"]
    tick_size: float
    is_perfectly_tuned: bool
    turn_sequence: list[str] = Field(default_factory=list)
    members: list[SpeedTuneEntryResult] = Field(default_factory=list)


def get_tick_size(mode: Literal["pve", "rta"] = "pve") -> float:
    """Devuelve el multiplicador de barra de ataque por tick según el modo (PVE 0.07, RTA 0.015)."""
    return RTA_TICK_SIZE if mode == "rta" else PVE_TICK_SIZE


def calculate_ticks_to_turn(combat_spd: int, mode: Literal["pve", "rta"] = "pve") -> int:
    """Calcula el número de ticks necesarios para alcanzar >= 100% de ATB desde 0."""
    if combat_spd <= 0:
        raise ValueError("combat_spd debe ser positivo")
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
    Calcula el Combat SPD mínimo para que un seguidor actúe exactamente `step_offset` ticks
    después del iniciador (sin ser cortado), considerando el tick_size (PVE=0.07, RTA=0.015),
    el boost de barra (atb_boost_pct) y buff de SPD (+30% durante ticks posteriores).
    """
    tick_size = get_tick_size(mode)
    leader_ticks = calculate_ticks_to_turn(leader_combat_spd, mode=mode)
    needed_atb = max(0.0, 100.0 - atb_boost_pct)
    if needed_atb == 0.0:
        return 1

    # Durante los primeros `leader_ticks` ticks no hay buff de velocidad;
    # durante los `step_offset` ticks posteriores al turno del iniciador, si hay spd_buff (+30%),
    # cada tick aporta 1.30 * tick_size * spd.
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
    Simula tick a tick (PVE 0.07 o RTA 0.015) el primer turno de cada miembro del equipo
    y verifica si el orden de turno real coincide con el orden esperado en la lista `team`.
    """
    tick_size = get_tick_size(mode)
    n = len(team)
    if n == 0:
        return SpeedTuneReport(mode=mode, tick_size=tick_size, is_perfectly_tuned=True)

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
        # Incremento de ATB en el tick actual para los que aún no han actuado
        for i in range(n):
            if not acted[i]:
                mult = 1.30 if spd_buff_active[i] else 1.0
                atb[i] += combat_spds[i] * mult * tick_size

        # Verificar quién tiene >= 100 ATB; el de mayor ATB actúa (desempate por posición)
        ready = [i for i in range(n) if not acted[i] and atb[i] >= 100.0 - 1e-9]
        if ready:
            ready.sort(key=lambda idx: (atb[idx], -idx), reverse=True)
            actor = ready[0]
            acted[actor] = True
            first_turn_tick[actor] = tick
            turn_order_indices.append(actor)

            # Aplicar efectos de habilidad del actor (ATB boost / SPD buff) a los aliados restantes
            boost = team[actor].atb_boost_pct
            gives_spd_buff = team[actor].spd_buff_turns > 0
            for j in range(n):
                if not acted[j]:
                    if boost > 0:
                        atb[j] += boost
                    if gives_spd_buff:
                        spd_buff_active[j] = True

    # Calcular requerimientos mínimos de velocidad en cadena
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
            min_from_booster = calculate_min_follower_combat_spd(
                leader_combat_spd=lead_c_spd,
                atb_boost_pct=total_boost,
                spd_buff_active=any_spd_buff,
                mode=mode,
                step_offset=idx,
            )
            # Además no debe superar al miembro inmediatamente anterior (idx - 1)
            min_c_spd = min_from_booster

        # Calcular rune_spd mínimo requerido para alcanzar min_c_spd
        totem_r = normalize_ratio(sky_totem)
        leader_r = normalize_ratio(leader_skill_spd)
        swift_r = 0.25 if member.swift_active else 0.0
        tower_lead_swift_bonus = math.ceil(member.base_spd * (totem_r + leader_r + swift_r))
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

