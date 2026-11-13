"""Pruebas unitarias para el motor de optimización Branch & Bound con Numba (src/optimizer.py)."""

from __future__ import annotations

from pathlib import Path

from scripts.sample_generator import generate_sample_swex_dict
from src.domain.models import Monster, Rune
from src.services.optimizer import (
    OptimizationConstraints,
    TeamOptimizationRequestMember,
    optimize_monster_builds,
    optimize_team_speed_tuning,
)
from src.services.parser import BestiaryCache, parse_swex_json


def test_optimizer_finds_valid_builds_with_constraints(tmp_path: Path) -> None:
    """Verifica que el optimizador encuentre builds válidas respetando sets y restricciones mínimas."""
    cache = BestiaryCache(tmp_path / "cache.sqlite")
    profile = parse_swex_json(generate_sample_swex_dict(seed=42), bestiary=cache)
    lushen = profile.monsters[1001]

    constraints = OptimizationConstraints(
        required_sets=[5, 4],  # Rage + Blade
        slot2_main_stats=[4, 8],
        slot4_main_stats=[10, 9],
        slot6_main_stats=[4],
        min_cr=70,
        min_spd=140,
        optimize_for="damage",
        max_runes_per_slot=20,
        top_k=5,
    )
    res = optimize_monster_builds(
        monster=lushen,
        available_runes=profile.get_available_runes(mode="pve"),
        constraints=constraints,
    )
    assert len(res.builds) >= 1
    assert res.pruned_triplets_246 > 0
    best = res.builds[0]
    assert "Rage" in best.stats.active_sets
    assert "Blade" in best.stats.active_sets
    assert best.stats.crate >= 70
    assert best.stats.combat_spd >= 140


def test_optimizer_intangible_completes_four_piece_set() -> None:
    """Verifica que el kernel Numba utilice una runa Intangible (set 25) para completar un set de 4 piezas."""
    monster = Monster(
        unit_id=99,
        unit_master_id=11013,
        name="Bernard",
        con=758,
        atk=538,
        def_=758,
        spd=111,
    )
    # 3 Swift (set 3), 1 Intangible (set 25), 2 Will (set 15) -> exactamente 1 runa por slot
    runes = [
        Rune.model_validate({"rune_id": 1, "slot_no": 1, "set_id": 3, "pri_eff": [3, 160], "sec_eff": [[8, 20, 0, 0]]}),
        Rune.model_validate({"rune_id": 2, "slot_no": 2, "set_id": 3, "pri_eff": [8, 42], "sec_eff": [[2, 20, 0, 0]]}),
        Rune.model_validate({"rune_id": 3, "slot_no": 3, "set_id": 3, "pri_eff": [5, 160], "sec_eff": [[8, 20, 0, 0]]}),
        Rune.model_validate({"rune_id": 4, "slot_no": 4, "set_id": 25, "pri_eff": [2, 63], "sec_eff": [[8, 20, 0, 0]]}),
        Rune.model_validate({"rune_id": 5, "slot_no": 5, "set_id": 15, "pri_eff": [1, 2448], "sec_eff": [[8, 20, 0, 0]]}),
        Rune.model_validate({"rune_id": 6, "slot_no": 6, "set_id": 15, "pri_eff": [6, 63], "sec_eff": [[8, 20, 0, 0]]}),
    ]
    cfg = OptimizationConstraints(
        required_sets=[3, 15],  # Swift + Will
        optimize_for="spd",
        top_k=3,
    )
    res = optimize_monster_builds(monster, runes, cfg)
    assert len(res.builds) == 1
    build = res.builds[0]
    assert "Swift" in build.stats.active_sets
    assert "Will" in build.stats.active_sets
    assert build.stats.intangible_replaced_set == "Swift"


def test_optimize_team_speed_tuning_no_duplicate_runes(tmp_path: Path) -> None:
    """
    Verifica que optimize_team_speed_tuning optimice un equipo en orden de turno
    sin reutilizar runas entre miembros y respetando el orden decreciente de Combat SPD.
    """
    cache = BestiaryCache(tmp_path / "cache.sqlite")
    profile = parse_swex_json(generate_sample_swex_dict(seed=42), bestiary=cache)

    bernard = profile.monsters[1007]
    galleon = profile.monsters[1008]
    lushen = profile.monsters[1001]

    team_reqs = [
        TeamOptimizationRequestMember(
            monster=bernard,
            constraints=OptimizationConstraints(
                required_sets=[3],  # Swift
                optimize_for="spd",
                max_runes_per_slot=15,
            ),
            atb_boost_pct=30.0,
            spd_buff_turns=2,
        ),
        TeamOptimizationRequestMember(
            monster=galleon,
            constraints=OptimizationConstraints(
                min_acc=40,
                optimize_for="spd",
                max_runes_per_slot=15,
            ),
        ),
        TeamOptimizationRequestMember(
            monster=lushen,
            constraints=OptimizationConstraints(
                min_cr=60,
                optimize_for="damage",
                max_runes_per_slot=15,
            ),
        ),
    ]

    results = optimize_team_speed_tuning(
        profile=profile,
        team_requests=team_reqs,
        mode="pve",
        lock_winning_builds=True,
    )
    assert len(results) == 3
    for r in results:
        assert len(r.builds) >= 1

    spd_1 = results[0].builds[0].stats.combat_spd
    spd_2 = results[1].builds[0].stats.combat_spd
    spd_3 = results[2].builds[0].stats.combat_spd
    assert spd_1 > spd_2 >= spd_3

    # Verificar que las 18 runas asignadas a los 3 monstruos sean disjuntas
    all_used_rune_ids: list[int] = []
    for r in results:
        all_used_rune_ids.extend(r.builds[0].rune_ids)
    assert len(all_used_rune_ids) == 18
    assert len(set(all_used_rune_ids)) == 18
    assert len(profile.locked_runes_pve) == 18
    assert len(profile.locked_runes_rta) == 0

