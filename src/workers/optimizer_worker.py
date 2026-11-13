"""Background worker (`OptimizerWorker`) with chunked Branch & Bound execution and live progress callbacks."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time
from typing import Callable, Iterable, Literal

import numpy as np

from src.domain.stat_calculator import StatCalculator, normalize_ratio
from src.models import (
    SET_SIZES,
    AccountProfile,
    Artifact,
    Monster,
    Rune,
)
from src.optimizer import (
    _OPT_MODE_MAP,
    OptimizationConstraints,
    OptimizationResult,
    OptimizedBuild,
    TeamOptimizationRequestMember,
    _branch_and_bound_kernel,
    calculate_min_follower_combat_spd,
    filter_and_prune_runes_by_slot,
    runes_to_matrix,
)

ProgressCallback = Callable[["OptimizerProgressUpdate"], None]


@dataclass(frozen=True, slots=True)
class OptimizerProgressUpdate:
    """Immutable progress snapshot emitted by `OptimizerWorker` during Branch & Bound search."""

    progress_ratio: float
    evaluated_builds: int
    pruned_triplets_246: int
    total_triplets_246: int
    stage_label: str


class OptimizerWorker:
    """
    Dedicated background worker that offloads the combinatorial Branch & Bound
    rune permutation solver off the UI thread (`nogil=True` Numba kernel inside a worker thread),
    reporting live chunked progress updates (`0% -> 100%`) to keep the UI responsive.
    """

    def __init__(self, max_workers: int = 2, chunk_size_slot2: int = 3) -> None:
        self.max_workers = max(1, max_workers)
        self.chunk_size_slot2 = max(1, chunk_size_slot2)

    def run_monster_optimization(
        self,
        monster: Monster,
        available_runes: Iterable[Rune],
        constraints: OptimizationConstraints | None = None,
        artifacts: Iterable[Artifact] = (),
        on_progress: ProgressCallback | None = None,
    ) -> OptimizationResult:
        """
        Executes the Branch & Bound rune permutation solver in a background worker thread,
        partitioning Slot 2 candidates into chunks so `on_progress` receives real-time updates.
        """
        t0 = time.perf_counter()
        cfg = constraints or OptimizationConstraints()
        artifact_list = list(artifacts)

        if on_progress is not None:
            on_progress(
                OptimizerProgressUpdate(
                    progress_ratio=0.05,
                    evaluated_builds=0,
                    pruned_triplets_246=0,
                    total_triplets_246=0,
                    stage_label=f"Podando candidatos por Focus Stats para {monster.name}...",
                )
            )

        pruned_by_slot = filter_and_prune_runes_by_slot(available_runes, cfg)
        slot_lists = [pruned_by_slot[s] for s in range(1, 7)]
        matrices = [
            runes_to_matrix(lst, simulate_plus15=cfg.simulate_plus15)
            for lst in slot_lists
        ]

        n2 = matrices[1].shape[0]
        n4 = matrices[3].shape[0]
        n6 = matrices[5].shape[0]
        total_triplets = int(n2 * n4 * n6)

        if any(m.shape[0] == 0 for m in matrices):
            if on_progress is not None:
                on_progress(
                    OptimizerProgressUpdate(
                        progress_ratio=1.0,
                        evaluated_builds=0,
                        pruned_triplets_246=0,
                        total_triplets_246=total_triplets,
                        stage_label="Búsqueda finalizada (slots sin candidatos disponibles).",
                    )
                )
            return OptimizationResult(
                unit_id=monster.unit_id,
                monster_name=monster.name,
                evaluated_builds=0,
                pruned_triplets_246=0,
                total_triplets_246=total_triplets,
                elapsed_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                builds=[],
            )

        art_hp = sum(a.flat_hp for a in artifact_list)
        art_atk = sum(a.flat_atk for a in artifact_list)
        art_def = sum(a.flat_def for a in artifact_list)

        set_counter = Counter(cfg.required_sets)
        if set_counter:
            req_set_ids = np.array(list(set_counter.keys()), dtype=np.int32)
            req_set_counts = np.array(list(set_counter.values()), dtype=np.int32)
            total_req_pieces = sum(
                SET_SIZES.get(sid, 0) * cnt for sid, cnt in set_counter.items()
            )
        else:
            req_set_ids = np.zeros(0, dtype=np.int32)
            req_set_counts = np.zeros(0, dtype=np.int32)
            total_req_pieces = 0

        totem_plus_leader = normalize_ratio(cfg.sky_totem) + normalize_ratio(
            cfg.leader_skill_spd
        )
        opt_mode_int = _OPT_MODE_MAP.get(cfg.optimize_for, 0)
        top_k = max(1, cfg.top_k)

        # Partition Slot 2 matrix into slices so the background worker reports progress after each chunk
        chunk_sz = max(1, min(self.chunk_size_slot2, n2))
        slices: list[tuple[int, int]] = [
            (start, min(n2, start + chunk_sz)) for start in range(0, n2, chunk_sz)
        ]

        candidates: list[tuple[float, tuple[int, int, int, int, int, int]]] = []
        evaluated_total = 0
        pruned_246_total = 0

        with ThreadPoolExecutor(max_workers=1) as executor:
            for idx, (s2_start, s2_end) in enumerate(slices):
                m2_slice = matrices[1][s2_start:s2_end]
                future = executor.submit(
                    _branch_and_bound_kernel,
                    matrices[0],
                    m2_slice,
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
                c_scores, c_indices, c_eval, c_pruned, _ = future.result()
                evaluated_total += int(c_eval)
                pruned_246_total += int(c_pruned)

                for k in range(top_k):
                    if c_indices[k, 0] < 0 or c_scores[k] <= -1e17:
                        continue
                    global_indices = (
                        int(c_indices[k, 0]),
                        int(c_indices[k, 1]) + s2_start,
                        int(c_indices[k, 2]),
                        int(c_indices[k, 3]),
                        int(c_indices[k, 4]),
                        int(c_indices[k, 5]),
                    )
                    candidates.append((float(c_scores[k]), global_indices))

                if on_progress is not None:
                    ratio = min(0.95, 0.10 + 0.85 * ((idx + 1) / len(slices)))
                    on_progress(
                        OptimizerProgressUpdate(
                            progress_ratio=round(ratio, 3),
                            evaluated_builds=evaluated_total,
                            pruned_triplets_246=pruned_246_total,
                            total_triplets_246=total_triplets,
                            stage_label=(
                                f"Evaluando permutaciones para {monster.name}: "
                                f"{evaluated_total:,} builds válidas ({pruned_246_total:,}/{total_triplets:,} ramas podadas)"
                            ),
                        )
                    )

        candidates.sort(key=lambda item: item[0], reverse=True)
        top_candidates = candidates[:top_k]

        builds: list[OptimizedBuild] = []
        for rank, (score, idx_tuple) in enumerate(top_candidates, start=1):
            chosen_runes = [
                slot_lists[slot_idx][idx_tuple[slot_idx]] for slot_idx in range(6)
            ]
            stats = StatCalculator.calculate_monster_stats(
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
                    score=round(score, 2),
                    rune_ids=[r.rune_id for r in chosen_runes],
                    runes=chosen_runes,
                    stats=stats,
                )
            )

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if on_progress is not None:
            on_progress(
                OptimizerProgressUpdate(
                    progress_ratio=1.0,
                    evaluated_builds=evaluated_total,
                    pruned_triplets_246=pruned_246_total,
                    total_triplets_246=total_triplets,
                    stage_label=(
                        f"Optimización completada en {elapsed_ms:.2f} ms "
                        f"({len(builds)} builds encontradas)."
                    ),
                )
            )

        return OptimizationResult(
            unit_id=monster.unit_id,
            monster_name=monster.name,
            evaluated_builds=evaluated_total,
            pruned_triplets_246=pruned_246_total,
            total_triplets_246=total_triplets,
            elapsed_ms=elapsed_ms,
            builds=builds,
        )

    def run_team_optimization(
        self,
        profile: AccountProfile,
        team_requests: list[TeamOptimizationRequestMember],
        mode: Literal["pve", "rta"] = "pve",
        lock_winning_builds: bool = True,
        on_progress: ProgressCallback | None = None,
    ) -> list[OptimizationResult]:
        """
        Sequentially optimizes a full Speed-Tuned team in the background worker,
        reporting aggregate progress across all team members.
        """
        results: list[OptimizationResult] = []
        temp_locked_runes: set[int] = set()

        lead_combat_spd: int | None = None
        prev_combat_spd: int | None = None
        accumulated_boost = 0.0
        spd_buff_active = False
        total_members = max(1, len(team_requests))

        for idx, req in enumerate(team_requests):
            member_cfg = req.constraints.model_copy(deep=True)

            if idx > 0 and prev_combat_spd is not None and lead_combat_spd is not None:
                member_cfg.max_spd = min(member_cfg.max_spd, prev_combat_spd - 1)
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

            pool = profile.get_available_runes(
                mode=mode, excluded_rune_ids=temp_locked_runes
            )

            def _member_progress(update: OptimizerProgressUpdate, m_idx: int = idx) -> None:
                if on_progress is not None:
                    overall_ratio = (m_idx + update.progress_ratio) / total_members
                    on_progress(
                        OptimizerProgressUpdate(
                            progress_ratio=round(min(1.0, overall_ratio), 3),
                            evaluated_builds=update.evaluated_builds,
                            pruned_triplets_246=update.pruned_triplets_246,
                            total_triplets_246=update.total_triplets_246,
                            stage_label=f"[Turno #{m_idx + 1}/{total_members}] {update.stage_label}",
                        )
                    )

            res = self.run_monster_optimization(
                monster=req.monster,
                available_runes=pool,
                constraints=member_cfg,
                artifacts=req.artifacts,
                on_progress=_member_progress if on_progress is not None else None,
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
