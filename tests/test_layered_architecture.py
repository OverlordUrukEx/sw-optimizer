"""Unit and integration tests for the Clean Layered Architecture (`src/domain/`, `src/services/storage/`, `src/workers/`)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.domain import (
    RuneSetMechanics,
    StatCalculator,
)
from src.models import Monster, Rune, RuneSubstat
from src.optimizer import OptimizationConstraints, TeamOptimizationRequestMember
from src.services.storage import (
    INDEXED_DB_NAME,
    AccountStorageService,
)
from src.ui_components import load_demo_account_profile
from src.workers import OptimizerProgressUpdate, OptimizerWorker


def _make_rune(
    rune_id: int,
    slot_no: int,
    set_id: int,
    main_stat_id: int = 8,
    main_val: int = 42,
    spd_sub: int = 18,
) -> Rune:
    return Rune(
        rune_id=rune_id,
        slot_no=slot_no,
        set_id=set_id,
        rank=5,
         rune_class=6,
        upgrade_curr=15,
        pri_eff=(main_stat_id, main_val),
        prefix_eff=(0, 0),
        sec_eff=[
            RuneSubstat(stat_id=8, base_val=spd_sub, enchanted=0, grind_val=4),
            RuneSubstat(stat_id=9, base_val=13, enchanted=0, grind_val=0),
            RuneSubstat(stat_id=10, base_val=15, enchanted=0, grind_val=0),
            RuneSubstat(stat_id=4, base_val=16, enchanted=0, grind_val=5),
        ],
    )


def test_domain_rune_set_mechanics_4set_2set_and_intangible() -> None:
    """Verifies `RuneSetMechanics` resolves 4-piece, 2-piece, Broken, and Set 25 Intangible wildcard rules."""
    # 3 Swift (set 3) + 1 Intangible (set 25) + 2 Will (set 15) -> Swift + Will completed
    active_ids, replaced = RuneSetMechanics.resolve_active_sets_from_ids(
        [3, 3, 3, 25, 15, 15]
    )
    assert active_ids == [3, 15]
    assert replaced == 3
    assert not RuneSetMechanics.is_broken_set(active_ids)
    assert RuneSetMechanics.format_active_set_names(active_ids) == ["Swift", "Will"]

    # 3 Fatal (set 8) + 1 Blade (set 4) + 1 Intangible (set 25) + 1 Energy (set 1)
    # Intangible prioritizes completing the 4-piece Fatal set over 2-piece sets
    active_ids_2, replaced_2 = RuneSetMechanics.resolve_active_sets_from_ids(
        [8, 8, 8, 4, 25, 1]
    )
    assert active_ids_2 == [8]
    assert replaced_2 == 8
    assert RuneSetMechanics.is_broken_set(active_ids_2)

    # Declarative set bonus vector check
    bonuses = RuneSetMechanics.compute_set_bonuses([1, 4, 5, 8, 3], ally_fight_sets=2)
    assert bonuses.hp_pct == 15.0
    assert bonuses.crate == 12
    assert bonuses.cdmg == 40
    assert bonuses.atk_pct == 35.0 + 16.0  # Fatal (35%) + 2x Fight (16%)
    assert bonuses.swift_active is True


def test_domain_stat_calculator_single_source_of_truth() -> None:
    """Verifies `StatCalculator` computes monster stats, EHP, damage score, and Barion efficiency."""
    mon = Monster(
        unit_id=1,
        unit_master_id=13413,
        name="Lushen",
        element="Wind",
        con=615,  # base_hp = 9225
        atk=900,
        def_=461,
        spd=103,
        critical_rate=15,
        critical_damage=50,
        resist=15,
        accuracy=0,
    )
    runes = [
        _make_rune(101, 1, 8, main_stat_id=3, main_val=160),
        _make_rune(102, 2, 8, main_stat_id=8, main_val=42),
        _make_rune(103, 3, 8, main_stat_id=5, main_val=160),
        _make_rune(104, 4, 25, main_stat_id=10, main_val=80),  # Intangible completes Fatal
        _make_rune(105, 5, 4, main_stat_id=1, main_val=2448),
        _make_rune(106, 6, 4, main_stat_id=4, main_val=63),
    ]
    stats = StatCalculator.calculate_monster_stats(mon, runes, sky_totem=0.15)
    assert stats.active_sets == ["Blade", "Fatal"]
    assert stats.intangible_replaced_set == "Fatal"
    assert stats.crate == 100  # Capped at 100%
    assert stats.ehp == StatCalculator.calculate_ehp(stats.total_hp, stats.total_def)
    assert StatCalculator.calculate_damage_score(stats.total_atk, stats.crate, stats.cdmg) > stats.total_atk


def test_account_storage_service_persistence_and_indexeddb_bridge(tmp_path: Path) -> None:
    """Verifies `AccountStorageService` saves, restores across page reloads (F5), and clears cleanly."""
    snapshot_file = tmp_path / "active_account_state.json"
    storage = AccountStorageService(snapshot_path=snapshot_file)

    assert storage.restore_account() is None

    demo_profile = load_demo_account_profile()
    demo_profile.locked_runes_pve.add(999001)

    envelope = asyncio.run(
        storage.save_account_async(
            profile=demo_profile,
            is_demo_mode=True,
            file_signature="demo_sig_123",
        )
    )
    assert snapshot_file.exists()
    assert envelope.profile.wizard_name == "Demo_Summoner"

    # Simulate page reload (F5) with a brand-new service instance reading the persisted snapshot
    reloaded_storage = AccountStorageService(snapshot_path=snapshot_file)
    restored = asyncio.run(reloaded_storage.restore_account_async())
    assert restored is not None
    assert restored.is_demo_mode is True
    assert restored.file_signature == "demo_sig_123"
    assert restored.profile.wizard_name == "Demo_Summoner"
    assert len(restored.profile.monsters) == 8
    assert 999001 in restored.profile.locked_runes_pve

    # Verify IndexedDB bridge script uses window.indexedDB (SWOptimizerDB) instead of 5MB localStorage
    from src.monster_data_service import MonsterDataService

    bridge_html = AccountStorageService.build_indexeddb_bridge_html(
        monster_service=MonsterDataService.get_instance(),
        profile=restored.profile,
        is_demo_mode=True,
        file_signature="demo_sig_123",
    )
    assert INDEXED_DB_NAME in bridge_html
    assert "window.indexedDB.open" in bridge_html
    assert "Demo_Summoner" in bridge_html

    # Clear account state ("Cambiar Cuenta / Limpiar")
    asyncio.run(reloaded_storage.clear_account_async())
    assert not snapshot_file.exists()
    assert reloaded_storage.restore_account() is None


def test_optimizer_worker_background_execution_with_progress() -> None:
    """Verifies `OptimizerWorker` offloads Branch & Bound search and emits live progress updates."""
    demo_profile = load_demo_account_profile()
    target_monster = next(iter(demo_profile.monsters.values()))
    available_runes = demo_profile.get_available_runes(mode="pve")

    worker = OptimizerWorker(chunk_size_slot2=2)
    progress_events: list[OptimizerProgressUpdate] = []

    result = worker.run_monster_optimization(
        monster=target_monster,
        available_runes=available_runes,
        constraints=OptimizationConstraints(
            min_spd=120,
            max_runes_per_slot=10,
            top_k=5,
        ),
        on_progress=progress_events.append,
    )

    assert len(progress_events) >= 2
    assert progress_events[0].progress_ratio > 0.0
    assert progress_events[-1].progress_ratio == 1.0
    assert result.unit_id == target_monster.unit_id
    assert len(result.builds) > 0

    # Also test team optimization through OptimizerWorker
    monsters_list = list(demo_profile.monsters.values())[:2]
    team_events: list[OptimizerProgressUpdate] = []
    team_reqs = [
        TeamOptimizationRequestMember(
            monster=m,
            constraints=OptimizationConstraints(max_runes_per_slot=8, top_k=2),
        )
        for m in monsters_list
    ]
    team_results = worker.run_team_optimization(
        profile=demo_profile,
        team_requests=team_reqs,
        mode="pve",
        lock_winning_builds=False,
        on_progress=team_events.append,
    )
    assert len(team_results) == 2
    assert len(team_events) >= 2
    assert team_events[-1].progress_ratio == 1.0
