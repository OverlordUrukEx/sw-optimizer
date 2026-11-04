"""Lector del JSON de SWEX y sincronizador de Bestiario con SWARFARM (con caché SQLite)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from src.models import (
    AccountProfile,
    Artifact,
    Monster,
    MonsterMasterData,
    Rune,
)

SWARFARM_API_URL = "https://swarfarm.com/api/v2/monsters/"
DEFAULT_CACHE_PATH = Path("data/bestiary_cache.sqlite")

# Diccionario semilla local de monstruos populares de Summoners War (com2us_id -> metadata)
# Garantiza funcionamiento offline inmediato y tests deterministas sin depender de red.
BUILTIN_BESTIARY_SEED: dict[int, dict[str, Any]] = {
    10111: {
        "com2us_id": 10111,
        "name": "Fairy (Elucia)",
        "element": "Water",
        "archetype": "Support",
        "awaken_level": 1,
        "base_stars": 3,
        "image_filename": "unit_icon_0001_0_0.png",
        "skills": [1001, 1002, 1003],
    },
    10612: {
        "com2us_id": 10612,
        "name": "Inugami (Raoq) 2A",
        "element": "Fire",
        "archetype": "Attack",
        "awaken_level": 2,
        "base_stars": 3,
        "image_filename": "unit_icon_0006_1_4.png",
        "skills": [1401, 1402, 1403],
    },
    10615: {
        "com2us_id": 10615,
        "name": "Inugami (Kro) 2A",
        "element": "Dark",
        "archetype": "Attack",
        "awaken_level": 2,
        "base_stars": 3,
        "image_filename": "unit_icon_0006_4_4.png",
        "skills": [1411, 1412, 1413],
    },
    10614: {
        "com2us_id": 10614,
        "name": "Inugami (Belladeon) 2A",
        "element": "Light",
        "archetype": "Defense",
        "awaken_level": 2,
        "base_stars": 3,
        "image_filename": "unit_icon_0006_3_4.png",
        "skills": [1421, 1422, 1423],
    },
    11012: {
        "com2us_id": 11012,
        "name": "Griffon (Spectra) 2A",
        "element": "Fire",
        "archetype": "Support",
        "awaken_level": 2,
        "base_stars": 3,
        "image_filename": "unit_icon_0010_1_4.png",
        "skills": [1801, 1802, 1803],
    },
    11013: {
        "com2us_id": 11013,
        "name": "Griffon (Bernard) 2A",
        "element": "Wind",
        "archetype": "Support",
        "awaken_level": 2,
        "base_stars": 3,
        "image_filename": "unit_icon_0010_2_4.png",
        "skills": [1811, 1812, 1813],
    },
    13513: {
        "com2us_id": 13513,
        "name": "Lushen",
        "element": "Wind",
        "archetype": "Attack",
        "awaken_level": 1,
        "base_stars": 4,
        "image_filename": "unit_icon_0019_2_2.png",
        "skills": [4101, 4102, 4103],
    },
    14712: {
        "com2us_id": 14712,
        "name": "Verdehile",
        "element": "Fire",
        "archetype": "Attack",
        "awaken_level": 1,
        "base_stars": 4,
        "image_filename": "unit_icon_0025_1_2.png",
        "skills": [5201, 5202, 5203],
    },
    15714: {
        "com2us_id": 15714,
        "name": "Fran",
        "element": "Light",
        "archetype": "Support",
        "awaken_level": 1,
        "base_stars": 3,
        "image_filename": "unit_icon_0030_3_3.png",
        "skills": [6101, 6102, 6103],
    },
    18114: {
        "com2us_id": 18114,
        "name": "Loren",
        "element": "Light",
        "archetype": "Support",
        "awaken_level": 1,
        "base_stars": 3,
        "image_filename": "unit_icon_0042_3_1.png",
        "skills": [7201, 7202, 7203],
    },
    19215: {
        "com2us_id": 19215,
        "name": "Veromos",
        "element": "Dark",
        "archetype": "HP",
        "awaken_level": 1,
        "base_stars": 5,
        "image_filename": "unit_icon_0034_4_4.png",
        "skills": [7801, 7802, 7803],
    },
    19411: {
        "com2us_id": 19411,
        "name": "Galleon",
        "element": "Water",
        "archetype": "Support",
        "awaken_level": 1,
        "base_stars": 4,
        "image_filename": "unit_icon_0035_0_1.png",
        "skills": [8101, 8102, 8103],
    },
    19813: {
        "com2us_id": 19813,
        "name": "Tiana",
        "element": "Wind",
        "archetype": "Support",
        "awaken_level": 1,
        "base_stars": 5,
        "image_filename": "unit_icon_0037_2_3.png",
        "skills": [8501, 8502, 8503],
    },
    16213: {
        "com2us_id": 16213,
        "name": "Seara",
        "element": "Wind",
        "archetype": "Attack",
        "awaken_level": 1,
        "base_stars": 5,
        "image_filename": "unit_icon_0028_2_3.png",
        "skills": [6501, 6502, 6503],
    },
    24713: {
        "com2us_id": 24713,
        "name": "Oliver",
        "element": "Wind",
        "archetype": "Attack",
        "awaken_level": 1,
        "base_stars": 5,
        "image_filename": "unit_icon_0065_2_3.png",
        "skills": [12101, 12102, 12103],
    },
    24011: {
        "com2us_id": 24011,
        "name": "Moore",
        "element": "Water",
        "archetype": "Attack",
        "awaken_level": 1,
        "base_stars": 5,
        "image_filename": "unit_icon_0060_0_3.png",
        "skills": [11501, 11502, 11503],
    },
    14413: {
        "com2us_id": 14413,
        "name": "Teshar",
        "element": "Wind",
        "archetype": "Attack",
        "awaken_level": 1,
        "base_stars": 5,
        "image_filename": "unit_icon_0023_2_3.png",
        "skills": [5001, 5002, 5003],
    },
    14411: {
        "com2us_id": 14411,
        "name": "Sigmarus",
        "element": "Water",
        "archetype": "Attack",
        "awaken_level": 1,
        "base_stars": 5,
        "image_filename": "unit_icon_0023_0_3.png",
        "skills": [5011, 5012, 5013],
    },
    25113: {
        "com2us_id": 25113,
        "name": "Riley",
        "element": "Wind",
        "archetype": "Support",
        "awaken_level": 1,
        "base_stars": 5,
        "image_filename": "unit_icon_0068_2_3.png",
        "skills": [12501, 12502, 12503, 12504],
    },
    24212: {
        "com2us_id": 24212,
        "name": "Kaki",
        "element": "Fire",
        "archetype": "Attack",
        "awaken_level": 1,
        "base_stars": 4,
        "image_filename": "unit_icon_0062_1_2.png",
        "skills": [11701, 11702, 11703],
    },
}


class BestiaryCache:
    """Gestor de caché local SQLite para sincronizar metadatos de monstruos con SWARFARM."""

    def __init__(self, db_path: Path | str = DEFAULT_CACHE_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS monsters (
                    com2us_id INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            # Poblar semilla inicial si no existen las entradas
            for cid, data in BUILTIN_BESTIARY_SEED.items():
                conn.execute(
                    "INSERT OR IGNORE INTO monsters (com2us_id, payload) VALUES (?, ?)",
                    (cid, json.dumps(data)),
                )
            conn.commit()

    def get(self, com2us_id: int) -> MonsterMasterData | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT payload FROM monsters WHERE com2us_id = ?", (com2us_id,)
            ).fetchone()
            if row:
                return MonsterMasterData.model_validate_json(row[0])
        return None

    def set(self, master_data: MonsterMasterData) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO monsters (com2us_id, payload) VALUES (?, ?)",
                (master_data.com2us_id, master_data.model_dump_json()),
            )
            conn.commit()

    def fetch_or_sync(
        self, com2us_id: int, fetch_remote: bool = True, timeout: float = 3.0
    ) -> MonsterMasterData:
        """Obtiene del caché SQLite o consulta SWARFARM si no existe localmente."""
        cached = self.get(com2us_id)
        if cached is not None:
            return cached

        if fetch_remote:
            try:
                with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                    resp = client.get(SWARFARM_API_URL, params={"com2us_id": com2us_id})
                    if resp.status_code == 200:
                        body = resp.json()
                        results = body.get("results", [])
                        if results:
                            item = results[0]
                            master = MonsterMasterData(
                                com2us_id=com2us_id,
                                name=item.get("name", f"Monster #{com2us_id}"),
                                element=item.get("element", "Unknown"),
                                archetype=item.get("archetype", "Unknown"),
                                awaken_level=int(item.get("awaken_level", 1) or 1),
                                base_stars=int(item.get("base_stars", 5) or 5),
                                image_filename=item.get("image_filename") or "",
                                skills=[int(s) for s in item.get("skills", [])],
                                leader_skill=item.get("leader_skill"),
                            )
                            self.set(master)
                            return master
            except Exception:
                # Si no hay red o SWARFARM falla, usamos fallback seguro
                pass

        fallback = MonsterMasterData(
            com2us_id=com2us_id,
            name=f"Monster #{com2us_id}",
            element="Unknown",
            archetype="Unknown",
        )
        return fallback


def _extract_unit_runes(raw_runes: Any) -> list[dict[str, Any]]:
    """Normaliza unit['runes'] tanto si viene como lista como si viene como dict de slots."""
    if isinstance(raw_runes, list):
        return [r for r in raw_runes if isinstance(r, dict)]
    if isinstance(raw_runes, dict):
        return [r for r in raw_runes.values() if isinstance(r, dict)]
    return []


def parse_swex_json(
    source: str | Path | bytes | dict[str, Any],
    bestiary: BestiaryCache | None = None,
    fetch_remote_bestiary: bool = False,
) -> AccountProfile:
    """
    Parsea un archivo o diccionario JSON exportado por SWEX (Summoners War Exporter).

    Reglas aplicadas:
    - Monstruos: base_hp = con * 15.
    - Inventario PVE: unión de json['runes'] + unit['runes'] de cada monstruo en unit_list.
    - Inventario RTA: mapeado a través de json['world_arena_rune_equip_list'] (rune_id -> occupied_id).
    """
    if isinstance(source, dict):
        data = source
    elif isinstance(source, (bytes, bytearray)):
        data = json.loads(source.decode("utf-8"))
    elif isinstance(source, str):
        path_candidate = Path(source)
        if len(source) < 260 and path_candidate.exists() and path_candidate.is_file():
            data = json.loads(path_candidate.read_text(encoding="utf-8"))
        else:
            data = json.loads(source)
    elif isinstance(source, Path):
        data = json.loads(source.read_text(encoding="utf-8"))
    else:
        raise TypeError(f"Tipo de fuente no soportado: {type(source)}")

    cache = bestiary or BestiaryCache()

    wizard_info = data.get("wizard_info", {})
    wizard_id = int(wizard_info.get("wizard_id", data.get("wizard_id", 0)))
    wizard_name = str(wizard_info.get("wizard_name", "Summoner"))

    runes_by_id: dict[int, Rune] = {}
    artifacts_by_id: dict[int, Artifact] = {}
    monsters_by_id: dict[int, Monster] = {}

    # 1. Runas en inventario general (json["runes"])
    for raw_rune in data.get("runes", []) or []:
        if not isinstance(raw_rune, dict):
            continue
        rune_payload = dict(raw_rune)
        rune_payload["occupied_id"] = int(rune_payload.get("occupied_id", 0) or 0)
        rune = Rune.model_validate(rune_payload)
        runes_by_id[rune.rune_id] = rune

    # 2. Artefactos en inventario general (json["artifacts"])
    for raw_art in data.get("artifacts", []) or []:
        if not isinstance(raw_art, dict):
            continue
        art_payload = dict(raw_art)
        art_payload["occupied_id"] = int(art_payload.get("occupied_id", 0) or 0)
        art = Artifact.model_validate(art_payload)
        artifacts_by_id[art.artifact_id] = art

    # 3. Monstruos (json["unit_list"]) y sus runas/artefactos equipados en modo Normal (PVE/PVP)
    for raw_unit in data.get("unit_list", []) or []:
        if not isinstance(raw_unit, dict):
            continue
        unit_id = int(raw_unit["unit_id"])
        unit_master_id = int(raw_unit["unit_master_id"])

        master_meta = cache.fetch_or_sync(
            unit_master_id, fetch_remote=fetch_remote_bestiary
        )

        unit_rune_ids: list[int] = []
        for raw_rune in _extract_unit_runes(raw_unit.get("runes", [])):
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

        monster = Monster(
            unit_id=unit_id,
            unit_master_id=unit_master_id,
            name=raw_unit.get("name") or master_meta.name,
            element=raw_unit.get("element") or master_meta.element,
            archetype=raw_unit.get("archetype") or master_meta.archetype,
            image_filename=master_meta.image_filename,
            unit_level=int(raw_unit.get("unit_level", 40)),
            unit_class=int(raw_unit.get("class", 6)),
            con=int(raw_unit["con"]),
            atk=int(raw_unit["atk"]),
            def_=int(raw_unit["def"]),
            spd=int(raw_unit["spd"]),
            critical_rate=int(raw_unit.get("critical_rate", 15)),
            critical_damage=int(raw_unit.get("critical_damage", 50)),
            resist=int(raw_unit.get("resist", 15)),
            accuracy=int(raw_unit.get("accuracy", 0)),
            runes=unit_rune_ids,
            artifacts=unit_artifact_ids,
        )
        monsters_by_id[unit_id] = monster

    # 4. Mapeo de runas equipadas en RTA (world_arena_rune_equip_list)
    rta_rune_equip_map: dict[int, int] = {}
    for entry in data.get("world_arena_rune_equip_list", []) or []:
        if not isinstance(entry, dict):
            continue
        rune_id = int(entry["rune_id"])
        occupied_id = int(entry["occupied_id"])
        rta_rune_equip_map[rune_id] = occupied_id
        if rune_id in runes_by_id:
            runes_by_id[rune_id].rta_occupied_id = occupied_id
        if occupied_id in monsters_by_id and rune_id in runes_by_id:
            if rune_id not in monsters_by_id[occupied_id].rta_runes:
                monsters_by_id[occupied_id].rta_runes.append(rune_id)

    # 5. Mapeo de artefactos equipados en RTA (world_arena_artifact_equip_list)
    rta_artifact_equip_map: dict[int, int] = {}
    for entry in data.get("world_arena_artifact_equip_list", []) or []:
        if not isinstance(entry, dict):
            continue
        art_id = int(entry.get("artifact_id", entry.get("rid", 0)))
        occupied_id = int(entry["occupied_id"])
        if art_id:
            rta_artifact_equip_map[art_id] = occupied_id
            if art_id in artifacts_by_id:
                artifacts_by_id[art_id].rta_occupied_id = occupied_id
            if occupied_id in monsters_by_id and art_id in artifacts_by_id:
                if art_id not in monsters_by_id[occupied_id].rta_artifacts:
                    monsters_by_id[occupied_id].rta_artifacts.append(art_id)

    return AccountProfile(
        wizard_id=wizard_id,
        wizard_name=wizard_name,
        monsters=monsters_by_id,
        runes=runes_by_id,
        artifacts=artifacts_by_id,
        rta_rune_equip_map=rta_rune_equip_map,
        rta_artifact_equip_map=rta_artifact_equip_map,
    )

