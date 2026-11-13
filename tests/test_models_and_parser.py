"""Pruebas unitarias para src/models.py, src/parser.py y src/sample_generator.py."""

from __future__ import annotations

from pathlib import Path

from scripts.sample_generator import ensure_sample_swex_file, generate_sample_swex_dict
from src.domain.models import MAIN_STAT_MAX_6STAR, Monster, Rune
from src.services.parser import BestiaryCache, parse_swex_json


def test_monster_base_hp_con_times_15() -> None:
    """Verifica la regla crítica de dominio: base_hp = con * 15."""
    lushen = Monster(
        unit_id=1001,
        unit_master_id=13513,
        name="Lushen",
        con=615,
        atk=900,
        def_=461,
        spd=103,
    )
    assert lushen.base_hp == 615 * 15
    assert lushen.base_hp == 9225


def test_rune_substat_effective_value_and_ancient_flag() -> None:
    """Verifica que sec_eff sume base_val + grind_val y detecte runas Ancient (class=16)."""
    raw_rune = {
        "rune_id": 999,
        "slot_no": 2,
        "set_id": 3,
        "class": 16,
        "upgrade_curr": 12,
        "pri_eff": [8, 31],
        "prefix_eff": [12, 8],
        "sec_eff": [
            [2, 18, 0, 7],   # HP%: 18 + 7 = 25
            [4, 15, 1, 6],   # ATK%: 15 + 6 = 21
            [9, 12, 0, 0],   # CRate%: 12
            [6, 10, 0, 5],   # DEF%: 10 + 5 = 15
        ],
    }
    rune = Rune.model_validate(raw_rune)
    assert rune.is_ancient is True
    assert rune.stars == 6
    assert rune.set_name == "Swift"
    assert rune.get_stat_total(2) == 25
    assert rune.get_stat_total(4) == 21
    assert rune.get_stat_total(12) == 8  # Innate
    assert rune.get_main_stat_val(simulate_plus15=False) == 31
    assert rune.get_main_stat_val(simulate_plus15=True) == MAIN_STAT_MAX_6STAR[8] == 42


def test_parse_swex_and_pve_rta_inventory_separation(tmp_path: Path) -> None:
    """
    Verifica que el parser cargue inventario + unit_list['runes'] y separe
    correctamente las asignaciones y bloqueos entre PVE y RTA.
    """
    cache = BestiaryCache(db_path=tmp_path / "test_bestiary.sqlite")
    sample_data = generate_sample_swex_dict(seed=42)
    profile = parse_swex_json(sample_data, bestiary=cache, fetch_remote_bestiary=False)

    # 12 monstruos en el sample
    assert len(profile.monsters) == 12
    # Lushen (1001) debe tener base_hp = 615 * 15 = 9225 y nombre sincronizado del bestiario
    lushen = profile.monsters[1001]
    assert lushen.name == "Lushen"
    assert lushen.base_hp == 9225
    assert len(lushen.runes) == 6
    assert len(lushen.rta_runes) == 0

    # Oliver (1011) no tiene runas en PVE pero sí tiene 6 runas equipadas en RTA
    oliver = profile.monsters[1011]
    assert oliver.name == "Oliver"
    assert len(oliver.runes) == 0
    assert len(oliver.rta_runes) == 6

    pve_equipped_oliver = profile.get_equipped_runes(1011, mode="pve")
    rta_equipped_oliver = profile.get_equipped_runes(1011, mode="rta")
    assert len(pve_equipped_oliver) == 0
    assert len(rta_equipped_oliver) == 6

    # Verificar unión total de runas: 6 monstruos * 6 runas PVE (36) + 108 inventario = 144
    assert len(profile.runes) == 144

    # Bloquear una runa en PVE no debe bloquearla en RTA
    first_lushen_rune_id = lushen.runes[0]
    profile.locked_runes_pve.add(first_lushen_rune_id)

    avail_pve = {r.rune_id for r in profile.get_available_runes(mode="pve")}
    avail_rta = {r.rune_id for r in profile.get_available_runes(mode="rta")}
    assert first_lushen_rune_id not in avail_pve
    assert first_lushen_rune_id in avail_rta


def test_ensure_sample_swex_file_creates_valid_json(tmp_path: Path) -> None:
    """Verifica que ensure_sample_swex_file cree el archivo sample_swex.json y sea parseable."""
    out_file = ensure_sample_swex_file(tmp_path / "sample_swex.json")
    assert out_file.exists()
    profile = parse_swex_json(out_file, BestiaryCache(tmp_path / "cache.sqlite"))
    assert profile.wizard_name == "KratosSW"
    assert len(profile.runes) == 144

