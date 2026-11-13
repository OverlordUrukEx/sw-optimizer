"""Unit tests for Sanitized Demo Mode (src/data/demo_account.json), HelpGuideModal, and Onboarding UI state."""

from __future__ import annotations

import json

from src.services.optimizer import OptimizationConstraints, optimize_monster_builds
from src.ui.ui_components import (
    DEMO_ACCOUNT_PATH,
    TOOLTIPS,
    HelpGuideModal,
    load_demo_account_profile,
)


def test_demo_account_json_schema_and_size() -> None:
    """
    Verifies that src/data/demo_account.json:
    - Exists and is under 150 KB
    - Has anonymized wizard_info (wizard_id=10000001, wizard_name='Demo_Summoner', wizard_level=100)
    - Contains 8 diverse units including 19811, 22911, 11031, 11532, and 1000113 ('Demo_Homu')
    - Contains 30 additional unequipped runes
    - Strips non-essential root arrays
    """
    assert DEMO_ACCOUNT_PATH.exists()
    size_kb = DEMO_ACCOUNT_PATH.stat().st_size / 1024.0
    assert size_kb < 150.0

    raw = json.loads(DEMO_ACCOUNT_PATH.read_text(encoding="utf-8"))
    assert raw["wizard_info"]["wizard_id"] == 10000001
    assert raw["wizard_info"]["wizard_name"] == "Demo_Summoner"
    assert raw["wizard_info"]["wizard_level"] == 100

    assert len(raw["unit_list"]) == 8
    assert len(raw["runes"]) == 30

    for forbidden_key in ("scenario_list", "quest_active", "quest_rewarded", "friend_list", "helper_list"):
        assert forbidden_key not in raw

    unit_mids = {u["unit_master_id"] for u in raw["unit_list"]}
    for required_mid in (19811, 22911, 11031, 11532, 1000113):
        assert required_mid in unit_mids

    homu_units = [u for u in raw["unit_list"] if u["unit_master_id"] == 1000113]
    assert len(homu_units) == 1
    assert homu_units[0]["homunculus_name"] == "Demo_Homu"


def test_load_demo_account_profile_and_optimize() -> None:
    """Verifies that the demo account loads into AccountProfile and runs an optimization."""
    profile = load_demo_account_profile()
    assert profile.wizard_id == 10000001
    assert profile.wizard_name == "Demo_Summoner"
    assert len(profile.monsters) == 8
    assert len(profile.runes) == 78  # 8 * 6 equipped + 30 unequipped

    homu = next(m for m in profile.monsters.values() if m.unit_master_id == 1000113)
    assert "Demo_Homu" in homu.name

    lapis = next(m for m in profile.monsters.values() if m.unit_master_id == 19811)
    assert lapis.name == "Lapis"

    res = optimize_monster_builds(
        monster=lapis,
        available_runes=profile.get_available_runes(mode="pve"),
        constraints=OptimizationConstraints(
            min_spd=120,
            optimize_for="damage",
            max_runes_per_slot=12,
            top_k=5,
        ),
    )
    assert len(res.builds) >= 1


def test_help_guide_modal_and_tooltips_content() -> None:
    """Verifies HelpGuideModal 3-step Spanish content, i18n dictionary, and technical UI tooltips."""
    from src.i18n import ES_DICT, STAT_TOOLTIPS_ES

    assert "Summoners War Exporter" in HelpGuideModal.STEP_1_SWEX_MD
    assert "HubUserLogin" in HelpGuideModal.STEP_1_SWEX_MD
    assert "Cargar JSON" in HelpGuideModal.STEP_1_SWEX_MD
    assert "con" in HelpGuideModal.STEP_2_STATS_MD.lower()
    assert "grind" in HelpGuideModal.STEP_2_STATS_MD.lower()
    assert "Ancient" in HelpGuideModal.STEP_2_STATS_MD
    assert "Runa Antigua" in HelpGuideModal.STEP_2_STATS_MD
    assert "Intangible" in HelpGuideModal.STEP_3_OPTIMIZER_MD
    assert "Broken" in HelpGuideModal.STEP_3_OPTIMIZER_MD
    assert "Calcular Builds" in HelpGuideModal.STEP_3_OPTIMIZER_MD

    assert ES_DICT["navbar"]["upload_json"] == "Cargar JSON"
    assert ES_DICT["navbar"]["try_demo"] == "Probar Cuenta Demo"
    assert ES_DICT["navbar"]["switch_or_clear"] == "Cambiar Cuenta / Limpiar"
    assert ES_DICT["navbar"]["help_guide"] == "Guía de Uso"
    assert ES_DICT["optimizer"]["panel_title"] == "Optimizador de Builds"
    assert ES_DICT["optimizer"]["calculate_builds"] == "Calcular Builds"
    assert ES_DICT["optimizer"]["results_found"] == "Resultados encontrados"

    for stat_key in ("HP", "ATK", "DEF", "SPD", "CR", "CD", "RES", "ACC", "EHP"):
        assert stat_key in STAT_TOOLTIPS_ES

    for required_tooltip in (
        "effective_hp",
        "damage_multiplier",
        "include_equipped_runes",
        "broken_sets",
        "intangible_wildcard",
    ):
        assert required_tooltip in TOOLTIPS
        assert len(TOOLTIPS[required_tooltip]) > 20
