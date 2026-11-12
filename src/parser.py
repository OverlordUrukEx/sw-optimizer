"""SWEX JSON parser and Bestiary integration powered by O(1) MonsterDataService."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.models import (
    AccountProfile,
    Artifact,
    Monster,
    MonsterMasterData,
    Rune,
)
from src.monster_data_service import (
    DEFAULT_MONSTER_MAP_PATH,
    MonsterDataService,
    MonsterMetadata,
    format_unknown_monster_name,
    infer_element_from_com2us_id,
)


class BestiaryCache:
    """
    Backward-compatible adapter wrapping `MonsterDataService` for O(1) lookups.
    Eliminates per-monster SQLite queries and N+1 HTTP calls.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_MONSTER_MAP_PATH
        if self.db_path.suffix == ".json":
            self.service = MonsterDataService(map_path=self.db_path)
        else:
            self.service = MonsterDataService.get_instance()

    def get(self, com2us_id: int) -> MonsterMasterData | None:
        meta = self.service._map.get(int(com2us_id))
        if meta is None:
            return None
        return MonsterMasterData(
            com2us_id=meta.com2us_id,
            name=meta.name,
            element=meta.element,
            awaken_level=meta.awaken_level,
            base_stars=meta.base_stars,
            image_filename=meta.image_filename,
        )

    def set(self, master_data: MonsterMasterData) -> None:
        self.service.register_monster(
            MonsterMetadata(
                com2us_id=master_data.com2us_id,
                name=master_data.name,
                element=master_data.element,
                base_stars=master_data.base_stars,
                awaken_level=master_data.awaken_level,
                image_filename=master_data.image_filename,
            )
        )

    def fetch_or_sync(
        self,
        com2us_id: int,
        fetch_remote: bool = False,
        element_hint: str | int | None = None,
    ) -> MonsterMasterData:
        """Performs an O(1) in-memory lookup via MonsterDataService without N+1 HTTP calls."""
        meta = self.service.get_monster_metadata(
            com2us_id=com2us_id, element_hint=element_hint
        )
        return MonsterMasterData(
            com2us_id=meta.com2us_id,
            name=meta.name,
            element=meta.element,
            awaken_level=meta.awaken_level,
            base_stars=meta.base_stars,
            image_filename=meta.image_filename,
        )


def _extract_unit_runes(raw_runes: Any) -> list[dict[str, Any]]:
    """Normalizes unit['runes'] whether provided as a list of dicts or a slot-keyed dict."""
    if isinstance(raw_runes, list):
        return [r for r in raw_runes if isinstance(r, dict)]
    if isinstance(raw_runes, dict):
        return [r for r in raw_runes.values() if isinstance(r, dict)]
    return []


def _load_json_payload(source: str | Path | bytes | dict[str, Any]) -> dict[str, Any]:
    """Validates and parses raw SWEX JSON input into a dictionary."""
    if isinstance(source, dict):
        data = source
    elif isinstance(source, (bytes, bytearray)):
        try:
            data = json.loads(source.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Invalid UTF-8 JSON bytes: {exc}") from exc
    elif isinstance(source, str):
        path_candidate = Path(source)
        if len(source) < 260 and path_candidate.exists() and path_candidate.is_file():
            try:
                data = json.loads(path_candidate.read_text(encoding="utf-8"))
            except Exception as exc:
                raise ValueError(
                    f"Failed to parse JSON file '{path_candidate}': {exc}"
                ) from exc
        else:
            try:
                data = json.loads(source)
            except Exception as exc:
                raise ValueError(f"Invalid JSON string: {exc}") from exc
    elif isinstance(source, Path):
        if not source.exists() or not source.is_file():
            raise ValueError(f"SWEX JSON file not found: {source}")
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Failed to parse JSON file '{source}': {exc}") from exc
    else:
        raise TypeError(f"Unsupported SWEX source type: {type(source)}")

    if not isinstance(data, dict):
        raise ValueError("SWEX JSON root must be a JSON object.")
    if "unit_list" not in data and "runes" not in data:
        raise ValueError(
            "Invalid SWEX JSON format: missing required 'unit_list' and 'runes' keys."
        )
    return data


def parse_swex_json(
    source: str | Path | bytes | dict[str, Any],
    bestiary: BestiaryCache | MonsterDataService | None = None,
    fetch_remote_bestiary: bool = False,
) -> AccountProfile:
    """
    Parses a SWEX (Summoners War Exporter) JSON file or dictionary into an AccountProfile.

    Domain & Architectural Rules:
    - Zero N+1 API Calls: Resolves `unit_master_id` (`com2us_id`) in O(1) time from `MonsterDataService`.
    - Base HP Rule: `base_hp = con * 15`.
    - Unmapped Monster Fallback: `"Unknown Monster (#ID) - [Element]"`.
    - PVE Inventory: union of `json['runes']` + `unit['runes']` across `unit_list`.
    - RTA Inventory: mapped via `json['world_arena_rune_equip_list']` (`rune_id -> occupied_id`).
    """
    data = _load_json_payload(source)

    if isinstance(bestiary, MonsterDataService):
        monster_service = bestiary
    elif isinstance(bestiary, BestiaryCache):
        monster_service = bestiary.service
    else:
        monster_service = MonsterDataService.get_instance()

    # Optional single bulk sync before parsing (never per monster)
    if fetch_remote_bestiary and monster_service.is_cache_expired():
        try:
            monster_service.sync_from_swarfarm(force=False)
        except Exception:
            pass

    wizard_info = data.get("wizard_info") or {}
    if not isinstance(wizard_info, dict):
        wizard_info = {}
    wizard_id = int(wizard_info.get("wizard_id", data.get("wizard_id", 0)) or 0)
    wizard_name = str(wizard_info.get("wizard_name", "Summoner") or "Summoner")
    wizard_level = int(wizard_info.get("wizard_level", data.get("wizard_level", 50)) or 50)
    wizard_mana = int(wizard_info.get("wizard_mana", data.get("wizard_mana", 0)) or 0)
    wizard_crystal = int(wizard_info.get("wizard_crystal", data.get("wizard_crystal", 0)) or 0)

    runes_by_id: dict[int, Rune] = {}
    artifacts_by_id: dict[int, Artifact] = {}
    monsters_by_id: dict[int, Monster] = {}

    # 1. Un-equipped inventory runes (json["runes"])
    for raw_rune in data.get("runes") or []:
        if not isinstance(raw_rune, dict) or "rune_id" not in raw_rune:
            continue
        rune_payload = dict(raw_rune)
        rune_payload["occupied_id"] = int(rune_payload.get("occupied_id", 0) or 0)
        rune = Rune.model_validate(rune_payload)
        runes_by_id[rune.rune_id] = rune

    # 2. Un-equipped inventory artifacts (json["artifacts"])
    for raw_art in data.get("artifacts") or []:
        if not isinstance(raw_art, dict):
            continue
        art_payload = dict(raw_art)
        art_payload["occupied_id"] = int(art_payload.get("occupied_id", 0) or 0)
        art = Artifact.model_validate(art_payload)
        artifacts_by_id[art.artifact_id] = art

    # 3. Monsters (json["unit_list"]) with O(1) metadata lookup (Zero N+1 calls)
    for raw_unit in data.get("unit_list") or []:
        if not isinstance(raw_unit, dict):
            continue
        if "unit_id" not in raw_unit or "unit_master_id" not in raw_unit:
            continue

        unit_id = int(raw_unit["unit_id"])
        unit_master_id = int(raw_unit["unit_master_id"])
        element_hint = raw_unit.get("element") or raw_unit.get("attribute")

        meta = monster_service.get_monster_metadata(
            com2us_id=unit_master_id,
            element_hint=element_hint,
        )

        unit_rune_ids: list[int] = []
        for raw_rune in _extract_unit_runes(raw_unit.get("runes", [])):
            if "rune_id" not in raw_rune:
                continue
            rune_payload = dict(raw_rune)
            rune_payload["occupied_id"] = unit_id
            rune = Rune.model_validate(rune_payload)
            runes_by_id[rune.rune_id] = rune
            unit_rune_ids.append(rune.rune_id)

        unit_artifact_ids: list[int] = []
        for raw_art in _extract_unit_runes(raw_unit.get("artifacts", [])):
            art_payload = dict(raw_art)
            art_payload["occupied_id"] = unit_id
            art = Artifact.model_validate(art_payload)
            artifacts_by_id[art.artifact_id] = art
            unit_artifact_ids.append(art.artifact_id)

        resolved_element = str(raw_unit.get("element") or meta.element or infer_element_from_com2us_id(unit_master_id))
        resolved_name = str(raw_unit.get("name") or meta.name or format_unknown_monster_name(unit_master_id, resolved_element))
        homunculus_name = str(raw_unit.get("homunculus_name") or "").strip()
        if raw_unit.get("homunculus") == 1 and homunculus_name and homunculus_name not in resolved_name:
            resolved_name = f"{resolved_name} ({homunculus_name})"

        monster = Monster(
            unit_id=unit_id,
            unit_master_id=unit_master_id,
            name=resolved_name,
            element=resolved_element,
            archetype=str(raw_unit.get("archetype") or "Unknown"),
            base_stars=int(raw_unit.get("base_stars") or meta.base_stars or 5),
            awaken_level=int(raw_unit.get("awaken_level") if raw_unit.get("awaken_level") is not None else meta.awaken_level),
            image_filename=str(raw_unit.get("image_filename") or meta.image_filename or ""),
            unit_level=int(raw_unit.get("unit_level", 40)),
            unit_class=int(raw_unit.get("class", 6)),
            con=int(raw_unit.get("con", 0)),
            atk=int(raw_unit.get("atk", 0)),
            def_=int(raw_unit.get("def", 0)),
            spd=int(raw_unit.get("spd", 100)),
            critical_rate=int(raw_unit.get("critical_rate", 15)),
            critical_damage=int(raw_unit.get("critical_damage", 50)),
            resist=int(raw_unit.get("resist", 15)),
            accuracy=int(raw_unit.get("accuracy", 0)),
            runes=unit_rune_ids,
            artifacts=unit_artifact_ids,
        )
        monsters_by_id[unit_id] = monster

    # 4. RTA equipped runes mapping (world_arena_rune_equip_list or world_arena_rune_equip_sync)
    rta_rune_equip_map: dict[int, int] = {}
    raw_rta_runes = data.get("world_arena_rune_equip_list") or []
    if raw_rta_runes:
        for entry in raw_rta_runes:
            if not isinstance(entry, dict):
                continue
            if "rune_id" not in entry or "occupied_id" not in entry:
                continue
            rune_id = int(entry["rune_id"])
            occupied_id = int(entry["occupied_id"])
            rta_rune_equip_map[rune_id] = occupied_id
            if rune_id in runes_by_id:
                runes_by_id[rune_id].rta_occupied_id = occupied_id
            if occupied_id in monsters_by_id and rune_id in runes_by_id:
                if rune_id not in monsters_by_id[occupied_id].rta_runes:
                    monsters_by_id[occupied_id].rta_runes.append(rune_id)
    elif int(data.get("world_arena_rune_equip_sync", 0) or 0) == 1:
        for monster in monsters_by_id.values():
            monster.rta_runes = list(monster.runes)
            for rune_id in monster.runes:
                rta_rune_equip_map[rune_id] = monster.unit_id
                if rune_id in runes_by_id:
                    runes_by_id[rune_id].rta_occupied_id = monster.unit_id

    # 5. RTA equipped artifacts mapping (world_arena_artifact_equip_list or world_arena_artifact_equip_sync)
    rta_artifact_equip_map: dict[int, int] = {}
    raw_rta_arts = data.get("world_arena_artifact_equip_list") or []
    if raw_rta_arts:
        for entry in raw_rta_arts:
            if not isinstance(entry, dict):
                continue
            art_id = int(entry.get("artifact_id", entry.get("rid", 0)) or 0)
            occupied_id = int(entry.get("occupied_id", 0) or 0)
            if art_id and occupied_id:
                rta_artifact_equip_map[art_id] = occupied_id
                if art_id in artifacts_by_id:
                    artifacts_by_id[art_id].rta_occupied_id = occupied_id
                if occupied_id in monsters_by_id and art_id in artifacts_by_id:
                    if art_id not in monsters_by_id[occupied_id].rta_artifacts:
                        monsters_by_id[occupied_id].rta_artifacts.append(art_id)
    elif int(data.get("world_arena_artifact_equip_sync", 0) or 0) == 1:
        for monster in monsters_by_id.values():
            monster.rta_artifacts = list(monster.artifacts)
            for art_id in monster.artifacts:
                rta_artifact_equip_map[art_id] = monster.unit_id
                if art_id in artifacts_by_id:
                    artifacts_by_id[art_id].rta_occupied_id = monster.unit_id

    return AccountProfile(
        wizard_id=wizard_id,
        wizard_name=wizard_name,
        wizard_level=wizard_level,
        wizard_mana=wizard_mana,
        wizard_crystal=wizard_crystal,
        monsters=monsters_by_id,
        runes=runes_by_id,
        artifacts=artifacts_by_id,
        rta_rune_equip_map=rta_rune_equip_map,
        rta_artifact_equip_map=rta_artifact_equip_map,
    )
