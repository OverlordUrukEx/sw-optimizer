"""Unit tests for MonsterDataService, O(1) lookup, fallback formatting, and UI monster filtering."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scripts.sample_generator import generate_sample_swex_dict
from src.app import build_monsters_dataframe, filter_monsters, format_monster_label
from src.services.monster_data_service import (
    DEFAULT_MONSTER_MAP_PATH,
    SWARFARM_ICON_BASE_URL,
    MonsterDataService,
    format_unknown_monster_name,
    infer_element_from_com2us_id,
)
from src.services.parser import parse_swex_json


def test_monster_data_service_o1_lookup_and_bundled_map() -> None:
    """Verifies that MonsterDataService loads bundled monster_map.json and resolves fields in O(1)."""
    assert DEFAULT_MONSTER_MAP_PATH.exists()
    service = MonsterDataService.get_instance()
    assert service.size >= 20

    lushen = service.get_monster_metadata(13413)
    assert lushen.name == "Lushen"
    assert lushen.element == "Wind"
    assert lushen.base_stars == 4
    assert lushen.awaken_level == 1
    assert lushen.image_filename.endswith(".png")
    assert lushen.icon_url == f"{SWARFARM_ICON_BASE_URL}{lushen.image_filename}"


def test_unknown_monster_fallback_format() -> None:
    """Verifies that unmapped monster IDs return 'Unknown Monster (#ID) - [Element]'."""
    service = MonsterDataService.get_instance()

    # Last digit 1 -> Water, 2 -> Fire, 3 -> Wind, 4 -> Light, 5 -> Dark
    unknown_fire = service.get_monster_metadata(999992)
    assert unknown_fire.name == "Unknown Monster (#999992) - [Fire]"
    assert unknown_fire.element == "Fire"
    assert unknown_fire.icon_url.startswith("data:image/svg+xml")

    unknown_dark = service.get_monster_metadata(888885)
    assert unknown_dark.name == "Unknown Monster (#888885) - [Dark]"
    assert unknown_dark.element == "Dark"

    assert infer_element_from_com2us_id(777771) == "Water"
    assert format_unknown_monster_name(777774) == "Unknown Monster (#777774) - [Light]"


def test_zero_n_plus_1_api_calls_during_swex_parse() -> None:
    """Ensures parse_swex_json performs zero per-unit HTTP calls even with unmapped monster IDs."""
    payload = generate_sample_swex_dict(seed=42)
    # Inject a brand-new unmapped monster into unit_list
    payload["unit_list"].append(
        {
            "unit_id": 9999,
            "unit_master_id": 987654,
            "unit_level": 40,
            "class": 6,
            "con": 700,
            "atk": 800,
            "def": 600,
            "spd": 105,
            "runes": [],
            "artifacts": [],
        }
    )

    with patch("httpx.Client.get", side_effect=AssertionError("HTTP call prohibited during parse!")) as mock_get:
        profile = parse_swex_json(payload, fetch_remote_bestiary=False)
        assert mock_get.call_count == 0

    new_mon = profile.monsters[9999]
    assert new_mon.name == "Unknown Monster (#987654) - [Light]"
    assert new_mon.element == "Light"
    assert new_mon.base_hp == 700 * 15


def test_monster_cache_version_and_expiration(tmp_path: Path) -> None:
    """Verifies local JSON cache save/load, version metadata, and TTL expiration."""
    custom_map = tmp_path / "monster_map.json"
    service = MonsterDataService(map_path=custom_map, ttl_seconds=3600)
    service.save_local_map()
    assert custom_map.exists()

    reloaded = MonsterDataService(map_path=custom_map, ttl_seconds=3600)
    assert reloaded.is_cache_expired() is False
    assert reloaded.is_cache_expired(now=reloaded.updated_at + 7200) is True

    browser_json = reloaded.export_browser_cache_json()
    assert '"version":1' in browser_json
    assert '"monsters":' in browser_json


def test_ui_monster_search_and_element_filter() -> None:
    """Verifies monster search by name and element filter in UI helpers."""
    profile = parse_swex_json(generate_sample_swex_dict(seed=42))

    wind_monsters = filter_monsters(profile.monsters.values(), elements=["Wind"])
    assert len(wind_monsters) >= 4
    assert all(m.element == "Wind" for m in wind_monsters)

    search_lushen = filter_monsters(profile.monsters.values(), search_query="lush")
    assert len(search_lushen) == 1
    assert search_lushen[0].name == "Lushen"
    assert "Lushen" in format_monster_label(search_lushen[0])
    assert "🌪️ Viento" in format_monster_label(search_lushen[0])

    wind_es = filter_monsters(profile.monsters.values(), elements=["Viento"])
    assert len(wind_es) == len(wind_monsters)

    df = build_monsters_dataframe(
        profile, search_query="o", selected_elements=["Agua", "Viento"]
    )
    assert not df.is_empty()
    assert "Avatar" in df.columns
    assert "Monstruo" in df.columns
    assert "Elemento" in df.columns
    assert "Estrellas" in df.columns


def test_sanitized_demo_swex_schema_parsing() -> None:
    """Verifies parsing against the sanitized SWEX schema (`src/data/demo_account.json`)."""
    demo_path = Path("src/data/demo_account.json")
    assert demo_path.exists()

    service = MonsterDataService.get_instance()
    lapis_meta = service.get_monster_metadata(19811)
    assert lapis_meta.name == "Lapis"
    assert lapis_meta.element == "Water"
    assert lapis_meta.image_filename == "unit_icon_0036_0_4.png"

    profile = parse_swex_json(demo_path, bestiary=service, fetch_remote_bestiary=False)
    assert profile.wizard_id == 10000001
    assert profile.wizard_name == "Demo_Summoner"
    assert len(profile.monsters) == 8
    assert len(profile.runes) >= 70

    lapis_units = [m for m in profile.monsters.values() if m.unit_master_id == 19811]
    assert len(lapis_units) == 1
    lapis_unit = lapis_units[0]
    assert lapis_unit.name == "Lapis"
    assert lapis_unit.element == "Water"
    assert lapis_unit.base_hp == 659 * 15

