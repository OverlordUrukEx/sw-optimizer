"""Motor de Optimización Combinatoria Branch & Bound acelerado con NumPy y Numba."""

from __future__ import annotations

from collections import Counter
import math
import time
from typing import Iterable, Literal

from numba import njit
import numpy as np
from pydantic import BaseModel, Field

from src.calculator import (
    calculate_min_follower_combat_spd,
    calculate_monster_stats,
    calculate_rune_efficiency,
    normalize_ratio,
)
from src.models import (
    AccountProfile,
    Artifact,
    Monster,
    MonsterStats,
    Rune,
    SET_SIZES,
)

# Índices de columnas en la matriz NumPy de runas por slot
COL_RUNE_ID = 0
COL_SET_ID = 1
COL_HP_FLAT = 2
COL_HP_PCT = 3
COL_ATK_FLAT = 4
COL_ATK_PCT = 5
COL_DEF_FLAT = 6
COL_DEF_PCT = 7
COL_SPD = 8
COL_CRATE = 9
COL_CDMG = 10
COL_RES = 11
COL_ACC = 12
COL_EFF = 13
NUM_RUNE_COLS = 14


class OptimizationConstraints(BaseModel):
    """Restricciones, filtros de sets, main stats y pesos de enfoque para el optimizador."""

    required_sets: list[int] = Field(default_factory=list)  # Ej: [3, 15] para Swift + Will
    slot2_main_stats: list[int] = Field(default_factory=list)  # Vacío = cualquier main stat
    slot4_main_stats: list[int] = Field(default_factory=list)
    slot6_main_stats: list[int] = Field(default_factory=list)

    min_spd: int = 0
    max_spd: int = 9999
    min_hp: int = 0
    min_atk: int = 0
    min_def: int = 0
    min_cr: int = 0
    min_cdmg: int = 0
    min_res: int = 0
    min_acc: int = 0
    min_ehp: float = 0.0

    simulate_plus15: bool = True
    allow_broken_sets: bool = True
    sky_totem: float = 0.15
    leader_skill_spd: float = 0.0

    # Objetivo a maximizar: "spd", "ehp", "damage", "atk", "hp", "def", "efficiency", "custom"
    optimize_for: Literal[
        "spd", "ehp", "damage", "atk", "hp", "def", "efficiency", "custom"
    ] = "damage"

    # Pesos para poda por Focus Stats y objetivo "custom"
    focus_weights: dict[int, float] = Field(
        default_factory=lambda: {
            8: 2.5,   # SPD
            9: 2.0,   # CRate%
            10: 1.8,  # CDmg%
            4: 1.5,   # ATK%
            2: 1.5,   # HP%
            6: 1.2,   # DEF%
            12: 1.0,  # ACC%
            11: 0.8,  # RES%
        }
    )

    max_runes_per_slot: int = 20
    top_k: int = 10


class OptimizedBuild(BaseModel):
    """Representa una combinación óptima de 6 runas y las estadísticas resultantes."""

    rank: int
    score: float
    rune_ids: list[int]
    runes: list[Rune]
    stats: MonsterStats


class OptimizationResult(BaseModel):
    """Resultado de una ejecución del motor de optimización."""

    unit_id: int
    monster_name: str
    evaluated_builds: int
    pruned_triplets_246: int
    total_triplets_246: int
    elapsed_ms: float
    builds: list[OptimizedBuild] = Field(default_factory=list)


class TeamOptimizationRequestMember(BaseModel):
    """Miembro de un equipo a optimizar secuencialmente con Speed Tuning."""

    monster: Monster
    constraints: OptimizationConstraints
    atb_boost_pct: float = 0.0
    spd_buff_turns: int = 0
    artifacts: list[Artifact] = Field(default_factory=list)


def score_rune_for_focus(
    rune: Rune,
    constraints: OptimizationConstraints,
) -> float:
    """Puntúa una runa según los Focus Stats y la afinidad con los sets requeridos."""
    sim = constraints.simulate_plus15
    score = calculate_rune_efficiency(rune) * 0.4

    for stat_id, weight in constraints.focus_weights.items():
        val = rune.get_stat_total(stat_id, simulate_plus15=sim)
        score += val * weight

    # Bonificación de prioridad si la runa pertenece a los sets requeridos o es Intangible (25)
    if rune.set_id in constraints.required_sets:
        score += 35.0
    elif rune.set_id == 25:
        score += 40.0

    return score


def filter_and_prune_runes_by_slot(
    available_runes: Iterable[Rune],
    constraints: OptimizationConstraints,
) -> dict[int, list[Rune]]:
    """
    Fase 1 del optimizador:
    - Separa las runas por slot (1..6).
    - Filtra slots (2, 4, 6) por main_stat_id permitido si se especificó.
    - Poda cada slot conservando las mejores `max_runes_per_slot` según Focus Stats,
      asegurando preservar candidatos de los sets requeridos e Intangible.
    """
    by_slot: dict[int, list[Rune]] = {s: [] for s in range(1, 7)}
    for r in available_runes:
        if r.slot_no == 2 and constraints.slot2_main_stats:
            if r.main_stat_id not in constraints.slot2_main_stats:
                continue
        elif r.slot_no == 4 and constraints.slot4_main_stats:
            if r.main_stat_id not in constraints.slot4_main_stats:
                continue
        elif r.slot_no == 6 and constraints.slot6_main_stats:
            if r.main_stat_id not in constraints.slot6_main_stats:
                continue
        by_slot[r.slot_no].append(r)

    limit = max(4, constraints.max_runes_per_slot)
    pruned: dict[int, list[Rune]] = {}
    for slot, rune_list in by_slot.items():
        scored = sorted(
            rune_list,
            key=lambda r: score_rune_for_focus(r, constraints),
            reverse=True,
        )
        pruned[slot] = scored[:limit]
    return pruned


def runes_to_matrix(runes: list[Rune], simulate_plus15: bool = True) -> np.ndarray:
    """Empaqueta una lista de runas en una matriz NumPy (N, NUM_RUNE_COLS) float64."""
    n = len(runes)
    mat = np.zeros((n, NUM_RUNE_COLS), dtype=np.float64)
    for i, r in enumerate(runes):
        mat[i, COL_RUNE_ID] = float(r.rune_id)
        mat[i, COL_SET_ID] = float(r.set_id)
        mat[i, COL_HP_FLAT] = float(r.get_stat_total(1, simulate_plus15=simulate_plus15))
        mat[i, COL_HP_PCT] = float(r.get_stat_total(2, simulate_plus15=simulate_plus15))
        mat[i, COL_ATK_FLAT] = float(r.get_stat_total(3, simulate_plus15=simulate_plus15))
        mat[i, COL_ATK_PCT] = float(r.get_stat_total(4, simulate_plus15=simulate_plus15))
        mat[i, COL_DEF_FLAT] = float(r.get_stat_total(5, simulate_plus15=simulate_plus15))
        mat[i, COL_DEF_PCT] = float(r.get_stat_total(6, simulate_plus15=simulate_plus15))
        mat[i, COL_SPD] = float(r.get_stat_total(8, simulate_plus15=simulate_plus15))
        mat[i, COL_CRATE] = float(r.get_stat_total(9, simulate_plus15=simulate_plus15))
        mat[i, COL_CDMG] = float(r.get_stat_total(10, simulate_plus15=simulate_plus15))
        mat[i, COL_RES] = float(r.get_stat_total(11, simulate_plus15=simulate_plus15))
        mat[i, COL_ACC] = float(r.get_stat_total(12, simulate_plus15=simulate_plus15))
        mat[i, COL_EFF] = calculate_rune_efficiency(r)
    return mat


@njit(cache=True, nogil=True)
def _check_sets_and_bonuses_numba(
    s1: int,
    s2: int,
    s3: int,
    s4: int,
    s5: int,
    s6: int,
    req_set_ids: np.ndarray,
    req_set_counts: np.ndarray,
    allow_broken: bool = True,
) -> tuple[bool, float, float, float, int, int, int, int, bool]:
    """
    Evalúa en código nativo compilado con Numba:
    1) Los sets activos entre las 6 runas (incluyendo la regla de Intangible = 25, máx 1 activa).
    2) Si se satisfacen todos los `req_set_ids` solicitados.
    3) Las bonificaciones porcentuales de sets activos:
       (hp_pct, atk_pct, def_pct, crate, cdmg, res, acc, swift_active).
    """
    counts = np.zeros(26, dtype=np.int32)
    counts[s1] += 1
    counts[s2] += 1
    counts[s3] += 1
    counts[s4] += 1
    counts[s5] += 1
    counts[s6] += 1

    # Regla SW: máximo 1 runa Intangible activa; si hay >1 Intangible, las extra no completan nada
    intangible_avail = 1 if counts[25] >= 1 else 0

    # Tamaños de set por ID (1..24)
    set_sizes = np.zeros(26, dtype=np.int32)
    set_sizes[1] = 2
    set_sizes[2] = 2
    set_sizes[3] = 4
    set_sizes[4] = 2
    set_sizes[5] = 4
    set_sizes[6] = 2
    set_sizes[7] = 2
    set_sizes[8] = 4
    set_sizes[10] = 4
    set_sizes[11] = 4
    set_sizes[13] = 4
    set_sizes[14] = 2
    set_sizes[15] = 2
    set_sizes[16] = 2
    set_sizes[17] = 2
    set_sizes[18] = 2
    set_sizes[19] = 2
    set_sizes[20] = 2
    set_sizes[21] = 2
    set_sizes[22] = 2
    set_sizes[23] = 2
    set_sizes[24] = 4

    completed = np.zeros(26, dtype=np.int32)
    rem = np.zeros(26, dtype=np.int32)

    for sid in range(1, 25):
        sz = set_sizes[sid]
        if sz > 0 and counts[sid] > 0:
            completed[sid] = counts[sid] // sz
            rem[sid] = counts[sid] % sz

    # Si hay 1 Intangible disponible, elegir qué set incompleto (al que le falte 1 pieza) completar
    if intangible_avail == 1:
        chosen_sid = 0
        # 1) Priorizar si algún set requerido necesita exactamente 1 pieza para alcanzar req_set_counts
        for idx in range(len(req_set_ids)):
            rsid = req_set_ids[idx]
            rcount = req_set_counts[idx]
            sz = set_sizes[rsid]
            if sz > 0 and completed[rsid] < rcount and rem[rsid] == sz - 1:
                chosen_sid = rsid
                break
        # 2) Si no, priorizar cualquier set de 4 piezas con rem == 3
        if chosen_sid == 0:
            for sid in range(1, 25):
                if set_sizes[sid] == 4 and rem[sid] == 3:
                    chosen_sid = sid
                    break
        # 3) Si no, cualquier set de 2 piezas con rem == 1
        if chosen_sid == 0:
            for sid in range(1, 25):
                if set_sizes[sid] == 2 and rem[sid] == 1:
                    chosen_sid = sid
                    break
        if chosen_sid > 0:
            completed[chosen_sid] += 1

    # Validar sets requeridos por el usuario
    for idx in range(len(req_set_ids)):
        rsid = req_set_ids[idx]
        if completed[rsid] < req_set_counts[idx]:
            return False, 0.0, 0.0, 0.0, 0, 0, 0, 0, False

    if not allow_broken:
        covered_pieces = 0
        for sid in range(1, 25):
            covered_pieces += completed[sid] * set_sizes[sid]
        if covered_pieces < 6:
            return False, 0.0, 0.0, 0.0, 0, 0, 0, 0, False

    # Calcular bonificaciones de sets activos
    hp_pct = completed[1] * 15.0 + completed[21] * 8.0
    def_pct = completed[2] * 15.0 + completed[20] * 8.0
    atk_pct = completed[8] * 35.0 + completed[19] * 8.0
    crate = completed[4] * 12
    cdmg = completed[5] * 40
    acc = completed[6] * 20 + completed[22] * 10
    res = completed[7] * 20 + completed[23] * 10
    swift_active = completed[3] >= 1

    return True, hp_pct, atk_pct, def_pct, crate, cdmg, res, acc, swift_active


@njit(cache=True, nogil=True)
def _branch_and_bound_kernel(
    m1: np.ndarray,
    m2: np.ndarray,
    m3: np.ndarray,
    m4: np.ndarray,
    m5: np.ndarray,
    m6: np.ndarray,
    base_hp: int,
    base_atk: int,
    base_def: int,
    base_spd: int,
    base_cr: int,
    base_cd: int,
    base_res: int,
    base_acc: int,
    art_hp_flat: int,
    art_atk_flat: int,
    art_def_flat: int,
    totem_plus_leader_ratio: float,
    req_set_ids: np.ndarray,
    req_set_counts: np.ndarray,
    total_req_pieces: int,
    min_spd: int,
    max_spd: int,
    min_hp: int,
    min_atk: int,
    min_def: int,
    min_cr: int,
    min_cdmg: int,
    min_res: int,
    min_acc: int,
    min_ehp: float,
    opt_mode: int,
    top_k: int,
    allow_broken: bool = True,
) -> tuple[np.ndarray, np.ndarray, int, int, int]:
    """
    Núcleo JIT (Numba) con evaluación prioritaria de slots (2, 4, 6) y poda temprana (Branch & Bound).
    """
    n1 = m1.shape[0]
    n2 = m2.shape[0]
    n3 = m3.shape[0]
    n4 = m4.shape[0]
    n5 = m5.shape[0]
    n6 = m6.shape[0]

    best_scores = np.full(top_k, -1e18, dtype=np.float64)
    best_indices = np.full((top_k, 6), -1, dtype=np.int32)

    if n1 == 0 or n2 == 0 or n3 == 0 or n4 == 0 or n5 == 0 or n6 == 0:
        return best_scores, best_indices, 0, 0, 0

    # Precalcular cotas superiores alcanzables en los slots (1, 3, 5) para Branch & Bound
    max_spd_135 = (
        np.max(m1[:, COL_SPD]) + np.max(m3[:, COL_SPD]) + np.max(m5[:, COL_SPD])
    )
    max_cr_135 = (
        np.max(m1[:, COL_CRATE]) + np.max(m3[:, COL_CRATE]) + np.max(m5[:, COL_CRATE])
    )
    max_acc_135 = (
        np.max(m1[:, COL_ACC]) + np.max(m3[:, COL_ACC]) + np.max(m5[:, COL_ACC])
    )
    max_hp_pct_135 = (
        np.max(m1[:, COL_HP_PCT]) + np.max(m3[:, COL_HP_PCT]) + np.max(m5[:, COL_HP_PCT])
    )
    max_hp_flat_135 = (
        np.max(m1[:, COL_HP_FLAT]) + np.max(m3[:, COL_HP_FLAT]) + np.max(m5[:, COL_HP_FLAT])
    )

    combat_bonus_no_swift = int(math.ceil(base_spd * totem_plus_leader_ratio))
    combat_bonus_swift = int(math.ceil(base_spd * (totem_plus_leader_ratio + 0.25)))

    total_triplets_246 = n2 * n4 * n6
    pruned_triplets_246 = 0
    evaluated_builds = 0

    # Tamaños de set para validación rápida en (2, 4, 6)
    set_sizes = np.zeros(26, dtype=np.int32)
    set_sizes[1] = 2
    set_sizes[2] = 2
    set_sizes[3] = 4
    set_sizes[4] = 2
    set_sizes[5] = 4
    set_sizes[6] = 2
    set_sizes[7] = 2
    set_sizes[8] = 4
    set_sizes[10] = 4
    set_sizes[11] = 4
    set_sizes[13] = 4
    set_sizes[14] = 2
    set_sizes[15] = 2
    set_sizes[16] = 2
    set_sizes[17] = 2
    set_sizes[18] = 2
    set_sizes[19] = 2
    set_sizes[20] = 2
    set_sizes[21] = 2
    set_sizes[22] = 2
    set_sizes[23] = 2
    set_sizes[24] = 4

    # Bucle externo: combinaciones de slots (2, 4, 6)
    for i2 in range(n2):
        s2 = int(m2[i2, COL_SET_ID])
        for i4 in range(n4):
            s4 = int(m4[i4, COL_SET_ID])
            for i6 in range(n6):
                s6 = int(m6[i6, COL_SET_ID])

                # 1. Poda temprana de compatibilidad de Set en (2, 4, 6)
                if total_req_pieces > 0:
                    have_req_pieces = 0
                    for r_idx in range(len(req_set_ids)):
                        rsid = req_set_ids[r_idx]
                        needed_for_set = req_set_counts[r_idx] * set_sizes[rsid]
                        c_in_246 = 0
                        if s2 == rsid:
                            c_in_246 += 1
                        if s4 == rsid:
                            c_in_246 += 1
                        if s6 == rsid:
                            c_in_246 += 1
                        have_req_pieces += min(needed_for_set, c_in_246)
                    # Si hay al menos una Intangible en (2, 4, 6), puede aportar 1 pieza requerida
                    if s2 == 25 or s4 == 25 or s6 == 25:
                        have_req_pieces += 1
                    # En los slots (1, 3, 5) solo quedan 3 espacios como máximo
                    if total_req_pieces - have_req_pieces > 3:
                        pruned_triplets_246 += 1
                        continue

                # 2. Poda temprana (Branch & Bound) contra min_spd, min_cr, min_acc, min_hp
                spd_246 = m2[i2, COL_SPD] + m4[i4, COL_SPD] + m6[i6, COL_SPD]
                max_possible_c_spd = (
                    base_spd + int(spd_246 + max_spd_135) + combat_bonus_swift
                )
                if max_possible_c_spd < min_spd:
                    pruned_triplets_246 += 1
                    continue

                cr_246 = m2[i2, COL_CRATE] + m4[i4, COL_CRATE] + m6[i6, COL_CRATE]
                # +36% máximo teórico de 3x Blade
                if base_cr + int(cr_246 + max_cr_135) + 36 < min_cr:
                    pruned_triplets_246 += 1
                    continue

                acc_246 = m2[i2, COL_ACC] + m4[i4, COL_ACC] + m6[i6, COL_ACC]
                # +60% máximo teórico de 3x Focus
                if base_acc + int(acc_246 + max_acc_135) + 60 < min_acc:
                    pruned_triplets_246 += 1
                    continue

                hp_pct_246 = m2[i2, COL_HP_PCT] + m4[i4, COL_HP_PCT] + m6[i6, COL_HP_PCT]
                hp_flat_246 = m2[i2, COL_HP_FLAT] + m4[i4, COL_HP_FLAT] + m6[i6, COL_HP_FLAT]
                # +45% máximo teórico de 3x Energy
                max_hp_reach = (
                    base_hp
                    + int(round(base_hp * ((hp_pct_246 + max_hp_pct_135 + 45.0) / 100.0)))
                    + int(hp_flat_246 + max_hp_flat_135)
                    + art_hp_flat
                )
                if max_hp_reach < min_hp:
                    pruned_triplets_246 += 1
                    continue

                atk_pct_246 = m2[i2, COL_ATK_PCT] + m4[i4, COL_ATK_PCT] + m6[i6, COL_ATK_PCT]
                atk_flat_246 = m2[i2, COL_ATK_FLAT] + m4[i4, COL_ATK_FLAT] + m6[i6, COL_ATK_FLAT]
                def_pct_246 = m2[i2, COL_DEF_PCT] + m4[i4, COL_DEF_PCT] + m6[i6, COL_DEF_PCT]
                def_flat_246 = m2[i2, COL_DEF_FLAT] + m4[i4, COL_DEF_FLAT] + m6[i6, COL_DEF_FLAT]
                cd_246 = m2[i2, COL_CDMG] + m4[i4, COL_CDMG] + m6[i6, COL_CDMG]
                res_246 = m2[i2, COL_RES] + m4[i4, COL_RES] + m6[i6, COL_RES]
                eff_246 = m2[i2, COL_EFF] + m4[i4, COL_EFF] + m6[i6, COL_EFF]

                # Bucle interno: slots (1, 3, 5)
                for i1 in range(n1):
                    s1 = int(m1[i1, COL_SET_ID])
                    for i3 in range(n3):
                        s3 = int(m3[i3, COL_SET_ID])
                        for i5 in range(n5):
                            s5 = int(m5[i5, COL_SET_ID])

                            (
                                ok_sets,
                                set_hp_pct,
                                set_atk_pct,
                                set_def_pct,
                                set_cr,
                                set_cd,
                                set_res,
                                set_acc,
                                swift_active,
                            ) = _check_sets_and_bonuses_numba(
                                s1, s2, s3, s4, s5, s6, req_set_ids, req_set_counts, allow_broken
                            )
                            if not ok_sets:
                                continue

                            evaluated_builds += 1

                            rune_spd = int(
                                spd_246 + m1[i1, COL_SPD] + m3[i3, COL_SPD] + m5[i5, COL_SPD]
                            )
                            c_spd = (
                                base_spd
                                + rune_spd
                                + (combat_bonus_swift if swift_active else combat_bonus_no_swift)
                            )
                            if c_spd < min_spd or c_spd > max_spd:
                                continue

                            raw_cr = (
                                base_cr
                                + int(cr_246 + m1[i1, COL_CRATE] + m3[i3, COL_CRATE] + m5[i5, COL_CRATE])
                                + set_cr
                            )
                            crate = 100 if raw_cr > 100 else raw_cr
                            if crate < min_cr:
                                continue

                            raw_acc = (
                                base_acc
                                + int(acc_246 + m1[i1, COL_ACC] + m3[i3, COL_ACC] + m5[i5, COL_ACC])
                                + set_acc
                            )
                            acc = 100 if raw_acc > 100 else raw_acc
                            if acc < min_acc:
                                continue

                            raw_res = (
                                base_res
                                + int(res_246 + m1[i1, COL_RES] + m3[i3, COL_RES] + m5[i5, COL_RES])
                                + set_res
                            )
                            res = 100 if raw_res > 100 else raw_res
                            if res < min_res:
                                continue

                            cdmg = (
                                base_cd
                                + int(cd_246 + m1[i1, COL_CDMG] + m3[i3, COL_CDMG] + m5[i5, COL_CDMG])
                                + set_cd
                            )
                            if cdmg < min_cdmg:
                                continue

                            sum_hp_pct = (
                                hp_pct_246
                                + m1[i1, COL_HP_PCT]
                                + m3[i3, COL_HP_PCT]
                                + m5[i5, COL_HP_PCT]
                                + set_hp_pct
                            )
                            sum_hp_flat = (
                                int(hp_flat_246 + m1[i1, COL_HP_FLAT] + m3[i3, COL_HP_FLAT] + m5[i5, COL_HP_FLAT])
                                + art_hp_flat
                            )
                            total_hp = base_hp + int(round(base_hp * (sum_hp_pct / 100.0))) + sum_hp_flat
                            if total_hp < min_hp:
                                continue

                            sum_atk_pct = (
                                atk_pct_246
                                + m1[i1, COL_ATK_PCT]
                                + m3[i3, COL_ATK_PCT]
                                + m5[i5, COL_ATK_PCT]
                                + set_atk_pct
                            )
                            sum_atk_flat = (
                                int(atk_flat_246 + m1[i1, COL_ATK_FLAT] + m3[i3, COL_ATK_FLAT] + m5[i5, COL_ATK_FLAT])
                                + art_atk_flat
                            )
                            total_atk = base_atk + int(round(base_atk * (sum_atk_pct / 100.0))) + sum_atk_flat
                            if total_atk < min_atk:
                                continue

                            sum_def_pct = (
                                def_pct_246
                                + m1[i1, COL_DEF_PCT]
                                + m3[i3, COL_DEF_PCT]
                                + m5[i5, COL_DEF_PCT]
                                + set_def_pct
                            )
                            sum_def_flat = (
                                int(def_flat_246 + m1[i1, COL_DEF_FLAT] + m3[i3, COL_DEF_FLAT] + m5[i5, COL_DEF_FLAT])
                                + art_def_flat
                            )
                            total_def = base_def + int(round(base_def * (sum_def_pct / 100.0))) + sum_def_flat
                            if total_def < min_def:
                                continue

                            ehp = (float(total_hp) * (1140.0 + float(total_def) * 3.5)) / 1000.0
                            if ehp < min_ehp:
                                continue

                            avg_eff = (
                                eff_246 + m1[i1, COL_EFF] + m3[i3, COL_EFF] + m5[i5, COL_EFF]
                            ) / 6.0

                            # Función objetivo
                            if opt_mode == 0:    # damage
                                score = float(total_atk) * (1.0 + (float(crate) / 100.0) * (float(cdmg) / 100.0))
                            elif opt_mode == 1:  # ehp
                                score = ehp
                            elif opt_mode == 2:  # spd
                                score = float(c_spd) * 1000.0 + avg_eff
                            elif opt_mode == 3:  # atk
                                score = float(total_atk)
                            elif opt_mode == 4:  # hp
                                score = float(total_hp)
                            elif opt_mode == 5:  # def
                                score = float(total_def)
                            else:                # efficiency / custom
                                score = avg_eff * 10.0 + float(c_spd)

                            # Insertar en Top-K ordenado descendente
                            if score > best_scores[top_k - 1]:
                                pos = top_k - 1
                                while pos > 0 and score > best_scores[pos - 1]:
                                    best_scores[pos] = best_scores[pos - 1]
                                    for c in range(6):
                                        best_indices[pos, c] = best_indices[pos - 1, c]
                                    pos -= 1
                                best_scores[pos] = score
                                best_indices[pos, 0] = i1
                                best_indices[pos, 1] = i2
                                best_indices[pos, 2] = i3
                                best_indices[pos, 3] = i4
                                best_indices[pos, 4] = i5
                                best_indices[pos, 5] = i6

    return best_scores, best_indices, evaluated_builds, pruned_triplets_246, total_triplets_246


_OPT_MODE_MAP: dict[str, int] = {
    "damage": 0,
    "ehp": 1,
    "spd": 2,
    "atk": 3,
    "hp": 4,
    "def": 5,
    "efficiency": 6,
    "custom": 6,
}


def optimize_monster_builds(
    monster: Monster,
    available_runes: Iterable[Rune],
    constraints: OptimizationConstraints | None = None,
    artifacts: Iterable[Artifact] = (),
) -> OptimizationResult:
    """
    Ejecuta el motor de optimización Branch & Bound con NumPy/Numba para un monstruo.
    """
    t0 = time.perf_counter()
    cfg = constraints or OptimizationConstraints()
    artifact_list = list(artifacts)

    pruned_by_slot = filter_and_prune_runes_by_slot(available_runes, cfg)
    slot_lists = [pruned_by_slot[s] for s in range(1, 7)]
    matrices = [runes_to_matrix(lst, simulate_plus15=cfg.simulate_plus15) for lst in slot_lists]

    art_hp = sum(a.flat_hp for a in artifact_list)
    art_atk = sum(a.flat_atk for a in artifact_list)
    art_def = sum(a.flat_def for a in artifact_list)

    set_counter = Counter(cfg.required_sets)
    if set_counter:
        req_set_ids = np.array(list(set_counter.keys()), dtype=np.int32)
        req_set_counts = np.array(list(set_counter.values()), dtype=np.int32)
        total_req_pieces = sum(SET_SIZES.get(sid, 0) * cnt for sid, cnt in set_counter.items())
    else:
        req_set_ids = np.zeros(0, dtype=np.int32)
        req_set_counts = np.zeros(0, dtype=np.int32)
        total_req_pieces = 0

    totem_plus_leader = normalize_ratio(cfg.sky_totem) + normalize_ratio(cfg.leader_skill_spd)
    opt_mode_int = _OPT_MODE_MAP.get(cfg.optimize_for, 0)
    top_k = max(1, cfg.top_k)

    best_scores, best_indices, evaluated, pruned_246, total_246 = _branch_and_bound_kernel(
        matrices[0],
        matrices[1],
        matrices[2],
        matrices[3],
        matrices[4],
        matrices[5],
        monster.base_hp,
        monster.atk,
        monster.def_,
        monster.spd,
        monster.critical_rate,
        monster.critical_damage,
        monster.resist,
        monster.accuracy,
        art_hp,
        art_atk,
        art_def,
        totem_plus_leader,
        req_set_ids,
        req_set_counts,
        total_req_pieces,
        cfg.min_spd,
        cfg.max_spd,
        cfg.min_hp,
        cfg.min_atk,
        cfg.min_def,
        cfg.min_cr,
        cfg.min_cdmg,
        cfg.min_res,
        cfg.min_acc,
        cfg.min_ehp,
        opt_mode_int,
        top_k,
        cfg.allow_broken_sets,
    )

    builds: list[OptimizedBuild] = []
    rank = 1
    for k in range(top_k):
        if best_indices[k, 0] < 0 or best_scores[k] <= -1e17:
            continue
        chosen_runes = [
            slot_lists[slot_idx][int(best_indices[k, slot_idx])]
            for slot_idx in range(6)
        ]
        stats = calculate_monster_stats(
            monster=monster,
            runes=chosen_runes,
            artifacts=artifact_list,
            simulate_plus15=cfg.simulate_plus15,
            sky_totem=cfg.sky_totem,
            leader_skill_spd=cfg.leader_skill_spd,
        )
        builds.append(
            OptimizedBuild(
                rank=rank,
                score=round(float(best_scores[k]), 2),
                rune_ids=[r.rune_id for r in chosen_runes],
                runes=chosen_runes,
                stats=stats,
            )
        )
        rank += 1

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return OptimizationResult(
        unit_id=monster.unit_id,
        monster_name=monster.name,
        evaluated_builds=int(evaluated),
        pruned_triplets_246=int(pruned_246),
        total_triplets_246=int(total_246),
        elapsed_ms=elapsed_ms,
        builds=builds,
    )


def optimize_team_speed_tuning(
    profile: AccountProfile,
    team_requests: list[TeamOptimizationRequestMember],
    mode: Literal["pve", "rta"] = "pve",
    lock_winning_builds: bool = True,
) -> list[OptimizationResult]:
    """
    Optimiza secuencialmente un equipo de hasta 5-10 monstruos en orden de turno (Speed Tuning):
    - Ajusta automáticamente `max_spd` de cada miembro para no cortar al miembro anterior.
    - Calcula `min_spd` requerido por los ticks del modo (PVE 0.07 o RTA 0.015) y el boost de barra.
    - Retira del pool de runas disponibles las 6 runas asignadas a cada monstruo antes de optimizar el siguiente.
    """
    results: list[OptimizationResult] = []
    temp_locked_runes: set[int] = set()

    lead_combat_spd: int | None = None
    prev_combat_spd: int | None = None
    accumulated_boost = 0.0
    spd_buff_active = False

    for idx, req in enumerate(team_requests):
        member_cfg = req.constraints.model_copy(deep=True)

        if idx > 0 and prev_combat_spd is not None and lead_combat_spd is not None:
            # No puede superar la velocidad de combate del monstruo anterior - 1
            member_cfg.max_spd = min(member_cfg.max_spd, prev_combat_spd - 1)
            # Debe alcanzar al menos la velocidad mínima para no ser cortado tras el iniciador
            min_tuned_spd = calculate_min_follower_combat_spd(
                leader_combat_spd=lead_combat_spd,
                atb_boost_pct=accumulated_boost,
                spd_buff_active=spd_buff_active,
                mode=mode,
                step_offset=idx,
            )
            member_cfg.min_spd = max(member_cfg.min_spd, min_tuned_spd)
            if member_cfg.min_spd > member_cfg.max_spd:
                member_cfg.min_spd = member_cfg.max_spd

        pool = profile.get_available_runes(mode=mode, excluded_rune_ids=temp_locked_runes)
        res = optimize_monster_builds(
            monster=req.monster,
            available_runes=pool,
            constraints=member_cfg,
            artifacts=req.artifacts,
        )
        results.append(res)

        if res.builds:
            winning = res.builds[0]
            for rid in winning.rune_ids:
                temp_locked_runes.add(rid)
                if lock_winning_builds:
                    if mode == "rta":
                        profile.locked_runes_rta.add(rid)
                    else:
                        profile.locked_runes_pve.add(rid)

            if idx == 0:
                lead_combat_spd = winning.stats.combat_spd
            prev_combat_spd = winning.stats.combat_spd

        accumulated_boost += req.atb_boost_pct
        if req.spd_buff_turns > 0:
            spd_buff_active = True

    return results

