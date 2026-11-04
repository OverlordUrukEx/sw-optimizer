"""Pruebas unitarias para src/calculator.py (Eficiencia Barion, +15, Intangible, EHP y Speed Tuning)."""

from __future__ import annotations

import math
import pytest

from src.calculator import (
    PVE_TICK_SIZE,
    RTA_TICK_SIZE,
    SpeedTuneMember,
    calculate_combat_spd,
    calculate_ehp,
    calculate_min_follower_combat_spd,
    calculate_monster_stats,
    calculate_rune_efficiency,
    evaluate_active_sets,
    simulate_rune_plus15,
    simulate_speed_tuning,
)
from src.models import Monster, Rune


def test_barion_rune_efficiency_formula() -> None:
    """
    Valida la fórmula exacta de Barion:
    Eficiencia = ((1.0 + sum(val_efectivo / max_roll_6star)) / 2.8) * 100
    Max rolls: HP%/ATK%/DEF%/ACC%/RES% = 40 | SPD/CRate = 30 | CDmg = 35 | HP flat = 1875 | ATK/DEF flat = 100
    """
    rune = Rune.model_validate(
        {
            "rune_id": 1,
            "slot_no": 1,
            "set_id": 13,
            "class": 6,
            "upgrade_curr": 15,
            "pri_eff": [3, 160],
            "prefix_eff": [9, 6],  # CRate 6 / 30 = 0.20
            "sec_eff": [
                [8, 18, 0, 6],     # SPD (18+6)=24 / 30 = 0.80
                [2, 16, 0, 4],     # HP% (16+4)=20 / 40 = 0.50
                [4, 14, 1, 6],     # ATK% (14+6)=20 / 40 = 0.50
                [10, 7, 0, 0],     # CDmg 7 / 35 = 0.20
            ],
        }
    )
    # Suma ratios con grinds + innate = 0.20 + 0.80 + 0.50 + 0.50 + 0.20 = 2.20
    # Eficiencia = ((1.0 + 2.20) / 2.8) * 100 = (3.20 / 2.8) * 100 = 114.2857 -> 114.29%
    eff_with_grinds = calculate_rune_efficiency(rune, include_innate=True, use_grinds=True)
    assert eff_with_grinds == pytest.approx(114.29, abs=0.01)

    # Sin grinds: CR 6/30 (0.2) + SPD 18/30 (0.6) + HP 16/40 (0.4) + ATK 14/40 (0.35) + CD 7/35 (0.2) = 1.75
    # ((1.0 + 1.75) / 2.8) * 100 = 98.21%
    eff_ungrinded = calculate_rune_efficiency(rune, include_innate=True, use_grinds=False)
    assert eff_ungrinded == pytest.approx(98.21, abs=0.01)


def test_simulate_rune_plus15() -> None:
    """Verifica que una runa 6★ a +12 suba su estadística principal al máximo de +15."""
    r_plus12 = Rune.model_validate(
        {
            "rune_id": 10,
            "slot_no": 4,
            "set_id": 5,
            "class": 6,
            "upgrade_curr": 12,
            "pri_eff": [10, 58],  # CDmg a +12
            "prefix_eff": [0, 0],
            "sec_eff": [[8, 15, 0, 0]],
        }
    )
    r_sim = simulate_rune_plus15(r_plus12)
    assert r_sim.upgrade_curr == 15
    assert r_sim.main_stat_val == 80  # CDmg 6★ a +15 = 80


def test_intangible_set_wildcard_logic() -> None:
    """
    Verifica la lógica de runa Intangible (set_id = 25):
    - Completa un set de 4 piezas cuando hay 3 piezas + 1 Intangible.
    - Completa un set de 2 piezas cuando hay 4 piezas de un set + 1 de otro + 1 Intangible.
    - Máximo 1 Intangible activa (2 Intangible + 2 Swift NO completan Swift).
    """
    def _dummy_rune(slot: int, set_id: int) -> Rune:
        return Rune.model_validate(
            {
                "rune_id": slot,
                "slot_no": slot,
                "set_id": set_id,
                "class": 6,
                "upgrade_curr": 15,
                "pri_eff": [1, 2448],
            }
        )

    # Caso 1: 3 Swift (3) + 1 Intangible (25) + 2 Will (15) -> Activos: Swift (3) y Will (15)
    runes_case1 = [
        _dummy_rune(1, 3),
        _dummy_rune(2, 3),
        _dummy_rune(3, 3),
        _dummy_rune(4, 25),
        _dummy_rune(5, 15),
        _dummy_rune(6, 15),
    ]
    active1, replaced1 = evaluate_active_sets(runes_case1)
    assert active1 == [3, 15]
    assert replaced1 == 3

    # Caso 2: 4 Rage (5) + 1 Blade (4) + 1 Intangible (25) -> Activos: Blade (4) y Rage (5)
    runes_case2 = [
        _dummy_rune(1, 5),
        _dummy_rune(2, 5),
        _dummy_rune(3, 5),
        _dummy_rune(4, 5),
        _dummy_rune(5, 4),
        _dummy_rune(6, 25),
    ]
    active2, replaced2 = evaluate_active_sets(runes_case2)
    assert active2 == [4, 5]
    assert replaced2 == 4

    # Caso 3: 2 Swift (3) + 2 Intangible (25) + 2 Will (15) -> Solo Will (15) está activo
    runes_case3 = [
        _dummy_rune(1, 3),
        _dummy_rune(2, 3),
        _dummy_rune(3, 25),
        _dummy_rune(4, 25),
        _dummy_rune(5, 15),
        _dummy_rune(6, 15),
    ]
    active3, replaced3 = evaluate_active_sets(runes_case3)
    assert active3 == [15]
    assert replaced3 is None


def test_monster_final_stats_and_ehp_formulas() -> None:
    """
    Valida las fórmulas exactas:
    - Total_HP = Base_HP + round(Base_HP * (Sum_HP% / 100)) + Sum_HP_Flat
    - Combat_SPD = Base_SPD + Rune_SPD + ceil(Base_SPD * (Sky_Totem_0.15 + Leader_Skill_SPD + Swift_Bonus_0.25))
    - Effective_HP (EHP) = Total_HP * (1140 + (Total_DEF * 3.5)) / 1000
    """
    monster = Monster(
        unit_id=1007,
        unit_master_id=11013,
        name="Bernard 2A",
        con=758,     # base_hp = 11370
        atk=538,
        def_=758,
        spd=111,
        critical_rate=15,
        critical_damage=50,
        resist=15,
        accuracy=0,
    )
    # 3 Swift (set 3) + 1 Intangible (set 25) + 2 Energy (set 1) => Swift (+25% SPD) + Energy (+15% HP)
    runes = [
        Rune.model_validate({"rune_id": 1, "slot_no": 1, "set_id": 3, "pri_eff": [3, 160], "sec_eff": [[8, 25, 0, 5], [2, 20, 0, 0]]}),
        Rune.model_validate({"rune_id": 2, "slot_no": 2, "set_id": 3, "pri_eff": [8, 42], "sec_eff": [[2, 30, 0, 0], [6, 20, 0, 0]]}),
        Rune.model_validate({"rune_id": 3, "slot_no": 3, "set_id": 3, "pri_eff": [5, 160], "sec_eff": [[8, 25, 0, 5], [6, 30, 0, 0]]}),
        Rune.model_validate({"rune_id": 4, "slot_no": 4, "set_id": 25, "pri_eff": [2, 63], "sec_eff": [[8, 25, 0, 5]]}),
        Rune.model_validate({"rune_id": 5, "slot_no": 5, "set_id": 1, "pri_eff": [1, 2448], "sec_eff": [[8, 25, 0, 5]]}),
        Rune.model_validate({"rune_id": 6, "slot_no": 6, "set_id": 1, "pri_eff": [6, 63], "sec_eff": [[8, 25, 0, 5]]}),
    ]
    # Sum_HP% = 20 (slot1) + 30 (slot2) + 63 (slot4) + 15 (Set Energy) = 128%
    # Sum_HP_Flat = 2448 (slot5)
    # Total_HP = 11370 + round(11370 * 1.28) + 2448 = 11370 + 14554 + 2448 = 28372
    # Sum_DEF% = 20 (slot2) + 30 (slot3) + 63 (slot6) = 113%
    # Sum_DEF_Flat = 160 (slot3)
    # Total_DEF = 758 + round(758 * 1.13) + 160 = 758 + 857 + 160 = 1775
    # Rune_SPD = 42 + 5 * 30 = 192
    # Combat_SPD (con líder 24% y Sky Totem 15% y Swift 25%) = 111 + 192 + ceil(111 * (0.15 + 0.24 + 0.25))
    # 111 * 0.64 = 71.04 -> ceil = 72 -> Combat_SPD = 111 + 192 + 72 = 375
    stats = calculate_monster_stats(
        monster=monster,
        runes=runes,
        sky_totem=0.15,
        leader_skill_spd=0.24,
    )
    assert "Swift" in stats.active_sets
    assert "Energy" in stats.active_sets
    assert stats.intangible_replaced_set == "Swift"
    assert stats.total_hp == 28372
    assert stats.total_def == 1775
    assert stats.rune_spd == 192
    assert stats.combat_spd == 375

    expected_ehp = round(28372 * (1140 + 1775 * 3.5) / 1000.0, 2)
    assert stats.ehp == expected_ehp
    assert calculate_ehp(28372, 1775) == expected_ehp


def test_speed_tuning_pve_and_rta_ticks() -> None:
    """
    Verifica el motor de Speed Tuning con ticks PVE (0.07) y RTA (0.015),
    validando orden de turnos y detección de cortes.
    """
    assert PVE_TICK_SIZE == 0.07
    assert RTA_TICK_SIZE == 0.015

    # Equipo PVE bien tuneado: Loren -> Kro -> Verdehile
    team_pve_ok = [
        SpeedTuneMember(unit_id=1, name="Loren", base_spd=102, rune_spd=95),
        SpeedTuneMember(unit_id=2, name="Kro", base_spd=108, rune_spd=75),
        SpeedTuneMember(unit_id=3, name="Verdehile", base_spd=99, rune_spd=68),
    ]
    report_pve = simulate_speed_tuning(team_pve_ok, mode="pve", sky_totem=0.15)
    assert report_pve.tick_size == 0.07
    assert report_pve.is_perfectly_tuned is True
    assert report_pve.turn_sequence == ["Loren", "Kro", "Verdehile"]

    # Equipo RTA desordenado (el 3er monstruo es más rápido que el 2do)
    team_rta_bad = [
        SpeedTuneMember(unit_id=10, name="Tiana", base_spd=96, rune_spd=195, swift_active=True, atb_boost_pct=30.0),
        SpeedTuneMember(unit_id=11, name="Galleon", base_spd=108, rune_spd=110),
        SpeedTuneMember(unit_id=12, name="Seara", base_spd=100, rune_spd=145),
    ]
    report_rta = simulate_speed_tuning(team_rta_bad, mode="rta", sky_totem=0.15, leader_skill_spd=0.24)
    assert report_rta.tick_size == 0.015
    assert report_rta.is_perfectly_tuned is False
    assert report_rta.turn_sequence == ["Tiana", "Seara", "Galleon"]

    # Verificar que calculate_min_follower_combat_spd devuelva un valor consistente
    tiana_c_spd = calculate_combat_spd(96, 195, swift_active=True, sky_totem=0.15, leader_skill_spd=0.24)
    min_ally_spd = calculate_min_follower_combat_spd(
        leader_combat_spd=tiana_c_spd,
        atb_boost_pct=30.0,
        mode="rta",
        step_offset=1,
    )
    assert min_ally_spd > 0
    assert min_ally_spd < tiana_c_spd

